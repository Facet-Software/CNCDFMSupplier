import { readFile } from "fs/promises";
import path from "path";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ name: string }> }
) {
  const { name } = await params;

  // basic safety
  if (!name || name.includes("..") || name.includes("/") || name.includes("\\")) {
    return new Response("Bad file name", { status: 400 });
  }

  const filePath = path.join(process.cwd(), "uploads", name);

  try {
    const buf = await readFile(filePath);

    // content-type guess
    const lower = name.toLowerCase();
    const contentType = lower.endsWith(".pdf")
      ? "application/pdf"
      : "application/octet-stream";

    return new Response(buf, {
      headers: {
        "content-type": contentType,
        "content-disposition": `attachment; filename="${name}"`,
      },
    });
  } catch {
    return new Response("Not found", { status: 404 });
  }
}