# sourcing/analysis/tool_access.py
# Per-fixturing minimum tool diameter analysis.
#
# Three passes, all scoped to faces assigned to *this* fixturing only:
#
#   Fillet pass  — axis-aligned concave fillets constrain tool dia to ≤ 2r.
#                  Perpendicular concave fillets (ball-nose) also ≤ 2r but
#                  labelled separately.
#
#   Planar pass  — opposing planar wall pairs (normals perpendicular to
#                  approach). Gap = perpendicular distance between planes.
#
#   Ray cast pass — non-planar, non-hole-wall faces assigned to this
#                   fixturing. Projects outward normal onto approach-
#                   perpendicular plane → ray direction. First hit = gap.
#
# Holes excluded — their diameter directly implies drill/bore size.

import math
import logging

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_OUT
from OCC.Core.TopoDS import topods
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core import GeomAbs
from OCC.Core.gp import gp_Dir, gp_Vec, gp_Pnt, gp_Lin
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.IntCurvesFace import IntCurvesFace_ShapeIntersector

from sourcing.config import (
    TOOL_ACCESS_WALL_PERP_TOL,
    TOOL_ACCESS_MAX_GAP_MM,
    TOOL_ACCESS_SAMPLE_GRID,
    TOOL_ACCESS_ANTIPARALLEL_TOL,
    DFM_CONVEX_FILLET_AXIS_ALIGNED_TOL,
)

logger = logging.getLogger(__name__)


def analyze_tool_access(shape, setup_analysis, planar_faces, hole_profiles, fillets=None, face_list=None):
    """
    Compute the minimum tool diameter constraint for each fixturing.

    Returns list of per-fixturing dicts:
        fixturing_idx   : int
        approach_axis   : str | None
        approach_vector : tuple(3)
        min_tool_dia_mm : float | None
        constraints     : list sorted narrowest-first, each with:
            source      : 'fillet_radius' | 'fillet_radius_ballnose'
                        | 'planar_pair' | 'ray_cast'
            width_mm    : float
            face_idxs   : list[int]
            position_mm : tuple(3) | None
    """
    fillets        = fillets or []
    hole_face_idxs = {fi for hp in hole_profiles for fi in hp.get('face_idxs', [])}
    planar_by_idx  = {pf['face_idx']: pf for pf in planar_faces}

    intersector = IntCurvesFace_ShapeIntersector()
    intersector.Load(shape, 1e-6)
    max_dist_model = TOOL_ACCESS_MAX_GAP_MM / 1000.0

    results = []
    for fix in setup_analysis['fixturings']:
        approach     = fix['approach_vector']
        approach_vec = gp_Vec(*approach)
        fix_idx      = fix['fixturing_idx']

        # Face indices assigned to this fixturing
        assigned_face_idxs = {
            feat['feature_idx']
            for feat in fix['features']
            if feat['feature_type'] == 'face'
        }

        fix_planar  = [planar_by_idx[fi] for fi in assigned_face_idxs if fi in planar_by_idx]
        fix_fillets = [f for f in fillets if f.get('fixturing_idx') == fix_idx]

        constraints = []
        _fillet_pass(approach_vec, fix_fillets, constraints)
        _planar_pass(shape, approach_vec, fix_planar, constraints)
        _ray_cast_pass(shape, approach_vec, fix_planar, assigned_face_idxs,
                       hole_face_idxs, intersector, max_dist_model, constraints,
                       face_list=face_list)

        constraints.sort(key=lambda c: c['width_mm'])
        min_dia = constraints[0]['width_mm'] if constraints else None

        logger.info(
            f"  Fixturing {fix_idx} ({fix['approach_axis']}): "
            f"{len(constraints)} tool-access constraints, "
            f"min={f'{min_dia:.2f} mm' if min_dia is not None else 'none'}"
        )

        results.append({
            'fixturing_idx':   fix_idx,
            'approach_axis':   fix['approach_axis'],
            'approach_vector': approach,
            'min_tool_dia_mm': round(min_dia, 3) if min_dia is not None else None,
            'constraints':     constraints,
        })

    return results


# ---------------------------------------------------------------------------
# Pass A — fillet radius constraints
# ---------------------------------------------------------------------------

def _fillet_pass(approach_vec, fix_fillets, constraints):
    """
    Concave fillets constrain max tool diameter to 2r regardless of
    axis alignment — aligned fillets use a flat end mill, perpendicular
    fillets use a ball-nose, but both must fit the radius.
    """
    approach_mag = approach_vec.Magnitude()

    for flt in fix_fillets:
        if flt.get('type') != 'concave':
            continue

        r  = flt['radius_mm']
        ax = flt.get('axis_direction')
        if not ax:
            continue

        ax_vec = gp_Vec(*ax)
        ax_mag = ax_vec.Magnitude()
        if ax_mag < 1e-9:
            continue

        dot     = abs(ax_vec.Dot(approach_vec)) / (ax_mag * approach_mag) if approach_mag > 1e-9 else 0.0
        aligned = dot >= DFM_CONVEX_FILLET_AXIS_ALIGNED_TOL
        source  = 'fillet_radius' if aligned else 'fillet_radius_ballnose'
        width   = r * 2.0

        pos    = flt.get('sample_position_mm')
        pos_mm = (round(pos[0], 1), round(pos[1], 1), round(pos[2], 1)) if pos else None

        constraints.append({
            'source':      source,
            'width_mm':    round(width, 3),
            'face_idxs':   [flt['face_idx']],
            'position_mm': pos_mm,
        })
        logger.debug(
            f"    Fillet face {flt['face_idx']}: r={r:.2f} mm → "
            f"max tool dia = {width:.2f} mm ({source})"
        )


# ---------------------------------------------------------------------------
# Pass B — planar opposing wall pairs
# ---------------------------------------------------------------------------

def _planar_pass(shape, approach_vec, fix_planar, constraints):
    approach_mag = approach_vec.Magnitude()
    if approach_mag < 1e-9:
        return

    wall_faces = []
    for pf in fix_planar:
        nv  = gp_Vec(pf['_normal_dir'])
        dot = abs(nv.Dot(approach_vec)) / (nv.Magnitude() * approach_mag)
        if dot < TOOL_ACCESS_WALL_PERP_TOL:
            wall_faces.append(pf)

    logger.debug(
        f"  Planar pass: {len(wall_faces)}/{len(fix_planar)} assigned faces "
        f"are walls"
    )

    for i, fa in enumerate(wall_faces):
        nrm_a = fa['_normal_dir']
        cog_a = fa['_centroid']

        for fb in wall_faces[i + 1:]:
            nrm_b   = fb['_normal_dir']
            dot_nrm = gp_Vec(nrm_a).Dot(gp_Vec(nrm_b))
            if dot_nrm > -TOOL_ACCESS_ANTIPARALLEL_TOL:
                continue

            cog_b      = fb['_centroid']
            vec_ab     = gp_Vec(cog_a, cog_b)
            mag        = vec_ab.Magnitude()
            if mag < 1e-9:
                continue

            nrm_a_vec = gp_Vec(nrm_a)
            gap_mm    = abs(vec_ab.Dot(nrm_a_vec)) / nrm_a_vec.Magnitude() * 1000.0
            if gap_mm < 1e-3 or gap_mm > TOOL_ACCESS_MAX_GAP_MM:
                continue

            mid_mm = (
                round((cog_a.X() + cog_b.X()) / 2 * 1000, 1),
                round((cog_a.Y() + cog_b.Y()) / 2 * 1000, 1),
                round((cog_a.Z() + cog_b.Z()) / 2 * 1000, 1),
            )

            # Verify the midpoint between the two faces is void, not solid.
            # A pair whose midpoint is inside the solid means the gap passes
            # through material — not a real tool-access channel.
            mid_pt = gp_Pnt(
                (cog_a.X() + cog_b.X()) / 2,
                (cog_a.Y() + cog_b.Y()) / 2,
                (cog_a.Z() + cog_b.Z()) / 2,
            )
            sc = BRepClass3d_SolidClassifier(shape)
            sc.Perform(mid_pt, 1e-6)
            if sc.State() != TopAbs_OUT:
                logger.debug(
                    f"    Planar pair [{fa['face_idx']}, {fb['face_idx']}]: "
                    f"SKIP — midpoint is inside solid (gap passes through material)"
                )
                continue
            constraints.append({
                'source':      'planar_pair',
                'width_mm':    round(gap_mm, 3),
                'face_idxs':   [fa['face_idx'], fb['face_idx']],
                'position_mm': mid_mm,
            })
            logger.debug(
                f"    Planar pair [{fa['face_idx']}, {fb['face_idx']}]: "
                f"gap = {gap_mm:.3f} mm"
            )


# ---------------------------------------------------------------------------
# Pass C — ray cast on non-planar faces assigned to this fixturing
# ---------------------------------------------------------------------------

def _ray_cast_pass(shape, approach_vec, fix_planar, assigned_face_idxs,
                   hole_face_idxs, intersector, max_dist_model, constraints,
                   face_list=None):
    planar_face_idxs = {pf['face_idx'] for pf in fix_planar}
    approach_mag     = approach_vec.Magnitude()

    exp      = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx = 0

    while exp.More():
        face    = topods.Face(exp.Current())
        adaptor = BRepAdaptor_Surface(face, True)
        stype   = adaptor.GetType()

        if face_idx not in assigned_face_idxs:
            face_idx += 1; exp.Next(); continue
        if face_idx in planar_face_idxs:
            face_idx += 1; exp.Next(); continue
        if face_idx in hole_face_idxs:
            face_idx += 1; exp.Next(); continue

        # Skip void-facing full cylinders
        if stype == GeomAbs.GeomAbs_Cylinder:
            u_span = abs(adaptor.LastUParameter() - adaptor.FirstUParameter())
            if abs(u_span - 2 * math.pi) <= 1e-4:
                cyl    = adaptor.Cylinder()
                ax_loc = cyl.Axis().Location()
                ax_dir = gp_Vec(cyl.Axis().Direction())
                v_mid  = (adaptor.FirstVParameter() + adaptor.LastVParameter()) / 2
                mid_pt = gp_Pnt(
                    ax_loc.X() + ax_dir.X() * v_mid,
                    ax_loc.Y() + ax_dir.Y() * v_mid,
                    ax_loc.Z() + ax_dir.Z() * v_mid,
                )
                sc = BRepClass3d_SolidClassifier(shape)
                sc.Perform(mid_pt, 1e-6)
                if sc.State() == TopAbs_OUT:
                    face_idx += 1; exp.Next(); continue

        flip  = -1.0 if face.Orientation() == TopAbs_REVERSED else 1.0
        u_min = adaptor.FirstUParameter()
        u_max = adaptor.LastUParameter()
        v_min = adaptor.FirstVParameter()
        v_max = adaptor.LastVParameter()

        n     = TOOL_ACCESS_SAMPLE_GRID
        u_pts = [u_min + (u_max - u_min) * (i + 0.5) / n for i in range(n)]
        v_pts = [v_min + (v_max - v_min) * (j + 0.5) / n for j in range(n)]

        for u in u_pts:
            for v in v_pts:
                try:
                    pt  = adaptor.Value(u, v)
                    d1u = adaptor.DN(u, v, 1, 0)
                    d1v = adaptor.DN(u, v, 0, 1)
                    nrm = d1u.Crossed(d1v)
                    if nrm.Magnitude() < 1e-10:
                        continue
                    nrm.Multiply(flip)
                except Exception:
                    continue

                dot_a  = nrm.Dot(approach_vec) / (approach_mag ** 2)
                wall_n = gp_Vec(
                    nrm.X() - approach_vec.X() * dot_a,
                    nrm.Y() - approach_vec.Y() * dot_a,
                    nrm.Z() - approach_vec.Z() * dot_a,
                )
                if wall_n.Magnitude() < 1e-6:
                    continue

                wall_n.Normalize()
                line = gp_Lin(pt, gp_Dir(wall_n))
                epsilon = 1e-4
                intersector.Perform(line, epsilon, max_dist_model)

                if not intersector.IsDone() or intersector.NbPnt() == 0:
                    continue

                # Find minimum hit and its face
                best_w        = None
                best_hit_idx  = None  # 1-based intersector index of best hit
                for k in range(1, intersector.NbPnt() + 1):
                    w = intersector.WParameter(k)
                    if w > epsilon and (best_w is None or w < best_w):
                        best_w       = w
                        best_hit_idx = k

                if best_w is None:
                    continue

                gap_mm = best_w * 1000.0
                if gap_mm < 1e-3 or gap_mm > TOOL_ACCESS_MAX_GAP_MM:
                    continue

                # Resolve hit face to index using IsSame()
                hit_face_idx = None
                if face_list is not None and best_hit_idx is not None:
                    try:
                        hit_face = intersector.Face(best_hit_idx)
                        for fi, fl_face in enumerate(face_list):
                            if fl_face.IsSame(hit_face):
                                hit_face_idx = fi
                                break
                    except Exception:
                        pass

                face_idxs = [face_idx]
                if hit_face_idx is not None and hit_face_idx != face_idx:
                    face_idxs = [face_idx, hit_face_idx]

                pos_mm = (
                    round(pt.X() * 1000, 1),
                    round(pt.Y() * 1000, 1),
                    round(pt.Z() * 1000, 1),
                )
                constraints.append({
                    'source':      'ray_cast',
                    'width_mm':    round(gap_mm, 3),
                    'face_idxs':   face_idxs,
                    'position_mm': pos_mm,
                })
                logger.debug(
                    f"    Ray cast face {face_idx} → face {hit_face_idx}: "
                    f"gap = {gap_mm:.3f} mm at {pos_mm}"
                )

        face_idx += 1
        exp.Next()