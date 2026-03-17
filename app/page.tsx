"use client";

import { useState, useRef, useCallback, useEffect } from "react";

type UploadState = "idle" | "submitting" | "analyzing" | "done" | "error";

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes)) return "";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function HomePage() {
  const [stepFile, setStepFile] = useState<File | null>(null);
  const [drawingFile, setDrawingFile] = useState<File | null>(null);
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [jobId, setJobId] = useState("");
  const [stepDrag, setStepDrag] = useState(false);
  const [drawingDrag, setDrawingDrag] = useState(false);

  const stepInputRef = useRef<HTMLInputElement>(null);
  const drawingInputRef = useRef<HTMLInputElement>(null);
  const uploadRef = useRef<HTMLDivElement>(null);

  const scrollToUpload = () =>
    uploadRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });

  const onDrop = useCallback(
    (setter: (f: File) => void, extensions: string[]) =>
      (e: React.DragEvent) => {
        e.preventDefault();
        setStepDrag(false);
        setDrawingDrag(false);
        const file = e.dataTransfer.files?.[0];
        if (!file) return;
        const ext = file.name.toLowerCase().split(".").pop() || "";
        if (extensions.includes(ext)) setter(file);
      },
    []
  );

  const prevent = (e: React.DragEvent) => e.preventDefault();

  // ── Poll for model completion ──
  // After upload, check every 2s if the model is done.
  // When complete → redirect to the HTML report.
  useEffect(() => {
    if (uploadState !== "analyzing" || !jobId) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        const data = await res.json();

        if (data.status === "complete" && data.reportUrl) {
          clearInterval(interval);
          // Redirect to JR's HTML report
          window.location.href = data.reportUrl;
        } else if (data.status === "error") {
          clearInterval(interval);
          setErrorMsg("Analysis failed. We'll follow up at your email with results.");
          setUploadState("error");
        }
      } catch {
        // Network hiccup — keep polling
      }
    }, 2000);

    // Safety timeout — 3 minutes max
    const timeout = setTimeout(() => {
      clearInterval(interval);
      if (uploadState === "analyzing") {
        setErrorMsg("Analysis is taking longer than expected. We'll email your results.");
        setUploadState("error");
      }
    }, 180000);

    return () => { clearInterval(interval); clearTimeout(timeout); };
  }, [uploadState, jobId]);

  async function handleSubmit() {
    setErrorMsg("");
    if (!stepFile) { setErrorMsg("STEP file is required."); return; }
    const ext = stepFile.name.toLowerCase().split(".").pop() || "";
    if (!["step", "stp"].includes(ext)) { setErrorMsg("File must be .step or .stp"); return; }
    if (!email.trim() || !email.includes("@")) { setErrorMsg("Valid email is required."); return; }
    if (drawingFile) {
      const dExt = drawingFile.name.toLowerCase().split(".").pop() || "";
      if (dExt !== "pdf") { setErrorMsg("Drawing must be a PDF."); return; }
    }

    setUploadState("submitting");
    try {
      const fd = new FormData();
      fd.append("step", stepFile);
      if (drawingFile) fd.append("drawing", drawingFile);
      fd.append("email", email.trim().toLowerCase());
      if (phone.trim()) fd.append("phone", phone.trim());

      const res = await fetch("/api/upload", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || `Upload failed (${res.status})`);
      if (!data?.jobId) throw new Error("No job ID returned.");
      setJobId(data.jobId);
      // Go to analyzing state — start polling
      setUploadState("analyzing");
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "Upload failed.");
      setUploadState("error");
    }
  }

  function reset() {
    setStepFile(null); setDrawingFile(null); setEmail(""); setPhone("");
    setUploadState("idle"); setErrorMsg(""); setJobId("");
  }

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
          --bg: #ffffff;
          --bg-secondary: #f8f8f8;
          --text: #111111;
          --text-secondary: #555555;
          --text-tertiary: #999999;
          --border: #e4e4e4;
          --border-hover: #c0c0c0;
          --accent: #2563eb;
          --accent-hover: #1d4ed8;
          --accent-light: #eff4ff;
          --accent-border: #bfdbfe;
          --error: #dc2626;
          --error-bg: #fef2f2;
          --error-border: #fecaca;
          --success: #16a34a;
          --success-bg: #f0fdf4;
          --success-border: #bbf7d0;
          --radius: 10px;
          --radius-sm: 6px;
          --font: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
          --font-mono: 'JetBrains Mono', monospace;
        }

        html { scroll-behavior: smooth; }

        body {
          background: var(--bg);
          color: var(--text);
          font-family: var(--font);
          font-size: 14px;
          font-weight: 400;
          line-height: 1.6;
          -webkit-font-smoothing: antialiased;
        }

        nav {
          position: fixed; top: 0; left: 0; right: 0; z-index: 100;
          display: flex; align-items: center; justify-content: space-between;
          padding: 16px 32px;
          background: rgba(255,255,255,0.85);
          backdrop-filter: blur(12px);
          border-bottom: 1px solid transparent;
          transition: border-color 0.3s;
        }
        nav.scrolled { border-bottom-color: var(--border); }

        .nav-logo { font-size: 22px; font-weight: 700; color: var(--text); letter-spacing: -0.03em; }

        .nav-btn {
          font-size: 13px; font-weight: 500; color: var(--bg); background: var(--text);
          border: none; padding: 8px 18px; border-radius: var(--radius-sm); cursor: pointer; transition: opacity 0.15s;
        }
        .nav-btn:hover { opacity: 0.8; }

        .hero { padding: 80px 32px 0; text-align: center; max-width: 720px; margin: 0 auto; }

        .hero-h1 { font-size: clamp(22px, 2.8vw, 28px); font-weight: 600; line-height: 1.35; letter-spacing: -0.02em; color: var(--text); margin-bottom: 10px; }

        .hero-sub { font-size: 14px; color: var(--text-secondary); line-height: 1.5; max-width: 540px; margin: 0 auto; }

        .hero-proof { display: flex; align-items: center; justify-content: center; gap: 6px; font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px; white-space: nowrap; }
        .hero-proof-sep { color: var(--border-hover); user-select: none; }

        .upload-wrapper { max-width: 640px; margin: 16px auto 0; }

        .upload-card { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px 24px; }

        .dropzone-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }

        .dropzone { border: 1.5px dashed var(--border); border-radius: var(--radius-sm); padding: 20px 12px; text-align: center; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
        .dropzone:hover { border-color: var(--border-hover); background: var(--bg-secondary); }
        .dropzone.active { border-color: var(--accent); background: var(--accent-light); }
        .dropzone.has-file { border-color: var(--accent); border-style: solid; background: var(--accent-light); }

        .dropzone-main { font-size: 14px; font-weight: 500; color: var(--text); margin-bottom: 3px; }
        .dropzone-hint { font-size: 12px; color: var(--text-tertiary); }
        .dropzone-filename { font-family: var(--font-mono); font-size: 13px; font-weight: 500; color: var(--accent); }
        .dropzone-size { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
        .dropzone-remove { font-size: 11px; color: var(--text-tertiary); background: none; border: none; cursor: pointer; font-family: var(--font); text-decoration: underline; margin-top: 6px; transition: color 0.15s; }
        .dropzone-remove:hover { color: var(--text); }

        .field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }

        .input-field { width: 100%; padding: 10px 12px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text); font-family: var(--font); font-size: 13px; outline: none; transition: border-color 0.15s; }
        .input-field::placeholder { color: var(--text-tertiary); }
        .input-field:focus { border-color: var(--accent); }

        .submit-btn { width: 100%; padding: 12px; background: var(--accent); color: white; border: none; border-radius: var(--radius-sm); font-family: var(--font); font-size: 14px; font-weight: 500; cursor: pointer; transition: background 0.15s; }
        .submit-btn:hover { background: var(--accent-hover); }
        .submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        .upload-footer { text-align: center; margin-top: 14px; font-size: 12px; color: var(--text-tertiary); display: flex; align-items: center; justify-content: center; gap: 6px; }
        .upload-footer svg { flex-shrink: 0; }

        .error-msg { font-size: 13px; color: var(--error); background: var(--error-bg); border: 1px solid var(--error-border); border-radius: var(--radius-sm); padding: 10px 14px; margin-bottom: 10px; }

        /* ── ANALYZING STATE ── */
        .analyzing-card { text-align: center; padding: 48px 20px; }
        .analyzing-spinner { width: 36px; height: 36px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .analyzing-title { font-size: 16px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
        .analyzing-sub { font-size: 13px; color: var(--text-secondary); }

        /* ── SUCCESS STATE ── */
        .success-card { text-align: center; padding: 32px 20px; }
        .success-check { width: 44px; height: 44px; border-radius: 50%; background: var(--success-bg); border: 1px solid var(--success-border); display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; color: var(--success); font-size: 20px; }
        .success-title { font-size: 18px; font-weight: 600; color: var(--text); margin-bottom: 8px; }
        .success-sub { font-size: 13px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 6px; }
        .success-email { font-weight: 500; color: var(--text); }
        .success-id { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); margin-top: 12px; }
        .reset-btn { margin-top: 20px; padding: 8px 18px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); font-family: var(--font); font-size: 13px; color: var(--text-secondary); cursor: pointer; transition: border-color 0.15s, color 0.15s; }
        .reset-btn:hover { border-color: var(--border-hover); color: var(--text); }

        .features { padding: 80px 32px; max-width: 880px; margin: 0 auto; }
        .features-header { text-align: center; margin-bottom: 48px; }
        .features-eyebrow { font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em; color: var(--accent); margin-bottom: 10px; }
        .features-h2 { font-size: clamp(22px, 3vw, 30px); font-weight: 600; color: var(--text); letter-spacing: -0.02em; }

        .features-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
        .feature-cell { background: var(--bg); padding: 28px 24px; }
        .feature-tag { font-family: var(--font-mono); font-size: 11px; font-weight: 500; color: var(--accent); margin-bottom: 10px; }
        .feature-title { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 6px; line-height: 1.3; }
        .feature-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.55; }

        .how { padding: 80px 32px; max-width: 880px; margin: 0 auto; border-top: 1px solid var(--border); }
        .how-header { text-align: center; margin-bottom: 48px; }
        .how-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 40px; }
        .how-num { font-family: var(--font-mono); font-size: 12px; font-weight: 500; color: var(--text-tertiary); margin-bottom: 12px; }
        .how-title { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 6px; }
        .how-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.55; }

        .trust { padding: 64px 32px 80px; max-width: 600px; margin: 0 auto; text-align: center; border-top: 1px solid var(--border); }
        .trust-h2 { font-size: 22px; font-weight: 600; color: var(--text); margin-bottom: 20px; letter-spacing: -0.02em; }
        .trust-points { display: flex; flex-direction: column; gap: 12px; text-align: left; max-width: 400px; margin: 0 auto 32px; }
        .trust-point { display: flex; align-items: flex-start; gap: 10px; font-size: 14px; color: var(--text-secondary); line-height: 1.5; }
        .trust-icon { flex-shrink: 0; margin-top: 3px; color: var(--success); }
        .trust-cta { display: inline-flex; font-size: 14px; font-weight: 500; color: var(--bg); background: var(--text); padding: 10px 24px; border: none; border-radius: var(--radius-sm); cursor: pointer; transition: opacity 0.15s; }
        .trust-cta:hover { opacity: 0.8; }

        footer { padding: 24px 32px; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
        .footer-logo { font-size: 15px; font-weight: 700; color: var(--text); letter-spacing: -0.03em; }
        .footer-meta { font-size: 12px; color: var(--text-tertiary); }

        @media (max-width: 700px) {
          .hero { padding: 76px 20px 0; }
          .upload-wrapper { margin-top: 16px; }
          .upload-card { padding: 16px; }
          .features-grid { grid-template-columns: 1fr; }
          .how-grid { grid-template-columns: 1fr; gap: 28px; }
          .features, .how, .trust { padding-left: 20px; padding-right: 20px; }
          nav { padding: 14px 20px; }
          footer { padding: 20px; flex-direction: column; gap: 8px; }
          .field-row { grid-template-columns: 1fr; }
          .dropzone-row { grid-template-columns: 1fr; }
          .hero-proof { white-space: normal; flex-wrap: wrap; font-size: 10px; }
        }
      `}</style>

      <nav id="main-nav">
        <span className="nav-logo">Facet</span>
        <button onClick={scrollToUpload} className="nav-btn">Analyze a part</button>
      </nav>

      <main>
        <section className="hero">
          <h1 className="hero-h1">
            Upload a STEP file.<br />
            Extract design intent, technical requirements, and DFM cost drivers — in seconds.
          </h1>
          <p className="hero-sub">
            Stop spending hours reviewing models and drawings before you can quote.
            Facet pulls the key requirements and flags major cost drivers — so you
            spend time making parts, not translating documents.
          </p>
        </section>

        <div className="upload-wrapper" ref={uploadRef}>
          <div className="hero-proof">
            <span>Setups</span>
            <span className="hero-proof-sep">·</span>
            <span>Holes + L/D</span>
            <span className="hero-proof-sep">·</span>
            <span>Thin walls</span>
            <span className="hero-proof-sep">·</span>
            <span>Tooling</span>
            <span className="hero-proof-sep">·</span>
            <span>DFM flags</span>
            <span className="hero-proof-sep">·</span>
            <span>Material removal</span>
          </div>
          <div className="upload-card">

            {/* ── ANALYZING STATE: spinner while model runs ── */}
            {uploadState === "analyzing" ? (
              <div className="analyzing-card">
                <div className="analyzing-spinner" />
                <div className="analyzing-title">Analyzing your part...</div>
                <div className="analyzing-sub">This typically takes 15–30 seconds.</div>
              </div>

            /* ── FORM: default upload state ── */
            ) : uploadState === "idle" || uploadState === "submitting" || uploadState === "error" ? (
              <>
                {errorMsg && <div className="error-msg">{errorMsg}</div>}

                <div className="dropzone-row">
                  <div
                    className={`dropzone ${stepDrag ? "active" : ""} ${stepFile ? "has-file" : ""}`}
                    onClick={() => stepInputRef.current?.click()}
                    onDragOver={(e) => { prevent(e); setStepDrag(true); }}
                    onDragLeave={() => setStepDrag(false)}
                    onDrop={onDrop((f) => setStepFile(f), ["step", "stp"])}
                  >
                    <input ref={stepInputRef} type="file" accept=".step,.stp" style={{ display: "none" }}
                      onChange={(e) => setStepFile(e.target.files?.[0] || null)} />
                    {stepFile ? (
                      <>
                        <div className="dropzone-filename">{stepFile.name}</div>
                        <div className="dropzone-size">{formatBytes(stepFile.size)}</div>
                        <button className="dropzone-remove"
                          onClick={(e) => { e.stopPropagation(); setStepFile(null); }}>Remove</button>
                      </>
                    ) : (
                      <>
                        <div className="dropzone-main">STEP file</div>
                        <div className="dropzone-hint">.step or .stp — required</div>
                      </>
                    )}
                  </div>

                  <div
                    className={`dropzone ${drawingDrag ? "active" : ""} ${drawingFile ? "has-file" : ""}`}
                    onClick={() => drawingInputRef.current?.click()}
                    onDragOver={(e) => { prevent(e); setDrawingDrag(true); }}
                    onDragLeave={() => setDrawingDrag(false)}
                    onDrop={onDrop((f) => setDrawingFile(f), ["pdf"])}
                  >
                    <input ref={drawingInputRef} type="file" accept=".pdf" style={{ display: "none" }}
                      onChange={(e) => setDrawingFile(e.target.files?.[0] || null)} />
                    {drawingFile ? (
                      <>
                        <div className="dropzone-filename">{drawingFile.name}</div>
                        <div className="dropzone-size">{formatBytes(drawingFile.size)}</div>
                        <button className="dropzone-remove"
                          onClick={(e) => { e.stopPropagation(); setDrawingFile(null); }}>Remove</button>
                      </>
                    ) : (
                      <>
                        <div className="dropzone-main">Engineering drawing</div>
                        <div className="dropzone-hint">PDF — optional</div>
                      </>
                    )}
                  </div>
                </div>

                <div className="field-row">
                  <input type="email" className="input-field" placeholder="Email"
                    value={email} onChange={(e) => setEmail(e.target.value)} />
                  <input type="tel" className="input-field" placeholder="Phone (optional)"
                    value={phone} onChange={(e) => setPhone(e.target.value)} />
                </div>

                <button className="submit-btn" onClick={handleSubmit}
                  disabled={uploadState === "submitting"}>
                  {uploadState === "submitting" ? "Uploading..." : "Analyze part"}
                </button>
              </>
            ) : null}

          </div>
          <div className="upload-footer">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
              <path d="M8 1a4.5 4.5 0 00-4.5 4.5V7H3a1 1 0 00-1 1v6a1 1 0 001 1h10a1 1 0 001-1V8a1 1 0 00-1-1h-.5V5.5A4.5 4.5 0 008 1zm-2.5 4.5a2.5 2.5 0 015 0V7h-5V5.5z" fill="currentColor"/>
            </svg>
            Files stored under a unique ID. Never shared without your permission.
          </div>
        </div>

        <section className="features">
          <div className="features-header">
            <div className="features-eyebrow">What you get</div>
            <h2 className="features-h2">Everything to evaluate a part before you quote</h2>
          </div>
          <div className="features-grid">
            <div className="feature-cell">
              <div className="feature-tag">SETUPS</div>
              <div className="feature-title">3-axis vs 5-axis</div>
              <div className="feature-desc">Number of fixturings, approach axis per setup, and machine classification.</div>
            </div>
            <div className="feature-cell">
              <div className="feature-tag">HOLES</div>
              <div className="feature-title">Full hole inventory</div>
              <div className="feature-desc">Through, blind, counterbore, countersink — with diameter, depth, and L/D ratios flagged.</div>
            </div>
            <div className="feature-cell">
              <div className="feature-tag">THIN WALLS</div>
              <div className="feature-title">Thickness + severity</div>
              <div className="feature-desc">Geometry-based and hole proximity detection. Critical, warning, advisory ratings.</div>
            </div>
            <div className="feature-cell">
              <div className="feature-tag">VOLUME</div>
              <div className="feature-title">Material removal %</div>
              <div className="feature-desc">Bounding box vs solid volume — see how much stock you&apos;re cutting before you quote.</div>
            </div>
            <div className="feature-cell">
              <div className="feature-tag">TOOLING</div>
              <div className="feature-title">Min tool dia + changes</div>
              <div className="feature-desc">Per-fixturing cutter constraints and estimated tool swaps from hole sizes and fillets.</div>
            </div>
            <div className="feature-cell">
              <div className="feature-tag">DFM FLAGS</div>
              <div className="feature-title">Issues — ranked</div>
              <div className="feature-desc">Deep pockets, small radii, tight access, special tooling — flagged with severity and detail.</div>
            </div>
          </div>
        </section>

        <section className="how">
          <div className="how-header">
            <div className="features-eyebrow">How it works</div>
            <h2 className="features-h2">Three steps</h2>
          </div>
          <div className="how-grid">
            <div>
              <div className="how-num">01</div>
              <div className="how-title">Upload your STEP file</div>
              <div className="how-desc">Drop in the file. Optionally add an engineering drawing for tolerance context.</div>
            </div>
            <div>
              <div className="how-num">02</div>
              <div className="how-title">We analyze the geometry</div>
              <div className="how-desc">Features, setups, tooling, and manufacturability issues — extracted automatically.</div>
            </div>
            <div>
              <div className="how-num">03</div>
              <div className="how-title">You get the breakdown</div>
              <div className="how-desc">Everything you need to decide if a job is worth taking and what to charge.</div>
            </div>
          </div>
        </section>

        <section className="trust">
          <h2 className="trust-h2">Your files. Your control.</h2>
          <div className="trust-points">
            <div className="trust-point">
              <span className="trust-icon"><svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 8l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"/></svg></span>
              Stored under a unique identifier — no public exposure
            </div>
            <div className="trust-point">
              <span className="trust-icon"><svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 8l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"/></svg></span>
              Never shared without your explicit permission
            </div>
            <div className="trust-point">
              <span className="trust-icon"><svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 8l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5"/></svg></span>
              No account required — upload, get your analysis, done
            </div>
          </div>
          <button onClick={scrollToUpload} className="trust-cta">Upload a part</button>
        </section>
      </main>

      <footer>
        <span className="footer-logo">Facet</span>
        <span className="footer-meta">© 2026 Facet</span>
      </footer>

      <script dangerouslySetInnerHTML={{ __html: `
        const nav = document.getElementById('main-nav');
        window.addEventListener('scroll', () => {
          nav.classList.toggle('scrolled', window.scrollY > 40);
        }, { passive: true });
      ` }} />
    </>
  );
}
