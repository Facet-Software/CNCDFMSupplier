import { prisma } from "@/app/lib/prisma";
import { randomUUID } from "crypto";
import { writeFile, mkdir } from "fs/promises";
import path from "path";
import { spawn } from "child_process";

function isAllowedStep(name: string) {
  const n = name.toLowerCase();
  return n.endsWith(".step") || n.endsWith(".stp");
}

function isAllowedPdf(name: string) {
  return name.toLowerCase().endsWith(".pdf");
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

export async function POST(req: Request) {
  const formData = await req.formData();

  // Files (required STEP, optional PDF)
  const step = formData.get("step");
  const drawing = formData.get("drawing");

  if (!step || !(step instanceof File)) {
    return Response.json({ error: "Missing STEP file" }, { status: 400 });
  }
  if (!isAllowedStep(step.name)) {
    return Response.json({ error: "STEP must be .step or .stp" }, { status: 400 });
  }
  if (drawing && !(drawing instanceof File)) {
    return Response.json({ error: "Invalid drawing file" }, { status: 400 });
  }
  if (drawing instanceof File && !isAllowedPdf(drawing.name)) {
    return Response.json({ error: "Drawing must be a PDF" }, { status: 400 });
  }

  // Fields
  const batchVolume = formData.get("batchVolume")?.toString() || null;
  const surfaceTreatment = formData.get("surfaceTreatment")?.toString() || null;

  const insertsRaw = formData.get("inserts")?.toString() || "no"; // "yes" | "no"
  const inserts = insertsRaw === "yes";

  const insertCountRaw = formData.get("insertCount")?.toString() || "";
  const insertCount =
    inserts && insertCountRaw ? Number.parseInt(insertCountRaw, 10) : null;

  if (inserts) {
    if (!Number.isFinite(insertCount) || (insertCount as number) <= 0) {
      return Response.json({ error: "Insert count must be a positive integer" }, { status: 400 });
    }
  }

  // Save files
  const savedStep = await saveUpload(step, "uploads");
  const savedDrawing = drawing instanceof File ? await saveUpload(drawing, "uploads") : null;

  // Parse drawing
  if (savedDrawing) {
    const py = spawn("python3", ["scripts/parse_drawing.py", savedDrawing.storedPath]);
    py.stdout.on("data", (d) => console.log("[parse]", d.toString()));
    py.stderr.on("data", (d) => console.error("[parse error]", d.toString()));
  }

  // Create DB row
  const job = await prisma.uploadJob.create({
    data: {
      status: "received",
      // fixed for MVP:
      material: "6061",
      manufacturing: "CNC",

      batchVolume,
      surfaceTreatment,
      inserts,
      insertCount: inserts ? (insertCount as number) : null,

      stepOriginal: savedStep.original,
      stepStored: savedStep.stored,

      drawingOriginal: savedDrawing?.original ?? null,
      drawingStored: savedDrawing?.stored ?? null,
    },
    select: { id: true },
  });

  // Kick off JR processing (non-blocking best effort)
  // 1) simplest: fire-and-forget internal endpoint that calls JR
  // 2) or direct fetch to JR service here
  // For now, do (1) to keep create fast:
  try {
    const url = new URL("/api/jobs/enqueue", req.url);
    // don’t await long; just attempt
    fetch(url.toString(), {
      method: "POST",
      headers: { "content-type": "application/json", 
        "x-internal-key": process.env.INTERNAL_KEY ?? ""},
      body: JSON.stringify({ jobId: job.id }),
    }).catch(() => {});
  } catch {}

  return Response.json({ id: job.id });
}