# Facet

DFM analysis tool for CNC machine shops. Upload a STEP file (+ optional drawing PDF), get an instant manufacturability report — setups, holes, thin walls, tool access, DFM flags. Cuts quoting prep time from hours to minutes.

Supplier-side only. No accounts. No marketplace.

---

## Architecture

Everything runs on the same machine. The Next.js app spawns the DFM model (Python) directly — no separate service, no HTTP between them.

```
app/
├── page.tsx                    # Landing page (supplier-focused + upload form)
├── layout.tsx                  # Root layout + metadata
├── globals.css                 # Global styles
├── api/
│   └── upload/
│       └── route.ts            # Handles STEP + optional PDF + email, stores files,
│                               #   spawns DFM model + drawing parser, returns jobId
├── lib/
│   └── prisma.ts               # Prisma client (Turso/LibSQL)
│
dfm-model/                       # DFM analysis engine (Python, OpenCASCADE)
│   ├── run.py                   # Entry point — spawned by upload route with STEP path
│   └── sourcing/                # Full pipeline (see DFM Engine section below)
│
scripts/
│   └── parse_drawing.py         # Tolerance parser for engineering drawing PDFs
│
prisma/
│   └── schema.prisma            # Database schema
│
uploads/                         # UUID-named files saved here (gitignored)
```

Results page architecture TBD — will be designed separately once upload flow is live.

---

## User Flow

```
1. Shop owner lands on facetquote.com
   └── Sees: value prop + upload zone above the fold

2. Uploads STEP file (required) + drawing PDF (optional) + enters email (required)
   └── Phone number: optional, shown but not blocking

3. Hits "Analyze"
   └── POST /api/upload
       ├── Validates files (STEP required, .step/.stp only)
       ├── Saves files to /uploads with UUID names
       ├── Creates UploadJob row in DB (status: "received")
       ├── Spawns dfm-model/run.py with STEP file path (fire-and-forget)
       ├── Spawns parse_drawing.py with PDF path if provided (fire-and-forget)
       ├── Sends notification email to founder (via Resend)
       └── Returns { jobId }

4. Client shows confirmation state
   └── "Your part is being analyzed. We'll follow up at [email]."
   └── Results page TBD

5. Background: run.py completes → updates UploadJob status to "complete"
   Background: parse_drawing.py completes → stores JSON in drawingParseJson
```

---

## Landing Page Structure (page.tsx)

**Above the fold:**
```
┌──────────────────────────────────────────────┐
│ NAV: Facet (left) ──── [Analyze a part] (right)│
├──────────────────────────────────────────────┤
│                                              │
│  HEADLINE:                                   │
│  "Upload a STEP file. Extract design intent, │
│   technical requirements, and DFM cost       │
│   drivers — in seconds."                     │
│                                              │
│  SUBHEAD:                                    │
│  Stop spending hours reviewing models and    │
│  drawings before you can quote. Facet pulls  │
│  the key requirements and flags major cost   │
│  drivers — so you spend time making parts,   │
│  not translating documents.                  │
│                                              │
│  3-axis vs 5-axis · Hole inventory + L/D ·   │
│  Thin walls · Min tool dia · DFM flags ·     │
│  Material removal %                          │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │  [ STEP file dropzone ] (required)   │    │
│  │  [ Drawing PDF dropzone ] (optional) │    │
│  │  [ Email ] [ Phone (optional) ]      │    │
│  │          [ Analyze part ]            │    │
│  └──────────────────────────────────────┘    │
│  🔒 Files stored under unique ID. Never shared│
│                                              │
└──────────────────────────────────────────────┘
```

**Below the fold:**
- What You Get (6-card grid: setups, holes, thin walls, volume, tooling, DFM flags)
- How It Works (3 steps)
- Your Files. Your Control. (trust section + CTA)

---

## DFM Engine (dfm-model/)

Full geometric analysis from a STEP file. Python + OpenCASCADE. Runs locally — spawned by the upload route with the saved STEP file path.

```
python3 dfm-model/run.py /path/to/saved/file.step
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
| **Conical chamfer detection** | External chamfers with angle + radii |
| **Tool access analysis** | Wall gap constraints that limit cutter diameter |

Drawing parser (`scripts/parse_drawing.py`) extracts general tolerance blocks, inline tolerances, and GD&T symbols from engineering drawing PDFs.

---

## Database Schema

```prisma
model UploadJob {
  id                String   @id @default(uuid())
  createdAt         DateTime @default(now())
  status            String   @default("received")  // received | processing | complete | error

  // Contact
  email             String
  phone             String?

  // Files
  stepOriginal      String
  stepStored        String
  drawingOriginal   String?
  drawingStored     String?

  // DFM results (JSON blob when model returns)
  dfmResultJson     String?

  // Drawing parse results
  drawingParseJson  String?
}
```

After changing schema: `npx prisma generate && npx prisma db push`

---

## API

### POST /api/upload
```
Request: multipart/form-data
  - step: File (required, .step or .stp)
  - drawing: File (optional, .pdf)
  - email: string (required)
  - phone: string (optional)

Response: { jobId: string }

Side effects:
  1. Save files to /uploads/<uuid>.step, /uploads/<uuid>.pdf
  2. Create UploadJob row
  3. Spawn dfm-model/run.py with STEP path (fire-and-forget, updates status on completion)
  4. Spawn parse_drawing.py with PDF path if provided (fire-and-forget, stores result in DB)
  5. Send notification email via Resend
```

Results-related endpoints will be designed with the results page.

---

## Local Dev Setup

```bash
# Install dependencies
npm install

# Set up database
npx prisma generate
npx prisma db push

# Make sure Python dependencies are installed for DFM model
pip install -r dfm-model/requirements.txt
pip install pdfplumber  # for parse_drawing.py

# Run dev server
npm run dev
```

Requires Python 3 with OpenCASCADE (pythonocc-core) installed for the DFM model.

---

## Implementation Phases

### Phase 1: Landing Page + Upload Flow
1. Update Prisma schema
2. Build POST /api/upload route
3. Build landing page with upload form + confirmation state on submit
4. Deploy

### Phase 2: Results Page (TBD)
- Architecture and design to be decided separately
- Will consume DFM model output (dfmResultJson stored in DB)

### Phase 3: Polish
1. Refine landing page design
2. Email notification when report is ready
3. Loading states and error handling

### Phase 4: Learn
1. Every upload → personal outreach within 24 hours
2. Track: upload started vs completed (drop-off = friction signal)
3. Ask: "Was this useful? What's missing?"

---

## Environment Variables
```
DATABASE_URL=         # Turso/LibSQL connection string
RESEND_API_KEY=       # Email notifications
```

That's it. No external model URL needed — DFM model runs locally via spawn.

---

## Design Decisions

- **No auth / no accounts.** Upload and go.
- **DFM model runs locally.** Spawned as a subprocess, not a separate service. Simplest thing that works.
- **Email required with upload.** How we close the feedback loop.
- **Phone optional.** Low friction.
- **Drawing optional.** STEP is enough to generate value. Drawing adds tolerance context.
- **Results page designed separately.** Ship the upload flow first.
- **One landing page.** facetquote.com = value prop + upload. That's it.
