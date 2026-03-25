# sourcing/features/thin_walls.py
# Hybrid thin wall detection:
#   Method A — planar opposing-pair distance
#   Method B — concentric cylinder exact geometry
#   Method C — ray casting with Nelder-Mead UV refinement
# Plus hole proximity web detection.

import math
import logging
from collections import defaultdict

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_OUT, TopAbs_REVERSED
from OCC.Core.TopoDS import topods
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core import GeomAbs
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.IntCurvesFace import IntCurvesFace_ShapeIntersector

from sourcing.config import (
    THIN_WALL_WARNING_RATIO,
    THIN_WALL_CRITICAL_RATIO,
    THIN_WALL_MAX_THICKNESS_MM,
    THIN_WALL_SAMPLE_GRID,
    THIN_WALL_MIN_FACE_EXTENT,
    THIN_WALL_CLUSTER_DIST_MM,
    THIN_WALL_ANTIPARALLEL_TOL,
    THIN_WALL_OPPOSING_TOL,
    COAXIAL_DIST_TOL_MM,
    PARALLEL_DOT_TOL,
)
from sourcing.utils.geometry import get_face_by_index, face_local_height, ray_thickness

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINTS
# ---------------------------------------------------------------------------

def detect_thin_walls(shape, planar_faces, fillets):
    """
    Detect thin wall regions using a hybrid approach.

    Method A — planar opposing-pair distance
      For each pair of planar faces with antiparallel normals, compute
      perpendicular plane distance (thickness) and local height. If
      aspect ratio (height/thickness) exceeds threshold → thin wall.

    Method B — concentric cylinder exact geometry
      For pairs of concave partial cylinders sharing the same axis,
      thickness = |r_outer - r_inner| exactly. No ray casting needed.

    Method C — ray casting with UV refinement
      For each non-planar, concave, non-hole-wall face, sample an N×N
      UV grid and shoot inward rays. Any sample that beats the threshold
      triggers a Nelder-Mead UV search to find the local minimum thickness.

    All samples are clustered (first by shared face index, then spatially)
    into regions. Each region reports min_thickness_mm, max_aspect_ratio,
    severity, centroid, contributing faces, and detection methods used.

    Returns a list of thin wall region dicts.
    """
    thin_samples   = []
    max_dist_model = THIN_WALL_MAX_THICKNESS_MM / 1000.0   # mm → model units

    _method_a_planar_pairs(shape, planar_faces, thin_samples)
    _method_b_concentric_cylinders(fillets, thin_samples)
    _method_c_ray_cast(shape, planar_faces, thin_samples, max_dist_model)

    thin_walls = _cluster_thin_samples(thin_samples)
    logger.info(f"Total thin wall regions found: {len(thin_walls)}")
    return thin_walls


def detect_hole_proximity_walls(hole_profiles):
    """
    Detect thin webs of material between pairs of holes that are drilled
    close enough together that the remaining material is dangerously thin.

    This case is invisible to the planar pair and ray cast methods because
    hole-wall cylinders are void-facing and intentionally skipped there.

    Algorithm
    ---------
    For every pair of hole profiles (A, B):

    1. AXIS SEPARATION — perpendicular distance between the two axis lines.
       Parallel axes: center-to-center distance in the plane perpendicular
       to the shared axis. Non-parallel axes: minimum skew-line distance.

    2. WEB THICKNESS — web = axis_separation - r_A - r_B.
       Negative → holes intersect (reported as "intersecting").

    3. OVERLAP DEPTH — axial length over which both holes coexist.
       Parallel: overlap of v intervals. Non-parallel: min hole depth.

    4. ASPECT RATIO — overlap_depth / web_thickness.
       Same warning/critical thresholds as geometric thin walls.

    5. Skip coaxial pairs (counterbore + through-hole share an axis —
       intentional compound feature, not a proximity problem).

    6. Skip deeply intersecting pairs (web < -min_radius) — almost
       certainly intentional compound geometry (cross-drilled passages).

    Returns a list of dicts, one per flagged hole pair.
    """
    results      = []
    n            = len(hole_profiles)
    parallel_tol = 0.05   # dot product tolerance for parallel axis test

    for i in range(n):
        pa      = hole_profiles[i]
        loc_a   = gp_Pnt(*pa['axis_location'])
        dir_a   = gp_Dir(pa['dir_vec'])
        r_a     = (pa['rep_radius_mm'] or 0.0) / 1000.0   # mm → model units
        v_min_a = pa['v_min_overall']
        v_max_a = pa['v_max_overall']

        for j in range(i + 1, n):
            pb      = hole_profiles[j]
            loc_b   = gp_Pnt(*pb['axis_location'])
            dir_b   = gp_Dir(pb['dir_vec'])
            r_b     = (pb['rep_radius_mm'] or 0.0) / 1000.0
            v_min_b = pb['v_min_overall']
            v_max_b = pb['v_max_overall']

            dot = abs(dir_a.Dot(dir_b))   # 1.0 = parallel, 0.0 = perpendicular

            # ----------------------------------------------------------
            # PARALLEL (or near-parallel) axes
            # ----------------------------------------------------------
            if dot > (1.0 - parallel_tol):
                vec_ab     = gp_Vec(loc_a, loc_b)
                along      = vec_ab.Dot(gp_Vec(dir_a))
                perp       = vec_ab.Subtracted(gp_Vec(dir_a).Multiplied(along))
                separation = perp.Magnitude()   # model units

                # Skip coaxial holes — same axis line, different depths
                if separation * 1000 < 0.1:
                    continue

                web_model = separation - r_a - r_b
                web_mm    = web_model * 1000

                # Skip deeply intersecting pairs (almost certainly intentional)
                min_r_mm = min(r_a, r_b) * 1000
                if web_mm < -min_r_mm:
                    continue

                if web_mm > THIN_WALL_MAX_THICKNESS_MM:
                    continue

                # Overlap along axis
                pb_offset     = along
                pb_v_min_in_a = pb_offset + v_min_b
                pb_v_max_in_a = pb_offset + v_max_b

                overlap_min = max(v_min_a, pb_v_min_in_a)
                overlap_max = min(v_max_a, pb_v_max_in_a)
                overlap_mm  = max(0.0, (overlap_max - overlap_min) * 1000)

                if overlap_mm < 1e-3:
                    continue

                # Midpoint
                mid_v = (overlap_min + overlap_max) / 2
                mid_pt = pa['get_point_along_axis'](mid_v)
                if separation > 1e-9:
                    toward_b = perp.Multiplied(0.5 / separation * separation)
                else:
                    toward_b = gp_Vec(0, 0, 0)
                mid_pt_shifted = gp_Pnt(
                    mid_pt.X() + toward_b.X(),
                    mid_pt.Y() + toward_b.Y(),
                    mid_pt.Z() + toward_b.Z(),
                )

            # ----------------------------------------------------------
            # NON-PARALLEL (skew or perpendicular) axes
            # ----------------------------------------------------------
            else:
                vec_ab    = gp_Vec(loc_a, loc_b)
                cross     = gp_Vec(dir_a).Crossed(gp_Vec(dir_b))
                cross_mag = cross.Magnitude()

                if cross_mag < 1e-10:
                    continue

                # Closest point parameters on each infinite axis line
                da = gp_Vec(dir_a)
                db = gp_Vec(dir_b)
                d  = vec_ab

                denom = da.Dot(da) * db.Dot(db) - da.Dot(db) ** 2
                if abs(denom) < 1e-12:
                    continue

                t_a_inf = (d.Dot(da) * db.Dot(db) - d.Dot(db) * da.Dot(db)) / denom
                t_b_inf = (d.Dot(da) * da.Dot(db) - d.Dot(db) * da.Dot(da)) / (-denom)

                # Clamp to actual hole extents — this is the critical fix.
                # Infinite-line closest approach may lie outside the physical
                # hole; clamping ensures we measure the real minimum distance
                # between the two bounded cylindrical surfaces.
                t_a = max(v_min_a, min(v_max_a, t_a_inf))
                t_b = max(v_min_b, min(v_max_b, t_b_inf))

                pt_a = pa['get_point_along_axis'](t_a)
                pt_b = pb['get_point_along_axis'](t_b)

                seg_vec    = gp_Vec(pt_a, pt_b)
                separation = seg_vec.Magnitude()

                web_model  = separation - r_a - r_b
                web_mm     = web_model * 1000

                min_r_mm = min(r_a, r_b) * 1000
                if web_mm < -min_r_mm:
                    continue

                if web_mm > THIN_WALL_MAX_THICKNESS_MM:
                    continue

                # Overlap depth: axial length over which both holes coexist
                # near the closest-approach zone. Use the clamped depths.
                depth_a    = (v_max_a - v_min_a) * 1000
                depth_b    = (v_max_b - v_min_b) * 1000
                overlap_mm = min(depth_a, depth_b)

                mid_pt_shifted = gp_Pnt(
                    (pt_a.X() + pt_b.X()) / 2,
                    (pt_a.Y() + pt_b.Y()) / 2,
                    (pt_a.Z() + pt_b.Z()) / 2,
                )

            # ----------------------------------------------------------
            # SEVERITY and REPORTING
            # ----------------------------------------------------------
            if web_mm <= 0:
                severity     = "intersecting"
                aspect_ratio = float('inf')
            else:
                aspect_ratio = overlap_mm / web_mm if web_mm > 1e-3 else float('inf')
                if aspect_ratio == float('inf') or aspect_ratio >= THIN_WALL_CRITICAL_RATIO:
                    severity = "critical"
                elif aspect_ratio >= THIN_WALL_WARNING_RATIO:
                    severity = "warning"
                else:
                    continue

            results.append({
                "hole_pair_idxs":    [i, j],
                "web_thickness_mm":  round(max(web_mm, 0.0), 3),
                "overlap_depth_mm":  round(overlap_mm, 1),
                "aspect_ratio":      round(aspect_ratio, 2) if aspect_ratio != float('inf') else None,
                "severity":          severity,
                "axis_relationship": "parallel" if dot > (1.0 - parallel_tol) else "skew",
                "midpoint_mm": (
                    round(mid_pt_shifted.X() * 1000, 1),
                    round(mid_pt_shifted.Y() * 1000, 1),
                    round(mid_pt_shifted.Z() * 1000, 1),
                ),
            })
            logger.debug(
                f"  Hole proximity: holes [{i}, {j}], "
                f"web={web_mm:.2f} mm, overlap={overlap_mm:.1f} mm, "
                f"ratio={aspect_ratio:.1f}, severity={severity}"
            )

    logger.info(f"Total hole proximity thin walls found: {len(results)}")
    return results


# ---------------------------------------------------------------------------
# METHOD A — planar opposing pairs
# ---------------------------------------------------------------------------

def _method_a_planar_pairs(shape, planar_faces, thin_samples):
    logger.debug("Thin wall detection — planar pair pass...")

    for i, fa in enumerate(planar_faces):
        nrm_a = fa['_normal_dir']
        cog_a = fa['_centroid']

        for fb in planar_faces[i + 1:]:
            nrm_b      = fb['_normal_dir']
            dot_nrm    = nrm_a.Dot(nrm_b)
            pair_label = f"[{fa['face_idx']},{fb['face_idx']}]"

            if dot_nrm > -THIN_WALL_ANTIPARALLEL_TOL:
                logger.debug(
                    f"  Pair {pair_label}: SKIP — not antiparallel "
                    f"(dot={dot_nrm:.4f}, need <{-THIN_WALL_ANTIPARALLEL_TOL:.4f})"
                )
                continue

            cog_b      = fb['_centroid']
            vec_ab     = gp_Vec(cog_a, cog_b)
            mag        = vec_ab.Magnitude()
            if mag < 1e-9:
                logger.debug(f"  Pair {pair_label}: SKIP — centroids coincident")
                continue
            along_frac = abs(vec_ab.Dot(gp_Vec(nrm_a))) / mag
            if along_frac < THIN_WALL_OPPOSING_TOL:
                logger.debug(
                    f"  Pair {pair_label}: SKIP — not opposing "
                    f"(along_frac={along_frac:.4f}, need >{THIN_WALL_OPPOSING_TOL:.4f})"
                )
                continue

            thickness_model = abs(vec_ab.Dot(gp_Vec(nrm_a)))
            thickness_mm    = thickness_model * 1000

            if thickness_mm > THIN_WALL_MAX_THICKNESS_MM or thickness_mm < 1e-3:
                logger.debug(
                    f"  Pair {pair_label}: SKIP — thickness {thickness_mm:.3f} mm "
                    f"out of range (0.001–{THIN_WALL_MAX_THICKNESS_MM} mm)"
                )
                continue

            face_a_occ = get_face_by_index(shape, fa['face_idx'])
            face_b_occ = get_face_by_index(shape, fb['face_idx'])
            height_a   = face_local_height(face_a_occ) if face_a_occ else None
            height_b   = face_local_height(face_b_occ) if face_b_occ else None

            if height_a is None and height_b is None:
                logger.debug(f"  Pair {pair_label}: SKIP — could not compute height")
                continue
            valid_heights = [h for h in [height_a, height_b] if h is not None]
            # Use the SMALLER face's extent — the thin region is bounded by
            # the overlap area, which cannot exceed the smaller face.
            # A blind hole floor (Ø8mm) opposite a large bottom face (100mm)
            # creates a thin section only 8mm wide, not 100mm.
            height_mm = min(valid_heights)

            if height_mm < 1e-3:
                logger.debug(f"  Pair {pair_label}: SKIP — height {height_mm:.4f} mm too small")
                continue

            ratio = height_mm / thickness_mm
            logger.debug(
                f"  Pair {pair_label}: t={thickness_mm:.3f} mm, h={height_mm:.3f} mm, "
                f"ratio={ratio:.2f} (warning threshold={THIN_WALL_WARNING_RATIO})"
            )
            if ratio < THIN_WALL_WARNING_RATIO:
                logger.debug(f"  Pair {pair_label}: SKIP — ratio {ratio:.2f} below threshold")
                continue

            mid_mm = (
                round((cog_a.X() + cog_b.X()) / 2 * 1000, 1),
                round((cog_a.Y() + cog_b.Y()) / 2 * 1000, 1),
                round((cog_a.Z() + cog_b.Z()) / 2 * 1000, 1),
            )
            thin_samples.append({
                "pos_mm":       mid_mm,
                "thickness_mm": round(thickness_mm, 3),
                "height_mm":    round(height_mm, 3),
                "aspect_ratio": round(ratio, 2),
                "face_idxs":    [fa['face_idx'], fb['face_idx']],
                "method":       "planar_pair",
            })
            logger.debug(
                f"  Planar thin wall: faces [{fa['face_idx']}, {fb['face_idx']}], "
                f"t={thickness_mm:.2f} mm, h={height_mm:.2f} mm, ratio={ratio:.1f}"
            )


# ---------------------------------------------------------------------------
# METHOD B — concentric cylinder pairs (exact geometry)
# ---------------------------------------------------------------------------

def _method_b_concentric_cylinders(fillets, thin_samples):
    """
    For pairs of concave partial cylinders sharing the same axis,
    thickness = |r_outer - r_inner| exactly. No sampling needed.
    """
    logger.debug("Thin wall detection — concentric cylinder pass...")

    concave_fillets = [f for f in fillets if f['type'] == 'concave']

    for i, fa in enumerate(concave_fillets):
        dir_a          = gp_Dir(*fa['axis_direction'])
        loc_a          = gp_Pnt(*fa['axis_location'])
        r_a            = fa['radius']
        va_min, va_max = fa['v_min'], fa['v_max']

        for fb in concave_fillets[i + 1:]:
            dir_b = gp_Dir(*fb['axis_direction'])
            dot   = abs(dir_a.Dot(dir_b))
            if dot < PARALLEL_DOT_TOL:
                continue

            loc_b       = gp_Pnt(*fb['axis_location'])
            vec_ab      = gp_Vec(loc_a, loc_b)
            along       = vec_ab.Dot(gp_Vec(dir_a))
            perp        = vec_ab.Subtracted(gp_Vec(dir_a).Multiplied(along))
            axis_sep_mm = perp.Magnitude() * 1000

            if axis_sep_mm > COAXIAL_DIST_TOL_MM:
                continue   # parallel but offset — not concentric

            r_b          = fb['radius']
            thickness_mm = abs(r_a - r_b) * 1000

            if thickness_mm < 1e-3 or thickness_mm > THIN_WALL_MAX_THICKNESS_MM:
                continue

            vb_min_in_a = along + fb['v_min']
            vb_max_in_a = along + fb['v_max']
            overlap_min = max(va_min, vb_min_in_a)
            overlap_max = min(va_max, vb_max_in_a)
            height_mm   = max(0.0, (overlap_max - overlap_min) * 1000)

            if height_mm < 1e-3:
                continue

            ratio = height_mm / thickness_mm
            if ratio < THIN_WALL_WARNING_RATIO:
                continue

            mid_v  = (overlap_min + overlap_max) / 2
            fa_loc = gp_Pnt(*fa['axis_location'])
            fa_dir = gp_Vec(*fa['axis_direction'])
            mid_pt = fa_loc.Translated(fa_dir.Multiplied(mid_v))
            mid_mm = (
                round(mid_pt.X() * 1000, 1),
                round(mid_pt.Y() * 1000, 1),
                round(mid_pt.Z() * 1000, 1),
            )

            thin_samples.append({
                "pos_mm":       mid_mm,
                "thickness_mm": round(thickness_mm, 3),
                "height_mm":    round(height_mm, 3),
                "aspect_ratio": round(ratio, 2),
                "face_idxs":    [fa['face_idx'], fb['face_idx']],
                "method":       "concentric_cylinders",
            })
            logger.debug(
                f"  Concentric cylinders: faces [{fa['face_idx']}, {fb['face_idx']}], "
                f"r_a={r_a*1000:.3f} mm, r_b={r_b*1000:.3f} mm, "
                f"t={thickness_mm:.3f} mm, h={height_mm:.2f} mm, ratio={ratio:.1f}"
            )


# ---------------------------------------------------------------------------
# METHOD C — ray casting with UV refinement
# ---------------------------------------------------------------------------

def _method_c_ray_cast(shape, planar_faces, thin_samples, max_dist_model):
    logger.debug("Thin wall detection — ray cast pass...")

    planar_face_idxs = {pf['face_idx'] for pf in planar_faces}

    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(shape, 1e-6)

    exp      = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx = 0

    while exp.More():
        face      = topods.Face(exp.Current())
        adaptor   = BRepAdaptor_Surface(face, True)
        surf_type = adaptor.GetType()

        # Skip planar faces — handled by Method A
        if face_idx in planar_face_idxs:
            face_idx += 1; exp.Next(); continue

        # Skip partial cylinders/cones that are CONVEX (outside fillets).
        # Concave partial cylinders (inside corner fillets, curved pocket walls)
        # are kept — the surface may be the thinnest point of a wall.
        #
        # Concave/convex test: evaluate outward normal at face midpoint,
        # then probe inward. TopAbs_IN → concave (material behind surface).
        # TopAbs_OUT → convex (void behind surface).
        if surf_type in (GeomAbs.GeomAbs_Cylinder, GeomAbs.GeomAbs_Cone):
            u_min_chk  = adaptor.FirstUParameter()
            u_max_chk  = adaptor.LastUParameter()
            u_span_chk = abs(u_max_chk - u_min_chk)
            if u_span_chk < 2 * math.pi - 1e-4:
                if surf_type == GeomAbs.GeomAbs_Cone:
                    logger.debug(f"  Skipping partial cone face {face_idx} (chamfer)")
                    face_idx += 1; exp.Next(); continue

                u_mid_chk  = (u_min_chk + u_max_chk) / 2
                v_mid_chk  = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
                mid_pt_chk = adaptor.Value(u_mid_chk, v_mid_chk)

                d1u     = adaptor.DN(u_mid_chk, v_mid_chk, 1, 0)
                d1v     = adaptor.DN(u_mid_chk, v_mid_chk, 0, 1)
                nrm_chk = d1u.Crossed(d1v)
                if nrm_chk.Magnitude() < 1e-10:
                    face_idx += 1; exp.Next(); continue
                nrm_chk.Normalize()

                if face.Orientation() == TopAbs_REVERSED:
                    nrm_chk.Multiply(-1.0)

                probe_eps = 1e-3
                inward_pt = gp_Pnt(
                    mid_pt_chk.X() - nrm_chk.X() * probe_eps,
                    mid_pt_chk.Y() - nrm_chk.Y() * probe_eps,
                    mid_pt_chk.Z() - nrm_chk.Z() * probe_eps,
                )
                sc_chk = BRepClass3d_SolidClassifier(shape)
                sc_chk.Perform(inward_pt, 1e-6)
                is_convex = sc_chk.State() == TopAbs_OUT

                if is_convex:
                    logger.debug(f"  Skipping convex partial cylinder face {face_idx} (outside fillet)")
                    face_idx += 1; exp.Next(); continue
                else:
                    logger.debug(f"  Concave partial cylinder face {face_idx} — ray casting")

        # Skip full hole-wall cylinders (void-facing, full revolution)
        if surf_type == GeomAbs.GeomAbs_Cylinder:
            u_min  = adaptor.FirstUParameter()
            u_max  = adaptor.LastUParameter()
            u_span = abs(u_max - u_min)
            if abs(u_span - 2 * math.pi) <= 1e-4:
                cyl      = adaptor.Cylinder()
                axis_loc = cyl.Axis().Location()
                axis_dir = gp_Vec(cyl.Axis().Direction())
                v_mid    = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
                mid_pt   = axis_loc.Translated(axis_dir.Multiplied(v_mid))
                sc       = BRepClass3d_SolidClassifier(shape)
                sc.Perform(mid_pt, 1e-6)
                if sc.State() == TopAbs_OUT:
                    logger.debug(f"  Skipping hole-wall cylinder face {face_idx}")
                    face_idx += 1; exp.Next(); continue

        # Skip faces too small to be walls
        u_min = adaptor.FirstUParameter()
        u_max = adaptor.LastUParameter()
        v_min = adaptor.FirstVParameter()
        v_max = adaptor.LastVParameter()
        u_ext = abs(u_max - u_min)
        v_ext = abs(v_max - v_min)
        if u_ext < THIN_WALL_MIN_FACE_EXTENT and v_ext < THIN_WALL_MIN_FACE_EXTENT:
            logger.debug(f"  Skipping small curved face {face_idx} (UV too small)")
            face_idx += 1; exp.Next(); continue

        flip = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0

        n     = THIN_WALL_SAMPLE_GRID
        u_pts = [u_min + (u_max - u_min) * (i + 0.5) / n for i in range(n)]
        v_pts = [v_min + (v_max - v_min) * (j + 0.5) / n for j in range(n)]

        # Estimate face height from 3D bounding box (UV extent is not reliable
        # in mm — the U parameter on a cylinder is an angle, not arc length).
        face_bnd = Bnd_Box()
        brepbndlib.Add(face, face_bnd, True)
        fx_min, fy_min, fz_min, fx_max, fy_max, fz_max = face_bnd.Get()
        height_approx_mm = max(
            (fx_max - fx_min) * 1000,
            (fy_max - fy_min) * 1000,
            (fz_max - fz_min) * 1000,
        )

        for u in u_pts:
            for v in v_pts:
                try:
                    pt      = adaptor.Value(u, v)
                    d1u     = adaptor.DN(u, v, 1, 0)
                    d1v     = adaptor.DN(u, v, 0, 1)
                    nrm_vec = d1u.Crossed(d1v)
                    if nrm_vec.Magnitude() < 1e-10:
                        continue
                    nrm_vec.Multiply(flip)
                    inward = gp_Dir(nrm_vec.Reversed())
                except Exception:
                    continue

                thickness_mm = ray_thickness(shape, pt, inward, max_dist_model, intersector)
                if thickness_mm is None:
                    continue
                if thickness_mm > THIN_WALL_MAX_THICKNESS_MM or thickness_mm < 1e-3:
                    continue

                ratio = height_approx_mm / thickness_mm
                if ratio < THIN_WALL_WARNING_RATIO:
                    continue

                # Coarse sample passes — refine to local minimum in UV space
                u_ref, v_ref, thickness_mm = _refine_min_thickness(
                    adaptor, flip, shape, intersector,
                    u, v, u_min, u_max, v_min, v_max,
                    max_dist_model, thickness_mm,
                )
                ratio  = height_approx_mm / thickness_mm
                pt     = adaptor.Value(u_ref, v_ref)
                pos_mm = (
                    round(pt.X() * 1000, 1),
                    round(pt.Y() * 1000, 1),
                    round(pt.Z() * 1000, 1),
                )
                thin_samples.append({
                    "pos_mm":       pos_mm,
                    "thickness_mm": round(thickness_mm, 3),
                    "height_mm":    round(height_approx_mm, 3),
                    "aspect_ratio": round(ratio, 2),
                    "face_idxs":    [face_idx],
                    "method":       "ray_cast",
                })
                logger.debug(
                    f"  Ray cast thin point: face {face_idx}, "
                    f"t={thickness_mm:.2f} mm, ratio={ratio:.1f}, "
                    f"pos={pos_mm}"
                )

        face_idx += 1
        exp.Next()


def _refine_min_thickness(adaptor, flip, shape, intersector,
                          u_seed, v_seed, u_min, u_max, v_min, v_max,
                          max_dist_model, thickness_seed_mm):
    """
    Refine a coarse ray-cast thin point to find the local minimum thickness
    in UV space using a Nelder-Mead simplex search (60 iterations max).

    Starts from (u_seed, v_seed). UV coordinates are clamped to face bounds.
    No-hit samples are penalised with a large value so the simplex avoids them.
    Falls back to the seed if refinement diverges or worsens.

    Returns (u_best, v_best, thickness_mm).
    """
    PENALTY  = 1e9
    MAX_ITER = 60
    UV_TOL   = 1e-5

    def clamp(val, lo, hi):
        return max(lo, min(hi, val))

    def thickness_at(u, v):
        u = clamp(u, u_min, u_max)
        v = clamp(v, v_min, v_max)
        try:
            pt      = adaptor.Value(u, v)
            d1u     = adaptor.DN(u, v, 1, 0)
            d1v     = adaptor.DN(u, v, 0, 1)
            nrm     = d1u.Crossed(d1v)
            if nrm.Magnitude() < 1e-10:
                return PENALTY
            nrm.Multiply(flip)
            inward = gp_Dir(nrm.Reversed())
        except Exception:
            return PENALTY
        t = ray_thickness(shape, pt, inward, max_dist_model, intersector)
        return t if t is not None else PENALTY

    step_u = (u_max - u_min) / 10.0
    step_v = (v_max - v_min) / 10.0

    simplex = [
        [u_seed,          v_seed         ],
        [u_seed + step_u, v_seed         ],
        [u_seed,          v_seed + step_v],
    ]
    values = [thickness_at(*p) for p in simplex]

    for _ in range(MAX_ITER):
        order   = sorted(range(3), key=lambda i: values[i])
        simplex = [simplex[i] for i in order]
        values  = [values[i]  for i in order]

        span_u = max(p[0] for p in simplex) - min(p[0] for p in simplex)
        span_v = max(p[1] for p in simplex) - min(p[1] for p in simplex)
        if span_u < UV_TOL and span_v < UV_TOL:
            break

        cx = (simplex[0][0] + simplex[1][0]) / 2
        cy = (simplex[0][1] + simplex[1][1]) / 2

        # Reflection
        ru    = cx + (cx - simplex[2][0])
        rv    = cy + (cy - simplex[2][1])
        r_val = thickness_at(ru, rv)

        if r_val < values[0]:
            # Expansion
            eu    = cx + 2 * (cx - simplex[2][0])
            ev    = cy + 2 * (cy - simplex[2][1])
            e_val = thickness_at(eu, ev)
            if e_val < r_val:
                simplex[2], values[2] = [eu, ev], e_val
            else:
                simplex[2], values[2] = [ru, rv], r_val
        elif r_val < values[1]:
            simplex[2], values[2] = [ru, rv], r_val
        else:
            # Contraction
            cu    = cx + 0.5 * (simplex[2][0] - cx)
            cv    = cy + 0.5 * (simplex[2][1] - cy)
            c_val = thickness_at(cu, cv)
            if c_val < values[2]:
                simplex[2], values[2] = [cu, cv], c_val
            else:
                # Shrink toward best
                for k in [1, 2]:
                    simplex[k][0] = simplex[0][0] + 0.5 * (simplex[k][0] - simplex[0][0])
                    simplex[k][1] = simplex[0][1] + 0.5 * (simplex[k][1] - simplex[0][1])
                    values[k]     = thickness_at(*simplex[k])

    best_u, best_v = simplex[0]
    best_t         = values[0]

    if best_t >= PENALTY or best_t > thickness_seed_mm * 1.05:
        return u_seed, v_seed, thickness_seed_mm

    return clamp(best_u, u_min, u_max), clamp(best_v, v_min, v_max), best_t


# ---------------------------------------------------------------------------
# CLUSTERING
# ---------------------------------------------------------------------------

def _cluster_thin_samples(samples):
    """
    Merge thin sample points into regions.

    Two-pass strategy:
    1. Union-find: samples sharing any face index are always merged into
       the same root group (e.g. 25 ray cast points on one concave fillet
       → 1 group regardless of spatial spread).
    2. Spatial merge: distinct-face groups whose centroids are within
       THIN_WALL_CLUSTER_DIST_MM are merged into one region.

    Each region:
      min_thickness_mm : thinnest point in the region
      max_aspect_ratio : worst aspect ratio
      severity         : "warning" or "critical"
      centroid_mm      : mean position of all cluster samples
      face_idxs        : all contributing face indices
      methods          : detection methods used
      sample_count     : total number of raw samples in region
    """
    if not samples:
        return []

    # Pass 1: union-find by shared face index
    sample_count = len(samples)
    parent = list(range(sample_count))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    face_to_samples = {}
    for idx, s in enumerate(samples):
        for fi in s['face_idxs']:
            face_to_samples.setdefault(fi, []).append(idx)

    for idxs in face_to_samples.values():
        for k in range(1, len(idxs)):
            union(idxs[0], idxs[k])

    # Build per-root groups
    root_to_members = defaultdict(list)
    for idx in range(sample_count):
        root_to_members[find(idx)].append(idx)

    groups = []
    for root, member_idxs in root_to_members.items():
        members = [samples[i] for i in member_idxs]
        cx = sum(m['pos_mm'][0] for m in members) / len(members)
        cy = sum(m['pos_mm'][1] for m in members) / len(members)
        cz = sum(m['pos_mm'][2] for m in members) / len(members)
        groups.append({'centroid': (cx, cy, cz), 'members': members})

    # Pass 2: spatial merge of groups
    tol_sq    = THIN_WALL_CLUSTER_DIST_MM ** 2
    unclaimed = list(range(len(groups)))
    regions   = []

    def dist_sq_3(a, b):
        return sum((a[k] - b[k]) ** 2 for k in range(3))

    while unclaimed:
        seed           = unclaimed.pop(0)
        cluster_groups = [seed]
        queue          = [seed]
        while queue:
            cur       = queue.pop(0)
            cen_c     = groups[cur]['centroid']
            remaining = []
            for idx in unclaimed:
                if dist_sq_3(cen_c, groups[idx]['centroid']) <= tol_sq:
                    cluster_groups.append(idx)
                    queue.append(idx)
                else:
                    remaining.append(idx)
            unclaimed = remaining

        all_members = [m for gi in cluster_groups for m in groups[gi]['members']]
        min_t       = min(m['thickness_mm'] for m in all_members)
        max_ratio   = max(m['aspect_ratio'] for m in all_members)
        face_idxs   = sorted({fi for m in all_members for fi in m['face_idxs']})
        methods     = sorted({m['method'] for m in all_members})
        cx = sum(m['pos_mm'][0] for m in all_members) / len(all_members)
        cy = sum(m['pos_mm'][1] for m in all_members) / len(all_members)
        cz = sum(m['pos_mm'][2] for m in all_members) / len(all_members)
        severity = "critical" if max_ratio >= THIN_WALL_CRITICAL_RATIO else "warning"

        regions.append({
            "min_thickness_mm": round(min_t, 3),
            "max_aspect_ratio": round(max_ratio, 2),
            "severity":         severity,
            "centroid_mm":      (round(cx, 1), round(cy, 1), round(cz, 1)),
            "face_idxs":        face_idxs,
            "methods":          methods,
            "sample_count":     len(all_members),
        })

    regions.sort(key=lambda r: (-int(r['severity'] == 'critical'), -r['max_aspect_ratio']))
    return regions