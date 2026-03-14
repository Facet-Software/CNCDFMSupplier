# sourcing/reporting/html_report.py
# Generates a self-contained single-page HTML report for suppliers.
# No build step — uses React + Babel Standalone from CDN.

import json
import pathlib


_COMPONENT_JSX = r"""
const R = window.__REPORT__;

const HOLE_LABELS = {
  through:             "Through",
  through_counterbore: "Counterbore",
  through_countersink: "Countersink",
  blind_flat:          "Blind (flat)",
  blind_with_tip:      "Blind (drill tip)",
};

const SEV_COLOR  = { critical: "#c0392b", warning: "#d97706", advisory: "#6b7280" };
const SEV_BG     = { critical: "#fef2f2", warning: "#fffbeb", advisory: "#f9fafb" };
const SEV_BORDER = { critical: "#fca5a5", warning: "#fcd34d", advisory: "#e5e7eb" };
const SEV_LABEL  = { critical: "CRITICAL", warning: "WARNING", advisory: "ADVISORY" };

function SectionHead({ children }) {
  return (
    <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: "#6b7280", marginBottom: 8 }}>{children}</div>
  );
}

function App() {
  const crits = R.dfm.filter(d => d.severity === "critical").length;
  const warns = R.dfm.filter(d => d.severity === "warning").length;
  const advs  = R.dfm.filter(d => d.severity === "advisory").length;
  const totalFlags = crits + warns + advs;
  const flagColor = crits > 0 ? SEV_COLOR.critical : warns > 0 ? SEV_COLOR.warning : "#16a34a";

  return (
    <div style={{ background: "#f8f7f4", minHeight: "100vh", fontFamily: "'IBM Plex Sans', system-ui, sans-serif", color: "#1a1a1a" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        @media print { body { background: white; } }
      `}</style>

      <div style={{ maxWidth: 860, margin: "0 auto", padding: "40px 40px 60px" }}>

        {/* HEADER */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 32, paddingBottom: 24, borderBottom: "2px solid #1a1a1a" }}>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.18em", color: "#6b7280", marginBottom: 6, textTransform: "uppercase" }}>
              Sourcing AI — Part Analysis Report
            </div>
            <div style={{ fontSize: 24, fontWeight: 600, color: "#1a1a1a", letterSpacing: "-0.01em", marginBottom: 4 }}>
              {R.filename}
            </div>
            <div style={{ fontSize: 12, color: "#9ca3af" }}>
              {new Date(R.analyzed_at).toLocaleString("en-US", { dateStyle: "long", timeStyle: "short" })}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.14em", color: "#9ca3af", marginBottom: 5, textTransform: "uppercase" }}>Machine Type</div>
            <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 18, fontWeight: 500, color: "#1a1a1a" }}>
              {R.machine_classification.replace(/-/g, " ")}
            </div>
          </div>
        </div>

        {/* STAT STRIP */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 1, marginBottom: 36, background: "#e5e3df", borderRadius: 6, overflow: "hidden" }}>
          {[
            { label: "Setups Required",  value: R.fixturing_count,   sub: "fixturings" },
            { label: "Bounding Box",     value: `${R.bounding_box.x} × ${R.bounding_box.y} × ${R.bounding_box.z}`, sub: "mm  X · Y · Z" },
            { label: "Planar Faces",     value: R.planar_faces,      sub: "flat surfaces" },
            { label: "Holes",            value: R.holes.length,      sub: `${R.holes.filter(h=>h.type.startsWith("blind")).length} blind · ${R.holes.filter(h=>h.type.startsWith("through")).length} through` },
            { label: "DFM Flags",        value: totalFlags,          sub: totalFlags === 0 ? "no issues" : `${crits} crit · ${warns} warn · ${advs} adv`, accent: flagColor },
          ].map(({ label, value, sub, accent }) => (
            <div key={label} style={{ background: "#fff", padding: "16px 18px" }}>
              <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.14em", color: "#9ca3af", textTransform: "uppercase", marginBottom: 6 }}>{label}</div>
              <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 15, fontWeight: 500, color: accent || "#1a1a1a", lineHeight: 1.2, marginBottom: 4 }}>{value}</div>
              <div style={{ fontSize: 10, color: "#9ca3af" }}>{sub}</div>
            </div>
          ))}
        </div>

        {/* TWO COLUMN */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 28 }}>

          {/* SETUPS */}
          <div>
            <SectionHead>Setup Summary</SectionHead>
            <div style={{ background: "#fff", border: "1px solid #e5e3df", borderRadius: 6, overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: "44px 1fr 52px 52px 52px", padding: "7px 14px", background: "#f8f7f4", borderBottom: "1px solid #e5e3df" }}>
                {["Axis", "Features", "Holes", "Faces", "Flags"].map((h, i) => (
                  <div key={h} style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.12em", color: "#9ca3af", textTransform: "uppercase", textAlign: i > 1 ? "right" : "left" }}>{h}</div>
                ))}
              </div>
              {R.fixturings.map((f, i) => {
                const tc = f.concerns.critical + f.concerns.warning + f.concerns.advisory;
                const fc = f.concerns.critical > 0 ? SEV_COLOR.critical : f.concerns.warning > 0 ? SEV_COLOR.warning : f.concerns.advisory > 0 ? SEV_COLOR.advisory : "#9ca3af";
                return (
                  <div key={f.id} style={{ display: "grid", gridTemplateColumns: "44px 1fr 52px 52px 52px", padding: "11px 14px", borderBottom: i < R.fixturings.length - 1 ? "1px solid #f0ede9" : "none", alignItems: "center" }}>
                    <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 14, fontWeight: 500, color: "#1a1a1a" }}>{f.label}</div>
                    <div style={{ fontSize: 11, color: "#6b7280" }}>
                      {[
                        f.planar > 0 && `${f.planar} planar`,
                        f.fillets > 0 && `${f.fillets} fillet${f.fillets > 1 ? "s" : ""}`,
                        f.min_tool_dia && `min ⌀${f.min_tool_dia}mm`,
                        `~${f.tool_changes} tool chg`,
                      ].filter(Boolean).join(" · ")}
                    </div>
                    <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 13, color: "#1a1a1a", textAlign: "right" }}>{f.holes}</div>
                    <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 13, color: "#1a1a1a", textAlign: "right" }}>{f.planar}</div>
                    <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 13, fontWeight: tc > 0 ? 600 : 400, color: fc, textAlign: "right" }}>{tc || "—"}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* HOLES */}
          <div>
            <SectionHead>Hole Inventory</SectionHead>
            <div style={{ background: "#fff", border: "1px solid #e5e3df", borderRadius: 6, overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 64px 68px 48px", padding: "7px 14px", background: "#f8f7f4", borderBottom: "1px solid #e5e3df" }}>
                {["Type", "⌀ (mm)", "Depth", "L/D"].map((h, i) => (
                  <div key={h} style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.12em", color: "#9ca3af", textTransform: "uppercase", textAlign: i > 0 ? "right" : "left" }}>{h}</div>
                ))}
              </div>
              {R.holes.length === 0
                ? <div style={{ padding: "14px", fontSize: 12, color: "#9ca3af" }}>No holes detected</div>
                : R.holes.map((h, i) => {
                  const ldColor = !h.ld ? "#9ca3af" : h.ld >= 6 ? SEV_COLOR.critical : h.ld >= 4 ? SEV_COLOR.warning : "#374151";
                  const isBlind = h.type.startsWith("blind");
                  return (
                    <div key={h.id} style={{ display: "grid", gridTemplateColumns: "1fr 64px 68px 48px", padding: "10px 14px", borderBottom: i < R.holes.length - 1 ? "1px solid #f0ede9" : "none", alignItems: "center" }}>
                      <div>
                        <span style={{ fontSize: 11, fontWeight: 500, color: isBlind ? "#92400e" : "#14532d", background: isBlind ? "#fef3c7" : "#f0fdf4", padding: "2px 7px", borderRadius: 3 }}>
                          {HOLE_LABELS[h.type] || h.type}
                        </span>
                        {h.cone_angle && <span style={{ fontSize: 10, color: "#9ca3af", marginLeft: 6 }}>{h.cone_angle}°</span>}
                      </div>
                      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, color: "#374151", textAlign: "right" }}>{(h.radius_mm * 2).toFixed(2)}</div>
                      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, color: "#374151", textAlign: "right" }}>{h.depth_mm.toFixed(1)} mm</div>
                      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, color: ldColor, textAlign: "right", fontWeight: h.ld >= 4 ? 600 : 400 }}>{h.ld ? `${h.ld}:1` : "—"}</div>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>

        {/* DFM FLAGS */}
        {totalFlags > 0 && (
          <div>
            <SectionHead>Manufacturing Flags</SectionHead>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {R.dfm.map((d, i) => (
                <div key={i} style={{
                  display: "grid", gridTemplateColumns: "88px 80px 1fr",
                  gap: 12, alignItems: "start",
                  background: SEV_BG[d.severity],
                  border: `1px solid ${SEV_BORDER[d.severity]}`,
                  borderLeft: `3px solid ${SEV_COLOR[d.severity]}`,
                  borderRadius: 5, padding: "10px 14px",
                }}>
                  <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", color: SEV_COLOR[d.severity], paddingTop: 1, textTransform: "uppercase" }}>{SEV_LABEL[d.severity]}</div>
                  <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "#6b7280", paddingTop: 1 }}>Fix. {d.fixturing}</div>
                  <div style={{ fontSize: 12, color: "#374151", lineHeight: 1.55 }}>{d.message}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {totalFlags === 0 && (
          <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "14px 18px", display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#16a34a", flexShrink: 0 }} />
            <div style={{ fontSize: 13, color: "#15803d", fontWeight: 500 }}>No manufacturing flags — part appears suitable for standard CNC machining.</div>
          </div>
        )}

        {/* FOOTER */}
        <div style={{ marginTop: 40, paddingTop: 16, borderTop: "1px solid #e5e3df", display: "flex", justifyContent: "space-between" }}>
          <div style={{ fontSize: 10, color: "#d1cdc7" }}>Generated by Sourcing AI · Rule-based geometric analysis · Not a substitute for engineering review</div>
          <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "#d1cdc7" }}>{R.filename}</div>
        </div>

      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
"""


def generate_report_html(report_dict, output_path=None):
    """
    Write a self-contained single-page HTML report for suppliers.

    Parameters
    ----------
    report_dict : dict
        Output of to_report_dict() from sourcing.pipeline.
    output_path : str or None
        Path to write the HTML file. If None, writes next to the STEP file
        as <stem>_report.html. If a directory, writes inside it.

    Returns
    -------
    str — absolute path of the written HTML file.
    """
    stem = pathlib.Path(report_dict["filename"]).stem

    if output_path is None:
        out = pathlib.Path(report_dict["filename"]).with_name(f"{stem}_report.html")
    else:
        out = pathlib.Path(output_path)
        if out.is_dir():
            out = out / f"{stem}_report.html"

    report_json = json.dumps(report_dict, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{report_dict['filename']} — Part Report</title>
  <script crossorigin src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
  <script crossorigin src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.2/babel.min.js"></script>
</head>
<body style="margin:0;background:#f8f7f4">
  <div id="root"></div>
  <script>window.__REPORT__ = {report_json};</script>
  <script type="text/babel">{_COMPONENT_JSX}</script>
</body>
</html>"""

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return str(out.resolve())