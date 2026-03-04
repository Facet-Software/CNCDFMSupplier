-- CreateTable
CREATE TABLE "JobSupplierMatch" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "jobId" TEXT NOT NULL,
    "supplierId" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'suggested',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "JobSupplierMatch_jobId_fkey" FOREIGN KEY ("jobId") REFERENCES "UploadJob" ("id") ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT "JobSupplierMatch_supplierId_fkey" FOREIGN KEY ("supplierId") REFERENCES "Supplier" ("id") ON DELETE RESTRICT ON UPDATE CASCADE
);

-- CreateIndex
CREATE UNIQUE INDEX "JobSupplierMatch_jobId_supplierId_key" ON "JobSupplierMatch"("jobId", "supplierId");
