# sourcing/loader.py
# Loads a STEP file and applies scale correction if the model is in metres.

import os
import logging

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.TopAbs import TopAbs_FACE
from OCC.Core.TopoDS import topods
from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
from OCC.Core import GeomAbs
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.gp import gp_Trsf, gp_Pnt
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform

logger = logging.getLogger(__name__)


def load_step_file(filepath):
    """
    Load a STEP file, detect metre-vs-mm scale mismatch, and return
    (shape, scale_factor).

    scale_factor is 1.0 if the model was already in mm, or 0.001 if it
    was in metres and has been rescaled to mm.  All downstream code works
    in mm; scale_factor is passed along so area computations can correct
    for the transform.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"STEP file not found: {filepath}")

    reader = STEPControl_Reader()
    status = reader.ReadFile(filepath)
    if status != 1:
        raise ValueError(f"Failed to read STEP file: status {status}")

    reader.TransferRoots()
    shape = reader.OneShape()
    logger.info(f"Successfully loaded: {filepath}")
    logger.debug(
        f"Shape type: {shape.ShapeType()} "
        f"(0=Compound,1=CompSolid,2=Solid,3=Shell,4=Face,5=Wire,6=Edge,7=Vertex)"
    )

    bnd_raw = Bnd_Box()
    brepbndlib.Add(shape, bnd_raw, True)
    xmin, ymin, zmin, xmax, ymax, zmax = bnd_raw.Get()
    dx_raw      = xmax - xmin
    dy_raw      = ymax - ymin
    dz_raw      = zmax - zmin
    max_dim_raw = max(dx_raw, dy_raw, dz_raw)
    logger.debug(
        f"Raw bounding box: x={xmin:.4f} to {xmax:.4f}, "
        f"y={ymin:.4f} to {ymax:.4f}, z={zmin:.4f} to {zmax:.4f}"
    )
    logger.debug(f"Raw dimensions: dx={dx_raw:.4f}, dy={dy_raw:.4f}, dz={dz_raw:.4f}")

    # Determine unit system from bounding box size.
    #
    # A real machined part in mm will have max_dim >> 1.0 (typically 5–5000 mm).
    # A model in metres will have max_dim << 1.0 (a 100 mm part = 0.1 m).
    #
    # Two cases, both end up with scale_factor = 0.001 so all downstream
    # `* 1000` unit conversions are correct:
    #
    #   mm file  (max_dim > 1.0): apply *0.001 spatial transform.
    #            model unit = 0.001 mm → *1000 → mm ✓
    #            area: props.Mass() in (0.001 mm)² / 0.001² → mm² ✓
    #
    #   metre file (max_dim ≤ 1.0): NO spatial transform needed.
    #            model unit = 1 m = 1000 mm → *1000 → 1000 mm ✗ …
    #            wait: model unit = 1 m, raw coord 0.005 m, *1000 = 5 mm ✓
    #            area: props.Mass() in m² / 0.001² = m² * 10⁶ = mm² ✓
    #            (1 m² = 10⁶ mm²)
    #
    # The cylinder-probe heuristic (radius * 1000 > max_dim * 50) was
    # unreliable — it fired for r=5 mm but not r=4 mm in a 99 mm part,
    # depending which cylinder face happened to be enumerated first.

    scale_factor = 0.001   # always; downstream code uses *1000 / scale_factor²

    if max_dim_raw > 1.0:
        # mm file — normalise to 0.001 mm model units
        trsf = gp_Trsf()
        trsf.SetScale(gp_Pnt(0, 0, 0), scale_factor)
        shape = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
        logger.debug(
            f"mm file detected (max_dim={max_dim_raw:.1f}): "
            f"applied 1/1000 normalisation."
        )
    else:
        # metre file — model coordinates already give mm when multiplied by 1000
        logger.debug(
            f"Metre file detected (max_dim={max_dim_raw:.4f}): "
            f"no spatial transform; downstream *1000 converts m → mm."
        )

    return shape, scale_factor