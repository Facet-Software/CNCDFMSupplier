import { prisma } from "@/app/lib/prisma";
import { NextResponse } from "next/server";


export async function POST(req: Request) {
  const key = req.headers.get("x-internal-key");
  if (key !== process.env.INTERNAL_KEY) {
    return new NextResponse("Not found", { status: 404 });
  }
  const { jobId } = await req.json();
  if (!jobId) return Response.json({ error: "Missing jobId" }, { status: 400 });

  const job = await prisma.uploadJob.findUnique({
    where: { id: jobId },
    select: {
      id: true,
      material: true,
      manufacturing: true,
      batchVolume: true,
      surfaceTreatment: true,
      inserts: true,
      insertCount: true,
      stepStored: true,
      drawingStored: true,
    },
  });

  if (!job) return Response.json({ error: "Job not found" }, { status: 404 });
  if (!job.stepStored) return Response.json({ error: "Job missing STEP" }, { status: 400 });

  // You need a way for JR to download the files.
  // We'll create /api/files/<storedName> next. For now, construct URLs:
  const base = new URL(req.url).origin;
  const stepUrl = `${base}/api/files/${encodeURIComponent(job.stepStored)}`;
  const drawingUrl = job.drawingStored
    ? `${base}/api/files/${encodeURIComponent(job.drawingStored)}`
    : null;

  // Send to JR (replace with his real endpoint)
  const jrEndpoint = process.env.JR_MODEL_URL; // e.g. https://jr-service.xyz/process
  if (!jrEndpoint) {
    // still OK for dev; you can enqueue later
    return Response.json({ ok: true, skipped: "JR_MODEL_URL not set" });
  }

  const res = await fetch(jrEndpoint, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      jobId: job.id,
      inputs: {
        material: job.material,
        manufacturing: job.manufacturing,
        batchVolume: job.batchVolume,
        surfaceTreatment: job.surfaceTreatment,
        inserts: job.inserts,
        insertCount: job.insertCount,
      },
      files: { stepUrl, drawingUrl },
    }),
  });

  const text = await res.text();
  if (!res.ok) {
    return Response.json({ error: `JR failed: ${res.status} ${text}` }, { status: 502 });
  }
  console.log("stepUrl:", stepUrl);
  console.log("drawingUrl:", drawingUrl);
  // optionally store returned outputs on the job later
  return Response.json({ ok: true });
}