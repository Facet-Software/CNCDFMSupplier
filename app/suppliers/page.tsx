"use client";

import { useState } from "react";
import WaitlistModal from "@/components/WaitlistModal";

export default function SuppliersPage() {
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;1,300;1,400&family=DM+Mono:wght@300;400;500&display=swap');
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
          --black: #080808; --panel: #141414; --panel-hover: #1b1b1b; --border: #232323;
          --gold: #C4913A; --gold-dim: #7A5820; --gold-pale: rgba(196,145,58,0.1);
          --white: #F5F0EB; --muted: #686868;
          --font-display: 'Cormorant Garamond', serif; --font-mono: 'DM Mono', monospace;
        }
        body { background: var(--black); color: var(--white); font-family: var(--font-mono); font-size: 13px; font-weight: 300; letter-spacing: 0.02em; line-height: 1.6; -webkit-font-smoothing: antialiased; overflow-x: hidden; }
        body::before { content: ''; position: fixed; inset: 0; background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E"); pointer-events: none; z-index: 1000; opacity: 0.35; }
        nav { position: fixed; top: 0; left: 0; right: 0; z-index: 100; display: flex; align-items: center; justify-content: space-between; padding: 24px 52px; transition: background 0.4s, border-color 0.4s; }
        nav.scrolled { background: rgba(8,8,8,0.95); border-bottom: 1px solid var(--border); backdrop-filter: blur(16px); }
        .nav-wordmark { font-family: var(--font-mono); font-size: 14px; font-weight: 500; letter-spacing: 0.2em; text-transform: uppercase; color: var(--white); text-decoration: none; }
        .nav-wordmark span { color: var(--gold); }
        .nav-right { display: flex; align-items: center; gap: 32px; }
        .nav-links { display: flex; gap: 28px; list-style: none; }
        .nav-links a { color: var(--muted); text-decoration: none; font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; transition: color 0.2s; }
        .nav-links a:hover, .nav-links a.active { color: var(--white); }
        .nav-divider { width: 1px; height: 16px; background: var(--border); }
        .nav-cta { font-family: var(--font-mono); font-size: 11px; font-weight: 500; letter-spacing: 0.14em; text-transform: uppercase; color: var(--black); background: var(--gold); padding: 9px 20px; border: none; cursor: pointer; transition: background 0.2s; }
        .nav-cta:hover { background: #D4A050; }
        .hero { padding: 120px 52px 88px; border-bottom: 1px solid var(--border); position: relative; overflow: hidden; }
        .hero-bg { position: absolute; bottom: -0.08em; right: -0.02em; font-family: var(--font-display); font-size: clamp(180px, 22vw, 360px); font-weight: 300; color: transparent; -webkit-text-stroke: 1px rgba(196,145,58,0.05); line-height: 1; user-select: none; pointer-events: none; }
        .hero-inner { position: relative; z-index: 2; max-width: 780px; animation: fadeUp 0.8s ease both; }
        .hero-eyebrow { font-size: 10px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--gold); margin-bottom: 20px; }
        .hero-h1 { font-family: var(--font-display); font-size: clamp(52px, 6.5vw, 96px); font-weight: 300; line-height: 1.0; letter-spacing: -0.01em; color: var(--white); margin-bottom: 32px; }
        .hero-h1 em { font-style: italic; color: var(--gold); }
        .hero-sub { font-size: 14px; color: var(--muted); line-height: 1.85; max-width: 540px; }
        .hero-sub strong { color: var(--white); font-weight: 400; }
        .how-section { padding: 96px 52px; border-bottom: 1px solid var(--border); }
        .section-eyebrow { font-size: 10px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--gold); margin-bottom: 16px; }
        .section-h2 { font-family: var(--font-display); font-size: clamp(32px, 3vw, 48px); font-weight: 300; color: var(--white); line-height: 1.05; margin-bottom: 56px; }
        .steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--border); }
        .step { background: var(--black); padding: 44px 40px; }
        .step-num { font-size: 11px; color: var(--gold); letter-spacing: 0.14em; margin-bottom: 24px; display: flex; align-items: center; gap: 12px; }
        .step-num::after { content: ''; flex: 1; height: 1px; background: var(--border); }
        .step-title { font-family: var(--font-display); font-size: 22px; font-weight: 400; color: var(--white); margin-bottom: 10px; }
        .step-desc { font-size: 12px; color: var(--muted); line-height: 1.8; }
        .benefits-section { border-bottom: 1px solid var(--border); display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--border); }
        .benefit-panel { background: var(--black); padding: 56px 52px; }
        .benefit-icon { font-size: 22px; margin-bottom: 20px; }
        .benefit-h3 { font-family: var(--font-display); font-size: 26px; font-weight: 400; color: var(--white); margin-bottom: 12px; line-height: 1.15; }
        .benefit-desc { font-size: 12px; color: var(--muted); line-height: 1.85; }
        .benefit-desc strong { color: var(--white); font-weight: 400; }
        .signup-section { padding: 100px 52px; display: grid; grid-template-columns: 1fr 1fr; gap: 80px; align-items: center; position: relative; overflow: hidden; }
        .signup-section::before { content: ''; position: absolute; width: 600px; height: 600px; border-radius: 50%; background: radial-gradient(circle, rgba(196,145,58,0.04) 0%, transparent 65%); top: 50%; left: 50%; transform: translate(-50%, -50%); pointer-events: none; }
        .signup-h2 { font-family: var(--font-display); font-size: clamp(38px, 4vw, 60px); font-weight: 300; color: var(--white); line-height: 1.05; margin-bottom: 16px; }
        .signup-h2 em { font-style: italic; color: var(--gold); }
        .signup-sub { font-size: 12px; color: var(--muted); line-height: 1.85; }
        .submit-btn { padding: 14px 22px; background: var(--gold); border: none; color: var(--black); font-family: var(--font-mono); font-size: 11px; font-weight: 500; letter-spacing: 0.14em; text-transform: uppercase; cursor: pointer; transition: background 0.2s; white-space: nowrap; }
        .submit-btn:hover { background: #D4A050; }
        footer { padding: 32px 52px; border-top: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
        .footer-wordmark { font-family: var(--font-mono); font-size: 12px; font-weight: 500; letter-spacing: 0.18em; text-transform: uppercase; color: var(--muted); }
        .footer-wordmark span { color: var(--gold); }
        .footer-links { display: flex; gap: 28px; list-style: none; }
        .footer-links a { font-size: 11px; color: var(--muted); text-decoration: none; letter-spacing: 0.1em; text-transform: uppercase; transition: color 0.2s; }
        .footer-links a:hover { color: var(--white); }
        .footer-meta { font-size: 11px; color: var(--muted); }
        @keyframes fadeUp { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: translateY(0); } }
        @media (max-width: 1000px) { .steps { grid-template-columns: 1fr; } .benefits-section { grid-template-columns: 1fr; } .signup-section { grid-template-columns: 1fr; gap: 48px; padding: 80px 24px; } }
        @media (max-width: 768px) { nav { padding: 20px 24px; } .nav-links { display: none; } .nav-divider { display: none; } .hero { padding: 100px 24px 64px; } .how-section { padding: 72px 24px; } .benefit-panel { padding: 44px 24px; } footer { padding: 28px 24px; flex-direction: column; gap: 16px; align-items: flex-start; } }
      `}</style>

      <WaitlistModal isOpen={modalOpen} onClose={() => setModalOpen(false)} defaultRole="shop" />
      <nav id="main-nav">
        <a href="/" className="nav-wordmark">Fac<span>et</span></a>
        <div className="nav-right">
          <ul className="nav-links">
            <li><a href="/buyers">Designers</a></li>
            <li><a href="/suppliers" className="active">Suppliers</a></li>
          </ul>
          <div className="nav-divider" />
          <button onClick={() => setModalOpen(true)} className="nav-cta">Join</button>
        </div>
      </nav>

      <main>
        <section className="hero">
          <div className="hero-bg" aria-hidden="true">SHOP</div>
          <div className="hero-inner">
            <div className="hero-eyebrow">For CNC Machine Shops</div>
            <h1 className="hero-h1">
              Stop wasting time on<br />
              <em>jobs that don&apos;t fit.</em>
            </h1>
            <p className="hero-sub">
              Too much back-and-forth. Buyers who don&apos;t understand what machining costs.
              Quotes that go nowhere because the budget was never realistic.{" "}
              <strong>Facet sends you pre-qualified jobs matched to your equipment</strong>{" "}
              — so you spend your time on work worth taking, not chasing dead ends.
              Starting with <strong>CNC aluminum 6061 brackets</strong> in the Northeast.
            </p>
          </div>
        </section>

        <section className="how-section">
          <div className="section-eyebrow">How it works</div>
          <h2 className="section-h2">Simple for your shop.</h2>
          <div className="steps">
            <div className="step">
              <div className="step-num">01</div>
              <div className="step-title">Tell us your capabilities</div>
              <p className="step-desc">
                Share your equipment, materials, capacity, and what you like to run.
                We use that to route jobs to you — not spam you with everything.
              </p>
            </div>
            <div className="step">
              <div className="step-num">02</div>
              <div className="step-title">Receive matched job requests</div>
              <p className="step-desc">
                Jobs arrive already filtered for your setup — right material,
                right tolerance range, right batch size. No cold leads, no noise.
              </p>
            </div>
            <div className="step">
              <div className="step-num">03</div>
              <div className="step-title">Accept only what works</div>
              <p className="step-desc">
                Review the job, decide if it&apos;s a fit, accept or pass.
                No exclusivity. No pressure. You stay in control of your capacity.
              </p>
            </div>
          </div>
        </section>

        <section className="benefits-section" aria-label="Supplier benefits">
          <div className="benefit-panel">
            <div className="benefit-icon">⬡</div>
            <h3 className="benefit-h3">No more misaligned budgets</h3>
            <p className="benefit-desc">
              The biggest time drain isn&apos;t machining — it&apos;s quoting jobs where the
              buyer&apos;s budget was never close. Facet shows designers what drives cost
              before they ever submit a job.{" "}
              <strong>By the time it reaches you, price expectations are already calibrated.</strong>
            </p>
          </div>
          <div className="benefit-panel">
            <div className="benefit-icon">◈</div>
            <h3 className="benefit-h3">Jobs matched to your machine</h3>
            <p className="benefit-desc">
              We don&apos;t send you everything and hope something sticks.
              Jobs are filtered to your equipment, materials, and capacity preferences.{" "}
              <strong>You see requests your shop can actually win.</strong>
            </p>
          </div>
          <div className="benefit-panel">
            <div className="benefit-icon">◇</div>
            <h3 className="benefit-h3">You decide what to take</h3>
            <p className="benefit-desc">
              No commitments, no exclusivity, no pressure to fill slots.
              Review each job on your own terms —{" "}
              <strong>accept what makes sense, pass on what doesn&apos;t.</strong>{" "}
              Your capacity, your call.
            </p>
          </div>
          <div className="benefit-panel">
            <div className="benefit-icon">◯</div>
            <h3 className="benefit-h3">Shape how this gets built</h3>
            <p className="benefit-desc">
              We&apos;re early and intentionally small. Every shop that joins in
              this phase has a direct line to what we build next —{" "}
              <strong>your feedback drives the product roadmap.</strong>
            </p>
          </div>
        </section>

        <section className="signup-section" aria-label="Supplier signup" id="signup">
          <div>
            <h2 className="signup-h2">
              Ready to<br />
              <em>get started?</em>
            </h2>
            <p className="signup-sub">
              We&apos;re onboarding Northeast shops now. Tell us about your setup
              and we&apos;ll be in touch directly — no sales call required.
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
        <div className="footer-wordmark">Fac<span>et</span></div>
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

