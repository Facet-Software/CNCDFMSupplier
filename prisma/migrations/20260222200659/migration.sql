/*
  Warnings:

  - You are about to drop the column `finish` on the `UploadJob` table. All the data in the column will be lost.
  - You are about to drop the column `originalFilename` on the `UploadJob` table. All the data in the column will be lost.
  - You are about to drop the column `quantityBucket` on the `UploadJob` table. All the data in the column will be lost.
  - You are about to drop the column `storedFilename` on the `UploadJob` table. All the data in the column will be lost.
  - You are about to drop the column `toleranceBucket` on the `UploadJob` table. All the data in the column will be lost.

*/
-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_UploadJob" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "status" TEXT NOT NULL DEFAULT 'received',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "material" TEXT NOT NULL DEFAULT '6061',
    "batchVolume" TEXT,
    "surfaceTreatment" TEXT,
    "inserts" BOOLEAN NOT NULL DEFAULT false,
    "insertCount" INTEGER,
    "stepOriginal" TEXT,
    "stepStored" TEXT,
    "drawingOriginal" TEXT,
    "drawingStored" TEXT
);
INSERT INTO "new_UploadJob" ("createdAt", "id", "status") SELECT "createdAt", "id", "status" FROM "UploadJob";
DROP TABLE "UploadJob";
ALTER TABLE "new_UploadJob" RENAME TO "UploadJob";
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
