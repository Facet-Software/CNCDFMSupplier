# sourcing/loader.py
# Loads a STEP file, detects unit system (mm, metres, or inches),
# normalises everything to internal mm, and returns display_unit so
# the report can render values in the original unit.

import os
import re
import logging

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.gp import gp_Trsf, gp_Pnt
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform

logger = logging.getLogger(__name__)

# 1 inch = 25.4 mm
_MM_PER_INCH = 25.4


def _detect_step_unit(filepath, max_bytes=131072):
    """
    Scan the first max_bytes of a STEP file for unit declarations.

    STEP AP203/AP214 embeds unit info in the DATA section as entities like:

        SI_UNIT($,.MILLI.,.METRE.)           -> mm
        SI_UNIT($,.METRE.)                   -> metres
        CONVERSION_BASED_UNIT('INCH',25.4    -> inches
        CONVERSION_BASED_UNIT('in',25.4      -> inches (alternate spelling)
        CONVERSION_BASED_UNIT('FOOT',        -> feet (rare)

    Returns 'mm' | 'inch' | 'metre' | 'unknown'.
    Text scan is used rather than OCC's unit API because the API behaviour
    varies across OCC versions and is unreliable for non-SI files.
    """
    try:
        with open(filepath, 'rb') as f:
            raw = f.read(max_bytes)
        text = raw.decode('ascii', errors='replace').upper()
    except OSError:
        return 'unknown'

    # Inch: CONVERSION_BASED_UNIT with 'INCH' or 'IN' label
    if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'(INCH|IN)\b", text):
        return 'inch'

    # Feet (rare but possible in imported architectural models)
    if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'(FOOT|FT|FEET)\b", text):
        return 'foot'

    # SI metre without MILLI prefix
    if re.search(r"SI_UNIT\s*\(\s*\$\s*,\s*\.METRE\.", text) and \
       not re.search(r"SI_UNIT\s*\(\s*\$\s*,\s*\.MILLI\.\s*,\s*\.METRE\.", text):
        return 'metre'

    # SI millimetre (most common)
    if re.search(r"SI_UNIT\s*\(\s*\$\s*,\s*\.MILLI\.\s*,\s*\.METRE\.", text):
        return 'mm'

    return 'unknown'


def load_step_file(filepath):
    """
    Load a STEP file, detect unit system, normalise to internal mm, and
    return (shape, scale_factor, display_unit).

    Internal representation
    -----------------------
    All downstream code works in mm. After this function returns:
        length_mm  = occ_value x 1000
        area_mm2   = occ_area  / scale_factor^2
        volume_mm3 = occ_vol   / scale_factor^3

    scale_factor is always 0.001 (the spatial transform applied or implied).

    display_unit
    ------------
    'mm'     -- original file was in millimetres (most common)
    'inch'   -- original file was in inches
    'metre'  -- original file was in metres
    'unknown'-- could not determine; display in mm as fallback

    Note on OCC inch handling
    -------------------------
    OCC converts declared inches to mm internally when reading. So after
    reader.TransferRoots(), coordinates in an inch file are already in mm
    (e.g. a 1-inch cube reads as 25.4 x 25.4 x 25.4 in raw OCC coords).
    The same x0.001 normalisation therefore applies to both mm and inch files.
    Only metre files skip the transform.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"STEP file not found: {filepath}")

    # Detect unit BEFORE loading — scan raw text
    declared_unit = _detect_step_unit(filepath)
    logger.debug(f"STEP unit declaration: {declared_unit}")

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

    scale_factor = 0.001   # always; downstream multiplies by 1000 to get mm

    # Metre files have raw coords in metres (max_dim ~ 0.001 to 1.0).
    # mm and inch files have raw coords already in mm after OCC reads them
    # (max_dim >> 1.0 for any real machined part).
    is_metric_metre = (declared_unit == 'metre') or \
                      (declared_unit == 'unknown' and max_dim_raw <= 1.0)

    if is_metric_metre:
        display_unit = 'metre' if declared_unit == 'metre' else 'mm'
        logger.debug(
            f"Metre file (max_dim={max_dim_raw:.4f}): "
            f"no transform; downstream x1000 converts m -> mm."
        )
    else:
        trsf = gp_Trsf()
        trsf.SetScale(gp_Pnt(0, 0, 0), scale_factor)
        shape = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
        display_unit = declared_unit if declared_unit in ('mm', 'inch') else 'mm'
        logger.debug(
            f"{display_unit.upper()} file detected (max_dim={max_dim_raw:.1f}): "
            f"applied x{scale_factor} normalisation."
        )

    logger.debug(f"display_unit={display_unit!r}")
    return shape, scale_factor, display_unit