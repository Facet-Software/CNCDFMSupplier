# sourcing/pipeline.py
# Orchestrates the full STEP file analysis pipeline.
# Import and call process_step_for_basics() to run everything.

import logging

from sourcing.loader import load_step_file
from sourcing.features.planar import get_planar_faces
from sourcing.features.cylindrical import detect_cylindrical_features
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


def process_step_for_basics(filepath):
    """
    Run the full feature extraction pipeline on a STEP file.

    Returns a dict with all detected features, ready for downstream use
    (API response, database write, etc.).
    """
    shape, scale_factor = load_step_file(filepath)
    bbox               = get_bounding_box(shape, scale_factor)
    dims               = bbox[:3]          # (dx_mm, dy_mm, dz_mm)
    bbox_extents       = bbox[3:]          # (xmin, ymin, zmin, xmax, ymax, zmax) model units
    solid_volume_mm3   = get_solid_volume(shape, scale_factor)

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
    hole_proximity_walls = detect_hole_proximity_walls(hole_profiles)

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
                               edge_to_faces=edge_to_faces)

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
        "planar_faces":         planar_faces,
        "hole_profiles":        hole_profiles,
        "fillets":              fillets,
        "conical_chamfers":     conical_chamfers,
        "thin_walls":           thin_walls,
        "hole_proximity_walls": hole_proximity_walls,
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
            "id":           fi,
            "label":        fix_label[fi],
            "setup_type":   fix.get("setup_type", "3-axis-standard"),
            "planar":       fc.get("planar_faces", 0),
            "floor":        fc.get("floor_faces", 0),
            "wall":         fc.get("wall_faces", 0),
            "holes":        fc.get("holes", {}).get("total", 0),
            "fillets":      fc.get("fillets", {}).get("total", 0),
            "tool_changes": fc.get("estimated_tool_changes", 0),
            "min_tool_dia": ta.get("min_tool_dia_mm"),
            "concerns":     cc,
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
            "radius_mm":  round(r_mm, 3),
            "depth_mm":   round(depth, 1),
            "cone_angle": cone_angle,
            "ld":         ld if (ld and ld > 2.0) else None,
            "face_idxs":  hp.get("face_idxs", []),
        })

    # ── dfm flags ─────────────────────────────────────────────────────────────
    dfm_out = []
    for flag in dfm["flags"]:
        fi = flag["detail"].get("fixturing_idx")
        dfm_out.append({
            "severity":  flag["severity"],
            "code":      flag["category"],
            "fixturing": fix_label.get(fi, "—"),
            "message":   flag["message"],
        })

    bbox_vol_mm3   = dims[0] * dims[1] * dims[2]
    solid_vol_mm3  = pipeline_result["solid_volume_mm3"]
    machined_vol   = max(0.0, bbox_vol_mm3 - solid_vol_mm3)
    removal_pct    = round(machined_vol / bbox_vol_mm3 * 100, 1) if bbox_vol_mm3 > 0 else 0.0

    return {
        "filename":               os.path.basename(filepath),
        "analyzed_at":            datetime.now(timezone.utc).isoformat(),
        "bounding_box":           {
            "x": round(dims[0], 1),
            "y": round(dims[1], 1),
            "z": round(dims[2], 1),
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
    }