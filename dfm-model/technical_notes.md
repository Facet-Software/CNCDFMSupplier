# Technical Design Notes

## Architecture Overview

The current MVP is a single-file rule-based geometry extractor. It operates on STEP files using `python-occ` (OpenCASCADE Python bindings).

## Core Pipeline

```
STEP file
   ↓
load_step_file()         — reads file, detects scale mismatch, applies correction
   ↓
get_bounding_box()       — overall part envelope in mm
count_planar_faces()     — flat surface count (machining setup indicator)
detect_cylindrical_features()  — scans all faces for cylinders (holes/fillets) and cones
   ↓
group_hole_sections()    — clusters coaxial faces into hole profiles
classify_through_blind() — endpoint probes + binary search to determine hole depth/type
print_hole_summary()     — final hole type classification per profile
```

## Key Design Decisions

### Cone Geometry via Bounding Circle Edges
The parametric v-range on OCC cone surfaces is unreliable for computing actual geometry bounds. Instead, we iterate circular edges on each cone face and use their center positions projected onto the cone axis to determine v_min / v_max and the actual radii at each end.

### Axis Normalization (`flip_section`)
When grouping coaxial sections, opposite-direction faces must be normalized to a common axis direction so v-ranges can be compared directly. `flip_section()` reverses the axis direction and negates/swaps v_min/v_max accordingly.

The pre-flip axis is preserved under `_original` so that the apex burial probe always uses the cone's native direction — critical for correctly classifying `blind_with_tip` holes.

### Apex Burial Probe
Standard endpoint probing (step just beyond v_min/v_max) can be fooled by cones: the probe steps into the cone's hollow void and returns `TopAbs_OUT`, incorrectly classifying the hole as through. The apex burial probe steps a small epsilon beyond the cone tip using the cone's own axis and tests whether that point is inside solid. If buried → `blind_with_tip`.

### Solid Classifier for Hole vs Boss
Full-span cylinders (u_span ≈ 2π) are classified as holes only if a point sampled on their axis is `TopAbs_OUT` (i.e., the cylinder is a void in the solid, not a protrusion). Partial-span cylinders are fillets.

### Binary Search for Blind Hole Depth
For flat-bottomed blind holes, we binary-search along the hole axis (60 iterations, ~1e-18 precision) to find the exact solid boundary, giving accurate depth measurements independent of bounding box projection.

## Planned Extensions

- **Thin wall detection**: flag walls below a threshold thickness relative to part size
- **Fixturing analysis**: count unique surface normal clusters to estimate setup count
- **GD&T extraction**: parse engineering drawings and map tolerances to STEP features
- **Assembly support**: iterate solids in compound shapes, map faces to parent solid, pass correct solid to `BRepClass3d_SolidClassifier`
- **ML pipeline**: use rule-based labels as training data; train classifiers once sufficient labeled parts accumulate
