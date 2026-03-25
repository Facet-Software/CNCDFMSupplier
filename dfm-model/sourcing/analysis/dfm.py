# sourcing/analysis/dfm.py
# DFM (Design for Manufacturability) flag generation.
#
# Takes already-computed feature data (hole_profiles, fillets) and
# produces advisory / warning / critical flags that a machining engineer
# would care about before quoting.
#
# Each flag dict has:
#   severity    : 'advisory' | 'warning' | 'critical'
#   category    : short tag used for grouping (e.g. 'hole_ld', 'small_hole')
#   message     : human-readable string
#   detail      : dict of numeric data that produced the flag (for callers)
#
# All thresholds live in config.py — never hardcode here.

import logging

from sourcing.config import (
    DFM_HOLE_LD_ADVISORY,
    DFM_HOLE_LD_WARNING,
    DFM_HOLE_LD_CRITICAL,
    DFM_HOLE_SMALL_ADVISORY_DIA_MM,
    DFM_HOLE_SMALL_WARNING_DIA_MM,
    DFM_CONVEX_FILLET_WARNING_R_MM,
    DFM_CONVEX_FILLET_AXIS_ALIGNED_TOL,
    DFM_CONCAVE_FILLET_SMALL_WARNING_R_MM,
    DFM_DEEP_FEATURE_FLOOR_TOL,
    DFM_DEEP_FEATURE_LD_ADVISORY,
    DFM_DEEP_FEATURE_LD_WARNING,
    DFM_DEEP_FEATURE_LD_CRITICAL,
)

logger = logging.getLogger(__name__)


def _severity_for_ld(ld_ratio: float) -> str:
    if ld_ratio >= DFM_HOLE_LD_CRITICAL:
        return 'critical'
    if ld_ratio >= DFM_HOLE_LD_WARNING:
        return 'warning'
    return 'advisory'


def _severity_for_dia(dia_mm: float) -> str:
    if dia_mm <= DFM_HOLE_SMALL_WARNING_DIA_MM:
        return 'warning'
    return 'advisory'


def _flag(severity: str, category: str, message: str, **detail) -> dict:
    return {
        'severity': severity,
        'category': category,
        'message':  message,
        'detail':   detail,
    }


# ---------------------------------------------------------------------------
# A. Deep hole L/D ratio
# ---------------------------------------------------------------------------

def _check_hole_ld(hole_profiles: list) -> list:
    """
    Flag holes whose depth-to-diameter ratio exceeds advisory / warning /
    critical thresholds.

    L/D is computed as total_height_mm / (2 * rep_radius_mm).

    A through hole's "depth" is the wall thickness the drill must traverse,
    not the part height, so we use total_height_mm (which for through holes
    equals the cylinder span — correct for tooling reach purposes).
    """
    flags = []
    for i, p in enumerate(hole_profiles):
        dia_mm = p['rep_radius_mm'] * 2.0
        if dia_mm < 1e-6:
            continue
        depth_mm = p['total_height_mm']
        ld = depth_mm / dia_mm

        if ld < DFM_HOLE_LD_ADVISORY:
            continue

        severity = _severity_for_ld(ld)

        if severity == 'critical':
            note = "gun-drilling or EDM likely required"
        elif severity == 'warning':
            note = "extended tooling and pecking cycle required"
        else:
            note = "standard tooling reaches limit — verify spindle reach"

        flags.append(_flag(
            severity, 'hole_ld',
            f"Hole {i+1}: L/D = {ld:.1f}:1 (depth {depth_mm:.1f} mm / "
            f"dia {dia_mm:.2f} mm) — {note}",
            hole_idx=i,
            dia_mm=dia_mm,
            depth_mm=depth_mm,
            ld_ratio=round(ld, 2),
        ))

    return flags


# ---------------------------------------------------------------------------
# B. Small hole diameter
# ---------------------------------------------------------------------------

def _check_small_holes(hole_profiles: list) -> list:
    """
    Flag holes below standard tooling diameter thresholds.

    These require specialty drills, slower feeds, and higher scrap risk —
    all significant cost drivers.
    """
    flags = []
    for i, p in enumerate(hole_profiles):
        dia_mm = p['rep_radius_mm'] * 2.0
        if dia_mm < 1e-6:
            continue

        if dia_mm > DFM_HOLE_SMALL_ADVISORY_DIA_MM:
            continue

        severity = _severity_for_dia(dia_mm)

        if severity == 'warning':
            note = "micro-drilling — high tool breakage risk, few capable suppliers"
        else:
            note = "specialty tooling required, slower cycle time"

        flags.append(_flag(
            severity, 'small_hole',
            f"Hole {i+1}: dia = {dia_mm:.3f} mm — {note}",
            hole_idx=i,
            dia_mm=dia_mm,
        ))

    return flags


# ---------------------------------------------------------------------------
# C. Ball-nose required — concave and convex fillets
# ---------------------------------------------------------------------------

def _check_ball_nose_required(fillets: list) -> list:
    """
    Flag fillets (concave or convex) that require a ball-nose end mill.

    The rule is the same for both types: a ball-nose is only needed when the
    tool must follow the curved cross-section of the fillet. If the fillet
    axis is parallel to the fixturing approach, the tool traverses along the
    axis and never has to cut the arc profile — a standard end mill (or
    corner-radius end mill for concave) handles it fine.

    Axis parallel to approach  → |dot| >= threshold → no flag
    Axis perpendicular          → |dot| <  threshold → ball-nose required

    Severity:
      - advisory  : ball-nose required, radius is manageable
      - warning   : radius < DFM_CONVEX_FILLET_WARNING_R_MM — very small
                    ball-nose, high breakage risk, specialist tooling

    If fixturing_approach_vector is not set (fillet unassigned), flag
    conservatively.
    """
    flags = []

    candidates = [
        f for f in fillets
        if not (f['type'] == 'convex' and f.get('subtype') == 'edge_round')
    ]

    for i, flt in enumerate(candidates):
        r    = flt['radius_mm']
        ax   = flt.get('axis_direction')
        vec  = flt.get('fixturing_approach_vector')
        ftype = flt['type']  # 'concave' or 'convex'

        aligned = False
        dot     = None
        if ax and vec:
            ax_mag  = (ax[0]**2 + ax[1]**2 + ax[2]**2) ** 0.5
            vec_mag = (vec[0]**2 + vec[1]**2 + vec[2]**2) ** 0.5
            if ax_mag > 1e-6 and vec_mag > 1e-6:
                dot = abs(
                    ax[0]*(vec[0]/vec_mag) +
                    ax[1]*(vec[1]/vec_mag) +
                    ax[2]*(vec[2]/vec_mag)
                )
                aligned = dot >= DFM_CONVEX_FILLET_AXIS_ALIGNED_TOL

        if aligned:
            logger.debug(
                f"  {ftype.capitalize()} fillet face {flt['face_idx']}: "
                f"axis aligned (dot={dot:.3f}) — standard tooling, no flag"
            )
            continue

        if r < DFM_CONVEX_FILLET_WARNING_R_MM:
            severity = 'warning'
            note = (f"r = {r:.2f} mm — very small ball-nose required "
                    f"(sub-{DFM_CONVEX_FILLET_WARNING_R_MM:.0f}mm), high breakage risk")
        else:
            severity = 'advisory'
            note = f"r = {r:.2f} mm — ball-nose end mill required"

        flags.append(_flag(
            severity, 'ball_nose_required',
            f"{ftype.capitalize()} fillet (face {flt['face_idx']}): {note}",
            fillet_face_idx=flt['face_idx'],
            fillet_type=ftype,
            radius_mm=r,
            axis_aligned=False,
        ))

    return flags




# ---------------------------------------------------------------------------
# D. Minimum tool diameter from concave fillets
# ---------------------------------------------------------------------------

def _is_axis_aligned(flt: dict) -> bool:
    """Return True if this fillet's axis is parallel to its fixturing approach."""
    ax  = flt.get('axis_direction')
    vec = flt.get('fixturing_approach_vector')
    if not ax or not vec:
        return False
    ax_mag  = (ax[0]**2  + ax[1]**2  + ax[2]**2)  ** 0.5
    vec_mag = (vec[0]**2 + vec[1]**2 + vec[2]**2) ** 0.5
    if ax_mag < 1e-6 or vec_mag < 1e-6:
        return False
    dot = abs(ax[0]*(vec[0]/vec_mag) + ax[1]*(vec[1]/vec_mag) + ax[2]*(vec[2]/vec_mag))
    return dot >= DFM_CONVEX_FILLET_AXIS_ALIGNED_TOL


def _check_concave_fillets(fillets: list) -> list:
    """
    Report the smallest concave fillet radius that constrains end mill
    diameter selection (tool dia ≤ 2 × r).

    Only applies to axis-aligned concave fillets — those machined with a
    standard end mill traversal. Concave fillets that require a ball-nose
    (axis perpendicular to fixturing) are excluded here because ball-nose
    tool selection follows different rules and is already flagged by
    _check_ball_nose_required.

    A single summary flag is emitted for the binding (smallest) radius.

    TODO — Tier 2F: tool reach into pockets.
    This check only flags the radius constraint in isolation. A concave fillet
    inside a deep pocket has a second constraint: the tool must reach the fillet
    floor without exceeding its own L/D limit. A r=3mm fillet at the bottom of
    a 40mm pocket requires a ≤6mm end mill at ~7:1 L/D — likely impossible at
    normal feeds, requiring slow multi-pass or specialist long-reach tooling.

    To implement: for each concave fillet, find its approach direction from
    setup_analysis (the fixturing that covers it), then measure the distance
    from the pocket entry face to the fillet centroid along that axis. Flag if
    depth / (2 × radius) exceeds DFM_HOLE_LD_ADVISORY. Requires pockets to be
    wired into the pipeline first (currently pockets=[] in pipeline.py) so
    fillet-to-pocket association can be established.
    """
    # Only axis-aligned concave fillets — ball-nose fillets use different tooling
    concave = [
        f for f in fillets
        if f['type'] == 'concave' and _is_axis_aligned(f)
    ]
    if not concave:
        return []

    min_flt  = min(concave, key=lambda f: f['radius_mm'])
    r        = min_flt['radius_mm']
    max_tool = r * 2.0

    if r <= DFM_CONCAVE_FILLET_SMALL_WARNING_R_MM:
        severity = 'warning'
        note = (f"max end mill dia ≤ {max_tool:.2f} mm — "
                f"very small tool, slow feeds, high cycle time")
    else:
        severity = 'advisory'
        note = (f"max end mill dia ≤ {max_tool:.2f} mm — "
                f"constrains roughing pass tool selection")

    return [_flag(
        severity, 'concave_fillet_tool_dia',
        f"Smallest concave fillet r = {r:.2f} mm (face {min_flt['face_idx']}): {note}",
        fillet_face_idx=min_flt['face_idx'],
        min_radius_mm=r,
        max_tool_dia_mm=max_tool,
        concave_fillet_count=len(concave),
    )]



# ---------------------------------------------------------------------------
# F. Sharp internal corners per fixturing (Tier 1E)
# ---------------------------------------------------------------------------

def _check_sharp_corners(setup_analysis, planar_faces, fillets,
                         face_list=None, face_to_edges=None,
                         edge_to_faces=None):
    """
    Flag sharp internal corners — edges where two wall faces meet at a
    concave angle with no fillet, which a rotating tool cannot machine
    as drawn.

    A corner is flagged when:
      1. Two planar wall faces (normals perpendicular to approach axis)
         share an edge.
      2. The corner is concave/internal — face B's centroid is on the
         opposite side of face A's outward normal from the edge midpoint.
         Test: dot(n_A, centroid_B - edge_midpoint) < 0
      3. No concave fillet face is adjacent to the same edge.

    Each flag reports the two wall face indices and the edge position.
    The minimum tool radius that could fit the corner is not computable
    without tolerance data — the flag always means "requires designer
    review or EDM/broaching".

    Skipped if adjacency maps or face_list are not provided.
    """
    from OCC.Core.BRepAdaptor import BRepAdaptor_Curve

    if not setup_analysis or not planar_faces:
        return []
    if face_list is None or face_to_edges is None or edge_to_faces is None:
        logger.debug("Sharp corner check: adjacency maps not provided — skipping")
        return []

    WALL_TOL  = 0.5    # |dot(normal, approach)| < this → wall face

    planar_by_idx = {pf['face_idx']: pf for pf in planar_faces}
    fillet_face_idxs = {f['face_idx'] for f in fillets}

    # Map edge_id → set of adjacent fillet face indices
    edge_to_fillets = {}
    for flt in fillets:
        fi = flt['face_idx']
        for eid, _ in face_to_edges.get(fi, []):
            edge_to_fillets.setdefault(eid, set()).add(fi)

    flags  = []
    seen   = set()   # frozenset of (fi_a, fi_b) pairs already flagged

    for fix in setup_analysis['fixturings']:
        approach   = fix['approach_vector']
        fix_idx    = fix['fixturing_idx']
        axis_label = fix['approach_axis'] or f'fixturing {fix_idx}'
        ap_mag     = (approach[0]**2 + approach[1]**2 + approach[2]**2) ** 0.5
        if ap_mag < 1e-9:
            continue

        ax = approach[0] / ap_mag
        ay = approach[1] / ap_mag
        az = approach[2] / ap_mag

        assigned_face_idxs = {
            feat['feature_idx']
            for feat in fix.get('features', [])
            if feat['feature_type'] == 'face'
        }

        # Wall faces for this fixturing
        wall_idxs = set()
        for fi in assigned_face_idxs:
            pf = planar_by_idx.get(fi)
            if pf is None:
                continue
            n   = pf['_normal_dir']
            dot = abs(n.X()*ax + n.Y()*ay + n.Z()*az)
            if dot < WALL_TOL:
                wall_idxs.add(fi)

        logger.debug(
            f"  Sharp corners fixturing {fix_idx} ({axis_label}): "
            f"{len(assigned_face_idxs)} assigned faces, "
            f"{len(wall_idxs)} wall faces: {sorted(wall_idxs)}"
        )

        # Check every shared edge between two wall faces
        for fi_a in wall_idxs:
            pf_a = planar_by_idx[fi_a]
            n_a  = pf_a['_normal_dir']   # outward normal of face A

            edges_a = face_to_edges.get(fi_a, [])
            logger.debug(f"    Face {fi_a}: {len(edges_a)} edges")

            for eid, edge in edges_a:
                neighbors = edge_to_faces.get(eid, [])
                for fi_b in neighbors:
                    if fi_b == fi_a or fi_b not in wall_idxs:
                        continue

                    pair = frozenset((fi_a, fi_b))
                    if pair in seen:
                        continue
                    seen.add(pair)

                    has_fillet = bool(edge_to_fillets.get(eid))
                    logger.debug(
                        f"      Wall pair ({fi_a},{fi_b}) edge {eid}: "
                        f"fillet_adjacent={has_fillet}"
                    )

                    # Skip if a fillet is already present on this edge
                    if has_fillet:
                        continue

                    # Near-edge sample test.
                    #
                    # Sample a point on face B a small distance from the shared
                    # edge rather than using the face centroid. This is robust
                    # for non-convex (L-shaped, U-shaped) faces where the
                    # centroid may fall outside the face boundary.
                    #
                    # Steps:
                    #   1. Get edge midpoint p_mid and tangent t.
                    #   2. Compute d_raw = n_B × t — perpendicular to edge,
                    #      lies in face B's plane.
                    #   3. Resolve sign of d_raw using the centroid: flip if
                    #      centroid is on the opposite side (centroid is always
                    #      geometrically on the face side of the edge even for
                    #      non-convex faces).
                    #   4. p_B_sample = p_mid + epsilon * d_in_B
                    #   5. Concavity: dot(n_A, p_B_sample - p_mid) > 0
                    #      → p_B_sample is on the outward side of face A
                    #      → CONCAVE / internal corner.
                    try:
                        adapt  = BRepAdaptor_Curve(edge)
                        t_mid  = (adapt.FirstParameter() + adapt.LastParameter()) / 2
                        mid_pt = adapt.Value(t_mid)
                        t_vec  = adapt.DN(t_mid, 1)
                        t_len  = (t_vec.X()**2 + t_vec.Y()**2 + t_vec.Z()**2) ** 0.5
                        if t_len < 1e-9:
                            continue
                        tx = t_vec.X() / t_len
                        ty = t_vec.Y() / t_len
                        tz = t_vec.Z() / t_len
                    except Exception:
                        continue

                    pf_b = planar_by_idx[fi_b]
                    nb   = pf_b['_normal_dir']

                    # d_raw = n_B × t  (in face B's plane, perp to edge)
                    drx = nb.Y()*tz - nb.Z()*ty
                    dry = nb.Z()*tx - nb.X()*tz
                    drz = nb.X()*ty - nb.Y()*tx
                    dr_len = (drx**2 + dry**2 + drz**2) ** 0.5
                    if dr_len < 1e-9:
                        continue
                    drx /= dr_len; dry /= dr_len; drz /= dr_len

                    # Resolve sign using centroid direction from edge midpoint
                    cog_b = pf_b['_centroid']
                    cx_   = cog_b.X() - mid_pt.X()
                    cy_   = cog_b.Y() - mid_pt.Y()
                    cz_   = cog_b.Z() - mid_pt.Z()
                    if drx*cx_ + dry*cy_ + drz*cz_ < 0:
                        drx = -drx; dry = -dry; drz = -drz

                    # Concavity: is the in-face-B direction on n_A's outward side?
                    sign = n_a.X()*drx + n_a.Y()*dry + n_a.Z()*drz

                    logger.debug(
                        f"      Pair ({fi_a},{fi_b}) near-edge sign={sign:.4f} "
                        f"(concave if > 0)"
                    )
                    if sign <= 0:
                        continue

                    pos_mm = (
                        round(mid_pt.X() * 1000, 1),
                        round(mid_pt.Y() * 1000, 1),
                        round(mid_pt.Z() * 1000, 1),
                    )

                    flags.append(_flag(
                        'warning', 'sharp_internal_corner',
                        (f"Fixturing {axis_label}: sharp internal corner "
                         f"between faces {fi_a} and {fi_b} — "
                         f"tool always leaves a radius, requires fillet or EDM"),
                        fixturing_idx=fix_idx,
                        face_idxs=[fi_a, fi_b],
                        edge_id=eid,
                        position_mm=pos_mm,
                    ))
                    logger.debug(
                        f"  Sharp corner: fixturing {fix_idx} ({axis_label}), "
                        f"faces [{fi_a}, {fi_b}], edge {eid}, pos={pos_mm}"
                    )

    return flags


# ---------------------------------------------------------------------------
# E. Deep features per fixturing (Tier 2E)
# ---------------------------------------------------------------------------

def _check_deep_features(tool_access, setup_analysis, planar_faces,
                         bbox_extents=None, **kwargs):
    """
    Flag deep features per fixturing using bounding box entry reference.

    For each floor face (normal parallel to approach axis) in an eligible
    fixturing, depth = distance from the bounding box entry surface to the
    face centroid, measured along the approach axis.

    Entry reference: bounding box maximum extent in the approach direction,
    computed by projecting all 8 corners and taking the max. This is always
    the true tool entry point — unaffected by bosses, steps, or which faces
    happen to sit at the top of the part.

    depth / min_tool_dia → L/D flag.

    Skipped for 5-axis-continuous fixturings — the approach vector varies
    per feature, making a fixed-axis depth meaningless.
    Skipped if no min_tool_dia is available for the fixturing.

    bbox_extents: (xmin, ymin, zmin, xmax, ymax, zmax) in model units.
    """
    if not tool_access or not setup_analysis or not planar_faces:
        return []
    if bbox_extents is None:
        logger.debug("Deep feature check: bbox_extents not provided — skipping")
        return []

    xmin, ymin, zmin, xmax, ymax, zmax = bbox_extents
    planar_by_idx = {pf['face_idx']: pf for pf in planar_faces}
    tool_by_fix   = {ta['fixturing_idx']: ta for ta in tool_access}
    flags         = []

    corners = [
        (xmin, ymin, zmin), (xmax, ymin, zmin),
        (xmin, ymax, zmin), (xmax, ymax, zmin),
        (xmin, ymin, zmax), (xmax, ymin, zmax),
        (xmin, ymax, zmax), (xmax, ymax, zmax),
    ]

    for fix in setup_analysis['fixturings']:
        fix_idx    = fix['fixturing_idx']
        setup_type = fix.get('setup_type', '3-axis-standard')
        approach   = fix['approach_vector']
        axis_label = fix['approach_axis'] or f'fixturing {fix_idx}'
        ap_mag     = (approach[0]**2 + approach[1]**2 + approach[2]**2) ** 0.5
        if ap_mag < 1e-9:
            continue

        if setup_type == '5-axis-continuous':
            logger.debug(
                f"  Deep feature fixturing {fix_idx} ({axis_label}): "
                f"5-axis-continuous — skipping depth check"
            )
            continue

        ta = tool_by_fix.get(fix_idx)
        if ta is None or ta['min_tool_dia_mm'] is None:
            logger.debug(
                f"  Deep feature fixturing {fix_idx} ({axis_label}): "
                f"no min tool dia — skipping"
            )
            continue

        min_dia = ta['min_tool_dia_mm']

        ax = approach[0] / ap_mag
        ay = approach[1] / ap_mag
        az = approach[2] / ap_mag

        # Entry reference: highest bbox corner projected onto approach axis
        entry_ref = max(x*ax + y*ay + z*az for x, y, z in corners)

        assigned_face_idxs = {
            feat['feature_idx']
            for feat in fix['features']
            if feat['feature_type'] == 'face'
        }

        for fi in assigned_face_idxs:
            pf = planar_by_idx.get(fi)
            if pf is None:
                continue
            n   = pf['_normal_dir']
            dot = abs(n.X()*ax + n.Y()*ay + n.Z()*az)
            if dot < DFM_DEEP_FEATURE_FLOOR_TOL:
                continue   # wall face, not a floor

            cog      = pf['_centroid']
            face_pos = cog.X()*ax + cog.Y()*ay + cog.Z()*az
            depth_mm = (entry_ref - face_pos) * 1000.0

            if depth_mm < 1e-3:
                continue   # at or above entry — external surface

            ld = depth_mm / min_dia

            if ld >= DFM_DEEP_FEATURE_LD_CRITICAL:
                severity = 'critical'
            elif ld >= DFM_DEEP_FEATURE_LD_WARNING:
                severity = 'warning'
            elif ld >= DFM_DEEP_FEATURE_LD_ADVISORY:
                severity = 'advisory'
            else:
                logger.debug(
                    f"  Deep feature: fixturing {fix_idx}, face {fi}: "
                    f"depth={depth_mm:.1f} mm, L/D={ld:.1f} — below advisory"
                )
                continue

            pos_mm = (
                round(cog.X() * 1000, 1),
                round(cog.Y() * 1000, 1),
                round(cog.Z() * 1000, 1),
            )
            flags.append(_flag(
                severity, 'deep_feature',
                (f"Fixturing {axis_label}, face {fi}: "
                 f"depth = {depth_mm:.1f} mm, "
                 f"min tool dia = {min_dia:.2f} mm, "
                 f"L/D = {ld:.1f}"),
                fixturing_idx=fix_idx,
                face_idx=fi,
                depth_mm=round(depth_mm, 2),
                min_tool_dia_mm=min_dia,
                ld_ratio=round(ld, 2),
                position_mm=pos_mm,
            ))
            logger.debug(
                f"  Deep feature: fixturing {fix_idx} ({axis_label}), "
                f"face {fi}, depth={depth_mm:.1f} mm, "
                f"L/D={ld:.1f} [{severity}]"
            )

    return flags

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _check_partial_holes(partial_holes: list) -> list:
    """
    Flag holes whose bore wall has been broken through by an intersecting
    feature — a pocket, slot, or adjacent hole.

    These are non-standard features that require the supplier to confirm
    the intended geometry: is this intentional (e.g. a drain slot crossing
    a bore), or a modelling error?
    """
    flags = []
    for ph in partial_holes:
        hi  = ph['hole_idx']
        r   = ph['rep_radius_mm']
        pct = ph['exposed_pct']
        sev = ph['severity']
        n_angles = len(ph['exposed_angles_deg'])
        flags.append(_flag(
            sev, 'partial_hole',
            f"Hole {hi + 1} (⌀{r * 2:.2f} mm): bore wall intersected by another feature "
            f"— {pct:.0f}% of circumference exposed "
            f"({'major breakthrough' if sev == 'critical' else 'minor clipping'}). "
            f"Confirm geometry is intentional.",
            hole_idx=hi,
            face_idxs=ph['face_idxs'],
            rep_radius_mm=r,
            exposed_pct=pct,
            exposed_angles_deg=ph['exposed_angles_deg'],
        ))
    return flags


def _check_thin_walls(thin_walls: list, hole_proximity_walls: list) -> list:
    """
    Convert detected thin wall regions and hole proximity webs into DFM flags.

    thin_walls            — from detect_thin_walls() (planar pair, concentric
                            cylinder, and ray-cast regions)
    hole_proximity_walls  — from detect_hole_proximity_walls() (webs between
                            adjacent drilled holes)
    """
    flags = []

    for i, tw in enumerate(thin_walls):
        t   = tw['min_thickness_mm']
        r   = tw['max_aspect_ratio']
        sev = tw['severity']   # already 'warning' or 'critical'
        face_str = f"faces {tw['face_idxs']}" if len(tw['face_idxs']) <= 4 else f"{len(tw['face_idxs'])} faces"
        flags.append(_flag(
            sev, 'thin_wall',
            f"Thin wall region {i+1} ({face_str}): "
            f"{t:.2f} mm thick, aspect ratio {r:.1f}:1 — "
            f"{'deflection and chatter risk' if sev == 'critical' else 'verify rigidity during machining'}",
            region_idx=i,
            min_thickness_mm=t,
            max_aspect_ratio=r,
            face_idxs=tw['face_idxs'],
        ))

    for hw in hole_proximity_walls:
        i, j = hw['hole_pair_idxs']
        web  = hw['web_thickness_mm']
        sev  = 'critical' if hw['severity'] in ('critical', 'intersecting') else 'warning'
        if hw['severity'] == 'intersecting':
            msg = (f"Holes {i+1} and {j+1} intersect — web thickness ≤ 0 mm, "
                   f"overlapping bores require combined operation or EDM")
        else:
            r   = hw.get('aspect_ratio') or 0
            msg = (f"Thin web between holes {i+1} and {j+1}: "
                   f"{web:.2f} mm wall, aspect ratio {r:.1f}:1 — "
                   f"risk of breakthrough during drilling")
        flags.append(_flag(
            sev, 'thin_wall_hole_proximity', msg,
            hole_pair_idxs=hw['hole_pair_idxs'],
            web_thickness_mm=web,
        ))

    return flags


# ---------------------------------------------------------------------------
# I. Workholding / fixturing concerns
# ---------------------------------------------------------------------------

def _check_workholding(fixturing_faces: list) -> list:
    """
    Flag workholding concerns from the fixturing face analysis.

    These are cost and risk drivers that affect quoting:
      - No viable datum face → custom fixture required (expensive)
      - Features on datum face → shimming or nest required
      - No opposing clamp pair → toe clamps, extra setup time
      - Centre of gravity outside rest footprint → tipping risk
      - Soft jaws required → fixture cost adder
    """
    if not fixturing_faces:
        return []

    flags = []
    for ff in fixturing_faces:
        fix_idx = ff['fixturing_idx']
        axis    = ff.get('approach_axis') or f'fixturing {fix_idx}'

        rest     = ff.get('rest_faces', [])
        pairs    = ff.get('clamp_pairs', [])
        wh_class = ff.get('workholding_class', 'unknown')
        stab     = ff.get('stability', {})

        # No rest face at all — critical
        if not rest:
            flags.append(_flag(
                'critical', 'no_datum_face',
                f"Fixturing {axis}: no viable datum/rest face found — "
                f"custom fixture or nest required",
                fixturing_idx=fix_idx,
            ))
            continue

        best_rest = rest[0]

        # Features on best rest face — warning
        if best_rest.get('has_features'):
            flags.append(_flag(
                'warning', 'datum_face_features',
                f"Fixturing {axis}: best datum face (face {best_rest['face_idx']}, "
                f"{best_rest['area_mm2']:.0f} mm²) has machined features — "
                f"part won't seat flat without shimming or custom nest",
                fixturing_idx=fix_idx,
                face_idxs=[best_rest['face_idx']],
            ))

        # CoG instability — warning
        if stab.get('cog_inside_footprint') is False:
            flags.append(_flag(
                'warning', 'cog_instability',
                f"Fixturing {axis}: part center of gravity projects outside "
                f"datum face footprint (offset "
                f"{stab.get('offset_from_center_mm', '?')} mm) — "
                f"part will tend to tip, toe clamps required",
                fixturing_idx=fix_idx,
                face_idxs=[best_rest['face_idx']],
            ))

        # No clamping pair — advisory (toe clamps work, just slower)
        if not pairs:
            flags.append(_flag(
                'advisory', 'no_clamp_pair',
                f"Fixturing {axis}: no opposing face pair for vise — "
                f"toe clamps or strap clamps needed (adds setup time)",
                fixturing_idx=fix_idx,
            ))
        elif pairs[0].get('has_features'):
            flags.append(_flag(
                'advisory', 'clamp_face_features',
                f"Fixturing {axis}: best clamp pair "
                f"(faces {pairs[0]['face_idx_a']}, {pairs[0]['face_idx_b']}) "
                f"has features — soft jaws recommended",
                fixturing_idx=fix_idx,
                face_idxs=[pairs[0]['face_idx_a'], pairs[0]['face_idx_b']],
            ))

        # Overall soft jaw / custom classification — advisory for cost impact
        if wh_class == 'custom':
            flags.append(_flag(
                'advisory', 'custom_fixture',
                f"Fixturing {axis}: custom fixture required — "
                f"significant setup cost adder for quoting",
                fixturing_idx=fix_idx,
            ))

    return flags


def analyze_dfm(hole_profiles: list, fillets: list,
                tool_access: list = None, setup_analysis: dict = None,
                planar_faces: list = None, bbox_extents: tuple = None,
                shape=None, face_list: list = None,
                face_to_edges: dict = None, edge_to_faces: dict = None,
                thin_walls: list = None,
                hole_proximity_walls: list = None,
                partial_holes: list = None,
                fixturing_faces: list = None) -> dict:
    """
    Run all DFM checks and return a structured result.

    Returns:
        {
            'flags':  list of flag dicts (sorted critical → warning → advisory),
            'counts': {'advisory': int, 'warning': int, 'critical': int},
        }
    """
    flags: list[dict] = []
    flags.extend(_check_hole_ld(hole_profiles))
    flags.extend(_check_small_holes(hole_profiles))
    flags.extend(_check_ball_nose_required(fillets))
    flags.extend(_check_concave_fillets(fillets))
    flags.extend(_check_sharp_corners(setup_analysis, planar_faces, fillets,
                                      face_list=face_list,
                                      face_to_edges=face_to_edges,
                                      edge_to_faces=edge_to_faces))
    flags.extend(_check_deep_features(tool_access, setup_analysis, planar_faces,
                                      bbox_extents=bbox_extents))
    flags.extend(_check_thin_walls(thin_walls or [], hole_proximity_walls or []))
    flags.extend(_check_partial_holes(partial_holes or []))
    flags.extend(_check_workholding(fixturing_faces or []))

    # ── Post-annotate flags with fixturing_idx ──
    # Some checks (hole_ld, small_hole, concave_fillet, ball_nose, partial_hole,
    # thin_wall) run without fixture context. Build lookup maps from setup_analysis
    # and annotate any flag that has a hole_idx or fillet_face_idx but no
    # fixturing_idx.
    if setup_analysis and setup_analysis.get('fixturings'):
        # hole profile index → fixturing_idx
        hole_to_fix = {}
        # face_idx → fixturing_idx
        face_to_fix = {}
        for fix in setup_analysis['fixturings']:
            fix_idx = fix['fixturing_idx']
            for feat in fix.get('features', []):
                if feat['feature_type'] == 'hole':
                    hole_to_fix[feat['feature_idx']] = fix_idx
                elif feat['feature_type'] == 'face':
                    face_to_fix[feat['feature_idx']] = fix_idx

        # Also map fillet face_idx → fixturing_idx from fillet assignments
        if fillets:
            for flt in fillets:
                fi = flt.get('face_idx')
                fix_i = flt.get('fixturing_idx')
                if fi is not None and fix_i is not None:
                    face_to_fix[fi] = fix_i

        for flag in flags:
            d = flag.get('detail', {})
            if 'fixturing_idx' in d:
                continue  # already annotated

            # Try hole_idx → fixturing
            hi = d.get('hole_idx')
            if hi is not None and hi in hole_to_fix:
                d['fixturing_idx'] = hole_to_fix[hi]
                continue

            # Try fillet_face_idx → fixturing
            ffi = d.get('fillet_face_idx')
            if ffi is not None and ffi in face_to_fix:
                d['fixturing_idx'] = face_to_fix[ffi]
                continue

            # Try face_idx → fixturing
            fi = d.get('face_idx')
            if fi is not None and fi in face_to_fix:
                d['fixturing_idx'] = face_to_fix[fi]
                continue

            # Try face_idxs → fixturing (use first match)
            for fi in d.get('face_idxs', []):
                if fi in face_to_fix:
                    d['fixturing_idx'] = face_to_fix[fi]
                    break

            # Try hole_pair_idxs → fixturing (use first match)
            for hi in d.get('hole_pair_idxs', []):
                if hi in hole_to_fix:
                    d['fixturing_idx'] = hole_to_fix[hi]
                    break

    # Sort: critical first, then warning, then advisory
    _order = {'critical': 0, 'warning': 1, 'advisory': 2}
    flags.sort(key=lambda f: _order[f['severity']])

    counts = {'advisory': 0, 'warning': 0, 'critical': 0}
    for f in flags:
        counts[f['severity']] += 1

    logger.debug(
        f"DFM analysis: {counts['critical']} critical, "
        f"{counts['warning']} warning, {counts['advisory']} advisory"
    )

    return {'flags': flags, 'counts': counts}