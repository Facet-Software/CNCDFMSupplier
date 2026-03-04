"use client";

import { useMemo, useState } from "react";

type BatchVolume = "proto" | "small" | "medium" | "large";
type SurfaceTreatment = "none" | "anodize" | "chem_film" | "paint";
type ToleranceTier = "standard" | "tight" | "loose";
type InspectionRequired = "no" | "yes";
type LeadTime = "standard" | "rush";

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes)) return "";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function IntakePage() {
  const [stepFile, setStepFile] = useState<File | null>(null);
  const [drawingFile, setDrawingFile] = useState<File | null>(null);

  const [batchVolume, setBatchVolume] = useState<BatchVolume>("small");
  const [surfaceTreatment, setSurfaceTreatment] = useState<SurfaceTreatment>("none");
  const [inserts, setInserts] = useState<"no" | "yes">("no");
  const [insertCount, setInsertCount] = useState<string>("");
  const [tolerance, setTolerance] = useState<ToleranceTier>("standard");
  const [inspectionRequired, setInspectionRequired] = useState<InspectionRequired>("no");
  const [inspectionFeatures, setInspectionFeatures] = useState<string>("");
  const [leadTime, setLeadTime] = useState<LeadTime>("standard");
  const [rushDate, setRushDate] = useState<string>("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedId, setSubmittedId] = useState<string | null>(null);

  const stepMeta = useMemo(() => {
    if (!stepFile) return null;
    return { name: stepFile.name, size: formatBytes(stepFile.size) };
  }, [stepFile]);

  const drawingMeta = useMemo(() => {
    if (!drawingFile) return null;
    return { name: drawingFile.name, size: formatBytes(drawingFile.size) };
  }, [drawingFile]);

  const minRushDate = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().split("T")[0];
  }, []);

  function validate(): string | null {
    if (!stepFile) return "STEP file is required.";
    const stepName = stepFile.name.toLowerCase();
    if (!stepName.endsWith(".step") && !stepName.endsWith(".stp"))
      return "STEP file must be .step or .stp.";
    if (!drawingFile) return "Drawing is required.";
    if (drawingFile) {
      const dName = drawingFile.name.toLowerCase();
      if (!dName.endsWith(".pdf")) return "Engineering drawing must be a PDF.";
    }
    if (inserts === "yes") {
      const n = Number(insertCount);
      if (!Number.isFinite(n) || n <= 0) return "Insert count must be a positive number.";
    }
    if (leadTime === "rush" && !rushDate) return "Select a required date for rush jobs.";
    return null;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const v = validate();
    if (v) { setError(v); return; }
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("batchVolume", batchVolume);
      fd.append("surfaceTreatment", surfaceTreatment);
      fd.append("inserts", inserts);
      if (inserts === "yes") fd.append("insertCount", insertCount);
      fd.append("tolerance", tolerance);
      fd.append("inspectionRequired", inspectionRequired);
      if (inspectionRequired === "yes" && inspectionFeatures.trim())
        fd.append("inspectionFeatures", inspectionFeatures.trim());
      fd.append("leadTime", leadTime);
      if (leadTime === "rush") fd.append("rushDate", rushDate);
      fd.append("step", stepFile!);
      if (drawingFile) fd.append("drawing", drawingFile);

      const res = await fetch("/api/jobs/create", { method: "POST", body: fd });
      const text = await res.text();
      let data: any = null;
      try { data = JSON.parse(text); } catch {}
      if (!res.ok) throw new Error(data?.error || `Submit failed (${res.status})`);
      if (!data?.id) throw new Error("Server did not return a job id.");
      setSubmittedId(data.id);
    } catch (err: any) {
      setError(err?.message || "Submit failed.");
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    setSubmittedId(null); setStepFile(null); setDrawingFile(null);
    setInserts("no"); setInsertCount(""); setBatchVolume("small");
    setSurfaceTreatment("none"); setTolerance("standard");
    setInspectionRequired("no"); setInspectionFeatures("");
    setLeadTime("standard"); setRushDate("");
  }

  if (submittedId) {
    return (
      <main className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center">
        <div className="mx-auto max-w-md px-6 text-center">
          <div className="text-4xl mb-4">✓</div>
          <h1 className="text-2xl font-semibold tracking-tight">Job submitted</h1>
          <p className="mt-2 text-sm text-zinc-400">Your files are being processed. Job ID:</p>
          <p className="mt-2 font-mono text-xs text-zinc-500 break-all">{submittedId}</p>
          <button onClick={reset}
            className="mt-6 rounded-xl px-4 py-2 text-sm font-medium bg-zinc-800 text-zinc-100 hover:bg-zinc-700 transition">
            Submit another
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      <div className="mx-auto max-w-4xl px-6 py-5">

        {/* Header */}
        <div className="flex items-start justify-between gap-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Get Competitive Quotes from CNC Shops for Aluminum Brackets
            </h1>
            <p className="mt-1 text-sm text-zinc-400">
              STEP required. Drawing required
            </p>
          </div>
          <button type="submit" form="intakeForm" disabled={submitting}
            className={`mt-1 shrink-0 rounded-xl px-4 py-2 text-sm font-medium transition ${
              submitting
                ? "cursor-not-allowed bg-zinc-700 text-zinc-200"
                : "bg-emerald-500 text-zinc-950 hover:bg-emerald-400"
            }`}>
            {submitting ? "Submitting..." : "Submit"}
          </button>
        </div>

        {error && (
          <div className="mt-3 rounded-xl border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-200">
            {error}
          </div>
        )}

        <form id="intakeForm" onSubmit={onSubmit} className="mt-4 grid gap-3">

          {/* Files */}
          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Files</h2>
              <span className="text-xs text-zinc-500">STEP required · PDF optional</span>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {/* STEP */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium">STEP file</div>
                  <div className="text-xs text-zinc-500">.step / .stp</div>
                </div>
                <label className="mt-2 flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-zinc-700 bg-zinc-950 px-4 py-3 text-center hover:border-zinc-500">
                  <input type="file" accept=".step,.stp" className="hidden"
                    onChange={(e) => setStepFile(e.target.files?.[0] || null)} />
                  <div className="text-sm text-zinc-300">
                    {stepMeta ? <span className="font-medium">{stepMeta.name}</span> : "Click to select STEP file"}
                  </div>
                  <div className="mt-0.5 text-xs text-zinc-500">
                    {stepMeta ? stepMeta.size : "We don't share your design publicly."}
                  </div>
                  {stepMeta && (
                    <button type="button" className="mt-2 text-xs text-zinc-400 underline hover:text-zinc-200"
                      onClick={(e) => { e.preventDefault(); setStepFile(null); }}>
                      Remove
                    </button>
                  )}
                </label>
              </div>

              {/* PDF */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium">Engineering drawing</div>
                  <div className="text-xs text-zinc-500">PDF</div>
                </div>
                <label className="mt-2 flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-zinc-700 bg-zinc-950 px-4 py-3 text-center hover:border-zinc-500">
                  <input type="file" accept=".pdf" className="hidden"
                    onChange={(e) => setDrawingFile(e.target.files?.[0] || null)} />
                  <div className="text-sm text-zinc-300">
                    {drawingMeta ? <span className="font-medium">{drawingMeta.name}</span> : "Upload drawing (PDF)"}
                  </div>
                  <div className="mt-0.5 text-xs text-zinc-500">
                    {drawingMeta ? drawingMeta.size : "Recommend GD&T / notes."}
                  </div>
                  {drawingMeta && (
                    <button type="button" className="mt-2 text-xs text-zinc-400 underline hover:text-zinc-200"
                      onClick={(e) => { e.preventDefault(); setDrawingFile(null); }}>
                      Remove
                    </button>
                  )}
                </label>
              </div>
            </div>
          </section>

          {/* Manufacturing requirements */}
          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-4 shadow-sm">
            <h2 className="text-base font-semibold">Manufacturing requirements</h2>
            <p className="mt-0.5 text-sm text-zinc-400">Used for supplier pricing and routing.</p>

            <div className="mt-3 grid gap-3 sm:grid-cols-2">

              {/* Batch Volume */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
                <label className="text-sm font-medium">Batch volume</label>
                <select value={batchVolume} onChange={(e) => setBatchVolume(e.target.value as BatchVolume)}
                  className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500">
                  <option value="proto">Prototype (1–10)</option>
                  <option value="small">Small (10–100)</option>
                  <option value="medium">Medium (100–1k)</option>
                  <option value="large">Large (1k+)</option>
                </select>
              </div>

              {/* Surface Treatment */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
                <label className="text-sm font-medium">Surface treatment</label>
                <select value={surfaceTreatment} onChange={(e) => setSurfaceTreatment(e.target.value as SurfaceTreatment)}
                  className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500">
                  <option value="none">None</option>
                  <option value="anodize">Anodization</option>
                  <option value="chem_film">Chem film</option>
                  <option value="paint">Paint</option>
                </select>
              </div>

              {/* Tolerance */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
                <label className="text-sm font-medium">Tolerance</label>
                <div className="mt-2 flex gap-2">
                  {(["loose", "standard", "tight"] as ToleranceTier[]).map((v) => (
                    <button key={v} type="button" onClick={() => setTolerance(v)}
                      className={`flex-1 rounded-lg border px-3 py-2 text-sm capitalize transition ${
                        tolerance === v
                          ? "border-zinc-500 bg-zinc-900 text-zinc-100"
                          : "border-zinc-700 bg-zinc-950 text-zinc-400 hover:border-zinc-500"
                      }`}>
                      {v}
                    </button>
                  ))}
                </div>
              </div>

              {/* Inserts */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
                <label className="text-sm font-medium">Inserts</label>
                <div className="mt-2 flex gap-2">
                  {(["no", "yes"] as const).map((v) => (
                    <button key={v} type="button" onClick={() => setInserts(v)}
                      className={`flex-1 rounded-lg border px-3 py-2 text-sm transition ${
                        inserts === v
                          ? "border-zinc-500 bg-zinc-900 text-zinc-100"
                          : "border-zinc-700 bg-zinc-950 text-zinc-400 hover:border-zinc-500"
                      }`}>
                      {v === "no" ? "No" : "Yes"}
                    </button>
                  ))}
                </div>
                {inserts === "yes" && (
                  <input value={insertCount} onChange={(e) => setInsertCount(e.target.value)}
                    placeholder="Count, e.g. 4" inputMode="numeric"
                    className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500" />
                )}
              </div>

              {/* Inspection */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium">Inspection</label>
                  <span className="text-xs text-zinc-500">Adds to price</span>
                </div>
                <div className="mt-2 flex gap-2">
                  {(["no", "yes"] as const).map((v) => (
                    <button key={v} type="button" onClick={() => setInspectionRequired(v)}
                      className={`flex-1 rounded-lg border px-3 py-2 text-sm transition ${
                        inspectionRequired === v
                          ? "border-zinc-500 bg-zinc-900 text-zinc-100"
                          : "border-zinc-700 bg-zinc-950 text-zinc-400 hover:border-zinc-500"
                      }`}>
                      {v === "no" ? "No" : "Yes"}
                    </button>
                  ))}
                </div>
                {inspectionRequired === "yes" && (
                  <input value={inspectionFeatures} onChange={(e) => setInspectionFeatures(e.target.value)}
                    placeholder="Critical features or surfaces, e.g. bore Ø12, mating face"
                    className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-zinc-500" />
                )}
              </div>

              {/* Fixed tags */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-950/40 p-3">
                <div className="flex flex-wrap gap-2 text-sm">
                  <span className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-200">
                    Process: CNC machining
                  </span>
                  <span className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-200">
                    Material: 6061 Aluminum
                  </span>
                </div>
              </div>

            </div>
          </section>

          {/* Lead time */}
          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-4 shadow-sm">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold">Lead time</h2>
                <p className="mt-0.5 text-sm text-zinc-400">
                  Standard lead time is estimated after review — depends on part complexity and supplier availability.
                </p>
              </div>
              <div className="mt-0.5 flex shrink-0 gap-2">
                {([
                  { value: "standard" as const, label: "Standard" },
                  { value: "rush" as const, label: "Rush" },
                ]).map((o) => (
                  <button key={o.value} type="button" onClick={() => setLeadTime(o.value)}
                    className={`rounded-lg border px-4 py-2 text-sm transition ${
                      leadTime === o.value
                        ? "border-zinc-500 bg-zinc-900 text-zinc-100"
                        : "border-zinc-700 bg-zinc-950 text-zinc-400 hover:border-zinc-500"
                    }`}>
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
            {leadTime === "rush" && (
              <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-end">
                <div className="sm:w-48">
                  <label className="text-xs text-zinc-500">Required by date</label>
                  <input type="date" value={rushDate} min={minRushDate}
                    onChange={(e) => setRushDate(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-500" />
                </div>
                <div className="rounded-lg border border-amber-900/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
                  Rush jobs carry a premium. We'll confirm pricing before proceeding.
                </div>
              </div>
            )}
          </section>

          {/* Bottom bar */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs text-zinc-500">
              STEP required · PDF optional · Material fixed to 6061 for MVP
            </div>
          </div>

        </form>
      </div>
    </main>
  );
}