import { prisma } from "@/app/lib/prisma";
import { randomUUID } from "crypto";
import { writeFile, mkdir, rename, readdir } from "fs/promises";
import path from "path";
import { spawn } from "child_process";
import { Resend } from "resend";

// ────────────────────────────────────────────────────────────────
// POST /api/upload
//
// 1. Browser sends STEP + optional PDF + email + phone
// 2. Validate, save files to /uploads with UUID names
// 3. Create DB row
// 4. Spawn JR's Python model (fire-and-forget)
//    - Model writes HTML report in dfm-model/ directory
//    - When done, we move the HTML to /uploads so we can serve it
// 5. Email founder
// 6. Return jobId immediately
// ────────────────────────────────────────────────────────────────

const resend = new Resend(process.env.RESEND_API_KEY);

// ── Use conda Python where OpenCASCADE is installed ──
// Got this path from: conda activate dfm && which python
const PYTHON_PATH = "/usr/local/Caskroom/miniconda/base/envs/dfm/bin/python";

// ── Validation helpers ──

function isAllowedStep(name: string) {
  const n = name.toLowerCase();
  return n.endsWith(".step") || n.endsWith(".stp");
}

function isAllowedPdf(name: string) {
  return name.toLowerCase().endsWith(".pdf");
}

function isValidEmail(email: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// ── File storage ──

async function saveUpload(file: File, subdir = "uploads") {
  const bytes = await file.arrayBuffer();
  const buffer = Buffer.from(bytes);

  const original = file.name || "upload";
  const ext = path.extname(original) || "";
  const stored = `${randomUUID()}${ext}`;

  const dir = path.join(process.cwd(), subdir);
  await mkdir(dir, { recursive: true });

  const storedPath = path.join(dir, stored);
  await writeFile(storedPath, buffer);

  return { original, stored, storedPath };
}

// ── Run DFM model ──
// Spawns: /path/to/conda/python dfm-model/run.py /path/to/file.step
//
// JR's run.py writes an HTML report in the dfm-model/ directory
// named <stem>_report.html (e.g. "a1b2c3d4_report.html").
//
// After Python finishes, we:
// 1. Find that HTML file in dfm-model/
// 2. Move it to uploads/ so it can be served via /api/files/[name]
// 3. Store the filename in the DB

function runDfmModel(stepPath: string, jobId: string, stepStored: string) {
  const modelDir = path.join(process.cwd(), "dfm-model");
  const runScript = path.join(modelDir, "run.py");
  const uploadsDir = path.join(process.cwd(), "uploads");

  // The HTML report will be named based on the STEP file stem
  // e.g. stepStored = "a1b2c3d4-xxxx.step" → report = "a1b2c3d4-xxxx_report.html"
  const stem = path.basename(stepStored, path.extname(stepStored));
  const reportFilename = `${stem}_report.html`;

  const py = spawn(PYTHON_PATH, [runScript, stepPath], {
    cwd: modelDir, // run from dfm-model/ so Python imports work
  });

  let stdout = "";
  let stderr = "";

  py.stdout.on("data", (d: Buffer) => {
    stdout += d.toString();
  });
  py.stderr.on("data", (d: Buffer) => {
    stderr += d.toString();
  });

  py.on("close", async (code) => {
    if (code === 0) {
      console.log(`[dfm-model] Completed for job ${jobId}`);

      try {
        // Move the HTML report from dfm-model/ to uploads/
        const reportSrc = path.join(modelDir, reportFilename);
        const reportDest = path.join(uploadsDir, reportFilename);

        try {
          await rename(reportSrc, reportDest);
          console.log(`[dfm-model] Moved report to uploads/${reportFilename}`);
        } catch (moveErr) {
          // Report might not exist if model only printed to stdout
          console.warn(`[dfm-model] Could not move report: ${moveErr}`);
        }

        // Update DB with status + report filename + JSON if printed to stdout
        await prisma.uploadJob.update({
          where: { id: jobId },
          data: {
            status: "complete",
            dfmResultJson: stdout.trim() || null,
          },
        });
      } catch (e) {
        console.error(`[dfm-model] Failed to update DB:`, e);
      }
    } else {
      console.error(`[dfm-model] Failed for job ${jobId} (exit code ${code})`);
      console.error(stderr);

      try {
        await prisma.uploadJob.update({
          where: { id: jobId },
          data: { status: "error" },
        });
      } catch (e) {
        console.error(`[dfm-model] Failed to update error status:`, e);
      }
    }
  });
}

// ── Run drawing parser ──

function runDrawingParser(drawingPath: string, jobId: string) {
  const py = spawn(PYTHON_PATH, ["scripts/parse_drawing.py", drawingPath]);

  let parseOutput = "";

  py.stdout.on("data", (d: Buffer) => {
    parseOutput += d.toString();
  });
  py.stderr.on("data", (d: Buffer) => {
    console.error("[parse_drawing]", d.toString());
  });

  py.on("close", async (code) => {
    if (code === 0 && parseOutput.trim()) {
      try {
        await prisma.uploadJob.update({
          where: { id: jobId },
          data: { drawingParseJson: parseOutput.trim() },
        });
        console.log(`[parse_drawing] Stored results for job ${jobId}`);
      } catch (e) {
        console.error("[parse_drawing] Failed to store:", e);
      }
    }
  });
}

// ── Main route handler ──

export async function POST(req: Request) {
  try {
    const formData = await req.formData();

    // ── Validate files ──
    const step = formData.get("step");
    const drawing = formData.get("drawing");

    if (!step || !(step instanceof File) || step.size === 0) {
      return Response.json({ error: "STEP file is required." }, { status: 400 });
    }
    if (!isAllowedStep(step.name)) {
      return Response.json({ error: "File must be .step or .stp" }, { status: 400 });
    }

    const hasDrawing = drawing instanceof File && drawing.size > 0;
    if (hasDrawing && !isAllowedPdf((drawing as File).name)) {
      return Response.json({ error: "Drawing must be a PDF." }, { status: 400 });
    }

    // ── Validate contact ──
    const email = formData.get("email")?.toString().trim().toLowerCase() || "";
    const phone = formData.get("phone")?.toString().trim() || null;

    if (!email || !isValidEmail(email)) {
      return Response.json({ error: "Valid email is required." }, { status: 400 });
    }

    // ── Save files ──
    const savedStep = await saveUpload(step, "uploads");
    const savedDrawing = hasDrawing
      ? await saveUpload(drawing as File, "uploads")
      : null;

    // ── Create DB row ──
    const job = await prisma.uploadJob.create({
      data: {
        status: "received",
        email,
        phone,
        stepOriginal: savedStep.original,
        stepStored: savedStep.stored,
        drawingOriginal: savedDrawing?.original ?? null,
        drawingStored: savedDrawing?.stored ?? null,
      },
      select: { id: true },
    });

    // ── Run DFM model (fire-and-forget) ──
    // Pass stepStored so we can find the HTML report by name
    runDfmModel(savedStep.storedPath, job.id, savedStep.stored);

    // ── Parse drawing (fire-and-forget) ──
    if (savedDrawing) {
      runDrawingParser(savedDrawing.storedPath, job.id);
    }

    // ── Notify founder ──
    resend.emails
      .send({
        from: "notifications@facetquote.com",
        to: "sunjay@facetquote.com",
        subject: `New upload: ${savedStep.original} from ${email}`,
        text: [
          `Email: ${email}`,
          `Phone: ${phone || "—"}`,
          `STEP: ${savedStep.original} (${savedStep.stored})`,
          `Drawing: ${savedDrawing ? savedDrawing.original : "—"}`,
          `Job ID: ${job.id}`,
        ].join("\n"),
      })
      .catch((e) => {
        console.error("[resend] Notification failed:", e);
      });

    // ── Return job ID + report URL ──
    // The report won't exist yet (model is still running), but the
    // frontend can poll /api/jobs/[jobId] or just wait and navigate
    // to the report URL when ready
    const stem = path.basename(savedStep.stored, path.extname(savedStep.stored));
    const reportFilename = `${stem}_report.html`;

    return Response.json({
      jobId: job.id,
      reportUrl: `/api/files/${reportFilename}`,
    });

  } catch (err) {
    console.error("[upload] Unexpected error:", err);
    return Response.json(
      { error: "Upload failed. Please try again." },
      { status: 500 }
    );
  }
}