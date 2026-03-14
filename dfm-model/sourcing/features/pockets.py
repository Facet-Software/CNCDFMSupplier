# sourcing/features/pockets.py
# Deep pocket and slot detection.
#
# A pocket is a cavity open on one face (the floor) with walls rising from
# it. It is "deep" when depth / (2 × min_radial_clearance) exceeds the
# warning or critical threshold.
#
# Pocket types
# ------------
# blind  — fully enclosed on all sides, open only at the entry face.
#           Depth ratio is computed and flagged.
# slot   — open on one or more sides (tool can enter laterally from a
#           different setup). Depth ratio is not flagged; open directions
#           are recorded for future setup count analysis.
#
# Algorithm
# ---------
# 1. For every planar face, treat it as a candidate pocket floor.
# 2. BFS across shared edges to collect wall faces and fillet faces.
# 3. Sample the floor face on a UV grid; verify each sample lies on the
#    face material using BRepClass_FaceClassifier (handles non-simply-
#    connected floors such as annular rings, floors with bosses, etc.).
# 4. From each valid sample origin, shoot a radial ray fan perpendicular
#    to the floor normal. Record hit distances and hit/miss per direction.
# 5. Aggregate across all origins:
#      min_radial_clearance_mm — min hit distance across all origins/directions
#      open directions         — directions where majority of origins miss
#    Cluster contiguous open directions into gaps; each gap is one open side.
# 6. Classify blind vs slot from open side count.
# 7. For blind pockets: measure depth from rim edges, compute ratio,
#    assign severity.

import math
import logging
from collections import defaultdict, deque

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_IN, TopAbs_ON, TopAbs_OUT
from OCC.Core.TopoDS import topods
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCC.Core import GeomAbs
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Lin, gp_Pnt2d
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.BRepClass import BRepClass_FaceClassifier
from OCC.Core.IntCurvesFace import IntCurvesFace_ShapeIntersector

from sourcing.config import (
    POCKET_WARNING_RATIO,
    POCKET_CRITICAL_RATIO,
    POCKET_MIN_DEPTH_MM,
    POCKET_RADIAL_RAY_COUNT,
    POCKET_FLOOR_SAMPLE_GRID,
    POCKET_OPEN_DIR_MISS_THRESHOLD,
    POCKET_MIN_GAP_RAYS,
    POCKET_MAX_SEARCH_RADIUS_MM,
    POCKET_WALL_PERP_TOL,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def detect_pockets(shape, planar_faces, face_list=None, edge_to_faces=None, face_to_edges=None):
    """
    Detect deep pockets and slots in the part.

    Parameters
    ----------
    shape         : TopoDS_Shape — the loaded solid
    planar_faces  : list of dicts — from get_planar_faces()
    face_list     : list[TopoDS_Face] — from build_face_adjacency(); built
    edge_to_faces : dict[hash → list[int]] — from build_face_adjacency()
    face_to_edges : dict[int → list[(hash, edge)]] — from build_face_adjacency()

    Adjacency maps are optional — if not provided they are built internally.
    Pass them from the pipeline to avoid traversing the shape twice.

    Returns
    -------
    List of pocket dicts sorted by severity then ratio (worst first).
    Each dict:

        pocket_type             : "blind" or "slot"
        floor_face_idx          : int
        wall_face_idxs          : list[int]
        fillet_face_idxs        : list[int]
        min_radial_clearance_mm : float — largest tool radius that fits
        floor_area_mm2          : float
        access_direction        : tuple — floor outward normal (tool entry)
        open_directions         : list[(angle_deg, (nx,ny,nz))] per open gap;
                                  empty for blind pockets
        # blind pockets only:
        depth_mm                : float
        ratio                   : float — depth / (2 × min_radial_clearance)
        severity                : "warning" | "critical"
    """
    if face_list is None or edge_to_faces is None or face_to_edges is None:
        face_list, edge_to_faces, face_to_edges = _build_adjacency(shape)

    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(shape, 1e-6)

    classifier = BRepClass3d_SolidClassifier(shape)

    pockets = []

    for pf in planar_faces:
        floor_idx      = pf['face_idx']
        floor_normal   = pf['normal']        # (nx, ny, nz) outward, unit
        floor_centroid = pf['_centroid']     # gp_Pnt — used for depth measurement
        floor_face     = face_list[floor_idx]

        nx, ny, nz       = floor_normal
        floor_normal_vec = gp_Vec(nx, ny, nz)
        floor_normal_dir = gp_Dir(nx, ny, nz)

        # --- 1. Collect walls and fillets via BFS -------------------------
        wall_idxs, fillet_idxs = _collect_pocket_faces(
            floor_idx, floor_normal_vec, face_list,
            edge_to_faces, face_to_edges, classifier,
        )

        if not wall_idxs:
            logger.debug(f"  Face {floor_idx}: no walls found — skipping")
            continue

        # --- 2. Radial ray fan from UV-sampled floor origins --------------
        min_clearance_mm, open_side_count, open_directions = _measure_radial_clearance(
            floor_face, floor_normal_dir, floor_normal_vec, intersector,
        )

        if min_clearance_mm is None or min_clearance_mm < 1e-3:
            logger.debug(f"  Face {floor_idx}: no radial hits — not an enclosed face")
            continue

        # --- 3. Classify blind vs slot ------------------------------------
        pocket_type = "blind" if open_side_count == 0 else "slot"

        record = {
            "pocket_type":             pocket_type,
            "floor_face_idx":          floor_idx,
            "wall_face_idxs":          sorted(wall_idxs),
            "fillet_face_idxs":        sorted(fillet_idxs),
            "min_radial_clearance_mm": round(min_clearance_mm, 3),
            "floor_area_mm2":          pf['area_mm2'],
            "access_direction":        floor_normal,
            "open_directions":         open_directions,
        }

        # --- 4. Blind pockets only: depth + ratio -------------------------
        if pocket_type == "blind":
            depth_mm = _measure_depth(
                floor_centroid, floor_normal,
                wall_idxs, fillet_idxs, floor_idx,
                face_to_edges, edge_to_faces,
            )

            if depth_mm < POCKET_MIN_DEPTH_MM:
                logger.debug(
                    f"  Face {floor_idx}: depth={depth_mm:.1f} mm "
                    f"< {POCKET_MIN_DEPTH_MM} mm — skipping"
                )
                continue

            ratio    = depth_mm / (2.0 * min_clearance_mm)
            severity = "critical" if ratio >= POCKET_CRITICAL_RATIO else "warning"

            if ratio < POCKET_WARNING_RATIO:
                logger.debug(
                    f"  Face {floor_idx}: ratio={ratio:.2f} < {POCKET_WARNING_RATIO} "
                    f"— not deep enough to flag"
                )
                continue

            record["depth_mm"] = round(depth_mm, 1)
            record["ratio"]    = round(ratio, 2)
            record["severity"] = severity

            logger.debug(
                f"  Blind pocket (floor {floor_idx}): depth={depth_mm:.1f} mm, "
                f"clearance={min_clearance_mm:.2f} mm, ratio={ratio:.2f}, "
                f"severity={severity}"
            )
        else:
            logger.debug(
                f"  Slot (floor {floor_idx}): open_sides={open_side_count}, "
                f"clearance={min_clearance_mm:.2f} mm, "
                f"open_dirs={[d[0] for d in open_directions]}"
            )

        pockets.append(record)

    def sort_key(p):
        if p['pocket_type'] == 'blind':
            return (0 if p.get('severity') == 'critical' else 1, -p.get('ratio', 0))
        return (2, 0)

    pockets.sort(key=sort_key)
    logger.info(
        f"Total pockets found: {len(pockets)} "
        f"({sum(1 for p in pockets if p['pocket_type'] == 'blind')} blind, "
        f"{sum(1 for p in pockets if p['pocket_type'] == 'slot')} slot)"
    )
    return pockets


# ---------------------------------------------------------------------------
# ADJACENCY BUILD
# ---------------------------------------------------------------------------

def _build_adjacency(shape):
    """
    Traverse all faces once and build:
      face_list       : list[TopoDS_Face]
      edge_to_faces   : dict[edge_idx → list[int]]
      face_to_edges   : dict[face_idx → list[(edge_idx, edge)]]

    Edges normalized to FORWARD orientation before map operations —
    see build_face_adjacency in geometry.py for explanation.
    """
    from OCC.Core.TopTools import TopTools_IndexedMapOfShape
    from OCC.Core.TopAbs   import TopAbs_FORWARD

    def _fwd(edge):
        return edge.Oriented(TopAbs_FORWARD)

    edge_map = TopTools_IndexedMapOfShape()
    exp_all  = TopExp_Explorer(shape, TopAbs_EDGE)
    while exp_all.More():
        edge_map.Add(_fwd(topods.Edge(exp_all.Current())))
        exp_all.Next()

    face_list     = []
    face_to_edges = {}
    edge_to_faces = defaultdict(list)

    exp      = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx = 0

    while exp.More():
        face = topods.Face(exp.Current())
        face_list.append(face)

        seen_idxs  = set()
        face_edges = []

        edge_exp = TopExp_Explorer(face, TopAbs_EDGE)
        while edge_exp.More():
            edge  = topods.Edge(edge_exp.Current())
            e_idx = edge_map.FindIndex(_fwd(edge))
            if e_idx > 0 and e_idx not in seen_idxs:
                seen_idxs.add(e_idx)
                face_edges.append((e_idx, edge))
                edge_to_faces[e_idx].append(face_idx)
            edge_exp.Next()

        face_to_edges[face_idx] = face_edges
        face_idx += 1
        exp.Next()

    return face_list, edge_to_faces, face_to_edges


# ---------------------------------------------------------------------------
# BFS — COLLECT POCKET FACES
# ---------------------------------------------------------------------------

def _collect_pocket_faces(floor_idx, floor_normal_vec, face_list,
                           edge_to_faces, face_to_edges, classifier):
    """
    BFS from the floor face across shared edges.

    Planar faces with normals roughly perpendicular to the floor normal are
    walls. Partial cylinders are fillets (floor-wall junction radii). Full
    cylinders are probed: material-facing (boss walls, curved pocket walls)
    are collected as walls; void-facing (hole walls) terminate BFS.

    Returns (wall_idxs, fillet_idxs) as sets of face indices.
    """
    wall_idxs   = set()
    fillet_idxs = set()
    visited     = {floor_idx}
    queue       = deque([floor_idx])
    tol         = 1e-6

    while queue:
        current_idx = queue.popleft()

        for edge_hash, _ in face_to_edges.get(current_idx, []):
            for neighbor_idx in edge_to_faces.get(edge_hash, []):
                if neighbor_idx in visited:
                    continue
                visited.add(neighbor_idx)

                neighbor_face = face_list[neighbor_idx]
                adaptor       = BRepAdaptor_Surface(neighbor_face)
                surf_type     = adaptor.GetType()

                if surf_type == GeomAbs.GeomAbs_Plane:
                    nrm = adaptor.Plane().Axis().Direction()
                    dot = abs(
                        gp_Vec(nrm.X(), nrm.Y(), nrm.Z()).Dot(floor_normal_vec)
                    )
                    if dot < POCKET_WALL_PERP_TOL:
                        wall_idxs.add(neighbor_idx)
                        queue.append(neighbor_idx)

                elif surf_type == GeomAbs.GeomAbs_Cylinder:
                    u_span = abs(
                        adaptor.LastUParameter() - adaptor.FirstUParameter()
                    )
                    if abs(u_span - 2 * math.pi) > 1e-4:
                        # Partial cylinder → floor-wall junction radius
                        fillet_idxs.add(neighbor_idx)
                        queue.append(neighbor_idx)
                    else:
                        # Full cylinder: probe axis to distinguish hole vs curved wall
                        cyl      = adaptor.Cylinder()
                        axis_loc = cyl.Axis().Location()
                        axis_vec = gp_Vec(cyl.Axis().Direction())
                        v_mid    = (
                            adaptor.FirstVParameter() + adaptor.LastVParameter()
                        ) / 2
                        axis_pt  = axis_loc.Translated(axis_vec.Multiplied(v_mid))
                        classifier.Perform(axis_pt, tol)
                        state = classifier.State()
                        if state != TopAbs_OUT:
                            # Axis in material → curved pocket wall or boss wall
                            wall_idxs.add(neighbor_idx)
                            queue.append(neighbor_idx)
                        # else: void-facing hole wall — stop BFS here

    return wall_idxs, fillet_idxs


# ---------------------------------------------------------------------------
# RADIAL RAY FAN — UV-SAMPLED ORIGINS
# ---------------------------------------------------------------------------

def _measure_radial_clearance(floor_face, floor_normal_dir, floor_normal_vec,
                               intersector):
    """
    Measure radial clearance and detect open sides.

    Samples the floor face on a UV grid, verifies each point is on the face
    material via BRepClass_FaceClassifier, then fires a radial ray fan from
    each valid sample. Works correctly for non-simply-connected floors
    (annular, floors with bosses, L-shaped, etc.) because origins are
    distributed across actual face material rather than the geometric
    centroid, which may lie off the face entirely.

    Returns
    -------
    (min_clearance_mm, open_side_count, open_directions)

    min_clearance_mm : float | None
        Minimum hit distance (mm) across all (sample, direction) pairs.
        For an annular pocket this equals the gap half-width — the largest
        tool radius that can physically enter the pocket.

    open_side_count : int
        Number of distinct angular gaps where the majority of origins miss.
        0 = blind, 1+ = slot.

    open_directions : list of (angle_deg, (nx, ny, nz))
        Midpoint angle and unit direction vector for each open gap.
        Empty for blind pockets.
    """
    n_rays   = POCKET_RADIAL_RAY_COUNT
    n_grid   = POCKET_FLOOR_SAMPLE_GRID
    max_dist = POCKET_MAX_SEARCH_RADIUS_MM / 1000.0   # mm → model units

    # Build in-plane basis vectors
    fn  = gp_Vec(floor_normal_dir)
    ref = gp_Vec(1.0, 0.0, 0.0)
    if abs(fn.Dot(ref)) > 0.9:
        ref = gp_Vec(0.0, 1.0, 0.0)
    u_dir = fn.Crossed(ref); u_dir.Normalize()
    v_dir = fn.Crossed(u_dir); v_dir.Normalize()

    # Precompute ray directions
    ray_dirs = []
    for i in range(n_rays):
        angle   = 2.0 * math.pi * i / n_rays
        ray_vec = gp_Vec(
            u_dir.X() * math.cos(angle) + v_dir.X() * math.sin(angle),
            u_dir.Y() * math.cos(angle) + v_dir.Y() * math.sin(angle),
            u_dir.Z() * math.cos(angle) + v_dir.Z() * math.sin(angle),
        )
        ray_dirs.append(gp_Dir(ray_vec))

    # Sample floor face on UV grid
    adaptor = BRepAdaptor_Surface(floor_face)
    u_min   = adaptor.FirstUParameter()
    u_max   = adaptor.LastUParameter()
    v_min_p = adaptor.FirstVParameter()
    v_max_p = adaptor.LastVParameter()

    face_classifier = BRepClass_FaceClassifier()
    epsilon         = 1e-3

    valid_origins = []
    for i in range(n_grid):
        u = u_min + (u_max - u_min) * (i + 0.5) / n_grid
        for j in range(n_grid):
            v = v_min_p + (v_max_p - v_min_p) * (j + 0.5) / n_grid

            face_classifier.Perform(floor_face, gp_Pnt2d(u, v), 1e-6)
            state = face_classifier.State()
            if state not in (TopAbs_IN, TopAbs_ON):
                continue

            pt = adaptor.Value(u, v)
            valid_origins.append(gp_Pnt(
                pt.X() + floor_normal_vec.X() * epsilon,
                pt.Y() + floor_normal_vec.Y() * epsilon,
                pt.Z() + floor_normal_vec.Z() * epsilon,
            ))

    if not valid_origins:
        logger.debug("  No valid UV samples on floor face")
        return None, 0, []

    logger.debug(f"  UV sampling: {len(valid_origins)}/{n_grid**2} valid origins")

    # Fire ray fan from each valid origin
    # hit_counts[i] = number of origins with a hit in direction i
    # min_dist[i]   = minimum hit distance (mm) in direction i across origins
    hit_counts = [0] * n_rays
    min_dist   = [None] * n_rays

    for origin in valid_origins:
        for i, ray_dir in enumerate(ray_dirs):
            line = gp_Lin(origin, ray_dir)
            intersector.Perform(line, 1e-4, max_dist)

            if not intersector.IsDone() or intersector.NbPnt() == 0:
                continue

            nearest = None
            for k in range(1, intersector.NbPnt() + 1):
                w = intersector.WParameter(k)
                if w > 1e-4:
                    if nearest is None or w < nearest:
                        nearest = w

            if nearest is not None:
                hit_counts[i] += 1
                dist_mm = nearest * 1000
                if min_dist[i] is None or dist_mm < min_dist[i]:
                    min_dist[i] = dist_mm

    # Global min clearance
    all_hits      = [d for d in min_dist if d is not None]
    min_clearance = min(all_hits) if all_hits else None

    # Detect open directions: direction i is open if hit fraction is below threshold
    n_origins   = len(valid_origins)
    is_open_dir = [
        (hit_counts[i] / n_origins) < POCKET_OPEN_DIR_MISS_THRESHOLD
        for i in range(n_rays)
    ]

    # Find contiguous runs of open directions (wrap-aware)
    doubled   = is_open_dir + is_open_dir
    in_gap    = False
    gap_start = None
    gaps      = []

    for i in range(2 * n_rays):
        if doubled[i] and not in_gap:
            in_gap    = True
            gap_start = i
        elif not doubled[i] and in_gap:
            in_gap = False
            if gap_start < n_rays:   # only record gaps starting in first window
                gap_len = i - gap_start
                if gap_len >= POCKET_MIN_GAP_RAYS:
                    gaps.append((gap_start % n_rays, gap_len))

    # Deduplicate (same gap can appear twice in the doubled list)
    seen_starts = set()
    unique_gaps = []
    for gs, gap_len in gaps:
        if gs not in seen_starts:
            seen_starts.add(gs)
            unique_gaps.append((gs, gap_len))

    open_directions = []
    for gs, gap_len in unique_gaps:
        mid_idx   = (gs + gap_len // 2) % n_rays
        mid_angle = 2.0 * math.pi * mid_idx / n_rays
        open_vec  = (
            round(u_dir.X() * math.cos(mid_angle) + v_dir.X() * math.sin(mid_angle), 4),
            round(u_dir.Y() * math.cos(mid_angle) + v_dir.Y() * math.sin(mid_angle), 4),
            round(u_dir.Z() * math.cos(mid_angle) + v_dir.Z() * math.sin(mid_angle), 4),
        )
        open_directions.append((round(math.degrees(mid_angle), 1), open_vec))
        logger.debug(
            f"  Open gap: start_ray={gs}, length={gap_len} rays "
            f"({gap_len * 360 / n_rays:.0f}°), direction={open_vec}"
        )

    return min_clearance, len(unique_gaps), open_directions


# ---------------------------------------------------------------------------
# DEPTH FROM RIM EDGES
# ---------------------------------------------------------------------------

def _measure_depth(floor_centroid, floor_normal,
                   wall_idxs, fillet_idxs, floor_idx,
                   face_to_edges, edge_to_faces):
    """
    Find pocket depth by locating rim edges — edges of wall faces that
    border a face outside the pocket set. Project sampled rim edge points
    onto the floor normal; depth is the signed distance from the floor
    centroid projection to the highest rim point. Falls back to max
    projection across all wall edges if no rim edges are found.
    """
    nx, ny, nz      = floor_normal
    pocket_face_set = wall_idxs | fillet_idxs | {floor_idx}

    ref_proj = (
        floor_centroid.X() * nx +
        floor_centroid.Y() * ny +
        floor_centroid.Z() * nz
    )

    max_proj  = ref_proj
    found_rim = False

    for wall_idx in wall_idxs:
        for edge_hash, edge in face_to_edges.get(wall_idx, []):
            outside = set(edge_to_faces.get(edge_hash, [])) - pocket_face_set
            if not outside:
                continue
            found_rim = True
            proj = _max_proj_on_edge(edge, nx, ny, nz)
            if proj is not None:
                max_proj = max(max_proj, proj)

    if not found_rim:
        logger.debug(
            f"  Pocket (floor {floor_idx}): no rim edges — "
            f"using wall-face bounding projection as fallback"
        )
        for wall_idx in wall_idxs:
            for _, edge in face_to_edges.get(wall_idx, []):
                proj = _max_proj_on_edge(edge, nx, ny, nz)
                if proj is not None:
                    max_proj = max(max_proj, proj)

    return max(0.0, (max_proj - ref_proj) * 1000)


def _max_proj_on_edge(edge, nx, ny, nz):
    """Max projection of three sample points on edge onto (nx, ny, nz)."""
    try:
        ca    = BRepAdaptor_Curve(edge)
        t_min = ca.FirstParameter()
        t_max = ca.LastParameter()
        if abs(t_max - t_min) < 1e-12:
            return None
        best = None
        for t in [t_min, (t_min + t_max) * 0.5, t_max]:
            pt   = ca.Value(t)
            proj = pt.X() * nx + pt.Y() * ny + pt.Z() * nz
            if best is None or proj > best:
                best = proj
        return best
    except Exception:
        return None