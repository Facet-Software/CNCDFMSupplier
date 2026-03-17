import { prisma } from "@/app/lib/prisma";

// ────────────────────────────────────────────────────────────────
// GET /api/jobs/[jobId]
//
// Frontend polls this every 2 seconds after uploading.
// When status = "complete", returns the report URL.
// Frontend then redirects the user to the HTML report.
// ────────────────────────────────────────────────────────────────

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ jobID: string }> }
) {
  const { jobID } = await params;

  if (!jobID) {
    return Response.json({ error: "Missing job ID" }, { status: 400 });
  }

  const job = await prisma.uploadJob.findUnique({
    where: { id: jobID },
    select: {
      id: true,
      status: true,
      stepStored: true,
    },
  });

  if (!job) {
    return Response.json({ error: "Job not found" }, { status: 404 });
  }

  // Build report URL from the STEP filename
  // stepStored = "a1b2c3d4-xxxx.step" → report = "a1b2c3d4-xxxx_report.html"
  const stem = job.stepStored.replace(/\.(step|stp)$/i, "");
  const reportUrl = `/api/files/${stem}_report.html`;

  return Response.json({
    status: job.status,
    reportUrl: job.status === "complete" ? reportUrl : null,
  });
}