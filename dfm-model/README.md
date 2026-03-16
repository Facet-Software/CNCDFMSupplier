# Facet

DFM analysis tool for CNC machine shops. Upload a STEP file (+ optional drawing PDF), get an instant manufacturability report — setups, holes, thin walls, tool access, DFM flags. Cuts quoting prep time from hours to minutes.

Supplier-side only. No accounts. No marketplace.

---

## Architecture

Next.js frontend on Vercel. Python DFM engine on a separate server. Upload route saves files, creates a DB row, then sends the STEP file to the model server via HTTP. Model runs, returns JSON, route stores it in the database.

```
Vercel (frontend + API routes)
├── app/
│   ├── page.tsx                    # Landing page (upload form above the fold)
│   ├── layout.tsx                  # Root layout + metadata
│   ├── globals.css                 # Global styles
│   ├── api/
│   │   ├── upload/
│   │   │   └── route.ts            # Saves files, creates DB row, sends to model server
│   │   ├── files/
│   │   │   └── [name]/
│   │   │       └── route.ts        # Serves uploaded files + HTML reports
│   │   └── jobs/
│   │       └── [jobId]/
│   │           └── route.ts        # Returns job status (for polling)
│   └── lib/
│       └── prisma.ts               # Prisma client (Turso/LibSQL)
│
│   prisma/
│   │   └── schema.prisma           # Database schema
│   scripts/
│       └── parse_drawing.py        # Tolerance parser for drawing PDFs
│
Model Server ($5/mo — Railway or DigitalOcean)
├── dfm-model/
│   ├── run.py                      # Entry point
│   ├── server.py                   # Simple HTTP wrapper (receives file, runs model, returns JSON)
│   └── sourcing/                   # Full pipeline
│
uploads/                            # UUID-named files + HTML reports (gitignored)
```

---

## User Flow

```
1. Shop owner uploads STEP file + email on facetquote.com

2. POST /api/upload (runs on Vercel)
   ├── Saves STEP to storage with UUID name
   ├── Creates UploadJob row (status: "received")
   ├── Sends STEP file to model server via HTTP POST
   ├── Emails founder via Resend
   └── Returns { jobId, reportUrl }

3. Frontend shows "Analyzing..." and polls GET /api/jobs/[jobId] every 2s

4. Model server finishes:
   ├── Returns JSON report to Vercel route
   ├── Route stores JSON in dfmResultJson column
   ├── Generates/stores HTML report
   └── Updates status → "complete"

5. Poll returns "complete" → frontend redirects to HTML report
```

---

## DFM Engine (dfm-model/)

Full geometric analysis from a STEP file. Python + OpenCASCADE. Requires conda environment with pythonocc-core.

```
conda activate dfm
python run.py /path/to/file.step
```

| Capability | Detail |
|-----------|--------|
| **Machine classification** | 3-axis standard vs 5-axis indexed |
| **Setup / fixturing count** | How many times the part needs to be re-fixtured |
| **Per-setup breakdown** | Approach axis, features per fixturing, concern counts |
| **Hole inventory** | Through, blind, counterbore, countersink — with diameter, depth, L/D ratio |
| **Small hole detection** | Flags holes below 1.5mm and 0.8mm diameter thresholds |
| **Deep hole detection** | L/D ratio flags at 3:1, 6:1, 10:1 (gun-drilling territory) |
| **Volume removal** | Bounding box volume vs solid volume = material removal percentage |
| **Thin wall detection** | Geometry-based + hole proximity walls, severity rated |
| **Deep pockets** | Depth-to-tool-diameter ratio flagging |
| **Minimum tool diameter** | Per fixturing, based on gap constraints between faces |
| **Fillet analysis** | Concave/convex, radius thresholds, special tooling flags for small radii |
| **Estimated tool changes** | Per fixturing based on distinct hole diameters + fillet tools |
| **DFM flags** | Critical / warning / advisory with specific actionable messages |
| **Bounding box dimensions** | X × Y × Z in mm |
| **Tool access analysis** | Wall gap constraints that limit cutter diameter |

Drawing parser (`scripts/parse_drawing.py`) extracts tolerances and GD&T from engineering drawing PDFs.

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

  dfmResultJson     String?    // entire report as one JSON blob
  drawingParseJson  String?
}
```

Manage via: `turso db shell facet`

---

## Model Server Setup (one time)

Spin up a $5/mo server (Railway or DigitalOcean). Then:

```bash
# Install conda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
source ~/.bashrc

# Accept TOS if prompted
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# Create environment
conda create -n dfm python=3.11 -y
conda activate dfm
conda install -c conda-forge pythonocc-core -y
pip install pdfplumber

# Clone and run
git clone [your-repo]
cd dfm-model
# Start the HTTP server (server.py — wraps run.py as an endpoint)
python server.py
```

---

## Environment Variables

**Vercel:**
```
DATABASE_URL=           # Turso/LibSQL connection string
RESEND_API_KEY=         # Email notifications
MODEL_SERVER_URL=       # URL of the Python model server (e.g. https://your-server.railway.app)
```

**Model server:**
```
# None needed — just receives files and returns JSON
```

---

## Security

### Already handled
- **SQL injection** — Prisma parameterizes all queries
- **XSS** — React escapes output by default
- **HTTPS** — Vercel provides this automatically. Model server needs HTTPS too (Railway/DigitalOcean provide this)
- **File names** — all uploads renamed to UUIDs, original names never used on disk

### Must do before sending to shops
- [ ] `.env` in `.gitignore` — confirm with `git log --all --full-history -- .env`
- [ ] `uploads/` in `.gitignore` — customer STEP files should never be in the repo
- [ ] `node_modules/` in `.gitignore`
- [ ] File size limit — add `if (step.size > 50_000_000)` check in upload route (50MB cap)
- [ ] Model server auth — add a shared secret header so only your Vercel app can call the model server, not anyone with the URL
- [ ] Rate limit — basic protection against upload spam (even just an in-memory counter is fine for now)

### Do later
- [ ] Per-upload access control on `/api/files/[name]` — right now anyone who guesses a UUID can download a STEP file. Low risk (UUIDs are unguessable) but should be locked down once you have real customers
- [ ] Email verification — currently no check that the email is real
- [ ] Upload cleanup — old files accumulate on disk, add a cron to delete files older than 30 days

---

## Tomorrow's Checklist

### 1. Merge JR's branch
```bash
git add -A && git commit -m "landing page + upload route"
git fetch origin
git merge origin/[his-branch-name]
```

### 2. Recreate /api/files/[name] route
Serves files from uploads/ — needed for HTML reports to load in browser.

### 3. Create /api/jobs/[jobId] route
Returns job status so frontend can poll and redirect when complete.

### 4. Edit dfm-model/run.py (two small changes)
- Comment out auto-open browser lines (the `subprocess.Popen(["open", ...])` block)
- Add `import json` + `print(json.dumps(report))` so route.ts can capture the output

### 5. Update .gitignore
```
.env
.env.local
uploads/
node_modules/
```

### 6. Set up model server
- Spin up Railway or DigitalOcean ($5/mo)
- Install conda + pythonocc-core + pdfplumber (same steps as local)
- Create a simple HTTP wrapper (server.py) that accepts a STEP file and returns JSON
- Update route.ts to `fetch` the model server instead of `spawn`

### 7. Test + ship
- Upload a STEP file on live URL
- Confirm report generates and displays
- Send link to shop owners

---

## Design Decisions

- **No auth / no accounts.** Upload and go.
- **Vercel + separate model server.** Vercel can't run Python/OpenCASCADE. Clean split: Vercel serves the frontend and API, model server handles the heavy compute.
- **Entire report stored as one JSON blob.** No schema changes when model adds capabilities.
- **Email required with upload.** How we close the feedback loop.
- **Drawing optional.** STEP is enough to generate value.
- **One landing page.** facetquote.com = value prop + upload. That's it.
