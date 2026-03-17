# sourcing/analysis/feature_summary.py
# Per-fixturing feature counts for supplier quoting.
#
# Aggregates geometry analysis results into a structured count summary
# per fixturing — the data a supplier needs to estimate setups, tool
# changes, and programming time without reading the raw CAD file.
#
# Returns a list of per-fixturing dicts that mirror the fixturing list
# from setup_analysis, enriched with feature counts.

import logging

logger = logging.getLogger(__name__)


def compute_feature_counts(setup_analysis, hole_profiles, fillets,
                           planar_faces, tool_access=None):
    """
    Compute per-fixturing feature counts for quoting.

    For each fixturing, produces:

        fixturing_idx       : int
        approach_axis       : str | None  (e.g. '+Z')
        setup_type          : str         (e.g. '3-axis-standard')
        min_tool_dia_mm     : float | None

        planar_faces        : int   — total planar faces assigned
        floor_faces         : int   — faces parallel to approach (pocket/step floors)
        wall_faces          : int   — faces perpendicular to approach

        holes               : {
            total           : int
            by_type         : dict[str, int]   e.g. {'through': 3, 'blind_flat': 1}
            min_dia_mm      : float | None
            max_dia_mm      : float | None
            max_depth_mm    : float | None
        }

        fillets             : {
            total           : int
            concave         : int
            convex          : int
            min_radius_mm   : float | None
            max_radius_mm   : float | None
        }

        estimated_tool_changes : int   — lower-bound estimate:
                                         1 per hole type group +
                                         1 if concave fillets need finishing pass +
                                         1 for face milling (if planar faces > 0)

    Parameters
    ----------
    setup_analysis  : dict returned by analyze_setups()
    hole_profiles   : list returned by classify_through_blind()
    fillets         : list returned by detect_cylindrical_features()
    planar_faces    : list returned by get_planar_faces()
    tool_access     : list returned by analyze_tool_access() — optional,
                      used to populate min_tool_dia_mm per fixturing
    """
    if not setup_analysis:
        return []

    # Build lookup maps
    planar_by_idx = {pf['face_idx']: pf for pf in planar_faces}

    tool_by_fix = {}
    if tool_access:
        tool_by_fix = {ta['fixturing_idx']: ta for ta in tool_access}

    results = []

    for fix in setup_analysis['fixturings']:
        fix_idx    = fix['fixturing_idx']
        approach   = fix['approach_vector']
        axis_label = fix.get('approach_axis')
        setup_type = fix.get('setup_type', '3-axis-standard')
        ap_mag     = (approach[0]**2 + approach[1]**2 + approach[2]**2) ** 0.5

        ta          = tool_by_fix.get(fix_idx)
        min_tool_dia = ta['min_tool_dia_mm'] if ta else None

        # Unit approach vector for floor/wall classification
        if ap_mag > 1e-9:
            ax, ay, az = approach[0]/ap_mag, approach[1]/ap_mag, approach[2]/ap_mag
        else:
            ax, ay, az = 0.0, 0.0, 1.0

        # Split assigned features into holes vs faces
        assigned_hole_idxs = set()
        assigned_face_idxs = set()
        for feat in fix.get('features', []):
            if feat['feature_type'] == 'hole':
                assigned_hole_idxs.add(feat['feature_idx'])
            elif feat['feature_type'] == 'face':
                assigned_face_idxs.add(feat['feature_idx'])

        # --- Planar face counts ---
        n_planar = len(assigned_face_idxs)
        n_floor  = 0
        n_wall   = 0
        FLOOR_TOL = 0.95

        for fi in assigned_face_idxs:
            pf = planar_by_idx.get(fi)
            if pf is None:
                continue
            n  = pf['_normal_dir']
            dot = abs(n.X()*ax + n.Y()*ay + n.Z()*az)
            if dot >= FLOOR_TOL:
                n_floor += 1
            else:
                n_wall += 1

        # --- Hole counts ---
        # assigned_hole_idxs contains hole PROFILE indices (not face indices).
        # Look up directly in hole_profiles list.
        seen_holes = set()   # deduplicate by profile index
        hole_types   = {}
        hole_dias    = []
        hole_depths  = []

        for hi in assigned_hole_idxs:
            if hi in seen_holes or hi < 0 or hi >= len(hole_profiles):
                continue
            seen_holes.add(hi)
            hp = hole_profiles[hi]

            htype = hp.get('hole_type', 'unknown')
            hole_types[htype] = hole_types.get(htype, 0) + 1

            # Smallest cylinder radius = nominal drill dia
            cyl_secs = [s for s in hp.get('sections', [])
                        if s['type'] == 'cylinder']
            if cyl_secs:
                min_r = min(s['radius_mm'] for s in cyl_secs)
                hole_dias.append(min_r * 2.0)

            depth = hp.get('total_height_mm')
            if depth is not None:
                hole_depths.append(depth)

        # Distinct diameters rounded to 2dp — each unique diameter is a
        # separate tool in the drill cycle
        distinct_dias = sorted({round(d, 2) for d in hole_dias})

        hole_summary = {
            'total':           sum(hole_types.values()),
            'by_type':         hole_types,
            'min_dia_mm':      round(min(hole_dias), 3)  if hole_dias   else None,
            'max_dia_mm':      round(max(hole_dias), 3)  if hole_dias   else None,
            'max_depth_mm':    round(max(hole_depths), 2) if hole_depths else None,
            'distinct_dias_mm': distinct_dias,
            'distinct_dia_count': len(distinct_dias),
        }

        # --- Fillet counts ---
        fix_fillets = [f for f in fillets if f.get('fixturing_idx') == fix_idx]
        concave = [f for f in fix_fillets if f.get('type') == 'concave']
        convex  = [f for f in fix_fillets if f.get('type') == 'convex']
        fillet_radii = [f['radius_mm'] for f in fix_fillets]

        fillet_summary = {
            'total':          len(fix_fillets),
            'concave':        len(concave),
            'convex':         len(convex),
            'min_radius_mm':  round(min(fillet_radii), 3) if fillet_radii else None,
            'max_radius_mm':  round(max(fillet_radii), 3) if fillet_radii else None,
        }

        # --- Estimated tool changes (lower bound) ---
        # Face milling / roughing: 1 tool
        # Each distinct hole diameter: 1 drill (better proxy than hole type)
        # Concave fillets: 1 finishing pass
        tool_change_estimate = 0
        if n_planar > 0:
            tool_change_estimate += 1
        tool_change_estimate += len(distinct_dias)
        if len(concave) > 0:
            tool_change_estimate += 1

        summary = {
            'fixturing_idx':         fix_idx,
            'approach_axis':         axis_label,
            'setup_type':            setup_type,
            'min_tool_dia_mm':       min_tool_dia,
            'planar_faces':          n_planar,
            'floor_faces':           n_floor,
            'wall_faces':            n_wall,
            'holes':                 hole_summary,
            'fillets':               fillet_summary,
            'estimated_tool_changes': tool_change_estimate,
        }
        results.append(summary)

        logger.debug(
            f"  Feature counts fixturing {fix_idx} ({axis_label}): "
            f"{n_planar} planar ({n_floor} floor, {n_wall} wall), "
            f"{hole_summary['total']} holes "
            f"({len(distinct_dias)} distinct dia: {distinct_dias}), "
            f"{len(fix_fillets)} fillets, "
            f"~{tool_change_estimate} tool changes"
        )

    return results