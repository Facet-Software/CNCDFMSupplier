# Sourcing AI — Mechanical Parts Manufacturability Analyzer

A Python tool that parses CAD STEP files and extracts manufacturability profiles for milled mechanical parts — without exposing raw IP. Designed as the analytical backbone of a competitive supplier sourcing platform.

## The Problem

Engineering companies sourcing complex mechanical parts face:
- **Supplier monopolies** — once a supplier is onboarded (expensive, time-consuming), companies lose bargaining power
- **Information asymmetry** — buyers have limited visibility into market pricing
- **IP exposure risk** — sharing raw CAD files with prospective suppliers is a liability

Existing services like Xometry handle made-to-order prototypes, but not production assemblies.

## The Solution

A platform where buyers upload CAD files and receive AI-generated manufacturability profiles — abstracted specs that describe *what* a part requires to manufacture without revealing *how* it was designed. Suppliers then bid competitively on those profiles.

## Current MVP: `geom_extractor.py`

A rule-based STEP file parser built on `python-occ` that extracts:

| Feature | Details |
|---|---|
| **Bounding box** | X/Y/Z dimensions in mm, with automatic scale mismatch detection (metres vs mm) |
| **Planar faces** | Total count of flat surfaces |
| **Holes** | Classified by type: `through`, `through_counterbore`, `through_countersink`, `blind_flat`, `blind_with_tip` |
| **Fillets** | Detected as `concave` or `convex`, with radius and position |

### Hole Classification Logic

- Full-span cylinders classified as holes vs bosses/protrusions via solid classifier
- Partial cylinders classified as fillets by angular span
- Cones detected via bounding circle edges (more reliable than parametric v-range)
- Blind-with-tip holes confirmed via apex burial probe into solid
- Axis normalization via `flip_section()` when grouping opposite-direction faces
- Binary search used to measure blind hole depth precisely

## Installation

```bash
pip install pythonocc-core
```

> Requires Python 3.x and a working `python-occ` / `pythonocc-core` installation.

## Usage

```python
from geom_extractor import process_step_for_basics

process_step_for_basics("/path/to/your/part.step")
```

Or run directly:

```bash
python geom_extractor.py
```

Edit the `example_file` path at the bottom of `geom_extractor.py` to point to your STEP file.

### Example Output

```
Successfully loaded: bracket1.step
Raw dimensions: dx=120.0, dy=80.0, dz=40.0
No scale mismatch detected.

Bounding box (mm): x=0.0 to 120.0, y=0.0 to 80.0, z=0.0 to 40.0
Overall dimensions: dx=120.0, dy=80.0, dz=40.0

Total planar faces: 12

--- Hole Classification Summary ---
  Hole 1 (faces [4, 5]): type=through_counterbore, r=4.00 mm, depth=40.0 mm
  Hole 2 (faces [9]):    type=blind_flat, r=3.00 mm, depth=15.0 mm
  Hole 3 (faces [14, 15]): type=blind_with_tip, r=2.50 mm, depth=20.0 mm
```

## Project Structure

```
sourcing-ai/
├── geom_extractor.py     # Core STEP file parser
├── tests/                # Unit tests (coming soon)
├── sample_parts/         # Example STEP files for testing
├── docs/                 # Technical notes and design decisions
└── README.md
```

## Roadmap

- [ ] Thin wall detection
- [ ] Fixturing complexity analysis (setup count, access directions)
- [ ] Tolerance / GD&T extraction from engineering drawings mapped to STEP features
- [ ] Assembly support (multiple solids)
- [ ] ML-based classification once labeled data accumulates
- [ ] Supplier network and bidding interface

## Key Technical Decisions

- **Rule-based first, ML later** — rules are interpretable and require no training data upfront
- **Cone geometry via bounding circle edges** — more reliable than parametric v-range
- **Apex burial probe** — uses the cone's native pre-flip axis to correctly detect blind-with-tip holes
- **Single solid only for now** — assembly support planned (iterate solids, map faces to parent solid)

## License

Private / Proprietary
