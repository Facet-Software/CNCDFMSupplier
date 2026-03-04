-- RedefineTables
PRAGMA defer_foreign_keys=ON;
PRAGMA foreign_keys=OFF;
CREATE TABLE "new_UploadJob" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "status" TEXT NOT NULL DEFAULT 'received',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "material" TEXT NOT NULL DEFAULT '6061',
    "manufacturing" TEXT NOT NULL DEFAULT 'CNC',
    "batchVolume" TEXT,
    "surfaceTreatment" TEXT,
    "inserts" BOOLEAN NOT NULL DEFAULT false,
    "insertCount" INTEGER,
    "stepOriginal" TEXT,
    "stepStored" TEXT,
    "drawingOriginal" TEXT,
    "drawingStored" TEXT
);
INSERT INTO "new_UploadJob" ("batchVolume", "createdAt", "drawingOriginal", "drawingStored", "id", "insertCount", "inserts", "material", "status", "stepOriginal", "stepStored", "surfaceTreatment") SELECT "batchVolume", "createdAt", "drawingOriginal", "drawingStored", "id", "insertCount", "inserts", "material", "status", "stepOriginal", "stepStored", "surfaceTreatment" FROM "UploadJob";
DROP TABLE "UploadJob";
ALTER TABLE "new_UploadJob" RENAME TO "UploadJob";
PRAGMA foreign_keys=ON;
PRAGMA defer_foreign_keys=OFF;
