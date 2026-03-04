import { PrismaClient } from "@prisma/client/edge";
import { createClient } from "@libsql/client";
import { PrismaLibSql } from "@prisma/adapter-libsql";

const adapter = new PrismaLibSql(createClient({
  url: process.env.DATABASE_URL!,
}));

declare global {
  var prisma: PrismaClient | undefined;
}

export const prisma =
  global.prisma ??
  new PrismaClient({ adapter });

if (process.env.NODE_ENV !== "production") global.prisma = prisma;