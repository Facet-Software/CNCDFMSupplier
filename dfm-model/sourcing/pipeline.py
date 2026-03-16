# sourcing/pipeline.py
# Orchestrates the full STEP file analysis pipeline.
# Import and call process_step_for_basics() to run everything.

import logging

from sourcing.loader import load_step_file
from sourcing.features.planar import get_planar_faces
from sourcing.features.cylindrical import detect_cylindrical_features, detect_partial_holes
from sourcing.features.thin_walls import detect_thin_walls, detect_hole_proximity_walls
from sourcing.classify.holes import classify_through_blind, classify_hole_type
from sourcing.analysis.setup import analyze_setups
from sourcing.analysis.tool_access import analyze_tool_access
from sourcing.analysis.dfm import analyze_dfm
from sourcing.analysis.feature_summary import compute_feature_counts
from sourcing.utils.geometry import get_face_by_index, build_face_adjacency
# pockets import deferred — detect_pockets not yet wired into pipeline
from sourcing.reporting.summary import (
    log_hole_summary,
    log_planar_face_summary,
    log_chamfer_summary,
    log_thin_wall_summary,
    log_setup_summary,
    log_dfm_summary,
    log_tool_access_summary,
    log_feature_count_summary,
)
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.GProp import GProp_GProps
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.BRep import BRep_Tool
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Core.TopAbs import TopAbs_REVERSED

import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_bounding_box(shape, scale_factor):
    """
    Return bounding box info as a tuple:
        (dx_mm, dy_mm, dz_mm,
         xmin_model, ymin_model, zmin_model,
         xmax_model, ymax_model, zmax_model)

    *_mm values are in millimetres (scale-corrected).
    *_model values are raw model units — used for entry-reference depth
    calculations that need extent along an arbitrary approach vector.
    """
    bnd = Bnd_Box()
    brepbndlib.Add(shape, bnd, True)
    xmin, ymin, zmin, xmax, ymax, zmax = bnd.Get()

    pf = 1.0 / scale_factor if scale_factor < 1 else 1.0
    logger.debug(
        f"Bounding box (mm): x={xmin*pf:.1f} to {xmax*pf:.1f}, "
        f"y={ymin*pf:.1f} to {ymax*pf:.1f}, "
        f"z={zmin*pf:.1f} to {zmax*pf:.1f}"
    )
    logger.debug(
        f"Overall dimensions: dx={(xmax-xmin)*pf:.1f}, "
        f"dy={(ymax-ymin)*pf:.1f}, "
        f"dz={(zmax-zmin)*pf:.1f}"
    )
    return (
        (xmax - xmin) * pf, (ymax - ymin) * pf, (zmax - zmin) * pf,
        xmin, ymin, zmin, xmax, ymax, zmax,
    )


def get_solid_volume(shape, scale_factor):
    """
    Return the volume of the solid in mm³.

    scale_factor < 1 means the model is in metres; each linear dimension
    needs dividing by scale_factor, so volume divides by scale_factor³.
    """
    props = GProp_GProps()
    brepgprop.VolumeProperties(shape, props)
    vol_model = props.Mass()   # "mass" == volume for VolumeProperties
    pf = 1.0 / scale_factor if scale_factor < 1 else 1.0
    vol_mm3 = vol_model * (pf ** 3)
    logger.debug(f"Solid volume: {vol_mm3:.1f} mm³")
    return vol_mm3


def tessellate_shape(shape):
    """
    Tessellate all faces of the shape into triangle data for the 3D viewer.

    Uses BRepMesh_IncrementalMesh with a 0.5mm linear deflection (0.0005
    model units, since coordinates are in units where ×1000 = mm).

    Returns a list of face dicts:
        i : int        — face_idx (matches pipeline face indices)
        v : list[float]— flat vertex array [x0,y0,z0, x1,y1,z1, ...] in mm
        t : list[int]  — flat triangle index array [a,b,c, ...] 0-based into v

    Coordinates are in mm, rounded to 2 decimal places.
    Triangles respect face orientation so outward normals are consistent.
    """
    from OCC.Core.TopExp import TopExp_Explorer as _Exp
    from OCC.Core.TopAbs import TopAbs_FACE as _FACE
    from OCC.Core.TopoDS import topods as _tds

    LINEAR_DEFLECTION = 0.0005   # 0.5 mm in model units (model_unit * 1000 = mm)
    ANGULAR_DEFLECTION = 0.5     # radians — controls curvature approximation

    try:
        mesh = BRepMesh_IncrementalMesh(shape, LINEAR_DEFLECTION, False, ANGULAR_DEFLECTION, True)
        mesh.Perform()
    except Exception as e:
        logger.warning(f"Tessellation failed: {e}")
        return []

    faces_data = []
    exp = _Exp(shape, _FACE)
    face_idx = 0

    while exp.More():
        face = _tds.Face(exp.Current())
        location = TopLoc_Location()
        tri = BRep_Tool.Triangulation(face, location)

        if tri is not None:
            is_reversed = (face.Orientation() == TopAbs_REVERSED)
            has_transform = not location.IsIdentity()
            trsf = location.Transformation() if has_transform else None

            n_nodes = tri.NbNodes()
            n_tris  = tri.NbTriangles()

            # Collect vertices in mm
            verts = []
            for i in range(1, n_nodes + 1):
                p = tri.Node(i)
                if trsf:
                    p = p.Transformed(trsf)
                verts.append(round(p.X() * 1000, 2))
                verts.append(round(p.Y() * 1000, 2))
                verts.append(round(p.Z() * 1000, 2))

            # Collect triangles (0-indexed), respecting face orientation
            tris = []
            for i in range(1, n_tris + 1):
                t = tri.Triangle(i)
                n1, n2, n3 = t.Get()
                if is_reversed:
                    tris.extend([n1 - 1, n3 - 1, n2 - 1])
                else:
                    tris.extend([n1 - 1, n2 - 1, n3 - 1])

            faces_data.append({"i": face_idx, "v": verts, "t": tris})

        face_idx += 1
        exp.Next()

    logger.debug(f"Tessellated {len(faces_data)} faces")
    return faces_data


def process_step_for_basics(filepath):
    """
    Run the full feature extraction pipeline on a STEP file.

    Returns a dict with all detected features, ready for downstream use
    (API response, database write, etc.).
    """
    shape, scale_factor, display_unit = load_step_file(filepath)
    bbox               = get_bounding_box(shape, scale_factor)
    dims               = bbox[:3]
    bbox_extents       = bbox[3:]
    solid_volume_mm3   = get_solid_volume(shape, scale_factor)
    geometry           = tessellate_shape(shape)

    # Build face adjacency once — reused by planar face detection,
    # pocket detection, and any future module needing topological adjacency.
    face_list, edge_to_faces, face_to_edges, global_edge_map = build_face_adjacency(shape)
    logger.debug(
        f"Face adjacency built: {len(face_list)} faces, "
        f"{len(edge_to_faces)} edges"
    )

    planar_faces = get_planar_faces(
        shape, scale_factor,
        edge_to_faces=edge_to_faces,
        face_to_edges=face_to_edges,
        global_edge_map=global_edge_map,
    )
    hole_profiles, fillets, conical_chamfers = detect_cylindrical_features(shape)
    thin_walls = detect_thin_walls(shape, planar_faces, fillets)

    classify_through_blind(shape, hole_profiles)
    for hp in hole_profiles:
        hp["hole_type"] = classify_hole_type(hp, shape)
    hole_proximity_walls  = detect_hole_proximity_walls(hole_profiles)
    partial_holes         = detect_partial_holes(shape, hole_profiles)

    setup_analysis = analyze_setups(shape, planar_faces, hole_profiles, pockets=[], fillets=fillets,
                                    edge_to_faces=edge_to_faces, face_list=face_list)

    tool_access = analyze_tool_access(shape, setup_analysis, planar_faces, hole_profiles, fillets=fillets, face_list=face_list)

    feature_counts = compute_feature_counts(setup_analysis, hole_profiles, fillets,
                                            planar_faces, tool_access=tool_access)

    dfm_analysis = analyze_dfm(hole_profiles, fillets,
                               tool_access=tool_access,
                               setup_analysis=setup_analysis,
                               planar_faces=planar_faces,
                               shape=shape,
                               bbox_extents=bbox_extents,
                               face_list=face_list,
                               face_to_edges=face_to_edges,
                               edge_to_faces=edge_to_faces,
                               thin_walls=thin_walls,
                               hole_proximity_walls=hole_proximity_walls,
                               partial_holes=partial_holes)

    log_hole_summary(hole_profiles, shape)
    log_planar_face_summary(planar_faces)
    log_chamfer_summary(conical_chamfers)
    log_thin_wall_summary(thin_walls, hole_proximity_walls)
    log_setup_summary(setup_analysis, fillets)
    log_tool_access_summary(tool_access)
    log_feature_count_summary(feature_counts)
    log_dfm_summary(dfm_analysis)

    return {
        "bounding_box_mm":      dims,
        "solid_volume_mm3":     solid_volume_mm3,
        "display_unit":         display_unit,
        "geometry":             geometry,
        "planar_faces":         planar_faces,
        "hole_profiles":        hole_profiles,
        "fillets":              fillets,
        "conical_chamfers":     conical_chamfers,
        "thin_walls":           thin_walls,
        "hole_proximity_walls": hole_proximity_walls,
        "partial_holes":        partial_holes,
        "setup_analysis":       setup_analysis,
        "tool_access":          tool_access,
        "feature_counts":       feature_counts,
        "dfm_analysis":         dfm_analysis,
        # Adjacency maps available for callers that need topological queries
        "_face_list":        face_list,
        "_edge_to_faces":    edge_to_faces,
        "_face_to_edges":    face_to_edges,
        "_global_edge_map":  global_edge_map,
    }


def to_report_dict(filepath, pipeline_result):
    """
    Serialize the pipeline result into a clean, UI-consumable dict.
    This is the schema the front-end report component expects.

    Parameters
    ----------
    filepath : str
        Original STEP file path (used for filename display).
    pipeline_result : dict
        The dict returned by process_step_for_basics().

    Returns
    -------
    dict  —  JSON-serializable report schema.
    """
    dims            = pipeline_result["bounding_box_mm"]
    setup           = pipeline_result["setup_analysis"]
    hole_profiles   = pipeline_result["hole_profiles"]
    fillets         = pipeline_result["fillets"]
    tool_access     = pipeline_result["tool_access"]
    feature_counts  = pipeline_result["feature_counts"]
    dfm             = pipeline_result["dfm_analysis"]
    display_unit    = pipeline_result.get("display_unit", "mm")

    MM_PER_INCH = 25.4

    def _len(mm):
        """Convert mm to display unit, rounded appropriately."""
        if display_unit == "inch":
            return round(mm / MM_PER_INCH, 4)
        return round(mm, 1)

    def _vol(mm3):
        """Convert mm³ to display unit³, rounded appropriately."""
        if display_unit == "inch":
            return round(mm3 / (MM_PER_INCH ** 3), 4)
        return round(mm3, 1)

    # ── fixturing label map (idx → axis label string e.g. "+Z") ──────────────
    fix_label = {}
    for fix in setup["fixturings"]:
        fix_label[fix["fixturing_idx"]] = fix["approach_axis"] or f"fix{fix['fixturing_idx']}"

    # ── per-fixturing concern counts from dfm flags ───────────────────────────
    concern_counts = {}   # fixturing_idx → {critical, warning, advisory}
    for flag in dfm["flags"]:
        fi = flag["detail"].get("fixturing_idx")
        if fi is None:
            continue
        bucket = concern_counts.setdefault(fi, {"critical": 0, "warning": 0, "advisory": 0})
        sev = flag["severity"]
        if sev in bucket:
            bucket[sev] += 1

    # ── tool access lookup (fixturing_idx → min_tool_dia_mm) ──────────────────
    ta_lookup = {ta["fixturing_idx"]: ta for ta in tool_access}

    # ── fixturing feature counts lookup ──────────────────────────────────────
    fc_lookup = {fc["fixturing_idx"]: fc for fc in feature_counts}

    # ── build fixturings list ─────────────────────────────────────────────────
    fixturings_out = []
    for fix in setup["fixturings"]:
        fi   = fix["fixturing_idx"]
        fc   = fc_lookup.get(fi, {})
        ta   = ta_lookup.get(fi, {})
        cc   = concern_counts.get(fi, {"critical": 0, "warning": 0, "advisory": 0})

        fixturings_out.append({
            "id":              fi,
            "label":           fix_label[fi],
            "setup_type":      fix.get("setup_type", "3-axis-standard"),
            "approach_vector": list(fix.get("approach_vector", (0, 0, 1))),
            "face_idxs":       [feat["feature_idx"] for feat in fix.get("features", [])],
            "planar":          fc.get("planar_faces", 0),
            "floor":           fc.get("floor_faces", 0),
            "wall":            fc.get("wall_faces", 0),
            "holes":           fc.get("holes", {}).get("total", 0),
            "fillets":         fc.get("fillets", {}).get("total", 0),
            "tool_changes":    fc.get("estimated_tool_changes", 0),
            "min_tool_dia":    _len(ta["min_tool_dia_mm"]) if ta.get("min_tool_dia_mm") else None,
            "concerns":        cc,
        })

    # ── holes ─────────────────────────────────────────────────────────────────
    holes_out = []
    for i, hp in enumerate(hole_profiles):
        r_mm  = hp.get("rep_radius_mm") or 0.0
        depth = hp.get("local_thickness_mm") or hp.get("total_height_mm") or 0.0
        ld    = round(depth / (r_mm * 2), 1) if r_mm > 0 else None

        cone_angle = None
        for s in hp.get("sections", []):
            if s.get("type") == "cone":
                ca = s.get("semi_angle_deg") or s.get("angle_deg")
                if ca:
                    cone_angle = round(ca, 1)
                break

        holes_out.append({
            "id":         i + 1,
            "type":       hp["hole_type"],
            "radius":     _len(r_mm),          # in display unit
            "depth":      _len(depth),          # in display unit
            "cone_angle": cone_angle,
            "ld":         ld if (ld and ld > 2.0) else None,
            "face_idxs":  hp.get("face_idxs", []),
        })

    # ── dfm flags ─────────────────────────────────────────────────────────────
    def _flag_face_idxs(flag):
        """Resolve which face_idxs a DFM flag applies to, for viewer highlighting."""
        d = flag.get("detail", {})
        if "face_idxs" in d:
            return list(d["face_idxs"])
        if "face_idx" in d:
            return [d["face_idx"]]
        if "hole_idx" in d:
            hi = d["hole_idx"]
            if 0 <= hi < len(hole_profiles):
                return list(hole_profiles[hi].get("face_idxs", []))
        if "fillet_face_idx" in d:
            return [d["fillet_face_idx"]]
        if "hole_pair_idxs" in d:
            result = []
            for hi in d["hole_pair_idxs"]:
                if 0 <= hi < len(hole_profiles):
                    result.extend(hole_profiles[hi].get("face_idxs", []))
            return result
        return []

    dfm_out = []
    for flag in dfm["flags"]:
        fi = flag["detail"].get("fixturing_idx")
        dfm_out.append({
            "severity":  flag["severity"],
            "code":      flag["category"],
            "fixturing": fix_label.get(fi, "—"),
            "message":   flag["message"],
            "face_idxs": _flag_face_idxs(flag),
        })

    bbox_vol_mm3   = dims[0] * dims[1] * dims[2]
    solid_vol_mm3  = pipeline_result["solid_volume_mm3"]
    machined_vol   = max(0.0, bbox_vol_mm3 - solid_vol_mm3)
    removal_pct    = round(machined_vol / bbox_vol_mm3 * 100, 1) if bbox_vol_mm3 > 0 else 0.0

    unit_label = "in" if display_unit == "inch" else "mm"

    return {
        "filename":               os.path.basename(filepath),
        "analyzed_at":            datetime.now(timezone.utc).isoformat(),
        "display_unit":           display_unit,
        "unit_label":             unit_label,
        "bounding_box":           {
            "x": _len(dims[0]),
            "y": _len(dims[1]),
            "z": _len(dims[2]),
        },
        "bbox_volume_mm3":        round(bbox_vol_mm3, 1),
        "solid_volume_mm3":       round(solid_vol_mm3, 1),
        "machined_volume_mm3":    round(machined_vol, 1),
        "material_removal_pct":   removal_pct,
        "planar_faces":           sum(1 for p in pipeline_result["planar_faces"]
                                      if not p.get("is_chamfer")),
        "machine_classification": setup.get("machine_classification", "3-axis-standard").upper(),
        "fixturing_count":        setup["fixturing_count"],
        "fixturings":             fixturings_out,
        "holes":                  holes_out,
        "dfm":                    dfm_out,
        "geometry":               pipeline_result.get("geometry", []),
    }