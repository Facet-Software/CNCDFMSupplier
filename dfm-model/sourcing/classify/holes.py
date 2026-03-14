# sourcing/classify/holes.py
# Classifies hole profiles as through or blind, then determines specific
# hole type (through, blind_flat, blind_with_tip, through_counterbore,
# through_countersink, blind_countersink).

import logging

from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.gp import gp_Vec, gp_Pnt
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.TopAbs import TopAbs_IN, TopAbs_ON

from sourcing.utils.geometry import probe_apex_burial, find_shared_circle_radius

logger = logging.getLogger(__name__)


def classify_through_blind(shape, hole_profiles):
    """
    Classify each hole profile as through or blind by probing just beyond
    both ends of the hole along its axis.

    Sets on each profile:
      is_through         : bool
      local_thickness_mm : float — wall thickness below blind holes (mm)
      has_tip            : bool  — True if a buried cone apex was found

    Uses binary search along the axis to measure the actual wall thickness
    below blind holes (more accurate than the bounding-box projection fallback).
    """
    logger.debug("Classifying through vs blind...")

    bnd = Bnd_Box()
    brepbndlib.Add(shape, bnd, True)
    xmin, ymin, zmin, xmax, ymax, zmax = bnd.Get()
    max_dim_model = max(xmax - xmin, ymax - ymin, zmax - zmin)

    tol      = 1e-6
    epsilon  = 1e-5
    far_dist = 2.0 * max_dim_model + 1.0

    classifier = BRepClass3d_SolidClassifier(shape)

    corners = [
        gp_Pnt(xmin, ymin, zmin), gp_Pnt(xmin, ymin, zmax),
        gp_Pnt(xmin, ymax, zmin), gp_Pnt(xmin, ymax, zmax),
        gp_Pnt(xmax, ymin, zmin), gp_Pnt(xmax, ymin, zmax),
        gp_Pnt(xmax, ymax, zmin), gp_Pnt(xmax, ymax, zmax),
    ]

    for profile in hole_profiles:
        v_min = profile['v_min_overall']
        v_max = profile['v_max_overall']
        gpa   = profile['get_point_along_axis']

        vec_axis = profile['dir_vec']
        dots     = [vec_axis.Dot(gp_Vec(c.XYZ())) for c in corners]
        projected_thickness_model = max(dots) - min(dots)

        classifier.Perform(gpa(v_min - epsilon), tol)
        closed_min = classifier.State() in (TopAbs_IN, TopAbs_ON)

        classifier.Perform(gpa(v_max + epsilon), tol)
        closed_max = classifier.State() in (TopAbs_IN, TopAbs_ON)

        is_through            = True
        local_thickness_model = projected_thickness_model
        is_bbox_fallback      = True
        closed_end            = None
        profile["has_tip"]    = False

        if closed_min and closed_max:
            logger.debug(f"  Profile {profile['face_idxs']}: both ends closed — blind")
            is_through = False
            closed_end = 'min'
        elif closed_min:
            is_through = False
            closed_end = 'min'
        elif closed_max:
            is_through = False
            closed_end = 'max'

        # Check for buried drill tip (blind_with_tip)
        if is_through:
            cone_secs = [s for s in profile['sections'] if s['type'] == 'cone']
            for cone_sec in cone_secs:
                buried = probe_apex_burial(cone_sec, classifier, epsilon)
                if buried:
                    logger.debug(
                        f"  Profile {profile['face_idxs']}: "
                        f"apex buried — overriding to blind_with_tip"
                    )
                    is_through            = False
                    is_bbox_fallback      = False
                    profile["has_tip"]    = True
                    local_thickness_model = profile['total_height_mm'] / 1000.0

                    # Determine closed_end so approach_direction is set correctly.
                    # The small epsilon probe at v_min/v_max fails near the cone
                    # apex due to numerical instability — use a large probe offset
                    # (2% of bounding box) to get a reliable result.
                    # Rule: the closed end is the end where the probe is INSIDE
                    # the solid. The open end (entry) is outside.
                    probe_dist = max_dim_model * 0.02
                    classifier.Perform(gpa(v_min - probe_dist), tol)
                    if classifier.State() in (TopAbs_IN, TopAbs_ON):
                        closed_end = 'min'
                        logger.debug(
                            f"  Profile {profile['face_idxs']}: "
                            f"apex at v_min end → closed_end='min', approach=+axis"
                        )
                    else:
                        closed_end = 'max'
                        logger.debug(
                            f"  Profile {profile['face_idxs']}: "
                            f"apex at v_max end → closed_end='max', approach=-axis"
                        )
                    break

        # Binary-search wall thickness below blind holes
        if not is_through and not profile["has_tip"]:
            is_bbox_fallback = False
            if closed_end == 'min':
                high, low = v_min - epsilon, v_min - far_dist
                for _ in range(60):
                    mid = (low + high) / 2
                    classifier.Perform(gpa(mid), tol)
                    if classifier.State() in (TopAbs_IN, TopAbs_ON):
                        high = mid
                    else:
                        low = mid
                local_thickness_model = v_max - (low + high) / 2
            elif closed_end == 'max':
                low, high = v_max + epsilon, v_max + far_dist
                for _ in range(60):
                    mid = (low + high) / 2
                    classifier.Perform(gpa(mid), tol)
                    if classifier.State() in (TopAbs_IN, TopAbs_ON):
                        low = mid
                    else:
                        high = mid
                local_thickness_model = (low + high) / 2 - v_min

        local_thickness_mm = round(local_thickness_model * 1000, 1)
        total_height_mm    = profile['total_height_mm']
        tolerance_mm       = max(0.1 * local_thickness_mm, 0.5)

        # If measured thickness ≈ drill depth, the hole is actually through
        if not is_through and not profile["has_tip"]:
            if abs(total_height_mm - local_thickness_mm) <= tolerance_mm:
                is_through       = True
                is_bbox_fallback = False

        profile["is_through"]         = is_through
        profile["local_thickness_mm"] = local_thickness_mm
        profile["closed_end"]         = closed_end  # 'min', 'max', or None (through)

        # approach_direction: unit vector pointing FROM the exterior INTO the hole.
        # For blind holes: determined by which end is open.
        # For simple through holes: axis_direction (either end valid — abs(dot) in set-cover).
        # For counterbore/countersink through holes: directional — must approach from
        # the counterbore/countersink entry side (the larger-diameter end). Marked with
        # is_directional_through=True so set-cover uses signed dot, not abs.
        ad = profile["axis_direction"]
        profile["is_directional_through"] = False

        if is_through:
            cylinder_secs = [s for s in profile['sections'] if s['type'] == 'cylinder']
            cone_secs     = [s for s in profile['sections'] if s['type'] == 'cone']
            radii = sorted(set(round(s['radius_mm'], 2) for s in cylinder_secs))
            has_counterbore = len(radii) > 1
            has_countersink = bool(cone_secs)

            if has_counterbore or has_countersink:
                if has_counterbore:
                    max_r  = max(radii)
                    entry  = next(s for s in cylinder_secs
                                  if round(s['radius_mm'], 2) == max_r)
                else:
                    entry = cone_secs[0]
                v_entry_mid = (entry['v_min'] + entry['v_max']) / 2
                v_hole_mid  = (profile['v_min_overall'] + profile['v_max_overall']) / 2
                if v_entry_mid < v_hole_mid:
                    profile["approach_direction"]      = (-ad[0], -ad[1], -ad[2])
                else:
                    profile["approach_direction"]      = ad
                profile["is_directional_through"] = True
                logger.debug(
                    f"  Profile {profile['face_idxs']}: counterbore/countersink — "
                    f"directional approach={profile['approach_direction']}"
                )
            else:
                profile["approach_direction"] = ad
        elif closed_end == 'max':
            profile["approach_direction"] = (-ad[0], -ad[1], -ad[2])
        else:
            profile["approach_direction"] = ad   # closed_end == 'min' or None

        status = "through" if is_through else "blind"
        if is_through and is_bbox_fallback:
            logger.debug(
                f"  Profile {profile['face_idxs']}: "
                f"depth={total_height_mm:.1f} mm (exits both faces) → {status}"
            )
        else:
            logger.debug(
                f"  Profile {profile['face_idxs']}: "
                f"depth={total_height_mm:.1f} mm, "
                f"local thickness={local_thickness_mm:.1f} mm → {status}"
            )

    through_count = sum(1 for p in hole_profiles if p["is_through"])
    blind_count   = len(hole_profiles) - through_count
    logger.info(f"Summary: {through_count} through holes, {blind_count} blind holes detected")


def classify_hole_type(profile, shape):
    """
    Return the specific hole type string for a profile that has already
    been through classify_through_blind().

    Types:
      through              — simple through hole
      through_counterbore  — through hole with counterbore (two cylinders)
      through_countersink  — through hole with countersink cone
      blind_flat           — blind hole, flat bottom
      blind_with_tip       — blind hole, drill-tip bottom (buried apex)
      blind_countersink    — blind hole with countersink cone
    """
    has_cone      = any(s['type'] == 'cone' for s in profile['sections'])
    cylinder_secs = [s for s in profile['sections'] if s['type'] == 'cylinder']
    cone_secs     = [s for s in profile['sections'] if s['type'] == 'cone']

    if profile['is_through']:
        if len(cylinder_secs) > 1:
            radii = sorted(set(round(s['radius_mm'], 2) for s in cylinder_secs))
            if len(radii) > 1:
                return "through_counterbore"
        if has_cone:
            return "through_countersink"
        return "through"

    if not has_cone:
        return "blind_flat"

    if profile.get('has_tip'):
        return "blind_with_tip"

    if cylinder_secs:
        junction_r = find_shared_circle_radius(
            cone_secs[0]['face_idx'], cylinder_secs[0]['face_idx'], shape
        )
        if junction_r is not None:
            if abs(junction_r - cylinder_secs[0]['radius']) < 1e-4:
                return "blind_with_tip"
            else:
                return "blind_countersink"

    return "blind_countersink"