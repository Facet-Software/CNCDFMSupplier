# sourcing/features/planar.py
# Detects all planar faces, corrects their normals to point outward,
# and computes area, centroid, and chamfer classification.

import math
import logging

from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_OUT
from OCC.Core.TopoDS import topods
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
from OCC.Core import GeomAbs
from OCC.Core.BRepClass3d import BRepClass3d_SolidClassifier
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp import GProp_GProps
from OCC.Core.gp import gp_Pnt

from sourcing.config import (
    SETUP_CHAMFER_ANGLE_TOL_DEG,
    SETUP_CHAMFER_WIDTH_RATIO,
    SETUP_CHAMFER_MAX_ABS_WIDTH_MM,
    SETUP_CHAMFER_MAX_ASPECT_RATIO,
)
from sourcing.utils.geometry import face_local_dimensions, edge_length_mm

logger = logging.getLogger(__name__)

# Standard chamfer semi-angles from a principal axis (degrees).
_CHAMFER_ANGLES = (30.0, 45.0, 60.0)

# The six principal axis directions as unit vectors.
_PRINCIPAL_AXES = [
    ( 1.0,  0.0,  0.0),
    (-1.0,  0.0,  0.0),
    ( 0.0,  1.0,  0.0),
    ( 0.0, -1.0,  0.0),
    ( 0.0,  0.0,  1.0),
    ( 0.0,  0.0, -1.0),
]


def get_planar_faces(shape, scale_factor=1.0, edge_to_faces=None, face_to_edges=None, global_edge_map=None):
    """
    Return all planar faces with normals, areas, centroids, and chamfer
    classification.

    Parameters
    ----------
    shape         : TopoDS_Shape
    scale_factor  : float — from loader; used to correct area units
    edge_to_faces : dict[hash → list[int]] — from build_face_adjacency()
    face_to_edges : dict[int → list[(hash, edge)]] — from build_face_adjacency()

    Both adjacency dicts are optional. If not provided, chamfer classification
    falls back to the face's own aspect ratio (less accurate — misses the case
    where a chamfer is large relative to one adjacent edge but not the other).

    Each entry:
      face_idx    : int
      normal      : tuple (nx, ny, nz) rounded to 4 dp, outward normal
      area_mm2    : float — mm²
      centroid_mm : tuple (x, y, z) mm
      is_chamfer  : bool

    Internal (not serialised):
      _normal_dir : gp_Dir
      _centroid   : gp_Pnt
    """
    planar_faces = []
    exp          = TopExp_Explorer(shape, TopAbs_FACE)
    face_index   = 0
    sc_normal    = BRepClass3d_SolidClassifier(shape)

    logger.debug("Collecting planar faces and normals...")

    while exp.More():
        face    = topods.Face(exp.Current())
        adaptor = BRepAdaptor_Surface(face)

        if adaptor.GetType() == GeomAbs.GeomAbs_Plane:
            nrm = adaptor.Plane().Axis().Direction()

            # Determine true outward normal by probing just outside the face.
            props_probe = GProp_GProps()
            brepgprop.SurfaceProperties(face, props_probe)
            cog_probe   = props_probe.CentreOfMass()
            epsilon_nrm = 1e-3

            probe_out = gp_Pnt(
                cog_probe.X() + nrm.X() * epsilon_nrm,
                cog_probe.Y() + nrm.Y() * epsilon_nrm,
                cog_probe.Z() + nrm.Z() * epsilon_nrm,
            )
            sc_normal.Perform(probe_out, 1e-6)
            if sc_normal.State() != TopAbs_OUT:
                nrm = nrm.Reversed()

            props = GProp_GProps()
            brepgprop.SurfaceProperties(face, props)
            area = props.Mass() / (scale_factor ** 2)
            cog  = props.CentreOfMass()

            normal_tuple = (round(nrm.X(), 4), round(nrm.Y(), 4), round(nrm.Z(), 4))
            is_chamfer   = _classify_chamfer(
                face, face_index, normal_tuple,
                edge_to_faces, global_edge_map,
            )

            planar_faces.append({
                "face_idx":    face_index,
                "normal":      normal_tuple,
                "area_mm2":    round(area, 3),
                "centroid_mm": (
                    round(cog.X() * 1000, 1),
                    round(cog.Y() * 1000, 1),
                    round(cog.Z() * 1000, 1),
                ),
                "is_chamfer":  is_chamfer,
                "_normal_dir": nrm,
                "_centroid":   cog,
            })
            logger.debug(
                f"  Planar face {face_index}: "
                f"normal={normal_tuple}, "
                f"area={area:.3f} mm², "
                f"centroid={planar_faces[-1]['centroid_mm']}, "
                f"is_chamfer={is_chamfer}"
            )

        face_index += 1
        exp.Next()

    n_chamfers = sum(1 for pf in planar_faces if pf['is_chamfer'])
    logger.info(
        f"Total planar faces: {len(planar_faces)} "
        f"({n_chamfers} classified as chamfers)"
    )
    return planar_faces


def _is_linear_edge(edge):
    """Return True if the edge is a straight line (not an arc, spline, etc.)."""
    try:
        return BRepAdaptor_Curve(edge).GetType() == GeomAbs.GeomAbs_Line
    except Exception:
        return False


def _classify_chamfer(face, face_idx, normal_tuple, edge_to_faces, global_edge_map):
    """
    Return True if this planar face is a chamfer edge.

    Uses the face object's own edges directly — never looks up via face_idx
    in face_to_edges. Index-based lookup is fragile: when a hole splits a
    chamfer face, topology ordering can shift so face_idx no longer matches
    the adjacency map entry, causing edge lookups to return data for the
    wrong face entirely. Iterating the face object directly is always correct.

    Parameters
    ----------
    face            : TopoDS_Face
    face_idx        : int — only used for debug logging
    normal_tuple    : (nx, ny, nz)
    edge_to_faces   : dict[int → list[int]] — from build_face_adjacency
    global_edge_map : TopTools_IndexedMapOfShape — from build_face_adjacency,
                      with FORWARD-normalized edges; used to look up edge
                      indices so we can check edge_to_faces for sharing.
    """
    from OCC.Core.TopExp import TopExp_Explorer as _TExp
    from OCC.Core.TopAbs import TopAbs_EDGE as _EDGE, TopAbs_FORWARD as _FWD
    from OCC.Core.TopoDS import topods as _tds

    # --- Condition 1: standard chamfer angle -----------------------------
    nx, ny, nz   = normal_tuple
    normal_mag   = math.sqrt(nx*nx + ny*ny + nz*nz)
    if normal_mag < 1e-6:
        return False

    min_angle_from_axis = float('inf')
    for ax in _PRINCIPAL_AXES:
        dot   = (nx*ax[0] + ny*ax[1] + nz*ax[2]) / normal_mag
        angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
        if angle < min_angle_from_axis:
            min_angle_from_axis = angle

    is_standard_angle = any(
        abs(min_angle_from_axis - ca) <= SETUP_CHAMFER_ANGLE_TOL_DEG
        for ca in _CHAMFER_ANGLES
    )
    if not is_standard_angle:
        return False

    # --- Condition 2: width check ----------------------------------------
    dims = face_local_dimensions(face)
    if dims is None:
        logger.debug(f"    face {face_idx}: chamfer check — face_local_dimensions returned None")
        return False
    shorter, longer = dims
    if longer < 1e-6:
        return False

    # A chamfer is a strip — much longer than wide. A circular face (hole
    # end cap) or square face has shorter ≈ longer. Reject anything too
    # "square" to be a chamfer strip before any width checks.
    if shorter / longer > SETUP_CHAMFER_MAX_ASPECT_RATIO:
        logger.debug(
            f"    face {face_idx}: chamfer check — "
            f"aspect ratio {shorter/longer:.3f} > {SETUP_CHAMFER_MAX_ASPECT_RATIO} → not a chamfer strip"
        )
        return False

    chamfer_width = shorter  # mm

    # Absolute width gate: anything under this is unambiguously a chamfer.
    if chamfer_width <= SETUP_CHAMFER_MAX_ABS_WIDTH_MM:
        logger.debug(
            f"    face {face_idx}: chamfer check — "
            f"width={chamfer_width:.3f} <= abs_threshold={SETUP_CHAMFER_MAX_ABS_WIDTH_MM} → chamfer"
        )
        return True

    # Iterate the face's own edges directly. For each shared straight edge
    # longer than the chamfer width, check the ratio against the threshold.
    if edge_to_faces is not None and global_edge_map is not None:
        all_shared          = []
        parent_edge_lengths = []

        edge_exp = _TExp(face, _EDGE)
        seen_idxs = set()
        while edge_exp.More():
            edge  = _tds.Edge(edge_exp.Current())
            e_idx = global_edge_map.FindIndex(edge.Oriented(_FWD))
            if e_idx <= 0 or e_idx in seen_idxs:
                edge_exp.Next()
                continue
            seen_idxs.add(e_idx)

            neighbors = edge_to_faces.get(e_idx, [])
            if len(neighbors) <= 1:
                edge_exp.Next()
                continue

            elen = edge_length_mm(edge)
            if elen < 1e-6:
                edge_exp.Next()
                continue

            all_shared.append(elen)

            if _is_linear_edge(edge) and elen > chamfer_width * 1.1:
                parent_edge_lengths.append(elen)

            edge_exp.Next()

        logger.debug(
            f"    face {face_idx}: chamfer check — "
            f"width={chamfer_width:.3f}, longer={longer:.3f}, "
            f"all_shared={[round(e,2) for e in all_shared]}, "
            f"parent_edges={[round(e,2) for e in parent_edge_lengths]}, "
            f"ratios={[round(chamfer_width/e,3) for e in parent_edge_lengths if e>0]}, "
            f"threshold={SETUP_CHAMFER_WIDTH_RATIO}"
        )

        if parent_edge_lengths:
            return all(
                chamfer_width / elen < SETUP_CHAMFER_WIDTH_RATIO
                for elen in parent_edge_lengths
            )

        # No straight parent edges longer than chamfer width.
        # If all shared edges are curved, this is a chamfer fragment
        # completely bounded by hole arcs — trust the angle test.
        has_any_straight_shared = any(
            _is_linear_edge(_tds.Edge(e.Current()))
            for e in [_TExp(face, _EDGE)]  # placeholder — use the collected data
        )
        # Simpler: check all_shared against parent_edge_lengths
        # If all_shared has entries but parent_edge_lengths is empty,
        # either all edges are curved or all straight edges are end-edges.
        # In either case, the angle alone is sufficient — it's a chamfer fragment.
        if all_shared:
            return True  # angle passed, no disqualifying parent edge found

    # Fallback: use the face's own aspect ratio
    logger.debug(
        f"    face {face_idx}: chamfer check fallback — "
        f"ratio={chamfer_width/longer:.3f}, threshold={SETUP_CHAMFER_WIDTH_RATIO}"
    )
    return (chamfer_width / longer) < SETUP_CHAMFER_WIDTH_RATIO