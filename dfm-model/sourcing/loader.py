# sourcing/loader.py
# Loads a STEP file, detects unit system, normalizes everything to internal mm,
# and returns display_unit so the report can render values in the original unit.

import os
import re
import logging

from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib
from OCC.Core.gp import gp_Trsf, gp_Pnt
from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform

logger = logging.getLogger(__name__)

_MM_PER_INCH = 25.4


# ---------------------------------------------------------------------------
# UNIT DETECTION
# ---------------------------------------------------------------------------

# Expected raw-coordinate magnitudes (max bounding box dimension) for a
# typical CNC part (1 mm to 3000 mm) in each unit system.
# Used for cross-validation and heuristic fallback.
_EXPECTED_RANGES = {
    #                 min_raw    max_raw      (in declared units)
    'mm':           (1.0,       5000.0),     # 1 mm - 5 m
    'cm':           (0.1,       500.0),      # 1 mm - 5 m
    'metre':        (0.001,     5.0),        # 1 mm - 5 m
    'micrometre':   (1000.0,    5e9),        # 1 mm - 5 m
    'inch':         (0.04,      200.0),      # ~1 mm - ~5 m
    'foot':         (0.003,     16.0),       # ~1 mm - ~5 m
}


def _detect_step_unit(filepath, max_bytes=262144):
    """
    Scan the STEP file for unit declarations.

    STEP files declare length units via SI_UNIT or CONVERSION_BASED_UNIT
    entities.  SI_UNIT has two arguments: SI_UNIT(prefix, name).

        SI_UNIT(.MILLI.,.METRE.)             -> mm
        SI_UNIT(.CENTI.,.METRE.)             -> cm
        SI_UNIT(.MICRO.,.METRE.)             -> um
        SI_UNIT($,.METRE.)                   -> metres (no prefix)
        CONVERSION_BASED_UNIT('INCH',...)    -> inches
        CONVERSION_BASED_UNIT('FOOT',...)    -> feet

    When a file contains multiple LENGTH_UNIT declarations (e.g. Fusion 360
    exports both .MILLI.+.METRE. and bare .METRE.), the most specific
    (prefixed) unit wins -- it's the one tied to the geometry context.

    Returns one of: 'mm' | 'cm' | 'micrometre' | 'metre' | 'inch' | 'foot' | 'unknown'
    """
    try:
        with open(filepath, 'rb') as f:
            raw = f.read(max_bytes)
        text = raw.decode('ascii', errors='replace').upper()
    except OSError:
        return 'unknown'

    # -- CONVERSION_BASED_UNIT (imperial) --
    if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'(INCH|IN)\b", text):
        return 'inch'

    if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'(FOOT|FT|FEET)\b", text):
        return 'foot'

    # -- SI_UNIT with LENGTH context --
    # SI_UNIT has two args: (prefix, unit_name)
    #   prefix:    .MILLI. | .CENTI. | .MICRO. | .KILO. | $ (none)
    #   unit_name: .METRE. | .GRAM. | .RADIAN. | .STERADIAN. | ...
    # We only care about .METRE. (length).  Other unit names (.GRAM.,
    # .RADIAN., .STERADIAN.) are mass/angle and must be ignored.
    #
    # [^)]* allows any prefix form (.MILLI., $, etc.) in the first arg.

    has_milli = bool(re.search(r"SI_UNIT\s*\([^)]*\.MILLI\.\s*,\s*\.METRE\.", text))
    has_centi = bool(re.search(r"SI_UNIT\s*\([^)]*\.CENTI\.\s*,\s*\.METRE\.", text))
    has_micro = bool(re.search(r"SI_UNIT\s*\([^)]*\.MICRO\.\s*,\s*\.METRE\.", text))
    has_bare  = bool(re.search(r"SI_UNIT\s*\(\s*\$\s*,\s*\.METRE\.", text))

    # Most specific prefix wins (files can declare multiple LENGTH_UNITs)
    if has_micro:
        return 'micrometre'
    if has_milli:
        return 'mm'
    if has_centi:
        return 'cm'
    if has_bare:
        return 'metre'

    return 'unknown'


def _validate_unit(declared_unit, max_dim_raw):
    """
    Cross-validate the declared unit against the actual coordinate magnitudes.

    Returns (validated_unit, warning_message_or_None).

    If the declared unit is plausible for the observed coordinates, returns
    it unchanged.  If implausible, attempts to infer the correct unit and
    returns a warning explaining the mismatch.
    """
    if declared_unit == 'unknown':
        return _infer_from_dimensions(max_dim_raw)

    expected = _EXPECTED_RANGES.get(declared_unit)
    if expected is None:
        return declared_unit, None

    lo, hi = expected
    if lo <= max_dim_raw <= hi:
        return declared_unit, None

    # Mismatch: declared unit doesn't match coordinate magnitudes.
    # Try to infer what's actually going on.
    inferred, _ = _infer_from_dimensions(max_dim_raw)

    if inferred == declared_unit:
        # Dimensions are unusual but inference agrees -- trust the declaration
        return declared_unit, None

    warning = (
        f"Unit mismatch: file declares '{declared_unit}' but max dimension "
        f"{max_dim_raw:.4f} is outside expected range [{lo}-{hi}]. "
        f"Coordinates suggest '{inferred}'. Using '{inferred}'."
    )
    return inferred, warning


def _infer_from_dimensions(max_dim_raw):
    """
    Infer the unit system from raw coordinate magnitudes when the file
    declaration is missing or implausible.

    Returns (inferred_unit, warning_message).
    """
    if max_dim_raw > 5000:
        # Could be micrometres or a very large mm part.
        # Micrometres: a 5mm part reads as 5000.  A 100mm part reads as 100000.
        # mm: a 5000mm part is 5 metres -- possible but unusual for CNC.
        unit = 'micrometre'
        warning = (
            f"No unit declaration found. max_dim={max_dim_raw:.1f} -- "
            f"assuming micrometres (large mm part also possible). "
            f"Verify dimensions in report."
        )
    elif max_dim_raw > 1.0:
        # Most likely mm.  Could also be cm for a very large part, but mm
        # is overwhelmingly more common in CNC STEP files.
        unit = 'mm'
        warning = (
            f"No unit declaration found. max_dim={max_dim_raw:.1f} -- "
            f"assuming millimetres."
        )
    elif max_dim_raw > 0.04:
        # Could be metres (a 40mm part -> 0.04 m) or inches (a 1mm part -> 0.04 in).
        # Metres is more common in STEP files without declarations.
        # Inches would typically have a CONVERSION_BASED_UNIT entity.
        unit = 'metre'
        warning = (
            f"No unit declaration found. max_dim={max_dim_raw:.6f} -- "
            f"assuming metres. If part looks 1000x too large, file may "
            f"be in inches."
        )
    elif max_dim_raw > 0.001:
        unit = 'metre'
        warning = (
            f"No unit declaration found. max_dim={max_dim_raw:.6f} -- "
            f"assuming metres (small part)."
        )
    else:
        unit = 'metre'
        warning = (
            f"No unit declaration found. max_dim={max_dim_raw:.9f} -- "
            f"very small coordinates, assuming metres. Verify dimensions."
        )

    return unit, warning


# ---------------------------------------------------------------------------
# LOAD + NORMALIZE
# ---------------------------------------------------------------------------

def load_step_file(filepath):
    """
    Load a STEP file, detect unit system, normalize to internal mm, and
    return (shape, scale_factor, display_unit).

    Internal representation
    -----------------------
    All downstream code works in model units where:
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

    Supported unit systems
    ----------------------
    mm, cm, um, metre, inch, foot.  Centimetre and micrometre files are
    rescaled to mm-equivalent coordinates before the standard x0.001
    normalization.

    Note on OCC inch handling
    -------------------------
    OCC converts declared inches to mm internally when reading.  So after
    reader.TransferRoots(), coordinates in an inch file are already in mm
    (e.g. a 1-inch cube reads as 25.4 x 25.4 x 25.4 in raw OCC coords).
    The same x0.001 normalization therefore applies to both mm and inch files.
    Only metre files skip the transform.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"STEP file not found: {filepath}")

    # Detect unit BEFORE loading -- scan raw text
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

    # Cross-validate declared unit against actual dimensions
    validated_unit, validation_warning = _validate_unit(declared_unit, max_dim_raw)
    if validation_warning:
        logger.warning(validation_warning)
    if validated_unit != declared_unit and declared_unit != 'unknown':
        logger.warning(
            f"Overriding declared unit '{declared_unit}' -> '{validated_unit}' "
            f"based on coordinate magnitude check"
        )

    scale_factor = 0.001   # always; downstream multiplies by 1000 to get mm

    # -- Metre files: skip spatial transform --
    # Raw coords are in metres; downstream x1000 converts m -> mm.
    if validated_unit == 'metre':
        display_unit = 'metre' if declared_unit == 'metre' else 'mm'
        logger.debug(
            f"Metre file (max_dim={max_dim_raw:.4f}): "
            f"no transform; downstream x1000 converts m -> mm."
        )

    # -- Centimetre files: scale x10 to get mm, then apply x0.001 --
    elif validated_unit == 'cm':
        cm_to_mm = 10.0
        combined_scale = scale_factor * cm_to_mm   # 0.01
        trsf = gp_Trsf()
        trsf.SetScale(gp_Pnt(0, 0, 0), combined_scale)
        shape = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
        display_unit = 'mm'
        logger.debug(
            f"CM file detected (max_dim={max_dim_raw:.1f}): "
            f"applied x{combined_scale} normalization (cm->mm then x0.001)."
        )

    # -- Micrometre files: scale x0.001 to get mm, then apply x0.001 --
    elif validated_unit == 'micrometre':
        um_to_mm = 0.001
        combined_scale = scale_factor * um_to_mm   # 1e-6
        trsf = gp_Trsf()
        trsf.SetScale(gp_Pnt(0, 0, 0), combined_scale)
        shape = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
        display_unit = 'mm'
        logger.debug(
            f"Micrometre file detected (max_dim={max_dim_raw:.1f}): "
            f"applied x{combined_scale} normalization (um->mm then x0.001)."
        )

    # -- MM and inch files: apply standard x0.001 --
    # OCC converts inch -> mm on read, so both use the same transform.
    else:
        trsf = gp_Trsf()
        trsf.SetScale(gp_Pnt(0, 0, 0), scale_factor)
        shape = BRepBuilderAPI_Transform(shape, trsf, True).Shape()
        display_unit = validated_unit if validated_unit in ('mm', 'inch') else 'mm'
        logger.debug(
            f"{display_unit.upper()} file detected (max_dim={max_dim_raw:.1f}): "
            f"applied x{scale_factor} normalization."
        )

    logger.debug(f"display_unit={display_unit!r}")
    return shape, scale_factor, display_unit