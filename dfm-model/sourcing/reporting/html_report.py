# sourcing/reporting/html_report.py
# Generates a self-contained single-page HTML report for suppliers.
# Includes a Three.js 3D viewer that highlights faces when DFM flags / holes
# are clicked. No build step — React + Babel + Three.js loaded from CDN.

import json
import pathlib


_COMPONENT_JSX = r"""
const R = window.__REPORT__;
const HAS_GEO = R.geometry && R.geometry.length > 0;

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

// ── 3D VIEWER ─────────────────────────────────────────────────────────────────
function Viewer3D({ selectedFaceIdxs, labelText, labelSev, activeFixture, snapRef, captureRef }) {
  const containerRef = React.useRef(null);
  const threeRef     = React.useRef({});
  const svgLineRef   = React.useRef(null);
  const svgDotRef    = React.useRef(null);
  const selectedRef  = React.useRef([]);
  const arrowRef     = React.useRef(null);
  const edgesRef     = React.useRef([]);    // LineSegments for fixturing edges
  const snapTargetRef = React.useRef(null); // {theta, phi} to animate to

  // ── INIT ──
  React.useEffect(() => {
    if (!containerRef.current || !HAS_GEO) return;
    const el = containerRef.current;

    const scene    = new THREE.Scene();
    scene.background = new THREE.Color(0xf0eeeb);
    const camera   = new THREE.PerspectiveCamera(45, el.clientWidth / el.clientHeight, 0.01, 100000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(el.clientWidth, el.clientHeight);
    el.appendChild(renderer.domElement);

    // Lights
    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const sun = new THREE.DirectionalLight(0xfff8f0, 0.85);
    sun.position.set(1, 2, 1.5); scene.add(sun);
    const fill = new THREE.DirectionalLight(0xe0eeff, 0.25);
    fill.position.set(-1, -0.5, -1); scene.add(fill);

    // Per-face meshes
    const faceMeshes = {};
    const MAT_DEFAULT   = () => new THREE.MeshPhongMaterial({ color: 0xd0cbc3, specular: 0x222222, shininess: 18, side: THREE.DoubleSide });
    const MAT_HIGHLIGHT = () => new THREE.MeshPhongMaterial({ color: 0xf97316, specular: 0x441100, shininess: 30, emissive: new THREE.Color(0x1a0500), side: THREE.DoubleSide });
    const MAT_DIM       = () => new THREE.MeshPhongMaterial({ color: 0xe0dbd4, specular: 0x111111, shininess: 5, side: THREE.DoubleSide, transparent: true, opacity: 0.35 });
    const MAT_FIXTURE   = () => new THREE.MeshPhongMaterial({ color: 0xc7d8f5, specular: 0x1133aa, shininess: 22, side: THREE.DoubleSide });

    let bbox = new THREE.Box3();
    R.geometry.forEach(fd => {
      try {
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(fd.v), 3));
        geo.setIndex(fd.t);
        geo.computeVertexNormals();
        const mesh = new THREE.Mesh(geo, MAT_DEFAULT());
        mesh.userData.faceIdx = fd.i;
        faceMeshes[fd.i] = mesh;
        scene.add(mesh);
        bbox.expandByObject(mesh);
      } catch(e) {}
    });

    const center = new THREE.Vector3(); bbox.getCenter(center);
    const size   = new THREE.Vector3(); bbox.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);

    const orbit = {
      theta: Math.PI * 0.35, phi: Math.PI * 0.30,
      radius: maxDim * 1.8, target: center.clone(),
      isDragging: false, isPanning: false, lastX: 0, lastY: 0,
    };

    function updateCamera() {
      const { theta, phi, radius, target } = orbit;
      camera.position.set(
        target.x + radius * Math.sin(phi) * Math.cos(theta),
        target.y + radius * Math.cos(phi),
        target.z + radius * Math.sin(phi) * Math.sin(theta),
      );
      camera.lookAt(target);
    }
    updateCamera();

    // Controls
    const canvas = renderer.domElement;
    const onDown  = (e) => { if (e.button === 2 || e.ctrlKey) orbit.isPanning = true; else orbit.isDragging = true; orbit.lastX = e.clientX; orbit.lastY = e.clientY; e.preventDefault(); };
    const onMove  = (e) => {
      const dx = e.clientX - orbit.lastX, dy = e.clientY - orbit.lastY;
      orbit.lastX = e.clientX; orbit.lastY = e.clientY;
      if (orbit.isDragging) {
        orbit.theta -= dx * 0.008;
        orbit.phi = Math.max(0.05, Math.min(Math.PI - 0.05, orbit.phi + dy * 0.008));
        updateCamera();
      } else if (orbit.isPanning) {
        const right = new THREE.Vector3().crossVectors(camera.getWorldDirection(new THREE.Vector3()), camera.up).normalize();
        const up    = camera.up.clone().normalize();
        const s = orbit.radius * 0.001;
        orbit.target.addScaledVector(right, -dx * s).addScaledVector(up, dy * s);
        updateCamera();
      }
    };
    const onUp    = () => { orbit.isDragging = false; orbit.isPanning = false; };
    const onWheel = (e) => {
      orbit.radius = Math.max(maxDim * 0.1, Math.min(maxDim * 10, orbit.radius * (1 + e.deltaY * 0.001)));
      updateCamera(); e.preventDefault();
    };
    canvas.addEventListener('mousedown', onDown);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    canvas.addEventListener('contextmenu', e => e.preventDefault());

    // Touch
    let ltd = 0;
    canvas.addEventListener('touchstart', e => {
      if (e.touches.length === 1) { orbit.isDragging = true; orbit.lastX = e.touches[0].clientX; orbit.lastY = e.touches[0].clientY; }
      if (e.touches.length === 2) ltd = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
      e.preventDefault();
    }, { passive: false });
    canvas.addEventListener('touchmove', e => {
      if (e.touches.length === 1) {
        const dx = e.touches[0].clientX - orbit.lastX, dy = e.touches[0].clientY - orbit.lastY;
        orbit.lastX = e.touches[0].clientX; orbit.lastY = e.touches[0].clientY;
        orbit.theta -= dx * 0.008;
        orbit.phi = Math.max(0.05, Math.min(Math.PI - 0.05, orbit.phi + dy * 0.008));
        updateCamera();
      }
      if (e.touches.length === 2) {
        const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY);
        orbit.radius = Math.max(maxDim * 0.1, Math.min(maxDim * 10, orbit.radius * ltd / d));
        ltd = d; updateCamera();
      }
      e.preventDefault();
    }, { passive: false });
    canvas.addEventListener('touchend', () => { orbit.isDragging = false; });

    // Resize
    const ro = new ResizeObserver(() => {
      camera.aspect = el.clientWidth / el.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(el.clientWidth, el.clientHeight);
    });
    ro.observe(el);

    // Render loop
    let animId;
    function animate() {
      animId = requestAnimationFrame(animate);

      // Smooth snap animation
      if (snapTargetRef.current) {
        const t = snapTargetRef.current;
        orbit.theta += (t.theta - orbit.theta) * 0.12;
        orbit.phi   += (t.phi   - orbit.phi)   * 0.12;
        if (Math.abs(t.theta - orbit.theta) < 0.001 && Math.abs(t.phi - orbit.phi) < 0.001) {
          orbit.theta = t.theta; orbit.phi = t.phi;
          snapTargetRef.current = null;
        }
        updateCamera();
      }

      renderer.render(scene, camera);

      // SVG leader line
      const idxs = selectedRef.current;
      if (idxs.length > 0 && svgLineRef.current && svgDotRef.current) {
        let cx = 0, cy = 0, cz = 0, n = 0;
        idxs.forEach(idx => {
          const fd = R.geometry.find(f => f.i === idx);
          if (!fd) return;
          for (let i = 0; i < fd.v.length; i += 3) { cx += fd.v[i]; cy += fd.v[i+1]; cz += fd.v[i+2]; n++; }
        });
        if (n > 0) {
          const sp = new THREE.Vector3(cx/n, cy/n, cz/n).project(camera);
          const rect = canvas.getBoundingClientRect();
          const px = (sp.x * 0.5 + 0.5) * rect.width;
          const py = (-sp.y * 0.5 + 0.5) * rect.height;
          svgLineRef.current.setAttribute('x1', 18); svgLineRef.current.setAttribute('y1', 18);
          svgLineRef.current.setAttribute('x2', px);  svgLineRef.current.setAttribute('y2', py);
          svgDotRef.current.setAttribute('cx', px);   svgDotRef.current.setAttribute('cy', py);
          svgLineRef.current.style.display = ''; svgDotRef.current.style.display = '';
        }
      } else {
        if (svgLineRef.current) svgLineRef.current.style.display = 'none';
        if (svgDotRef.current)  svgDotRef.current.style.display  = 'none';
      }
    }
    animate();

    threeRef.current = { renderer, scene, camera, faceMeshes, MAT_DEFAULT, MAT_HIGHLIGHT, MAT_DIM, MAT_FIXTURE, center, maxDim, orbit, updateCamera };

    // Expose snap function
    if (snapRef) snapRef.current = (approachVec) => {
      const [ax, ay, az] = approachVec;
      const phi   = Math.acos(Math.max(-1, Math.min(1, ay / Math.sqrt(ax*ax+ay*ay+az*az))));
      const theta = Math.atan2(az, ax);
      snapTargetRef.current = { theta, phi };
    };

    // Expose isometric capture function for PDF export
    if (captureRef) captureRef.current = () => {
      const savedTheta = orbit.theta, savedPhi = orbit.phi, savedRadius = orbit.radius;
      // True isometric: camera at equal X, Y, Z distance → phi = acos(1/√3) ≈ 54.74°
      orbit.theta  = -Math.PI * 0.75;
      orbit.phi    = Math.acos(1 / Math.sqrt(3));
      orbit.radius = maxDim * 2.2;
      updateCamera();
      renderer.render(scene, camera);
      const dataURL = renderer.domElement.toDataURL('image/png');
      orbit.theta = savedTheta; orbit.phi = savedPhi; orbit.radius = savedRadius;
      updateCamera();
      return dataURL;
    };

    return () => {
      cancelAnimationFrame(animId);
      ro.disconnect();
      canvas.removeEventListener('mousedown', onDown);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      canvas.removeEventListener('wheel', onWheel);
      if (el.contains(canvas)) el.removeChild(canvas);
      renderer.dispose();
    };
  }, []);

  // ── FACE HIGHLIGHT UPDATE ──
  React.useEffect(() => {
    const t = threeRef.current;
    if (!t.faceMeshes) return;
    selectedRef.current = selectedFaceIdxs;
    const hasSelection = selectedFaceIdxs.length > 0;
    const selSet = new Set(selectedFaceIdxs);
    // Determine fixture face set (for coloring when no dfm selection)
    const fixSet = new Set(activeFixture ? activeFixture.face_idxs : []);

    Object.entries(t.faceMeshes).forEach(([idxStr, mesh]) => {
      const idx = parseInt(idxStr);
      if (hasSelection) {
        if (selSet.has(idx))       mesh.material = t.MAT_HIGHLIGHT();
        else if (fixSet.has(idx))  mesh.material = t.MAT_FIXTURE();
        else                       mesh.material = t.MAT_DIM();
      } else if (activeFixture) {
        if (fixSet.has(idx))  mesh.material = t.MAT_FIXTURE();
        else                  mesh.material = t.MAT_DIM();
      } else {
        mesh.material = t.MAT_DEFAULT();
      }
    });
  }, [selectedFaceIdxs, activeFixture]);

  // ── FIXTURE ARROW + EDGE WIREFRAME ──
  React.useEffect(() => {
    const t = threeRef.current;
    if (!t.scene) return;

    // Remove previous arrow
    if (arrowRef.current) { t.scene.remove(arrowRef.current); arrowRef.current = null; }
    // Remove previous edge overlays
    edgesRef.current.forEach(l => t.scene.remove(l));
    edgesRef.current = [];

    if (!activeFixture) return;

    const { center, maxDim } = t;
    const [ax, ay, az] = activeFixture.approach_vector;
    const mag = Math.sqrt(ax*ax + ay*ay + az*az) || 1;
    const dir = new THREE.Vector3(ax/mag, ay/mag, az/mag);

    // Arrow — positioned outside the part on the approach side, pointing toward part
    const arrowLen  = maxDim * 0.45;
    const arrowFrom = center.clone().addScaledVector(dir, maxDim * 1.05);
    const arrowDir  = dir.clone().negate();  // arrow points FROM outside TOWARD part
    const arrow = new THREE.ArrowHelper(arrowDir, arrowFrom, arrowLen, 0x2563eb, arrowLen * 0.28, arrowLen * 0.18);
    // Make shaft and head thicker for visibility
    arrow.line.material.linewidth = 3;
    t.scene.add(arrow);
    arrowRef.current = arrow;

    // Edge wireframes for every face in this fixturing
    const fixSet = new Set(activeFixture.face_idxs);
    R.geometry.forEach(fd => {
      if (!fixSet.has(fd.i)) return;
      try {
        const geo  = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(fd.v), 3));
        geo.setIndex(fd.t);
        const edgeGeo = new THREE.EdgesGeometry(geo, 15);  // crease angle 15°
        const mat = new THREE.LineBasicMaterial({ color: 0x1d4ed8, linewidth: 2 });
        const lines = new THREE.LineSegments(edgeGeo, mat);
        t.scene.add(lines);
        edgesRef.current.push(lines);
      } catch(e) {}
    });
  }, [activeFixture]);

  const dotColor = SEV_COLOR[labelSev] || "#374151";

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", background: "#f0eeeb" }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", overflow: "visible" }}>
        <line ref={svgLineRef} stroke="#9ca3af" strokeWidth="1.5" strokeDasharray="5,3" display="none" />
        <circle ref={svgDotRef} r="5" fill={dotColor} stroke="#fff" strokeWidth="1.5" display="none" />
      </svg>

      {labelText && selectedFaceIdxs.length > 0 && (
        <div style={{
          position: "absolute", top: 10, left: 10,
          background: "#fff", border: `1.5px solid ${SEV_BORDER[labelSev] || "#e5e7eb"}`,
          borderLeft: `3px solid ${SEV_COLOR[labelSev] || "#374151"}`,
          borderRadius: 5, padding: "8px 12px",
          maxWidth: 260, boxShadow: "0 2px 8px rgba(0,0,0,0.12)", pointerEvents: "none",
        }}>
          <div style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.12em", color: SEV_COLOR[labelSev], textTransform: "uppercase", marginBottom: 3 }}>{SEV_LABEL[labelSev] || "INFO"}</div>
          <div style={{ fontSize: 11, color: "#374151", lineHeight: 1.5, fontFamily: "'IBM Plex Sans', sans-serif" }}>{labelText}</div>
        </div>
      )}

      {activeFixture && !labelText && (
        <div style={{ position: "absolute", top: 10, left: 10, background: "rgba(37,99,235,0.08)", border: "1px solid rgba(37,99,235,0.25)", borderLeft: "3px solid #2563eb", borderRadius: 5, padding: "7px 12px", pointerEvents: "none" }}>
          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", color: "#2563eb", textTransform: "uppercase", marginBottom: 2 }}>FIXTURING {activeFixture.label}</div>
          <div style={{ fontSize: 10, color: "#374151" }}>{activeFixture.face_idxs.length} surfaces assigned · approach {activeFixture.label}</div>
        </div>
      )}

      {!HAS_GEO && (
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 11, color: "#9ca3af", fontFamily: "'IBM Plex Mono', monospace" }}>NO GEOMETRY</div>
          <div style={{ fontSize: 10, color: "#d1cdc7" }}>STEP tessellation unavailable</div>
        </div>
      )}
    </div>
  );
}

// ── MAIN APP ──────────────────────────────────────────────────────────────────
function App() {
  const crits = R.dfm.filter(d => d.severity === "critical").length;
  const warns = R.dfm.filter(d => d.severity === "warning").length;
  const advs  = R.dfm.filter(d => d.severity === "advisory").length;
  const totalFlags = crits + warns + advs;
  const flagColor = crits > 0 ? SEV_COLOR.critical : warns > 0 ? SEV_COLOR.warning : "#16a34a";

  const [selectedFaceIdxs, setSelectedFaceIdxs] = React.useState([]);
  const [labelText, setLabelText] = React.useState("");
  const [labelSev,  setLabelSev]  = React.useState("advisory");
  const [activeFixture, setActiveFixture] = React.useState(null);
  const snapRef    = React.useRef(null);
  const captureRef = React.useRef(null);
  const [pdfBusy, setPdfBusy] = React.useState(false);

  async function buildPDF() {
    if (pdfBusy) return;
    setPdfBusy(true);
    try {
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait' });
      const PW = 210, PH = 297, ML = 15, MR = 15, MT = 15;
      const CW = PW - ML - MR;  // 180mm

      let y = MT;

      // ── HEADER ──────────────────────────────────────────────────────────────
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(7);
      doc.setTextColor(107, 114, 128);
      doc.text('FACET — PART ANALYSIS REPORT', ML, y + 5);

      doc.setFont('helvetica', 'normal');
      doc.setFontSize(6);
      doc.text('MACHINE TYPE', PW - MR, y + 3, { align: 'right' });
      doc.setFont('courier', 'bold');
      doc.setFontSize(10);
      doc.setTextColor(26, 26, 26);
      doc.text(R.machine_classification.replace(/-/g, ' '), PW - MR, y + 9, { align: 'right' });

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(16);
      doc.setTextColor(26, 26, 26);
      doc.text(R.filename, ML, y + 15);

      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8);
      doc.setTextColor(156, 163, 175);
      doc.text(new Date(R.analyzed_at).toLocaleString('en-US', { dateStyle: 'long', timeStyle: 'short' }), ML, y + 21);

      y += 26;
      doc.setDrawColor(26, 26, 26);
      doc.setLineWidth(0.5);
      doc.line(ML, y, PW - MR, y);
      y += 7;

      // ── ISOMETRIC PART IMAGE ─────────────────────────────────────────────────
      if (HAS_GEO && captureRef.current) {
        const imgData = captureRef.current();
        const imgH = 78;
        doc.addImage(imgData, 'PNG', ML, y, CW, imgH, undefined, 'FAST');
        // Border around image
        doc.setDrawColor(229, 227, 223);
        doc.setLineWidth(0.3);
        doc.rect(ML, y, CW, imgH);
        y += imgH + 7;
      }

      // ── STAT STRIP ───────────────────────────────────────────────────────────
      const statCells = [
        { label: 'SETUPS REQUIRED', value: String(R.fixturing_count), sub: 'fixturings' },
        { label: 'BOUNDING BOX',    value: `${R.bounding_box.x} × ${R.bounding_box.y} × ${R.bounding_box.z}`, sub: `${R.unit_label}  X · Y · Z` },
        { label: 'HOLES',           value: String(R.holes.length), sub: `${R.holes.filter(h=>h.type.startsWith('blind')).length} blind · ${R.holes.filter(h=>h.type.startsWith('through')).length} through` },
        { label: 'PLANAR FACES',    value: String(R.planar_faces), sub: 'flat surfaces' },
        { label: 'MATERIAL REMOVED',value: `${R.material_removal_pct}%`, sub: R.display_unit === 'inch' ? `${(R.machined_volume_mm3/16387.1).toFixed(3)} in³ of ${(R.bbox_volume_mm3/16387.1).toFixed(3)} in³` : `${(R.machined_volume_mm3/1000).toFixed(1)} cm³ of ${(R.bbox_volume_mm3/1000).toFixed(1)} cm³`, accent: R.material_removal_pct > 70 ? [217,119,6] : [26,26,26] },
        { label: 'DFM FLAGS',        value: String(totalFlags), sub: totalFlags === 0 ? 'no issues' : `${crits} crit · ${warns} warn · ${advs} adv`, accent: crits > 0 ? [192,57,43] : warns > 0 ? [217,119,6] : [22,163,74] },
      ];

      const cellW = CW / 3, cellH = 20;
      statCells.forEach((cell, idx) => {
        const col = idx % 3, row = Math.floor(idx / 3);
        const cx = ML + col * cellW, cy = y + row * cellH;
        doc.setFillColor(255, 255, 255);
        doc.rect(cx, cy, cellW, cellH, 'F');
        doc.setDrawColor(229, 227, 223);
        doc.setLineWidth(0.25);
        doc.rect(cx, cy, cellW, cellH, 'S');
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(6);
        doc.setTextColor(156, 163, 175);
        doc.text(cell.label, cx + 3, cy + 5);
        doc.setFont('courier', 'bold');
        doc.setFontSize(10);
        doc.setTextColor(...(cell.accent || [26, 26, 26]));
        doc.text(String(cell.value), cx + 3, cy + 13);
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(6);
        doc.setTextColor(156, 163, 175);
        doc.text(cell.sub, cx + 3, cy + 18);
      });
      y += cellH * 2 + 8;

      // ── SETUP SUMMARY + HOLE INVENTORY (side by side) ─────────────────────────
      const colW = (CW - 6) / 2;
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(7);
      doc.setTextColor(107, 114, 128);
      doc.text('SETUP SUMMARY', ML, y);
      doc.text('HOLE INVENTORY', ML + colW + 6, y);
      y += 5;

      const rowH = 7;
      const hdrH = 6;
      let yL = y, yR = y;

      // — Setup header —
      doc.setFillColor(248, 247, 244);
      doc.rect(ML, yL, colW, hdrH, 'F');
      doc.setDrawColor(229, 227, 223);
      doc.setLineWidth(0.2);
      doc.rect(ML, yL, colW, hdrH, 'S');
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(5.5);
      doc.setTextColor(156, 163, 175);
      ['AXIS','FEATURES','H','F','FLAGS'].forEach((h, i) => {
        const xs = [ML+2, ML+14, ML+colW-18, ML+colW-11, ML+colW-2];
        doc.text(h, xs[i], yL + 4, i === 4 ? { align: 'right' } : {});
      });
      yL += hdrH;

      // — Setup rows —
      R.fixturings.forEach((f, i) => {
        const tc = f.concerns.critical + f.concerns.warning + f.concerns.advisory;
        const fRgb = f.concerns.critical > 0 ? [192,57,43] : f.concerns.warning > 0 ? [217,119,6] : tc > 0 ? [107,114,128] : [156,163,175];
        doc.setFillColor(i%2===0 ? 255:250, i%2===0 ? 255:250, i%2===0 ? 255:250);
        doc.rect(ML, yL, colW, rowH, 'F');
        doc.setDrawColor(240, 237, 233);
        doc.rect(ML, yL, colW, rowH, 'S');
        doc.setFont('courier', 'bold');
        doc.setFontSize(8);
        doc.setTextColor(26, 26, 26);
        doc.text(f.label, ML + 2, yL + 5);
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(5.5);
        doc.setTextColor(107, 114, 128);
        const feats = [f.planar>0&&`${f.planar}pl`, f.holes>0&&`${f.holes}h`, `~${f.tool_changes}tc`].filter(Boolean).join(' · ');
        doc.text(feats, ML + 14, yL + 5);
        doc.setFont('courier', 'normal');
        doc.setFontSize(7);
        doc.setTextColor(26, 26, 26);
        doc.text(String(f.holes),  ML + colW - 18, yL + 5);
        doc.text(String(f.planar), ML + colW - 11, yL + 5);
        doc.setFont('courier', tc > 0 ? 'bold' : 'normal');
        doc.setTextColor(...fRgb);
        doc.text(tc > 0 ? String(tc) : '—', ML + colW - 2, yL + 5, { align: 'right' });
        yL += rowH;
      });

      // — Hole header —
      const hx = ML + colW + 6;
      doc.setFillColor(248, 247, 244);
      doc.rect(hx, yR, colW, hdrH, 'F');
      doc.setDrawColor(229, 227, 223);
      doc.rect(hx, yR, colW, hdrH, 'S');
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(5.5);
      doc.setTextColor(156, 163, 175);
      doc.text('TYPE', hx + 2, yR + 4);
      doc.text(`⌀ (${R.unit_label})`, hx + colW - 24, yR + 4);
      doc.text('DEPTH', hx + colW - 14, yR + 4);
      doc.text('L/D', hx + colW - 2, yR + 4, { align: 'right' });
      yR += hdrH;

      // — Hole rows —
      const HOLE_LABELS_PDF = { through:'Through', through_counterbore:'Counterbore', through_countersink:'Countersink', blind_flat:'Blind (flat)', blind_with_tip:'Blind (tip)' };
      R.holes.forEach((h, i) => {
        doc.setFillColor(i%2===0 ? 255:250, i%2===0 ? 255:250, i%2===0 ? 255:250);
        doc.rect(hx, yR, colW, rowH, 'F');
        doc.setDrawColor(240, 237, 233);
        doc.rect(hx, yR, colW, rowH, 'S');
        const isBlind = h.type.startsWith('blind');
        doc.setFont('helvetica', 'normal');
        doc.setFontSize(6.5);
        doc.setTextColor(...(isBlind ? [146,64,14] : [20,83,45]));
        doc.text(HOLE_LABELS_PDF[h.type] || h.type, hx + 2, yR + 5);
        doc.setFont('courier', 'normal');
        doc.setFontSize(7);
        doc.setTextColor(55, 65, 81);
        doc.text((h.radius*2).toFixed(R.display_unit==='inch'?4:2), hx + colW - 24, yR + 5);
        doc.text(h.depth.toFixed(R.display_unit==='inch'?4:1), hx + colW - 14, yR + 5);
        const ldRgb = !h.ld ? [156,163,175] : h.ld >= 6 ? [192,57,43] : h.ld >= 4 ? [217,119,6] : [55,65,81];
        doc.setTextColor(...ldRgb);
        doc.setFont('courier', h.ld >= 4 ? 'bold' : 'normal');
        doc.text(h.ld ? `${h.ld}:1` : '—', hx + colW - 2, yR + 5, { align: 'right' });
        yR += rowH;
      });

      y = Math.max(yL, yR) + 10;

      // ── DFM FLAGS ────────────────────────────────────────────────────────────
      if (y > PH - 50) { doc.addPage(); y = MT; }

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(7);
      doc.setTextColor(107, 114, 128);
      doc.text('MANUFACTURING FLAGS', ML, y);
      y += 5;

      const SEV_BG_PDF  = { critical:[254,242,242], warning:[255,251,235], advisory:[249,250,251] };
      const SEV_RGB_PDF = { critical:[192,57,43],   warning:[217,119,6],   advisory:[107,114,128] };

      if (totalFlags === 0) {
        doc.setFillColor(240, 253, 244);
        doc.rect(ML, y, CW, 8, 'F');
        doc.setFont('helvetica', 'bold');
        doc.setFontSize(8);
        doc.setTextColor(21, 128, 61);
        doc.text('No manufacturing flags — part appears suitable for standard CNC machining.', ML + 4, y + 5.5);
      } else {
        groups.forEach(g => {
          if (y > PH - 20) { doc.addPage(); y = MT; }
          const sev = g.severity;
          const label = CODE_LABELS[g.code] || g.code.replace(/_/g, ' ');
          // Group header
          doc.setFillColor(...SEV_BG_PDF[sev]);
          doc.rect(ML, y, CW, 7, 'F');
          doc.setDrawColor(...SEV_RGB_PDF[sev]);
          doc.setLineWidth(0.8);
          doc.line(ML, y, ML, y + 7);
          doc.setDrawColor(229, 227, 223);
          doc.setLineWidth(0.2);
          doc.rect(ML, y, CW, 7, 'S');
          doc.setFont('helvetica', 'bold');
          doc.setFontSize(6);
          doc.setTextColor(...SEV_RGB_PDF[sev]);
          doc.text(sev.toUpperCase(), ML + 3, y + 4.5);
          doc.setFontSize(7);
          doc.setTextColor(55, 65, 81);
          doc.text(label, ML + 22, y + 4.5);
          if (g.items.length > 1) {
            doc.setFont('courier', 'bold');
            doc.setFontSize(7);
            doc.setTextColor(...SEV_RGB_PDF[sev]);
            doc.text(`×${g.items.length}`, ML + CW - 2, y + 4.5, { align: 'right' });
          }
          y += 7;
          // Item rows
          g.items.forEach((item, i) => {
            if (y > PH - 12) { doc.addPage(); y = MT; }
            doc.setFillColor(i%2===0 ? 255:250, i%2===0 ? 255:250, i%2===0 ? 255:250);
            doc.rect(ML, y, CW, 6, 'F');
            doc.setDrawColor(229, 227, 223);
            doc.setLineWidth(0.2);
            doc.rect(ML, y, CW, 6, 'S');
            doc.setFont('courier', 'normal');
            doc.setFontSize(6);
            doc.setTextColor(156, 163, 175);
            doc.text(`Fix. ${item.fixturing}`, ML + 3, y + 4);
            doc.setFont('helvetica', 'normal');
            doc.setFontSize(6.5);
            doc.setTextColor(55, 65, 81);
            const msgLine = doc.splitTextToSize(item.message, CW - 25)[0];
            doc.text(msgLine, ML + 22, y + 4);
            y += 6;
          });
          y += 2;
        });
      }

      // Footer
      doc.setFont('courier', 'normal');
      doc.setFontSize(7);
      doc.setTextColor(209, 205, 199);
      doc.text(R.filename, PW - MR, PH - 8, { align: 'right' });

      doc.save(`${R.filename.replace(/\.[^.]+$/, '')}_facet_report.pdf`);
    } finally {
      setPdfBusy(false);
    }
  }

  function selectFaces(faceIdxs, text, sev) {
    if (JSON.stringify(faceIdxs.sort()) === JSON.stringify([...selectedFaceIdxs].sort())) {
      setSelectedFaceIdxs([]); setLabelText(""); setLabelSev("advisory");
    } else {
      setSelectedFaceIdxs(faceIdxs); setLabelText(text); setLabelSev(sev);
    }
  }

  function toggleFixture(fix) {
    if (activeFixture && activeFixture.id === fix.id) {
      setActiveFixture(null);
      // restore default face colors by clearing selection
    } else {
      setActiveFixture(fix);
      setSelectedFaceIdxs([]); setLabelText(""); setLabelSev("advisory");
    }
  }

  function snapToFixture(fix) {
    if (snapRef.current) snapRef.current(fix.approach_vector);
  }

  // ── DFM flag grouping ──
  const SEV_RANK = { critical: 0, warning: 1, advisory: 2 };
  const CODE_LABELS = {
    hole_ld:                  "Deep Hole (L/D)",
    small_hole:               "Small Hole",
    ball_nose_required:       "Ball Nose Required",
    concave_fillet_tool_dia:  "Concave Fillet Tool",
    sharp_internal_corner:    "Sharp Internal Corner",
    deep_feature:             "Deep Feature",
    thin_wall:                "Thin Wall",
    thin_wall_hole_proximity: "Thin Wall — Hole Proximity",
    partial_hole:             "Partial / Intersected Hole",
  };
  const groups = [];
  const seen = {};
  for (const d of R.dfm) {
    if (!seen[d.code]) { seen[d.code] = { code: d.code, severity: d.severity, items: [] }; groups.push(seen[d.code]); }
    if (SEV_RANK[d.severity] < SEV_RANK[seen[d.code].severity]) seen[d.code].severity = d.severity;
    seen[d.code].items.push(d);
  }
  const [expanded, setExpanded] = React.useState({});
  const toggle = (code) => setExpanded(e => ({ ...e, [code]: !e[code] }));

  function SectionHead({ children }) {
    return <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: "#6b7280", marginBottom: 8 }}>{children}</div>;
  }

  const isActiveFlag = (items) => items.some(d => d.face_idxs && d.face_idxs.length > 0 && JSON.stringify(d.face_idxs.slice().sort()) === JSON.stringify([...selectedFaceIdxs].sort()));
  const isActiveHole = (h) => h.face_idxs && h.face_idxs.length > 0 && JSON.stringify(h.face_idxs.slice().sort()) === JSON.stringify([...selectedFaceIdxs].sort());

  return (
    <div style={{ background: "#f8f7f4", minHeight: "100vh", fontFamily: "'IBM Plex Sans', system-ui, sans-serif", color: "#1a1a1a" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        .clickable-row:hover { background: #f5f3f0 !important; cursor: pointer; }
        .clickable-row.active { background: #fff7ed !important; outline: 1px solid #fed7aa; }
        @media print { .viewer-card { display: none; } body { background: white; } }
      `}</style>

      <div style={{ maxWidth: 860, margin: "0 auto", padding: "40px 40px 60px" }}>

        {/* HEADER */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 28, paddingBottom: 20, borderBottom: "2px solid #1a1a1a" }}>
          <div>
            <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.18em", color: "#6b7280", marginBottom: 5, textTransform: "uppercase" }}>Facet — Part Analysis Report</div>
            <div style={{ fontSize: 22, fontWeight: 600, color: "#1a1a1a", letterSpacing: "-0.01em", marginBottom: 3 }}>{R.filename}</div>
            <div style={{ fontSize: 11, color: "#9ca3af" }}>{new Date(R.analyzed_at).toLocaleString("en-US", { dateStyle: "long", timeStyle: "short" })}</div>
          </div>
          <div style={{ textAlign: "right", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 12 }}>
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.14em", color: "#9ca3af", marginBottom: 4, textTransform: "uppercase" }}>Machine Type</div>
              <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 16, fontWeight: 500, color: "#1a1a1a" }}>{R.machine_classification.replace(/-/g, " ")}</div>
            </div>
            <button
              onClick={buildPDF}
              disabled={pdfBusy}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "8px 16px", borderRadius: 5, cursor: pdfBusy ? "wait" : "pointer",
                background: pdfBusy ? "#f1f5f9" : "#1a1a1a",
                color: pdfBusy ? "#9ca3af" : "#fff",
                border: "none", fontFamily: "'IBM Plex Mono', monospace",
                fontSize: 11, fontWeight: 500, letterSpacing: "0.04em",
                boxShadow: pdfBusy ? "none" : "0 1px 3px rgba(0,0,0,0.18)",
              }}
            >
              <span style={{ fontSize: 13 }}>{pdfBusy ? "⏳" : "↓"}</span>
              {pdfBusy ? "GENERATING…" : "EXPORT PDF"}
            </button>
          </div>
        </div>

        {/* STAT STRIP */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 1, marginBottom: 20, background: "#e5e3df", borderRadius: 6, overflow: "hidden" }}>
          {[
            { label: "Setups Required", value: R.fixturing_count, sub: "fixturings" },
            { label: "Bounding Box",    value: `${R.bounding_box.x} × ${R.bounding_box.y} × ${R.bounding_box.z}`, sub: `${R.unit_label}  X · Y · Z` },
            { label: "Holes",          value: R.holes.length, sub: `${R.holes.filter(h=>h.type.startsWith("blind")).length} blind · ${R.holes.filter(h=>h.type.startsWith("through")).length} through` },
            { label: "Planar Faces",   value: R.planar_faces, sub: "flat surfaces" },
            { label: "Material Removed", value: `${R.material_removal_pct}%`, sub: R.display_unit === "inch" ? `${(R.machined_volume_mm3/16387.1).toFixed(3)} in³ of ${(R.bbox_volume_mm3/16387.1).toFixed(3)} in³` : `${(R.machined_volume_mm3/1000).toFixed(1)} cm³ of ${(R.bbox_volume_mm3/1000).toFixed(1)} cm³`, accent: R.material_removal_pct > 70 ? SEV_COLOR.warning : "#1a1a1a" },
            { label: "DFM Flags",      value: totalFlags, sub: totalFlags === 0 ? "no issues" : `${crits} crit · ${warns} warn · ${advs} adv`, accent: flagColor },
          ].map(({ label, value, sub, accent }) => (
            <div key={label} style={{ background: "#fff", padding: "14px 16px" }}>
              <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.14em", color: "#9ca3af", textTransform: "uppercase", marginBottom: 5 }}>{label}</div>
              <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 14, fontWeight: 500, color: accent || "#1a1a1a", lineHeight: 1.2, marginBottom: 3 }}>{value}</div>
              <div style={{ fontSize: 10, color: "#9ca3af" }}>{sub}</div>
            </div>
          ))}
        </div>

        {/* INLINE 3D VIEWER */}
        {HAS_GEO && (
          <div className="viewer-card" style={{ marginBottom: 24, background: "#fff", border: "1px solid #e5e3df", borderRadius: 8, overflow: "hidden" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 16px", background: "#f8f7f4", borderBottom: "1px solid #e5e3df" }}>
              <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: "#6b7280" }}>3D View</div>
              <div style={{ fontSize: 9, color: "#c4bfb8", fontFamily: "'IBM Plex Mono', monospace" }}>DRAG · SCROLL · RIGHT-DRAG PAN · CLICK FEATURES TO HIGHLIGHT</div>
            </div>
            <div style={{ height: 400 }}>
              <Viewer3D
                selectedFaceIdxs={selectedFaceIdxs}
                labelText={labelText}
                labelSev={labelSev}
                activeFixture={activeFixture}
                snapRef={snapRef}
                captureRef={captureRef}
              />
            </div>
          </div>
        )}

        {/* SETUP + HOLES TWO COLUMN */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 24 }}>

            {/* SETUPS */}
            <div>
              <SectionHead>Setup Summary {HAS_GEO && <span style={{ fontWeight: 400, letterSpacing: 0, textTransform: "none", color: "#c4bfb8", fontSize: 9 }}>— click to show axis</span>}</SectionHead>
              <div style={{ background: "#fff", border: "1px solid #e5e3df", borderRadius: 6, overflow: "hidden" }}>
                <div style={{ display: "grid", gridTemplateColumns: "44px 1fr 38px 38px 38px 52px", padding: "7px 12px", background: "#f8f7f4", borderBottom: "1px solid #e5e3df" }}>
                  {["Axis","Features","Holes","Faces","Flags",""].map((h, i) => (
                    <div key={i} style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.12em", color: "#9ca3af", textTransform: "uppercase", textAlign: i > 1 ? "right" : "left" }}>{h}</div>
                  ))}
                </div>
                {R.fixturings.map((f, i) => {
                  const tc = f.concerns.critical + f.concerns.warning + f.concerns.advisory;
                  const fc = f.concerns.critical > 0 ? SEV_COLOR.critical : f.concerns.warning > 0 ? SEV_COLOR.warning : f.concerns.advisory > 0 ? SEV_COLOR.advisory : "#9ca3af";
                  const isActiveFix = activeFixture && activeFixture.id === f.id;
                  return (
                    <div
                      key={f.id}
                      style={{
                        display: "grid", gridTemplateColumns: "44px 1fr 38px 38px 38px 52px",
                        padding: "10px 12px",
                        borderBottom: i < R.fixturings.length - 1 ? "1px solid #f0ede9" : "none",
                        alignItems: "center",
                        background: isActiveFix ? "#eff6ff" : "transparent",
                        cursor: HAS_GEO ? "pointer" : "default",
                        outline: isActiveFix ? "1px solid #bfdbfe" : "none",
                      }}
                      onClick={() => HAS_GEO && toggleFixture(f)}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                        <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 13, fontWeight: 500, color: isActiveFix ? "#2563eb" : "#1a1a1a" }}>{f.label}</div>
                        {isActiveFix && <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#2563eb" }} />}
                      </div>
                      <div style={{ fontSize: 10, color: "#6b7280" }}>
                        {[f.planar > 0 && `${f.planar} planar`, f.fillets > 0 && `${f.fillets} fillet${f.fillets > 1?"s":""}`, f.min_tool_dia && `⌀${f.min_tool_dia}${R.unit_label}`, `~${f.tool_changes} chg`].filter(Boolean).join(" · ")}
                      </div>
                      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, textAlign: "right" }}>{f.holes}</div>
                      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, textAlign: "right" }}>{f.planar}</div>
                      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12, fontWeight: tc > 0 ? 600 : 400, color: fc, textAlign: "right" }}>{tc || "—"}</div>
                      <div style={{ textAlign: "right" }}>
                        {HAS_GEO && (
                          <button
                            onClick={e => { e.stopPropagation(); if (!isActiveFix) toggleFixture(f); snapToFixture(f); }}
                            title="View from tool direction"
                            style={{
                              fontFamily: "'IBM Plex Mono', monospace", fontSize: 9,
                              padding: "3px 7px", borderRadius: 4, cursor: "pointer",
                              background: isActiveFix ? "#2563eb" : "#f1f5f9",
                              color: isActiveFix ? "#fff" : "#64748b",
                              border: isActiveFix ? "1px solid #1d4ed8" : "1px solid #e2e8f0",
                            }}
                          >↗ VIEW</button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* HOLES */}
            <div>
              <SectionHead>Hole Inventory {HAS_GEO && <span style={{ fontWeight: 400, letterSpacing: 0, textTransform: "none", color: "#c4bfb8", fontSize: 9 }}>— click to highlight</span>}</SectionHead>
              <div style={{ background: "#fff", border: "1px solid #e5e3df", borderRadius: 6, overflow: "hidden" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 58px 60px 44px", padding: "7px 12px", background: "#f8f7f4", borderBottom: "1px solid #e5e3df" }}>
                  {["Type", `⌀ (${R.unit_label})`, "Depth", "L/D"].map((h, i) => (
                    <div key={h} style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.12em", color: "#9ca3af", textTransform: "uppercase", textAlign: i > 0 ? "right" : "left" }}>{h}</div>
                  ))}
                </div>
                {R.holes.length === 0
                  ? <div style={{ padding: "14px 12px", fontSize: 12, color: "#9ca3af" }}>No holes detected</div>
                  : R.holes.map((h, i) => {
                    const ldColor = !h.ld ? "#9ca3af" : h.ld >= 6 ? SEV_COLOR.critical : h.ld >= 4 ? SEV_COLOR.warning : "#374151";
                    const isBlind = h.type.startsWith("blind");
                    const active = isActiveHole(h);
                    const hasGeoLink = HAS_GEO && h.face_idxs && h.face_idxs.length > 0;
                    return (
                      <div
                        key={h.id}
                        className={hasGeoLink ? `clickable-row${active ? " active" : ""}` : ""}
                        onClick={() => hasGeoLink && selectFaces(h.face_idxs, `${HOLE_LABELS[h.type] || h.type} — ⌀${(h.radius*2).toFixed(R.display_unit==="inch"?4:2)} ${R.unit_label}`, "advisory")}
                        style={{ display: "grid", gridTemplateColumns: "1fr 58px 60px 44px", padding: "9px 12px", borderBottom: i < R.holes.length - 1 ? "1px solid #f0ede9" : "none", alignItems: "center" }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                          <span style={{ fontSize: 10, fontWeight: 500, color: isBlind ? "#92400e" : "#14532d", background: isBlind ? "#fef3c7" : "#f0fdf4", padding: "2px 6px", borderRadius: 3 }}>
                            {HOLE_LABELS[h.type] || h.type}
                          </span>
                          {h.cone_angle && <span style={{ fontSize: 9, color: "#9ca3af" }}>{h.cone_angle}°</span>}
                        </div>
                        <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "#374151", textAlign: "right" }}>{(h.radius * 2).toFixed(R.display_unit === "inch" ? 4 : 2)}</div>
                        <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "#374151", textAlign: "right" }}>{h.depth.toFixed(R.display_unit === "inch" ? 4 : 1)}</div>
                        <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: ldColor, textAlign: "right", fontWeight: h.ld >= 4 ? 600 : 400 }}>{h.ld ? `${h.ld}:1` : "—"}</div>
                      </div>
                    );
                  })}
              </div>
            </div>
          </div>

          {/* DFM FLAGS */}
          {totalFlags > 0 && (
            <div>
              <SectionHead>Manufacturing Flags {HAS_GEO && <span style={{ fontWeight: 400, letterSpacing: 0, textTransform: "none", color: "#c4bfb8", fontSize: 9 }}>— click to highlight</span>}</SectionHead>
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                {groups.map(g => {
                  const sev   = g.severity;
                  const open  = !!expanded[g.code];
                  const label = CODE_LABELS[g.code] || g.code.replace(/_/g, " ");
                  const multi = g.items.length > 1;
                  const active = isActiveFlag(g.items);

                  return (
                    <div key={g.code} style={{ borderRadius: 5, overflow: "hidden", border: `1px solid ${SEV_BORDER[sev]}`, borderLeft: `3px solid ${SEV_COLOR[sev]}`, outline: active ? `2px solid ${SEV_COLOR[sev]}` : "none" }}>
                      {/* GROUP HEADER */}
                      <div
                        onClick={() => {
                          if (multi) toggle(g.code);
                          // If single item with face_idxs, highlight it
                          if (!multi && g.items[0].face_idxs && g.items[0].face_idxs.length > 0) {
                            selectFaces(g.items[0].face_idxs, g.items[0].message, sev);
                          }
                        }}
                        style={{
                          display: "grid", gridTemplateColumns: "80px 1fr auto auto",
                          gap: 10, alignItems: "center",
                          background: active ? (sev === "critical" ? "#fee2e2" : sev === "warning" ? "#fef3c7" : "#f3f4f6") : SEV_BG[sev],
                          padding: "10px 12px",
                          cursor: "pointer", userSelect: "none",
                        }}
                      >
                        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.12em", color: SEV_COLOR[sev], textTransform: "uppercase" }}>{SEV_LABEL[sev]}</div>
                        <div style={{ fontSize: 12, color: "#374151", lineHeight: 1.45 }}>
                          <span style={{ fontWeight: 500 }}>{label}</span>
                          {!multi && <span style={{ color: "#6b7280", marginLeft: 7, fontFamily: "'IBM Plex Mono', monospace", fontSize: 10 }}>Fix. {g.items[0].fixturing}</span>}
                          {!open && multi && <span style={{ color: "#9ca3af", marginLeft: 7, fontSize: 11 }}>— {g.items[0].message.length > 65 ? g.items[0].message.slice(0,65)+"…" : g.items[0].message}</span>}
                        </div>
                        {multi && <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: SEV_COLOR[sev], background: SEV_BORDER[sev], padding: "2px 6px", borderRadius: 3, whiteSpace: "nowrap" }}>{g.items.length}</span>}
                        {multi && <span style={{ fontSize: 11, color: "#9ca3af", width: 14, textAlign: "center" }}>{open ? "▲" : "▼"}</span>}
                      </div>
                      {/* EXPANDED ITEMS */}
                      {open && multi && (
                        <div style={{ background: "#fff", borderTop: `1px solid ${SEV_BORDER[sev]}` }}>
                          {g.items.map((d, i) => {
                            const itemActive = d.face_idxs && d.face_idxs.length > 0 && JSON.stringify(d.face_idxs.slice().sort()) === JSON.stringify([...selectedFaceIdxs].sort());
                            const hasLink = HAS_GEO && d.face_idxs && d.face_idxs.length > 0;
                            return (
                              <div
                                key={i}
                                className={hasLink ? `clickable-row${itemActive ? " active" : ""}` : ""}
                                onClick={() => hasLink && selectFaces(d.face_idxs, d.message, sev)}
                                style={{
                                  display: "grid", gridTemplateColumns: "72px 1fr",
                                  gap: 10, alignItems: "start",
                                  padding: "8px 12px",
                                  borderBottom: i < g.items.length - 1 ? `1px solid ${SEV_BORDER[sev]}` : "none",
                                  background: itemActive ? (sev === "critical" ? "#fee2e2" : sev === "warning" ? "#fef3c7" : "#f3f4f6") : (i % 2 === 0 ? "#fff" : "#fafafa"),
                                }}
                              >
                                <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "#9ca3af", paddingTop: 1 }}>Fix. {d.fixturing}</div>
                                <div style={{ fontSize: 11, color: "#374151", lineHeight: 1.5 }}>{d.message}</div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                      {/* SINGLE ITEM message */}
                      {!multi && (
                        <div style={{ background: "#fff", borderTop: `1px solid ${SEV_BORDER[sev]}`, padding: "8px 12px" }}>
                          <div style={{ fontSize: 11, color: "#374151", lineHeight: 1.55 }}>{g.items[0].message}</div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {totalFlags === 0 && (
            <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 6, padding: "13px 16px", display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#16a34a", flexShrink: 0 }} />
              <div style={{ fontSize: 13, color: "#15803d", fontWeight: 500 }}>No manufacturing flags — part appears suitable for standard CNC machining.</div>
            </div>
          )}

          {/* FOOTER */}
          <div style={{ marginTop: 36, paddingTop: 14, borderTop: "1px solid #e5e3df", display: "flex", justifyContent: "flex-end" }}>
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
    Write a self-contained single-page HTML report with 3D viewer.

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
  <title>{report_dict['filename']} — Facet Part Report</title>
  <script crossorigin src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
  <script crossorigin src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
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