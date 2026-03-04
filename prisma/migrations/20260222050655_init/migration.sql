-- CreateTable
CREATE TABLE "UploadJob" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "originalFilename" TEXT NOT NULL,
    "storedFilename" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'received',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
