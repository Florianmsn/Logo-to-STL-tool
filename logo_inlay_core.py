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
        raise ValueError("Keine sichtbaren Pixel gefunden.")
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
    """Choose the most plausible local color owner for one leftover polygon.

    The most important rule is continuity: whenever possible, a gap is assigned
    to a color it actually touches so it merges into that existing part instead
    of becoming a new floating island. The raster vote then resolves which of
    the touching colors is locally correct.
    """
    gid = _gap_pixel_vote(gap, group_map, mm_per_px)
    voted = names[gid] if gid is not None and 0 <= gid < len(names) else None

    # First identify colors that genuinely share boundary/contact with this gap.
    # Because the gap was produced by subtracting the vector pieces from total,
    # exact boundary contact is normally available.
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
        touching_names = {name for _, name in exact_contacts}
        if voted in touching_names:
            return voted
        exact_contacts.sort(reverse=True)
        return exact_contacts[0][1]

    # Numerical contour simplification can leave a microscopic separation.
    # Use a very narrow local band as a second continuity test.
    tol = max(float(mm_per_px) * 0.55, float(simplify_mm) * 0.12, 1e-6)
    band = gap.buffer(tol)
    near_contacts = []
    for name in names:
        geom = partition.get(name)
        if geom is None or geom.is_empty:
            continue
        try:
            score = float(band.intersection(geom).area)
        except Exception:
            score = 0.0
        if score > 0:
            near_contacts.append((score, name))

    if near_contacts:
        touching_names = {name for _, name in near_contacts}
        if voted in touching_names:
            return voted
        near_contacts.sort(reverse=True)
        return near_contacts[0][1]

    # If there is no geometric contact at all, fall back to the smoothed raster
    # ownership map, which is still local and far better than a global largest
    # color fallback.
    if voted is not None:
        geom = raw.get(voted)
        if geom is not None and not geom.is_empty:
            return voted

    distances = []
    probe = gap.representative_point()
    for name in names:
        geom = partition.get(name)
        if geom is None or geom.is_empty:
            geom = raw.get(name)
        if geom is None or geom.is_empty:
            continue
        try:
            distances.append((float(probe.distance(geom)), name))
        except Exception:
            pass

    if distances:
        distances.sort(key=lambda item: item[0])
        return distances[0][1]

    candidates = [
        (float(raw[name].area), name)
        for name in names
        if name in raw and raw[name] is not None and not raw[name].is_empty
    ]
    if candidates:
        return max(candidates)[1]
    return None


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

    V7.7 change:
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
        gaps_by_owner = {}
        for gap in iter_polygons(remaining):
            if gap.is_empty or gap.area <= 0:
                continue

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
                continue
            gaps_by_owner.setdefault(owner, []).append(gap)

        for owner, gaps in gaps_by_owner.items():
            existing = partition.get(owner)
            pieces = ([existing] if existing is not None and not existing.is_empty else [])
            pieces.extend(gaps)
            merged = unary_union(pieces).buffer(0)
            if not merged.is_empty:
                partition[owner] = merged

    # Numerical safety net. This should normally be effectively zero area.
    union_partition = unary_union(
        [g for g in partition.values() if g is not None and not g.is_empty]
    ).buffer(0)
    final_missing = total.difference(union_partition).buffer(0)

    if not final_missing.is_empty and final_missing.area > 1e-10:
        # Even this last-resort path is local per connected component.
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
                continue
            existing = partition.get(owner)
            partition[owner] = unary_union(
                [g for g in (existing, gap) if g is not None and not g.is_empty]
            ).buffer(0)

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
            raise ValueError("Polygon konnte für manifold STL nicht eindeutig repariert werden.")

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
            "Keine sichere Polygon-Triangulation verfügbar. "
            "Bitte Shapely >= 2.1 installieren."
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
    """Resolve 'auto verteilen' locally inside each connected AUTO region.

    Rules:
    1. A printable group may take over an AUTO component only if it actually
       touches that connected AUTO component.
    2. Assignment then propagates from those contact edges through the AUTO
       region using geodesic distance inside the AUTO region.
    3. Therefore a nearby color separated by background or another region
       cannot "jump across" and steal AUTO pixels.

    This is designed for anti-aliasing / transition tones around logos.
    """
    import cv2
    import numpy as np
    import heapq
    import math
    from collections import Counter

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
        return labels, plan

    # Group multiple detected colors which already belong to the same print group.
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

    # Map every printable source pixel to its destination group id.
    print_gid = np.full(labels.shape, -1, dtype=np.int16)
    for gid, cluster_ids in enumerate(group_cluster_ids):
        print_gid[np.isin(labels, cluster_ids)] = gid

    # Average RGB per printable group for tie-breaking at a shared boundary.
    group_rgb = []
    for cluster_ids in group_cluster_ids:
        rgbs = [cluster_rgb[c] for c in cluster_ids if c in cluster_rgb]
        if rgbs:
            group_rgb.append(np.mean(np.stack(rgbs), axis=0))
        else:
            group_rgb.append(np.array([128, 128, 128], dtype=np.float32))

    num_components, component_labels = cv2.connectedComponents(
        auto_mask.astype(np.uint8), connectivity=8
    )

    neighbors = [
        (-1, -1, math.sqrt(2.0)), (-1, 0, 1.0), (-1, 1, math.sqrt(2.0)),
        (0, -1, 1.0),                              (0, 1, 1.0),
        (1, -1, math.sqrt(2.0)),  (1, 0, 1.0),  (1, 1, math.sqrt(2.0)),
    ]
    h, w = labels.shape

    for cid in range(1, num_components):
        comp = component_labels == cid
        ys, xs = np.nonzero(comp)
        if len(ys) == 0:
            continue

        dist = np.full(labels.shape, np.inf, dtype=np.float32)
        owner = np.full(labels.shape, -1, dtype=np.int16)
        heap = []

        # Seed only from AUTO pixels that DIRECTLY touch a printable group.
        for y, x in zip(ys, xs):
            adjacent = []
            for dy, dx, _ in neighbors:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    gid = int(print_gid[ny, nx])
                    if gid >= 0:
                        adjacent.append(gid)

            if not adjacent:
                continue

            counts = Counter(adjacent)
            best_count = max(counts.values())
            candidates = [gid for gid, count in counts.items() if count == best_count]

            # If two colors touch the same AUTO boundary pixel equally often,
            # prefer the one whose RGB is closer to that AUTO source tone.
            source_cluster = int(labels[y, x])
            source_rgb = cluster_rgb.get(
                source_cluster, np.array([128, 128, 128], dtype=np.float32)
            )
            best_gid = min(
                candidates,
                key=lambda gid: float(np.linalg.norm(source_rgb - group_rgb[gid]))
            )

            if dist[y, x] > 0:
                dist[y, x] = 0.0
                owner[y, x] = best_gid
                heapq.heappush(heap, (0.0, y, x, best_gid))

        if heap:
            # Geodesic propagation ONLY through this AUTO component.
            while heap:
                d, y, x, gid = heapq.heappop(heap)
                if d > float(dist[y, x]) + 1e-6:
                    continue
                if int(owner[y, x]) != gid:
                    continue

                for dy, dx, step in neighbors:
                    ny, nx = y + dy, x + dx
                    if not (0 <= ny < h and 0 <= nx < w):
                        continue
                    if not comp[ny, nx]:
                        continue

                    nd = d + step
                    old = float(dist[ny, nx])
                    if nd + 1e-6 < old:
                        dist[ny, nx] = nd
                        owner[ny, nx] = gid
                        heapq.heappush(heap, (nd, ny, nx, gid))
                    elif abs(nd - old) <= 1e-6 and int(owner[ny, nx]) != gid:
                        # Stable tie: prefer the closer RGB group for this AUTO tone.
                        source_cluster = int(labels[ny, nx])
                        source_rgb = cluster_rgb.get(
                            source_cluster, np.array([128, 128, 128], dtype=np.float32)
                        )
                        current_gid = int(owner[ny, nx])
                        if current_gid < 0 or np.linalg.norm(
                            source_rgb - group_rgb[gid]
                        ) < np.linalg.norm(source_rgb - group_rgb[current_gid]):
                            owner[ny, nx] = gid

            for gid, cluster in enumerate(representative_cluster):
                mask = comp & (owner == gid)
                labels[mask] = cluster
        else:
            # Rare fallback: isolated AUTO component touches no printable color.
            # Use nearest printable group globally only in this exceptional case.
            component_coords = np.column_stack((ys, xs))
            best_gid_for_component = None
            best_dist = np.inf

            cy = float(np.mean(ys))
            cx = float(np.mean(xs))
            for gid in range(len(group_names)):
                gy, gx = np.nonzero(print_gid == gid)
                if len(gy) == 0:
                    continue
                squared = (gy.astype(np.float32) - cy) ** 2 + (
                    gx.astype(np.float32) - cx
                ) ** 2
                d = float(np.min(squared))
                if d < best_dist:
                    best_dist = d
                    best_gid_for_component = gid

            if best_gid_for_component is not None:
                labels[comp] = representative_cluster[best_gid_for_component]

    # Safety fallback:
    # A connected AUTO component should normally be fully resolved above.
    # If any AUTO pixels remain (e.g. unusual isolated topology), assign only
    # those leftovers to the spatially nearest printable group. This guarantees
    # that a successful calculation never leaves grey/AUTO pixels behind.
    remaining_auto = np.isin(labels, list(auto_clusters))
    if np.any(remaining_auto):
        distance_maps = []
        for cluster_ids in group_cluster_ids:
            group_mask = np.isin(labels, cluster_ids).astype(np.uint8)
            inv = np.where(group_mask > 0, 0, 1).astype(np.uint8)
            distance_maps.append(cv2.distanceTransform(inv, cv2.DIST_L2, 5))

        if distance_maps:
            nearest = np.argmin(np.stack(distance_maps, axis=0), axis=0)
            ys, xs = np.nonzero(remaining_auto)
            for y, x in zip(ys, xs):
                gid = int(nearest[y, x])
                labels[y, x] = representative_cluster[gid]

    # AUTO never exports as its own STL.
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
    """Build a raster preview from the exact same vector partition used by STL export."""
    image_path = Path(image_path)
    analysis = analyze_colors(
        image_path, working_pixels, detect_colors, background_mode,
        white_threshold, auto_merge, merge_distance
    )

    if label_override is not None:
        label_img = np.asarray(label_override, dtype=analysis["label_img"].dtype).copy()
        if label_img.shape != analysis["label_img"].shape:
            raise ValueError("Vorschau: manuelle Bearbeitung hat falsche Bildgröße.")
    else:
        label_img = analysis["label_img"].copy()

    label_img, plan, explicit_background_mask = extract_background_groups(label_img, color_plan)

    if manual_background_mask is not None:
        manual_bg = np.asarray(manual_background_mask, dtype=bool)
        if manual_bg.shape != label_img.shape:
            raise ValueError("Vorschau: manuelle Hintergrundmaske hat falsche Bildgröße.")
        explicit_background_mask = explicit_background_mask | manual_bg
        label_img[manual_bg] = -1

    label_img, plan = redistribute_auto_groups(label_img, plan)
    label_img, explicit_background_mask = upscale_geometry_grid(
        label_img, explicit_background_mask, geometry_pixels
    )

    ih, iw = label_img.shape
    width_mm = float(manual_width_mm)
    mm_per_px = width_mm / max(1, iw)
    min_area_px = max(1, int(min_area_mm2 / max(1e-12, mm_per_px ** 2)))

    groups = {}
    for item in plan:
        if not item.get("enabled", True):
            continue
        group_key = str(item.get("group") or item.get("name") or "").strip()
        if group_key.lower() in ("zu hintergrund", "auto verteilen"):
            continue
        cluster = int(item["cluster"])
        group = safe_filename_part(group_key or f"gruppe_{cluster}")
        groups.setdefault(group, []).append(cluster)

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

    # Optional non-proportional sizing. Existing/default keep_aspect=True behavior
    # is unchanged; only an explicitly disabled aspect lock uses Logo Höhe.
    render_h = ih
    if not keep_aspect and manual_height_mm is not None and float(manual_height_mm) > 0:
        target_y_mm_per_px = float(manual_height_mm) / max(1, ih)
        y_factor = target_y_mm_per_px / max(1e-12, mm_per_px)
        if abs(y_factor - 1.0) > 1e-9:
            geoms = {name: scale_geom(g, xfact=1.0, yfact=y_factor, origin=(0, 0)) for name, g in geoms.items()}
            total = scale_geom(total, xfact=1.0, yfact=y_factor, origin=(0, 0))
        render_h = max(1, int(round(float(manual_height_mm) / max(1e-12, mm_per_px))))

    rgba = np.zeros((render_h, iw, 4), dtype=np.uint8)
    masks = {}

    def geom_to_mask(geom):
        mask = np.zeros((render_h, iw), dtype=np.uint8)
        for poly in iter_polygons(geom):
            ext = np.asarray([
                [round(x / mm_per_px), round(render_h - y / mm_per_px)]
                for x, y in poly.exterior.coords
            ], dtype=np.int32)
            if len(ext) >= 3:
                cv2.fillPoly(mask, [ext], 255)
            for ring in poly.interiors:
                hole = np.asarray([
                    [round(x / mm_per_px), round(render_h - y / mm_per_px)]
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

    total_mask = geom_to_mask(total) if total is not None and not total.is_empty else np.zeros((render_h, iw), dtype=bool)

    union_groups = unary_union(list(geoms.values())).buffer(0) if geoms else MultiPolygon([])
    missing_area = float(total.difference(union_groups).area) if total is not None and not total.is_empty else 0.0
    overlap_area = max(
        0.0,
        float(sum(g.area for g in geoms.values()) - union_groups.area)
    ) if geoms else 0.0

    return {
        "rgba": rgba,
        "group_masks": masks,
        "total_mask": total_mask,
        "geoms": geoms,
        "total": total,
        "label_img": label_img,
        "mm_per_px": mm_per_px,
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
    raster_path = prepare_input_image(image_path, out_dir, project, working_pixels)
    save_input_copies(image_path, out_dir, project)
    analysis = analyze_colors(raster_path, working_pixels, detect_colors, background_mode, white_threshold, auto_merge, merge_distance)
    if label_override is not None:
        label_img = np.asarray(label_override, dtype=analysis["label_img"].dtype).copy()
        if label_img.shape != analysis["label_img"].shape:
            raise ValueError("Manuelle Bearbeitung hat eine andere Bildgröße als die Analyse.")
    else:
        label_img = analysis["label_img"].copy()

    label_img, color_plan, explicit_background_mask = extract_background_groups(label_img, color_plan)

    if manual_background_mask is not None:
        manual_bg = np.asarray(manual_background_mask, dtype=bool)
        if manual_bg.shape != label_img.shape:
            raise ValueError("Manuelle Hintergrundmaske hat eine andere Bildgröße als die Analyse.")
        explicit_background_mask = explicit_background_mask | manual_bg
        label_img[manual_bg] = -1

    label_img, color_plan = redistribute_auto_groups(label_img, color_plan)
    label_img, explicit_background_mask = upscale_geometry_grid(
        label_img, explicit_background_mask, geometry_pixels
    )
    rgba = analysis["rgba"]
    ih, iw = label_img.shape
    aspect = iw / ih
    width_mm = compute_logo_width(aspect, target_mode, manual_width_mm, deck_width_mm, deck_height_mm, margin_mm, fit_percent)
    mm_per_px = width_mm / iw
    min_area_px = max(1, int(min_area_mm2 / (mm_per_px ** 2)))

    groups = {}
    cluster_to_rgb = {}
    for item in color_plan:
        if not item.get("enabled", True):
            continue
        cluster = int(item["cluster"])
        group = safe_filename_part(item.get("group") or item.get("name") or f"gruppe_{cluster}")
        groups.setdefault(group, []).append(cluster)
        cluster_to_rgb[cluster] = item.get("rgb", [120,120,120])

    # Build one common, gap-free partition instead of vectorizing colors
    # independently. This guarantees that all color STLs exactly fill the total.
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

    if not keep_aspect and manual_height_mm is not None and float(manual_height_mm) > 0:
        target_y_mm_per_px = float(manual_height_mm) / max(1, ih)
        y_factor = target_y_mm_per_px / max(1e-12, mm_per_px)
        if abs(y_factor - 1.0) > 1e-9:
            geoms = {name: scale_geom(g, xfact=1.0, yfact=y_factor, origin=(0, 0)) for name, g in geoms.items()}
            total = scale_geom(total, xfact=1.0, yfact=y_factor, origin=(0, 0))

    if not geoms or total.is_empty:
        raise ValueError("Keine aktiven Farbflächen erzeugt. Prüfe Farbauswahl.")

    # Für den zusätzlichen SVG Export pro Gruppe eine repräsentative Farbe merken.
    group_color_meta = {}
    for item in color_plan:
        if not item.get("enabled", True):
            continue
        group = safe_filename_part(item.get("group") or item.get("name") or f"gruppe_{item['cluster']}")
        if group not in group_color_meta:
            group_color_meta[group] = item.get("rgb", [160, 160, 160])

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
    preview_name = f"{project}_vorschau.png"
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
