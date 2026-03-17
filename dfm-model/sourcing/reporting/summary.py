# sourcing/reporting/summary.py
# Human-readable log summaries for all detected features.
# Each function takes the relevant data structure and logs at INFO level.

import logging

from sourcing.classify.holes import classify_hole_type

logger = logging.getLogger(__name__)


def log_hole_summary(hole_profiles, shape):
    logger.info("--- Hole Classification Summary ---")
    for i, profile in enumerate(hole_profiles):
        hole_type = classify_hole_type(profile, shape)
        cone_secs = [s for s in profile['sections'] if s['type'] == 'cone']
        angle_str = (
            f", cone semi-angle={cone_secs[0]['semi_angle_deg']:.1f}°"
            if cone_secs else ""
        )
        logger.info(
            f"  Hole {i+1} (faces {profile['face_idxs']}): "
            f"type={hole_type}, "
            f"r={profile['rep_radius_mm']:.2f} mm, "
            f"depth={profile['total_height_mm']:.1f} mm"
            f"{angle_str}"
        )


def log_planar_face_summary(planar_faces):
    logger.info("--- Planar Face Summary ---")
    logger.info(f"  Total planar faces: {len(planar_faces)}")
    unique_normals = list({pf['normal'] for pf in planar_faces})
    logger.info(f"  Distinct normals (raw, pre-clustering): {len(unique_normals)}")
    for n in unique_normals:
        count = sum(1 for pf in planar_faces if pf['normal'] == n)
        logger.info(f"    normal={n}  count={count}")


def log_chamfer_summary(conical_chamfers):
    logger.info("--- Conical Chamfer Summary ---")
    if not conical_chamfers:
        logger.info("  No external conical chamfers detected.")
        return
    for i, ch in enumerate(conical_chamfers):
        logger.info(
            f"  Chamfer {i+1} (face {ch['face_idx']}): "
            f"angle={ch['semi_angle_deg']}°, "
            f"r_major={ch['major_radius_mm']:.2f} mm, "
            f"r_minor={ch['minor_radius_mm']:.2f} mm"
        )


def log_thin_wall_summary(thin_walls, hole_proximity_walls):
    logger.info("--- Thin Wall Summary ---")
    all_walls = thin_walls + hole_proximity_walls
    if not all_walls:
        logger.info("  No thin walls detected.")
        return
    for i, tw in enumerate(thin_walls):
        logger.info(
            f"  Region {i+1} [geometry]: "
            f"severity={tw['severity'].upper()}, "
            f"min_thickness={tw['min_thickness_mm']:.2f} mm, "
            f"max_ratio={tw['max_aspect_ratio']:.1f}:1, "
            f"centroid={tw['centroid_mm']}, "
            f"faces={tw['face_idxs']}, "
            f"method(s)={tw['methods']}"
        )
    for i, hw in enumerate(hole_proximity_walls):
        ratio_str = (
            f"{hw['aspect_ratio']:.1f}:1"
            if hw['aspect_ratio'] is not None
            else "∞ (intersecting)"
        )
        logger.info(
            f"  Region {i+1} [hole proximity]: "
            f"severity={hw['severity'].upper()}, "
            f"web_thickness={hw['web_thickness_mm']:.2f} mm, "
            f"overlap_depth={hw['overlap_depth_mm']:.1f} mm, "
            f"aspect_ratio={ratio_str}, "
            f"holes={hw['hole_pair_idxs']}, "
            f"midpoint={hw['midpoint_mm']}"
        )


def log_setup_summary(setup_analysis, fillets=None):
    logger.info("--- Setup Analysis Summary ---")
    logger.info(
        f"  Machine classification: "
        f"{setup_analysis['machine_classification'].upper()}"
    )
    logger.info(f"  Fixturing count: {setup_analysis['fixturing_count']}")

    exc = setup_analysis.get('excluded_counts', {})
    unassigned = setup_analysis.get('unassigned_face_count', 0)
    total = setup_analysis.get('total_features_assigned', 0)
    exc_parts = []
    if exc.get('hole_wall'):
        exc_parts.append(f"{exc['hole_wall']} hole-wall")
    if exc.get('convex_fillet'):
        exc_parts.append(f"{exc['convex_fillet']} convex-fillet")
    if exc.get('passive'):
        exc_parts.append(f"{exc['passive']} passive (post-assigned)")
    exc_str = f" (excluded: {', '.join(exc_parts)})" if exc_parts else ""
    logger.info(
        f"  Features assigned: {total}{exc_str}"
        + (f", {unassigned} face(s) unassigned" if unassigned else "")
    )

    # Build fillet counts per fixturing_idx for the breakdown line
    fillet_counts = {}  # fixturing_idx → {'concave': N, 'convex_fillet': N, 'edge_round': N}
    for flt in (fillets or []):
        fix_idx = flt.get('fixturing_idx')
        if fix_idx is None:
            continue
        bucket = fillet_counts.setdefault(fix_idx, {})
        if flt['type'] == 'concave':
            key = 'concave'
        elif flt.get('subtype') == 'edge_round':
            key = 'edge_round'
        else:
            key = 'convex_fillet'
        bucket[key] = bucket.get(key, 0) + 1

    for f in setup_analysis['fixturings']:
        # Feature type breakdown — build this first so we have the real total
        type_counts = {}
        for a in f['features']:
            ft = a['feature_type']
            type_counts[ft] = type_counts.get(ft, 0) + 1

        # Merge in fillet counts for this fixturing
        for key, count in fillet_counts.get(f['fixturing_idx'], {}).items():
            type_counts[key] = type_counts.get(key, 0) + count

        total_count = sum(type_counts.values())

        vec = f.get('approach_vector')
        if f['approach_axis']:
            axis_str = f", approach={f['approach_axis']}"
        elif vec:
            axis_str = f", approach=({vec[0]:.3f}, {vec[1]:.3f}, {vec[2]:.3f})"
        else:
            axis_str = ""
        alt_str  = (
            " (alt: 3-axis + multiple special fixtures)"
            if f['setup_type'] == "5-axis-indexed"
            else ""
        )
        logger.info(
            f"  Fixturing {f['fixturing_idx'] + 1}: "
            f"type={f['setup_type']}{alt_str}, "
            f"clusters={f['cluster_count']}, "
            f"features={total_count}"
            f"{axis_str}, "
            f"concerns={f['concern_count']}"
        )

        # Human-readable labels, only emit if count > 0
        label_map = [
            ('face',          'planar face'),
            ('hole',          'hole'),
            ('pocket',        'pocket'),
            ('concave',       'concave fillet'),
            ('convex_fillet', 'convex fillet'),
            ('edge_round',    'edge round'),
        ]
        parts = []
        for key, label in label_map:
            n = type_counts.get(key, 0)
            if n:
                parts.append(f"{n} {label}{'s' if n != 1 else ''}")
        if parts:
            logger.info(f"    {', '.join(parts)}")

        for a in f['features']:
            if a['concern_level']:
                logger.info(
                    f"    [{a['concern_level'].upper()}] {a['concern_reason']}"
                )
        advisory = f.get('surface_quality_advisory')
        if advisory:
            logger.info(f"    [ADVISORY] {advisory}")

def log_dfm_summary(dfm_analysis: dict) -> None:
    counts = dfm_analysis['counts']
    flags  = dfm_analysis['flags']

    logger.info("--- DFM Analysis Summary ---")
    logger.info(
        f"  {counts['critical']} critical, "
        f"{counts['warning']} warning, "
        f"{counts['advisory']} advisory"
    )

    if not flags:
        logger.info("  No DFM flags raised.")
        return

    for f in flags:
        label = f['severity'].upper()
        logger.info(f"  [{label}] ({f['category']}) {f['message']}")


def log_tool_access_summary(tool_access: list) -> None:
    logger.info("--- Tool Access — Minimum Tool Diameter per Fixturing ---")

    if not tool_access:
        logger.info("  No fixturings to report.")
        return

    for fix in tool_access:
        axis  = fix['approach_axis'] or 'special'
        label = f"Fixturing {fix['fixturing_idx']} ({axis})"

        if fix['min_tool_dia_mm'] is None:
            logger.info(f"  {label}: no constraints found")
            continue

        min_dia = fix['min_tool_dia_mm']
        n       = len(fix['constraints'])
        tightest = fix['constraints'][0]   # already sorted narrowest-first

        logger.info(
            f"  {label}: min tool dia = {min_dia:.2f} mm  "
            f"({n} constraint{'s' if n != 1 else ''}, "
            f"tightest from {tightest['source']} "
            f"at faces {tightest['face_idxs']})"
        )


def log_feature_count_summary(feature_counts):
    logger.info("--- Feature Count Summary (per Fixturing) ---")
    if not feature_counts:
        logger.info("  No feature count data.")
        return

    for fix in feature_counts:
        axis  = fix['approach_axis'] or 'special'
        label = f"Fixturing {fix['fixturing_idx']} ({axis})"
        h     = fix['holes']
        f     = fix['fillets']

        logger.info(f"  {label}  [{fix['setup_type']}]")
        logger.info(
            f"    Planar: {fix['planar_faces']} faces "
            f"({fix['floor_faces']} floor, {fix['wall_faces']} wall)"
        )

        if h['total'] > 0:
            types_str = ', '.join(f"{v}× {k}" for k, v in h['by_type'].items())
            dias_str  = ', '.join(f"{d:.2f}" for d in h['distinct_dias_mm'])
            depth_str = f", max depth {h['max_depth_mm']:.1f} mm" if h['max_depth_mm'] else ""
            logger.info(f"    Holes:  {h['total']} ({types_str})")
            logger.info(f"            {h['distinct_dia_count']} distinct dia: [{dias_str}] mm{depth_str}")
        else:
            logger.info(f"    Holes:  none")

        if f['total'] > 0:
            logger.info(
                f"    Fillets: {f['total']} "
                f"({f['concave']} concave, {f['convex']} convex), "
                f"r {f['min_radius_mm']:.2f}–{f['max_radius_mm']:.2f} mm"
            )
        else:
            logger.info(f"    Fillets: none")

        logger.info(
            f"    Est. tool changes: ~{fix['estimated_tool_changes']}"
            + (f"  (min tool dia: {fix['min_tool_dia_mm']:.2f} mm)"
               if fix['min_tool_dia_mm'] else "")
        )


def log_fixturing_faces_summary(fixturing_faces):
    logger.info("--- Fixturing Faces Summary ---")
    if not fixturing_faces:
        logger.info("  No fixturing face analysis available.")
        return
    for ff in fixturing_faces:
        axis = ff.get('approach_axis') or 'special'
        label = f"Fixturing {ff['fixturing_idx']} ({axis})"
        wh = ff.get('workholding_class', 'unknown')
        rest = ff.get('rest_faces', [])
        pairs = ff.get('clamp_pairs', [])
        warnings = ff.get('warnings', [])

        logger.info(f"  {label}  workholding={wh}")
        if rest:
            best = rest[0]
            feat_str = " (has features)" if best['has_features'] else ""
            logger.info(
                f"    Best rest face: face {best['face_idx']}, "
                f"area={best['area_mm2']:.0f} mm²{feat_str}"
            )
        else:
            logger.info(f"    No viable rest face")

        if pairs:
            best = pairs[0]
            logger.info(
                f"    Best clamp pair: faces [{best['face_idx_a']}, {best['face_idx_b']}], "
                f"jaw opening={best['jaw_opening_mm']:.1f} mm, "
                f"height={best['clamp_height_mm']:.1f} mm"
            )
        else:
            logger.info(f"    No viable clamp pair")

        for w in warnings:
            logger.info(f"    WARN: {w}")