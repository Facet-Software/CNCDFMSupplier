# Facet

DFM analysis and quoting tool for CNC machine shops.

![Python](https://img.shields.io/badge/Python-OpenCASCADE-blue) ![Next.js](https://img.shields.io/badge/Frontend-Next.js-black) ![Live](https://img.shields.io/badge/Live-facetquote.com-green)

---

Upload a STEP file and get a structured manufacturability report in under a minute — setups, hole inventory, DFM flags, material removal, and tool access analysis. Optionally attach an engineering drawing PDF to add tolerance extraction, GD&T parsing, and thread matching.

Built for precision job shops (aerospace, medical, semiconductor) where quoting a complex part currently takes 30–90 minutes of manual geometry reasoning. Facet automates the reading and transcription work without replacing the machinist's judgment.

---

## Background

The original idea was a two-sided marketplace for precision CNC sourcing. The core insight: you can describe what a part requires to manufacture — setups, features, tolerances — without exposing the design IP in the raw CAD file. Buyers could solicit competitive bids from new suppliers without sending their geometry to five unknown shops. Nothing does this end-to-end today.

The marketplace has a cold-start problem. We're solving it by sequencing: build the supplier side first as a standalone product that suppliers want independently of any marketplace. Job shops doing 20–30 RFQs per week spend a significant fraction of their estimating labor manually reading STEP files — opening them in CAD, counting setups, mentally flagging thin walls and deep holes. Facet replaces that manual pass, makes pricing objective by grounding quotes in measurable geometry rather than estimator intuition, and catches DFM issues before they become first-article failures.

The target is deliberately not the commodity quoting market (Xometry, Protolabs). It's precision production work — tolerances in the 0.001–0.005" range — where underquoting a 5-axis part as 3-axis is a serious margin problem and DFM issues cause real rework costs.

---

## Long-term vision

Every analysis Facet runs is a structured data record: part geometry fingerprint, feature complexity, setup count, DFM flag profile. At scale, this becomes something more valuable than the quoting tool itself — a dataset that maps hard part features to real supplier behavior.

Which shops consistently underquote complex fixturings? Which flag thin walls that others miss? Which suppliers' quotes correlate with on-time delivery and first-article pass rates? This data doesn't exist anywhere in the market today. Buyers have no objective basis for supplier selection beyond past relationships and reputation.

The endgame is the marketplace the project started as: buyers upload a part, receive an abstracted manufacturability profile (no IP exposure), and get competitive bids from a pre-qualified supplier network ranked by demonstrated competence on comparable geometry. The supplier tool is how we build that network and the dataset that makes the ranking meaningful. By the time we open the buyer side, the supply side is already conditioned.

---

## What it analyzes

- Setup count and fixturing plan — approach directions, machine type classification (3-axis vs 5-axis indexed)
- Full hole inventory — through, blind, counterbore, countersink — with diameter, depth, and L/D ratios
- DFM flags — deep holes, thin walls, sharp internal corners, small holes, proximity webs — with severity levels (critical / warning / advisory)
- Material removal % — solid volume vs bounding box, drives cycle time estimates
- Minimum tool diameter per fixturing — tightest geometric constraint on tooling per setup
- Drawing parser (optional) — tolerance extraction, GD&T callouts, thread detection matched to STEP geometry

---

## Architecture

Single Railway server. Next.js handles the frontend and API routes. The upload route spawns the Python DFM engine directly via conda — no microservices, no separate model server.

```
STEP + PDF upload
     ↓
POST /api/upload — saves files, spawns python run.py, returns jobId immediately
     ↓
Frontend polls /api/jobs/[jobID] every 2s
     ↓
Python (OpenCASCADE) — geometric analysis, HTML report generation
     ↓
Report served at /api/files/[uuid] — 3D viewer, setup summary, DFM flags, PDF + Excel export
```

Stack: `pythonocc-core` · `pdfplumber` · Next.js · Prisma · Turso (LibSQL) · Railway · Docker

---

## DFM engine

```bash
conda activate dfm
python run.py /path/to/file.step [/path/to/drawing.pdf]
```

Pure geometric analysis — no ML, no heuristics. Reads B-Rep topology directly from the STEP file via OpenCASCADE.

> For a full technical breakdown of the pipeline, feature extraction algorithms, fixturing logic, known limitations, and report schema — see [FACET.md](FACET.md).

---

## Report output

Self-contained HTML file. No dependencies, opens in any browser.

- Interactive 3D viewer with per-fixturing face highlighting and approach vector visualization
- Setup table with workholding classification and DFM flag counts per fixture
- Export to PDF (jsPDF, isometric capture) and Excel (SheetJS, multi-sheet)

---

## Status

Live at [facetquote.com](https://facetquote.com). No auth, no accounts — upload and go.
