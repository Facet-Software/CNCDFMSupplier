import { prisma } from "@/app/lib/prisma";
import { randomUUID } from "crypto";
import { writeFile, mkdir, rename } from "fs/promises";
import path from "path";
import { spawn } from "child_process";
import { Resend } from "resend";

// ────────────────────────────────────────────────────────────────
// POST /api/upload
//
// Everything runs on the same server:
// 1. Save STEP file to /uploads
// 2. Create DB row in Turso (status: "received")
// 3. Spawn JR's Python model (fire-and-forget)
// 4. Return jobId immediately — don't wait for Python
// 5. Frontend polls /api/jobs/[jobId] until complete
// 6. When Python finishes → stores JSON + moves HTML to uploads
// ────────────────────────────────────────────────────────────────

const resend = new Resend(process.env.RESEND_API_KEY);

// Conda Python path — update this for your server
// Find it with: conda activate dfm && which python
const PYTHON_PATH = process.env.PYTHON_PATH || "/usr/local/Caskroom/miniconda/base/envs/dfm/bin/python";

// ── Helpers ──

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

// ── Spawn model (fire-and-forget) ──

function runDfmModel(stepPath: string, jobId: string, stepStored: string) {
  const modelDir = path.join(process.cwd(), "dfm-model");
  const runScript = path.join(modelDir, "run.py");
  const uploadsDir = path.join(process.cwd(), "uploads");

  const stem = path.basename(stepStored, path.extname(stepStored));
  const reportFilename = `${stem}_report.html`;

  const py = spawn(PYTHON_PATH, [runScript, stepPath], { cwd: modelDir });

  let stdout = "";
  let stderr = "";

  py.stdout.on("data", (d: Buffer) => { stdout += d.toString(); });
  py.stderr.on("data", (d: Buffer) => { stderr += d.toString(); });

  py.on("close", async (code) => {
    if (code === 0) {
      console.log(`[dfm-model] Completed for job ${jobId}`);

      // Move HTML report from dfm-model/ to uploads/
      try {
        const reportSrc = path.join(modelDir, reportFilename);
        const reportDest = path.join(uploadsDir, reportFilename);
        await rename(reportSrc, reportDest);
        console.log(`[dfm-model] Report → uploads/${reportFilename}`);
      } catch {
        console.warn(`[dfm-model] Could not move report HTML`);
      }

      // Store JSON + mark complete
      try {
        await prisma.uploadJob.update({
          where: { id: jobId },
          data: {
            status: "complete",
            dfmResultJson: stdout.trim() || null,
          },
        });
      } catch (e) {
        console.error(`[dfm-model] DB update failed:`, e);
      }
    } else {
      console.error(`[dfm-model] Failed for job ${jobId} (exit ${code})`);
      console.error(stderr);
      try {
        await prisma.uploadJob.update({
          where: { id: jobId },
          data: { status: "error" },
        });
      } catch (e) {
        console.error(`[dfm-model] DB error update failed:`, e);
      }
    }
  });
}

// ── Route handler ──

export async function POST(req: Request) {
  try {
    const formData = await req.formData();

    const step = formData.get("step");
    const drawing = formData.get("drawing");

    if (!step || !(step instanceof File) || step.size === 0) {
      return Response.json({ error: "STEP file is required." }, { status: 400 });
    }
    if (!isAllowedStep(step.name)) {
      return Response.json({ error: "File must be .step or .stp" }, { status: 400 });
    }
    if (step.size > 50_000_000) {
      return Response.json({ error: "File too large. Max 50MB." }, { status: 400 });
    }

    const hasDrawing = drawing instanceof File && drawing.size > 0;
    if (hasDrawing && !isAllowedPdf((drawing as File).name)) {
      return Response.json({ error: "Drawing must be a PDF." }, { status: 400 });
    }

    const email = formData.get("email")?.toString().trim().toLowerCase() || "";
    const phone = formData.get("phone")?.toString().trim() || null;

    if (!email || !isValidEmail(email)) {
      return Response.json({ error: "Valid email is required." }, { status: 400 });
    }

    // Save files
    const savedStep = await saveUpload(step, "uploads");
    const savedDrawing = hasDrawing ? await saveUpload(drawing as File, "uploads") : null;

    // Create DB row
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

    // Spawn model (returns immediately, Python runs in background)
    runDfmModel(savedStep.storedPath, job.id, savedStep.stored);

    // Email notification (fire-and-forget)
    resend.emails
      .send({
        from: "notifications@facetquote.com",
        to: "sunjay@facetquote.com",
        subject: `New upload: ${savedStep.original} from ${email}`,
        text: `Email: ${email}\nPhone: ${phone || "—"}\nSTEP: ${savedStep.original}\nJob ID: ${job.id}`,
      })
      .catch((e) => console.error("[resend]", e));

    // Return immediately — frontend will poll for completion
    return Response.json({ jobId: job.id });

  } catch (err) {
    console.error("[upload]", err);
    return Response.json({ error: "Upload failed. Please try again." }, { status: 500 });
  }
}