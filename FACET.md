# Facet — Master Documentation

> From first principles to every line of code.

---

## Table of Contents

1. [The Original Idea — The Marketplace](#1-the-original-idea--the-marketplace)
2. [Why We Pivoted — The Supplier-Side Tool](#2-why-we-pivoted--the-supplier-side-tool)
3. [The Problem We're Solving](#3-the-problem-were-solving)
4. [The Solution](#4-the-solution)
5. [The Market](#5-the-market)
6. [Why Suppliers Would Use This](#6-why-suppliers-would-use-this)
7. [Competitive Landscape](#7-competitive-landscape)
8. [Codebase Architecture](#8-codebase-architecture)
9. [The Pipeline — Step by Step](#9-the-pipeline--step-by-step)
10. [Feature Extraction — Deep Dive](#10-feature-extraction--deep-dive)
11. [Setup and Fixturing Analysis](#11-setup-and-fixturing-analysis)
12. [DFM Analysis](#12-dfm-analysis)
13. [The Report](#13-the-report)
14. [Key Algorithms and Why We Chose Them](#14-key-algorithms-and-why-we-chose-them)
15. [Known Limitations](#15-known-limitations)
16. [Pitfalls — Critical Knowledge for Writing New Code](#16-pitfalls--critical-knowledge-for-writing-new-code)
17. [Future Additions](#17-future-additions)
18. [Configuration Reference](#18-configuration-reference)
19. [Unit Detection and Display](#19-unit-detection-and-display)
20. [Tessellation and Geometry Export](#20-tessellation-and-geometry-export)
21. [Report Schema — Current Specification](#21-report-schema--current-specification)
22. [HTML Report — 3D Viewer](#22-html-report--3d-viewer)
23. [HTML Report — Fixture Interaction](#23-html-report--fixture-interaction)
24. [HTML Report — PDF Export](#24-html-report--pdf-export)
25. [HTML Report — Excel Export](#25-html-report--excel-export)

---

## 1. The Original Idea — The Marketplace

The original concept was a two-sided marketplace for precision mechanical parts sourcing. The problem it addressed was structural: engineering companies that source complex machined parts face supplier monopolies once a supplier has been onboarded. Onboarding a precision CNC supplier is expensive and slow — qualification, ITAR agreements, first article inspection, process audits. Once a supplier is in, the buyer has no negotiating leverage and no visibility into whether the pricing they're paying is competitive. The supplier knows this.

At the same time, buyers couldn't send raw CAD files to prospective new suppliers to get competitive bids, because the CAD file contains the design intent — the IP. Sending it to five shops to get quotes is a real liability.

The marketplace concept: buyers upload CAD files and receive an **abstracted manufacturability profile** — a description of *what* a part requires to manufacture, without revealing *how* it was designed. Suppliers bid competitively on those profiles. The platform takes a transaction cut.

This was a clean idea. The core insight — that you can describe manufacturability without exposing IP — is genuinely novel. Nothing does this end-to-end today.

---

## 2. Why We Pivoted — The Supplier-Side Tool

The marketplace has a cold-start problem. To be valuable to buyers, you need suppliers. To attract suppliers, you need parts flowing through the platform. This is a classic two-sided network problem, and it's hard.

The pivot is **sequencing**, not abandonment. Instead of building both sides simultaneously, we're building the supplier side first as a standalone product that suppliers want independently of any marketplace.

The insight: job shops and contract manufacturers already struggle with quoting. They receive STEP files, open them in CAD, manually inspect geometry, estimate setup count, mentally flag manufacturability issues, and write a quote. This takes hours per part. For a shop doing 20–30 RFQs per week, it's a significant fraction of their estimating labor. And they often get it wrong — underquoting complex geometry, missing a setup, not noticing a thin wall until they're already cutting metal.

A tool that reads the STEP file and produces a structured analysis — setups, holes, DFM flags, material removal, tool change estimates — in under a minute is directly valuable to the supplier regardless of any marketplace. They use it for every quote they write. It becomes part of their workflow.

Once we have a supplier base using the tool daily, we have the supply side of the marketplace already built. Adding buyer-facing functionality on top is an evolution, not a rebuild.

---

## 3. The Problem We're Solving

Quoting precision CNC parts is a geometry reasoning problem, and humans are doing it manually at scale.

A machinist receives a STEP file. To write an accurate quote they need to know:

- How many setups does this require? Which faces are machined from which direction?
- What's the minimum tool diameter each setup can reach into?
- Are there any features that are going to cause problems — deep holes, thin walls, sharp internal corners, small holes, deep pockets?
- What type of machine does this need — 3-axis standard, 3-axis with special fixture, 5-axis indexed, 5-axis continuous?
- How much material is being removed? (Drives cycle time.)
- What kinds of holes are there, and how many of each?

An experienced machinist answers all of these by reading the geometry. The same reasoning, applied systematically, is what this tool does.

The secondary problem it solves: design review. Engineers often design features that are difficult or impossible to machine as drawn. Sharp internal corners, holes drilled at steep angles to an accessible surface, walls too thin to hold rigidity during cutting. A supplier who catches these before quoting saves everyone time and money. A supplier who catches them *after* first article inspection has already spent the money.

---

## 4. The Solution

Facet is a Python CLI tool that reads a STEP file and produces a structured analysis report. It does not require the user to interact with a GUI, learn any software, or configure anything per-part. Drop in a STEP file, run the command, get a report.

The report surfaces:

- **Bounding box and material removal** — overall dimensions, solid volume vs. bounding box volume, percentage of material machined away
- **Setup count and fixturing plan** — which directions the part must be approached from, what machine type this implies
- **Hole inventory** — every hole classified by type (through, counterbore, countersink, blind flat, blind with drill tip), with diameter, depth, and L/D ratio
- **Minimum tool diameter per fixturing** — the tightest geometric constraint on tooling in each setup
- **DFM flags** — manufacturing issues grouped by type (sharp corners, thin walls, deep holes, partial holes, proximity webs between holes) with severity levels

The output is a self-contained HTML file that opens in any browser with no dependencies.

---

## 5. The Market

The primary target is precision aerospace, medical device, and semiconductor equipment job shops — suppliers doing lower-volume, higher-complexity work. These are shops where:

- Parts have tolerances in the 0.001–0.005" range
- Setup count directly drives cost
- Quoting errors are expensive (underquoting a 5-axis part as 3-axis is a serious margin problem)
- DFM issues cause real rework and first-article failures

This is deliberately not a fit for the prototype/on-demand market (Xometry, Protolabs, Fictiv). Those platforms handle high-volume, lower-complexity work where the economics favor commodity quoting. The precision production market is where human judgment is currently doing the work that Facet automates.

---

## 6. Why Suppliers Would Use This

**Time savings on every quote.** A supplier currently spends 30–90 minutes per complex part manually extracting the information Facet produces in seconds. At 20 quotes per week, that's 10–30 hours of estimating labor per week. Facet doesn't replace the machinist's judgment — it replaces the manual reading and transcription work.

**Catch DFM issues early.** A thin wall or a sharp internal corner caught at quoting time costs nothing to address. The same issue caught at first article costs the shop real money and strains the customer relationship. Facet surfaces these automatically.

**Standardize quoting language.** A structured analysis gives the supplier's estimator a consistent starting point rather than starting from a blank page. Setup counts, tool change estimates, and hole inventories are extracted the same way every time.

**Quote more aggressively on complex parts.** Suppliers often add margin to complex-looking parts because they can't quickly tell if the complexity is real or apparent. A supplier who can quickly confirm that a complicated-looking part is actually 3-axis standard with clean geometry can price it more accurately.

---

## 7. Competitive Landscape

| Competitor | What They Do | Why They Don't Do What Facet Does |
|---|---|---|
| **Paperless Parts** | Quoting workflow / CRM with geometry awareness | Fundamentally a workflow tool. DFM is shallow, automated cycle time estimation is unreliable for complex 5-axis geometry (confirmed by machinists on Practical Machinist forums — 50%+ of complex parts have unrecognizable features). P3L scripting for shop customization is a significant burden. |
| **Xometry / Protolabs** | Are the supplier; automated quoting for their own shop | No incentive to help buyers find competitive alternatives. Not supplier-facing. |
| **Boothroyd Dewhurst / DFMPro** | Sophisticated DFM rule engines | PLM-integrated, expensive, report-only — no connection to supplier workflow or quoting. Designed for design teams, not shops. |
| **CAD-embedded DFM (NX, SolidWorks Costing)** | DFM within the design tool | Requires full native CAD (IP exposure). Cost models are generic. Designed for designers, not estimators. |

The gap Facet occupies: **geometry intelligence for the supplier quoting workflow**. Deep enough to be useful on complex parts, fast enough to run on every RFQ, structured enough to connect to downstream quoting tools.

---

## 8. Codebase Architecture

```
sourcing/
├── config.py               All tunable thresholds — import from here, never hardcode
├── loader.py               STEP file loading + scale normalization
├── pipeline.py             Orchestrates full pipeline; to_report_dict() for UI
├── utils/
│   └── geometry.py         Shared geometric primitives (ray cast, adjacency, flip_section...)
├── features/
│   ├── planar.py           Planar face detection, outward normal, chamfer classification
│   ├── cylindrical.py      Hole cylinders, fillets, cones, detect_partial_holes()
│   ├── thin_walls.py       Three-method thin wall detection + hole proximity webs
│   └── pockets.py          Pocket detection (archived — see note below)
├── classify/
│   └── holes.py            Through/blind classification, approach direction, hole_type
├── drawing/
│   ├── __init__.py
│   ├── parser.py           PDF text extraction — tolerances, GD&T, threads, surface finish
│   └── thread_match.py     Maps drawing thread callouts to STEP holes by tap drill diameter
├── analysis/
│   ├── setup.py            Hemisphere set-cover → fixturing plan, accessibility verification
│   ├── tool_access.py      Min tool diameter per fixturing (fillet + planar + ray cast)
│   ├── fixturing_faces.py  Rest faces, clamp pairs, workholding classification
│   ├── feature_summary.py  Per-fixturing feature counts for quoting
│   └── dfm.py              All DFM flag checks + fixture annotation post-pass
└── reporting/
    ├── summary.py          Debug log output
    └── html_report.py      Self-contained HTML report generator (PDF + Excel export)
```

**Dependency flow** (each module only imports from modules above it in the list):

```
config.py
  ↓
loader.py → utils/geometry.py
  ↓
features/planar.py
features/cylindrical.py
features/thin_walls.py
  ↓
classify/holes.py
  ↓
analysis/setup.py
analysis/tool_access.py
analysis/feature_summary.py
analysis/dfm.py
  ↓
pipeline.py
reporting/html_report.py
```

---

## 9. The Pipeline — Step by Step

The entry point is `run.py`, which calls `process_step_for_basics(filepath)` in `pipeline.py`, then `to_report_dict()`, then `generate_report_html()`.

### Step 1 — Load and normalize (`loader.py`)

The STEP file is read with `STEPControl_Reader`. The loader then detects whether the model is in millimetres or metres by checking the bounding box magnitude:

- If `max_dim > 1.0` → model is in mm. Apply a `×0.001` spatial transform to normalize all coordinates to model units where `1 unit = 0.001 mm`. This way, `value * 1000 = mm` everywhere downstream.
- If `max_dim ≤ 1.0` → model is already in metres. No transform needed; `value * 1000 = mm` already holds.

The result is that **all downstream code always multiplies by 1000 to get mm**, regardless of the input unit system. The `scale_factor` (always `0.001`) is passed downstream for area correction: areas from `BRepGProp.SurfaceProperties` come back in `(model_units)²`, so dividing by `scale_factor²` gives `mm²`.

### Step 2 — Bounding box and volume (`pipeline.py`)

`get_bounding_box()` calls `brepbndlib.Add()` and returns both the mm dimensions and the raw model-unit extents. The raw extents are kept because the deep feature depth calculation needs them in model units for dot-product comparisons with face centroids.

`get_solid_volume()` uses `brepgprop.VolumeProperties()`. The result is divided by `scale_factor³` to get `mm³`. Material removal percentage is derived as `(bbox_volume - solid_volume) / bbox_volume`.

### Step 3 — Face adjacency (`utils/geometry.py`)

`build_face_adjacency()` traverses all faces and edges once, building:
- `face_list`: ordered list of `TopoDS_Face` objects
- `edge_to_faces`: `edge_id → [face_idx, face_idx, ...]`
- `face_to_edges`: `face_idx → [(edge_id, TopoDS_Edge), ...]`
- `global_edge_map`: `TopTools_IndexedMapOfShape` for edge lookup

**Critical implementation detail**: `TopTools_IndexedMapOfShape.IsEqual()` includes edge orientation. The same physical edge appears as `FORWARD` on one face and `REVERSED` on the adjacent face. If you add both orientations, they get different indices and the shared edge never appears shared. The fix is to always normalize edges to `TopAbs_FORWARD` before adding to the map and before any lookup. This is done with `edge.Oriented(TopAbs_FORWARD)` everywhere the edge map is touched.

This adjacency structure is computed once and shared across all downstream modules that need topological relationships.

### Step 4 — Planar face detection (`features/planar.py`)

Iterates all faces. For each planar face:

1. Gets the plane normal from `BRepAdaptor_Surface.Plane().Axis().Direction()`
2. Determines true outward direction by probing a point `ε` along the normal from the centroid and checking `BRepClass3d_SolidClassifier`. If the probe returns `IN` (inside solid), the normal is reversed.
3. Computes area via `brepgprop.SurfaceProperties()`, corrected by `scale_factor²`
4. Classifies as chamfer or not (see below)

**Chamfer classification** requires two conditions:
1. The face normal must be within `SETUP_CHAMFER_ANGLE_TOL_DEG` (5°) of a standard chamfer angle (30°, 45°, or 60°) from any principal axis
2. The face must be geometrically strip-shaped: `shorter_dimension / longer_dimension < SETUP_CHAMFER_MAX_ASPECT_RATIO` (0.5) AND `shorter_dimension / parent_edge_length < SETUP_CHAMFER_WIDTH_RATIO` (0.15)

The width check is done by finding all straight shared edges longer than the face's short dimension, then verifying the ratio. This prevents large bevelled surfaces from being misclassified as chamfers. Chamfer faces are excluded from the setup set-cover (they don't require their own fixturing direction) and from the planar face count shown to suppliers.

### Step 5 — Cylindrical feature detection (`features/cylindrical.py`)

Iterates all faces. Classifies each cylindrical or conical face:

**Full-revolution cylinders** (`u_span ≈ 2π`): probes the axis midpoint with `BRepClass3d_SolidClassifier`. If `OUT` → void-facing → hole wall cylinder. If `IN` → material-facing → boss/protrusion, skipped.

**Partial cylinders** (`u_span < 2π`): classified as fillets. Concavity is determined by the same solid classifier probe. `convex` (probe returns `IN` = material behind) vs `concave` (probe returns `OUT` = void behind). Convex partial cylinders are further sub-classified as `edge_round` vs `fillet`:
- `edge_round`: radius ≥ 5mm AND height/radius < 3 — these are break-edge features machined with a standard end mill
- `fillet`: everything else — these require special tooling consideration

**Cones**: classified as drill-tip cones (minor radius ≈ 0), truncated void-facing cones (countersink geometry), or external chamfers (material-facing, standard angle). Non-standard material-facing cones are skipped.

Coaxial, contiguous sections are grouped into **hole profiles** by `_group_hole_sections()`. Two sections are coaxial if their axis lines (not just directions) are within `tol_axis` — this is checked by computing the perpendicular distance between the infinite axis lines, not just the direction dot product. This prevents cone apexes (which can be far from the physical feature) from being incorrectly matched.

Each hole profile carries:
- `sections`: list of constituent cylinder/cone dicts
- `rep_radius_mm`: smallest cylinder radius (the drill size)
- `axis_direction`, `axis_location`, `dir_vec`, `get_point_along_axis`
- `v_min_overall`, `v_max_overall`: parametric extent along the axis

**Partial hole detection** (`detect_partial_holes()`): for each hole profile, samples a circumferential ring at `n_angles` evenly spaced angles and `n_depths` depths, at radius `+ max(20%, 0.8mm)` from the bore axis. The probe distance must be physically meaningful — 5% was too small, catching surface noise and nearby external geometry. Uses the section-specific radius at each depth (not `rep_radius_mm`) to avoid false positives on counterbore holes where the wider shoulder would appear void. A bbox guard filters out voids that are simply "outside the part" from a nearby external face. Any void within the bbox indicates a feature has broken through the bore wall.

### Step 6 — Thin wall detection (`features/thin_walls.py`)

Three independent detection methods, results merged and clustered:

**Method A — Planar opposing pairs**: iterates all pairs of planar faces with antiparallel normals (dot < −0.99). Computes perpendicular distance between planes as the projection of the centroid-to-centroid vector onto the face normal. If this distance is below `THIN_WALL_MAX_THICKNESS_MM` and the `height / thickness` ratio exceeds the warning threshold, records a thin wall sample. Height is the largest in-plane extent of either face (`face_local_height()`).

**Method B — Concentric cylinders**: for pairs of concave partial cylinders (fillets) sharing the same axis, wall thickness = `|r_outer − r_inner|`. No ray casting needed — exact geometry. Coaxiality is verified by perpendicular axis-line distance, not just direction.

**Method C — Ray casting with Nelder-Mead refinement**: for non-planar, concave, non-hole-wall faces, samples an `N×N` UV grid and shoots inward rays using `IntCurvesFace_ShapeIntersector`. Any sample within the thickness threshold triggers a Nelder-Mead simplex search in UV space to find the local minimum thickness (the worst point on that surface). This is important because a single grid sample may not hit the thinnest point.

Samples from all three methods are clustered: first by shared face index (union-find), then spatially by centroid distance (< `THIN_WALL_CLUSTER_DIST_MM`). Each region reports minimum thickness, maximum aspect ratio, severity, centroid, contributing faces, and detection methods.

**Hole proximity webs**: separately computed by `detect_hole_proximity_walls()`. For every pair of hole profiles, computes web thickness = `axis_separation − r_A − r_B`. Handles both parallel and skew axes. Skew case: clamps to physical hole extents to avoid measuring closest approach at a point outside the actual hole bore. Coaxial pairs (counterbore + through-hole sharing an axis) are skipped.

### Step 7 — Hole classification (`classify/holes.py`)

`classify_through_blind()` determines for each hole whether it is through or blind by probing just beyond both ends of the cylinder span with `BRepClass3d_SolidClassifier`:

- `v_min − ε` probe: if `IN` → closed at min end
- `v_max + ε` probe: if `IN` → closed at max end

If one end is closed → blind, `closed_end` set accordingly. If neither → through.

Special case — **blind_with_tip**: if the hole has a cone section, `probe_apex_burial()` checks whether the cone apex is buried in solid. This is necessary because some geometry (counterbore + through bores) has cone sections that are open. The apex probe uses the cone's **pre-flip native axis direction** — critical because `flip_section()` reverses the axis when grouping opposite-direction sections, and the probe must go in the original direction to work correctly. After apex burial is confirmed, a larger-offset probe (`2% of bounding box`) determines `closed_end` — the small `ε` probe fails near the apex due to numerical instability.

For counterbore/countersink holes, `approach_direction` is set to the entry side (the larger-diameter end) and `is_directional_through = True`. This tells the set-cover to use signed dot product rather than `abs(dot)` — you can only approach a counterbore from the entry side.

`classify_hole_type()` then maps the combination of `is_through`, `has_tip`, cone sections, and multiple cylinder radii to the six type strings: `through`, `through_counterbore`, `through_countersink`, `blind_flat`, `blind_with_tip`, `blind_countersink`.

### Step 8 — Setup analysis (`analysis/setup.py`)

The core geometric reasoning step. Goal: find the minimum set of approach directions that covers every machining feature.

**Coverage model**: a face normal `N` is covered by approach direction `A` if `dot(N, A) ≥ FACE_COVER_MIN` (−0.05). This means walls (dot ≈ 0) are reachable by side-milling from any approach direction that covers adjacent faces. Holes require `dot ≥ cos(SETUP_HOLE_CRITICAL_DEG)` (cos 15° ≈ 0.966) — the critical threshold, not an arbitrary constant. This is important: the coverage threshold must match the concern threshold, or holes at, say, 18° off +Z will be simultaneously "covered" and "critically wrong".

**Phase 1 — Hole-driven set-cover**: only holes drive the fixturing count in this phase. Face normals score candidates (weighted by area) but are not items that need covering — this prevents vertical walls from forcing unnecessary fixturing directions. The greedy algorithm seeds with the dominant principal axis (most area-weighted face normals), then iteratively picks the candidate direction that covers the most uncovered machining items while maximizing face coverage score.

**Phase 2 — Face-driven additions**: after Phase 1, any face genuinely inaccessible from all current approach directions (e.g., bottom face requiring a flip) adds a new fixturing. Principal-axis faces are only considered covered by principal-axis approaches — a 45° approach that technically has dot > −0.05 with a flat bottom face does not count as "covering" it, because no machinist would tilt a part 45° just to reach a flat bottom face.

**Assignment**: each face and hole is assigned to its best-covering fixturing. For faces, principal-axis fixturings are preferred unless a non-principal fixturing has a significantly better fit (dot ≥ 0.9, more than 0.2 better than the best principal). For holes, best-covering by dot product.

**Post-processing**: clusters are sorted by coverage (most faces first), then faces are reassigned to the earliest fixturing that can access them (side-millable walls belong to the first setup that can reach them). Through holes are deduplicated — they appear in both +Z and −Z clusters, but are kept only in the fixturing where their deviation is smallest. Fillets are post-assigned by neighbor vote — the fixturing that contains most of a fillet's adjacent faces gets the fillet.

**Classification**: each fixturing is classified as `3-axis-standard` (approach within 10° of a principal axis), `3-axis-special-fixture` (approach within 2° of a standard fixture angle: 30°, 45°, 60°), `5-axis-indexed` (any other angle, or multiple special-fixture setups), or `5-axis-continuous` (freeform surfaces with significant normal variation).

### Step 9 — Tool access (`analysis/tool_access.py`)

Three passes per fixturing to find the minimum tool diameter that can reach every assigned feature:

**Fillet pass**: for each axis-aligned concave fillet in this fixturing, tool diameter ≤ `2 × radius`. Non-axis-aligned concave fillets (ball-nose) also constrain tool diameter.

**Planar pass**: for wall-face pairs with antiparallel normals, perpendicular distance between planes = gap width. The midpoint is probed with `BRepClass3d_SolidClassifier` to verify the gap actually opens into a real pocket interior (not through the part body).

**Ray cast pass**: for non-planar faces (cone surfaces, curved pockets), samples an `N×N` UV grid, projects the outward normal onto the approach-perpendicular plane to get the ray direction, then shoots the ray and measures first-hit distance.

All three produce constraints in mm. The minimum across all constraints is `min_tool_dia_mm` for the fixturing.

### Step 10 — DFM analysis (`analysis/dfm.py`)

Seven independent checks, each returning a list of flag dicts. All flags have `severity` (critical/warning/advisory), `category` (string tag), `message` (human-readable), and `detail` (dict of numeric data).

Checks: hole L/D, small holes, ball-nose required (fillets), concave fillet tool diameter constraint, sharp internal corners, deep features (floor face depth / min tool dia), thin walls, hole proximity webs, partial holes.

**Sharp corner detection** deserves special mention. A naive approach uses face centroid to determine concavity, but centroids of non-convex (L-shaped, U-shaped) faces can lie outside the face boundary, producing wrong results. The algorithm instead uses a **near-edge sample**: compute a point on face B a small distance from the shared edge (in face B's plane, perpendicular to the edge). The sign of `dot(n_A, p_B_sample − edge_midpoint)` determines concavity. The sign of the in-plane direction is resolved using the centroid (which even for non-convex faces is guaranteed to be on the correct side of any edge that bounds the face).

---

## 10. Feature Extraction — Deep Dive

### Coordinate system and model units

OCC (OpenCASCADE) works in whatever units the STEP file specifies. After the loader's normalization, coordinates are in `model_units` where `1 model_unit = 0.001 mm`. So:
- `length_mm = occ_length × 1000`
- `area_mm2 = occ_area / scale_factor² = occ_area × 10⁶`
- `volume_mm3 = occ_volume / scale_factor³ = occ_volume × 10⁹`

### Parametric axis representation

Hole and fillet cylinders are represented by an axis: a location point + direction vector + parametric function `get_point_along_axis(t)` that returns `location + t × direction`. The `v_min` and `v_max` values are the parameter values at the ends of the cylinder, measured along this axis. For a cylinder of height `h`, `v_max − v_min = h / 1000` (in model units).

`flip_section()` reverses the direction when grouping sections that were found with opposite axis orientations. The `v` values are negated and swapped accordingly. The `_original` key preserves the pre-flip state so apex burial probes always use the original native direction.

### Why `BRepClass3d_SolidClassifier` is central

The classifier probes a point and returns whether it's `IN`, `OUT`, or `ON` the solid. This is the fundamental geometric test underlying almost every detection:

- Hole vs. boss: is the cylinder axis midpoint inside or outside?
- Through vs. blind: is the point past the end of the cylinder inside or outside?
- Thin wall: is a point inward from a face surface inside solid?
- Chamfer convexity: is a point inward from the face surface inside or outside?
- Partial hole: is a point at radius + ε from the bore axis inside or outside?

The classifier is relatively expensive to create (requires building a shape representation) but fast to query once built. It's initialized once per shape in modules that use it heavily.

### The `IntCurvesFace_ShapeIntersector` for ray casting

Used in tool access and thin wall detection. Pre-built once per shape (`intersector.Load(shape, tol)`), then queried for each ray (`intersector.Perform(line, epsilon, max_dist)`). Returns all intersection points sorted by parameter. The epsilon lower bound prevents the ray from self-intersecting the origin face.

---

## 11. Setup and Fixturing Analysis

### The hemisphere set-cover intuition

Think of the Gauss map: every face normal is a point on the unit sphere. The set of all face normals for a part describes which directions material needs to be approached from to machine every surface.

A single fixturing "covers" a hemisphere: any face whose outward normal has `dot(n, approach) ≥ −0.05` can be machined from that approach direction (floors and angled surfaces face the tool; walls can be side-milled). Finding the minimum number of fixturings is equivalent to finding the minimum number of hemispheres that cover all required normals — a set-cover problem.

The greedy algorithm is provably an `O(log n)` approximation of the optimal set-cover. For manufacturing purposes, it's effectively optimal because the number of fixturings is almost always small (2–5) and the greedy choice (largest area-weighted coverage) almost always matches a machinist's intuition.

### Why holes and faces are treated differently in Phase 1

Walls generate face normals in all horizontal directions. If Phase 1 included face normals as items to cover, every pocket wall (dot = 0 with +Z) would satisfy any horizontal approach and would never force a new fixturing. But a bottom face (normal = −Z) would, despite being perfectly reachable in a flip. The solution is to drive Phase 1 only from holes (features that genuinely require a specific approach direction) and let Phase 2 handle faces that are inaccessible from the Phase 1 directions.

### The coverage threshold consistency requirement

`HOLE_COVER_MIN` in the set-cover must equal `cos(SETUP_HOLE_CRITICAL_DEG)`. If the set-cover says a hole is "covered" by +Z but the concern system says it's "critically wrong" to drill at that angle from +Z, you get the nonsensical result: "this hole is assigned to +Z fixturing but is marked critical." The fix: a hole beyond its critical angle gets its own fixturing rather than a critical warning in the wrong one.

### Accessibility verification — `_reassign_by_adjacency()`

The set-cover assigns faces based on normal alignment only. This is fundamentally unable to distinguish between a pocket floor (normal -Z, inside a pocket that opens from -Y) and the bottom face (normal -Z, directly accessible from -Z). Both get `dot = 1.0` with the -Z fixture.

After the set-cover assigns faces, `_reassign_by_adjacency()` verifies and corrects assignments using physical accessibility testing. Three sequential phases, each feeding into the next:

**Phase 1 — Inverted ray (exterior classification):** For each face, cast a ray from far outside the bounding box (3× bbox diagonal) toward the face centroid along ALL 6 principal axes plus any non-principal fixture approach vectors. If the face centroid is the first surface hit from any direction, the face is classified as **exterior**. If something else always blocks it, the face is **interior** (inside a pocket or enclosed cavity).

Freeform faces (BSpline, Bezier, etc.) are always forced to interior regardless of inverted ray results — their curved surface can face outward from some angle, causing false exterior classification.

**Phase 2 — Pocket BFS:** Two passes, run sequentially so the first seeds the second:

*Pass A — Hole-anchored BFS:* Holes are the most reliably assigned features (their axis direction is unambiguous). For each hole, find the OCC wall faces and seed BFS into their interior neighbors. The BFS bridges through exterior opening faces (the face the hole is drilled into) to reach pocket walls on the other side. For **through holes**, only seed neighbors on the **entry side** of the bore (approach direction side) — otherwise the BFS floods through the bore cylinder to the wrong side of the part. Entry side is determined by projecting the vector from hole midpoint to neighbor centroid onto the hole's approach direction: positive dot = entry side (seed), negative dot = exit side (skip).

*Pass B — General pocket opening BFS:* For remaining unassigned interior faces, detect exterior faces with 2+ unassigned interior neighbors. These are pocket openings. Match the opening face's outward normal to the nearest fixture approach direction (dot > 0.3). BFS from the opening face through interior neighbors assigns the pocket to the matched fixture. This handles pockets without holes.

**Phase 3 — Void ray + neighbor propagation (fallback):** For any interior faces still unassigned (e.g., pockets with no hole and no clear opening face):

*Pass A — Multi-sample void ray:* Step into the void adjacent to the face (5 UV samples for all face types). Cast rays in each fixture's approach direction. If a ray escapes without hitting solid, that fixture can access the void. Single-clear → assign. Multi-clear → tiebreak using all verified neighbors.

*Pass B — Neighbor propagation:* Remaining faces follow verified neighbors by majority vote. Up to 5 rounds for deep chains.

### Post-reassignment steps

After `_reassign_by_adjacency()`, the pipeline:

1. Removes empty fixturings and re-indexes
2. Upgrades special-fixture classifications to 5-axis-indexed where the approach angle doesn't match standard stock fixture plates (30°, 45°, 60° ± 2°)
3. Checks fixturings containing freeform faces for 5-axis-continuous requirement (nz_range > 0.25 AND max normal spread > 25°). The freeform face is now in the correct fixture from BFS — only needs to check whether continuous tilting is required, not which fixture gets the face. The `approach_axis` is preserved (e.g. "-Y" stays "-Y") even when upgraded to 5-axis-continuous.
4. Assigns fillets to fixturings by axis alignment + neighbor vote
5. Computes fixturing face analysis (rest faces, clamp pairs, workholding classification)

---

## 12. DFM Analysis

### Severity hierarchy

- **Critical**: cannot reasonably manufacture as-designed with standard processes. Requires either geometry change or specialist process (gun drilling, EDM, broaching).
- **Warning**: manufacturable but with significant cost or risk implications. Extended tooling, pecking cycles, thin wall vibration, breakthrough risk.
- **Advisory**: worth noting for quoting accuracy. Specialty tooling, slower feeds, tighter scheduling.

### Flag categories

| Code | What it checks | Key threshold |
|---|---|---|
| `hole_ld` | Depth-to-diameter ratio | Advisory 3:1, Warning 10:1, Critical 20:1 |
| `small_hole` | Hole diameter | Advisory < 1.5mm, Warning < 0.8mm |
| `ball_nose_required` | Fillet axis vs approach alignment | `\|dot\|` < 0.9 → ball-nose needed |
| `concave_fillet_tool_dia` | Concave fillet radius | r < 1.5mm → warning |
| `sharp_internal_corner` | Wall–wall concave edges without fillet | No threshold — any unfilleted concave corner |
| `deep_feature` | Floor face depth / min tool dia | Same L/D thresholds as hole_ld |
| `thin_wall` | Aspect ratio of thin regions | Warning 8:1, Critical 10:1 |
| `thin_wall_hole_proximity` | Web between adjacent holes | Same aspect ratio thresholds |
| `partial_hole` | Bore wall intersection | Warning any exposure, Critical > 25% |
| `no_datum_face` | Workholding rest face quality | Warning if best rest face has features |
| `datum_face_features` | Hole coverage on rest face | Warning if > 15% feature coverage |
| `cog_instability` | Centre of gravity vs rest face | Warning if CoG outside footprint |

### DFM fixture annotation

DFM checks that run globally (hole_ld, small_hole, concave_fillet, ball_nose, partial_hole, thin_wall) produce flags without fixture context. A post-annotation pass at the end of `analyze_dfm()` maps each flag to a fixture using lookup tables built from the setup analysis: `hole_idx → fixturing_idx` (from fixture feature assignments) and `face_idx → fixturing_idx` (from fixture face assignments + fillet `fixturing_idx`). The resolution priority for each flag is: `hole_idx` → `fillet_face_idx` → `face_idx` → `face_idxs` → `hole_pair_idxs`.

---

## 13. The Report

`html_report.py` generates a self-contained HTML file. React 18, Three.js r128, jsPDF 2.5.1, SheetJS (xlsx.full.min.js), and Babel Standalone are all loaded from CDNs. The report data is injected as `window.__REPORT__` (JSON). No build step, no server — the file opens in any browser.

### Layout

Single-column scrollable page within a `maxWidth: 860px` container:

1. **Header** — filename, date, machine type, `↓ EXPORT PDF` and `↓ EXPORT XLSX` buttons
2. **Stat strip** — 3×2 grid: setups, bounding box, holes, planar faces, material removed, DFM flags
3. **3D viewer card** — 400px tall, full width, inline between stat strip and tables (hidden on print)
4. **Two-column section** — Setup Summary left, Hole Inventory right
5. **Drawing Info** — material, tightest tolerance + type, surface finish, datums, GD&T callout badges, inline tolerances, process notes (shown only when drawing PDF was parsed)
6. **Manufacturing Flags** — grouped by code, collapsible for multi-item groups
7. **Footer** — filename

### `to_report_dict()` — serialization contract

This is the schema boundary between the pipeline and the UI. All field names here are authoritative — the JSX reads them directly. Key fields:

`display_unit` — `'mm'` | `'inch'` | `'metre'` | `'unknown'`. Drives all display conversions in the UI and PDF. `unit_label` — `'mm'` or `'in'`.

Hole fields are named `radius` and `depth` (not `radius_mm`/`depth_mm`) because they are already in display units. Bounding box dimensions are similarly converted. Volumes remain in `mm3` (named `bbox_volume_mm3` etc.) because they are used for computed ratios, not direct display.

`geometry` — list of tessellated face dicts (see Section 20). Passes through from `pipeline_result` directly.

`face_idxs` on DFM flags — resolved by `_flag_face_idxs()` inside `to_report_dict`. The resolver checks `detail` keys in this priority order: `face_idxs` → `face_idx` → `hole_idx` (resolves via `hole_profiles[i].face_idxs`) → `fillet_face_idx` → `hole_pair_idxs` (unions both holes' face_idxs). Empty list if nothing maps.

`approach_vector` on fixturings — raw `[x, y, z]` from the setup dict, already normalized. Used by the viewer to place the approach arrow and by the snap function to position the camera.

`face_idxs` on fixturings — all feature indices assigned to that fixturing, used to drive edge wireframe overlay and face shading in the viewer.

---

## 14. Key Algorithms and Why We Chose Them

### Rule-based over ML

All detection is rule-based. This is a deliberate choice, not a limitation. Rules are:

1. **Interpretable**: a machinist can read the logic and validate it
2. **Auditable**: every flag has a clear geometric reason
3. **Correct on the first part**: ML requires labeled training data; rules work immediately

The important thing rules do: they generate **labeled feature vectors**. Every part that flows through the pipeline produces: bounding box, setup count, hole types, thin wall regions, DFM flags. Once parts go through the platform and production outcomes are known (did this thin wall cause vibration? did this hole tolerance get missed?), these feature vectors become training data. The rule-based system is the **labeling engine** for the eventual ML system.

### Greedy set-cover for fixturing

Optimal set-cover is NP-hard. Greedy is `O(n log n)` with a `(1 + ln n)` approximation bound. For manufacturing, greedy produces the correct answer on almost all real parts because:
- The number of fixturings is small (2–5 in practice)
- The dominant axes (+Z, −Z) absorb most faces
- The seeding heuristic (dominant area-weighted axis) matches machinist intuition

### Nelder-Mead for thin wall refinement

After a coarse grid sample finds a thin point, Nelder-Mead minimizes wall thickness in UV space to find the worst-case point on that surface. A regular grid will often miss the true minimum. Nelder-Mead converges in ~60 iterations for a 2D problem with a smooth objective, which is fast relative to the ray cast cost.

### Near-edge sample for sharp corner concavity

The standard approach — centroid-based concavity test — fails for non-convex (L-shaped, U-shaped) faces whose centroid falls outside the face boundary. The near-edge sample is robust: compute a point in face B's plane, perpendicular to the shared edge, close to the edge midpoint. The face centroid is used only to resolve the sign of the perpendicular direction — and the centroid reliably indicates which side of an edge is "into the face" even for non-convex faces, because it's always on the interior of the face's boundary.

---

## 15. Known Limitations

### Single solid only

The pipeline assumes one solid body. STEP files with multiple bodies (assemblies) are not handled — the geometry explorer will traverse all faces but the `BRepClass3d_SolidClassifier` will be built from the whole compound, which may produce incorrect inside/outside classifications. There is no guard or error message. **Before adding assembly support**, add a check at load time: count solids with `TopExp_Explorer(shape, TopAbs_SOLID)` and raise if > 1.

### GD&T and tolerances not extracted

No drawing integration. The tool has no visibility into specified tolerances, surface finishes, or GD&T callouts. This means:
- L/D thresholds are conservative (a tight-tolerance bore may need even more conservative tooling)
- The tool cannot know if a nominally-standard feature (e.g., a 10mm hole) has a H7 tolerance that changes the process
- Sharp corner flags cannot distinguish between "requires a fillet" and "this corner is already filletted by design intent but the model just doesn't show it"

This is the most significant limitation for production quoting. The drawing parsing pipeline is designed (see conversation notes) but not built.

### The blind_with_tip false negative risk

If the apex of a drill-tip cone is shadowed by another cut feature (a pocket that was cut in the same Z range), `probe_apex_burial()` returns `OUT` because the void adjacent to the apex is from the pocket, not from the hole being through. The hole gets misclassified as through and assigned to the wrong fixturing. Fix: move the hole clear of other features, or extend apex detection to use multiple probe points spread around the apex.

### Pockets intentionally not used — face-based architecture

`features/pockets.py` exists but is deliberately not wired into the pipeline. The original intent was to detect pocket regions explicitly (floor face + surrounding walls + entry face) and use them as first-class objects in setup analysis and DFM.

This was abandoned in favor of a purely **face-based architecture** for a fundamental reason: pockets in real precision parts break every definition you can write for them. Islands, multiple floors, intersecting pockets, pockets with holes in the floor, non-rectangular shapes, fillets shared between pocket walls and part body — every rule has exceptions, and the exceptions are precisely the complex parts this tool is designed for.

The face-based system already covers everything pocket detection was supposed to provide:

- **Access direction**: Phase 2 of the set-cover detects any floor face inaccessible from current approaches and forces a new fixturing. The pocket's access direction emerges from the floor face normal — no explicit pocket needed.
- **Floor depth**: `_check_deep_features()` identifies floor faces by `|dot(normal, approach)| ≥ 0.95` and measures depth from the bounding box entry reference. It doesn't need to know a face is a pocket floor vs. a step floor — the geometry is identical.
- **Narrow slot**: the tool access planar pass measures gap between opposing wall faces directly. A narrow slot is two close antiparallel wall faces — that's the exact structure the planar pass detects.

`pockets.py` should be treated as archived. Do not wire it into the pipeline. The `pockets=[]` placeholder in `analyze_setups()` exists only for backwards compatibility and will be removed.

### Thin wall ray cast sampling

The `5×5` grid misses thin points that fall between sample locations on large curved faces. Nelder-Mead refinement mitigates this for each grid hit, but if the thinnest point isn't within the capture radius of any grid sample, it won't be found. On production parts with large smooth curved surfaces and one very thin region, this can miss the worst-case thickness.

### Thread detection — heuristic via drawing parser

Thread detection from STEP geometry alone is not possible (thread form is not in the B-Rep). Detection is now implemented via the drawing parser (`sourcing/drawing/thread_match.py`): thread callouts extracted from the PDF are matched to STEP holes by tap drill diameter (metric: `major_dia - pitch`, imperial: lookup table). Tolerance ±0.3mm diameter, ±2mm depth. Confidence scoring (high/medium/low). Mutates `hole_type` to `"thread"` with designation, pitch, and class attached. Without a drawing PDF, threaded holes appear as plain blind or through holes.

### Fillet face double-counting across fixtures

`_assign_fillets_to_fixturings()` runs after `_reassign_by_adjacency()` and assigns each fillet to a fixture by axis alignment + neighbor vote. It does not check whether the fillet's OCC face index is already claimed as a `face` feature in a different fixture. This can cause the same surface to appear highlighted in both fixtures in the 3D viewer. Fix: before assigning a fillet, check if its `face_idx` is already in another fixture's face features, and assign it to the same fixture or skip it.

### Pocket detection without holes or matching fixture

When a pocket has no holes and no existing fixture with an approach direction matching the pocket opening normal, the general pocket opening BFS in Phase 2B of `_reassign_by_adjacency()` will fail to find a target fixture. The pocket faces remain in their original (incorrect) normal-based assignment. Fix: have pocket opening detection create a new fixture when it discovers an unmatched opening direction — this requires modifying `_hemisphere_set_cover` to accept post-hoc fixture additions.

---

## 16. Pitfalls — Critical Knowledge for Writing New Code

### Never hardcode a threshold

Every tunable constant lives in `config.py` and is imported from there. If you write `if ld > 6.0:` anywhere in a feature module, you're creating a maintenance problem. The constants in `config.py` are the single source of truth, and changing them cascades correctly to all checks.

### The scale_factor is always 0.001

The loader always sets `scale_factor = 0.001` regardless of whether it applied a spatial transform. This means `model_unit × 1000 = mm` always holds. When you see `× 1000` or `/ 1000` in the code, it's unit conversion. When you see `/ scale_factor²`, it's area correction. Don't change this without understanding the full implications — every area computation, every thin wall threshold comparison, and every distance measurement depends on it.

### The face explorer order is the face index

OCC does not provide stable face indices. Face 7 means "the seventh face encountered when traversing with `TopExp_Explorer(shape, TopAbs_FACE)`." This order is deterministic for a given shape but can differ between OCC versions or after topology operations. Do not persist face indices across pipeline runs unless the shape hasn't changed.

### Edge orientation must be normalized

`TopTools_IndexedMapOfShape.IsEqual()` includes orientation. A `FORWARD` edge and a `REVERSED` edge of the same physical edge get different indices. Always call `edge.Oriented(TopAbs_FORWARD)` before `Add()` or `FindIndex()`. This bug is silent — the code works but adjacency lookups return empty lists for all shared edges, making sharp corner detection find nothing.

### `flip_section()` and the `_original` key

When `_group_hole_sections()` encounters two coaxial sections pointing in opposite directions, it flips one to align them. `flip_section()` reverses `dir_vec` and negates `v_min`/`v_max`. It stores the pre-flip state under `_original`. `probe_apex_burial()` must use `_original` for the apex probe direction, not the flipped direction. If you add any code that needs the native axis of a section, use `sec.get('_original', sec)` — not `sec` directly.

### Thin wall vs. counterbore false positive

Before the section-aware probe fix, `detect_partial_holes()` used `rep_radius_mm` (smallest bore radius) as the probe radius at all depths. A counterbore hole has a wider shoulder that appears void at the probe radius — this was a persistent false positive. The fix: look up which section the depth falls in with `_radius_at(v)` and probe at the section-specific radius. Any future code that probes around a hole at a specific depth should use this same pattern.

### Hole proximity coaxiality

`detect_hole_proximity_walls()` skips coaxial hole pairs (`separation * 1000 < 0.1 mm`). This is intentional — a counterbore + through bore sharing an axis is a compound feature, not a proximity problem. But if you have two intentionally close coaxial holes (e.g., a stepped bore designed to create a retaining ring seat), this check will skip them. The coaxiality threshold (0.1mm) is a safety margin, not geometrically significant.

### Set-cover seeding

The Phase 1 seed is the positive direction of the dominant axis (most area-weighted face normals). "Positive" is defined as `+X`, `+Y`, or `+Z` — the axis with the most area, then the positive direction. This means if a part's dominant faces all point downward (normal = −Z), the seed is still `+Z` initially and −Z gets added in Phase 2. This is intentional: +Z is the machinist's natural first setup (part sitting on its bottom face in a vise).

### `BRepClass3d_SolidClassifier` accuracy near boundaries

The classifier uses a tolerance (`1e-6` model units = `1e-9 mm`). Points very close to a face boundary can return ambiguous results. All critical probes use a non-trivial offset from the surface (`1e-3` to `1e-4` model units). If you add a probe that returns `ON` unexpectedly, move the probe further from the surface.

### `IntCurvesFace_ShapeIntersector` self-intersection

The intersector's `epsilon` lower bound (default `1e-4` model units) prevents rays from intersecting the face they originate from. But this only works if the origin point is actually on the face surface. If you offset the origin point along the surface normal before casting, the origin is no longer on the face and the epsilon guard may fail, causing self-intersection. Either keep the origin on the surface or increase epsilon proportionally to the offset distance.

### Through-hole BFS must filter by approach side

Through holes span the entire part depth. Their bore cylinder OCC faces are adjacent to faces on BOTH sides of the part. If the hole-anchored BFS in `_reassign_by_adjacency()` seeds all neighbors of through-hole wall faces, it floods through the bore to the wrong side and pulls faces into the wrong fixture. The fix: for through holes, compute the dot product of (neighbor centroid − hole midpoint) with the approach direction. Only seed neighbors with positive dot (entry side). Blind holes skip this filter — all their neighbors are on the same side.

### Freeform faces must be forced to interior

`_reassign_by_adjacency()` Phase 1 uses inverted ray to classify exterior vs. interior faces. Freeform (BSpline) faces can face outward from some angle, causing the inverted ray to hit the curved surface first and falsely classify it as exterior. Freeform faces must always bypass Phase 1 and go directly to Phase 2/3 for BFS or void-ray assignment. This is tracked by the `freeform_face_idxs` set passed to the function.

### Pocket opening detection false positives

An exterior face with 2+ interior neighbors triggers general pocket opening detection (Phase 2B). But the top face of a part (face 2, normal +Z) might share edges with pocket walls AND be adjacent to the bore of a through-hole whose cone face is classified as interior. This creates a false pocket opening from +Z, flooding the pocket with the wrong fixture. The fix: hole-anchored BFS (Phase 2A) runs first and marks faces as assigned. Phase 2B only counts **unassigned** interior neighbors when detecting openings.

---

## 17. Future Additions

### Thread detection — COMPLETED

Thread detection is implemented via the drawing parser. See Section 15 for details. STEP-only heuristic matching (diameter to standard thread series) is not implemented — drawing parsing is the definitive solution.

### Drawing parser — COMPLETED (rule-based, v7)

`sourcing/drawing/parser.py` extracts from engineering drawing PDFs: general tolerances, inline tolerances, hole callouts (through/blind/counterbore/countersink), thread callouts (metric M + imperial UNC/UNF), GD&T frames (unicode symbols + keyword fallback), radii, surface finish (general vs individual), material, datums, process notes, dimension count. European comma decimal normalization. Thread-to-hole matching via `sourcing/drawing/thread_match.py`. Integrated into pipeline via `process_drawing()` and `_serialize_drawing()` in `to_report_dict()`.

### GD&T and tolerance extraction — Tier 2 (LLM-based)

The designed pipeline (from conversation notes):
1. **PDF/image → text**: OCR (largely solved)
2. **Text → GD&T callouts**: LLM API (Claude or GPT-4V) — models handle symbol parsing well
3. **GD&T callout → STEP feature**: match by geometry signature (diameter, depth, position) — medium difficulty
4. **STEP feature identification**: the hard part — requires matching drawing projection views to 3D geometry

The matching layer is the research problem. Strategy: extract feature descriptors from the STEP (position, diameter, depth — already available from hole profiles and planar faces) and from the drawing (nominal dimension, datum references). Match on geometry signature with LLM resolution for ambiguous cases.

### Assembly support

Current guard needed at load time: count `TopAbs_SOLID` children in the compound. If > 1, either:
a) Iterate each solid independently and run the full pipeline per body
b) Return an error asking for single-body STEP export

Per-body analysis requires passing the correct `TopoDS_Solid` (not the compound) to `BRepClass3d_SolidClassifier`. The classifier must be built from the solid, not the compound, or inside/outside tests break at body boundaries.

### Pocket volume for cycle time estimation

The one thing face-based analysis cannot provide: **pocket volume** — how much material must be cleared from a specific enclosed cavity. This matters for cycle time estimation (roughing passes, tool path length).

This is not addressable with face topology and is a fundamentally different problem. The most practical approach is voxel-based: subtract the solid from a bounding envelope and analyze the resulting void regions. This is a significant undertaking and not needed until quote range estimation is a priority feature.

### Quote range estimation

Once setups, tool changes, material removal, and DFM flags are available, a rough $/part estimate is achievable using empirical machining time models:
- Setup time: fixed per fixturing (e.g., 15–30 min) plus variable per feature count
- Cycle time: material removal rate (MRR) based on volume, adjusted for thin walls, deep holes, small holes
- Overhead factor: based on machine type (5-axis > 3-axis)

Not precise enough for a binding quote, but useful as a sanity check and a complexity tier anchor.

### Machine classification expansion

Currently: `3-axis-standard`, `3-axis-special-fixture`, `5-axis-indexed`, `5-axis-continuous`. Could add:
- `turning` (rotational symmetry detection)
- `turn-mill` (turning + milling features combined)
- `EDM required` (escalated from unfilleted sharp corners)

---

## 18. Configuration Reference

All constants live in `sourcing/config.py`. Key thresholds:

| Constant | Default | What it controls |
|---|---|---|
| `SETUP_PRINCIPAL_AXIS_TOL_DEG` | 10° | Snap to principal axis → 3-axis-standard |
| `SETUP_HOLE_CRITICAL_DEG` | 15° | Hole angle → needs own fixturing (also drives `HOLE_COVER_MIN`) |
| `SETUP_HOLE_WARNING_DEG` | 8° | Hole angle → pecking/special tooling warning |
| `SETUP_HOLE_ADVISORY_DEG` | 3° | Hole angle → tool life advisory |
| `SETUP_STANDARD_FIXTURE_ANGLES_DEG` | 30°, 45°, 60° | Angles with off-the-shelf angle plates |
| `THIN_WALL_WARNING_RATIO` | 8:1 | Height:thickness ratio → warning |
| `THIN_WALL_CRITICAL_RATIO` | 10:1 | Height:thickness ratio → critical |
| `THIN_WALL_MAX_THICKNESS_MM` | 50mm | Thicker than this → never flagged |
| `DFM_HOLE_LD_ADVISORY` | 3:1 | L/D → advisory |
| `DFM_HOLE_LD_WARNING` | 10:1 | L/D → warning |
| `DFM_HOLE_LD_CRITICAL` | 20:1 | L/D → critical |
| `DFM_HOLE_SMALL_ADVISORY_DIA_MM` | 1.5mm | Diameter → advisory |
| `DFM_HOLE_SMALL_WARNING_DIA_MM` | 0.8mm | Diameter → warning |
| `FILLET_EDGE_ROUND_MIN_RADIUS_MM` | 5mm | Below → always a fillet, not edge_round |
| `FILLET_EDGE_ROUND_MAX_HR_RATIO` | 3.0 | H/R above → true fillet, not edge_round |
| `CHAMFER_SEMI_ANGLES_DEG` | 30°, 45°, 60° | Recognized chamfer angles |
| `SETUP_CHAMFER_ANGLE_TOL_DEG` | 5° | Tolerance on chamfer angle recognition |
| `SETUP_CHAMFER_WIDTH_RATIO` | 0.15 | Chamfer width / parent edge length threshold |

**The critical invariant**: `cos(SETUP_HOLE_CRITICAL_DEG)` must equal the `HOLE_COVER_MIN` used inside `_hemisphere_set_cover()`. This is computed dynamically in the code (`math.cos(math.radians(SETUP_HOLE_CRITICAL_DEG))`) — do not override it with a hardcoded value.

---

*This document was written in March 2026. The codebase is under active development. When in doubt, the code is authoritative — this document describes intent and design decisions, but the code is what actually runs.*

---

## 19. Unit Detection and Display

### The problem

STEP files can be authored in mm, inches, or metres. OCC reads all three but always presents coordinates in the declared unit after its own internal conversion — so a 1-inch cube in an inch file reads as 25.4 × 25.4 × 25.4 in raw OCC coordinates (OCC converts declared inches → mm on read). A metre file reads as small raw floats (e.g. 0.025 for 25mm). The internal pipeline always normalises to mm, but the display layer needs to know the original unit to show sensible numbers to the user.

### `_detect_step_unit(filepath, max_bytes=131072)`

Located in `loader.py`. Scans the first 128KB of the STEP file as ASCII text before OCC reads it, looking for unit declaration entities in the DATA section:

```
SI_UNIT($,.MILLI.,.METRE.)           → 'mm'
SI_UNIT($,.METRE.)                   → 'metre'   (without MILLI prefix)
CONVERSION_BASED_UNIT('INCH',25.4    → 'inch'
CONVERSION_BASED_UNIT('IN',          → 'inch'    (alternate)
CONVERSION_BASED_UNIT('FOOT',        → 'foot'    (rare)
```

Returns `'mm'` | `'inch'` | `'metre'` | `'foot'` | `'unknown'`. Text scan is used rather than OCC's unit API because the API behaviour varies across OCC versions and is unreliable for non-SI files.

### `load_step_file(filepath)` — return value change

Now returns `(shape, scale_factor, display_unit)` instead of `(shape, scale_factor)`. All callers must unpack three values. The internal normalisation is unchanged — `scale_factor = 0.001` always, and `model_unit × 1000 = mm` always holds.

**Inch files**: OCC converts declared inches to mm on read, so after `TransferRoots()` the coordinates are already in mm. The same ×0.001 normalising transform is applied as for mm files. `display_unit = 'inch'`. Downstream display divides mm values by 25.4.

**Metre files**: raw OCC coordinates are in metres. No ×0.001 transform is needed — multiplying by 1000 converts m → mm directly. Detected by `max_dim_raw ≤ 1.0` as fallback when declaration is `'unknown'`.

### Display conversions in `to_report_dict`

Two helpers inside `to_report_dict()`:

```python
def _len(mm):   # mm → display unit, rounded appropriately
    return round(mm / 25.4, 4) if display_unit == "inch" else round(mm, 1)

def _vol(mm3):  # mm³ → display unit³
    return round(mm3 / (25.4 ** 3), 4) if display_unit == "inch" else round(mm3, 1)
```

Applied to: bounding box dimensions, hole `radius` and `depth`, fixturing `min_tool_dia`. Volumes in the report dict remain in mm³ (the PDF and UI convert them on the fly using `R.display_unit`).

### Volume display in the UI

```javascript
R.display_unit === "inch"
  ? `${(R.machined_volume_mm3/16387.1).toFixed(3)} in³`  // 1 in³ = 16387.064 mm³
  : `${(R.machined_volume_mm3/1000).toFixed(1)} cm³`
```

### Hole field rename

`radius_mm` and `depth_mm` were renamed to `radius` and `depth` in the report JSON because the values are now in display units, not necessarily mm. Any code consuming the report dict must use the new names.

---

## 20. Tessellation and Geometry Export

### `tessellate_shape(shape)` — in `pipeline.py`

Called once after the main pipeline analysis, before `to_report_dict`. Returns a list of face dicts:

```python
[
  {
    "i": face_idx,        # int — matches pipeline face indices (TopExp_Explorer order)
    "v": [x,y,z, ...],    # flat float array, vertices in mm, rounded to 2dp
    "t": [a,b,c, ...],    # flat int array, triangle indices (0-based into v)
  },
  ...
]
```

Uses `BRepMesh_IncrementalMesh` with `LINEAR_DEFLECTION = 0.0005` model units (= 0.5mm) and `ANGULAR_DEFLECTION = 0.5` radians. Triangle winding is corrected for face orientation: reversed faces (`TopAbs_REVERSED`) have triangle winding flipped so outward normals are consistent in the renderer.

### Face index correspondence

The face index `i` in each geometry dict matches the face index used everywhere else in the pipeline — it is the ordinal position of that face in a `TopExp_Explorer(shape, TopAbs_FACE)` traversal. This is the same ordering used in `build_face_adjacency()`, `get_planar_faces()`, and every DFM flag's `face_idxs`. This correspondence is what makes click-to-highlight work: a DFM flag's `face_idxs: [12, 14]` maps directly to `geometry` entries with `i: 12` and `i: 14`.

### Size warning

For complex parts with many faces, the geometry array can be large. A 200-face part at 0.5mm deflection typically produces 50–200KB of vertex/triangle data. The JSON is embedded in the HTML, so the report file size scales with part complexity. This is acceptable for desktop use but worth watching for web delivery.

### Locations and transforms

Some faces carry a `TopLoc_Location` that must be applied to get world-space coordinates. `tessellate_shape` checks `location.IsIdentity()` and applies `p.Transformed(trsf)` when needed. Skipping this step produces geometry misaligned from the part centre, which breaks the camera auto-fit and leader line projection.

---

## 21. Report Schema — Current Specification

This is the authoritative schema for `to_report_dict()` output. The JSX and PDF builder both read from this directly.

```json
{
  "filename":               "part.step",
  "analyzed_at":            "2026-03-15T10:00:00Z",
  "display_unit":           "mm",
  "unit_label":             "mm",

  "bounding_box":           { "x": 112.0, "y": 84.0, "z": 35.0 },
  "bbox_volume_mm3":        329280.0,
  "solid_volume_mm3":       267987.0,
  "machined_volume_mm3":    61293.0,
  "material_removal_pct":   18.6,

  "planar_faces":           30,
  "machine_classification": "3-AXIS-STANDARD",
  "fixturing_count":        2,

  "fixturings": [
    {
      "id":              0,
      "label":           "+Z",
      "setup_type":      "3-axis-standard",
      "approach_vector": [0, 0, 1],
      "face_idxs":       [3, 7, 12, 14, 24],
      "planar":          26,
      "floor":           5,
      "wall":            20,
      "holes":           8,
      "fillets":         0,
      "tool_changes":    5,
      "min_tool_dia":    5.6,
      "concerns":        { "critical": 3, "warning": 17, "advisory": 5 }
    }
  ],

  "holes": [
    {
      "id":         1,
      "type":       "through_countersink",
      "radius":     2.80,
      "depth":      35.0,
      "cone_angle": 45.0,
      "ld":         6.2,
      "face_idxs":  [20, 9]
    }
  ],

  "dfm": [
    {
      "severity":  "critical",
      "code":      "hole_ld",
      "fixturing": "+Z",
      "message":   "Hole 9: L/D = 15.0:1 — gun-drilling or EDM likely required",
      "face_idxs": [35]
    }
  ],

  "geometry": [
    { "i": 39, "v": [0,0,35, 112,0,35, ...], "t": [0,1,2, 0,2,3] }
  ]
}
```

Notes: `bounding_box` values and hole `radius`/`depth` and fixturing `min_tool_dia` are in `display_unit`. All `*_mm3` volume fields remain in mm³ regardless of display unit. `face_idxs` on holes, DFM flags, and fixturings all use the same face index space (TopExp_Explorer ordinal). `ld` is omitted (null) when ≤ 2.0 — only flagged when it matters for quoting.

---

## 22. HTML Report — 3D Viewer

### Component: `Viewer3D`

Props: `selectedFaceIdxs`, `labelText`, `labelSev`, `activeFixture`, `snapRef`, `captureRef`.

The viewer is an inline card (400px tall, full width) between the stat strip and the two-column tables. It is hidden on print (`@media print { .viewer-card { display: none; } }`).

### Initialization

One `THREE.Mesh` per geometry face, stored in `faceMeshes[face_idx]`. All meshes share the scene; materials are swapped per-frame based on selection/fixture state. `BRepMesh_IncrementalMesh` tessellation is done Python-side; the browser receives flat arrays.

Camera auto-fit: bounding box of all meshes → centre + max dimension × 1.8 as initial radius.

### Material states

Four material factories (called as functions to produce new instances — Three.js does not support sharing materials when properties differ):

| State | Color | When applied |
|---|---|---|
| `MAT_DEFAULT` | Neutral gray `#d4d4d4` | No selection, no active fixture |
| `MAT_FIXTURE` | Light blue `#c7d8f5` | Face belongs to active fixturing |
| `MAT_HIGHLIGHT` | Orange `#f97316` with emissive | Face in `selectedFaceIdxs` |
| `MAT_DIM` | Light gray `#e0e0e0`, 35% opacity | Not selected / not in active fixture |

Priority when both a DFM selection and a fixture are active: selected faces → orange, fixture faces → blue, rest → dimmed.

### Coordinate axes gizmo

Small XYZ gizmo in the top-left corner of the viewer (transparent background). X = red, Y = green, Z = blue. Axes rotate with the camera orbit. Labels ("X", "Y", "Z") positioned at axis tips.

### Deselect button

`✕` button in the top-right corner of the viewer. Clears all selections: `selectedFaceIdxs`, `labelText`, `activeFixture`, `snappedFixId`.

### Fixture info card

When a fixturing is active, a blue info card appears in the bottom-left of the viewer showing: fixture label, surface count, approach direction, setup type badge (green for 3-axis, amber for 5-axis), workholding classification with color legend (green = rest face, orange = clamp faces, blue = machined surfaces), and any workholding warnings.

For non-principal-axis fixtures (label doesn't match `±X/Y/Z`), the card also shows angles from each principal axis and the raw approach vector.

### Orbit controls

Manual spherical coordinates: `theta` (azimuth), `phi` (polar), `radius`, `target` (look-at point). Left-drag rotates theta/phi. Right-drag or Ctrl+drag pans the target. Scroll zooms radius. Touch: single-finger rotate, two-finger pinch-zoom.

Camera position: `target + radius × (sin(phi)cos(theta), cos(phi), sin(phi)sin(theta))`.

### SVG leader line

Absolute-positioned SVG overlay (same dimensions as canvas, `pointerEvents: none`). Updated every animation frame: projects the vertex centroid of `selectedFaceIdxs` through `camera.project()` to get screen-space pixel coordinates. Draws a dashed line from the label card's anchor point (top-left corner, `(18, 18)`) to the projected centroid dot. Dot color matches `SEV_COLOR[labelSev]`.

### Snap function (`snapRef`)

Exposed via `snapRef.current = (approachVec) => {...}` inside the init effect. Converts the approach vector to spherical angles:

```javascript
phi   = acos(ay / |approachVec|)   // polar angle from +Y
theta = atan2(az, ax)              // azimuth
```

Sets `snapTargetRef.current` to `{ theta, phi }`. The animation loop lerps toward the target at 12% per frame (`~20 frames to settle`). Calling `snapRef.current(approach_vector)` from outside the component triggers a smooth camera rotation to view the part from the tool's approach direction.

### Capture function (`captureRef`)

Exposed via `captureRef.current = () => dataURL`. Temporarily repositions the camera to a true isometric angle (`phi = acos(1/√3) ≈ 54.74°`, `theta = -0.75π`, `radius = maxDim × 2.2`), renders one synchronous frame, captures `renderer.domElement.toDataURL('image/png')`, then restores the previous orbit state. Called by `buildPDF()` to get the part image.

---

## 23. HTML Report — Fixture Interaction

### State in App

`activeFixture` — the full fixturing object from `R.fixturings`, or `null`. Set by `toggleFixture(fix)`. Clicking the same row again sets it to null.

`snapRef` — ref passed to Viewer3D; calling `snapRef.current(approach_vector)` triggers camera snap.

### Setup table

Column layout: `44px 1fr 38px 38px 38px 52px` — axis label, features summary, holes count, faces count, flags count, view button.

Clicking any row calls `toggleFixture(fix)`. Active row gets `background: #eff6ff`, `outline: 1px solid #bfdbfe`, axis label in blue with a small blue dot indicator.

`↗ VIEW` button: calls `snapToFixture(fix)` (which calls `snapRef.current`) and activates the fixturing if not already active. Button style changes when its fixturing is active: black background → blue background.

### Approach arrow

`THREE.ArrowHelper` positioned at `center + approach_vector × maxDim × 1.05` (one bounding-box-diameter outside the part on the approach side), pointing toward `center` (direction = `approach_vector.negate()`). Color `#2563eb` (blue). Length 45% of max part dimension. Head is 28% of length, 18% width. Removed when `activeFixture` is cleared.

Arrow shaft `linewidth` is set to 3 but note that `linewidth > 1` has no effect on most WebGL implementations (it is a known Three.js / WebGL limitation). The arrow is large enough to be visible without it.

### Edge wireframe

`THREE.EdgesGeometry` computed from each face's geometry with a 15° crease angle. Rendered as `THREE.LineSegments` with `LineBasicMaterial({ color: 0x1d4ed8 })`. One LineSegments object per face in the active fixturing. Stored in `edgesRef.current[]` and removed from the scene when the fixturing changes.

The crease angle of 15° is important: too small (e.g. 1°) and you get every triangle edge, producing a mess. 15° catches real feature boundaries (pockets, hole entries, steps) while suppressing tessellation artifacts on smooth curved surfaces.

### Info card in viewer

When a fixturing is active but no DFM flag is selected, a blue info card appears in the bottom-left of the viewer: "FIXTURING +Z — N surfaces assigned · approach +Z" with a setup type badge (green `3 AXIS STANDARD` or amber `5 AXIS CONTINUOUS`). For non-principal fixtures, shows angles from X/Y/Z axes and raw approach vector. Includes workholding classification (VISE / SOFT JAW / CUSTOM) with color-coded legend and any warnings (datum face features, CoG instability). Replaced by the DFM flag label card when a flag is also selected.

---

## 24. HTML Report — PDF Export

### Dependencies

jsPDF 2.5.1 loaded from `https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js`. Accessed as `window.jspdf.jsPDF`.

### `buildPDF()` — structure

A4 portrait, 15mm margins. Built entirely with jsPDF primitives (no HTML-to-canvas). Page breaks added automatically when `y > PH - threshold`.

Layout top to bottom:

1. **Header** — eyebrow text ("FACET — PART ANALYSIS REPORT"), filename at 16pt bold, date at 8pt, machine type right-aligned
2. **Rule** — 0.5pt full-width line
3. **Isometric part image** — 78mm tall, full content width. Captured from the Three.js renderer via `captureRef.current()`. Skipped if `HAS_GEO` is false or captureRef not yet set
4. **Stat strip** — 3×2 grid of 20mm-tall cells, same six stats as UI. Colored accents on material removal (warning orange if >70%) and DFM flags (red/orange/green by severity)
5. **Setup summary + Hole inventory** — two columns side by side, each with a header row and alternating-shade data rows
6. **Manufacturing flags** — each code group gets a header row (severity badge left, label, count right) with colored left border. Each flag item is its own row (fixturing label + message). Messages truncated to fit the column width using `doc.splitTextToSize(...)[0]`
7. **Footer** — filename right-aligned at bottom of last page

### UI button

In the report header, right side, below the machine type. Dark background (`#1a1a1a`), white text, `↓ EXPORT PDF` label. Disabled during generation (`pdfBusy` state), shows `⏳ GENERATING…` while running. Re-enables on completion or error.

### Fonts in jsPDF

jsPDF built-in fonts only: `helvetica` and `courier`. Helvetica for UI text, courier for monospaced values (axis labels, dimensions, L/D ratios). Custom fonts (IBM Plex) are not embedded — the PDF will use the system's Helvetica/Courier.

### Critical: renderer must be initialized

`captureRef.current` is set inside the Viewer3D `useEffect` init callback. If the user clicks `↓ EXPORT PDF` before the Three.js renderer has initialized (e.g., immediately on page load), `captureRef.current` will be null and the image section is skipped silently. This is acceptable — the rest of the PDF still generates correctly.

---

## 25. HTML Report — Excel Export

### Dependencies

SheetJS (xlsx.full.min.js v0.20.1) loaded from `https://cdn.sheetjs.com/xlsx-0.20.1/package/dist/xlsx.full.min.js`. Accessed as `window.XLSX`.

### `buildExcel()` — structure

Generates a multi-sheet `.xlsx` workbook using `XLSX.utils.aoa_to_sheet` (array-of-arrays). Downloads as `{filename}_facet_report.xlsx`.

### Sheets

| Sheet | Contents |
|---|---|
| **Summary** | Filename, date, machine classification, display unit, bounding box dimensions, volumes (bbox/solid/machined), material removal %, counts (setups, planar faces, holes, DFM flags) |
| **Setups** | One row per fixture: ID, axis label, setup type, hole count, planar/floor/wall face counts, tool changes, min tool diameter, workholding class, concern counts (critical/warning/advisory) |
| **Holes** | One row per hole: ID, type, thread designation (if matched), diameter, depth, L/D ratio, cone angle |
| **DFM Flags** | One row per flag: severity, category code, fixture label, full message text |
| **Drawing** | Only present when a drawing PDF was parsed. Material, tightest tolerance + type, datums, surface finish (general/individual), confidence. Sub-tables for GD&T callouts, inline tolerances, general tolerance block, and process notes |

### UI button

White outline button with `↓ EXPORT XLSX` label, positioned left of the dark PDF export button. No busy state — SheetJS generation is synchronous and fast.

### Column widths

Each sheet has manually set `!cols` with `wch` (width in characters) to produce readable default column widths. The widths are tuned for the typical data lengths in each column (e.g., 80 characters for DFM message text, 22 for category labels).
