import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const key = req.nextUrl.searchParams.get("key");
  if (key !== process.env.INTERNAL_KEY) {
    return new NextResponse("Not found", { status: 404 });
  }
  return NextResponse.next();
}

export const config = {
    matcher: ["/internal/:path*", "/api/jobs/:path*", "/api/files/:path*"],
  };
