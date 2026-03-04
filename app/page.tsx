"use client";

import { useState } from "react";
import WaitlistModal from "@/components/WaitlistModal";

export default function HomePage() {
  const [modalOpen, setModalOpen] = useState(false);
  const [modalRole, setModalRole] = useState<"designer" | "shop">("designer");

  const openModal = (role: "designer" | "shop" = "designer") => {
    setModalRole(role);
    setModalOpen(true);
  };

  return (
    <>
      <WaitlistModal isOpen={modalOpen} onClose={() => setModalOpen(false)} defaultRole={modalRole} />
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=DM+Mono:wght@300;400;500&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
          --black: #080808;
          --panel: #141414;
          --panel-hover: #1b1b1b;
          --border: #232323;
          --gold: #C4913A;
          --gold-dim: #7A5820;
          --gold-pale: rgba(196,145,58,0.1);
          --white: #F5F0EB;
          --muted: #686868;
          --font-display: 'Cormorant Garamond', serif;
          --font-mono: 'DM Mono', monospace;
        }

        html { scroll-behavior: smooth; }

        body {
          background: var(--black);
          color: var(--white);
          font-family: var(--font-mono);
          font-size: 13px;
          font-weight: 300;
          letter-spacing: 0.02em;
          line-height: 1.6;
          -webkit-font-smoothing: antialiased;
          overflow-x: hidden;
        }

        body::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
          pointer-events: none;
          z-index: 1000;
          opacity: 0.35;
        }

        /* ── NAV ── */
        nav {
          position: fixed;
          top: 0; left: 0; right: 0;
          z-index: 100;
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 24px 52px;
          transition: background 0.4s, border-color 0.4s;
        }

        nav.scrolled {
          background: rgba(8,8,8,0.95);
          border-bottom: 1px solid var(--border);
          backdrop-filter: blur(16px);
        }

        .nav-wordmark {
          font-family: var(--font-mono);
          font-size: 14px;
          font-weight: 500;
          letter-spacing: 0.2em;
          text-transform: uppercase;
          color: var(--gold);
          text-decoration: none;
          flex-shrink: 0;
        }

        .nav-right {
          display: flex;
          align-items: center;
          gap: 32px;
        }

        /* Nav links always visible on desktop */
        .nav-links {
          display: flex;
          gap: 28px;
          list-style: none;
          align-items: center;
        }

        .nav-links a {
          color: var(--muted);
          text-decoration: none;
          font-size: 11px;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          transition: color 0.2s;
          white-space: nowrap;
        }
        .nav-links a:hover { color: var(--white); }

        .nav-divider {
          width: 1px;
          height: 16px;
          background: var(--border);
        }

        .nav-cta {
          display: inline-flex;
          align-items: center;
          font-family: var(--font-mono);
          font-size: 11px;
          font-weight: 500;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          color: var(--black);
          background: var(--gold);
          padding: 9px 20px;
          text-decoration: none;
          transition: background 0.2s;
          white-space: nowrap;
        }
        .nav-cta:hover { background: #D4A050; }

        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }

        /* ── HERO ── */
        .hero {
          padding: 88px 52px 80px;
          position: relative;
          overflow: hidden;
          border-bottom: 1px solid var(--border);
        }

        .hero-bg-text {
          position: absolute;
          bottom: -0.08em;
          right: -0.03em;
          font-family: var(--font-display);
          font-size: clamp(220px, 28vw, 440px);
          font-weight: 300;
          color: transparent;
          -webkit-text-stroke: 1px rgba(196,145,58,0.055);
          line-height: 1;
          user-select: none;
          pointer-events: none;
          letter-spacing: -0.02em;
        }

        .hero-inner {
          position: relative;
          z-index: 2;
          max-width: 860px;
          animation: fadeUp 0.8s ease both;
        }

        .hero-meta-row {
          display: flex;
          align-items: center;
          margin-bottom: 28px;
        }

        .hero-meta-badge {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          font-size: 10px;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: var(--gold);
          background: var(--gold-pale);
          border: 1px solid rgba(196,145,58,0.28);
          padding: 6px 14px;
        }

        .hero-meta-badge::before {
          content: '';
          width: 5px; height: 5px;
          border-radius: 50%;
          background: var(--gold);
          animation: pulse 2s ease infinite;
          flex-shrink: 0;
        }

        .hero-meta-sep {
          height: 30px;
          width: 1px;
          background: var(--border);
          margin: 0 16px;
        }

        .hero-meta-region {
          font-size: 10px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: var(--muted);
        }
        .hero-meta-region strong { color: var(--white); font-weight: 400; }

        .hero-h1 {
          font-family: var(--font-display);
          font-size: clamp(58px, 7vw, 108px);
          font-weight: 300;
          line-height: 1.0;
          letter-spacing: -0.01em;
          color: var(--white);
          margin-bottom: 36px;
        }
        .hero-h1 em { font-style: italic; color: var(--gold); }

        .hero-h1 .line-sub {
          display: block;
          font-size: clamp(26px, 3vw, 44px);
          color: var(--muted);
          font-weight: 300;
          font-style: normal;
          margin-top: 10px;
          letter-spacing: 0;
        }

        .hero-sub {
          font-size: 14px;
          font-weight: 300;
          color: var(--muted);
          line-height: 1.9;
          max-width: 580px;
        }
        .hero-sub strong { color: var(--white); font-weight: 400; }

        /* ── CARDS ── */
        .cards-section {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1px;
          background: var(--border);
        }

        .side-card {
          background: var(--black);
          padding: 72px 60px;
          position: relative;
          text-decoration: none;
          display: block;
          transition: background 0.25s;
        }
        .side-card:hover { background: #0e0e0e; }

        .side-card::after {
          content: attr(data-num);
          position: absolute;
          top: 52px; right: 52px;
          font-family: var(--font-display);
          font-size: 88px;
          font-weight: 300;
          color: transparent;
          -webkit-text-stroke: 1px rgba(255,255,255,0.028);
          line-height: 1;
          user-select: none;
        }

        .card-eyebrow {
          font-size: 10px;
          letter-spacing: 0.22em;
          text-transform: uppercase;
          color: var(--gold);
          margin-bottom: 20px;
        }

        .card-h2 {
          font-family: var(--font-display);
          font-size: clamp(28px, 2.6vw, 42px);
          font-weight: 300;
          color: var(--white);
          line-height: 1.1;
          margin-bottom: 18px;
          letter-spacing: -0.01em;
        }

        .card-body {
          font-size: 12px;
          color: var(--muted);
          line-height: 1.9;
          margin-bottom: 32px;
          max-width: 360px;
        }

        .card-points {
          display: flex;
          flex-direction: column;
          gap: 12px;
          margin-bottom: 44px;
        }

        .card-point {
          display: flex;
          align-items: flex-start;
          gap: 13px;
          font-size: 12px;
          color: var(--white);
          line-height: 1.55;
        }
        .card-point::before { content: '—'; color: var(--gold); flex-shrink: 0; }

        .card-link {
          display: inline-flex;
          align-items: center;
          gap: 9px;
          font-size: 11px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: var(--gold);
          text-decoration: none;
          transition: gap 0.2s;
        }
        .side-card:hover .card-link { gap: 14px; }

        /* ── FOOTER ── */
        footer {
          padding: 32px 52px;
          border-top: 1px solid var(--border);
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .footer-wordmark {
          font-family: var(--font-mono);
          font-size: 12px;
          font-weight: 500;
          letter-spacing: 0.18em;
          text-transform: uppercase;
          color: var(--gold);
        }

        .footer-links { display: flex; gap: 28px; list-style: none; }
        .footer-links a {
          font-size: 11px;
          color: var(--muted);
          text-decoration: none;
          letter-spacing: 0.1em;
          text-transform: uppercase;
          transition: color 0.2s;
        }
        .footer-links a:hover { color: var(--white); }

        .footer-meta { font-size: 11px; color: var(--muted); }

        /* ── ANIMATIONS ── */
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(18px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        /* ── RESPONSIVE ── */
        @media (max-width: 1080px) {
          .cards-section { grid-template-columns: 1fr; }
        }

        @media (max-width: 768px) {
          nav { padding: 20px 24px; }
          .nav-links { display: none; }
          .nav-divider { display: none; }
          .hero { padding: 88px 24px 64px; }
          .side-card { padding: 52px 28px; }
          footer { padding: 28px 24px; flex-direction: column; gap: 20px; align-items: flex-start; }
        }
      `}</style>

      {/* ── NAV ── */}
      <nav id="main-nav">
        <a href="/" className="nav-wordmark">Facet</a>
        <div className="nav-right">
          <ul className="nav-links">
            <li><a href="/buyers">Designers</a></li>
            <li><a href="/suppliers">Suppliers</a></li>
          </ul>
          <div className="nav-divider" />
          <button onClick={() => openModal("designer")} className="nav-cta">Join</button>
        </div>
      </nav>

      <main>
        {/* ── HERO ── */}
        <section className="hero" aria-label="Facet — CNC manufacturing marketplace">
          <div className="hero-bg-text" aria-hidden="true">FCT</div>

          <div className="hero-inner">
            <div className="hero-meta-row">
              <span className="hero-meta-region">
                <strong>Northeast Launch</strong>&nbsp;— expanding across regions
              </span>
            </div>

            <h1 className="hero-h1">
              Machined parts.<br />
              <em>Real designers.</em><br />
              <em>Real suppliers.</em>
              <span className="line-sub">Quotes you can trust. Jobs worth taking.</span>
            </h1>

            <p className="hero-sub">
              Designers upload a STEP file and get{" "}
              <strong>multiple competitive quotes with pricing you can actually understand</strong>{" "}
              — no cold emails, no black-box numbers, IP protected end to end.
              Shops receive{" "}
              <strong>pre-qualified jobs matched to their equipment</strong>{" "}
              — no wasted time on misaligned budgets or parts they can't make.
            </p>
          </div>
        </section>

        {/* ── CARDS ── */}
        <section className="cards-section" aria-label="Platform value for designers and suppliers">
          <div className="side-card" data-num="01" style={{cursor:"pointer"}} onClick={() => openModal("designer")} role="button" aria-label="Facet for designers">
            <div className="card-eyebrow">Designers &amp; Engineers</div>
            <h2 className="card-h2">
              Know what you're<br />paying for.
            </h2>
            <p className="card-body">
              Stop guessing why one shop quotes $800 and another quotes $3,200.
              Upload your part, get competing quotes from verified Northeast CNC suppliers,
              and actually understand the pricing.
            </p>
            <div className="card-points">
              <div className="card-point">Upload STEP or DWG — stored securely under a UUID, never shared without your approval</div>
              <div className="card-point">Get multiple competing quotes so you can compare on price and capability</div>
              <div className="card-point">Facet routes to shops that fit your part — you see quotes with pricing explained</div>
              <div className="card-point">Starting with CNC aluminum 6061 (brackets) — more materials coming</div>
            </div>
            <span className="card-link">Learn more for designers →</span>
          </div>

          <div className="side-card" data-num="02" style={{cursor:"pointer"}} onClick={() => openModal("shop")} role="button" aria-label="Facet for machine shops">
            <div className="card-eyebrow">CNC Machine Shops</div>
            <h2 className="card-h2">
              Only jobs<br />worth taking.
            </h2>
            <p className="card-body">
              Stop wasting time on back-and-forth that leads nowhere — wrong budgets,
              bad fits, buyers who don't understand what machining costs.
              Facet sends you pre-qualified jobs matched to your shop.
            </p>
            <div className="card-points">
              <div className="card-point">Jobs pre-matched to your equipment, materials, and capacity — no cold leads</div>
              <div className="card-point">Buyers who understand cost drivers — far less time on misaligned quotes</div>
              <div className="card-point">You decide what to accept — no exclusivity, no pressure</div>
              <div className="card-point">Early partners directly shape how the platform develops</div>
            </div>
            <span className="card-link">Learn more for suppliers →</span>
          </div>
        </section>
      </main>

      {/* ── FOOTER ── */}
      <footer>
        <div className="footer-wordmark">Facet</div>
        <ul className="footer-links">
          <li><a href="/buyers">Designers</a></li>
          <li><a href="/suppliers">Suppliers</a></li>
          <li><button onClick={() => openModal("designer")} style={{background:"none",border:"none",cursor:"pointer",fontFamily:"inherit",fontSize:"11px",color:"var(--muted)",letterSpacing:"0.1em",textTransform:"uppercase",transition:"color 0.2s",padding:0}} onMouseOver={e=>(e.currentTarget.style.color="var(--white)")} onMouseOut={e=>(e.currentTarget.style.color="var(--muted)")}>Join</button></li>
        </ul>
        <div className="footer-meta">© 2026 Facet. All rights reserved.</div>
      </footer>

      <script dangerouslySetInnerHTML={{
        __html: `
          const nav = document.getElementById('main-nav');
          window.addEventListener('scroll', () => {
            nav.classList.toggle('scrolled', window.scrollY > 40);
          }, { passive: true });
        `
      }} />
    </>
  );
}
