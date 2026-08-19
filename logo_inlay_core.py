from __future__ import annotations

import json
import re
import shutil
from collections import deque
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image
from shapely.affinity import scale as scale_geom, translate
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, box
from shapely.ops import unary_union
try:
    from shapely import constrained_delaunay_triangles
except Exception:
    constrained_delaunay_triangles = None
import trimesh


BG_ID = -1
AUTO_ID = -2

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


def safe_filename_part(text: str) -> str:
    text = str(text or "").lower().replace("ß", "ss")
    text = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
    return text or "logo"


def english_output_group_name(group_name: str) -> str:
    text = str(group_name or "").strip()
    lower = text.lower()
    if lower in OUTPUT_GROUP_NAMES:
        return OUTPUT_GROUP_NAMES[lower]
    m = re.match(r"^(.*?)(?:\s+)(\d+)$", lower)
    if m and m.group(1) in OUTPUT_GROUP_NAMES:
        return f"{OUTPUT_GROUP_NAMES[m.group(1)]}_{m.group(2)}"
    return safe_filename_part(text)


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


# ---------------------------------------------------------------------------
# Image analysis
# ---------------------------------------------------------------------------


def load_rgba(path: Path, working_pixels: int) -> np.ndarray:
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    limit = max(100, int(working_pixels))
    scale = min(1.0, limit / max(w, h))
    if scale < 1.0:
        img = img.resize(
            (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
            Image.Resampling.LANCZOS,
        )
    return np.asarray(img, dtype=np.uint8)


def remove_edge_background_rgba(rgba: np.ndarray, tolerance: float = 18.0) -> np.ndarray:
    arr = np.asarray(rgba, dtype=np.uint8).copy()
    h, w = arr.shape[:2]
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3]

    edge_pixels = np.concatenate(
        [rgb[0], rgb[h - 1], rgb[:, 0], rgb[:, w - 1]], axis=0
    )
    bg = np.median(edge_pixels, axis=0).astype(np.float32)
    diff = np.linalg.norm(rgb - bg, axis=2)
    candidate = (diff <= float(tolerance)) & (alpha > 0)
    if not np.any(candidate):
        return arr

    count, labels = cv2.connectedComponents(candidate.astype(np.uint8), connectivity=8)
    if count <= 1:
        return arr

    border_ids = np.unique(
        np.concatenate([labels[0], labels[h - 1], labels[:, 0], labels[:, w - 1]])
    )
    border_ids = border_ids[border_ids != 0]
    if border_ids.size:
        arr[np.isin(labels, border_ids), 3] = 0
    return arr


def build_visible_mask(
    rgba: np.ndarray, background_mode: str, white_threshold: int
) -> np.ndarray:
    alpha = rgba[:, :, 3]
    rgb = rgba[:, :, :3]
    visible = alpha > 10
    mode = str(background_mode or "transparent").lower()

    if mode in ("transparent", "all", "edge"):
        return visible
    if mode == "white":
        not_white = ~(
            (rgb[:, :, 0] >= white_threshold)
            & (rgb[:, :, 1] >= white_threshold)
            & (rgb[:, :, 2] >= white_threshold)
        )
        return visible & not_white
    if mode == "corner":
        h, w = alpha.shape
        corners = np.asarray(
            [rgb[0, 0], rgb[0, w - 1], rgb[h - 1, 0], rgb[h - 1, w - 1]],
            dtype=np.float32,
        )
        bg = np.median(corners, axis=0)
        diff = np.linalg.norm(rgb.astype(np.float32) - bg, axis=2)
        return visible & (diff > 28.0)
    return visible


def _sample_pixels_for_kmeans(pixels: np.ndarray, max_samples: int = 250_000) -> np.ndarray:
    if len(pixels) <= max_samples:
        return pixels
    # Deterministic evenly spaced sample: fast and reproducible across runs.
    idx = np.linspace(0, len(pixels) - 1, max_samples, dtype=np.int64)
    return pixels[idx]


def quantize(rgba: np.ndarray, visible: np.ndarray, k: int):
    rgb = rgba[:, :, :3]
    pixels_u8 = rgb[visible].reshape((-1, 3))
    if pixels_u8.size == 0:
        raise ValueError("No visible pixels were found in the selected image.")

    # Determine the usable K on the same bounded deterministic sample used for
    # K-Means. Avoid np.unique over millions of full-resolution pixels.
    sample_u8 = _sample_pixels_for_kmeans(pixels_u8)
    unique_count = len(np.unique(sample_u8, axis=0))
    k = max(1, min(int(k), unique_count))
    pixels = pixels_u8.astype(np.float32)
    sample = sample_u8.astype(np.float32)

    cv2.setRNGSeed(12345)
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        60,
        0.20,
    )
    _, _, centers = cv2.kmeans(
        sample,
        k,
        None,
        criteria,
        3,
        cv2.KMEANS_PP_CENTERS,
    )
    centers = np.clip(centers, 0, 255).astype(np.float32)

    # Assign all visible pixels to the learned centers in bounded chunks.
    assignments = np.empty(len(pixels), dtype=np.int32)
    chunk = 200_000
    for start in range(0, len(pixels), chunk):
        part = pixels[start : start + chunk]
        d2 = np.sum((part[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        assignments[start : start + len(part)] = np.argmin(d2, axis=1)

    # Recompute center colors from all assigned pixels for representative swatches.
    final_centers = np.zeros((k, 3), dtype=np.float64)
    for cid in range(k):
        mask = assignments == cid
        if np.any(mask):
            final_centers[cid] = np.mean(pixels[mask], axis=0)
        else:
            final_centers[cid] = centers[cid]

    label_img = np.full(visible.shape, -1, dtype=np.int32)
    label_img[visible] = assignments
    return label_img, np.clip(final_centers, 0, 255).astype(np.uint8)


def merge_similar_clusters(label_img, centers, distance):
    if len(centers) <= 1 or float(distance) <= 0:
        return label_img, centers

    parent = list(range(len(centers)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(centers)):
        for j in range(i + 1, len(centers)):
            if np.linalg.norm(
                centers[i].astype(float) - centers[j].astype(float)
            ) <= float(distance):
                union(i, j)

    groups = {}
    for i in range(len(centers)):
        groups.setdefault(find(i), []).append(i)

    new_label = np.full_like(label_img, -1)
    new_centers = []
    for new_idx, group in enumerate(groups.values()):
        mask = np.isin(label_img, group)
        if not np.any(mask):
            continue
        values = np.asarray([centers[g] for g in group], dtype=np.float64)
        new_centers.append(np.clip(np.mean(values, axis=0), 0, 255).astype(np.uint8))
        new_label[mask] = new_idx

    return new_label, np.asarray(new_centers, dtype=np.uint8)


def analyze_colors(
    image_path: Path,
    working_pixels: int = 1600,
    detect_colors: int = 4,
    background_mode: str = "transparent",
    white_threshold: int = 245,
    auto_merge: bool = True,
    merge_distance: float = 18.0,
):
    image_path = Path(image_path)
    if image_path.suffix.lower() == ".svg":
        raise RuntimeError("SVG input is not supported. Please export the logo as PNG first.")

    rgba = load_rgba(image_path, working_pixels)
    if str(background_mode).lower() == "edge":
        rgba = remove_edge_background_rgba(rgba, tolerance=18.0)

    visible = build_visible_mask(rgba, background_mode, int(white_threshold))
    label_img, centers = quantize(rgba, visible, int(detect_colors))
    if auto_merge:
        label_img, centers = merge_similar_clusters(
            label_img, centers, float(merge_distance)
        )

    total = int(np.count_nonzero(label_img >= 0))
    colors = []
    for idx, center in enumerate(centers):
        count = int(np.count_nonzero(label_img == idx))
        if count <= 0:
            continue
        rgb = [int(v) for v in center]
        colors.append(
            {
                "cluster": int(idx),
                "name": closest_color_name(rgb),
                "rgb": rgb,
                "pixel_count": count,
                "percent": round(100.0 * count / total, 1) if total else 0.0,
                "enabled": True,
                "group": closest_color_name(rgb),
            }
        )
    colors.sort(key=lambda item: item["pixel_count"], reverse=True)

    return {
        "width_px": int(rgba.shape[1]),
        "height_px": int(rgba.shape[0]),
        "colors": colors,
        "label_img": label_img,
        "centers": centers,
        "rgba": rgba,
        "visible_mask": visible,
    }


# ---------------------------------------------------------------------------
# Final color map: this is the single source of truth after Calculate.
# ---------------------------------------------------------------------------


def _normalize_group_name(value) -> str:
    return str(value or "").strip()


def _build_group_model(color_plan: list[dict]):
    group_defs = []
    group_index = {}
    cluster_to_gid = {}
    auto_clusters = set()
    bg_clusters = set()
    disabled_clusters = set()
    representative_cluster = {}

    for item in color_plan:
        cluster = int(item["cluster"])
        enabled = bool(item.get("enabled", True))
        group = _normalize_group_name(item.get("group", item.get("name", "")))
        key = group.lower()

        if not enabled:
            disabled_clusters.add(cluster)
            continue
        if key == "zu hintergrund":
            bg_clusters.add(cluster)
            continue
        if key == "auto verteilen":
            auto_clusters.add(cluster)
            continue

        if group not in group_index:
            gid = len(group_defs)
            group_index[group] = gid
            rgb = [int(v) for v in item.get("rgb", [160, 160, 160])]
            group_defs.append(
                {
                    "id": gid,
                    "name": group,
                    "safe_name": english_output_group_name(group),
                    "rgb": rgb,
                }
            )
            representative_cluster[gid] = cluster
        gid = group_index[group]
        cluster_to_gid[cluster] = gid

    return {
        "group_defs": group_defs,
        "cluster_to_gid": cluster_to_gid,
        "auto_clusters": auto_clusters,
        "bg_clusters": bg_clusters,
        "disabled_clusters": disabled_clusters,
        "representative_cluster": representative_cluster,
    }


def _labels_to_group_map(label_img: np.ndarray, model: dict, background_mask=None):
    labels = np.asarray(label_img)
    group_map = np.full(labels.shape, BG_ID, dtype=np.int16)

    for cluster, gid in model["cluster_to_gid"].items():
        group_map[labels == int(cluster)] = int(gid)
    for cluster in model["auto_clusters"]:
        group_map[labels == int(cluster)] = AUTO_ID

    if background_mask is not None:
        bg = np.asarray(background_mask, dtype=bool)
        if bg.shape != group_map.shape:
            raise ValueError("The manual background mask has a different image size.")
        group_map[bg] = BG_ID

    return group_map


def _active_bbox(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    return x0, y0, x1, y1


def _physical_island_threshold_px(
    group_map: np.ndarray,
    min_area_mm2: float,
    target_width_mm: float,
    target_height_mm: float | None,
    keep_aspect: bool,
) -> int:
    try:
        min_area = float(min_area_mm2)
        width_mm = float(target_width_mm)
    except Exception:
        return 1
    if not np.isfinite(min_area) or min_area <= 0 or width_mm <= 0:
        return 1

    bbox = _active_bbox(group_map != BG_ID)
    if bbox is None:
        return 1
    x0, y0, x1, y1 = bbox
    pw = max(1, x1 - x0)
    ph = max(1, y1 - y0)
    x_mm = width_mm / pw

    if keep_aspect or target_height_mm is None:
        y_mm = x_mm
    else:
        try:
            height_mm = float(target_height_mm)
        except Exception:
            height_mm = width_mm * ph / pw
        if not np.isfinite(height_mm) or height_mm <= 0:
            height_mm = width_mm * ph / pw
        y_mm = height_mm / ph

    pixel_area = max(1e-12, x_mm * y_mm)
    return max(1, int(np.ceil(min_area / pixel_area)))


def _stable_group_components(group_map: np.ndarray, threshold_px: int):
    """Map only genuinely stable, sufficiently large print-color components.

    Manual-locked tiny components are preserved by `_despeckle_group_map`, but
    they are deliberately NOT promoted to stable neighbor seeds. This keeps a
    one-pixel Manual correction authoritative without allowing it to grow by
    absorbing nearby automatic noise.
    """
    stable = np.full(group_map.shape, -1, dtype=np.int16)
    image_h, image_w = group_map.shape

    gids = [int(v) for v in np.unique(group_map) if int(v) >= 0]
    for gid in gids:
        mask = (group_map == gid).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        for cid in range(1, count):
            area = int(stats[cid, cv2.CC_STAT_AREA])
            if area < threshold_px:
                continue
            x = int(stats[cid, cv2.CC_STAT_LEFT])
            y = int(stats[cid, cv2.CC_STAT_TOP])
            cw = int(stats[cid, cv2.CC_STAT_WIDTH])
            ch = int(stats[cid, cv2.CC_STAT_HEIGHT])
            x1 = min(image_w, x + cw)
            y1 = min(image_h, y + ch)
            cc_roi = labels[y:y1, x:x1]
            component = cc_roi == cid
            stable_roi = stable[y:y1, x:x1]
            stable_roi[component] = gid
    return stable

def _edge_neighbor_counts(component: np.ndarray, stable_map: np.ndarray, original_gid: int):
    component = np.asarray(component, dtype=bool)
    counts = {}
    h, w = component.shape
    ys, xs = np.nonzero(component)
    for y, x in zip(ys, xs):
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if not (0 <= ny < h and 0 <= nx < w) or component[ny, nx]:
                continue
            gid = int(stable_map[ny, nx])
            if gid >= 0 and gid != original_gid:
                counts[gid] = counts.get(gid, 0) + 1
    return counts


def _local_majority(component: np.ndarray, stable_map: np.ndarray, candidates):
    candidates = set(int(v) for v in candidates)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    dilated = cv2.dilate(component.astype(np.uint8), kernel, iterations=1).astype(bool)
    ring = dilated & (~component)
    values = stable_map[ring]
    return {gid: int(np.count_nonzero(values == gid)) for gid in candidates}


def _despeckle_group_map(group_map: np.ndarray, threshold_px: int, locked_mask=None):
    original = np.asarray(group_map, dtype=np.int16)
    if threshold_px <= 1:
        return original.copy(), {"changed_pixels": 0, "changed_components": 0}

    result = original.copy()
    locked = (
        np.asarray(locked_mask, dtype=bool)
        if locked_mask is not None and np.asarray(locked_mask).shape == original.shape
        else np.zeros(original.shape, dtype=bool)
    )
    stable = _stable_group_components(original, threshold_px)
    image_h, image_w = original.shape

    changed_pixels = 0
    changed_components = 0
    gids = [int(v) for v in np.unique(original) if int(v) >= 0]

    for gid in gids:
        mask = (original == gid).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        for cid in range(1, count):
            area = int(stats[cid, cv2.CC_STAT_AREA])
            if area >= threshold_px:
                continue

            x = int(stats[cid, cv2.CC_STAT_LEFT])
            y = int(stats[cid, cv2.CC_STAT_TOP])
            cw = int(stats[cid, cv2.CC_STAT_WIDTH])
            ch = int(stats[cid, cv2.CC_STAT_HEIGHT])
            pad = 2
            x0 = max(0, x - pad)
            y0 = max(0, y - pad)
            x1 = min(image_w, x + cw + pad)
            y1 = min(image_h, y + ch + pad)

            cc_roi = labels[y0:y1, x0:x1]
            component = cc_roi == cid
            if np.any(locked[y0:y1, x0:x1] & component):
                continue

            stable_roi = stable[y0:y1, x0:x1]
            counts = _edge_neighbor_counts(component, stable_roi, gid)
            if not counts:
                continue
            best_edges = max(counts.values())
            tied = [g for g, score in counts.items() if score == best_edges]
            if len(tied) == 1:
                owner = tied[0]
            else:
                local = _local_majority(component, stable_roi, tied)
                best_local = max(local.get(g, 0) for g in tied)
                owner = min(g for g in tied if local.get(g, 0) == best_local)

            result_roi = result[y0:y1, x0:x1]
            result_roi[component] = owner
            changed_pixels += area
            changed_components += 1

    return result, {
        "changed_pixels": int(changed_pixels),
        "changed_components": int(changed_components),
    }

def _resolve_auto_map(group_map: np.ndarray):
    result = np.asarray(group_map, dtype=np.int16).copy()
    auto_mask = result == AUTO_ID
    if not np.any(auto_mask):
        return result, {"resolved_pixels": 0, "unresolved_components": 0, "unresolved_pixels": 0}

    count, components = cv2.connectedComponents(auto_mask.astype(np.uint8), connectivity=4)
    h, w = result.shape
    resolved_pixels = 0
    unresolved_components = 0
    unresolved_pixels = 0

    for cid in range(1, count):
        comp = components == cid
        ys, xs = np.nonzero(comp)
        if len(xs) == 0:
            continue

        y0, y1 = int(ys.min()), int(ys.max())
        x0, x1 = int(xs.min()), int(xs.max())
        roi = comp[y0 : y1 + 1, x0 : x1 + 1]
        rh, rw = roi.shape

        seeds = {}
        contact_counts = {}
        for y, x in zip(ys, xs):
            local_seen = set()
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if not (0 <= ny < h and 0 <= nx < w):
                    continue
                gid = int(result[ny, nx])
                if gid >= 0:
                    contact_counts[gid] = contact_counts.get(gid, 0) + 1
                    local_seen.add(gid)
            for gid in local_seen:
                seeds.setdefault(gid, set()).add((int(y - y0), int(x - x0)))

        candidates = sorted(seeds)
        if not candidates:
            unresolved_components += 1
            unresolved_pixels += int(len(xs))
            continue
        if len(candidates) == 1:
            result[comp] = candidates[0]
            resolved_pixels += int(len(xs))
            continue

        inf = np.iinfo(np.int32).max
        distances = {}
        for gid in candidates:
            dist = np.full((rh, rw), inf, dtype=np.int32)
            q = deque()
            for ly, lx in seeds[gid]:
                dist[ly, lx] = 0
                q.append((ly, lx))
            while q:
                ly, lx = q.popleft()
                nd = int(dist[ly, lx]) + 1
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = ly + dy, lx + dx
                    if not (0 <= ny < rh and 0 <= nx < rw) or not roi[ny, nx]:
                        continue
                    if nd < int(dist[ny, nx]):
                        dist[ny, nx] = nd
                        q.append((ny, nx))
            distances[gid] = dist

        for y, x in zip(ys, xs):
            ly, lx = int(y - y0), int(x - x0)
            best_d = min(int(distances[g][ly, lx]) for g in candidates)
            tied = [g for g in candidates if int(distances[g][ly, lx]) == best_d]
            if len(tied) == 1:
                owner = tied[0]
            else:
                # No RGB guessing. Prefer the color with the strongest real edge
                # contact to this AUTO component, then stable group id.
                best_contact = max(contact_counts.get(g, 0) for g in tied)
                owner = min(g for g in tied if contact_counts.get(g, 0) == best_contact)
            result[y, x] = owner
            resolved_pixels += 1

    return result, {
        "resolved_pixels": int(resolved_pixels),
        "unresolved_components": int(unresolved_components),
        "unresolved_pixels": int(unresolved_pixels),
    }


def finalize_color_map(
    label_img: np.ndarray,
    color_plan: list[dict],
    manual_background_mask=None,
    manual_locked_mask=None,
    min_area_mm2: float = 0.05,
    target_width_mm: float = 70.0,
    target_height_mm: float | None = None,
    keep_aspect: bool = True,
):
    """Create the immutable print-group map used by every later stage.

    After this function returns, STL geometry never chooses or changes a color.
    Values in `final_group_map` are:
        -1 = BG / non-printing
         0..N = final print-group IDs
    """
    labels = np.asarray(label_img)
    model = _build_group_model(color_plan)
    if not model["group_defs"]:
        raise ValueError("No active print-color group is available.")

    group_map = _labels_to_group_map(labels, model, manual_background_mask)
    threshold_px = _physical_island_threshold_px(
        group_map,
        min_area_mm2,
        target_width_mm,
        target_height_mm,
        keep_aspect,
    )

    pre, pre_stats = _despeckle_group_map(group_map, threshold_px, manual_locked_mask)
    auto_resolved, auto_stats = _resolve_auto_map(pre)
    if auto_stats["unresolved_components"] > 0:
        raise ValueError(
            "AUTO could not resolve "
            f"{auto_stats['unresolved_components']} isolated region(s) / "
            f"{auto_stats['unresolved_pixels']} pixel(s). AUTO only uses print "
            "colors sharing a real horizontal/vertical pixel edge. Assign those "
            "isolated regions manually."
        )
    final_map, post_stats = _despeckle_group_map(
        auto_resolved, threshold_px, manual_locked_mask
    )

    if manual_background_mask is not None:
        bg = np.asarray(manual_background_mask, dtype=bool)
        final_map[bg] = BG_ID

    # Translate final group IDs back to representative analysis-cluster IDs for
    # the existing Manual editor. This is display/edit storage only; geometry
    # never uses these cluster labels again.
    resolved_labels = labels.copy()
    for gid, cluster in model["representative_cluster"].items():
        resolved_labels[final_map == gid] = int(cluster)

    present = set(int(v) for v in np.unique(final_map) if int(v) >= 0)
    group_defs = [dict(item, present=(item["id"] in present)) for item in model["group_defs"]]

    return {
        "final_group_map": final_map.astype(np.int16, copy=False),
        "group_defs": group_defs,
        "resolved_label_img": resolved_labels,
        "threshold_px": int(threshold_px),
        "stats": {
            "pre_cleanup_pixels": int(pre_stats["changed_pixels"]),
            "pre_cleanup_components": int(pre_stats["changed_components"]),
            "auto_resolved_pixels": int(auto_stats["resolved_pixels"]),
            "post_cleanup_pixels": int(post_stats["changed_pixels"]),
            "post_cleanup_components": int(post_stats["changed_components"]),
            "cleanup_pixels": int(pre_stats["changed_pixels"] + post_stats["changed_pixels"]),
            "cleanup_components": int(pre_stats["changed_components"] + post_stats["changed_components"]),
        },
    }


# Compatibility wrappers for older call sites / user scripts.
def redistribute_auto_groups(label_img, color_plan):
    model = _build_group_model(color_plan)
    group_map = _labels_to_group_map(np.asarray(label_img), model)
    resolved, stats = _resolve_auto_map(group_map)
    out = np.asarray(label_img).copy()
    for gid, cluster in model["representative_cluster"].items():
        out[resolved == gid] = int(cluster)
    plan = [dict(item) for item in color_plan]
    if stats["unresolved_components"] == 0:
        auto_clusters = model["auto_clusters"]
        for item in plan:
            if int(item["cluster"]) in auto_clusters:
                item["enabled"] = False
    return out, plan


def cleanup_small_color_islands(
    label_img,
    color_plan,
    min_area_mm2,
    target_width_mm,
    target_height_mm=None,
    keep_aspect=True,
    background_mask=None,
    locked_mask=None,
):
    model = _build_group_model(color_plan)
    group_map = _labels_to_group_map(np.asarray(label_img), model, background_mask)
    threshold = _physical_island_threshold_px(
        group_map,
        min_area_mm2,
        target_width_mm,
        target_height_mm,
        keep_aspect,
    )
    cleaned, stats = _despeckle_group_map(group_map, threshold, locked_mask)
    out = np.asarray(label_img).copy()
    for gid, cluster in model["representative_cluster"].items():
        out[cleaned == gid] = int(cluster)
    stats = dict(stats)
    stats["threshold_px"] = int(threshold)
    return out, stats


# ---------------------------------------------------------------------------
# Exact raster-cell geometry. No recoloring, smoothing or gap ownership.
# ---------------------------------------------------------------------------


def iter_polygons(geom):
    if geom is None or geom.is_empty:
        return
    if isinstance(geom, Polygon):
        yield geom
    elif isinstance(geom, MultiPolygon):
        yield from geom.geoms
    elif isinstance(geom, GeometryCollection):
        for item in geom.geoms:
            yield from iter_polygons(item)


def _run_rectangles(mask: np.ndarray):
    """Merge identical horizontal runs vertically into large pixel rectangles."""
    h, _ = mask.shape
    active = {}
    finished = []

    for y in range(h):
        row = np.asarray(mask[y], dtype=bool)
        padded = np.concatenate(([False], row, [False])).astype(np.int8)
        delta = np.diff(padded)
        starts = np.flatnonzero(delta == 1)
        ends = np.flatnonzero(delta == -1)

        current = {}
        for x0, x1 in zip(starts, ends):
            key = (int(x0), int(x1))
            if key in active:
                y0, _old_y1 = active[key]
                current[key] = (y0, y + 1)
            else:
                current[key] = (y, y + 1)

        for key, (y0, y1) in active.items():
            if key not in current:
                finished.append((key[0], y0, key[1], y1))
        active = current

    for key, (y0, y1) in active.items():
        finished.append((key[0], y0, key[1], y1))
    return finished


def _pixel_group_geometry(cropped_map: np.ndarray, gid: int):
    h, _ = cropped_map.shape
    rects = _run_rectangles(cropped_map == gid)
    if not rects:
        return None
    boxes = [box(x0, h - y1, x1, h - y0) for x0, y0, x1, y1 in rects]
    geom = unary_union(boxes)
    # GEOS union of axis-aligned cells is already valid; buffer(0) is only a
    # last inexpensive normalization for extremely fragmented maps.
    if not geom.is_valid:
        geom = geom.buffer(0)
    return geom


def build_exact_geometry(
    final_group_map: np.ndarray,
    group_defs: list[dict],
    width_mm: float,
    height_mm: float | None = None,
    keep_aspect: bool = True,
    center_output: bool = False,
):
    group_map = np.asarray(final_group_map, dtype=np.int16)
    if group_map.ndim != 2:
        raise ValueError("Final color map must be a 2D array.")

    bbox = _active_bbox(group_map >= 0)
    if bbox is None:
        raise ValueError("The final color map contains no printable pixels.")
    x0, y0, x1, y1 = bbox
    cropped = group_map[y0:y1, x0:x1]
    h, w = cropped.shape

    width_mm = float(width_mm)
    if not np.isfinite(width_mm) or width_mm <= 0:
        raise ValueError("Logo Width must be greater than 0 mm.")
    if keep_aspect:
        final_h = width_mm * h / max(1, w)
    else:
        if height_mm is None:
            raise ValueError("Logo Height is required when aspect ratio is unlocked.")
        final_h = float(height_mm)
        if not np.isfinite(final_h) or final_h <= 0:
            raise ValueError("Logo Height must be greater than 0 mm.")

    sx = width_mm / w
    sy = final_h / h

    geoms = {}
    for item in group_defs:
        gid = int(item["id"])
        if not np.any(cropped == gid):
            continue
        geom = _pixel_group_geometry(cropped, gid)
        if geom is None or geom.is_empty:
            continue
        geoms[item["name"]] = scale_geom(geom, xfact=sx, yfact=sy, origin=(0, 0))

    if not geoms:
        raise ValueError("No printable color geometry could be created.")

    total = unary_union(list(geoms.values()))
    if not total.is_valid:
        total = total.buffer(0)

    if center_output:
        minx, miny, maxx, maxy = total.bounds
        dx = -((minx + maxx) / 2.0)
        dy = -((miny + maxy) / 2.0)
        total = translate(total, xoff=dx, yoff=dy)
        geoms = {name: translate(g, xoff=dx, yoff=dy) for name, g in geoms.items()}

    union = unary_union(list(geoms.values()))
    missing = float(total.difference(union).area)
    overlap = max(0.0, float(sum(g.area for g in geoms.values()) - union.area))

    return {
        "cropped_group_map": cropped,
        "crop_box": (x0, y0, x1, y1),
        "geoms": geoms,
        "total": total,
        "final_width_mm": float(width_mm),
        "final_height_mm": float(final_h),
        "missing_area_mm2": missing,
        "overlap_area_mm2": overlap,
        "source_width_px": int(w),
        "source_height_px": int(h),
    }


def _group_color_lookup(group_defs: list[dict], group_colors=None):
    group_colors = group_colors or {}
    out = {}
    for item in group_defs:
        name = item["name"]
        safe = safe_filename_part(name)
        rgb = group_colors.get(name, group_colors.get(safe, item.get("rgb", [160, 160, 160])))
        out[int(item["id"])] = np.asarray([int(v) for v in rgb], dtype=np.uint8)
    return out


def render_final_map_rgba(final_group_map, group_defs, group_colors=None):
    group_map = np.asarray(final_group_map, dtype=np.int16)
    bbox = _active_bbox(group_map >= 0)
    if bbox is None:
        raise ValueError("The final color map contains no printable pixels.")
    x0, y0, x1, y1 = bbox
    cropped = group_map[y0:y1, x0:x1]
    rgba = np.zeros((cropped.shape[0], cropped.shape[1], 4), dtype=np.uint8)
    colors = _group_color_lookup(group_defs, group_colors)
    for gid, rgb in colors.items():
        mask = cropped == gid
        rgba[mask, :3] = rgb
        rgba[mask, 3] = 255
    return rgba, cropped


def build_partition_preview(
    final_group_map: np.ndarray,
    group_defs: list[dict],
    manual_width_mm: float,
    manual_height_mm: float | None = None,
    keep_aspect: bool = True,
    group_colors=None,
    **_legacy_ignored,
):
    geometry = build_exact_geometry(
        final_group_map=final_group_map,
        group_defs=group_defs,
        width_mm=manual_width_mm,
        height_mm=manual_height_mm,
        keep_aspect=keep_aspect,
        center_output=False,
    )
    rgba, cropped = render_final_map_rgba(final_group_map, group_defs, group_colors)

    group_masks = {}
    for item in group_defs:
        gid = int(item["id"])
        if np.any(cropped == gid):
            group_masks[safe_filename_part(item["name"])] = cropped == gid

    return {
        "rgba": rgba,
        "label_img": cropped,
        "group_masks": group_masks,
        "total_mask": cropped >= 0,
        "geoms": geometry["geoms"],
        "total": geometry["total"],
        "final_width_mm": geometry["final_width_mm"],
        "final_height_mm": geometry["final_height_mm"],
        "missing_area_mm2": geometry["missing_area_mm2"],
        "overlap_area_mm2": geometry["overlap_area_mm2"],
        "source_width_px": geometry["source_width_px"],
        "source_height_px": geometry["source_height_px"],
        "geometry_mode": "Exact raster-cell geometry",
    }


# ---------------------------------------------------------------------------
# Manifold extrusion / export
# ---------------------------------------------------------------------------


def _ring_area(coords):
    area = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:] + coords[:1]):
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _clean_ring(coords):
    pts = list(coords)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    cleaned = []
    for point in pts:
        p = (float(point[0]), float(point[1]))
        if not cleaned or cleaned[-1] != p:
            cleaned.append(p)
    return cleaned


def _extrude_polygon_manifold(poly: Polygon, height_mm: float) -> trimesh.Trimesh:
    if poly.is_empty or poly.area <= 0:
        return trimesh.Trimesh(vertices=[], faces=[], process=False)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if not isinstance(poly, Polygon):
        raise ValueError("A polygon could not be repaired for STL export.")
    if constrained_delaunay_triangles is None:
        raise RuntimeError("Shapely >= 2.1 is required for safe STL triangulation.")

    vertices = []
    faces = []
    vertex_map = {}

    def vertex_id(x, y, z):
        key = (round(float(x), 12), round(float(y), 12), round(float(z), 12))
        idx = vertex_map.get(key)
        if idx is None:
            idx = len(vertices)
            vertex_map[key] = idx
            vertices.append((float(x), float(y), float(z)))
        return idx

    tri_geom = constrained_delaunay_triangles(poly)
    triangles = []
    for tri in getattr(tri_geom, "geoms", []):
        if tri.is_empty or tri.area <= 0:
            continue
        coords = list(tri.exterior.coords)[:-1]
        if len(coords) == 3:
            triangles.append(coords)
    if not triangles:
        raise RuntimeError("No safe polygon triangulation could be created.")

    for coords in triangles:
        if _ring_area(list(coords)) < 0:
            coords = [coords[0], coords[2], coords[1]]
        top = [vertex_id(x, y, height_mm) for x, y in coords]
        bottom = [vertex_id(x, y, 0.0) for x, y in coords]
        faces.append(top)
        faces.append([bottom[2], bottom[1], bottom[0]])

    def add_ring_sides(ring, is_hole=False):
        pts = _clean_ring(ring.coords)
        if len(pts) < 3:
            return
        area = _ring_area(pts)
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

    add_ring_sides(poly.exterior, False)
    for ring in poly.interiors:
        add_ring_sides(ring, True)

    mesh = trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=np.float64),
        faces=np.asarray(faces, dtype=np.int64),
        process=False,
        validate=False,
    )
    try:
        mesh.remove_unreferenced_vertices()
    except Exception:
        pass
    return mesh


def extrude_geometry(geom, height_mm):
    meshes = []
    for original in iter_polygons(geom):
        repaired = original if original.is_valid else original.buffer(0)
        for poly in iter_polygons(repaired):
            if poly.is_empty or poly.area <= 0:
                continue
            mesh = _extrude_polygon_manifold(poly, float(height_mm))
            if not mesh.is_empty:
                meshes.append(mesh)
    if not meshes:
        return trimesh.Trimesh(vertices=[], faces=[], process=False)
    return meshes[0] if len(meshes) == 1 else trimesh.util.concatenate(meshes)


def _mesh_manifold_edge_counts(mesh: trimesh.Trimesh):
    if mesh.is_empty:
        return 0, 0, 0
    edges = np.sort(np.asarray(mesh.edges, dtype=np.int64), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return (
        int(np.count_nonzero(counts != 2)),
        int(np.count_nonzero(counts == 1)),
        int(np.count_nonzero(counts > 2)),
    )


def export_repaired_stl(mesh, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_bad, raw_boundary, raw_overused = _mesh_manifold_edge_counts(mesh)
    raw_warning = raw_bad != 0 or not mesh.is_watertight
    mesh.export(path)

    roundtrip_error = None
    try:
        loaded = trimesh.load_mesh(path, process=True)
        bad, boundary, overused = _mesh_manifold_edge_counts(loaded)
        watertight = bool(loaded.is_watertight)
    except Exception as exc:
        roundtrip_error = str(exc)
        bad, boundary, overused = raw_bad, raw_boundary, raw_overused
        watertight = bool(mesh.is_watertight)

    if raw_warning or bad != 0 or not watertight or roundtrip_error:
        return {
            "file": path.name,
            "bad_edges": int(bad),
            "boundary_edges": int(boundary),
            "overused_edges": int(overused),
            "watertight": watertight,
            "raw_bad_edges": int(raw_bad),
            "roundtrip_error": roundtrip_error,
        }
    return None


def _save_final_preview_png(path: Path, final_group_map, group_defs):
    rgba, _ = render_final_map_rgba(final_group_map, group_defs)
    Image.fromarray(rgba, mode="RGBA").save(path)


def generate_logo_stls(
    image_path: Path,
    out_dir: Path,
    project_name: str,
    final_group_map: np.ndarray,
    group_defs: list[dict],
    manual_width_mm: float = 70.0,
    manual_height_mm: float | None = None,
    keep_aspect: bool = True,
    height_mm: float = 0.8,
    cut_depth_mm: float = 0.8,
    clearance_mm: float = 0.0,
    center_output: bool = True,
    **_legacy_ignored,
):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    project = safe_filename_part(project_name)

    height_mm = float(height_mm)
    cut_depth_mm = float(cut_depth_mm)
    clearance_mm = float(clearance_mm)
    if not np.isfinite(height_mm) or height_mm <= 0:
        raise ValueError("Part Height must be greater than 0 mm.")
    if not np.isfinite(cut_depth_mm) or cut_depth_mm <= 0:
        raise ValueError("Cutout Depth must be greater than 0 mm.")
    if not np.isfinite(clearance_mm) or clearance_mm < 0:
        raise ValueError("Clearance must be 0 mm or greater.")

    geometry = build_exact_geometry(
        final_group_map=final_group_map,
        group_defs=group_defs,
        width_mm=manual_width_mm,
        height_mm=manual_height_mm,
        keep_aspect=keep_aspect,
        center_output=center_output,
    )
    geoms = geometry["geoms"]
    total = geometry["total"]

    manifold_warnings = []
    files = []
    colors_meta = []
    total_area = float(total.area)

    ordered_defs = [item for item in group_defs if item["name"] in geoms]
    for idx, item in enumerate(ordered_defs, start=1):
        name = item["name"]
        geom = geoms[name]
        fname = f"{project}_color_{idx:02d}_{english_output_group_name(name)}.stl"
        warning = export_repaired_stl(extrude_geometry(geom, height_mm), out_dir / fname)
        if warning:
            manifold_warnings.append(warning)
        files.append(fname)
        colors_meta.append(
            {
                "file": fname,
                "group": name,
                "area_mm2": round(float(geom.area), 3),
                "percent": round(100.0 * float(geom.area) / total_area, 1)
                if total_area
                else 0.0,
            }
        )

    total_name = f"{project}_complete_cutout.stl"
    warning = export_repaired_stl(
        extrude_geometry(total, cut_depth_mm), out_dir / total_name
    )
    if warning:
        manifold_warnings.append(warning)
    files.append(total_name)

    clearance_tag = f"{clearance_mm:.2f}".replace(".", "_")
    negative_name = f"{project}_negative_clearance_{clearance_tag}mm.stl"
    negative = total.buffer(clearance_mm, join_style=2)
    if not negative.is_valid:
        negative = negative.buffer(0)
    warning = export_repaired_stl(
        extrude_geometry(negative, cut_depth_mm), out_dir / negative_name
    )
    if warning:
        manifold_warnings.append(warning)
    files.append(negative_name)

    preview_name = f"{project}_preview.png"
    _save_final_preview_png(out_dir / preview_name, final_group_map, group_defs)

    # Keep an input copy for traceability, but it plays no role in geometry.
    try:
        src = Path(image_path)
        if src.exists() and src.is_file():
            shutil.copy2(src, out_dir / f"{project}_original{src.suffix.lower() or '.png'}")
    except Exception:
        pass

    meta = {
        "project": project,
        "final_logo_width_mm": round(float(geometry["final_width_mm"]), 3),
        "final_logo_height_mm": round(float(geometry["final_height_mm"]), 3),
        "files": files,
        "colors": colors_meta,
        "total_file": total_name,
        "negative_file": negative_name,
        "preview": preview_name,
        "manifold_warnings": manifold_warnings,
        "settings": {
            "geometry_mode": "exact_raster_cells",
            "source_width_px": geometry["source_width_px"],
            "source_height_px": geometry["source_height_px"],
            "requested_logo_width_mm": float(manual_width_mm),
            "requested_logo_height_mm": (
                float(manual_height_mm) if manual_height_mm is not None else None
            ),
            "lock_aspect_ratio": bool(keep_aspect),
            "clearance_mm": clearance_mm,
            "height_mm": height_mm,
            "cut_depth_mm": cut_depth_mm,
            "partition_missing_area_mm2": round(geometry["missing_area_mm2"], 10),
            "partition_overlap_area_mm2": round(geometry["overlap_area_mm2"], 10),
            "colors_frozen_after_calculate": True,
        },
    }
    (out_dir / f"{project}_info.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return meta
