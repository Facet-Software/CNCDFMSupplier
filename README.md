# Facet

DFM analysis tool for CNC machine shops. Upload a STEP file (+ optional engineering drawing PDF), get an instant manufacturability report — setups, holes, thin walls, tool access, tolerances, thread detection, DFM flags.

**Live at [facetquote.com](https://facetquote.com)**

---

## Architecture

Everything runs on one Railway server. Next.js handles the frontend and API routes. The upload route spawns JR's Python model directly via conda. No microservices, no split deployment.

```
app/
├── page.tsx                          # Landing page (upload form)
├── layout.tsx
├── globals.css
├── api/
│   ├── upload/
│   │   └── route.ts                  # Saves files, creates DB row, spawns model
│   ├── files/
│   │   └── [name]/
│   │       └── route.ts              # Serves HTML reports + uploaded files
│   └── jobs/
│       └── [jobID]/
│           └── route.ts              # Polling endpoint (frontend checks every 2s)
├── lib/
│   └── prisma.ts                     # Prisma client (Turso/LibSQL adapter)
│
dfm-model/                            # Python DFM engine (OpenCASCADE)
│   ├── run.py                        # Entry point: python run.py file.step [drawing.pdf]
│   ├── sourcing/
│   │   ├── pipeline.py               # Main pipeline + drawing processing
│   │   ├── loader.py                 # STEP file loader
│   │   ├── config.py
│   │   ├── analysis/                 # Setup, DFM flags, tool access, feature summary
│   │   ├── classify/                 # Hole classification
│   │   ├── features/                 # Planar, cylindrical, thin walls, pockets
│   │   ├── reporting/                # HTML report + summary generation
│   │   └── utils/                    # Geometry helpers
│   └── parse_drawing.py              # PDF tolerance + thread parser
│
prisma/
│   └── schema.prisma
│
uploads/                              # UUID-named files + HTML reports (gitignored)
Dockerfile                            # Railway deployment (Node + conda + pythonocc-core)
```

---

## User Flow

```
1. Shop owner uploads STEP + email (optional: drawing PDF) at facetquote.com

2. POST /api/upload
   ├── Saves STEP + PDF to /uploads with UUID names
   ├── Creates UploadJob row in Turso (status: "received")
   ├── Spawns: python dfm-model/run.py /uploads/uuid.step [/uploads/uuid.pdf]
   └── Returns { jobId } immediately

3. Frontend shows "Analyzing your part..." spinner
   └── Polls GET /api/jobs/[jobID] every 2 seconds

4. Python finishes in background:
   ├── Prints JSON report to stdout → route.ts captures it
   ├── Writes HTML report to dfm-model/ → route.ts moves to uploads/
   ├── Stores JSON in Turso dfmResultJson column
   └── Updates status → "complete"

5. Poll returns { status: "complete", reportUrl } → browser redirects to HTML report

6. GET /api/files/uuid_report.html serves JR's interactive report
   └── 3D viewer, setup summary, hole inventory, DFM flags, PDF export
```

---

## DFM Engine

Full geometric analysis from a STEP file. Python + OpenCASCADE (pythonocc-core).

```
conda activate dfm
python run.py /path/to/file.step [/path/to/drawing.pdf]
```

**Capabilities:**

- Machine classification (3-axis standard vs 5-axis indexed)
- Setup / fixturing count with per-setup breakdown
- Hole inventory (through, blind, counterbore, countersink) with L/D ratios
- Small hole detection (below 1.5mm and 0.8mm thresholds)
- Deep hole detection (L/D flags at 3:1, 6:1, 10:1)
- Volume removal percentage (bounding box vs solid)
- Thin wall detection (geometry-based + hole proximity)
- Deep pocket flagging
- Minimum tool diameter per fixturing
- Fillet analysis (concave/convex, radius thresholds)
- Estimated tool changes per fixturing
- DFM flags (critical / warning / advisory)
- Bounding box dimensions
- Tool access / wall gap analysis

**Drawing Parser (optional PDF input):**

- Tolerance extraction from engineering drawing PDFs
- Thread detection and matching to holes in the STEP model
- GD&T parsing
- Confidence scoring

---

## Database

Turso (LibSQL). One table:

```prisma
model UploadJob {
  id                String   @id @default(uuid())
  createdAt         DateTime @default(now())
  status            String   @default("received")

  email             String
  phone             String?

  stepOriginal      String
  stepStored        String
  drawingOriginal   String?
  drawingStored     String?

  dfmResultJson     String?
  drawingParseJson  String?
}
```

Manage via: `turso db shell facet`

---

## Deployment

Everything runs on Railway ($5/mo Hobby plan). Docker container with Node 20 + conda + pythonocc-core.

**Dockerfile handles:**
- System deps (libgl, libglib for OpenCASCADE)
- Miniconda install + TOS acceptance
- conda env `dfm` with python 3.11 + pythonocc-core + pdfplumber
- Node deps + Next.js build
- Starts with `npm start`

**Railway env vars:**
```
DATABASE_URL=libsql://facet-sunjayshanker.aws-us-east-1.turso.io?authToken=xxx
RESEND_API_KEY=re_xxx
PYTHON_PATH=/opt/conda/envs/dfm/bin/python
```

**Domain:** facetquote.com → Railway via CNAME in Namecheap

**Auto-deploy:** Push to `main` on GitHub → Railway rebuilds and deploys automatically.

---

## Local Development

```bash
# Start dev server
npm run dev

# Test model directly
conda activate dfm
cd dfm-model
python run.py ../uploads/any-file.step

# Test model with drawing
python run.py ../uploads/any-file.step ../uploads/any-drawing.pdf

# Check database
turso db shell facet
SELECT * FROM UploadJob ORDER BY createdAt DESC LIMIT 5;
```

**Local conda Python path (Mac):**
```
/usr/local/Caskroom/miniconda/base/envs/dfm/bin/python
```

**Server conda Python path (Railway Docker):**
```
/opt/conda/envs/dfm/bin/python
```

---

## .gitignore

```
.env
.env.local
uploads/
node_modules/
__pycache__/
*.pyc
.DS_Store
__MACOSX/
dfm-model/Sample_Parts/
```

---

## Security

**Already handled:**
- SQL injection — Prisma parameterizes all queries
- XSS — React escapes output
- HTTPS — Railway provides this automatically
- File names — all uploads renamed to UUIDs
- File size limit — 50MB cap in upload route

**Add when you have real users:**
- Rate limiting on upload route
- Per-upload access control on /api/files/[name]
- Email verification
- Upload cleanup (cron to delete old files)

---

## Design Decisions

- **No auth / no accounts.** Upload and go.
- **One server.** Next.js + Python on the same Railway box. Simplest possible deployment.
- **Spawn, not HTTP.** Route.ts spawns python directly. No model server, no fetch between services.
- **Entire report stored as one JSON blob.** No schema changes when model adds capabilities.
- **Email required with upload.** How we close the feedback loop.
- **Drawing optional.** STEP alone generates full value. Drawing adds tolerances + thread matching.
- **One landing page.** facetquote.com = value prop + upload form. That's it.