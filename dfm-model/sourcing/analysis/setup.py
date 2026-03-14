# sourcing/analysis/setup.py
# Setup and fixturing analysis.
#
# Answers what a supplier needs to quote a part:
#   - How many times does the part need to be re-fixtured?
#   - What kind of machine is required?
#   - Which features are accessible from which setup, and are any at a
#     difficult approach angle?
#
# Machine classifications (in order of cost/complexity):
#   3-axis-standard        All setups align to ±X ±Y ±Z principal axes.
#   3-axis-special-fixture One setup needs a non-axis-aligned fixture
#                          (sine plate, angle block), but all features within
#                          it share a single fixed approach direction.
#   5-axis-indexed         At least one fixturing needs multiple discrete tilt
#                          positions (3+2 operation).
#   5-axis-continuous      Freeform faces require continuously varying tool
#                          orientation within a fixturing.
#
# Algorithm
# ---------
# 1. Collect directional constraints: planar face normals, hole axes, pocket
#    access directions — each tagged with source type.
# 2. Gauss map clustering: group directions by angular proximity on the unit
#    sphere. Cluster count emerges from the data.
# 3. Hemisphere grouping: merge clusters into fixturings. Clusters within 90°
#    of a common pole share a fixturing; opposite clusters require re-fixturing.
# 4. Per-fixturing classification: principal axis snap → setup type.
# 5. Feature assignment: compute angular deviation per feature, map to concern
#    level per feature type.

import math
import logging

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCC.Core.TopoDS import topods
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core import GeomAbs
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir

from sourcing.config import (
    SETUP_PRINCIPAL_AXIS_TOL_DEG,
    SETUP_HOLE_ADVISORY_DEG,
    SETUP_HOLE_WARNING_DEG,
    SETUP_HOLE_CRITICAL_DEG,
    SETUP_POCKET_ADVISORY_DEG,
    SETUP_POCKET_WARNING_DEG,
    SETUP_POCKET_CRITICAL_DEG,
    SETUP_PLANAR_ADVISORY_DEG,
    SETUP_PLANAR_WARNING_DEG,
    SETUP_PLANAR_CRITICAL_DEG,
    SETUP_STANDARD_FIXTURE_ANGLES_DEG,
    SETUP_STANDARD_FIXTURE_ANGLE_TOL_DEG,
)

logger = logging.getLogger(__name__)

_PRINCIPAL_AXES = [
    ("+Z", ( 0.0,  0.0,  1.0)),
    ("-Z", ( 0.0,  0.0, -1.0)),
    ("+X", ( 1.0,  0.0,  0.0)),
    ("-X", (-1.0,  0.0,  0.0)),
    ("+Y", ( 0.0,  1.0,  0.0)),
    ("-Y", ( 0.0, -1.0,  0.0)),
]


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def analyze_setups(shape, planar_faces, hole_profiles, pockets, fillets=None,
                   edge_to_faces=None, face_list=None):
    """
    Perform setup and fixturing analysis on the part.

    Parameters
    ----------
    shape         : TopoDS_Shape
    planar_faces  : list of dicts — from get_planar_faces()
    hole_profiles : list of dicts — from detect_cylindrical_features() +
                    classify_through_blind()
    pockets       : list of dicts — from detect_pockets(); pass [] if not
                    yet implemented

    Returns
    -------
    {
        machine_classification : str   — worst-case across all fixturings
        fixturing_count        : int
        fixturings             : list[fixturing_dict]
    }

    Each fixturing_dict:
        fixturing_idx   : int
        setup_type      : "3-axis-standard" | "3-axis-special-fixture"
                          | "5-axis-indexed" | "5-axis-continuous"
        approach_axis   : str | None    e.g. "+Z"; None if non-principal
        cluster_count   : int           discrete tilt positions needed
        feature_count   : int
        has_freeform    : bool
        features        : list[feature_assignment_dict]
        concern_count   : {"advisory": N, "warning": N, "critical": N}

    Each feature_assignment_dict:
        feature_type          : "planar_face" | "hole" | "pocket"
        feature_idx           : int
        constraint_direction  : (nx, ny, nz)
        angular_deviation_deg : float
        concern_level         : None | "advisory" | "warning" | "critical"
        concern_reason        : str | None
    """
    face_normals, face_adjacency, passive_face_idxs, has_freeform, excluded_counts = _collect_face_normals(
        shape, hole_profiles, fillets or [], edge_to_faces=edge_to_faces,
        face_list=face_list)

    if not face_normals and not hole_profiles and not pockets:
        logger.warning("No directional constraints — cannot determine setups")
        return {
            "machine_classification": "unknown",
            "fixturing_count":        0,
            "fixturings":             [],
        }

    clusters = _hemisphere_set_cover(face_normals, hole_profiles, pockets, face_adjacency, passive_face_idxs)
    logger.info(
        f"Set-cover: {len(face_normals)} face samples → "
        f"{len(clusters)} fixturing directions"
    )

    # Each cluster from set-cover is one fixturing
    fixturing_groups = [[c] for c in clusters]

    freeform_faces = _find_freeform_faces(shape)
    if freeform_faces:
        logger.debug(f"  Freeform faces found: {list(freeform_faces.keys())}")

    fixturings = [
        _build_fixturing(
            i, cluster_group,
            planar_faces, hole_profiles, pockets,
        )
        for i, cluster_group in enumerate(fixturing_groups)
    ]

    # Deduplicate through-hole assignments across fixturings.
    _deduplicate_through_holes(fixturings, hole_profiles)

    # Remove fixturings that ended up with no features after deduplication.
    fixturings = [f for f in fixturings if f['feature_count'] > 0]
    for i, f in enumerate(fixturings):
        f['fixturing_idx'] = i

    # Upgrade special-fixture classifications to 5-axis-indexed where needed.
    _upgrade_special_to_indexed(fixturings)

    # Upgrade fixturings with undercut freeform surfaces to 5-axis-continuous.
    _upgrade_freeform_to_continuous(fixturings, freeform_faces)

    # Flag non-principal fixturings driven by large faces — surface quality
    # advisory only, does not change setup count or classification.
    non_principal_advisories = _flag_large_non_principal_faces(face_normals, clusters)
    for f in fixturings:
        centroid = f['_cluster_centroid']
        advisory = next(
            (v for k, v in non_principal_advisories.items()
             if _angle_deg(k, centroid) < 5.0),
            None
        )
        f['surface_quality_advisory'] = advisory

    rank = {
        "3-axis-standard":        0,
        "3-axis-special-fixture": 1,
        "5-axis-indexed":         2,
        "5-axis-continuous":      3,
    }
    worst = max(fixturings, key=lambda f: rank[f["setup_type"]])

    logger.info(
        f"Machine classification: {worst['setup_type']}, "
        f"fixturings: {len(fixturings)}"
    )

    # Compute how many face_normals entries (unique face_idxs) ended up unassigned
    assigned_face_idxs = {
        fi
        for f in fixturings
        for _, src, fi in f.get('_members', [])
        if src == 'face'
    }
    # _members isn't stored on the fixturing dict — use features list instead
    assigned_face_idxs = set()
    assigned_hole_idxs = set()
    for f in fixturings:
        for feat in f['features']:
            if feat['feature_type'] == 'face':
                assigned_face_idxs.add(feat['feature_idx'])
            elif feat['feature_type'] == 'hole':
                assigned_hole_idxs.add(feat['feature_idx'])

    all_face_idxs_in_normals = {fi for _, _, fi in face_normals}
    unassigned_face_idxs = all_face_idxs_in_normals - assigned_face_idxs
    total_features = sum(f['feature_count'] for f in fixturings)

    # Post-assign fillets to fixturings by neighbor vote.
    # Fillets were excluded from set-cover but DFM needs their fixturing
    # context (e.g. is a concave fillet inside a deep pocket or on an open wall).
    _assign_fillets_to_fixturings(fillets or [], fixturings, edge_to_faces or {})

    return {
        "machine_classification": worst["setup_type"],
        "fixturing_count":        len(fixturings),
        "fixturings":             fixturings,
        "total_features_assigned": total_features,
        "unassigned_face_count":  len(unassigned_face_idxs),
        "excluded_counts":        excluded_counts,
    }


# ---------------------------------------------------------------------------
# STEP 1 — COLLECT FACE NORMALS
# ---------------------------------------------------------------------------

def _collect_face_normals(shape, hole_profiles, fillets, edge_to_faces=None, face_list=None):
    """
    Sample outward normals from every face on the shape.

    Returns list of (normal_tuple, area_mm2, face_idx).

    Planes      → one sample at center UV
    Freeform    → N×N UV grid, each sample weighted by area/N²
    Cylinders   → axis direction (±), excluding hole walls and fillets.
                  Hole walls are already captured by hole_profiles axes.
                  Fillets are transition features reached from the adjacent
                  floor/wall approach — their axis would give a misleading
                  direction. Non-hole, non-fillet cylinders (pocket walls,
                  bosses) contribute their axis as the machining direction.
    Cones       → same treatment as cylinders (excluding hole cones and fillets)
    Spheres     → excluded — no single meaningful axis
    Tori        → excluded — transition features like fillets
    """
    from OCC.Core.BRepGProp import brepgprop
    from OCC.Core.GProp     import GProp_GProps

    N_FREEFORM = 5
    has_freeform = False  # True if any genuinely freeform face is found

    freeform_types = {
        GeomAbs.GeomAbs_BSplineSurface,
        GeomAbs.GeomAbs_BezierSurface,
        GeomAbs.GeomAbs_SurfaceOfRevolution,
        GeomAbs.GeomAbs_SurfaceOfExtrusion,
        GeomAbs.GeomAbs_OffsetSurface,
        GeomAbs.GeomAbs_OtherSurface,
    }

    # Faces to exclude from cylinder/cone axis sampling
    hole_face_idxs   = {fi for hp in hole_profiles for fi in hp.get('face_idxs', [])}

    # Also exclude planar end cap faces at the closed end of blind holes.
    # These interior faces (e.g. the flat floor of a blind hole, or a chamfered
    # drill entry) are produced by the drilling operation — they're not separately
    # machined surfaces and shouldn't drive setup direction or feature count.
    # Detection: a planar face adjacent (via edge_to_faces) to a hole wall face
    # whose centroid lies at or near the closed-end v-coordinate along the axis.
    if edge_to_faces:
        for hp in hole_profiles:
            if hp.get('is_through'):
                continue
            gpa       = hp.get('get_point_along_axis')
            axis_loc  = hp.get('axis_location')
            axis_dir  = hp.get('axis_direction')
            closed_end = hp.get('closed_end')
            if gpa is None or axis_dir is None or closed_end is None:
                continue
            v_closed = hp['v_min_overall'] if closed_end == 'min' else hp['v_max_overall']
            ax = _norm(axis_dir)
            # Tolerance: 3mm along axis to catch angled/chamfered end caps
            tol_v = 3.0 / 1000.0  # model units (metres)
            # Find all face_idxs adjacent to any hole wall face
            adj_candidates = set()
            for fi in hp.get('face_idxs', []):
                for edge_key, face_pair in edge_to_faces.items():
                    if fi in face_pair:
                        for other_fi in face_pair:
                            if other_fi != fi and other_fi not in hole_face_idxs:
                                adj_candidates.add(other_fi)
            # Check each adjacent face: is its centroid at the closed end?
            if adj_candidates and face_list is not None:
                for fi in adj_candidates:
                    if fi >= len(face_list):
                        continue
                    fc = face_list[fi]
                    try:
                        props2 = GProp_GProps()
                        brepgprop.SurfaceProperties(fc, props2)
                        c = props2.CentreOfMass()
                        # Project centroid onto hole axis relative to axis_loc
                        loc = axis_loc
                        rel = (c.X()-loc[0], c.Y()-loc[1], c.Z()-loc[2])
                        v_proj = rel[0]*ax[0] + rel[1]*ax[1] + rel[2]*ax[2]
                        if abs(v_proj - v_closed) < tol_v:
                            hole_face_idxs.add(fi)
                    except Exception:
                        pass
    # Only exclude convex faces classified as true fillets (small radius, high h/r).
    # Edge rounds (large radius, low h/r) do constrain fixturing direction and are
    # included in setup analysis like any other face.
    fillet_face_idxs = {
        f['face_idx'] for f in fillets
        if f.get('type') == 'convex' and f.get('subtype', 'fillet') == 'fillet'
    }
    skip_axis_idxs   = hole_face_idxs | fillet_face_idxs
    passive_face_idxs = set()  # vertical cylinders/cones assigned post-hoc by neighbor vote

    result   = []
    exp      = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx = 0

    while exp.More():
        face    = topods.Face(exp.Current())
        adaptor = BRepAdaptor_Surface(face)
        stype   = adaptor.GetType()

        # Compute face area regardless of type
        props = GProp_GProps()
        brepgprop.SurfaceProperties(face, props)
        area_mm2 = props.Mass() * 1e6   # model units² → mm²

        # Orientation flip: D1 cross product gives parametric normal which
        # points inward when the face is reversed in the topology.
        flip = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0

        u0, u1 = adaptor.FirstUParameter(), adaptor.LastUParameter()
        v0, v1 = adaptor.FirstVParameter(), adaptor.LastVParameter()

        if stype == GeomAbs.GeomAbs_Plane:
            if face_idx not in hole_face_idxs:
                try:
                    p = gp_Pnt(); du = gp_Vec(); dv = gp_Vec()
                    adaptor.D1((u0+u1)/2, (v0+v1)/2, p, du, dv)
                    n = (flip*(du.Y()*dv.Z()-du.Z()*dv.Y()),
                         flip*(du.Z()*dv.X()-du.X()*dv.Z()),
                         flip*(du.X()*dv.Y()-du.Y()*dv.X()))
                    if _mag(n) > 1e-6:
                        result.append((_norm(n), area_mm2, face_idx))
                except Exception:
                    pass

        elif stype in freeform_types:
            if face_idx not in hole_face_idxs:
                has_freeform = True
                per_sample = area_mm2 / (N_FREEFORM ** 2)
                for i in range(N_FREEFORM):
                    u = u0 + (u1-u0)*(i+0.5)/N_FREEFORM
                    for j in range(N_FREEFORM):
                        v = v0 + (v1-v0)*(j+0.5)/N_FREEFORM
                        try:
                            p = gp_Pnt(); du = gp_Vec(); dv = gp_Vec()
                            adaptor.D1(u, v, p, du, dv)
                            n = (flip*(du.Y()*dv.Z()-du.Z()*dv.Y()),
                                 flip*(du.Z()*dv.X()-du.X()*dv.Z()),
                                 flip*(du.X()*dv.Y()-du.Y()*dv.X()))
                            if _mag(n) > 1e-6:
                                result.append((_norm(n), per_sample, face_idx))
                        except Exception:
                            continue
                logger.debug(
                    f"  Freeform face {face_idx}: type={stype}, "
                    f"area={area_mm2:.0f} mm² → requires 5-axis-continuous"
                )

        elif stype == GeomAbs.GeomAbs_Cylinder:
            if face_idx not in skip_axis_idxs:
                try:
                    ax = adaptor.Cylinder().Axis().Direction()
                    n  = (ax.X(), ax.Y(), ax.Z())
                    if _mag(n) > 1e-6:
                        nn = _norm(n)
                        if abs(nn[2]) < 0.9:
                            # Non-vertical: both ± axes contribute to scoring
                            result.append((nn,       area_mm2, face_idx))
                            result.append((_neg(nn), area_mm2, face_idx))
                            logger.debug(
                                f"  Cylinder face {face_idx}: axis={_fv(nn)}, "
                                f"area={area_mm2:.0f} mm² (non-vertical, scored)"
                            )
                        else:
                            # Vertical pocket wall / fillet — omit from face_normals.
                            # These faces will be assigned post-hoc by neighbor
                            # majority vote in _hemisphere_set_cover so they're
                            # counted in the correct fixturing without influencing
                            # set-cover direction selection.
                            passive_face_idxs.add(face_idx)
                            logger.debug(
                                f"  Cylinder face {face_idx}: axis={_fv(nn)}, "
                                f"area={area_mm2:.0f} mm² (vertical, passive post-assign)"
                            )
                except Exception:
                    pass

        elif stype == GeomAbs.GeomAbs_Cone:
            if face_idx not in skip_axis_idxs:
                try:
                    ax = adaptor.Cone().Axis().Direction()
                    n  = (ax.X(), ax.Y(), ax.Z())
                    if _mag(n) > 1e-6:
                        nn = _norm(n)
                        if abs(nn[2]) < 0.9:
                            result.append((nn,       area_mm2, face_idx))
                            result.append((_neg(nn), area_mm2, face_idx))
                            logger.debug(
                                f"  Cone face {face_idx}: axis={_fv(nn)}, "
                                f"area={area_mm2:.0f} mm² (non-vertical, scored)"
                            )
                        else:
                            passive_face_idxs.add(face_idx)
                            logger.debug(
                                f"  Cone face {face_idx}: axis={_fv(nn)}, "
                                f"area={area_mm2:.0f} mm² (vertical, passive post-assign)"
                            )
                except Exception:
                    pass

        # Spheres and tori excluded — no single meaningful machining axis

        face_idx += 1
        exp.Next()

    logger.debug(
        f"  Face normals: {len(result)} samples from {face_idx} total faces "
        f"({len(hole_face_idxs)} hole-wall, {len(fillet_face_idxs)} convex-fillet faces excluded from axis sampling)"
    )

    # Build face adjacency from the pipeline's edge_to_faces map (already
    # correctly built with orientation-normalized edges). This is face_idx →
    # set of adjacent face_idxs sharing at least one edge.
    adjacency = {i: set() for i in range(face_idx)}
    if edge_to_faces:
        for edge_faces in edge_to_faces.values():
            for a in edge_faces:
                for b in edge_faces:
                    if a != b:
                        adjacency[a].add(b)
    else:
        # Fallback: rebuild using orientation-normalized edges (same logic as
        # build_face_adjacency in utils/geometry.py)
        try:
            from OCC.Core.TopTools import TopTools_IndexedMapOfShape
            from OCC.Core.TopAbs   import TopAbs_EDGE as _EDGE, TopAbs_FORWARD
            from OCC.Core.TopoDS   import topods as _topods

            def _fwd(e): return e.Oriented(TopAbs_FORWARD)

            edge_map = TopTools_IndexedMapOfShape()
            exp_all  = TopExp_Explorer(shape, _EDGE)
            while exp_all.More():
                edge_map.Add(_fwd(_topods.Edge(exp_all.Current())))
                exp_all.Next()

            edge_to_fi = {}
            fi = 0
            exp_f = TopExp_Explorer(shape, TopAbs_FACE)
            while exp_f.More():
                exp_e = TopExp_Explorer(exp_f.Current(), _EDGE)
                while exp_e.More():
                    e_idx = edge_map.FindIndex(_fwd(_topods.Edge(exp_e.Current())))
                    if e_idx > 0:
                        edge_to_fi.setdefault(e_idx, []).append(fi)
                    exp_e.Next()
                fi += 1
                exp_f.Next()

            for fi_list in edge_to_fi.values():
                for a in fi_list:
                    for b in fi_list:
                        if a != b:
                            adjacency[a].add(b)
        except Exception:
            pass

    excluded_counts = {
        "hole_wall":    len(hole_face_idxs),
        "convex_fillet": len(fillet_face_idxs),
        "passive":      len(passive_face_idxs),
    }

    return result, adjacency, passive_face_idxs, has_freeform, excluded_counts


# ---------------------------------------------------------------------------
# STEP 2 — HEMISPHERE SET-COVER
# ---------------------------------------------------------------------------

def _hemisphere_set_cover(face_normals, hole_profiles, pockets, face_adjacency=None, passive_face_idxs=None):
    """
    Find the minimum set of approach directions that covers every face normal
    and machining direction using a greedy weighted hemisphere set-cover.

    A face normal N is COVERED by approach direction A if dot(N,A) >= -TOL.
    TOL=0.05 means walls at ≤93° from the approach are considered reachable
    by side-milling — they do not require a dedicated fixturing direction.

    This correctly handles:
      Floor (normal=+Z, approach=+Z): dot=1.0 → covered ✓
      Wall  (normal=+X, approach=+Z): dot=0.0 → covered ✓ (side-milled)
      Angled surface 45° (normal=(0.7,0,0.7), approach=+Z): dot=0.7 → covered ✓
      True undercut (normal points away): dot<-0.05 → needs own fixturing ✗

    Candidate approach directions:
      1. Principal axes (+X/-X/+Y/-Y/+Z/-Z) — preferred; tried at each step
      2. Face normals — optimal greedy pick always lies near input normals
      3. Hole/pocket axes — ensure these drive fixturings when needed

    Greedy algorithm:
      1. Pick candidate covering the highest total area of uncovered faces
      2. Mark those faces covered, add approach to fixturings
      3. Repeat until all faces covered

    Returns list of cluster dicts compatible with _build_fixturing:
        centroid   : (nx, ny, nz)  — chosen approach direction
        members    : list[(direction, source_type, feature_idx)]
        spread_deg : float
    """
    # Coverage thresholds by source type.
    FACE_COVER_MIN   = -0.05   # walls (dot=0) reachable by side-milling
    # Derive from critical concern thresholds in config — a hole/pocket beyond
    # its critical angle needs its OWN fixturing, not a warning in an existing one.
    # Previously hardcoded at 0.90 (26°) and 0.50 (60°), which contradicted
    # SETUP_HOLE_CRITICAL_DEG=15° and SETUP_POCKET_CRITICAL_DEG=35°.
    HOLE_COVER_MIN   = math.cos(math.radians(SETUP_HOLE_CRITICAL_DEG))    # cos(15°)≈0.966
    POCKET_COVER_MIN = math.cos(math.radians(SETUP_POCKET_CRITICAL_DEG))  # cos(35°)≈0.819

    def _face_covered(dot):        return dot >= FACE_COVER_MIN
    def _pocket_covered(dot):      return dot >= POCKET_COVER_MIN
    # Through holes: abs(dot) — either end is a valid drill approach.
    # Blind holes: signed dot only — approach_direction is the open end only.
    def _hole_covered(dot, through): return (abs(dot) if through else dot) >= HOLE_COVER_MIN

    def _item_covered(dot, src, through=True):
        if src == "hole":   return _hole_covered(dot, through)
        if src == "pocket": return _pocket_covered(dot)
        return _face_covered(dot)

    # --- Build candidates ---
    candidates = [ax for _, ax in _PRINCIPAL_AXES]
    for n, _, _ in face_normals:
        candidates.append(n)

    for hp in hole_profiles:
        # Use approach_direction (set by classify_through_blind) which correctly
        # points FROM the exterior INTO the hole — the actual drill approach.
        # Falls back to axis_direction for profiles that haven't been classified yet.
        d = hp.get('approach_direction') or hp['axis_direction']
        if _mag(d) > 1e-6:
            candidates.append(_norm(d))

    for p in pockets:
        d = p['access_direction']
        if _mag(d) > 1e-6:
            candidates.append(_norm(d))

    # Deduplicate candidates within 2°
    unique_cands = []
    for c in candidates:
        if all(_angle_deg(c, u) > 2.0 for u in unique_cands):
            unique_cands.append(c)
    candidates = unique_cands

    # -----------------------------------------------------------------------
    # PHASE 1 — set-cover driven by holes and pockets only.
    # Face normals score candidates (dot×area weighting) but are not items
    # that need covering. This prevents wall faces (dot=0 with +Z) from
    # forcing their own fixturings — walls are always side-millable from an
    # adjacent setup. Only genuine machining operations (holes, pockets) drive
    # the fixturing count in this phase.
    # -----------------------------------------------------------------------
    machining_items = []
    for i, hp in enumerate(hole_profiles):
        d = hp.get('approach_direction') or hp['axis_direction']
        if _mag(d) < 1e-6:
            continue
        # is_through=True → abs(dot) (either drill end valid).
        # is_directional_through overrides: counterbore/countersink must approach
        # from the entry side only → treat as directional (signed dot).
        is_through = hp.get('is_through', True) and not hp.get('is_directional_through', False)
        machining_items.append((_norm(d), "hole", i, 1.0, is_through))
    for i, p in enumerate(pockets):
        d = p['access_direction']
        if _mag(d) > 1e-6:
            machining_items.append((_norm(d), "pocket", i, 1.0, None))

    covered      = [False] * len(machining_items)
    approach_dirs = []

    # Seed the first approach with the principal axis whose two faces together
    # have the most area. Sum both ± directions so +Z vs -Z don't compete —
    # then always pick the positive direction by convention so the output is
    # predictable (+Z, not -Z, for a flat part sitting on its bottom face).
    if face_normals:
        axis_score = {}
        for label, ax in _PRINCIPAL_AXES:
            axis = label[-1]   # 'X', 'Y', or 'Z'
            score = sum(abs(n[0]*ax[0]+n[1]*ax[1]+n[2]*ax[2]) * a
                        for n, a, _ in face_normals)
            axis_score[axis] = max(axis_score.get(axis, 0.0), score)

        dominant_axis = max(axis_score, key=axis_score.get)
        # Pick positive direction of dominant axis
        best_axis = next(ax for label, ax in _PRINCIPAL_AXES
                         if label == f"+{dominant_axis}")

        approach_dirs.append(best_axis)
        for k, (n, src, fi, w, through) in enumerate(machining_items):
            dot = n[0]*best_axis[0] + n[1]*best_axis[1] + n[2]*best_axis[2]
            if _item_covered(dot, src, through):
                covered[k] = True
        logger.debug(
            f"  Set-cover seed: dominant axis={dominant_axis}, "
            f"approach={_fv(best_axis)}, score={axis_score[dominant_axis]:.0f} mm²"
        )

    while not all(covered):
        best_cand    = None
        best_indices = []
        best_weight  = -1.0

        for cand in candidates:
            idxs   = []
            weight = 0.0

            # Score by face dot×area — prefer approaches aligned with real faces
            for n, area, _ in face_normals:
                dot = n[0]*cand[0] + n[1]*cand[1] + n[2]*cand[2]
                weight += max(0.0, dot) * area

            # Count uncovered machining items this candidate would cover
            for k, (n, src, fi, w, through) in enumerate(machining_items):
                if not covered[k]:
                    dot = n[0]*cand[0] + n[1]*cand[1] + n[2]*cand[2]
                    if _item_covered(dot, src, through):
                        idxs.append(k)

            # Must cover at least one machining item to be considered
            if idxs and weight > best_weight:
                best_weight  = weight
                best_cand    = cand
                best_indices = idxs

        if best_cand is None:
            # Remaining holes/pockets uncoverable from any candidate
            # (shouldn't happen — hole axes are candidates)
            break

        for k in best_indices:
            covered[k] = True
        approach_dirs.append(best_cand)

        logger.debug(
            f"  Set-cover phase 1: approach={_fv(best_cand)}, "
            f"covers {len(best_indices)} machining items, "
            f"face_weight={best_weight:.0f} mm²"
        )

    # If no holes or pockets, seed with the face-dominant approach
    if not approach_dirs and face_normals:
        best_cand   = None
        best_weight = -1.0
        for cand in candidates:
            weight = sum(max(0.0, n[0]*cand[0]+n[1]*cand[1]+n[2]*cand[2]) * a
                         for n, a, _ in face_normals)
            if weight > best_weight:
                best_weight = weight
                best_cand   = cand
        if best_cand:
            approach_dirs.append(best_cand)
            logger.debug(
                f"  Set-cover phase 1: no machining items — "
                f"seeded with face-dominant approach={_fv(best_cand)}"
            )

    # -----------------------------------------------------------------------
    # PHASE 2 — add fixturings for faces genuinely inaccessible from all
    # current approach directions (e.g. bottom face, undercut faces).
    # Walls (dot ≈ 0) are already side-millable — skip them.
    # Special rule: a face whose normal aligns with a principal axis (e.g.
    # bottom face with normal -Z) must be covered by a *principal* fixturing,
    # not a non-principal one that happens to have dot > -0.05. A machinist
    # would never tilt a part 45° just to reach a flat bottom face.
    # -----------------------------------------------------------------------
    for n, area, fi in face_normals:
        # For principal-axis faces, only count coverage from principal approaches
        is_principal_face = any(
            _angle_deg(n, ax) < SETUP_PRINCIPAL_AXIS_TOL_DEG
            for _, ax in _PRINCIPAL_AXES
        )
        if is_principal_face:
            relevant_dirs = [a for a in approach_dirs
                             if _nearest_principal_axis(a) is not None]
        else:
            relevant_dirs = approach_dirs

        best_dot = max(
            (n[0]*a[0] + n[1]*a[1] + n[2]*a[2] for a in relevant_dirs),
            default=-float('inf')
        )
        if not _face_covered(best_dot):
            # This face is not reachable from any relevant approach — find
            # the best candidate to cover it and add a new fixturing.
            # For principal-axis faces, prefer a principal-axis candidate.
            best_cand   = None
            best_weight = -1.0
            cand_pool   = candidates
            if is_principal_face:
                principal_cands = [c for c in candidates
                                   if _nearest_principal_axis(c) is not None]
                if principal_cands:
                    cand_pool = principal_cands
            for cand in cand_pool:
                dot = n[0]*cand[0] + n[1]*cand[1] + n[2]*cand[2]
                if _face_covered(dot):
                    w = sum(
                        max(0.0, n2[0]*cand[0]+n2[1]*cand[1]+n2[2]*cand[2]) * a2
                        for n2, a2, _ in face_normals
                        if max((n2[0]*ad[0]+n2[1]*ad[1]+n2[2]*ad[2]
                                for ad in approach_dirs), default=-1) < FACE_COVER_MIN
                    )
                    if w > best_weight:
                        best_weight = w
                        best_cand   = cand
            if best_cand and not any(_angle_deg(best_cand, a) < 5.0
                                     for a in approach_dirs):
                approach_dirs.append(best_cand)
                logger.debug(
                    f"  Set-cover phase 2: face {fi} inaccessible "
                    f"(best_dot={best_dot:.3f}) → adding approach={_fv(best_cand)}"
                )

    # -----------------------------------------------------------------------
    # ASSIGN items to fixturings
    # -----------------------------------------------------------------------
    all_items = list(machining_items)
    for n, area, fi in face_normals:
        all_items.append((n, "face", fi, area, None))

    clusters = [{'centroid': a, 'members': []} for a in approach_dirs]

    # Pre-classify clusters as principal or non-principal for assignment priority
    principal_clusters     = [c for c in clusters
                               if _nearest_principal_axis(c['centroid']) is not None]
    non_principal_clusters = [c for c in clusters
                               if _nearest_principal_axis(c['centroid']) is None]

    for n, src, fi, _, through in all_items:
        best_c   = None
        best_dot = -float('inf')

        if src == "face":
            # Faces: prefer principal fixturings for walls and flat faces, since
            # a wall (dot=0 with +Z) belongs to +Z via side-milling, not to a
            # 45° fixturing that sees it at 0.707.
            # Exception: if a non-principal cluster fits significantly better
            # (e.g. an angled face at dot=1.0 vs a principal at dot=0.707),
            # assign to the non-principal — it genuinely belongs there.
            best_principal_dot = -float('inf')
            best_principal_c   = None
            for c in principal_clusters:
                dot = n[0]*c['centroid'][0] + n[1]*c['centroid'][1] + n[2]*c['centroid'][2]
                if _face_covered(dot) and dot > best_principal_dot:
                    best_principal_dot = dot
                    best_principal_c   = c

            best_nonprincipal_dot = -float('inf')
            best_nonprincipal_c   = None
            for c in non_principal_clusters:
                dot = n[0]*c['centroid'][0] + n[1]*c['centroid'][1] + n[2]*c['centroid'][2]
                if _face_covered(dot) and dot > best_nonprincipal_dot:
                    best_nonprincipal_dot = dot
                    best_nonprincipal_c   = c

            # Use non-principal only if it's a near-perfect fit (dot >= 0.9,
            # meaning the face normal closely aligns with the special fixture
            # approach direction) AND the principal fit is meaningfully worse.
            # This catches angled faces like chamfers that genuinely belong to a
            # special fixture, while keeping walls (dot=0.707 with 45° cluster)
            # in the principal fixturing where a machinist would side-mill them.
            if (best_nonprincipal_c is not None and
                    best_nonprincipal_dot >= 0.9 and
                    best_nonprincipal_dot > best_principal_dot + 0.2):
                best_c   = best_nonprincipal_c
                best_dot = best_nonprincipal_dot
            elif best_principal_c is not None:
                best_c   = best_principal_c
                best_dot = best_principal_dot
            else:
                best_c   = best_nonprincipal_c
                best_dot = best_nonprincipal_dot
        else:
            # Holes and pockets: assign to best-covering fixturing regardless
            for c in clusters:
                dot = n[0]*c['centroid'][0] + n[1]*c['centroid'][1] + n[2]*c['centroid'][2]
                if _item_covered(dot, src, through) and dot > best_dot:
                    best_dot = dot
                    best_c   = c

        if best_c is not None:
            existing = next((m for m in best_c['members']
                             if m[1] == src and m[2] == fi), None)
            if existing is None:
                # For holes and pockets, ensure the stored direction agrees with
                # the cluster centroid — OCC axis signs are arbitrary and an
                # antiparallel direction would produce a spurious 180° concern.
                store_n = n
                if src in ('hole', 'pocket') and _mag(n) > 1e-6:
                    if (n[0]*best_c['centroid'][0] + n[1]*best_c['centroid'][1]
                            + n[2]*best_c['centroid'][2]) < 0:
                        store_n = _neg(n)
                best_c['members'].append((store_n, src, fi))

    # Remove empty clusters, compute spread
    clusters = [c for c in clusters if c['members']]

    # Post-assign passive faces (vertical cylinders, cones) by neighbor majority.
    # These faces were excluded from face_normals entirely — they don't influence
    # set-cover direction selection. Now assign each one to whichever cluster
    # contains the most of its topologically adjacent faces.
    # A pocket wall is always adjacent to the pocket floor; the floor is already
    # assigned to the correct fixturing, so the wall follows it unambiguously.
    if passive_face_idxs and face_adjacency and clusters:
        # Build fi → cluster for all already-assigned faces (the anchors)
        fi_to_cluster = {}
        for c in clusters:
            for _, src, fi in c['members']:
                fi_to_cluster[fi] = c

        for fi in passive_face_idxs:
            neighbors = face_adjacency.get(fi, set())
            votes = {}
            for nb_fi in neighbors:
                nb_c = fi_to_cluster.get(nb_fi)
                if nb_c is not None:
                    votes[id(nb_c)] = votes.get(id(nb_c), 0) + 1

            if votes:
                winner_id = max(votes, key=votes.__getitem__)
                winner    = next(c for c in clusters if id(c) == winner_id)
                # Use a dummy normal — this face has no directional constraint
                winner['members'].append(((0.0, 0.0, 0.0), 'face', fi))
                fi_to_cluster[fi] = winner
                logger.debug(
                    f"  Passive face {fi} → cluster {_fv(winner['centroid'])} "
                    f"(neighbor votes: {votes})"
                )
            else:
                # No adjacent anchors — fall back to first (principal) cluster
                clusters[0]['members'].append(((0.0, 0.0, 0.0), 'face', fi))
                logger.debug(
                    f"  Passive face {fi} → cluster {_fv(clusters[0]['centroid'])} "
                    f"(no neighbors, default to principal)"
                )

    clusters = [c for c in clusters if c['members']]
    for c in clusters:
        non_zero = [m for m in c['members'] if _mag(m[0]) > 1e-6]
        c['spread_deg'] = max((_angle_deg(m[0], c['centroid']) for m in non_zero), default=0.0)
        src_counts = {}
        for _, src, _ in c['members']:
            src_counts[src] = src_counts.get(src, 0) + 1
        logger.debug(
            f"  Cluster: centroid={_fv(c['centroid'])}, "
            f"n={len(c['members'])}, spread={c['spread_deg']:.1f}°, "
            f"sources={src_counts}"
        )

    # Sort fixturings using greedy coverage: the first fixture is the one that
    # can machine the most total faces (scored + passive). Passive faces belong
    # to whichever cluster they were assigned to, so a -Z pocket's walls and
    # fillets count toward -Z coverage, not +Z.
    #
    # For scored faces: accessible from approach A if dot(normal, A) >= FACE_COVER_MIN
    # For passive faces: accessible from approach A if they were assigned to A's cluster
    #
    # After fixture 1 is chosen, its accessible faces are removed and we count
    # again for fixture 2 — ensuring each fixture only gets credit for faces
    # not already covered by a prior setup.

    # Build passive face → cluster mapping from member list
    passive_to_cluster = {}
    if passive_face_idxs:
        for c in clusters:
            for _, src, fi in c['members']:
                if fi in passive_face_idxs:
                    passive_to_cluster[fi] = c

    def _total_accessible(approach, exclude_fi=None):
        """Count all faces accessible from approach, excluding already-counted ones."""
        exclude_fi = exclude_fi or set()
        count = 0
        seen = set()
        # Scored faces: accessible if dot >= FACE_COVER_MIN
        for n, area, fi in face_normals:
            if fi in exclude_fi or fi in seen:
                continue
            seen.add(fi)
            dot = n[0]*approach[0] + n[1]*approach[1] + n[2]*approach[2]
            if dot >= FACE_COVER_MIN:
                count += 1
        # Passive faces (vertical pocket walls, fillets): these are side-milled
        # and accessible from any approach direction — count them for all
        # approaches so symmetric parts tie correctly and principal-axis
        # tiebreak (not cluster assignment) determines fixture order.
        for fi in (passive_face_idxs or set()):
            if fi not in exclude_fi:
                count += 1
        return count

    # Build a principal axis priority lookup: lower index = higher priority.
    # +Z=0, -Z=1, +X=2, -X=3, +Y=4, -Y=5, non-principal=6
    # Used as tiebreak when two fixturings cover the same number of faces.
    _axis_priority = {}
    for i, (_, ax) in enumerate(_PRINCIPAL_AXES):
        _axis_priority[ax] = i

    def _fixture_sort_key(c, exclude_fi):
        coverage = _total_accessible(c['centroid'], exclude_fi)
        priority = _axis_priority.get(c['centroid'], 6)
        return (coverage, -priority)  # higher coverage first, lower priority index first

    # Greedy sort: pick highest coverage first, then remove those faces and repeat
    ordered    = []
    covered_fi = set()
    remaining  = list(clusters)

    while remaining:
        best   = max(remaining, key=lambda c: _fixture_sort_key(c, covered_fi))
        ordered.append(best)
        remaining.remove(best)
        # Mark all faces accessible from this approach as covered
        for n, area, fi in face_normals:
            dot = n[0]*best['centroid'][0] + n[1]*best['centroid'][1] + n[2]*best['centroid'][2]
            if dot >= FACE_COVER_MIN:
                covered_fi.add(fi)
        # Passive faces are side-millable from any approach — mark them covered
        # after the first fixture claims them so fixture 2 doesn't double-count.
        for fi in (passive_face_idxs or set()):
            covered_fi.add(fi)

    clusters = ordered

    # Post-sort reassignment: a face accessible from multiple fixturings should
    # belong to the FIRST (highest-priority) fixturing that can reach it.
    # Side walls (dot=0) are equally accessible from +Z and -Z — after sorting
    # puts -Z first, walls should move to -Z so the feature count reflects reality.
    for i, c in enumerate(clusters):
        for j, earlier in enumerate(clusters):
            if j >= i:
                break
            # Move members of cluster i to earlier if earlier can also access them
            stay   = []
            move   = []
            for entry in c['members']:
                n, src, fi = entry
                if src in ('hole', 'pocket'):
                    # Holes and pockets must stay in their assigned fixturing —
                    # they require a specific approach direction to drill/machine.
                    # Moving them to an earlier fixture would generate false
                    # 90° off-approach concerns.
                    stay.append(entry)
                elif _mag(n) < 1e-6:
                    # Passive face (vertical wall/fillet) — side-millable from
                    # any approach, so always belongs to the earliest fixture.
                    move.append(entry)
                else:
                    dot = n[0]*earlier['centroid'][0] + n[1]*earlier['centroid'][1] + n[2]*earlier['centroid'][2]
                    if dot >= FACE_COVER_MIN:
                        move.append(entry)
                    else:
                        stay.append(entry)
            for entry in move:
                n, src, fi = entry
                if not any(f == fi and s == src for _, s, f in earlier['members']):
                    earlier['members'].append(entry)
            c['members'] = stay

    # Recompute spread after reassignment
    clusters = [c for c in clusters if c['members']]
    for c in clusters:
        non_zero = [m for m in c['members'] if _mag(m[0]) > 1e-6]
        c['spread_deg'] = max((_angle_deg(m[0], c['centroid']) for m in non_zero), default=0.0)

    return clusters


# ---------------------------------------------------------------------------
# STEP 3 — NON-PRINCIPAL FACE QUALITY ADVISORY
# ---------------------------------------------------------------------------

def _flag_large_non_principal_faces(face_normals, clusters):
    """
    For each non-principal fixturing, check whether large-area faces are
    driving it. Large non-principal faces may need a dedicated fixture for
    face-milling quality even though the hemisphere set-cover considers them
    accessible from an adjacent setup.

    Returns list of advisory strings added to the fixturing record.
    This does NOT add fixturings — it annotates existing ones.
    Without GD&T data this is a heuristic. These are flagged as advisories,
    not warnings, since a shop may accept ball-nose finish on these faces.
    """
    LARGE_FACE_MM2  = 500.0
    MIN_TOTAL_MM2   = 1000.0
    FACE_COVER_MIN  = -0.05

    advisories = {}   # cluster centroid tuple → advisory string

    for c in clusters:
        approach = c['centroid']
        if _nearest_principal_axis(approach) is not None:
            continue  # principal — no advisory needed

        # Find large faces exclusively served by this non-principal approach —
        # i.e. not covered by any principal-axis fixturing.
        # A wall (dot=0 with +Z) is covered by +Z, so it doesn't count here
        # even if the 45° fixturing also sees it at 0.707.
        large_faces = []
        for n, area, fi in face_normals:
            dot = n[0]*approach[0] + n[1]*approach[1] + n[2]*approach[2]
            if dot < FACE_COVER_MIN:
                continue
            # Skip if any principal fixturing covers this face
            covered_by_principal = any(
                n[0]*other_c['centroid'][0] + n[1]*other_c['centroid'][1] + n[2]*other_c['centroid'][2] >= FACE_COVER_MIN
                for other_c in clusters
                if _nearest_principal_axis(other_c['centroid']) is not None
            )
            if covered_by_principal:
                continue
            if area >= LARGE_FACE_MM2:
                large_faces.append((fi, area))

        total_area = sum(a for _, a in large_faces)
        if total_area >= MIN_TOTAL_MM2:
            angle = min(
                min(_angle_deg(approach, ax), 180.0 - _angle_deg(approach, ax))
                for _, ax in _PRINCIPAL_AXES
            )
            advisories[approach] = (
                f"{len(large_faces)} large face(s) totalling {total_area:.0f} mm² "
                f"at {angle:.1f}° from principal axis — may need dedicated "
                f"fixture for face-milling finish (no GD&T available to confirm)"
            )

    return advisories


# ---------------------------------------------------------------------------
# STEP 4 — FREEFORM FACE DETECTION
# ---------------------------------------------------------------------------

def _find_freeform_faces(shape):
    """
    Return dict[face_idx → TopoDS_Face] for all non-analytic faces.

    Planes, cylinders, cones, spheres, and tori are analytic — a fixed
    spindle can always reach them with standard 3-axis motion. BSpline,
    Bezier, and other freeform surfaces may or may not require continuous
    tilting depending on whether their normals undercut the approach axis.
    We collect them here and evaluate them per-fixturing in
    _upgrade_freeform_to_continuous.
    """
    freeform_types = {
        GeomAbs.GeomAbs_BSplineSurface,
        GeomAbs.GeomAbs_BezierSurface,
        GeomAbs.GeomAbs_SurfaceOfRevolution,
        GeomAbs.GeomAbs_SurfaceOfExtrusion,
        GeomAbs.GeomAbs_OffsetSurface,
        GeomAbs.GeomAbs_OtherSurface,
    }
    result   = {}
    exp      = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx = 0
    while exp.More():
        face = topods.Face(exp.Current())
        adaptor = BRepAdaptor_Surface(face)
        stype   = adaptor.GetType()
        if stype in freeform_types:
            result[face_idx] = face

            # Sample normals for debug reporting
            type_name = {
                GeomAbs.GeomAbs_BSplineSurface:      "BSplineSurface",
                GeomAbs.GeomAbs_BezierSurface:       "BezierSurface",
                GeomAbs.GeomAbs_SurfaceOfRevolution: "SurfaceOfRevolution",
                GeomAbs.GeomAbs_SurfaceOfExtrusion:  "SurfaceOfExtrusion",
                GeomAbs.GeomAbs_OffsetSurface:       "OffsetSurface",
                GeomAbs.GeomAbs_OtherSurface:        "OtherSurface",
            }.get(stype, f"Unknown({stype})")

            normals  = _sample_face_normals(face, n_samples=8)
            if normals:
                min_nz   = min(nz for nx, ny, nz in normals)
                max_nz   = max(nz for nx, ny, nz in normals)
                avg_nz   = sum(nz for nx, ny, nz in normals) / len(normals)
                min_dot_z = min_nz   # dot with (0,0,1)
                logger.debug(
                    f"  Freeform face {face_idx}: type={type_name}, "
                    f"n_normals={len(normals)}, "
                    f"nz_range=[{min_nz:.3f}, {max_nz:.3f}], avg_nz={avg_nz:.3f} "
                    f"(negative nz = undercut from +Z)"
                )
            else:
                logger.debug(
                    f"  Freeform face {face_idx}: type={type_name}, "
                    f"could not sample normals"
                )

        face_idx += 1
        exp.Next()
    return result


def _sample_face_normals(face, n_samples=6):
    """
    Sample surface normals across a face on an n×n UV grid.
    Returns a list of (nx, ny, nz) unit vectors. Skips degenerate points.
    """
    normals = []
    try:
        adaptor = BRepAdaptor_Surface(face)
        u0, u1  = adaptor.FirstUParameter(), adaptor.LastUParameter()
        v0, v1  = adaptor.FirstVParameter(), adaptor.LastVParameter()
        for i in range(n_samples):
            u = u0 + (u1 - u0) * (i + 0.5) / n_samples
            for j in range(n_samples):
                v = v0 + (v1 - v0) * (j + 0.5) / n_samples
                try:
                    p  = gp_Pnt()
                    du = gp_Vec()
                    dv = gp_Vec()
                    adaptor.D1(u, v, p, du, dv)
                    nx = du.Y() * dv.Z() - du.Z() * dv.Y()
                    ny = du.Z() * dv.X() - du.X() * dv.Z()
                    nz = du.X() * dv.Y() - du.Y() * dv.X()
                    mag = math.sqrt(nx*nx + ny*ny + nz*nz)
                    if mag > 1e-10:
                        normals.append((nx/mag, ny/mag, nz/mag))
                except Exception:
                    continue
    except Exception:
        pass
    return normals


def _upgrade_freeform_to_continuous(fixturings, freeform_faces):
    """
    Upgrade fixturings to 5-axis-continuous where freeform faces require it.

    For each freeform face, finds the single fixturing whose approach direction
    best aligns with that face's sampled normals — that's the fixturing which
    would naturally machine this surface. Only that fixturing is checked for
    the continuous requirement.

    Using centroid position as a visibility proxy is unreliable: a 45° fixturing
    that exists only for a drilled hole could have a positive centroid dot with
    a dome on the top face, causing a false upgrade. Best-normal-alignment
    assigns each face to exactly one fixturing based on geometry, not position.

    A face requires continuous tilting if even its best-aligned fixturing has
    any sampled normal with dot < -0.1 against that approach direction. The
    -0.1 tolerance avoids false positives from vertical walls (dot ≈ 0).

    Mutates fixturings in place.
    """
    if not freeform_faces:
        return

    # Pre-compute normalised approach vectors for each fixturing
    approach_vecs = {}
    for f in fixturings:
        approach_axis = f.get('approach_axis')
        if approach_axis is not None:
            av = dict(_PRINCIPAL_AXES)[approach_axis]
        else:
            av = f['_cluster_centroid']
        ax, ay, az = av
        mag = math.sqrt(ax*ax + ay*ay + az*az)
        if mag > 1e-6:
            approach_vecs[f['fixturing_idx']] = (ax/mag, ay/mag, az/mag)

    if not approach_vecs:
        return

    for face_idx, face in freeform_faces.items():
        normals = _sample_face_normals(face)
        if not normals:
            continue

        # Find fixturing whose approach vector best aligns with this face's normals.
        # "Best" = highest average dot product across all sampled normals.
        # This is the fixturing that would naturally machine this surface.
        best_fixing_idx = None
        best_avg_dot    = -float('inf')

        for fix_idx, av in approach_vecs.items():
            avg_dot = sum(
                nx * av[0] + ny * av[1] + nz * av[2]
                for nx, ny, nz in normals
            ) / len(normals)
            if avg_dot > best_avg_dot:
                best_avg_dot    = avg_dot
                best_fixing_idx = fix_idx

        if best_fixing_idx is None:
            continue

        # A freeform face requires 5-axis-continuous only if its normals vary
        # in genuinely 3D fashion — i.e. the surface has curvature that causes
        # the tool to need to continuously reorient while cutting.
        #
        # Counter-examples that do NOT require 5-axis-continuous:
        #   - Spline pocket wall extruded vertically: normals all horizontal
        #     (nz ≈ 0), vary only in XY — reachable by 3-axis side-milling.
        #   - Tilted planar spline: normals all parallel — one fixed approach.
        #
        # 5-axis-continuous IS required when:
        #   - nz varies significantly (surface tilts in and out of horizontal)
        #     AND the normal direction also rotates in XY (not just a ruled surface)
        #   - In other words: significant angular spread AND not all normals
        #     coplanar (rank-3 normal distribution).
        #
        # We test: nz_range > NZ_THRESHOLD (surface tilts in Z) AND
        #          angular spread between any two normals > SPREAD_THRESHOLD.
        NZ_THRESHOLD     = 0.25   # nz must vary by at least this much
        SPREAD_THRESHOLD = 25.0   # degrees — normals must spread this far apart

        nz_vals = [nz for nx, ny, nz in normals]
        nz_range = max(nz_vals) - min(nz_vals)

        max_spread = 0.0
        for i in range(len(normals)):
            for j in range(i+1, len(normals)):
                ni, nj = normals[i], normals[j]
                dot = max(-1.0, min(1.0,
                    ni[0]*nj[0] + ni[1]*nj[1] + ni[2]*nj[2]))
                max_spread = max(max_spread, math.degrees(math.acos(dot)))

        needs_continuous = nz_range > NZ_THRESHOLD and max_spread > SPREAD_THRESHOLD

        logger.debug(
            f"  Freeform face {face_idx}: best fixturing={best_fixing_idx}, "
            f"avg_dot={best_avg_dot:.3f}, nz_range={nz_range:.3f}, "
            f"max_spread={max_spread:.1f}° → needs_continuous={needs_continuous}"
        )

        if needs_continuous:
            f = next(x for x in fixturings if x['fixturing_idx'] == best_fixing_idx)
            if f['setup_type'] != '5-axis-continuous':
                logger.debug(
                    f"  Fixturing {best_fixing_idx}: upgrading to 5-axis-continuous "
                    f"(freeform face {face_idx}: nz_range={nz_range:.3f}, "
                    f"spread={max_spread:.1f}°)"
                )
                f['setup_type']    = '5-axis-continuous'
                f['approach_axis'] = None


# ---------------------------------------------------------------------------
# STEP 5 — BUILD FIXTURING RECORD
# ---------------------------------------------------------------------------

def _build_fixturing(fixturing_idx, cluster_group,
                     planar_faces, hole_profiles, pockets):
    """
    Classify a fixturing and assign all features to it with concern levels.
    5-axis-continuous classification is applied separately by
    _upgrade_freeform_to_continuous after all fixturings are built.
    """

    # Classify setup type.
    # Each fixturing is always exactly one cluster (hemisphere grouping was
    # removed — see _group_into_fixturings). So the only question is whether
    # this cluster's centroid aligns with a principal axis.
    # 5-axis-continuous is assigned by _upgrade_freeform_to_continuous after
    # all fixturings are built, based on normal sampling — not here.
    n_clusters    = len(cluster_group)
    centroid      = cluster_group[0]['centroid']
    approach_axis = _nearest_principal_axis(centroid)

    if approach_axis is not None:
        setup_type = "3-axis-standard"
    else:
        setup_type    = "3-axis-special-fixture"
        approach_axis = None

    # Assign features — deduplicate by (source_type, feature_idx),
    # keeping the entry with smallest angular deviation.
    # Deviation is measured from the principal axis when one exists
    # (3-axis-standard), so the reported angle reflects true off-axis
    # deviation rather than deviation from a shifted cluster centroid.
    # For special fixtures (no principal axis), centroid is the correct
    # reference since that's the actual approach direction.
    if approach_axis is not None:
        reference_dir = dict(_PRINCIPAL_AXES)[approach_axis]
    else:
        reference_dir = cluster_group[0]['centroid']

    seen = {}  # (source_type, feature_idx) → assignment dict

    for c in cluster_group:
        for direction, source_type, feature_idx in c['members']:
            deviation             = _angle_deg(direction, reference_dir)
            concern_level, reason = _concern(source_type, feature_idx, deviation)
            key                   = (source_type, feature_idx)

            if key not in seen or deviation < seen[key]['angular_deviation_deg']:
                seen[key] = {
                    "feature_type":          source_type,
                    "feature_idx":           feature_idx,
                    "constraint_direction":  direction,
                    "angular_deviation_deg": round(deviation, 2),
                    "concern_level":         concern_level,
                    "concern_reason":        reason,
                }

    features = sorted(
        seen.values(),
        key=lambda a: (
            {"critical": 0, "warning": 1, "advisory": 2, None: 3}[a['concern_level']],
            a['feature_type'],
            a['feature_idx'],
        ),
    )

    concern_count = {"advisory": 0, "warning": 0, "critical": 0}
    for a in features:
        if a['concern_level']:
            concern_count[a['concern_level']] += 1

    return {
        "fixturing_idx":     fixturing_idx,
        "setup_type":        setup_type,
        "approach_axis":     approach_axis,
        "approach_vector":   centroid,
        "cluster_count":     n_clusters,
        "feature_count":     len(features),
        "features":          features,
        "concern_count":     concern_count,
        "_cluster_centroid": cluster_group[0]['centroid'],
    }


# ---------------------------------------------------------------------------
# CROSS-FIXTURING DEDUPLICATION
# ---------------------------------------------------------------------------

def _assign_fillets_to_fixturings(fillets, fixturings, edge_to_faces):
    """
    Post-assign every fillet/edge round to a fixturing based on axis alignment,
    with neighbor vote as a tiebreaker.

    The key insight: cylindrical faces (fillets, edge rounds) are machined by
    running the tool PARALLEL to the cylinder axis. So the correct fixturing is
    the one whose approach vector is most ALIGNED with the fillet axis
    (highest |dot product|), not perpendicular to it.

    Examples:
      - Fillet axis=(0,0,1): tool runs along Z → assign to +Z fixturing
      - Fillet axis=(0,-1,0): tool runs along Y → assign to -Y fixturing
      - Concave fillet axis=(1,0,0): tool runs along X → assign to whichever
        fixturing can traverse X (typically the principal +Z fixturing)

    If two fixturings are equally aligned (within 0.1), neighbor vote is used
    as tiebreaker.

    Mutates each fillet dict in place, adding:
        fixturing_idx             : int
        fixturing_approach_axis   : str | None
        fixturing_approach_vector : tuple
    """
    if not fillets or not fixturings:
        return

    # Build face_idx → fixturing_idx from assigned features (for tiebreaker)
    fi_to_fix = {}
    for fix in fixturings:
        for feat in fix.get('features', []):
            fi_to_fix[feat['feature_idx']] = fix['fixturing_idx']

    for flt in fillets:
        fi   = flt['face_idx']
        axis = flt.get('axis_direction')  # (x, y, z) tuple

        # --- Axis alignment score per fixturing ---
        # |dot(approach, fillet_axis)| — higher means tool can run along the axis
        axis_scores = {}
        if axis and any(abs(v) > 1e-6 for v in axis):
            ax, ay, az = axis
            mag = (ax*ax + ay*ay + az*az) ** 0.5
            if mag > 1e-6:
                ax, ay, az = ax/mag, ay/mag, az/mag
                for fix in fixturings:
                    vec = fix.get('approach_vector')
                    if vec:
                        vx, vy, vz = vec
                        vmag = (vx*vx + vy*vy + vz*vz) ** 0.5
                        if vmag > 1e-6:
                            dot = abs(ax*(vx/vmag) + ay*(vy/vmag) + az*(vz/vmag))
                            axis_scores[fix['fixturing_idx']] = round(dot, 4)

        # --- Neighbor vote (tiebreaker) ---
        neighbor_votes = {}
        for nb_fi in edge_to_faces.get(fi, set()):
            fix_idx = fi_to_fix.get(nb_fi)
            if fix_idx is not None:
                neighbor_votes[fix_idx] = neighbor_votes.get(fix_idx, 0) + 1

        # --- Pick winner ---
        if axis_scores:
            best_score = max(axis_scores.values())
            # All candidates within 0.1 of best alignment score
            candidates = [idx for idx, s in axis_scores.items()
                          if best_score - s < 0.1]
            if len(candidates) == 1:
                winner_idx = candidates[0]
            else:
                # Tiebreak by neighbor votes
                winner_idx = max(candidates,
                                 key=lambda idx: neighbor_votes.get(idx, 0))
        elif neighbor_votes:
            winner_idx = max(neighbor_votes, key=neighbor_votes.__getitem__)
        else:
            winner_idx = 0  # fallback to principal

        winner = fixturings[winner_idx]
        flt['fixturing_idx']             = winner_idx
        flt['fixturing_approach_axis']   = winner.get('approach_axis')
        flt['fixturing_approach_vector'] = winner.get('approach_vector')

        logger.debug(
            f"  Fillet face {fi} (type={flt['type']}, subtype={flt.get('subtype')}, "
            f"r={flt['radius_mm']:.2f}mm, axis={axis}) → fixturing {winner_idx} "
            f"(axis_scores={axis_scores}, neighbor_votes={neighbor_votes})"
        )


def _upgrade_special_to_indexed(fixturings):
    """
    Upgrade 3-axis-special-fixture fixturings to 5-axis-indexed where needed.

    Two rules, applied in order:

    1. NON-STANDARD ANGLE — if a special-fixture fixturing's cluster centroid
       is not within SETUP_STANDARD_FIXTURE_ANGLE_TOL_DEG of a standard stock
       fixture angle (30°, 45°, 60° from any principal axis), no common angle
       plate exists for it. A 5-axis-indexed machine is the practical solution.

    2. MULTIPLE SPECIAL FIXTURES — if after rule 1 there are still two or more
       3-axis-special-fixture fixturings, the operator would need multiple
       different angle blocks and re-clampings. A 5-axis-indexed machine is
       cheaper than that level of setup complexity. Upgrade all of them.

    Mutates fixturing dicts in place (setup_type only).
    """
    for f in fixturings:
        if f['setup_type'] != '3-axis-special-fixture':
            continue
        centroid = f['_cluster_centroid']
        if not _is_standard_fixture_angle(centroid):
            f['setup_type'] = '5-axis-indexed'

    # Rule 2: multiple remaining special-fixture setups → all go to indexed
    remaining_special = [
        f for f in fixturings
        if f['setup_type'] == '3-axis-special-fixture'
    ]
    if len(remaining_special) > 1:
        for f in remaining_special:
            f['setup_type'] = '5-axis-indexed'


def _is_standard_fixture_angle(direction):
    """
    Return True if the direction is within SETUP_STANDARD_FIXTURE_ANGLE_TOL_DEG
    of a standard stock fixture angle (30°, 45°, 60°) from any principal axis.

    These are the angles for which sine vises, angle plates, and standard
    tombstone fixtures are readily available off the shelf.
    """
    for _, axis in _PRINCIPAL_AXES:
        angle = _angle_deg(direction, axis)
        # angle_deg gives 0° for aligned, 90° for perpendicular, 180° for opposite.
        # Normalise to 0–90° range since fixtures work from either side.
        angle = min(angle, 180.0 - angle)
        for standard in SETUP_STANDARD_FIXTURE_ANGLES_DEG:
            if abs(angle - standard) <= SETUP_STANDARD_FIXTURE_ANGLE_TOL_DEG:
                return True
    return False


def _deduplicate_through_holes(fixturings, hole_profiles):
    """
    A through hole contributes both +axis and -axis directions, so it can
    appear in two fixturings. Remove it from all but the fixturing where
    its angular deviation is smallest — that's the natural approach side.

    Mutates the fixturings list in place, rebuilding feature lists and
    concern counts for any fixturing that loses features.
    """
    # Collect all fixturing assignments for each through hole
    # key: hole feature_idx → list of (fixturing_idx, deviation, feature_dict)
    hole_assignments = {}
    for f in fixturings:
        for feat in f['features']:
            if feat['feature_type'] != 'hole':
                continue
            idx = feat['feature_idx']
            if not hole_profiles[idx].get('is_through', False):
                continue
            if idx not in hole_assignments:
                hole_assignments[idx] = []
            hole_assignments[idx].append((f['fixturing_idx'], feat['angular_deviation_deg'], feat))

    # For each through hole that appears in more than one fixturing,
    # keep only the best (smallest deviation) assignment
    to_remove = {}  # fixturing_idx → set of hole feature_idxs to drop
    for hole_idx, assignments in hole_assignments.items():
        if len(assignments) <= 1:
            continue
        best_fixing_idx = min(assignments, key=lambda x: x[1])[0]
        for fixing_idx, _, _ in assignments:
            if fixing_idx != best_fixing_idx:
                to_remove.setdefault(fixing_idx, set()).add(hole_idx)

    if not to_remove:
        return

    # Rebuild affected fixturings
    for f in fixturings:
        drop = to_remove.get(f['fixturing_idx'])
        if not drop:
            continue
        f['features'] = [
            feat for feat in f['features']
            if not (feat['feature_type'] == 'hole' and feat['feature_idx'] in drop)
        ]
        f['feature_count'] = len(f['features'])
        concern_count = {"advisory": 0, "warning": 0, "critical": 0}
        for feat in f['features']:
            if feat['concern_level']:
                concern_count[feat['concern_level']] += 1
        f['concern_count'] = concern_count


# ---------------------------------------------------------------------------
# CONCERN LEVEL ASSIGNMENT
# ---------------------------------------------------------------------------

def _concern(source_type, feature_idx, deviation_deg):
    """
    Map angular deviation to a concern level for the given feature type.
    Returns (concern_level, reason_string) — level is None if no concern.

    Different feature types have different tolerances:
      holes   — tightest (drill/bore wants to be on-axis)
      pockets — moderate (floor finish and depth-of-cut degrade with angle)
      planar  — loosest  (face milling tolerates more angular deviation)
    """
    if source_type == "hole":
        adv, wrn, crit = (
            SETUP_HOLE_ADVISORY_DEG,
            SETUP_HOLE_WARNING_DEG,
            SETUP_HOLE_CRITICAL_DEG,
        )
        label  = f"hole {feature_idx}"
        detail = "drill/bore axis off approach — affects tool life and hole quality"

    elif source_type == "pocket":
        adv, wrn, crit = (
            SETUP_POCKET_ADVISORY_DEG,
            SETUP_POCKET_WARNING_DEG,
            SETUP_POCKET_CRITICAL_DEG,
        )
        label  = f"pocket {feature_idx}"
        detail = "pocket floor off perpendicular — affects floor finish and depth of cut"

    else:  # face — any face covered by this fixturing via hemisphere set-cover
        # 0°  = floor (tool perpendicular) — ideal
        # 90° = wall  (tool parallel, side-milled) — perfectly normal, no concern
        # >90° cannot happen — set-cover only assigns faces with dot >= -TOL
        # Concern only arises for faces in the awkward mid-range where neither
        # full face-milling nor clean side-milling applies well, e.g. 60-80°
        # from approach on a non-vertical angled surface with finish requirements.
        # Without GD&T we can't be definitive, so we don't flag faces at all —
        # the surface_quality_advisory on the fixturing handles that case.
        return None, None

    if deviation_deg >= crit:
        level = "critical"
    elif deviation_deg >= wrn:
        level = "warning"
    elif deviation_deg >= adv:
        level = "advisory"
    else:
        return None, None

    return level, f"{label}: {deviation_deg:.1f}° off approach — {detail}"


# ---------------------------------------------------------------------------
# PRINCIPAL AXIS SNAP
# ---------------------------------------------------------------------------

def _nearest_principal_axis(direction):
    """
    Return the label of the nearest principal axis (e.g. "+Z") if the
    direction is within SETUP_PRINCIPAL_AXIS_TOL_DEG of it, else None.
    """
    best_label, best_angle = None, float('inf')
    for label, axis in _PRINCIPAL_AXES:
        a = _angle_deg(direction, axis)
        if a < best_angle:
            best_angle = a
            best_label = label
    return best_label if best_angle <= SETUP_PRINCIPAL_AXIS_TOL_DEG else None


# ---------------------------------------------------------------------------
# VECTOR UTILITIES
# ---------------------------------------------------------------------------

def _dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def _mag(v):
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)

def _norm(v):
    m = _mag(v)
    return (v[0]/m, v[1]/m, v[2]/m) if m > 1e-10 else (0.0, 0.0, 1.0)

def _neg(v):
    return (-v[0], -v[1], -v[2])

def _angle_deg(a, b):
    return math.degrees(math.acos(max(-1.0, min(1.0, _dot(a, b)))))

def _fv(v):
    return f"({v[0]:.3f}, {v[1]:.3f}, {v[2]:.3f})"