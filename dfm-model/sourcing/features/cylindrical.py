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
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_OUT, TopAbs_IN, TopAbs_ON
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

                # --- Secondary check: bore wall vs external boss surface ---
                # The axis midpoint probe can return OUT for a boss exterior when
                # a central bore runs through the axis (the midpoint is in the
                # bore void, not in solid material).  Distinguish by probing
                # points just OUTSIDE the cylinder surface (radially outward):
                #   bore wall   → outward probes enter solid  (IN)
                #   boss surface → outward probes enter void  (OUT)
                # Probe at multiple angles around circumference for robustness —
                # a single probe can miss if the hole is near the part edge.
                axis_mid = gpa((v_min + v_max) / 2)
                radial = gp_Vec(axis_mid, loc)     # axis → surface point
                rad_mag = radial.Magnitude()
                if rad_mag > 1e-12:
                    radial.Normalize()
                    # Build a perpendicular vector for multi-angle probing
                    perp = radial.Crossed(dir_vec)
                    perp_mag = perp.Magnitude()
                    probe_offset = 5e-4  # 0.5mm in model units
                    any_in_solid = False
                    if perp_mag > 1e-12:
                        perp.Normalize()
                        # Probe at 4 angles: 0°, 90°, 180°, 270°
                        for angle_deg in [0, 90, 180, 270]:
                            a = math.radians(angle_deg)
                            probe_dir_x = radial.X() * math.cos(a) + perp.X() * math.sin(a)
                            probe_dir_y = radial.Y() * math.cos(a) + perp.Y() * math.sin(a)
                            probe_dir_z = radial.Z() * math.cos(a) + perp.Z() * math.sin(a)
                            # Point on the surface at this angle
                            surf_pt = gp_Pnt(
                                axis_mid.X() + probe_dir_x * rad_mag,
                                axis_mid.Y() + probe_dir_y * rad_mag,
                                axis_mid.Z() + probe_dir_z * rad_mag,
                            )
                            probe_pt = gp_Pnt(
                                surf_pt.X() + probe_dir_x * probe_offset,
                                surf_pt.Y() + probe_dir_y * probe_offset,
                                surf_pt.Z() + probe_dir_z * probe_offset,
                            )
                            classifier.Perform(probe_pt, tol)
                            if classifier.State() == TopAbs_IN:
                                any_in_solid = True
                                break
                    else:
                        # Fallback: single probe at the UV midpoint direction
                        probe_outward = gp_Pnt(
                            loc.X() + radial.X() * probe_offset,
                            loc.Y() + radial.Y() * probe_offset,
                            loc.Z() + radial.Z() * probe_offset,
                        )
                        classifier.Perform(probe_outward, tol)
                        any_in_solid = (classifier.State() == TopAbs_IN)

                    if not any_in_solid:
                        logger.debug(
                            f"  Skipping full cylinder face {face_idx}: "
                            f"r={round(radius*1000,2)} mm — axis midpoint in void "
                            f"but no radial outward probe found solid "
                            f"(external boss surface with central bore)"
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


# ---------------------------------------------------------------------------
# PARTIAL HOLE DETECTION
# ---------------------------------------------------------------------------

def _perp_basis(axis_dir):
    """
    Return two unit vectors (u, v) perpendicular to axis_dir.
    Uses cross product with a non-parallel reference to build a stable basis.
    """
    ax, ay, az = axis_dir
    # Pick a reference vector not parallel to the axis
    if abs(ax) <= abs(ay) and abs(ax) <= abs(az):
        ref = (1.0, 0.0, 0.0)
    elif abs(ay) <= abs(az):
        ref = (0.0, 1.0, 0.0)
    else:
        ref = (0.0, 0.0, 1.0)

    # u = axis × ref, then normalise
    ux = ay * ref[2] - az * ref[1]
    uy = az * ref[0] - ax * ref[2]
    uz = ax * ref[1] - ay * ref[0]
    m  = math.sqrt(ux*ux + uy*uy + uz*uz)
    ux, uy, uz = ux/m, uy/m, uz/m

    # v = axis × u
    vx = ay * uz - az * uy
    vy = az * ux - ax * uz
    vz = ax * uy - ay * ux

    return (ux, uy, uz), (vx, vy, vz)


def detect_partial_holes(shape, hole_profiles, n_angles=12, n_depths=3):
    """
    Detect holes that have been partially intersected by another feature —
    a pocket, slot, or adjacent hole that breaks through the bore wall,
    leaving the hole with missing wall material on one side.

    Method
    ------
    For each hole, sample points at (radius + ε) at n_angles evenly spaced
    around the full circumference and n_depths evenly spaced along the bore
    depth (excluding the top 15% and bottom 15% to avoid end-cap geometry).

    A complete bore has solid at all those points — the probe returns IN.
    If any sample returns OUT (void), the wall is broken at that angle/depth.

    severity
    --------
    critical  — > 25% of circumference exposed (significant breakthrough)
    warning   — 1 sample exposed (minor clipping — may be intentional slot)

    Returns
    -------
    List of dicts:
        hole_idx          : int   — index into hole_profiles
        face_idxs         : list  — face indices of the hole
        rep_radius_mm     : float
        depth_mm          : float — total bore depth
        exposed_pct       : float — percentage of circumference samples that are void
        exposed_angles_deg: list  — approximate angles (0–360°) where void was found
        severity          : 'warning' | 'critical'
    """
    if not hole_profiles:
        return []

    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.BRepBndLib import brepbndlib

    bnd = Bnd_Box()
    brepbndlib.Add(shape, bnd, True)
    bnd.Enlarge(0.0)   # no gap
    xmin, ymin, zmin, xmax, ymax, zmax = bnd.Get()

    def _inside_bbox(px, py, pz, tol=1e-6):
        """Return True if point is within part bounding box (with tiny tolerance)."""
        return (xmin - tol <= px <= xmax + tol and
                ymin - tol <= py <= ymax + tol and
                zmin - tol <= pz <= zmax + tol)

    classifier = BRepClass3d_SolidClassifier(shape)
    tol        = 1e-6
    results    = []

    for hi, hp in enumerate(hole_profiles):
        r_mm     = hp.get('rep_radius_mm') or 0.0
        if r_mm < 0.1:
            continue   # degenerate

        r_model  = r_mm / 1000.0

        v_min    = hp['v_min_overall']
        v_max    = hp['v_max_overall']
        v_span   = v_max - v_min

        if v_span < 1e-9:
            continue

        # Build a list of (v_min, v_max, radius_model) for each cylinder section
        # so we probe at the correct radius at each depth. This prevents false
        # positives on counterbore/countersink holes where the wider shoulder
        # would make a probe at rep_radius (smallest bore) land in void.
        cyl_sections = [
            (s['v_min'], s['v_max'], s['radius'])
            for s in hp.get('sections', [])
            if s.get('type') == 'cylinder'
        ]

        def _radius_at(v):
            """Return the cylinder radius (model units) at depth v.
            Falls back to rep_radius_mm if no section covers v."""
            for sv_min, sv_max, sr in cyl_sections:
                if sv_min - 1e-6 <= v <= sv_max + 1e-6:
                    return sr
            return r_model

        gpa      = hp['get_point_along_axis']
        ax, ay, az = hp['axis_direction']
        u_basis, v_basis = _perp_basis((ax, ay, az))

        # Sample depths — skip outermost 15% at each end to avoid end-cap noise
        margin  = 0.15 * v_span
        depths  = [v_min + margin + (v_span - 2*margin) * i / max(n_depths - 1, 1)
                   for i in range(n_depths)]

        void_samples   = []
        total_samples  = 0

        for v in depths:
            # Use section-specific radius at this depth
            r_at_v       = _radius_at(v)
            probe_offset = max(r_at_v * 0.20, 0.0008)   # ≥ 0.8mm in model units
            probe_r      = r_at_v + probe_offset

            axis_pt = gpa(v)
            cx, cy, cz = axis_pt.X(), axis_pt.Y(), axis_pt.Z()

            for k in range(n_angles):
                angle_rad = 2.0 * math.pi * k / n_angles
                cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)

                # Point at (radius + ε) from bore axis
                px = cx + probe_r * (cos_a * u_basis[0] + sin_a * v_basis[0])
                py = cy + probe_r * (cos_a * u_basis[1] + sin_a * v_basis[1])
                pz = cz + probe_r * (cos_a * u_basis[2] + sin_a * v_basis[2])

                classifier.Perform(gp_Pnt(px, py, pz), tol)
                total_samples += 1

                if classifier.State() == TopAbs_OUT:
                    # Only count as a breach if the probe point is inside the
                    # part bounding box — points outside the bbox are just
                    # "outside the part" from a nearby outer face, not a
                    # feature intersecting the bore.
                    if _inside_bbox(px, py, pz):
                        void_samples.append(round(math.degrees(angle_rad), 1))

        if not void_samples:
            continue

        # Deduplicate angles (same angle at multiple depths → report once)
        unique_angles = sorted(set(void_samples))
        exposed_pct   = round(len(void_samples) / total_samples * 100, 1)
        severity      = 'critical' if exposed_pct > 25.0 else 'warning'

        depth_mm = round(
            (hp.get('local_thickness_mm') or hp.get('total_height_mm') or 0.0),
            1
        )

        results.append({
            'hole_idx':           hi,
            'face_idxs':          hp.get('face_idxs', []),
            'rep_radius_mm':      round(r_mm, 3),
            'depth_mm':           depth_mm,
            'exposed_pct':        exposed_pct,
            'exposed_angles_deg': unique_angles,
            'severity':           severity,
        })

        logger.debug(
            f"  Partial hole {hi} (faces {hp.get('face_idxs')}): "
            f"r={r_mm:.2f}mm, {exposed_pct:.0f}% exposed, "
            f"angles={unique_angles}, severity={severity}"
        )

    logger.info(f"Partial hole detection: {len(results)} partial holes found")
    return results