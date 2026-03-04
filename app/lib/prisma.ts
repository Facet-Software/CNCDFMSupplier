import { PrismaClient } from "@prisma/client";
import { createClient } from "@libsql/client";
import { PrismaLibSql } from "@prisma/adapter-libsql";

const client = createClient({
  url: process.env.DATABASE_URL!,
});

const adapter = new PrismaLibSql(client);

export const prisma = new PrismaClient({ adapter });