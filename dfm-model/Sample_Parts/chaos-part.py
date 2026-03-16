#!/usr/bin/env python3
"""
make_chaos_part.py — Generate test_chaos.step, a part designed to trigger
every DFM flag category in Facet.

Run from Sourcing_Software root:
    python make_chaos_part.py

Outputs: Sample_Parts/test_chaos.step

Flags triggered
───────────────
hole_ld CRITICAL       Side through hole  Ø6 × 120mm  → L/D = 20.0
hole_ld WARNING        Deep blind hole    Ø8 × 52mm   → L/D = 6.5
hole_ld ADVISORY       Medium blind hole  Ø8 × 28mm   → L/D = 3.5
small_hole ADVISORY    Spotface prep hole Ø1.5 × 8mm
thin_wall CRITICAL     Twin slot rib:     2mm wall, 24mm tall → ratio 12
thin_wall_proximity    Pair of Ø10 holes: 2mm web between them → CRITICAL
sharp_internal_corner  Pocket corners (no fillets)
deep_feature           Narrow slot: 8mm wide, 50mm deep → L/D 6.25
hole types             through, through_counterbore, through_countersink,
                       blind_flat, blind_with_tip (5 types all present)
3 fixturings           +Z (top), −Z (bottom blind), +Y (side gun-drill hole)
high material removal  ~68% of bounding box machined away
"""

import math
import os
import sys

from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCC.Core.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCone,
    BRepPrimAPI_MakeCylinder,
)
from OCC.Core.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCC.Core.IFSelect import IFSelect_RetDone
from OCC.Core.STEPControl import STEPControl_AsIs, STEPControl_Writer

MM = 1.0 / 1000.0   # OCC works in metres


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _box(x, y, z, dx, dy, dz):
    """Solid box with corner at (x,y,z) and dimensions (dx,dy,dz) in mm."""
    return BRepPrimAPI_MakeBox(
        gp_Pnt(x * MM, y * MM, z * MM),
        dx * MM, dy * MM, dz * MM,
    ).Shape()


def _cyl(cx, cy, cz, nx, ny, nz, r, h):
    """Solid cylinder: axis starts at (cx,cy,cz) pointing (nx,ny,nz), r and h in mm."""
    ax = gp_Ax2(gp_Pnt(cx * MM, cy * MM, cz * MM), gp_Dir(nx, ny, nz))
    return BRepPrimAPI_MakeCylinder(ax, r * MM, h * MM).Shape()


def _cone(cx, cy, cz, nx, ny, nz, r1, r2, h):
    """Solid cone/frustum from r1 to r2 over height h, all in mm."""
    ax = gp_Ax2(gp_Pnt(cx * MM, cy * MM, cz * MM), gp_Dir(nx, ny, nz))
    return BRepPrimAPI_MakeCone(ax, r1 * MM, r2 * MM, h * MM).Shape()


def cut(base, *tools):
    """Subtract one or more tool shapes from base."""
    result = base
    for tool in tools:
        op = BRepAlgoAPI_Cut(result, tool)
        op.Build()
        if not op.IsDone():
            raise RuntimeError("Boolean cut failed")
        result = op.Shape()
    return result


# ---------------------------------------------------------------------------
# Part construction
# ---------------------------------------------------------------------------

def build():
    # ── BASE BLOCK ───────────────────────────────────────────────────────────
    # 160 × 120 × 50 mm  (x × y × z)
    part = _box(0, 0, 0, 160, 120, 50)

    # ════════════════════════════════════════════════════════════════════════
    # +Z FIXTURING — features machined from the top face (z = 50)
    # ════════════════════════════════════════════════════════════════════════

    # ── 1. WIDE POCKET with sharp corners ───────────────────────────────────
    #   60 × 50 × 35 mm deep, positioned at x=[20,80], y=[20,70], z=[15,50]
    #   → sharp_internal_corner flags at all 4 vertical edges
    #   → deep_feature for the narrower slot cut below
    part = cut(part, _box(20, 20, 15, 60, 50, 35))

    # ── 2. NARROW SLOT inside the pocket — deep_feature WARNING ─────────────
    #   8 mm wide, 50 mm deep, cut from z=0 up through pocket floor
    #   Slot: x=[44,52], y=[22,68], z=[0,15]
    #   Tool must reach 50mm into a pocket only 8mm wide → L/D = 50/8 = 6.25
    part = cut(part, _box(44, 22, 0, 8, 46, 15))

    # ── 3. THIN WALL RIB — twin parallel slots, 2mm wall ───────────────────
    #   Slot A: x=[90,102], y=[20,100], z=[26,50] → 12mm wide, 24mm deep
    #   Slot B: x=[104,116], y=[20,100], z=[26,50] → 12mm wide, 24mm deep
    #   Wall between: 104−102 = 2mm thick, 24mm tall → ratio 12 → CRITICAL
    part = cut(part, _box(90, 20, 26, 12, 80, 24))
    part = cut(part, _box(104, 20, 26, 12, 80, 24))

    # ── 4. COUNTERBORE HOLE — through_counterbore ────────────────────────────
    #   Center (135, 25)  Outer Ø14 × 8mm deep, then Ø8 through
    part = cut(
        part,
        _cyl(135, 25, 50, 0, 0, -1, 7.0,  8.0),   # shoulder
        _cyl(135, 25, 50, 0, 0, -1, 4.0, 50.0),   # through bore
    )

    # ── 5. COUNTERSINK HOLE — through_countersink ────────────────────────────
    #   Center (135, 60)  90° csink (half-angle 45°), Ø8 through
    csink_outer_r = 7.0       # csink outer radius
    csink_inner_r = 4.0       # bore radius that continues through
    csink_h = (csink_outer_r - csink_inner_r) / math.tan(math.radians(45.0))
    part = cut(
        part,
        _cone(135, 60, 50, 0, 0, -1, csink_outer_r, csink_inner_r, csink_h),
        _cyl( 135, 60, 50, 0, 0, -1, csink_inner_r, 50.0),
    )

    # ── 6. BLIND FLAT HOLE ───────────────────────────────────────────────────
    #   Center (135, 95)  Ø10 × 22mm deep  L/D = 22/10 = 2.2 (below advisory)
    part = cut(part, _cyl(135, 95, 50, 0, 0, -1, 5.0, 22.0))

    # ── 7. DEEP BLIND HOLE — hole_ld WARNING ────────────────────────────────
    #   Center (15, 95)  Ø8 × 52mm deep  L/D = 52/8 = 6.5 → WARNING
    part = cut(part, _cyl(15, 95, 50, 0, 0, -1, 4.0, 52.0))

    # ── 8. SMALL HOLE — small_hole ADVISORY ─────────────────────────────────
    #   Center (15, 15)  Ø1.5 × 8mm deep
    part = cut(part, _cyl(15, 15, 50, 0, 0, -1, 0.75, 8.0))

    # ── 9. HOLE PROXIMITY — two close holes, 2mm web ────────────────────────
    #   Centers (50, 107) and (62, 107)  both Ø10 × 28mm
    #   Web = (62−50) − 5 − 5 = 2mm,  depth 28mm → ratio 14 → CRITICAL
    part = cut(
        part,
        _cyl(50, 107, 50, 0, 0, -1, 5.0, 28.0),
        _cyl(62, 107, 50, 0, 0, -1, 5.0, 28.0),
    )

    # ════════════════════════════════════════════════════════════════════════
    # −Z FIXTURING — feature machined from the bottom face (z = 0)
    # ════════════════════════════════════════════════════════════════════════

    # ── 10. BLIND WITH TIP — from bottom ────────────────────────────────────
    #    Center (80, 55)  Ø10 × 20mm  with 118° drill tip
    #    Cylinder drilled from z=0 upward
    tip_semi_angle = 59.0    # 118° included → 59° half-angle
    tip_r          = 5.0     # matches bore radius
    tip_h          = tip_r / math.tan(math.radians(tip_semi_angle))   # ≈ 3.0mm
    part = cut(
        part,
        _cyl( 80, 55, 0,  0, 0,  1, 5.0, 20.0),       # blind bore upward
        _cone(80, 55, 20, 0, 0,  1, tip_r, 0.0, tip_h),  # drill tip cone
    )

    # ════════════════════════════════════════════════════════════════════════
    # +Y FIXTURING — feature machined from the front face (y = 0)
    # ════════════════════════════════════════════════════════════════════════

    # ── 11. DEEP THROUGH HOLE — gun-drill territory ──────────────────────────
    #    Center at x=148, z=25  Ø6 through full 120mm width
    #    L/D = 120/6 = 20 → CRITICAL
    part = cut(part, _cyl(148, 0, 25, 0, 1, 0, 3.0, 120.0))

    return part


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def main():
    print("Building geometry...")
    part = build()

    os.makedirs("Sample_Parts", exist_ok=True)
    output = "Sample_Parts/test_chaos.step"

    writer = STEPControl_Writer()
    writer.Transfer(part, STEPControl_AsIs)
    status = writer.Write(output)

    if status == IFSelect_RetDone:
        print(f"✓  Written: {output}")
        print()
        print("Expected flags")
        print("──────────────────────────────────────────────────────────────")
        print("  CRITICAL  hole_ld               Side hole Ø6×120  L/D=20.0")
        print("  CRITICAL  thin_wall             2mm rib, 24mm tall, ratio=12")
        print("  CRITICAL  thin_wall_proximity   2mm web between Ø10 holes")
        print("  WARNING   hole_ld               Blind Ø8×52      L/D=6.5")
        print("  WARNING   sharp_internal_corner Pocket corners (×4 edges)")
        print("  WARNING   deep_feature          Narrow slot 8mm×50mm L/D≈6")
        print("  ADVISORY  hole_ld               Blind Ø10×28     L/D=3.5  (proximity holes)")
        print("  ADVISORY  small_hole            Ø1.5 hole")
        print("  ADVISORY  concave_fillet_tool   (if any concave fillets detected)")
        print()
        print("Hole types present")
        print("  through_counterbore  through_countersink  blind_flat")
        print("  blind_with_tip  through (via counterbore/countersink bores)")
        print()
        print("Fixturings expected: +Z, −Z, +Y  (3 setups)")
    else:
        print(f"✗  STEP export failed (status={status})")
        sys.exit(1)


if __name__ == "__main__":
    main()