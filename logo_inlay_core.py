from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image
import shutil
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union, triangulate
try:
    from shapely import constrained_delaunay_triangles
except Exception:
    constrained_delaunay_triangles = None
from shapely.affinity import translate, scale as scale_geom
import trimesh

try:
    import mapbox_earcut as earcut
except Exception:
    earcut = None


def safe_filename_part(text: str) -> str:
    text = text.lower().replace("ß", "ss")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = text.strip("_")
    return text or "logo"



OUTPUT_GROUP_NAMES = {
    "schwarz": "black",
    "weiss": "white",
    "weiß": "white",
    "gelb": "yellow",
    "gruen": "green",
    "grün": "green",
    "blau": "blue",
    "hellblau": "light_blue",
    "rot": "red",
    "orange": "orange",
    "grau": "gray",
    "lila": "purple",
    "pink": "pink",
    "braun": "brown",
    "beige": "beige",
}

def english_output_group_name(group_name: str) -> str:
    """Convert built-in internal group names to readable English filenames."""
    text = str(group_name or "").strip()
    lower = text.lower()

    if lower in OUTPUT_GROUP_NAMES:
        return OUTPUT_GROUP_NAMES[lower]

    # Preserve numbered variants such as "rot 2" -> "red_2".
    match = re.match(r"^(.*?)(?:\s+)(\d+)$", lower)
    if match and match.group(1) in OUTPUT_GROUP_NAMES:
        return f"{OUTPUT_GROUP_NAMES[match.group(1)]}_{match.group(2)}"

    # Custom group names are kept, only made filesystem-safe.
    return safe_filename_part(text).lower()


def prepare_input_image(image_path: Path, work_dir: Path, project: str, working_pixels: int) -> Path:
    """Only raster images are supported as input."""
    if image_path.suffix.lower() == ".svg":
        raise RuntimeError("SVG Import wurde entfernt. Bitte das Logo vorher als PNG exportieren.")
    return image_path


def save_input_copies(original_path: Path, out_dir: Path, project: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = original_path.suffix.lower() or ".png"
    if suffix != ".svg":
        shutil.copy2(original_path, out_dir / f"{project}_original{suffix}")


def closest_color_name(rgb: Iterable[int]) -> str:
    r, g, b = [int(x) for x in rgb]
    palette = {
        "schwarz": (18, 18, 18),
        "weiss": (245, 245, 245),
        "grau": (130, 130, 130),
        "rot": (220, 45, 45),
        "orange": (240, 130, 35),
        "gelb": (240, 220, 60),
        "gruen": (70, 165, 80),
        "blau": (45, 95, 220),
        "hellblau": (90, 180, 230),
        "lila": (140, 75, 180),
        "pink": (230, 80, 160),
        "braun": (125, 80, 45),
        "beige": (220, 190, 145),
    }
    def dist(c):
        return (r - c[0]) ** 2 + (g - c[1]) ** 2 + (b - c[2]) ** 2
    return min(palette.items(), key=lambda item: dist(item[1]))[0]


def load_rgba(path: Path, working_pixels: int) -> np.ndarray:
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    scale = min(1.0, working_pixels / max(w, h))
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    return np.array(img)


def build_visible_mask(rgba: np.ndarray, background_mode: str, white_threshold: int) -> np.ndarray:
    alpha = rgba[:, :, 3]
    rgb = rgba[:, :, :3]
    visible = alpha > 10

    if background_mode == "transparent":
        return visible
    if background_mode == "white":
        not_white = ~((rgb[:, :, 0] >= white_threshold) & (rgb[:, :, 1] >= white_threshold) & (rgb[:, :, 2] >= white_threshold))
        return visible & not_white
    if background_mode == "corner":
        h, w = alpha.shape
        corners = np.array([rgb[0, 0], rgb[0, w-1], rgb[h-1, 0], rgb[h-1, w-1]], dtype=np.float32)
        bg = np.median(corners, axis=0)
        diff = np.linalg.norm(rgb.astype(np.float32) - bg, axis=2)
        return visible & (diff > 28)
    return visible


def quantize(rgba: np.ndarray, visible: np.ndarray, k: int):
    rgb = rgba[:, :, :3]
    pixels = rgb[visible].reshape((-1, 3)).astype(np.float32)
    if len(pixels) == 0:
        raise ValueError("No visible pixels were found in the selected image.")
    k = max(1, min(k, len(np.unique(pixels.astype(np.uint8), axis=0))))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.12)
    _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)
    centers = np.clip(centers, 0, 255).astype(np.uint8)
    label_img = np.full(visible.shape, -1, dtype=np.int32)
    label_img[visible] = labels.flatten()
    return label_img, centers


def merge_similar_clusters(label_img, centers, distance):
    if len(centers) <= 1 or distance <= 0:
        return label_img, centers
    parent = list(range(len(centers)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a,b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for i in range(len(centers)):
        for j in range(i + 1, len(centers)):
            if np.linalg.norm(centers[i].astype(float) - centers[j].astype(float)) <= distance:
                union(i, j)
    groups = {}
    for i in range(len(centers)):
        groups.setdefault(find(i), []).append(i)
    new_label = np.full_like(label_img, -1)
    new_centers = []
    for new_idx, group in enumerate(groups.values()):
        mask = np.isin(label_img, group)
        if np.any(mask):
            avg = np.mean(np.array([centers[g] for g in group], dtype=float), axis=0)
            new_centers.append(np.clip(avg, 0, 255).astype(np.uint8))
            new_label[mask] = new_idx
    return new_label, np.array(new_centers, dtype=np.uint8)



def remove_edge_background_rgba(rgba, tolerance=18):
    """Remove only background-like pixels connected to the image border.

    This implementation uses connected components instead of repeatedly flood
    filling from every edge pixel. It is faster and avoids integer overflow in
    RGB distance calculations.
    """
    arr = rgba.copy()
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3]

    edge_pixels = np.concatenate([
        rgb[0, :, :],
        rgb[h - 1, :, :],
        rgb[:, 0, :],
        rgb[:, w - 1, :],
    ], axis=0)
    bg = np.median(edge_pixels, axis=0).astype(np.float32)

    diff = np.linalg.norm(rgb - bg, axis=2)
    candidate = (diff <= float(tolerance)) & (alpha > 0)

    if not np.any(candidate):
        return arr

    count, labels = cv2.connectedComponents(candidate.astype(np.uint8), connectivity=8)
    if count <= 1:
        return arr

    border_labels = np.unique(np.concatenate([
        labels[0, :],
        labels[h - 1, :],
        labels[:, 0],
        labels[:, w - 1],
    ]))
    border_labels = border_labels[border_labels != 0]

    if len(border_labels):
        remove = np.isin(labels, border_labels)
        arr[remove, 3] = 0

    return arr

def analyze_colors(
    image_path: Path,
    working_pixels: int = 1400,
    detect_colors: int = 8,
    background_mode: str = "transparent",
    white_threshold: int = 245,
    auto_merge: bool = True,
    merge_distance: float = 18.0,
):
    project = safe_filename_part(image_path.stem)
    temp_dir = image_path.parent / ".logo_inlay_temp"
    raster_path = prepare_input_image(image_path, temp_dir, project, working_pixels)
    rgba = load_rgba(raster_path, working_pixels)
    if background_mode == "edge":
        rgba = remove_edge_background_rgba(rgba, tolerance=18)
    visible = build_visible_mask(rgba, background_mode, white_threshold)
    label_img, centers = quantize(rgba, visible, detect_colors)
    if auto_merge:
        label_img, centers = merge_similar_clusters(label_img, centers, merge_distance)

    total = int(np.sum(label_img >= 0))
    colors = []
    for idx, c in enumerate(centers):
        count = int(np.sum(label_img == idx))
        if count == 0:
            continue
        colors.append({
            "cluster": int(idx),
            "name": closest_color_name(c),
            "rgb": [int(x) for x in c],
            "pixel_count": count,
            "percent": round(100 * count / total, 1) if total else 0,
            "enabled": True,
            "group": closest_color_name(c),
        })
    colors.sort(key=lambda x: x["pixel_count"], reverse=True)
    return {
        "width_px": int(rgba.shape[1]),
        "height_px": int(rgba.shape[0]),
        "colors": colors,
        "label_img": label_img,
        "centers": centers,
        "rgba": rgba,
    }


def clean_mask(mask: np.ndarray, min_area_px: int, close_strength: int) -> np.ndarray:
    mask_u8 = (mask.astype(np.uint8) * 255)
    if close_strength > 0:
        k = 2 * close_strength + 1
        kernel = np.ones((k, k), np.uint8)
        mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_CLOSE, kernel)
        mask_u8 = cv2.morphologyEx(mask_u8, cv2.MORPH_OPEN, kernel)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8, 8)
    cleaned = np.zeros_like(mask_u8)
    for i in range(1, num):
        if stats[i, cv2.CC_STAT_AREA] >= min_area_px:
            cleaned[labels == i] = 255
    return cleaned > 0


def contour_to_polygons(mask: np.ndarray, mm_per_px: float, simplify_mm: float, contour_mode: str) -> MultiPolygon:
    mask_u8 = (mask.astype(np.uint8) * 255)
    if contour_mode == "smooth":
        method = cv2.CHAIN_APPROX_TC89_KCOS
    elif contour_mode == "detail":
        method = cv2.CHAIN_APPROX_NONE
    else:
        method = cv2.CHAIN_APPROX_SIMPLE
    contours, hierarchy = cv2.findContours(mask_u8, cv2.RETR_CCOMP, method)
    if hierarchy is None:
        return MultiPolygon([])
    hierarchy = hierarchy[0]
    h, _ = mask.shape
    polys = []
    for idx, cnt in enumerate(contours):
        if hierarchy[idx][3] != -1:
            continue
        eps = max(0.01, simplify_mm / mm_per_px)
        outer = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
        if len(outer) < 3:
            continue
        outer_xy = [(float(x)*mm_per_px, float(h-y)*mm_per_px) for x,y in outer]
        holes = []
        child = hierarchy[idx][2]
        while child != -1:
            hole = cv2.approxPolyDP(contours[child], eps, True).reshape(-1, 2)
            if len(hole) >= 3:
                holes.append([(float(x)*mm_per_px, float(h-y)*mm_per_px) for x,y in hole])
            child = hierarchy[child][0]
        poly = Polygon(outer_xy, holes)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if not poly.is_empty and poly.area > 0:
            polys.append(poly)
    if not polys:
        return MultiPolygon([])
    merged = unary_union(polys).buffer(0)
    if isinstance(merged, Polygon):
        return MultiPolygon([merged])
    if isinstance(merged, MultiPolygon):
        return merged
    return MultiPolygon([g for g in getattr(merged, "geoms", []) if isinstance(g, Polygon)])



def external_silhouette_to_polygons(mask: np.ndarray, mm_per_px: float, simplify_mm: float, contour_mode: str):
    """Build only the OUTER silhouette of a mask.

    Internal holes are deliberately ignored. This makes the total cutting body
    solid; only the outer/background region is removed.
    """
    mask_u8 = mask.astype(np.uint8) * 255
    if contour_mode == "smooth":
        method = cv2.CHAIN_APPROX_TC89_KCOS
    elif contour_mode == "detail":
        method = cv2.CHAIN_APPROX_NONE
    else:
        method = cv2.CHAIN_APPROX_SIMPLE

    contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, method)
    if not contours:
        return MultiPolygon([])

    h, _ = mask.shape
    eps = max(0.01, simplify_mm / mm_per_px)
    polys = []
    for cnt in contours:
        outer = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
        if len(outer) < 3:
            continue
        outer_xy = [(float(x) * mm_per_px, float(h-y) * mm_per_px) for x, y in outer]
        poly = Polygon(outer_xy)
        if not poly.is_valid:
            poly = poly.buffer(0)
        for p in iter_polygons(poly):
            if not p.is_empty and p.area > 0:
                # Explicitly drop interior rings: total body must be solid.
                polys.append(Polygon(p.exterior.coords))

    if not polys:
        return MultiPolygon([])
    return unary_union(polys).buffer(0)


def _smooth_binary_mask(mask: np.ndarray, smoothing_mm: float, mm_per_px: float) -> np.ndarray:
    """Smooth a binary boundary using a Gaussian measured in real millimetres."""
    mask = mask.astype(bool)
    if smoothing_mm <= 0 or mm_per_px <= 0 or not np.any(mask):
        return mask.copy()

    # Treat smoothing_mm as an approximate visible boundary smoothing radius.
    radius_px = max(1.0, float(smoothing_mm) / float(mm_per_px))
    sigma = max(0.6, radius_px / 2.0)
    half = max(1, int(np.ceil(sigma * 3.0)))
    k = 2 * half + 1

    blurred = cv2.GaussianBlur(
        mask.astype(np.float32),
        (k, k),
        sigmaX=sigma,
        sigmaY=sigma,
        borderType=cv2.BORDER_REPLICATE,
    )
    return blurred >= 0.5


def smooth_group_partition(label_img: np.ndarray, groups: dict,
                           mm_per_px: float, smoothing_mm: float = 0.18):
    """Create a gap-free group raster with visibly smoothed shared boundaries.

    Unlike the old implementation, smoothing is measured in real millimetres
    and also changes the common outer silhouette. All groups are blurred
    together and resolved by winner-takes-all, so shared borders remain exact
    and cannot create gaps.
    """
    names = list(groups.keys())
    group_map = np.full(label_img.shape, -1, dtype=np.int16)
    for gid, name in enumerate(names):
        group_map[np.isin(label_img, groups[name])] = gid

    active = group_map >= 0
    if not np.any(active):
        return names, group_map, active

    if smoothing_mm <= 0 or len(names) <= 1:
        return names, group_map, active.copy()

    radius_px = max(1.0, float(smoothing_mm) / float(mm_per_px))
    sigma = max(0.6, radius_px / 2.0)
    half = max(1, int(np.ceil(sigma * 3.0)))
    k = 2 * half + 1

    # Smooth overall silhouette as well as group boundaries.
    smoothed_active = _smooth_binary_mask(active, smoothing_mm, mm_per_px)

    scores = []
    for gid in range(len(names)):
        channel = (group_map == gid).astype(np.float32)
        score = cv2.GaussianBlur(
            channel,
            (k, k),
            sigmaX=sigma,
            sigmaY=sigma,
            borderType=cv2.BORDER_REPLICATE,
        )
        scores.append(score)

    stack = np.stack(scores, axis=0)
    winners = np.argmax(stack, axis=0).astype(np.int16)

    out = np.full(group_map.shape, -1, dtype=np.int16)
    out[smoothed_active] = winners[smoothed_active]
    return names, out, smoothed_active



def _stable_raster_components(group_map: np.ndarray, min_area_px: int):
    """Return a map containing only stable (non-tiny) 4-connected components.

    Pixels belonging to tiny components are -1. This lets tiny artifacts choose
    only genuinely stable neighboring colors instead of one tiny artifact
    pulling another tiny artifact into the wrong group.
    """
    stable = np.full(group_map.shape, -1, dtype=np.int16)
    threshold = max(1, int(min_area_px))

    gids = [int(v) for v in np.unique(group_map) if int(v) >= 0]
    for gid in gids:
        mask = (group_map == gid).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask, connectivity=4
        )
        for cid in range(1, count):
            area = int(stats[cid, cv2.CC_STAT_AREA])
            if area >= threshold:
                stable[labels == cid] = gid
    return stable


def _component_edge_neighbor_counts(
    component_mask: np.ndarray,
    stable_group_map: np.ndarray,
):
    """Count real shared pixel EDGES from a component to stable print colors."""
    component_mask = np.asarray(component_mask, dtype=bool)
    h, w = component_mask.shape
    counts = {}

    ys, xs = np.nonzero(component_mask)
    for y, x in zip(ys, xs):
        if y > 0 and not component_mask[y - 1, x]:
            gid = int(stable_group_map[y - 1, x])
            if gid >= 0:
                counts[gid] = counts.get(gid, 0) + 1
        if y + 1 < h and not component_mask[y + 1, x]:
            gid = int(stable_group_map[y + 1, x])
            if gid >= 0:
                counts[gid] = counts.get(gid, 0) + 1
        if x > 0 and not component_mask[y, x - 1]:
            gid = int(stable_group_map[y, x - 1])
            if gid >= 0:
                counts[gid] = counts.get(gid, 0) + 1
        if x + 1 < w and not component_mask[y, x + 1]:
            gid = int(stable_group_map[y, x + 1])
            if gid >= 0:
                counts[gid] = counts.get(gid, 0) + 1

    return counts


def _component_local_majority_counts(
    component_mask: np.ndarray,
    stable_group_map: np.ndarray,
    candidate_gids,
    radius_px: int = 2,
):
    """Tie-break edge contact using the local stable-color majority around it.

    Candidates are already proven edge-neighbors; this function never adds a new
    color that did not share an edge with the component.
    """
    candidate_gids = {int(v) for v in candidate_gids}
    if not candidate_gids:
        return {}

    mask = component_mask.astype(np.uint8)
    radius = max(1, int(radius_px))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1)
    )
    dilated = cv2.dilate(mask, kernel, iterations=1).astype(bool)
    ring = dilated & (~component_mask)

    values = stable_group_map[ring]
    out = {}
    for gid in candidate_gids:
        out[gid] = int(np.count_nonzero(values == gid))
    return out


def _reassign_tiny_raster_components(
    group_map: np.ndarray,
    active_mask: np.ndarray,
    min_area_px: int,
):
    """Clean tiny wrong-color raster islands before vectorization.

    Rules:
      * components are 4-connected;
      * only colors sharing a REAL PIXEL EDGE are eligible;
      * the color with the most shared edges wins;
      * a local-majority vote is used only to break a true edge-count tie;
      * diagonal/non-touching colors are never candidates;
      * components surrounded only by background are preserved.

    Performance:
      Each tiny component is processed only inside its own small bounding box,
      rather than allocating a full-image mask per component. This keeps the
      cleanup practical even when a high-resolution logo contains hundreds or
      thousands of tiny artifacts.
    """
    threshold = max(1, int(min_area_px))
    original = np.asarray(group_map, dtype=np.int16)
    if threshold <= 1:
        return original.copy()

    result = original.copy()
    stable_map = _stable_raster_components(original, threshold)
    image_h, image_w = original.shape

    gids = [int(v) for v in np.unique(original) if int(v) >= 0]

    for gid in gids:
        mask = (original == gid).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            mask, connectivity=4
        )

        for cid in range(1, count):
            area = int(stats[cid, cv2.CC_STAT_AREA])
            if area >= threshold:
                continue

            x = int(stats[cid, cv2.CC_STAT_LEFT])
            y = int(stats[cid, cv2.CC_STAT_TOP])
            cw = int(stats[cid, cv2.CC_STAT_WIDTH])
            ch = int(stats[cid, cv2.CC_STAT_HEIGHT])

            # Two pixels of padding support direct edge counting plus the
            # radius-2 tie-break neighborhood.
            pad = 2
            x0 = max(0, x - pad)
            y0 = max(0, y - pad)
            x1 = min(image_w, x + cw + pad)
            y1 = min(image_h, y + ch + pad)

            cc_roi = labels[y0:y1, x0:x1]
            component = cc_roi == cid
            stable_roi = stable_map[y0:y1, x0:x1]

            edge_counts = _component_edge_neighbor_counts(
                component, stable_roi
            )
            edge_counts = {
                ngid: score
                for ngid, score in edge_counts.items()
                if ngid >= 0 and ngid != gid and score > 0
            }

            if not edge_counts:
                # Isolated tiny detail in background: preserve it.
                continue

            best_edges = max(edge_counts.values())
            tied = [
                ngid for ngid, score in edge_counts.items()
                if score == best_edges
            ]

            if len(tied) == 1:
                owner = tied[0]
            else:
                local_counts = _component_local_majority_counts(
                    component,
                    stable_roi,
                    tied,
                    radius_px=2,
                )
                best_local = max(local_counts.get(v, 0) for v in tied)
                tied2 = [
                    v for v in tied
                    if local_counts.get(v, 0) == best_local
                ]
                owner = min(tied2)

            result_roi = result[y0:y1, x0:x1]
            result_roi[component] = int(owner)

    result[~np.asarray(active_mask, dtype=bool)] = -1
    return result



def _polygon_raster_edge_neighbor_counts(
    polygon: Polygon,
    group_map: np.ndarray,
    mm_per_px: float,
):
    """Count direct 4-neighbor raster colors around a vector gap polygon.

    This examines the ring immediately OUTSIDE the rasterized gap. It therefore
    answers the useful question for gap filling: "which colors actually surround
    this hole, and how much of its local boundary do they occupy?"
    """
    if polygon is None or polygon.is_empty or polygon.area <= 0 or mm_per_px <= 0:
        return {}

    h, w = group_map.shape
    minx, miny, maxx, maxy = polygon.bounds

    # Two pixels of padding are enough to capture a direct 4-neighbor ring.
    x0 = max(0, int(np.floor(minx / mm_per_px)) - 2)
    x1 = min(w - 1, int(np.ceil(maxx / mm_per_px)) + 2)
    y0 = max(0, int(np.floor(h - (maxy / mm_per_px))) - 2)
    y1 = min(h - 1, int(np.ceil(h - (miny / mm_per_px))) + 2)

    if x1 < x0 or y1 < y0:
        return {}

    local = np.zeros((y1 - y0 + 1, x1 - x0 + 1), dtype=np.uint8)

    def ring_to_pixels(ring):
        pts = []
        for x, y in ring.coords:
            px = int(round(x / mm_per_px)) - x0
            py = int(round(h - (y / mm_per_px))) - y0
            pts.append([px, py])
        return np.asarray(pts, dtype=np.int32)

    try:
        outer = ring_to_pixels(polygon.exterior)
        if len(outer) >= 3:
            cv2.fillPoly(local, [outer], 1)
        for hole in polygon.interiors:
            pts = ring_to_pixels(hole)
            if len(pts) >= 3:
                cv2.fillPoly(local, [pts], 0)
    except Exception:
        return {}

    inside = local.astype(bool)
    if not np.any(inside):
        return {}

    # Cross kernel = strict edge adjacency. Diagonals do not count.
    cross = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    dilated = cv2.dilate(local, cross, iterations=1).astype(bool)
    ring = dilated & (~inside)

    values = group_map[y0:y1 + 1, x0:x1 + 1][ring]
    values = values[values >= 0]
    if values.size == 0:
        return {}

    ids, counts = np.unique(values.astype(np.int32), return_counts=True)
    return {
        int(gid): int(count)
        for gid, count in zip(ids, counts)
        if int(count) > 0
    }


def _gap_pixel_vote(gap: Polygon, group_map: np.ndarray, mm_per_px: float):
    """Return the raster group id that locally owns most of a vectorization gap.

    The smoothed raster partition is the last unambiguous color assignment
    before contour simplification. Mapping tiny leftover polygons back onto it
    gives us a local owner instead of assigning every gap to the globally
    largest color.
    """
    if gap.is_empty or gap.area <= 0 or mm_per_px <= 0:
        return None

    h, w = group_map.shape
    minx, miny, maxx, maxy = gap.bounds

    x0 = max(0, int(np.floor(minx / mm_per_px)) - 1)
    x1 = min(w - 1, int(np.ceil(maxx / mm_per_px)) + 1)
    y0 = max(0, int(np.floor(h - (maxy / mm_per_px))) - 1)
    y1 = min(h - 1, int(np.ceil(h - (miny / mm_per_px))) + 1)

    if x1 < x0 or y1 < y0:
        return None

    local = np.zeros((y1 - y0 + 1, x1 - x0 + 1), dtype=np.uint8)

    def ring_to_pixels(ring):
        pts = []
        for x, y in ring.coords:
            px = int(round(x / mm_per_px)) - x0
            py = int(round(h - (y / mm_per_px))) - y0
            pts.append([px, py])
        return np.asarray(pts, dtype=np.int32)

    try:
        outer = ring_to_pixels(gap.exterior)
        if len(outer) >= 3:
            cv2.fillPoly(local, [outer], 1)
        for hole in gap.interiors:
            pts = ring_to_pixels(hole)
            if len(pts) >= 3:
                cv2.fillPoly(local, [pts], 0)
    except Exception:
        return None

    labels = group_map[y0:y1 + 1, x0:x1 + 1][local.astype(bool)]
    labels = labels[labels >= 0]
    if labels.size == 0:
        return None

    ids, counts = np.unique(labels.astype(np.int32), return_counts=True)
    if ids.size == 0:
        return None

    return int(ids[int(np.argmax(counts))])


def _choose_local_gap_owner(
    gap: Polygon,
    names: list[str],
    group_map: np.ndarray,
    mm_per_px: float,
    partition: dict,
    raw: dict,
    simplify_mm: float,
):
    """Choose a vector-gap owner from proven physical adjacency only.

    V8.1 final rules:
      1. Direct 4-neighbor raster ring: most represented color wins.
      2. An exact tie may be broken by shared vector-boundary length, but only
         between those same directly adjacent raster colors.
      3. If the raster ring cannot represent a sub-pixel gap, a TRUE shared
         vector boundary may be used.
      4. Otherwise return None and report the unresolved gap.

    No inside-gap vote, distance search, RGB search, near-color search or
    largest-group fallback remains.
    """
    if gap is None or gap.is_empty or gap.area <= 0:
        return None

    # 1) Strict direct-edge raster neighborhood.
    raster_counts = _polygon_raster_edge_neighbor_counts(
        gap, group_map, mm_per_px
    )
    if raster_counts:
        valid = [
            (int(count), int(gid), names[int(gid)])
            for gid, count in raster_counts.items()
            if 0 <= int(gid) < len(names) and int(count) > 0
        ]
        if valid:
            best_count = max(count for count, _, _ in valid)
            tied = [
                (gid, name)
                for count, gid, name in valid
                if count == best_count
            ]

            if len(tied) == 1:
                return tied[0][1]

            # Exact tie only. No new candidate can enter here.
            boundary_scores = []
            for gid, name in tied:
                geom = partition.get(name)
                if geom is None or geom.is_empty:
                    shared = 0.0
                else:
                    try:
                        shared = float(
                            gap.boundary.intersection(geom.boundary).length
                        )
                    except Exception:
                        shared = 0.0
                boundary_scores.append((shared, name))

            boundary_scores.sort(key=lambda item: (-item[0], item[1]))
            return boundary_scores[0][1]

    # 2) True shared vector boundary is also proven physical adjacency.
    exact_contacts = []
    for name in names:
        geom = partition.get(name)
        if geom is None or geom.is_empty:
            continue
        try:
            shared = float(gap.boundary.intersection(geom.boundary).length)
        except Exception:
            shared = 0.0
        if shared > 1e-10:
            exact_contacts.append((shared, name))

    if exact_contacts:
        exact_contacts.sort(key=lambda item: (-item[0], item[1]))
        return exact_contacts[0][1]

    # 3) No proof of adjacency -> never invent an owner.
    return None



def _choose_small_island_neighbor(
    island: Polygon,
    original_name: str,
    names: list[str],
    stable_partition: dict,
    mm_per_px: float,
    simplify_mm: float,
):
    """Choose a surrounding stable color using true shared boundary only.

    Raster-level cleanup already handles pixel artifacts before vectorization.
    This second vector-level safety net therefore reassigns an island only when
    another stable print color physically shares its boundary. The longest
    shared boundary wins. Otherwise the detail stays in its original color.
    """
    contacts = []
    for name in names:
        if name == original_name:
            continue
        geom = stable_partition.get(name)
        if geom is None or geom.is_empty:
            continue
        try:
            shared = float(island.boundary.intersection(geom.boundary).length)
        except Exception:
            shared = 0.0
        if shared > 1e-10:
            contacts.append((shared, name))

    if contacts:
        contacts.sort(key=lambda item: (-item[0], item[1]))
        return contacts[0][1]

    return None



def _reassign_tiny_embedded_islands(
    partition: dict,
    names: list[str],
    min_area_mm2: float,
    mm_per_px: float,
    simplify_mm: float,
):
    """Reassign sub-threshold embedded color specks without creating gaps.

    `Min. Island Area` previously cleaned only the global silhouette; tiny
    wrong-color components inside another color could therefore survive and
    produce dozens of STL islands. We now apply the threshold to color
    components too, but only reassign a tiny component when it has a stable
    neighboring printable color. Truly isolated details are preserved.

    Because every removed component is immediately added to a neighboring group,
    the union of all color geometries remains exactly unchanged.
    """
    try:
        threshold = float(min_area_mm2)
    except Exception:
        return partition

    if not np.isfinite(threshold) or threshold <= 0:
        return partition

    stable = {}
    tiny = []

    for name in names:
        geom = partition.get(name)
        if geom is None or geom.is_empty:
            stable[name] = MultiPolygon([])
            continue

        keep_parts = []
        for poly in iter_polygons(geom):
            if float(poly.area) < threshold:
                tiny.append((float(poly.area), name, poly))
            else:
                keep_parts.append(poly)

        if keep_parts:
            stable[name] = unary_union(keep_parts).buffer(0)
        else:
            stable[name] = MultiPolygon([])

    # Process the smallest artifacts first. They are assigned only to stable
    # neighboring geometry, never to another tiny fragment, preventing chains of
    # micro-islands from simply changing color together.
    tiny.sort(key=lambda item: item[0])

    for _, original_name, island in tiny:
        owner = _choose_small_island_neighbor(
            island=island,
            original_name=original_name,
            names=names,
            stable_partition=stable,
            mm_per_px=mm_per_px,
            simplify_mm=simplify_mm,
        )

        if owner is None:
            owner = original_name

        existing = stable.get(owner)
        if existing is None or existing.is_empty:
            stable[owner] = island
        else:
            stable[owner] = unary_union([existing, island]).buffer(0)

    result = {}
    for name in names:
        geom = stable.get(name)
        if geom is not None and not geom.is_empty:
            result[name] = geom
    return result


def make_exact_partition(label_img: np.ndarray, groups: dict, mm_per_px: float,
                         min_area_px: int, min_area_mm2: float,
                         simplify_mm: float, close_strength: int,
                         contour_mode: str, explicit_background_mask=None,
                         edge_smoothing_mm: float = 0.18):
    """Return (geoms, total) as an exact, gap-free planar partition.

    Invariants:
      * total is a solid outer silhouette (no interior holes)
      * group geometries do not overlap
      * union(group geometries) == total, apart from floating point noise

    Local-gap partitioning:
      Contour simplification can leave microscopic polygons between neighboring
      vector colors. Earlier versions assigned every such remainder to the
      globally largest color, which could create thin wrong-color lines and many
      tiny islands around lettering. We now vectorize ALL groups first, then
      assign only the true leftover polygons to their locally most plausible
      color using the smoothed raster ownership map and geometric adjacency.
    """
    names, group_map, active_mask = smooth_group_partition(
        label_img, groups, mm_per_px, edge_smoothing_mm
    )
    if not np.any(active_mask):
        return {}, MultiPolygon([])

    # V8.1: eliminate tiny wrong-color raster components BEFORE vectorization.
    # A component can only move to a stable color sharing a real 4-neighbor
    # pixel edge, and the strongest surrounding edge count wins.
    group_map = _reassign_tiny_raster_components(
        group_map=group_map,
        active_mask=active_mask,
        min_area_px=min_area_px,
    )

    # Clean only the global active mask. This avoids deleting individual color
    # fragments in a way that would create gaps between neighboring colors.
    master_mask = clean_mask(active_mask, min_area_px, close_strength)
    total = external_silhouette_to_polygons(
        master_mask, mm_per_px, simplify_mm, contour_mode
    )

    # Explicit background remains a real hole/background region.
    if explicit_background_mask is not None and np.any(explicit_background_mask):
        smooth_bg_mask = _smooth_binary_mask(
            explicit_background_mask, edge_smoothing_mm, mm_per_px
        )
        bg_geom = contour_to_polygons(
            smooth_bg_mask,
            mm_per_px,
            simplify_mm,
            contour_mode,
        )
        if not bg_geom.is_empty:
            total = total.difference(bg_geom).buffer(0)

    if total.is_empty:
        return {}, total

    raw = {}
    for gid, name in enumerate(names):
        mask = (group_map == gid) & master_mask
        geom = contour_to_polygons(mask, mm_per_px, simplify_mm, contour_mode)
        if not geom.is_empty:
            geom = geom.intersection(total).buffer(0)
        raw[name] = geom

    nonempty = [n for n in names if n in raw and not raw[n].is_empty]
    if not nonempty:
        return {}, total

    # Keep the previous detail-preserving overlap rule: smaller groups win when
    # simplified contours overlap. Crucially, unlike <=7.6, the largest group is
    # also vectorized here instead of becoming the entire global remainder.
    ordered = sorted(nonempty, key=lambda n: raw[n].area)
    remaining = total
    partition = {}

    for name in ordered:
        piece = raw[name].intersection(remaining).buffer(0)
        if not piece.is_empty:
            partition[name] = piece
            remaining = remaining.difference(piece).buffer(0)

    # What is left now is ONLY approximation/vectorization gap geometry.
    # Allocate each connected gap locally instead of gifting all of it to the
    # dominant color.
    if not remaining.is_empty and remaining.area > 0:
        pending_gaps = [
            gap for gap in iter_polygons(remaining)
            if not gap.is_empty and gap.area > 0
        ]

        # Two local passes: assigning clear gaps can make exact boundaries
        # available for neighboring sub-gaps on the next pass.
        for _pass in range(2):
            if not pending_gaps:
                break

            next_pending = []
            gaps_by_owner = {}

            for gap in pending_gaps:
                owner = _choose_local_gap_owner(
                    gap=gap,
                    names=names,
                    group_map=group_map,
                    mm_per_px=mm_per_px,
                    partition=partition,
                    raw=raw,
                    simplify_mm=simplify_mm,
                )
                if owner is None:
                    next_pending.append(gap)
                else:
                    gaps_by_owner.setdefault(owner, []).append(gap)

            for owner, gaps in gaps_by_owner.items():
                existing = partition.get(owner)
                pieces = (
                    [existing]
                    if existing is not None and not existing.is_empty
                    else []
                )
                pieces.extend(gaps)
                merged = unary_union(pieces).buffer(0)
                if not merged.is_empty:
                    partition[owner] = merged

            pending_gaps = next_pending

        # Never invent a remote color to maintain a mathematically exact fill.
        # If a meaningful gap somehow has no local neighbor, report it instead.
        unresolved_area = float(sum(g.area for g in pending_gaps))
        if unresolved_area > 1e-9:
            raise RuntimeError(
                "Local partitioning found a vectorization gap of "
                f"{unresolved_area:.8f} mm² with no physically adjacent print "
                "color. The gap was not assigned to a random/remote color. "
                "Try a higher Geometry Resolution or lower Contour Simplification."
            )

    # Numerical safety net. This should normally be effectively zero area.
    union_partition = unary_union(
        [g for g in partition.values() if g is not None and not g.is_empty]
    ).buffer(0)
    final_missing = total.difference(union_partition).buffer(0)

    if not final_missing.is_empty and final_missing.area > 1e-10:
        unresolved = []
        for gap in list(iter_polygons(final_missing)):
            owner = _choose_local_gap_owner(
                gap=gap,
                names=names,
                group_map=group_map,
                mm_per_px=mm_per_px,
                partition=partition,
                raw=raw,
                simplify_mm=simplify_mm,
            )
            if owner is None:
                unresolved.append(gap)
                continue
            existing = partition.get(owner)
            partition[owner] = unary_union(
                [g for g in (existing, gap) if g is not None and not g.is_empty]
            ).buffer(0)

        unresolved_area = float(sum(g.area for g in unresolved))
        if unresolved_area > 1e-9:
            raise RuntimeError(
                "Final partition contains "
                f"{unresolved_area:.8f} mm² that has no local adjacent print "
                "color. V8.1 refuses to assign that area globally."
            )

    # Remove tiny embedded wrong-color specks according to Min. Island Area,
    # while transferring their exact geometry to the surrounding stable color.
    # This preserves the total union and therefore cannot create STL gaps.
    partition = _reassign_tiny_embedded_islands(
        partition=partition,
        names=names,
        min_area_mm2=min_area_mm2,
        mm_per_px=mm_per_px,
        simplify_mm=simplify_mm,
    )

    # Preserve original UI/group order.
    result = {}
    for name in names:
        geom = partition.get(name)
        if geom is not None and not geom.is_empty:
            result[name] = geom

    return result, total

def iter_polygons(geom):
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, MultiPolygon):
        yield from geom.geoms
    elif isinstance(geom, GeometryCollection):
        for g in geom.geoms:
            yield from iter_polygons(g)



def export_repaired_stl(mesh, path):
    """Always export STL and return a warning when topology may need repair.

    The validation is performed twice:
    1. on the in-memory mesh;
    2. after writing and reloading the STL with vertex processing enabled.

    The second check is the more important one because STL stores triangle
    coordinates without shared vertex indices, similar to what a slicer imports.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    bad, boundary, overused = _mesh_manifold_edge_counts(mesh)
    raw_warning = (bad != 0 or not mesh.is_watertight)

    # Export is deliberately non-blocking; slicers can repair rare residual issues.
    mesh.export(path)

    # Validate the actual file we just wrote. process=True merges coincident STL
    # coordinates and therefore better reflects typical slicer interpretation.
    roundtrip_error = None
    try:
        loaded = trimesh.load_mesh(path, process=True)
        file_bad, file_boundary, file_overused = _mesh_manifold_edge_counts(loaded)
        file_watertight = bool(loaded.is_watertight)
    except Exception as exc:
        roundtrip_error = str(exc)
        file_bad, file_boundary, file_overused = bad, boundary, overused
        file_watertight = bool(mesh.is_watertight)

    if raw_warning or file_bad != 0 or not file_watertight or roundtrip_error:
        return {
            "file": path.name,
            "bad_edges": int(file_bad),
            "boundary_edges": int(file_boundary),
            "overused_edges": int(file_overused),
            "watertight": file_watertight,
            "raw_bad_edges": int(bad),
            "roundtrip_error": roundtrip_error,
        }

    return None

def _ring_area(coords):
    area = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:] + coords[:1]):
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _clean_ring(coords):
    # Remove closing coordinate and repeated direct duplicates
    pts = list(coords)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    cleaned = []
    for p in pts:
        if not cleaned or cleaned[-1] != p:
            cleaned.append((float(p[0]), float(p[1])))
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned = cleaned[:-1]
    return cleaned


def _triangulate_polygon_earcut(poly: Polygon):
    """Triangulates a Shapely polygon including holes. Returns vertices2d and triangle indices."""
    if earcut is None:
        return None, None

    rings = []

    outer = _clean_ring(poly.exterior.coords)
    if len(outer) < 3:
        return None, None

    # Earcut expects rings with sane orientation. Exterior CCW, holes CW.
    if _ring_area(outer) < 0:
        outer = list(reversed(outer))
    rings.append(outer)

    for interior in poly.interiors:
        hole = _clean_ring(interior.coords)
        if len(hole) < 3:
            continue
        if _ring_area(hole) > 0:
            hole = list(reversed(hole))
        rings.append(hole)

    vertices = []
    ring_ends = []
    count = 0
    for ring in rings:
        vertices.extend(ring)
        count += len(ring)
        ring_ends.append(count)

    if len(vertices) < 3:
        return None, None

    vertices_np = np.array(vertices, dtype=np.float64)
    ring_ends_np = np.array(ring_ends, dtype=np.uint32)

    try:
        indices = earcut.triangulate_float64(vertices_np, ring_ends_np)
    except Exception:
        return None, None

    if indices is None or len(indices) < 3:
        return None, None

    return vertices_np, np.array(indices, dtype=np.int64).reshape((-1, 3))


def _extrude_polygon_manifold(poly: Polygon, height_mm: float) -> trimesh.Trimesh:
    """Extrude one polygon into a closed, consistently wound manifold mesh.

    Critical difference to the old exporter:
    - top, bottom and side walls SHARE the exact same indexed boundary vertices
    - polygon caps use constrained Delaunay triangulation when available
    - no graph/networkx based repair is required afterwards
    """
    if poly.is_empty or poly.area <= 0:
        return trimesh.Trimesh(vertices=[], faces=[], process=False)

    if not poly.is_valid:
        poly = poly.buffer(0)
        if not isinstance(poly, Polygon):
            raise ValueError("A polygon could not be repaired unambiguously for manifold STL export.")

    vertices = []
    faces = []
    vertex_map = {}

    def vertex_id(x, y, z):
        # Stable shared vertex identity. 12 decimal places is far below STL precision
        # but safely merges exactly corresponding cap/side coordinates.
        key = (round(float(x), 12), round(float(y), 12), round(float(z), 12))
        idx = vertex_map.get(key)
        if idx is None:
            idx = len(vertices)
            vertex_map[key] = idx
            vertices.append((float(x), float(y), float(z)))
        return idx

    # --- Top / bottom caps ---
    triangles = []

    if constrained_delaunay_triangles is not None:
        try:
            tri_geom = constrained_delaunay_triangles(poly)
            for tri in getattr(tri_geom, "geoms", []):
                if tri.is_empty or tri.area <= 0:
                    continue
                coords = list(tri.exterior.coords)[:-1]
                if len(coords) == 3:
                    triangles.append(coords)
        except Exception:
            triangles = []

    # Optional fallback for older Shapely installations.
    if not triangles:
        verts2d, tris = _triangulate_polygon_earcut(poly)
        if verts2d is not None and tris is not None:
            for a, b, c in tris:
                triangles.append([
                    tuple(verts2d[a]),
                    tuple(verts2d[b]),
                    tuple(verts2d[c]),
                ])

    if not triangles:
        raise RuntimeError(
            "No safe polygon triangulation is available. "
            "Please install Shapely >= 2.1."
        )

    for coords in triangles:
        # Top must face +Z. Ensure CCW in XY.
        if _ring_area(list(coords)) < 0:
            coords = [coords[0], coords[2], coords[1]]

        top = [vertex_id(x, y, height_mm) for x, y in coords]
        bottom = [vertex_id(x, y, 0.0) for x, y in coords]

        faces.append(top)
        faces.append([bottom[2], bottom[1], bottom[0]])

    # --- Side walls ---
    def add_ring_sides(ring, is_hole=False):
        pts = _clean_ring(ring.coords)
        if len(pts) < 3:
            return

        area = _ring_area(pts)

        # Base side pattern points to the RIGHT of ring travel.
        # Exterior: outward is right for CCW, left for CW.
        # Hole: outward into hole is left for CCW, right for CW.
        reverse = (area < 0) if not is_hole else (area > 0)

        closed = pts + [pts[0]]
        for (x1, y1), (x2, y2) in zip(closed[:-1], closed[1:]):
            b1 = vertex_id(x1, y1, 0.0)
            b2 = vertex_id(x2, y2, 0.0)
            t2 = vertex_id(x2, y2, height_mm)
            t1 = vertex_id(x1, y1, height_mm)

            if reverse:
                faces.append([b1, t2, b2])
                faces.append([b1, t1, t2])
            else:
                faces.append([b1, b2, t2])
                faces.append([b1, t2, t1])

    add_ring_sides(poly.exterior, is_hole=False)
    for ring in poly.interiors:
        add_ring_sides(ring, is_hole=True)

    mesh = trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=np.float64),
        faces=np.asarray(faces, dtype=np.int64),
        process=False,
        validate=False,
    )

    # Local deterministic cleanup only.
    try:
        areas = np.asarray(mesh.area_faces)
        valid = np.isfinite(areas) & (areas > 1e-12)
        if len(valid) == len(mesh.faces) and not np.all(valid):
            mesh.update_faces(valid)
    except Exception:
        pass

    try:
        mesh.remove_unreferenced_vertices()
    except Exception:
        pass

    return mesh


def _mesh_manifold_edge_counts(mesh: trimesh.Trimesh):
    """Return (bad, boundary, overused) using indexed mesh edges."""
    if mesh.is_empty:
        return 0, 0, 0

    edges = np.sort(np.asarray(mesh.edges, dtype=np.int64), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return (
        int(np.count_nonzero(counts != 2)),
        int(np.count_nonzero(counts == 1)),
        int(np.count_nonzero(counts > 2)),
    )


def extrude_geometry(geom, height_mm):
    """Create a truly manifold extrusion for Polygon/MultiPolygon geometry."""
    meshes = []

    for original in iter_polygons(geom):
        if original.is_empty or original.area <= 0:
            continue

        repaired = original if original.is_valid else original.buffer(0)

        for poly in iter_polygons(repaired):
            if poly.is_empty or poly.area <= 0:
                continue

            mesh = _extrude_polygon_manifold(poly, height_mm)
            if not mesh.is_empty:
                # Validation remains informational. Some slicers can repair rare
                # residual topology issues, so never abort only for this reason.
                meshes.append(mesh)

    if not meshes:
        return trimesh.Trimesh(vertices=[], faces=[], process=False)

    if len(meshes) == 1:
        result = meshes[0]
    else:
        # Disconnected shells in one STL are fine as long as each shell is manifold.
        result = trimesh.util.concatenate(meshes)

    # Do not block export here. export_repaired_stl performs the same check
    # and returns a structured warning while still writing the STL.
    return result


def center_geom(geom):
    minx,miny,maxx,maxy = geom.bounds
    return translate(geom, xoff=-((minx+maxx)/2), yoff=-((miny+maxy)/2))


def compute_logo_width(image_aspect, mode, manual_width, deck_w, deck_h, margin, fit):
    if mode == "manual":
        return manual_width
    usable_w = max(1.0, deck_w - 2*margin)
    usable_h = max(1.0, deck_h - 2*margin)
    fitted = min(usable_w, usable_h * image_aspect)
    return max(1.0, fitted * max(1, min(100, fit))/100)


def make_preview(label_img, color_map, path: Path):
    h, w = label_img.shape
    y, x = np.indices((h, w))
    checker = ((x // 16 + y // 16) % 2).astype(np.uint8)
    arr = np.where(checker[:, :, None] == 0, 210, 238).astype(np.uint8)
    arr = np.repeat(arr, 3, axis=2)
    for cluster, rgb in color_map.items():
        arr[label_img == cluster] = np.array(rgb, dtype=np.uint8)
    Image.fromarray(arr).save(path)



def extract_background_groups(label_img, color_plan):
    """Remove groups explicitly assigned to background.

    Pixels assigned to 'zu Hintergrund' become true background/transparent pixels.
    The returned mask is later subtracted from the master cutting body as well,
    so even enclosed background regions remain holes instead of being filled.
    """
    import numpy as np

    labels = np.array(label_img, copy=True)
    plan = [dict(item) for item in color_plan]

    bg_clusters = {
        int(item["cluster"])
        for item in plan
        if item.get("enabled", True)
        and str(item.get("group", "")).strip().lower() == "zu hintergrund"
    }

    bg_mask = np.isin(labels, list(bg_clusters)) if bg_clusters else np.zeros(labels.shape, dtype=bool)

    if bg_clusters:
        labels[bg_mask] = -1
        for item in plan:
            if int(item["cluster"]) in bg_clusters:
                item["enabled"] = False

    return labels, plan, bg_mask


def redistribute_auto_groups(label_img, color_plan):
    """Resolve AUTO only from genuinely edge-adjacent printable colors.

    V8 Final AUTO fix:
      * 4-neighbor connectivity is used for AUTO components.
      * Only print colors sharing a real pixel EDGE with an AUTO component are
        allowed to own pixels from that component.
      * Diagonal contact does NOT count as adjacency.
      * Each eligible print color propagates geodesically through the AUTO
        component from its own real contact edge.
      * A print color elsewhere in the logo can never jump into the component.
      * If an AUTO component has no edge contact with any printable color, it is
        deliberately left unresolved instead of being guessed globally.

    This matches the intended anti-aliasing workflow: AUTO distributes transition
    pixels between the colors that physically border that transition region.
    """
    import cv2
    import numpy as np
    from collections import deque

    labels = np.array(label_img, copy=True)
    plan = [dict(item) for item in color_plan]

    auto_items = [
        item for item in plan
        if item.get("enabled", True)
        and str(item.get("group", "")).strip().lower() == "auto verteilen"
    ]
    printable_items = [
        item for item in plan
        if item.get("enabled", True)
        and str(item.get("group", "")).strip().lower()
        not in ("zu hintergrund", "auto verteilen")
    ]

    if not auto_items or not printable_items:
        return labels, plan

    auto_clusters = {int(item["cluster"]) for item in auto_items}
    auto_mask = np.isin(labels, list(auto_clusters))
    if not np.any(auto_mask):
        # No AUTO pixels remain, so the AUTO source rows no longer export.
        for item in plan:
            if int(item["cluster"]) in auto_clusters:
                item["enabled"] = False
        return labels, plan

    # Multiple detected shades may already belong to the same print group.
    groups = {}
    cluster_rgb = {}
    for item in printable_items + auto_items:
        cluster_rgb[int(item["cluster"])] = np.asarray(
            item.get("rgb", [128, 128, 128]), dtype=np.float32
        )

    for item in printable_items:
        name = str(item.get("group", "")).strip()
        groups.setdefault(name, []).append(int(item["cluster"]))

    group_names = list(groups.keys())
    group_cluster_ids = [groups[name] for name in group_names]
    representative_cluster = [ids[0] for ids in group_cluster_ids]

    print_gid = np.full(labels.shape, -1, dtype=np.int16)
    for gid, cluster_ids in enumerate(group_cluster_ids):
        print_gid[np.isin(labels, cluster_ids)] = gid

    # RGB is used ONLY as a deterministic tie-breaker when two genuinely
    # adjacent colors are at exactly the same geodesic distance.
    group_rgb = []
    for cluster_ids in group_cluster_ids:
        rgbs = [cluster_rgb[c] for c in cluster_ids if c in cluster_rgb]
        if rgbs:
            group_rgb.append(np.mean(np.stack(rgbs), axis=0))
        else:
            group_rgb.append(np.array([128, 128, 128], dtype=np.float32))

    # 4-connectivity is intentional: diagonal touching must not merge separate
    # AUTO patches or make a diagonally placed print color a valid neighbor.
    num_components, component_labels = cv2.connectedComponents(
        auto_mask.astype(np.uint8), connectivity=4
    )

    h, w = labels.shape
    edge_neighbors = [(-1, 0), (0, -1), (0, 1), (1, 0)]

    for cid in range(1, num_components):
        comp = component_labels == cid
        ys, xs = np.nonzero(comp)
        if len(ys) == 0:
            continue

        # Work only inside this component's bounding box. This keeps AUTO fast
        # even on large 1600/1800 px analyses with many small AUTO components.
        y0, y1 = int(np.min(ys)), int(np.max(ys))
        x0, x1 = int(np.min(xs)), int(np.max(xs))
        comp_roi = comp[y0:y1 + 1, x0:x1 + 1]
        roi_h, roi_w = comp_roi.shape

        # One seed set per group. A group becomes a candidate ONLY when one of
        # its pixels shares a real edge with this AUTO component.
        seeds_by_gid = {}

        for y, x in zip(ys, xs):
            touching = set()
            for dy, dx in edge_neighbors:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    gid = int(print_gid[ny, nx])
                    if gid >= 0:
                        touching.add(gid)

            for gid in touching:
                seeds_by_gid.setdefault(gid, []).append(
                    (int(y - y0), int(x - x0))
                )

        # No true edge-adjacent print color -> do not invent one.
        if not seeds_by_gid:
            continue

        candidate_gids = sorted(seeds_by_gid.keys())

        # If exactly one print color borders the component, the answer is
        # unambiguous and no propagation calculation is required.
        if len(candidate_gids) == 1:
            gid = candidate_gids[0]
            labels[comp] = representative_cluster[gid]
            continue

        # Compute geodesic distance INSIDE this AUTO component for every
        # edge-adjacent candidate group. This is a multi-source BFS per group.
        inf = np.iinfo(np.int32).max
        distance_maps = {}

        for gid in candidate_gids:
            dist = np.full((roi_h, roi_w), inf, dtype=np.int32)
            q = deque()

            for ly, lx in seeds_by_gid[gid]:
                if dist[ly, lx] != 0:
                    dist[ly, lx] = 0
                    q.append((ly, lx))

            while q:
                ly, lx = q.popleft()
                nd = int(dist[ly, lx]) + 1
                for dy, dx in edge_neighbors:
                    nly, nlx = ly + dy, lx + dx
                    if not (0 <= nly < roi_h and 0 <= nlx < roi_w):
                        continue
                    if not comp_roi[nly, nlx]:
                        continue
                    if nd < int(dist[nly, nlx]):
                        dist[nly, nlx] = nd
                        q.append((nly, nlx))

            distance_maps[gid] = dist

        # Resolve every AUTO pixel using only the eligible edge-adjacent groups.
        for y, x in zip(ys, xs):
            ly, lx = int(y - y0), int(x - x0)
            best_distance = min(
                int(distance_maps[gid][ly, lx]) for gid in candidate_gids
            )
            tied = [
                gid for gid in candidate_gids
                if int(distance_maps[gid][ly, lx]) == best_distance
            ]

            if len(tied) == 1:
                best_gid = tied[0]
            else:
                source_cluster = int(labels[y, x])
                source_rgb = cluster_rgb.get(
                    source_cluster,
                    np.array([128, 128, 128], dtype=np.float32),
                )
                best_gid = min(
                    tied,
                    key=lambda gid: (
                        float(np.linalg.norm(source_rgb - group_rgb[gid])),
                        gid,
                    ),
                )

            labels[y, x] = representative_cluster[best_gid]

    # Only disable AUTO source rows when every AUTO pixel was safely resolved.
    # If isolated AUTO remains, callers can report it instead of exporting a
    # silently guessed/wrong color.
    remaining_auto = np.isin(labels, list(auto_clusters))
    if not np.any(remaining_auto):
        for item in plan:
            if int(item["cluster"]) in auto_clusters:
                item["enabled"] = False

    return labels, plan

def upscale_geometry_grid(label_img, explicit_background_mask=None, target_pixels=1600):
    """Upscale the already-classified label map for smoother vector geometry.

    Color assignment remains unchanged because nearest-neighbor interpolation
    only duplicates existing class labels. This gives the geometry/smoothing
    stage more resolution without forcing a new color analysis.
    """
    labels = np.asarray(label_img)
    h, w = labels.shape
    target = max(int(target_pixels or 0), max(h, w))
    if target <= max(h, w):
        bg = None if explicit_background_mask is None else np.asarray(explicit_background_mask, dtype=bool).copy()
        return labels.copy(), bg

    scale = target / max(h, w)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))

    resized = cv2.resize(
        labels.astype(np.float32),
        (nw, nh),
        interpolation=cv2.INTER_NEAREST,
    ).astype(labels.dtype)

    if explicit_background_mask is None:
        bg = None
    else:
        bg = cv2.resize(
            np.asarray(explicit_background_mask, dtype=np.uint8),
            (nw, nh),
            interpolation=cv2.INTER_NEAREST,
        ).astype(bool)

    return resized, bg



def _build_print_groups(color_plan: list[dict]) -> dict:
    """Return enabled printable groups as {safe_group_name: [cluster_ids]}."""
    groups = {}
    for item in color_plan:
        if not item.get("enabled", True):
            continue
        group_key = str(item.get("group") or item.get("name") or "").strip()
        if group_key.lower() in ("zu hintergrund", "auto verteilen"):
            continue
        cluster = int(item["cluster"])
        group = safe_filename_part(group_key or f"group_{cluster}")
        groups.setdefault(group, []).append(cluster)
    return groups


def cleanup_small_color_islands(
    label_img: np.ndarray,
    color_plan: list[dict],
    min_area_mm2: float,
    target_width_mm: float,
    target_height_mm: float | None = None,
    keep_aspect: bool = True,
    background_mask=None,
):
    """Reassign tiny print-color islands in the ACTUAL label raster.

    This is intentionally earlier than vectorization. It fixes the class of
    errors where a one/few-pixel Blue, Black, Red, etc. artifact is already
    present in Manual after color grouping / Calculate.

    Rules:
      * colors are merged by their assigned print group first;
      * components are 4-connected;
      * only stable colors sharing a real horizontal/vertical edge are eligible;
      * most shared edges wins;
      * a true tie uses local stable-color majority;
      * diagonal/non-touching colors are never candidates;
      * AUTO / BG / disabled colors are not used as replacement candidates;
      * details surrounded only by background are preserved.

    The physical `Min. Island Area (mm²)` setting determines how many source
    raster pixels count as a tiny island. This same concept is also used again
    later as a vector-geometry safety net.

    Returns:
        (cleaned_label_img, stats)
    """
    labels = np.asarray(label_img).copy()

    try:
        min_area = float(min_area_mm2)
        width_mm = float(target_width_mm)
    except Exception:
        return labels, {
            "changed_pixels": 0,
            "changed_components": 0,
            "threshold_px": 1,
        }

    if (
        not np.isfinite(min_area)
        or min_area <= 0
        or not np.isfinite(width_mm)
        or width_mm <= 0
    ):
        return labels, {
            "changed_pixels": 0,
            "changed_components": 0,
            "threshold_px": 1,
        }

    groups = _build_print_groups(color_plan)
    bbox = _active_content_bbox_px(labels, groups)
    if not groups or bbox is None:
        return labels, {
            "changed_pixels": 0,
            "changed_components": 0,
            "threshold_px": 1,
        }

    _, _, _, _, content_w_px, content_h_px = bbox
    x_mm_per_px = width_mm / max(1, content_w_px)

    if keep_aspect or target_height_mm is None:
        y_mm_per_px = x_mm_per_px
    else:
        try:
            height_mm = float(target_height_mm)
        except Exception:
            height_mm = 0.0
        if not np.isfinite(height_mm) or height_mm <= 0:
            y_mm_per_px = x_mm_per_px
        else:
            y_mm_per_px = height_mm / max(1, content_h_px)

    pixel_area_mm2 = max(1e-12, x_mm_per_px * y_mm_per_px)
    threshold_px = max(
        1,
        int(np.ceil(min_area / pixel_area_mm2)),
    )

    if threshold_px <= 1:
        return labels, {
            "changed_pixels": 0,
            "changed_components": 0,
            "threshold_px": threshold_px,
        }

    names = list(groups.keys())
    group_map = np.full(labels.shape, -1, dtype=np.int16)
    representative_cluster = {}

    for gid, name in enumerate(names):
        cluster_ids = [int(v) for v in groups[name]]
        if not cluster_ids:
            continue
        representative_cluster[gid] = cluster_ids[0]
        group_map[np.isin(labels, cluster_ids)] = gid

    if background_mask is not None:
        bg = np.asarray(background_mask, dtype=bool)
        if bg.shape == labels.shape:
            group_map[bg] = -1

    active_mask = group_map >= 0
    if not np.any(active_mask):
        return labels, {
            "changed_pixels": 0,
            "changed_components": 0,
            "threshold_px": threshold_px,
        }

    cleaned_map = _reassign_tiny_raster_components(
        group_map=group_map,
        active_mask=active_mask,
        min_area_px=threshold_px,
    )

    changed = active_mask & (cleaned_map != group_map)
    changed_pixels = int(np.count_nonzero(changed))

    if changed_pixels == 0:
        return labels, {
            "changed_pixels": 0,
            "changed_components": 0,
            "threshold_px": threshold_px,
        }

    count, _ = cv2.connectedComponents(
        changed.astype(np.uint8), connectivity=4
    )
    changed_components = max(0, int(count) - 1)

    # Convert cleaned print-group IDs back to a valid cluster ID of that group.
    for gid, cluster_id in representative_cluster.items():
        target = changed & (cleaned_map == gid)
        if np.any(target):
            labels[target] = int(cluster_id)

    return labels, {
        "changed_pixels": changed_pixels,
        "changed_components": changed_components,
        "threshold_px": threshold_px,
    }


def _active_content_bbox_px(label_img: np.ndarray, groups: dict):
    """Return (x0, y0, x1, y1, width_px, height_px) for printable pixels."""
    if not groups:
        return None

    cluster_ids = []
    for ids in groups.values():
        cluster_ids.extend(int(v) for v in ids)
    if not cluster_ids:
        return None

    mask = np.isin(label_img, cluster_ids)
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    return x0, y0, x1, y1, (x1 - x0 + 1), (y1 - y0 + 1)


def _fit_partition_to_requested_size(
    geoms: dict,
    total,
    target_width_mm: float,
    target_height_mm: float | None = None,
    keep_aspect: bool = True,
):
    """Scale a finished partition so requested dimensions describe the STL itself.

    Width always means the final vector geometry width, not the source-image
    canvas width. With aspect lock enabled the scale is uniform. With the lock
    disabled, width and height are applied independently.
    """
    if total is None or total.is_empty:
        return geoms, total

    target_width_mm = float(target_width_mm)
    if not np.isfinite(target_width_mm) or target_width_mm <= 0:
        raise ValueError("Logo Width must be greater than 0 mm.")

    minx, miny, maxx, maxy = total.bounds
    current_w = float(maxx - minx)
    current_h = float(maxy - miny)
    if current_w <= 1e-12 or current_h <= 1e-12:
        raise ValueError("The final logo geometry has no measurable width or height.")

    sx = target_width_mm / current_w

    if keep_aspect:
        sy = sx
    else:
        if target_height_mm is None:
            raise ValueError("Logo Height is required when Lock aspect ratio is disabled.")
        target_height_mm = float(target_height_mm)
        if not np.isfinite(target_height_mm) or target_height_mm <= 0:
            raise ValueError("Logo Height must be greater than 0 mm.")
        sy = target_height_mm / current_h

    origin = (minx, miny)
    fitted_geoms = {
        name: scale_geom(g, xfact=sx, yfact=sy, origin=origin)
        for name, g in geoms.items()
    }
    fitted_total = scale_geom(total, xfact=sx, yfact=sy, origin=origin)

    # Normalize tiny floating-point drift so the bounds start at the same origin.
    return fitted_geoms, fitted_total


def _prepare_partition_geometry(
    image_path: Path,
    color_plan: list[dict],
    target_mode: str = "manual",
    manual_width_mm: float = 70,
    manual_height_mm: float | None = None,
    keep_aspect: bool = True,
    deck_width_mm: float = 100,
    deck_height_mm: float = 70,
    margin_mm: float = 5,
    fit_percent: float = 90,
    detect_colors: int = 8,
    background_mode: str = "transparent",
    white_threshold: int = 245,
    working_pixels: int = 1400,
    geometry_pixels: int = 1600,
    min_area_mm2: float = 0.12,
    simplify_mm: float = 0.12,
    close_strength: int = 0,
    auto_merge: bool = True,
    merge_distance: float = 18,
    contour_mode: str = "straight",
    edge_smoothing_mm: float = 0.18,
    label_override=None,
    manual_background_mask=None,
):
    """Shared geometry path used by STL Preview and STL export.

    Keeping preview and export on one preparation path prevents them from
    silently disagreeing about target size, background or color partitioning.
    """
    image_path = Path(image_path)
    analysis = analyze_colors(
        image_path,
        working_pixels,
        detect_colors,
        background_mode,
        white_threshold,
        auto_merge,
        merge_distance,
    )

    if label_override is not None:
        label_img = np.asarray(
            label_override, dtype=analysis["label_img"].dtype
        ).copy()
        if label_img.shape != analysis["label_img"].shape:
            raise ValueError(
                "Manual editing data has a different size than the current analysis."
            )
    else:
        label_img = analysis["label_img"].copy()

    label_img, plan, explicit_background_mask = extract_background_groups(
        label_img, color_plan
    )

    if manual_background_mask is not None:
        manual_bg = np.asarray(manual_background_mask, dtype=bool)
        if manual_bg.shape != label_img.shape:
            raise ValueError(
                "The manual background mask has a different size than the current analysis."
            )
        explicit_background_mask = explicit_background_mask | manual_bg
        label_img[manual_bg] = -1

    # V8.2: clean tiny already-assigned wrong-color islands BEFORE AUTO.
    # This prevents one stray Blue/Black/Red pixel from becoming a valid AUTO
    # seed and spreading the wrong color into a transition region.
    if target_mode == "manual":
        label_img, _ = cleanup_small_color_islands(
            label_img=label_img,
            color_plan=plan,
            min_area_mm2=min_area_mm2,
            target_width_mm=manual_width_mm,
            target_height_mm=manual_height_mm,
            keep_aspect=keep_aspect,
            background_mask=explicit_background_mask,
        )

    label_img, plan = redistribute_auto_groups(label_img, plan)

    # Run the same cleanup again after AUTO. This removes any residual tiny
    # print-color islands before geometry upscaling / smoothing.
    if target_mode == "manual":
        label_img, _ = cleanup_small_color_islands(
            label_img=label_img,
            color_plan=plan,
            min_area_mm2=min_area_mm2,
            target_width_mm=manual_width_mm,
            target_height_mm=manual_height_mm,
            keep_aspect=keep_aspect,
            background_mask=explicit_background_mask,
        )

    unresolved_auto_ids = {
        int(item["cluster"])
        for item in plan
        if item.get("enabled", True)
        and str(item.get("group", "")).strip().lower() == "auto verteilen"
    }
    if unresolved_auto_ids:
        unresolved_mask = np.isin(label_img, list(unresolved_auto_ids))
        if np.any(unresolved_mask):
            count, _ = cv2.connectedComponents(
                unresolved_mask.astype(np.uint8), connectivity=4
            )
            components = max(0, int(count) - 1)
            pixels = int(np.sum(unresolved_mask))
            raise ValueError(
                "AUTO contains "
                f"{components} isolated region(s) / {pixels} pixel(s) that do not "
                "share an edge with any active print color. They were left AUTO "
                "instead of being guessed. Assign those regions manually or make "
                "them touch the intended print color, then Calculate again."
            )

    label_img, explicit_background_mask = upscale_geometry_grid(
        label_img, explicit_background_mask, geometry_pixels
    )

    groups = _build_print_groups(plan)
    bbox = _active_content_bbox_px(label_img, groups)
    if bbox is None:
        raise ValueError(
            "No active printable color area remains. Check color assignments and background settings."
        )

    _, _, _, _, content_w_px, content_h_px = bbox
    content_aspect = content_w_px / max(1, content_h_px)

    if target_mode == "manual":
        width_mm = float(manual_width_mm)
    else:
        width_mm = compute_logo_width(
            content_aspect,
            target_mode,
            manual_width_mm,
            deck_width_mm,
            deck_height_mm,
            margin_mm,
            fit_percent,
        )

    if not np.isfinite(width_mm) or width_mm <= 0:
        raise ValueError("Logo Width must be greater than 0 mm.")

    # Use the printable content width rather than the complete source-image
    # canvas. Transparent/removed margins therefore no longer shrink the STL.
    mm_per_px = width_mm / max(1, content_w_px)
    min_area_px = max(
        1,
        int(float(min_area_mm2) / max(1e-12, mm_per_px ** 2)),
    )

    geoms, total = make_exact_partition(
        label_img=label_img,
        groups=groups,
        mm_per_px=mm_per_px,
        min_area_px=min_area_px,
        min_area_mm2=min_area_mm2,
        simplify_mm=simplify_mm,
        close_strength=close_strength,
        contour_mode=contour_mode,
        explicit_background_mask=explicit_background_mask,
        edge_smoothing_mm=edge_smoothing_mm,
    )

    if not geoms or total is None or total.is_empty:
        raise ValueError(
            "No printable geometry was generated. Check the active color groups."
        )

    # The UI always uses manual mode. For compatibility, area mode also gets
    # its computed width applied exactly to the final vector bounds.
    geoms, total = _fit_partition_to_requested_size(
        geoms,
        total,
        target_width_mm=width_mm,
        target_height_mm=manual_height_mm,
        keep_aspect=(True if target_mode != "manual" else bool(keep_aspect)),
    )

    return {
        "analysis": analysis,
        "label_img": label_img,
        "plan": plan,
        "groups": groups,
        "geoms": geoms,
        "total": total,
        "vectorization_mm_per_px": mm_per_px,
        "content_bbox_px": bbox,
        "content_aspect": content_aspect,
    }


def build_partition_preview(
    image_path: Path,
    color_plan: list[dict],
    manual_width_mm: float = 70,
    manual_height_mm: float | None = None,
    keep_aspect: bool = True,
    detect_colors: int = 8,
    background_mode: str = "transparent",
    white_threshold: int = 245,
    working_pixels: int = 1400,
    geometry_pixels: int = 1600,
    min_area_mm2: float = 0.12,
    simplify_mm: float = 0.12,
    close_strength: int = 0,
    auto_merge: bool = True,
    merge_distance: float = 18,
    contour_mode: str = "straight",
    edge_smoothing_mm: float = 0.18,
    label_override=None,
    manual_background_mask=None,
    group_colors=None,
):
    """Build a raster preview from the exact same vector geometry as STL export."""
    prepared = _prepare_partition_geometry(
        image_path=image_path,
        color_plan=color_plan,
        target_mode="manual",
        manual_width_mm=manual_width_mm,
        manual_height_mm=manual_height_mm,
        keep_aspect=keep_aspect,
        detect_colors=detect_colors,
        background_mode=background_mode,
        white_threshold=white_threshold,
        working_pixels=working_pixels,
        geometry_pixels=geometry_pixels,
        min_area_mm2=min_area_mm2,
        simplify_mm=simplify_mm,
        close_strength=close_strength,
        auto_merge=auto_merge,
        merge_distance=merge_distance,
        contour_mode=contour_mode,
        edge_smoothing_mm=edge_smoothing_mm,
        label_override=label_override,
        manual_background_mask=manual_background_mask,
    )

    geoms = prepared["geoms"]
    total = prepared["total"]
    label_img = prepared["label_img"]

    minx, miny, maxx, maxy = total.bounds
    final_w_mm = float(maxx - minx)
    final_h_mm = float(maxy - miny)

    # Rasterize only the final STL bounds. Source-image padding is intentionally
    # excluded so the preview corresponds to the physical STL dimensions.
    target_px = max(200, int(geometry_pixels or 1600))
    px_per_mm = target_px / max(final_w_mm, final_h_mm, 1e-12)
    render_w = max(2, int(round(final_w_mm * px_per_mm)) + 1)
    render_h = max(2, int(round(final_h_mm * px_per_mm)) + 1)

    rgba = np.zeros((render_h, render_w, 4), dtype=np.uint8)
    masks = {}

    def geom_to_mask(geom):
        mask = np.zeros((render_h, render_w), dtype=np.uint8)
        for poly in iter_polygons(geom):
            ext = np.asarray([
                [
                    round((x - minx) * px_per_mm),
                    round((maxy - y) * px_per_mm),
                ]
                for x, y in poly.exterior.coords
            ], dtype=np.int32)
            if len(ext) >= 3:
                cv2.fillPoly(mask, [ext], 255)

            for ring in poly.interiors:
                hole = np.asarray([
                    [
                        round((x - minx) * px_per_mm),
                        round((maxy - y) * px_per_mm),
                    ]
                    for x, y in ring.coords
                ], dtype=np.int32)
                if len(hole) >= 3:
                    cv2.fillPoly(mask, [hole], 0)
        return mask.astype(bool)

    for name, geom in geoms.items():
        mask = geom_to_mask(geom)
        masks[name] = mask
        rgb = (group_colors or {}).get(name, [160, 160, 160])
        rgba[mask, :3] = np.asarray(rgb, dtype=np.uint8)
        rgba[mask, 3] = 255

    total_mask = geom_to_mask(total)

    union_groups = unary_union(list(geoms.values())).buffer(0)
    missing_area = float(total.difference(union_groups).area)
    overlap_area = max(
        0.0,
        float(sum(g.area for g in geoms.values()) - union_groups.area),
    )

    return {
        "rgba": rgba,
        "group_masks": masks,
        "total_mask": total_mask,
        "geoms": geoms,
        "total": total,
        "label_img": label_img,
        "mm_per_px": 1.0 / px_per_mm,
        "vectorization_mm_per_px": prepared["vectorization_mm_per_px"],
        "content_aspect": prepared["content_aspect"],
        "final_width_mm": final_w_mm,
        "final_height_mm": final_h_mm,
        "missing_area_mm2": missing_area,
        "overlap_area_mm2": overlap_area,
    }


def generate_logo_stls(
    image_path: Path,
    out_dir: Path,
    project_name: str,
    color_plan: list[dict],
    target_mode: str = "area",
    manual_width_mm: float = 70,
    manual_height_mm: float | None = None,
    keep_aspect: bool = True,
    deck_width_mm: float = 100,
    deck_height_mm: float = 70,
    margin_mm: float = 5,
    fit_percent: float = 90,
    height_mm: float = 0.8,
    cut_depth_mm: float = 0.82,
    clearance_mm: float = 0.08,
    detect_colors: int = 8,
    background_mode: str = "transparent",
    white_threshold: int = 245,
    working_pixels: int = 1400,
    geometry_pixels: int = 1600,
    min_area_mm2: float = 0.12,
    simplify_mm: float = 0.12,
    close_strength: int = 0,
    auto_merge: bool = True,
    merge_distance: float = 18,
    contour_mode: str = "straight",
    edge_smoothing_mm: float = 0.18,
    center_output: bool = True,
    label_override=None,
    manual_background_mask=None,
):
    out_dir.mkdir(parents=True, exist_ok=True)
    project = safe_filename_part(project_name)
    manifold_warnings = []

    height_mm = float(height_mm)
    cut_depth_mm = float(cut_depth_mm)
    clearance_mm = float(clearance_mm)
    if not np.isfinite(height_mm) or height_mm <= 0:
        raise ValueError("Part Height must be greater than 0 mm.")
    if not np.isfinite(cut_depth_mm) or cut_depth_mm <= 0:
        raise ValueError("Cutout Depth must be greater than 0 mm.")
    if not np.isfinite(clearance_mm) or clearance_mm < 0:
        raise ValueError("Clearance must be 0 mm or greater.")

    raster_path = prepare_input_image(
        Path(image_path), out_dir, project, working_pixels
    )
    save_input_copies(Path(image_path), out_dir, project)

    prepared = _prepare_partition_geometry(
        image_path=raster_path,
        color_plan=color_plan,
        target_mode=target_mode,
        manual_width_mm=manual_width_mm,
        manual_height_mm=manual_height_mm,
        keep_aspect=keep_aspect,
        deck_width_mm=deck_width_mm,
        deck_height_mm=deck_height_mm,
        margin_mm=margin_mm,
        fit_percent=fit_percent,
        detect_colors=detect_colors,
        background_mode=background_mode,
        white_threshold=white_threshold,
        working_pixels=working_pixels,
        geometry_pixels=geometry_pixels,
        min_area_mm2=min_area_mm2,
        simplify_mm=simplify_mm,
        close_strength=close_strength,
        auto_merge=auto_merge,
        merge_distance=merge_distance,
        contour_mode=contour_mode,
        edge_smoothing_mm=edge_smoothing_mm,
        label_override=label_override,
        manual_background_mask=manual_background_mask,
    )

    label_img = prepared["label_img"]
    color_plan = prepared["plan"]
    geoms = prepared["geoms"]
    total = prepared["total"]

    # `total` comes from the solid outer silhouette. The group pieces form an
    # exact partition of it. Keep this master instead of rebuilding from colors.
    union_groups = unary_union(list(geoms.values())).buffer(0)
    missing_area = float(total.difference(union_groups).area)
    overlap_area = max(0.0, float(sum(g.area for g in geoms.values()) - union_groups.area))

    if center_output:
        centered = center_geom(total)
        dx = centered.bounds[0] - total.bounds[0]
        dy = centered.bounds[1] - total.bounds[1]
        geoms = {name: translate(g, xoff=dx, yoff=dy) for name,g in geoms.items()}
        total = centered

    files = []
    colors_meta = []
    total_area = float(total.area)
    for idx, (group, geom) in enumerate(geoms.items(), start=1):
        output_group = english_output_group_name(group)
        fname = f"{project}_color_{idx:02d}_{output_group}.stl"
        warning = export_repaired_stl(
            extrude_geometry(geom, height_mm), out_dir / fname
        )
        if warning:
            manifold_warnings.append(warning)
        files.append(fname)
        colors_meta.append({
            "file": fname,
            "group": group,
            "area_mm2": round(float(geom.area), 2),
            "percent": round(float(100*geom.area/total_area), 1) if total_area else 0,
        })

    total_name = f"{project}_complete_cutout.stl"
    warning = export_repaired_stl(
        extrude_geometry(total, cut_depth_mm), out_dir / total_name
    )
    if warning:
        manifold_warnings.append(warning)
    files.append(total_name)

    clearance_tag = f"{clearance_mm:.2f}".replace(".", "_")
    neg_name = f"{project}_negative_clearance_{clearance_tag}mm.stl"
    negative = total.buffer(clearance_mm, join_style=2).buffer(0)
    warning = export_repaired_stl(
        extrude_geometry(negative, cut_depth_mm), out_dir / neg_name
    )
    if warning:
        manifold_warnings.append(warning)
    files.append(neg_name)

    preview_colors = {}
    for item in color_plan:
        if item.get("enabled", True):
            preview_colors[int(item["cluster"])] = item.get("rgb", [120,120,120])
    preview_name = f"{project}_preview.png"
    make_preview(label_img, preview_colors, out_dir / preview_name)

    minx,miny,maxx,maxy = total.bounds
    meta = {
        "project": project,
        "final_logo_width_mm": round(float(maxx-minx), 3),
        "final_logo_height_mm": round(float(maxy-miny), 3),
        "files": files,
        "colors": colors_meta,
        "total_file": total_name,
        "negative_file": neg_name,
        "preview": preview_name,
        "manifold_warnings": manifold_warnings,
        "settings": {
            "working_pixels": working_pixels,
            "geometry_pixels": geometry_pixels,
            "requested_logo_width_mm": float(manual_width_mm),
            "requested_logo_height_mm": (
                float(manual_height_mm)
                if manual_height_mm is not None else None
            ),
            "lock_aspect_ratio": bool(keep_aspect),
            "simplify_mm": simplify_mm,
            "clearance_mm": clearance_mm,
            "height_mm": height_mm,
            "cut_depth_mm": cut_depth_mm,
            "partition_missing_area_mm2": round(missing_area, 8),
            "partition_overlap_area_mm2": round(overlap_area, 8),
            "solid_master_body": True,
        }
    }
    with open(out_dir / f"{project}_info.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return meta
