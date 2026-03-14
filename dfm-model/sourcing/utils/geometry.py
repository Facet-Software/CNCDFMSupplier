# sourcing/utils/geometry.py
# Pure geometry helper functions shared across feature modules.
# No feature-detection logic here — only reusable geometric primitives.

import math
from collections import defaultdict

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_REVERSED
from OCC.Core.TopoDS import topods
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCC.Core import GeomAbs
from OCC.Core.gp import gp_Pnt, gp_Vec, gp_Dir, gp_Lin
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.TopAbs import TopAbs_IN, TopAbs_OUT, TopAbs_ON
from OCC.Core.IntCurvesFace import IntCurvesFace_ShapeIntersector
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepAdaptor import BRepAdaptor_Curve as _BAC

import logging
logger = logging.getLogger(__name__)


def make_axis_fn(loc, vec):
    """Return a closure mapping parameter t → point along axis."""
    def get_point_along_axis(t):
        return loc.Translated(vec.Multiplied(t))
    return get_point_along_axis


def flip_section(sec):
    """
    Return a shallow copy of sec with its axis direction reversed.

    Negating dir_vec negates the v parameter measured along it:
      original v_min → new -v_max
      original v_max → new -v_min
    For cone sections, radius_at_vmin/vmax swap to stay consistent
    with the new v orientation.
    The pre-flip original is stored under '_original' so apex probes
    can always use the cone's native axis direction.
    """
    orig_v_min = sec['v_min']
    orig_v_max = sec['v_max']

    sec     = dict(sec)
    new_vec = sec['dir_vec'].Reversed()

    sec['_original']            = {k: v for k, v in sec.items() if k != '_original'}
    sec['dir_vec']              = new_vec
    sec['v_min']                = -orig_v_max
    sec['v_max']                = -orig_v_min
    sec['get_point_along_axis'] = make_axis_fn(gp_Pnt(*sec['axis_location']), new_vec)
    sec['axis_direction']       = (
        round(-sec['axis_direction'][0], 4),
        round(-sec['axis_direction'][1], 4),
        round(-sec['axis_direction'][2], 4),
    )
    if sec['type'] == 'cone':
        sec['radius_at_vmin'], sec['radius_at_vmax'] = (
            sec['radius_at_vmax'], sec['radius_at_vmin']
        )
    return sec


def axes_are_coaxial(sec, other, tol_axis):
    """
    True if the two sections share the same infinite axis line.
    Uses perpendicular distance between axes to avoid being fooled by
    cone apex origins that sit far from the physical feature.
    """
    dir1 = gp_Dir(sec['dir_vec'])
    dir2 = gp_Dir(other['dir_vec'])
    if not (dir1.IsEqual(dir2, tol_axis) or dir1.IsOpposite(dir2, tol_axis)):
        return False

    loc1        = gp_Pnt(*sec['axis_location'])
    loc2        = gp_Pnt(*other['axis_location'])
    vec_between = gp_Vec(loc1, loc2)
    axis_vec    = gp_Vec(dir1)
    along       = vec_between.Dot(axis_vec)
    perp        = vec_between.Subtracted(axis_vec.Multiplied(along))
    return perp.Magnitude() < tol_axis


def get_face_by_index(shape, target_idx):
    """Return the TopoDS_Face at position target_idx in the face traversal order."""
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    idx = 0
    while exp.More():
        if idx == target_idx:
            return topods.Face(exp.Current())
        idx += 1
        exp.Next()
    return None


def get_circle_edges_of_face(face):
    """Return a dict of {radius: gp_Circle} for all circular edges on face."""
    result = {}
    exp    = TopExp_Explorer(face, TopAbs_EDGE)
    while exp.More():
        edge = topods.Edge(exp.Current())
        ca   = BRepAdaptor_Curve(edge)
        if ca.GetType() == GeomAbs.GeomAbs_Circle:
            r         = round(ca.Circle().Radius(), 8)
            result[r] = ca.Circle()
        exp.Next()
    return result


def find_shared_circle_radius(face_idx_a, face_idx_b, shape):
    """
    Return the radius of the circular edge shared between two faces, or None.
    junction_r ≈ cyl_r  → tip terminates at cylinder wall → blind_with_tip
    junction_r  > cyl_r  → wider chamfer on top            → countersink
    """
    face_a = get_face_by_index(shape, face_idx_a)
    face_b = get_face_by_index(shape, face_idx_b)
    if face_a is None or face_b is None:
        return None
    edges_a = get_circle_edges_of_face(face_a)
    edges_b = get_circle_edges_of_face(face_b)
    for r_a in edges_a:
        for r_b in edges_b:
            if abs(r_a - r_b) < 1e-6:
                return (r_a + r_b) / 2.0
    return None


def probe_apex_burial(cone_sec, classifier, epsilon=1e-4):
    """
    Probe a point just beyond the cone apex along the cone's OWN original
    axis direction (pre-flip if the section was flipped during grouping).
    """
    src      = cone_sec.get('_original', cone_sec)
    apex_tol = 1e-4

    r_vmin = src['radius_at_vmin']
    r_vmax = src['radius_at_vmax']
    gpa    = src['get_point_along_axis']

    if r_vmin <= apex_tol:
        probe_pt = gpa(src['v_min'] - epsilon)
    elif r_vmax <= apex_tol:
        probe_pt = gpa(src['v_max'] + epsilon)
    else:
        return None

    classifier.Perform(probe_pt, 1e-6)
    state  = classifier.State()
    buried = state in (TopAbs_IN, TopAbs_ON)
    logger.debug(
        f"    Apex burial probe cone face {src['face_idx']}: "
        f"state={state} → {'BURIED → blind_with_tip' if buried else 'VOID → through/countersink'}"
    )
    return buried


def face_local_height(face):
    """
    Return the largest in-plane extent of a planar face (mm) — used as the
    wall height in the aspect ratio calculation.

    Projects all face vertices onto the two in-plane axes of the face's
    coordinate system (XAxis and YAxis of the underlying gp_Pln) and
    returns max(x_extent, y_extent).
    """
    adaptor = BRepAdaptor_Surface(face)
    if adaptor.GetType() != GeomAbs.GeomAbs_Plane:
        return None

    plane  = adaptor.Plane()
    x_axis = plane.XAxis().Direction()
    y_axis = plane.YAxis().Direction()

    xs, ys = [], []
    exp = TopExp_Explorer(face, TopAbs_EDGE)
    while exp.More():
        edge    = topods.Edge(exp.Current())
        e_adapt = BRepAdaptor_Curve(edge)
        t_min   = e_adapt.FirstParameter()
        t_max   = e_adapt.LastParameter()
        for t in [t_min, (t_min + t_max) / 2, t_max]:
            pt  = e_adapt.Value(t)
            vec = gp_Vec(plane.Location(), pt)
            xs.append(vec.Dot(gp_Vec(x_axis.X(), x_axis.Y(), x_axis.Z())))
            ys.append(vec.Dot(gp_Vec(y_axis.X(), y_axis.Y(), y_axis.Z())))
        exp.Next()

    if not xs:
        return None

    x_extent = (max(xs) - min(xs)) * 1000  # model → mm
    y_extent = (max(ys) - min(ys)) * 1000
    return max(x_extent, y_extent)


def face_local_dimensions(face):
    """
    Return (shorter_mm, longer_mm) in-plane extents of a planar face.

    Same projection logic as face_local_height() but returns both dimensions
    so callers can compute aspect ratios (e.g. chamfer width / edge length).
    Returns None if the face is not planar or has no edges.
    """
    adaptor = BRepAdaptor_Surface(face)
    if adaptor.GetType() != GeomAbs.GeomAbs_Plane:
        return None

    plane  = adaptor.Plane()
    x_axis = plane.XAxis().Direction()
    y_axis = plane.YAxis().Direction()

    xs, ys = [], []
    exp = TopExp_Explorer(face, TopAbs_EDGE)
    while exp.More():
        edge    = topods.Edge(exp.Current())
        e_adapt = BRepAdaptor_Curve(edge)
        t_min   = e_adapt.FirstParameter()
        t_max   = e_adapt.LastParameter()
        for t in [t_min, (t_min + t_max) / 2, t_max]:
            pt  = e_adapt.Value(t)
            vec = gp_Vec(plane.Location(), pt)
            xs.append(vec.Dot(gp_Vec(x_axis.X(), x_axis.Y(), x_axis.Z())))
            ys.append(vec.Dot(gp_Vec(y_axis.X(), y_axis.Y(), y_axis.Z())))
        exp.Next()

    if not xs:
        return None

    x_extent = (max(xs) - min(xs)) * 1000
    y_extent = (max(ys) - min(ys)) * 1000
    shorter  = min(x_extent, y_extent)
    longer   = max(x_extent, y_extent)
    return shorter, longer


def ray_thickness(shape, origin_pt, inward_dir, max_dist, intersector):
    """
    Shoot a ray from origin_pt along inward_dir and return the distance
    to the first intersection on the far side of the solid (mm), or None.

    Uses IntCurvesFace_ShapeIntersector which finds all ray-shape face
    intersections in one call. We want the nearest intersection that is
    strictly in front of the origin (positive parameter) and not on the
    origin face itself (parameter > small epsilon).

    Parameters
    ----------
    shape        : TopoDS_Shape
    origin_pt    : gp_Pnt  — sample point on the face surface
    inward_dir   : gp_Dir  — direction pointing into the solid
    max_dist     : float   — maximum ray length in model units
    intersector  : IntCurvesFace_ShapeIntersector (pre-built, reused)
    """
    epsilon = 1e-4  # ignore intersections within epsilon of origin (self-hit)

    line = gp_Lin(origin_pt, inward_dir)
    intersector.Perform(line, epsilon, max_dist)

    if not intersector.IsDone() or intersector.NbPnt() == 0:
        return None

    hits = []
    for i in range(1, intersector.NbPnt() + 1):
        w = intersector.WParameter(i)
        if w > epsilon:
            hits.append(w)

    if not hits:
        return None

    return min(hits) * 1000  # model units → mm

def build_face_adjacency(shape):
    """
    Traverse all faces once and build shared-edge adjacency maps.

    Returns
    -------
    face_list     : list[TopoDS_Face]
    edge_to_faces : dict[int → list[int]]
    face_to_edges : dict[int → list[(int, TopoDS_Edge)]]

    Uses TopTools_IndexedMapOfShape with orientation-normalized edges.
    Critical: edges must be normalized to TopAbs_FORWARD before adding to
    the map and before lookup. TopTools_IndexedMapOfShape uses IsEqual()
    which includes orientation — a FORWARD and REVERSED version of the same
    underlying edge get different indices, so shared edges between faces
    never appear as shared. Normalizing to FORWARD before every Add() and
    FindIndex() call fixes this.
    """
    from OCC.Core.TopTools import TopTools_IndexedMapOfShape
    from OCC.Core.TopAbs  import TopAbs_FORWARD

    def _fwd(edge):
        """Return edge with FORWARD orientation (normalised for map lookup)."""
        return edge.Oriented(TopAbs_FORWARD)

    # Build global edge index using normalized orientations
    edge_map = TopTools_IndexedMapOfShape()
    exp_all  = TopExp_Explorer(shape, TopAbs_EDGE)
    while exp_all.More():
        edge_map.Add(_fwd(topods.Edge(exp_all.Current())))
        exp_all.Next()

    face_list     = []
    face_to_edges = {}
    edge_to_faces = defaultdict(list)
    exp           = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx      = 0

    while exp.More():
        face       = topods.Face(exp.Current())
        seen_idxs  = set()
        face_edges = []

        edge_exp = TopExp_Explorer(face, TopAbs_EDGE)
        while edge_exp.More():
            edge  = topods.Edge(edge_exp.Current())
            e_idx = edge_map.FindIndex(_fwd(edge))
            if e_idx > 0 and e_idx not in seen_idxs:
                seen_idxs.add(e_idx)
                face_edges.append((e_idx, edge))
                edge_to_faces[e_idx].append(face_idx)
            edge_exp.Next()

        face_list.append(face)
        face_to_edges[face_idx] = face_edges
        face_idx += 1
        exp.Next()

    return face_list, edge_to_faces, face_to_edges, edge_map


def edge_length_mm(edge):
    """
    Return the arc length of an edge in mm, sampled at 5 points.

    Uses GaussQuadrature-style chord summation — accurate enough for
    straight edges (exact) and smooth curves (error < 0.1% for typical
    fillets and chamfer edges). Returns 0.0 on degenerate edges.
    """
    try:
        ca    = BRepAdaptor_Curve(edge)
        t0    = ca.FirstParameter()
        t1    = ca.LastParameter()
        if abs(t1 - t0) < 1e-12:
            return 0.0
        n      = 8
        pts    = [ca.Value(t0 + (t1 - t0) * i / n) for i in range(n + 1)]
        length = sum(
            math.sqrt(
                (pts[i+1].X() - pts[i].X())**2 +
                (pts[i+1].Y() - pts[i].Y())**2 +
                (pts[i+1].Z() - pts[i].Z())**2
            )
            for i in range(n)
        )
        return length * 1000  # model units → mm
    except Exception:
        return 0.0