import { prisma } from "@/app/lib/prisma";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const { email, name, company, location, role } = await req.json();

    if (!email || typeof email !== "string") {
      return NextResponse.json({ error: "Email required" }, { status: 400 });
    }

    const entry = await prisma.waitlistEntry.create({
      data: {
        email: email.trim().toLowerCase(),
        name: name?.trim() || null,
        company: company?.trim() || null,
        location: location?.trim() || null,
        role: role === "shop" ? "shop" : "designer",
      },
    });

    return NextResponse.json({ ok: true, id: entry.id });
  } catch (err: any) {
    // P2002 = unique constraint (duplicate email) — still return ok to user
    if (err?.code === "P2002") {
      return NextResponse.json({ ok: true, duplicate: true });
    }
    console.error("Waitlist error:", err);
    return NextResponse.json({ error: "Server error" }, { status: 500 });
  }
}
