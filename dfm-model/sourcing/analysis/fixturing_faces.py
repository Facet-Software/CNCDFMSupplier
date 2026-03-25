# sourcing/analysis/fixturing_faces.py
# Fixture face analysis — identifies viable clamping and datum surfaces
# for each fixturing in the setup plan.
#
# For each fixturing (approach direction), determines:
#   1. REST FACES — candidate datum surfaces opposite to the approach
#      direction. The part sits on these. Scored by area, feature
#      interference, and planarity.
#   2. CLAMPING PAIRS — opposing planar faces perpendicular to the
#      approach direction that a vise can grip. Scored by height,
#      parallelism, and feature interference.
#   3. STABILITY — whether the rest face footprint contains the
#      projected center of gravity of the part.
#   4. WORKHOLDING CLASSIFICATION — vise, toe-clamp, soft-jaw, or
#      custom fixture based on available surfaces.
#
# Output integrates into the pipeline alongside tool_access and
# feature_summary — one dict per fixturing.

import math
import logging

from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp import GProp_GProps
from OCC.Core.gp import gp_Vec

from sourcing.config import (
    FIXTURE_REST_FACE_DOT_MIN,
    FIXTURE_CLAMP_FACE_PERP_MAX,
    FIXTURE_CLAMP_PAIR_ANTIPARALLEL,
    FIXTURE_REST_MIN_AREA_MM2,
    FIXTURE_CLAMP_MIN_AREA_MM2,
    FIXTURE_CLAMP_MIN_HEIGHT_MM,
    FIXTURE_STABILITY_COG_MARGIN_MM,
    FIXTURE_REST_FEATURE_PENALTY,
    FIXTURE_CLAMP_FEATURE_PENALTY,
    FIXTURE_FEATURE_COVERAGE_THRESHOLD,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def analyze_fixturing_faces(shape, setup_analysis, planar_faces,
                            hole_profiles, fillets=None,
                            face_list=None, edge_to_faces=None):
    """
    Identify candidate clamping and datum surfaces for each fixturing.

    Parameters
    ----------
    shape          : TopoDS_Shape
    setup_analysis : dict from analyze_setups()
    planar_faces   : list from get_planar_faces()
    hole_profiles  : list from detect_cylindrical_features() + classify
    fillets        : list from detect_cylindrical_features()
    face_list      : list[TopoDS_Face] from build_face_adjacency()
    edge_to_faces  : dict from build_face_adjacency()

    Returns
    -------
    list of per-fixturing dicts:
        fixturing_idx       : int
        approach_axis       : str | None
        approach_vector     : tuple(3)
        rest_faces          : list of candidate dicts, scored best-first
        clamp_pairs         : list of opposing-pair dicts, scored best-first
        workholding_class   : str — 'vise' | 'toe_clamp' | 'soft_jaw' | 'custom'
        stability           : dict — cog_inside_footprint, margin_mm, etc.
        warnings            : list[str] — human-readable fixture concerns
    """
    if not setup_analysis or not setup_analysis.get('fixturings'):
        return []

    planar_by_idx  = {pf['face_idx']: pf for pf in planar_faces}
    feature_faces  = _build_feature_face_set(hole_profiles, fillets or [],
                                              edge_to_faces=edge_to_faces)
    part_cog       = _part_center_of_gravity(shape)

    results = []
    for fix in setup_analysis['fixturings']:
        fix_idx   = fix['fixturing_idx']
        approach  = fix['approach_vector']
        ap        = _normalise(approach)
        neg_ap    = (-ap[0], -ap[1], -ap[2])

        # All faces assigned to this fixturing
        assigned_face_idxs = {
            feat['feature_idx']
            for feat in fix.get('features', [])
            if feat['feature_type'] == 'face'
        }

        # --- REST FACES (opposite to approach) ---
        rest_candidates = _find_rest_faces(
            planar_by_idx, neg_ap, feature_faces, assigned_face_idxs,
        )

        # --- CLAMPING PAIRS (perpendicular to approach) ---
        clamp_pairs = _find_clamp_pairs(
            planar_faces, ap, feature_faces,
        )

        # --- STABILITY CHECK ---
        best_rest = rest_candidates[0] if rest_candidates else None
        stability = _check_stability(
            best_rest, part_cog, ap, planar_by_idx,
        )

        # --- WORKHOLDING CLASSIFICATION ---
        workholding, warnings = _classify_workholding(
            rest_candidates, clamp_pairs, stability, fix,
        )

        result = {
            'fixturing_idx':     fix_idx,
            'approach_axis':     fix.get('approach_axis'),
            'approach_vector':   approach,
            'rest_faces':        rest_candidates,
            'clamp_pairs':       clamp_pairs,
            'workholding_class': workholding,
            'stability':         stability,
            'warnings':          warnings,
        }
        results.append(result)

        logger.info(
            f"  Fixturing {fix_idx} ({fix.get('approach_axis')}): "
            f"{len(rest_candidates)} rest candidates, "
            f"{len(clamp_pairs)} clamp pairs → {workholding}"
        )
        for w in warnings:
            logger.debug(f"    WARN: {w}")

    return results


# ---------------------------------------------------------------------------
# REST FACE DETECTION
# ---------------------------------------------------------------------------

def _find_rest_faces(planar_by_idx, neg_approach, feature_faces,
                     assigned_face_idxs):
    """
    Find and score planar faces suitable as datum/rest surfaces.

    A rest face:
      - Is planar (already filtered — we're iterating planar_by_idx)
      - Has outward normal roughly aligned with -approach (part sits on it,
        face points away from the tool)
      - Is not a chamfer
      - Has sufficient area
      - Is at or near the extreme boundary of the part in the -approach
        direction. Internal pocket floors also point -approach but are
        recessed — they're not viable datum surfaces.

    Score = area_mm2 × feature_penalty × extremity_factor. Higher is better.
    """
    # First pass: collect all qualifying faces with their position along
    # the approach axis (centroid projected onto -approach).
    raw_candidates = []

    for fi, pf in planar_by_idx.items():
        if pf.get('is_chamfer'):
            continue

        n   = pf['_normal_dir']
        dot = n.X()*neg_approach[0] + n.Y()*neg_approach[1] + n.Z()*neg_approach[2]

        if dot < FIXTURE_REST_FACE_DOT_MIN:
            continue

        area = pf['area_mm2']
        if area < FIXTURE_REST_MIN_AREA_MM2:
            continue

        # Project centroid onto -approach direction (model units).
        # Higher value = further in the -approach direction = closer to
        # the outer boundary where the part actually rests.
        c = pf['_centroid']
        depth_proj = (c.X()*neg_approach[0] + c.Y()*neg_approach[1] +
                      c.Z()*neg_approach[2])

        raw_candidates.append((fi, pf, dot, area, depth_proj))

    if not raw_candidates:
        return []

    # Find the extreme position — the face furthest in the -approach direction
    # is at the true boundary of the part (where it would rest on a table).
    max_depth = max(c[4] for c in raw_candidates)
    # Tolerance: faces within 2mm (in model units: 0.002) of the extreme are
    # considered boundary faces. Anything deeper is an internal pocket floor
    # or step and should be excluded entirely.
    DEPTH_TOL = 0.002  # 2mm in model units

    candidates = []
    for fi, pf, dot, area, depth_proj in raw_candidates:
        depth_offset_mm = (max_depth - depth_proj) * 1000  # mm from boundary

        if depth_offset_mm > 2.0:
            # Internal face — skip entirely. A pocket floor 2mm above the
            # part bottom is not a rest face.
            continue

        has_features = fi in feature_faces
        # Coverage check: only treat features as problematic when they
        # consume a significant fraction of the face area. A small through
        # hole in a large face is fine for vise seating.
        feature_coverage = 0.0
        if has_features:
            hole_area = feature_faces[fi].get("hole_area_mm2", 0.0)
            feature_coverage = hole_area / area if area > 0 else 0.0
            has_features = feature_coverage > FIXTURE_FEATURE_COVERAGE_THRESHOLD

        penalty = FIXTURE_REST_FEATURE_PENALTY if has_features else 1.0
        score   = area * penalty

        disqualifications = []
        if has_features:
            n_features = len(feature_faces.get(fi, {}).get("descriptions", []))
            disqualifications.append(
                f"{n_features} feature(s) cover {feature_coverage*100:.0f}% of face — "
                f"may require shimming or custom nest"
            )

        candidates.append({
            'face_idx':           fi,
            'area_mm2':           round(area, 1),
            'normal':             pf['normal'],
            'centroid_mm':        pf['centroid_mm'],
            'alignment_dot':      round(dot, 4),
            'has_features':       has_features,
            'score':              round(score, 1),
            'disqualifications':  disqualifications,
            'in_fixturing':       fi in assigned_face_idxs,
        })

    candidates.sort(key=lambda c: c['score'], reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# CLAMPING PAIR DETECTION
# ---------------------------------------------------------------------------

def _find_clamp_pairs(planar_faces, approach, feature_faces):
    """
    Find opposing planar face pairs perpendicular to the approach direction
    suitable for vise clamping.

    A valid pair:
      - Both faces have normals perpendicular to approach (±CLAMP_FACE_PERP_MAX)
      - Normals are antiparallel (facing each other)
      - Both faces have sufficient area
      - The perpendicular extent (height in approach direction) is sufficient
        for a jaw to grip

    Returns list of pair dicts, scored best-first.
    """
    # Collect clamping candidates
    clamp_candidates = []
    for pf in planar_faces:
        if pf.get('is_chamfer'):
            continue

        n   = pf['_normal_dir']
        dot = abs(n.X()*approach[0] + n.Y()*approach[1] + n.Z()*approach[2])

        # We want faces roughly perpendicular to approach (walls, not floors).
        # |dot| close to 0 = perpendicular, close to 1 = parallel to approach.
        if dot > FIXTURE_CLAMP_FACE_PERP_MAX:
            continue

        if pf['area_mm2'] < FIXTURE_CLAMP_MIN_AREA_MM2:
            continue

        clamp_candidates.append(pf)

    # Find antiparallel pairs
    pairs = []
    seen  = set()

    for i, fa in enumerate(clamp_candidates):
        na = fa['_normal_dir']
        for fb in clamp_candidates[i+1:]:
            nb    = fb['_normal_dir']
            dot_n = gp_Vec(na).Dot(gp_Vec(nb))

            if dot_n > FIXTURE_CLAMP_PAIR_ANTIPARALLEL:
                continue

            pair_key = frozenset((fa['face_idx'], fb['face_idx']))
            if pair_key in seen:
                continue
            seen.add(pair_key)

            # Compute jaw opening = perpendicular distance between faces
            cog_a = fa['_centroid']
            cog_b = fb['_centroid']
            vec_ab = gp_Vec(cog_a, cog_b)
            na_vec = gp_Vec(na)
            jaw_opening_mm = abs(vec_ab.Dot(na_vec)) / na_vec.Magnitude() * 1000.0

            if jaw_opening_mm < 1e-3:
                continue

            # Estimate clamping height = extent of each face along the
            # approach direction. This tells you how much jaw contact
            # height is available.
            height_a = _face_extent_along(fa, approach)
            height_b = _face_extent_along(fb, approach)
            clamp_height = min(height_a, height_b)

            # Feature coverage check — same logic as rest faces
            def _face_has_significant_features(fi, area_mm2):
                if fi not in feature_faces:
                    return False
                hole_area = feature_faces[fi].get("hole_area_mm2", 0.0)
                return (hole_area / area_mm2) > FIXTURE_FEATURE_COVERAGE_THRESHOLD if area_mm2 > 0 else False

            has_features_a = _face_has_significant_features(fa['face_idx'], fa['area_mm2'])
            has_features_b = _face_has_significant_features(fb['face_idx'], fb['area_mm2'])
            has_any_features = has_features_a or has_features_b
            penalty = FIXTURE_CLAMP_FEATURE_PENALTY if has_any_features else 1.0

            # Score: jaw_opening is the critical differentiator between
            # external boundary pairs (full part width, e.g. 100mm) and
            # internal pocket wall pairs (pocket width, e.g. 20mm).
            # Weighting it squares the advantage of external pairs.
            combined_area = fa['area_mm2'] + fb['area_mm2']
            score = jaw_opening_mm * combined_area * clamp_height * penalty

            notes = []
            if clamp_height < FIXTURE_CLAMP_MIN_HEIGHT_MM:
                notes.append(
                    f"clamp height {clamp_height:.1f} mm — may need soft jaws"
                )
            if has_any_features:
                notes.append("feature(s) on clamping face — soft jaws recommended")

            pairs.append({
                'face_idx_a':       fa['face_idx'],
                'face_idx_b':       fb['face_idx'],
                'jaw_opening_mm':   round(jaw_opening_mm, 1),
                'clamp_height_mm':  round(clamp_height, 1),
                'combined_area_mm2': round(combined_area, 1),
                'has_features':     has_any_features,
                'score':            round(score, 1),
                'notes':            notes,
                'centroid_a_mm':    fa['centroid_mm'],
                'centroid_b_mm':    fb['centroid_mm'],
                'normal_a':         fa['normal'],
                'normal_b':         fb['normal'],
            })

    pairs.sort(key=lambda p: p['score'], reverse=True)
    return pairs


# ---------------------------------------------------------------------------
# STABILITY CHECK
# ---------------------------------------------------------------------------

def _check_stability(rest_face, part_cog, approach, planar_by_idx):
    """
    Check whether the part's center of gravity, projected onto the rest
    face plane along the approach direction, falls within the rest face's
    bounding footprint.

    A part whose CoG projects outside the rest face will tend to tip —
    requiring toe clamps or a different datum face.
    """
    if rest_face is None or part_cog is None:
        return {
            'cog_inside_footprint': None,
            'cog_mm':               None,
            'reason':               'no rest face or unable to compute CoG',
        }

    pf = planar_by_idx.get(rest_face['face_idx'])
    if pf is None:
        return {
            'cog_inside_footprint': None,
            'cog_mm':               None,
            'reason':               'rest face not in planar index',
        }

    # Project CoG onto the rest face plane along the approach direction.
    # The rest face plane normal ≈ -approach. Project CoG onto the plane
    # by removing the component along the face normal.
    n  = pf['_normal_dir']
    c  = pf['_centroid']  # a point on the rest face plane

    cog_vec = gp_Vec(c, part_cog)
    # Perpendicular distance from CoG to rest plane
    perp_dist = cog_vec.Dot(gp_Vec(n)) / gp_Vec(n).Magnitude()

    # Project CoG onto rest face plane
    proj_x = part_cog.X() - n.X() * perp_dist
    proj_y = part_cog.Y() - n.Y() * perp_dist
    proj_z = part_cog.Z() - n.Z() * perp_dist

    # Check if the projected point is within the face's bounding box in
    # the face's local coordinate system. This is an approximation — a
    # convex hull check would be more accurate but the bbox is sufficient
    # for V1 and catches the important cases (cantilevered parts).
    face_centroid = c
    offset_x = (proj_x - face_centroid.X()) * 1000  # mm
    offset_y = (proj_y - face_centroid.Y()) * 1000
    offset_z = (proj_z - face_centroid.Z()) * 1000
    offset_dist = math.sqrt(offset_x**2 + offset_y**2 + offset_z**2)

    # Simple heuristic: compare offset distance to a characteristic length
    # derived from face area (sqrt(area) as a proxy for face "radius").
    face_radius = math.sqrt(rest_face['area_mm2']) / 2.0
    margin = face_radius - offset_dist + FIXTURE_STABILITY_COG_MARGIN_MM
    inside = margin >= 0

    cog_mm = (
        round(part_cog.X() * 1000, 1),
        round(part_cog.Y() * 1000, 1),
        round(part_cog.Z() * 1000, 1),
    )

    return {
        'cog_inside_footprint': inside,
        'cog_mm':               cog_mm,
        'offset_from_center_mm': round(offset_dist, 1),
        'face_characteristic_radius_mm': round(face_radius, 1),
        'margin_mm':            round(margin, 1),
    }


# ---------------------------------------------------------------------------
# WORKHOLDING CLASSIFICATION
# ---------------------------------------------------------------------------

def _classify_workholding(rest_candidates, clamp_pairs, stability, fix):
    """
    Classify the practical workholding approach for this fixturing.

    Categories (in order of preference / cost):
      vise              — clean rest face + clean opposing clamp pair
      toe_clamp         — clean rest face but no good clamp pair
      soft_jaw          — rest or clamp faces have features requiring custom jaws
      custom            — no viable rest face, or CoG instability, or complex geometry

    Returns (classification_str, list_of_warning_strings).
    """
    warnings = []

    has_clean_rest = (
        rest_candidates
        and not rest_candidates[0]['has_features']
        and rest_candidates[0]['area_mm2'] >= FIXTURE_REST_MIN_AREA_MM2
    )

    has_any_rest = bool(rest_candidates)

    has_clean_clamp = (
        clamp_pairs
        and not clamp_pairs[0]['has_features']
        and clamp_pairs[0]['clamp_height_mm'] >= FIXTURE_CLAMP_MIN_HEIGHT_MM
    )

    has_any_clamp = bool(clamp_pairs)

    cog_stable = stability.get('cog_inside_footprint', True)
    if cog_stable is None:
        cog_stable = True  # assume stable if we couldn't compute

    # Generate warnings
    if not has_any_rest:
        warnings.append(
            "No viable datum/rest face found opposite to approach — "
            "part may need a custom fixture or nest"
        )
    elif rest_candidates[0]['has_features']:
        n_feat = len(rest_candidates[0].get('disqualifications', []))
        warnings.append(
            f"Best rest face (face {rest_candidates[0]['face_idx']}) has "
            f"features — part won't seat flat without shimming"
        )

    if not has_any_clamp:
        warnings.append(
            "No opposing face pair found for vise clamping — "
            "toe clamps or custom fixture required"
        )
    elif clamp_pairs[0]['clamp_height_mm'] < FIXTURE_CLAMP_MIN_HEIGHT_MM:
        warnings.append(
            f"Best clamp pair height is only "
            f"{clamp_pairs[0]['clamp_height_mm']:.1f} mm — "
            f"insufficient for standard jaws, soft jaws needed"
        )

    if not cog_stable and has_any_rest:
        warnings.append(
            f"Part center of gravity projects outside rest face footprint "
            f"(offset {stability.get('offset_from_center_mm', '?')} mm "
            f"vs face radius {stability.get('face_characteristic_radius_mm', '?')} mm) "
            f"— part will tend to tip, toe clamps or fixture required"
        )

    # Classify
    if not has_any_rest:
        return 'custom', warnings
    if not cog_stable:
        return 'custom', warnings
    if has_clean_rest and has_clean_clamp:
        return 'vise', warnings
    if has_clean_rest and not has_any_clamp:
        return 'toe_clamp', warnings
    if has_any_clamp and (rest_candidates[0]['has_features'] or
                          clamp_pairs[0]['has_features']):
        return 'soft_jaw', warnings
    if has_clean_rest:
        return 'toe_clamp', warnings

    return 'soft_jaw', warnings


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _build_feature_face_set(hole_profiles, fillets, edge_to_faces=None):
    """
    Build a dict of face_idx → {descriptions, hole_area_mm2} for faces
    that have machined features on or through them.

    Tracks the total cross-sectional area of holes passing through each
    face so callers can compute a coverage ratio. A Ø8mm hole through a
    5000mm² face is 1% coverage — negligible for workholding. The same
    hole through a 100mm² face is 50% — real problem.
    """
    import math

    feature_faces = {}  # face_idx → {"descriptions": [...], "hole_area_mm2": float}

    # Collect all hole wall face indices
    hole_face_idxs = set()
    # Map hole wall face_idx → hole profile (for area computation)
    hole_wall_to_profile = {}
    for i, hp in enumerate(hole_profiles):
        for fi in hp.get('face_idxs', []):
            hole_face_idxs.add(fi)
            hole_wall_to_profile[fi] = hp
            entry = feature_faces.setdefault(fi, {"descriptions": [], "hole_area_mm2": 0.0})
            entry["descriptions"].append(
                f"hole {i+1} ({hp.get('hole_type', 'unknown')})"
            )

    # Adjacency pass: find planar faces that share an edge with a hole
    # wall face. Track which holes pass through each planar face.
    if edge_to_faces:
        face_to_holes = {}  # planar face_idx → set of hole profile ids
        for edge_faces in edge_to_faces.values():
            # Find hole wall faces on this edge
            hole_faces_on_edge = [fi for fi in edge_faces if fi in hole_face_idxs]
            if not hole_faces_on_edge:
                continue
            # Find non-hole faces on this edge (the planar faces the hole passes through)
            for fi in edge_faces:
                if fi not in hole_face_idxs:
                    for hfi in hole_faces_on_edge:
                        hp = hole_wall_to_profile.get(hfi)
                        if hp is not None:
                            face_to_holes.setdefault(fi, set()).add(id(hp))

        # For each planar face with adjacent holes, compute total hole area
        for fi, hole_ids in face_to_holes.items():
            total_hole_area = 0.0
            for hp in hole_profiles:
                if id(hp) in hole_ids:
                    r = hp.get('rep_radius_mm', 0)
                    total_hole_area += math.pi * r * r

            entry = feature_faces.setdefault(fi, {"descriptions": [], "hole_area_mm2": 0.0})
            if not any('adjacent' in desc for desc in entry["descriptions"]):
                entry["descriptions"].append("adjacent to hole — hole entry/exit on this face")
            entry["hole_area_mm2"] += total_hole_area

    # Fillets
    for flt in fillets:
        fi = flt.get('face_idx')
        if fi is not None:
            entry = feature_faces.setdefault(fi, {"descriptions": [], "hole_area_mm2": 0.0})
            entry["descriptions"].append(
                f"fillet (r={flt.get('radius_mm', 0):.1f} mm)"
            )

    return feature_faces


def _part_center_of_gravity(shape):
    """
    Return the part's volumetric center of gravity as a gp_Pnt (model units).
    Returns None if volume computation fails.
    """
    try:
        props = GProp_GProps()
        brepgprop.VolumeProperties(shape, props)
        return props.CentreOfMass()
    except Exception:
        return None


def _face_extent_along(pf, direction):
    """
    Estimate the extent (mm) of a planar face along a given direction.

    Projects the face's in-plane dimensions onto the direction vector.
    Uses sqrt(area) as an isotropic extent estimate, scaled by how much
    of the direction lies in the face plane. Approximate but directionally
    correct — a proper V2 would iterate face edge vertices.
    """
    n = pf['normal']  # outward normal tuple

    # Component of `direction` that lies in the face plane
    dot_n = direction[0]*n[0] + direction[1]*n[1] + direction[2]*n[2]
    in_plane = (
        direction[0] - dot_n * n[0],
        direction[1] - dot_n * n[1],
        direction[2] - dot_n * n[2],
    )
    ip_mag = math.sqrt(in_plane[0]**2 + in_plane[1]**2 + in_plane[2]**2)

    if ip_mag < 1e-6:
        # Direction is perpendicular to the face plane — no extent
        return 0.0

    # Use sqrt(area) as isotropic extent, then scale by the in-plane
    # projection magnitude. This is approximate but directionally correct.
    isotropic_extent = math.sqrt(pf['area_mm2'])
    return isotropic_extent * ip_mag


def _normalise(v):
    """Normalise a 3-tuple to unit length."""
    m = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    if m < 1e-10:
        return (0.0, 0.0, 1.0)
    return (v[0]/m, v[1]/m, v[2]/m)