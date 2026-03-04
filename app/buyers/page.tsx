"use client";

import { useState } from "react";
import WaitlistModal from "@/components/WaitlistModal";

export default function BuyersPage() {
  const [modalOpen, setModalOpen] = useState(false);
 


  return (
    <>
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
        }

        .nav-right { display: flex; align-items: center; gap: 32px; }
        .nav-links { display: flex; gap: 28px; list-style: none; }
        .nav-links a {
          color: var(--muted);
          text-decoration: none;
          font-size: 11px;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          transition: color 0.2s;
        }
        .nav-links a:hover { color: var(--white); }
        .nav-links a.active { color: var(--white); }

        .nav-divider { width: 1px; height: 16px; background: var(--border); }

        .nav-cta {
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
        }
        .nav-cta:hover { background: #D4A050; }

        /* HERO */
        .hero {
          padding: 120px 52px 88px;
          border-bottom: 1px solid var(--border);
          position: relative;
          overflow: hidden;
        }

        .hero-bg {
          position: absolute;
          bottom: -0.08em; right: -0.02em;
          font-family: var(--font-display);
          font-size: clamp(180px, 22vw, 360px);
          font-weight: 300;
          color: transparent;
          -webkit-text-stroke: 1px rgba(196,145,58,0.05);
          line-height: 1;
          user-select: none;
          pointer-events: none;
        }

        .hero-inner {
          position: relative;
          z-index: 2;
          max-width: 780px;
          animation: fadeUp 0.8s ease both;
        }

        .hero-eyebrow {
          font-size: 10px;
          letter-spacing: 0.22em;
          text-transform: uppercase;
          color: var(--gold);
          margin-bottom: 20px;
        }

        .hero-h1 {
          font-family: var(--font-display);
          font-size: clamp(52px, 6.5vw, 96px);
          font-weight: 300;
          line-height: 1.0;
          letter-spacing: -0.01em;
          color: var(--white);
          margin-bottom: 32px;
        }
        .hero-h1 em { font-style: italic; color: var(--gold); }

        .hero-sub {
          font-size: 14px;
          color: var(--muted);
          line-height: 1.85;
          max-width: 540px;
        }
        .hero-sub strong { color: var(--white); font-weight: 400; }

        /* HOW IT WORKS */
        .how-section {
          padding: 96px 52px;
          border-bottom: 1px solid var(--border);
        }

        .section-eyebrow {
          font-size: 10px;
          letter-spacing: 0.22em;
          text-transform: uppercase;
          color: var(--gold);
          margin-bottom: 16px;
        }

        .section-h2 {
          font-family: var(--font-display);
          font-size: clamp(32px, 3vw, 48px);
          font-weight: 300;
          color: var(--white);
          line-height: 1.05;
          margin-bottom: 56px;
        }

        .steps {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 1px;
          background: var(--border);
        }

        .step {
          background: var(--black);
          padding: 44px 40px;
        }

        .step-num {
          font-size: 11px;
          color: var(--gold);
          letter-spacing: 0.14em;
          margin-bottom: 24px;
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .step-num::after { content: ''; flex: 1; height: 1px; background: var(--border); }

        .step-title {
          font-family: var(--font-display);
          font-size: 22px;
          font-weight: 400;
          color: var(--white);
          margin-bottom: 10px;
        }

        .step-desc { font-size: 12px; color: var(--muted); line-height: 1.8; }

        /* BENEFITS */
        .benefits-section {
          padding: 96px 52px;
          border-bottom: 1px solid var(--border);
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1px;
          background: var(--border);
        }

        .benefit-panel {
          background: var(--black);
          padding: 56px 52px;
        }

        .benefit-icon {
          font-size: 22px;
          margin-bottom: 20px;
        }

        .benefit-h3 {
          font-family: var(--font-display);
          font-size: 26px;
          font-weight: 400;
          color: var(--white);
          margin-bottom: 12px;
          line-height: 1.15;
        }

        .benefit-desc {
          font-size: 12px;
          color: var(--muted);
          line-height: 1.85;
        }
        .benefit-desc strong { color: var(--white); font-weight: 400; }

        /* SIGNUP */
        .signup-section {
          padding: 100px 52px;
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 80px;
          align-items: center;
          position: relative;
          overflow: hidden;
        }

        .signup-section::before {
          content: '';
          position: absolute;
          width: 600px; height: 600px;
          border-radius: 50%;
          background: radial-gradient(circle, rgba(196,145,58,0.04) 0%, transparent 65%);
          top: 50%; left: 50%;
          transform: translate(-50%, -50%);
          pointer-events: none;
        }

        .signup-h2 {
          font-family: var(--font-display);
          font-size: clamp(38px, 4vw, 60px);
          font-weight: 300;
          color: var(--white);
          line-height: 1.05;
          margin-bottom: 16px;
        }
        .signup-h2 em { font-style: italic; color: var(--gold); }

        .signup-sub {
          font-size: 12px;
          color: var(--muted);
          line-height: 1.85;
        }

        .email-row { display: flex; margin-bottom: 12px; }

        .email-input {
          flex: 1;
          padding: 14px 18px;
          background: var(--panel);
          border: 1px solid var(--border);
          border-right: none;
          color: var(--white);
          font-family: var(--font-mono);
          font-size: 12px;
          font-weight: 300;
          letter-spacing: 0.04em;
          outline: none;
          transition: border-color 0.2s;
        }
        .email-input::placeholder { color: var(--muted); }
        .email-input:focus { border-color: var(--gold-dim); }

        .submit-btn {
          padding: 14px 22px;
          background: var(--gold);
          border: none;
          color: var(--black);
          font-family: var(--font-mono);
          font-size: 11px;
          font-weight: 500;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          cursor: pointer;
          transition: background 0.2s;
          white-space: nowrap;
        }
        .submit-btn:hover { background: #D4A050; }
        .submit-btn:disabled { opacity: 0.6; cursor: not-allowed; }

        .form-note { font-size: 11px; color: var(--muted); }

        .success-state {
          padding: 28px;
          border: 1px solid rgba(196,145,58,0.25);
          background: rgba(196,145,58,0.04);
        }
        .success-title {
          font-family: var(--font-display);
          font-size: 24px;
          color: var(--white);
          margin-bottom: 8px;
        }
        .success-sub { font-size: 11px; color: var(--muted); line-height: 1.7; }

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
          font-size: 11px; color: var(--muted); text-decoration: none;
          letter-spacing: 0.1em; text-transform: uppercase; transition: color 0.2s;
        }
        .footer-links a:hover { color: var(--white); }
        .footer-meta { font-size: 11px; color: var(--muted); }

        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(18px); }
          to   { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 1000px) {
          .steps { grid-template-columns: 1fr; }
          .benefits-section { grid-template-columns: 1fr; padding: 0; }
          .signup-section { grid-template-columns: 1fr; gap: 48px; padding: 80px 24px; }
        }
        @media (max-width: 768px) {
          nav { padding: 20px 24px; }
          .nav-links { display: none; }
          .nav-divider { display: none; }
          .hero { padding: 100px 24px 64px; }
          .how-section { padding: 72px 24px; }
          .benefit-panel { padding: 44px 24px; }
          footer { padding: 28px 24px; flex-direction: column; gap: 16px; align-items: flex-start; }
        }
      `}</style>

      <WaitlistModal isOpen={modalOpen} onClose={() => setModalOpen(false)} defaultRole="designer" />
      <nav id="main-nav">
        <a href="/" className="nav-wordmark">Facet</a>
        <div className="nav-right">
          <ul className="nav-links">
            <li><a href="/buyers" className="active">Designers</a></li>
            <li><a href="/suppliers">Suppliers</a></li>
          </ul>
          <div className="nav-divider" />
          <button onClick={() => setModalOpen(true)} className="nav-cta">Join</button>
        </div>
      </nav>

      <main>
        {/* HERO */}
        <section className="hero">
          <div className="hero-bg" aria-hidden="true">MAKE</div>
          <div className="hero-inner">
            <div className="hero-eyebrow">For Designers &amp; Engineers</div>
            <h1 className="hero-h1">
              Finally understand<br />
              <em>your quote.</em>
            </h1>
            <p className="hero-sub">
              Upload your design and get competing quotes from{" "}
              <strong>multiple verified CNC machine shops</strong> — with pricing you
              can actually understand. Know what's driving cost, compare your options,
              and design smarter for the next run.
              Starting with <strong>CNC aluminum 6061 brackets</strong> in the Northeast.
            </p>
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section className="how-section">
          <div className="section-eyebrow">How it works</div>
          <h2 className="section-h2">Three steps. That's it.</h2>
          <div className="steps">
            <div className="step">
              <div className="step-num">01</div>
              <div className="step-title">Upload your file</div>
              <p className="step-desc">
                Drop in your STEP or DWG. It's stored under a UUID — only you control
                who sees it. NDA-grade protection by default.
              </p>
            </div>
            <div className="step">
              <div className="step-num">02</div>
              <div className="step-title">Get matched to shops</div>
              <p className="step-desc">
                We match your part to verified Northeast CNC shops that have the right
                equipment and available capacity for your job — not a generic list.
              </p>
            </div>
            <div className="step">
              <div className="step-num">03</div>
              <div className="step-title">We match, you move</div>
              <p className="step-desc">
                Facet routes your job to the right shops based on capability
                and fit. You get competing quotes back — see pricing and why,
                then confirm the one that works.
              </p>
            </div>
          </div>
        </section>

        {/* BENEFITS */}
        <section className="benefits-section" aria-label="Designer benefits">
          <div className="benefit-panel">
            <div className="benefit-icon">⬡</div>
            <h3 className="benefit-h3">Your IP stays yours</h3>
            <p className="benefit-desc">
              Files are stored under a UUID and never shared with any shop without
              your explicit approval. <strong>You control access end to end.</strong>
              NDA-grade protection by default.
            </p>
          </div>
          <div className="benefit-panel">
            <div className="benefit-icon">◈</div>
            <h3 className="benefit-h3">Understand your quote</h3>
            <p className="benefit-desc">
              Tired of quotes that feel arbitrary? Facet surfaces what actually drives cost —
              tolerance spec, surface treatment, batch size, setup complexity.{" "}
              <strong>You'll know why you're quoted what you're quoted.</strong>{" "}
              And how to design more cost-effectively next time.
            </p>
          </div>
          <div className="benefit-panel">
            <div className="benefit-icon">◇</div>
            <h3 className="benefit-h3">Multiple competing quotes</h3>
            <p className="benefit-desc">
              The old way: one shop, one number, take it or leave it.
              The Facet way: <strong>multiple verified shops compete for your job.</strong>{" "}
              We route based on capability and fit — you see the quotes, understand the pricing,
              and confirm the one that works.
            </p>
          </div>
          <div className="benefit-panel">
            <div className="benefit-icon">◯</div>
            <h3 className="benefit-h3">No cold emails. Ever.</h3>
            <p className="benefit-desc">
              Finding a machine shop today means hours of searching, emails that
              go nowhere, and NDAs that never get signed.{" "}
              <strong>Facet cuts all of that out.</strong> Upload, get options, move.
            </p>
          </div>
        </section>

        {/* SIGNUP */}
        <section className="signup-section" aria-label="Designer signup" id="signup">
          <div>
            <h2 className="signup-h2">
              Ready to<br />
              <em>get started?</em>
            </h2>
            <p className="signup-sub">
              Join designers already on the list. We'll reach out as we bring
              Northeast suppliers online for your first job.
            </p>
          </div>
          <div>
            <button onClick={() => setModalOpen(true)} className="submit-btn" style={{width:"auto",padding:"15px 36px"}}>
              Join →
            </button>
          </div>
        </section>
      </main>

      <footer>
        <div className="footer-wordmark">Facet</div>
        <ul className="footer-links">
          <li><a href="/buyers">Designers</a></li>
          <li><a href="/suppliers">Suppliers</a></li>
          <li><button onClick={() => setModalOpen(true)} style={{background:"none",border:"none",cursor:"pointer",fontFamily:"inherit",fontSize:"11px",color:"var(--muted)",letterSpacing:"0.1em",textTransform:"uppercase",transition:"color 0.2s",padding:0}} onMouseOver={e=>(e.currentTarget.style.color="var(--white)")} onMouseOut={e=>(e.currentTarget.style.color="var(--muted)")}>Join</button></li>
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