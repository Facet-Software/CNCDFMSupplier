# sourcing/features/cylindrical.py
# Detects all cylindrical and conical faces, classifies them as:
#   - hole-wall cylinders (full revolution, void-facing)
#   - fillets (partial cylinders, concave or convex)
#   - hole-forming cones (pointed drill tips, void-facing truncated cones)
#   - external conical chamfers (material-facing, standard angle)
# Then groups coaxial, contiguous sections into hole profiles.

import math
import logging

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_OUT
from OCC.Core.TopoDS import topods
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCC.Core import GeomAbs
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier

from sourcing.config import (
    CHAMFER_SEMI_ANGLES_DEG, CHAMFER_ANGLE_TOL_DEG, CHAMFER_MIN_MINOR_RADIUS_MM,
    FILLET_EDGE_ROUND_MIN_RADIUS_MM, FILLET_EDGE_ROUND_MAX_HR_RATIO,
)
from sourcing.utils.geometry import make_axis_fn, flip_section, axes_are_coaxial

logger = logging.getLogger(__name__)


def _is_chamfer_angle(semi_angle_deg):
    """Return True if semi_angle_deg matches a standard chamfer angle within tolerance."""
    return any(
        abs(semi_angle_deg - std) <= CHAMFER_ANGLE_TOL_DEG
        for std in CHAMFER_SEMI_ANGLES_DEG
    )


def detect_cylindrical_features(shape):
    """
    Scan all faces and classify:
      - Full cylinders (void-facing)                        → hole sections
      - Partial cylinders                                   → fillets (concave/convex)
      - Cones: pointed (minor_r ≈ 0)                       → hole-forming (drill tip/apex)
      - Cones: truncated, void-facing, any angle            → hole-forming
                                                              (countersink/seat — drawing classifies)
      - Cones: truncated, material-facing, standard angle   → external conical chamfer

    Returns (hole_profiles, fillets, conical_chamfers).
    """
    holes            = []
    fillets          = []
    cones            = []
    conical_chamfers = []

    exp      = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx = 0

    logger.debug("Scanning for cylindrical and conical faces...")
    tol        = 1e-6
    classifier = BRepClass3d_SolidClassifier(shape)

    while exp.More():
        face      = topods.Face(exp.Current())
        adaptor   = BRepAdaptor_Surface(face, True)
        surf_type = adaptor.GetType()

        # ---- CYLINDER ------------------------------------------------
        if surf_type == GeomAbs.GeomAbs_Cylinder:
            cylinder = adaptor.Cylinder()
            radius   = cylinder.Radius()
            u_min    = adaptor.FirstUParameter()
            u_max    = adaptor.LastUParameter()
            u_span   = abs(u_max - u_min)
            v_min    = adaptor.FirstVParameter()
            v_max    = adaptor.LastVParameter()
            if v_min > v_max:
                v_min, v_max = v_max, v_min
            height_approx = abs(v_max - v_min)

            loc      = adaptor.Value((u_min + u_max) / 2, (v_min + v_max) / 2)
            axis_dir = cylinder.Axis().Direction()
            axis_loc = cylinder.Axis().Location()
            dir_vec  = gp_Vec(axis_dir.X(), axis_dir.Y(), axis_dir.Z())
            gpa      = make_axis_fn(axis_loc, dir_vec)

            classifier.Perform(gpa((v_min + v_max) / 2), tol)
            state = classifier.State()

            if abs(u_span - 2 * math.pi) <= 1e-4:
                # Full revolution cylinder
                if state != TopAbs_OUT:
                    logger.debug(
                        f"  Skipping full cylinder face {face_idx}: {state} (boss/protrusion)"
                    )
                    face_idx += 1; exp.Next(); continue

                holes.append({
                    "face_idx":           face_idx,
                    "type":               "cylinder",
                    "radius":             radius,
                    "radius_mm":          round(radius * 1000, 3),
                    "v_min":              v_min,
                    "v_max":              v_max,
                    "height_approx":      height_approx,
                    "height_approx_mm":   round(height_approx * 1000, 1),
                    "sample_position_mm": (
                        round(loc.X() * 1000, 1),
                        round(loc.Y() * 1000, 1),
                        round(loc.Z() * 1000, 1),
                    ),
                    "axis_direction": (
                        round(axis_dir.X(), 4),
                        round(axis_dir.Y(), 4),
                        round(axis_dir.Z(), 4),
                    ),
                    "axis_location":        (axis_loc.X(), axis_loc.Y(), axis_loc.Z()),
                    "dir_vec":              dir_vec,
                    "get_point_along_axis": gpa,
                })
                logger.debug(
                    f"  Hole cylinder face {face_idx}: "
                    f"r={holes[-1]['radius_mm']:.2f} mm, "
                    f"h≈{holes[-1]['height_approx_mm']:.1f} mm"
                )
            else:
                # Partial cylinder → fillet
                if u_span < 1e-4:
                    logger.debug(f"  Skipping tiny partial cylinder face {face_idx}")
                    face_idx += 1; exp.Next(); continue

                fillet_type = "concave" if state == TopAbs_OUT else "convex"
                r_mm        = round(radius * 1000, 3)
                h_mm        = round(height_approx * 1000, 1)

                if fillet_type == "convex":
                    hr_ratio = h_mm / r_mm if r_mm > 1e-6 else float('inf')
                    fillet_subtype = (
                        "edge_round"
                        if r_mm >= FILLET_EDGE_ROUND_MIN_RADIUS_MM
                           and hr_ratio < FILLET_EDGE_ROUND_MAX_HR_RATIO
                        else "fillet"
                    )
                else:
                    fillet_subtype = "fillet"  # concave fillets are always true fillets

                fillets.append({
                    "face_idx":           face_idx,
                    "radius":             radius,
                    "radius_mm":          r_mm,
                    "height_approx_mm":   h_mm,
                    "v_min":              v_min,
                    "v_max":              v_max,
                    "u_span_deg":         round(math.degrees(u_span), 1),
                    "sample_position_mm": (
                        round(loc.X() * 1000, 1),
                        round(loc.Y() * 1000, 1),
                        round(loc.Z() * 1000, 1),
                    ),
                    "axis_direction": (
                        round(axis_dir.X(), 4),
                        round(axis_dir.Y(), 4),
                        round(axis_dir.Z(), 4),
                    ),
                    "axis_location": (axis_loc.X(), axis_loc.Y(), axis_loc.Z()),
                    "dir_vec":       dir_vec,
                    "type":          fillet_type,
                    "subtype":       fillet_subtype,
                })
                logger.debug(
                    f"  Fillet face {face_idx}: r={fillets[-1]['radius_mm']:.2f} mm, "
                    f"type={fillet_type}, subtype={fillet_subtype}"
                )

        # ---- CONE ----------------------------------------------------
        elif surf_type == GeomAbs.GeomAbs_Cone:
            cone       = adaptor.Cone()
            semi_angle = cone.SemiAngle()
            ref_radius = cone.RefRadius()
            axis_dir   = cone.Axis().Direction()
            axis_loc   = cone.Axis().Location()
            u_min      = adaptor.FirstUParameter()
            u_max      = adaptor.LastUParameter()
            u_span     = abs(u_max - u_min)

            # Read radii from bounding circle edges — more reliable than
            # parametric v range on degenerate cones.
            edge_radii = []
            edge_exp   = TopExp_Explorer(face, TopAbs_EDGE)
            while edge_exp.More():
                edge = topods.Edge(edge_exp.Current())
                ca   = BRepAdaptor_Curve(edge)
                if ca.GetType() == GeomAbs.GeomAbs_Circle:
                    r      = ca.Circle().Radius()
                    center = ca.Circle().Location()
                    v_pos  = gp_Vec(axis_loc, center).Dot(gp_Vec(axis_dir))
                    edge_radii.append((v_pos, r))
                edge_exp.Next()

            if not edge_radii:
                logger.debug(f"  Skipping cone face {face_idx}: no circular edges")
                face_idx += 1; exp.Next(); continue

            # Deduplicate and sort by v position
            unique = []
            for e in edge_radii:
                if not any(abs(e[0] - u[0]) < 1e-9 for u in unique):
                    unique.append(e)
            edge_radii = sorted(unique, key=lambda x: x[0])

            # If only one edge, synthesise the apex
            if len(edge_radii) == 1:
                tan_a  = math.tan(semi_angle)
                v_apex = (-ref_radius / tan_a) if abs(tan_a) > 1e-12 else 0.0
                edge_radii.append((v_apex, 0.0))
                edge_radii.sort(key=lambda x: x[0])

            v_bottom, r_bottom = edge_radii[0]
            v_top,    r_top    = edge_radii[-1]
            height_approx      = abs(v_top - v_bottom)

            dir_vec = gp_Vec(axis_dir.X(), axis_dir.Y(), axis_dir.Z())
            gpa     = make_axis_fn(axis_loc, dir_vec)

            classifier.Perform(gpa((v_bottom + v_top) / 2), tol)
            state = classifier.State()
            loc   = adaptor.Value((u_min + u_max) / 2, (v_bottom + v_top) / 2)

            semi_angle_deg  = round(math.degrees(semi_angle), 1)
            is_large_u      = u_span > 3 * math.pi / 2
            is_void         = state == TopAbs_OUT
            minor_radius_mm = round(min(r_bottom, r_top) * 1000, 3)
            major_radius_mm = round(max(r_bottom, r_top) * 1000, 3)
            is_pointed      = minor_radius_mm < CHAMFER_MIN_MINOR_RADIUS_MM

            if not is_large_u:
                logger.debug(
                    f"  Skipping partial cone face {face_idx}: "
                    f"u_span={math.degrees(u_span):.1f}°"
                )
                face_idx += 1; exp.Next(); continue

            cone_record = {
                "face_idx":           face_idx,
                "type":               "cone",
                "radius_at_vmin":     r_bottom,
                "radius_at_vmax":     r_top,
                "radius_start":       max(r_bottom, r_top),
                "radius_end":         min(r_bottom, r_top),
                "radius_start_mm":    major_radius_mm,
                "radius_end_mm":      minor_radius_mm,
                "semi_angle_deg":     semi_angle_deg,
                "v_min":              v_bottom,
                "v_max":              v_top,
                "height_approx":      height_approx,
                "height_approx_mm":   round(height_approx * 1000, 1),
                "sample_position_mm": (
                    round(loc.X() * 1000, 1),
                    round(loc.Y() * 1000, 1),
                    round(loc.Z() * 1000, 1),
                ),
                "axis_direction": (
                    round(axis_dir.X(), 4),
                    round(axis_dir.Y(), 4),
                    round(axis_dir.Z(), 4),
                ),
                "axis_location":        (axis_loc.X(), axis_loc.Y(), axis_loc.Z()),
                "dir_vec":              dir_vec,
                "get_point_along_axis": gpa,
            }

            if is_pointed:
                logger.debug(
                    f"  Pointed cone face {face_idx}: angle={semi_angle_deg}° "
                    f"→ hole-forming (drill tip/apex)"
                )
                cones.append(cone_record)

            elif is_void:
                logger.debug(
                    f"  Void-facing cone face {face_idx}: angle={semi_angle_deg}°, "
                    f"r_minor={minor_radius_mm:.2f} mm → hole-forming (drawing will classify)"
                )
                cones.append(cone_record)

            elif _is_chamfer_angle(semi_angle_deg):
                conical_chamfers.append({
                    "face_idx":           face_idx,
                    "subtype":            "external_edge",
                    "semi_angle_deg":     semi_angle_deg,
                    "major_radius_mm":    major_radius_mm,
                    "minor_radius_mm":    minor_radius_mm,
                    "height_approx_mm":   round(height_approx * 1000, 1),
                    "sample_position_mm": (
                        round(loc.X() * 1000, 1),
                        round(loc.Y() * 1000, 1),
                        round(loc.Z() * 1000, 1),
                    ),
                    "axis_direction": (
                        round(axis_dir.X(), 4),
                        round(axis_dir.Y(), 4),
                        round(axis_dir.Z(), 4),
                    ),
                })
                logger.debug(
                    f"  External conical chamfer face {face_idx}: "
                    f"angle={semi_angle_deg}°"
                )
            else:
                logger.debug(
                    f"  Skipping material-facing non-chamfer cone face {face_idx}: "
                    f"angle={semi_angle_deg}°"
                )

        face_idx += 1
        exp.Next()

    hole_profiles = _group_hole_sections(holes, cones)
    logger.info(f"Total hole profiles found: {len(hole_profiles)}")
    logger.info(f"Total fillets found: {len(fillets)}")
    logger.info(f"Total conical chamfers found: {len(conical_chamfers)}")
    return hole_profiles, fillets, conical_chamfers


def _group_hole_sections(holes, cones):
    """
    Group coaxial, contiguous cylinder/cone sections into unified hole profiles.

    Each profile represents one logical hole and contains all the face sections
    that make it up (e.g. counterbore cylinder + through cylinder + countersink cone).
    """
    tol_axis = 1e-3
    tol_gap  = 0.05
    groups   = []

    all_sections = holes + cones

    while all_sections:
        sec   = all_sections.pop(0)
        group = [sec]

        i = 0
        while i < len(all_sections):
            other = all_sections[i]
            if axes_are_coaxial(sec, other, tol_axis):
                dir_sec   = gp_Dir(sec['dir_vec'])
                dir_other = gp_Dir(other['dir_vec'])
                if dir_sec.IsOpposite(dir_other, tol_axis):
                    other_to_add = flip_section(other)
                else:
                    other_to_add = other

                gap = (max(sec['v_min'], other_to_add['v_min'])
                       - min(sec['v_max'], other_to_add['v_max']))
                if gap < tol_gap:
                    group.append(other_to_add)
                    all_sections.pop(i)
                    continue
            i += 1

        group.sort(key=lambda s: s['v_min'])

        cylinders = [s for s in group if s['type'] == 'cylinder']
        main_sec  = min(cylinders, key=lambda s: s['radius']) if cylinders else group[0]

        profile = {
            "sections":             group,
            "face_idxs":            [s['face_idx'] for s in group],
            "total_height_mm":      sum(s['height_approx_mm'] for s in group),
            "rep_radius_mm":        main_sec.get('radius_mm') or main_sec.get('radius_end_mm'),
            "axis_direction":       main_sec['axis_direction'],
            "axis_location":        main_sec['axis_location'],
            "dir_vec":              main_sec['dir_vec'],
            "get_point_along_axis": main_sec['get_point_along_axis'],
            "v_min_overall":        min(s['v_min'] for s in group),
            "v_max_overall":        max(s['v_max'] for s in group),
        }
        groups.append(profile)

    return groups