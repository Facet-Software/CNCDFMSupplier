"use client";

import { useState, useEffect } from "react";

interface WaitlistModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultRole?: "designer" | "shop";
}

export default function WaitlistModal({ isOpen, onClose, defaultRole = "designer" }: WaitlistModalProps) {
  const [role, setRole] = useState<"designer" | "shop">(defaultRole);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  // Sync role if defaultRole changes (e.g. opening from different pages)
  useEffect(() => {
    setRole(defaultRole);
  }, [defaultRole, isOpen]);

  // Reset form when modal closes
  useEffect(() => {
    if (!isOpen) {
      setTimeout(() => {
        setSubmitted(false);
        setEmail("");
        setName("");
        setCompany("");
        setLocation("");
      }, 300);
    }
  }, [isOpen]);

  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setLoading(true);
    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, name, company, location, role }),
      });
      if (!res.ok) throw new Error("Failed");
      setSubmitted(true);
    } catch {
      // Still show success to user — don't block on backend errors
      setSubmitted(true);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <>
      <style>{`
        .wl-overlay {
          position: fixed;
          inset: 0;
          background: rgba(4,4,4,0.85);
          backdrop-filter: blur(8px);
          z-index: 500;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 24px;
          animation: wlFadeIn 0.2s ease both;
        }

        .wl-modal {
          background: #111111;
          border: 1px solid #2a2a2a;
          width: 100%;
          max-width: 540px;
          position: relative;
          animation: wlSlideUp 0.25s ease both;
        }

        .wl-header {
          padding: 32px 36px 24px;
          border-bottom: 1px solid #1e1e1e;
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 16px;
        }

        .wl-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: 32px;
          font-weight: 300;
          color: #F5F0EB;
          line-height: 1.05;
        }
        .wl-title em { font-style: italic; color: #C4913A; }

        .wl-close {
          background: none;
          border: none;
          color: #686868;
          font-size: 20px;
          cursor: pointer;
          line-height: 1;
          padding: 4px;
          transition: color 0.2s;
          flex-shrink: 0;
          margin-top: 4px;
        }
        .wl-close:hover { color: #F5F0EB; }

        .wl-body { padding: 28px 36px 36px; }

        .wl-sub {
          font-family: 'DM Mono', monospace;
          font-size: 12px;
          color: #686868;
          line-height: 1.7;
          margin-bottom: 24px;
        }

        .wl-toggle {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1px;
          background: #2a2a2a;
          margin-bottom: 12px;
        }

        .wl-role-btn {
          padding: 12px 16px;
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          background: #141414;
          color: #686868;
          border: none;
          cursor: pointer;
          transition: background 0.2s, color 0.2s;
          text-align: center;
        }
        .wl-role-btn.active { background: #C4913A; color: #080808; font-weight: 500; }
        .wl-role-btn:not(.active):hover { background: #1b1b1b; color: #F5F0EB; }

        .wl-role-hint {
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          color: #686868;
          margin-bottom: 20px;
          min-height: 16px;
          line-height: 1.6;
        }

        .wl-field { margin-bottom: 12px; }
        .wl-field-row {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
          margin-bottom: 12px;
        }

        .wl-label {
          display: block;
          font-family: 'DM Mono', monospace;
          font-size: 10px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: #686868;
          margin-bottom: 7px;
        }

        .wl-input {
          width: 100%;
          padding: 12px 14px;
          background: #0e0e0e;
          border: 1px solid #232323;
          color: #F5F0EB;
          font-family: 'DM Mono', monospace;
          font-size: 12px;
          font-weight: 300;
          letter-spacing: 0.04em;
          outline: none;
          transition: border-color 0.2s;
        }
        .wl-input::placeholder { color: #4a4a4a; }
        .wl-input:focus { border-color: #7A5820; }

        .wl-submit {
          width: 100%;
          padding: 14px;
          background: #C4913A;
          border: none;
          color: #080808;
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          font-weight: 500;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          cursor: pointer;
          transition: background 0.2s;
          margin-top: 8px;
        }
        .wl-submit:hover { background: #D4A050; }
        .wl-submit:disabled { opacity: 0.6; cursor: not-allowed; }

        .wl-note {
          font-family: 'DM Mono', monospace;
          font-size: 11px;
          color: #686868;
          margin-top: 12px;
          text-align: center;
          line-height: 1.6;
        }

        .wl-success {
          text-align: center;
          padding: 16px 0 8px;
        }
        .wl-success-icon { font-size: 28px; color: #C4913A; margin-bottom: 14px; }
        .wl-success-title {
          font-family: 'Cormorant Garamond', serif;
          font-size: 30px;
          font-weight: 300;
          color: #F5F0EB;
          margin-bottom: 10px;
        }
        .wl-success-sub {
          font-family: 'DM Mono', monospace;
          font-size: 12px;
          color: #686868;
          line-height: 1.75;
          max-width: 340px;
          margin: 0 auto;
        }

        @keyframes wlFadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        @keyframes wlSlideUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 540px) {
          .wl-header { padding: 24px 24px 20px; }
          .wl-body { padding: 24px 24px 28px; }
          .wl-field-row { grid-template-columns: 1fr; }
          .wl-title { font-size: 26px; }
        }
      `}</style>

      {/* Overlay — click outside to close */}
      <div className="wl-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }} role="dialog" aria-modal="true" aria-label="Join Facet">
        <div className="wl-modal">
          <div className="wl-header">
            <div className="wl-title">
              Join<br /><em>Facet.</em>
            </div>
            <button className="wl-close" onClick={onClose} aria-label="Close">✕</button>
          </div>

          <div className="wl-body">
            {!submitted ? (
              <>
                <p className="wl-sub">
                  Tell us which side you're on and we'll be in touch.
                </p>

                <div className="wl-toggle" role="group" aria-label="Select your role">
                  <button
                    className={`wl-role-btn ${role === "designer" ? "active" : ""}`}
                    onClick={() => setRole("designer")}
                    type="button"
                  >
                    I need parts made
                  </button>
                  <button
                    className={`wl-role-btn ${role === "shop" ? "active" : ""}`}
                    onClick={() => setRole("shop")}
                    type="button"
                  >
                    I run a shop
                  </button>
                </div>

                <p className="wl-role-hint">
                  {role === "designer"
                    ? "Upload your part, get competing quotes, and understand exactly what drives your price."
                    : "Receive pre-qualified job requests matched to your equipment and capacity."}
                </p>

                <form onSubmit={handleSubmit}>
                  <div className="wl-field-row">
                    <div className="wl-field">
                      <label className="wl-label">Name</label>
                      <input
                        className="wl-input"
                        type="text"
                        placeholder="Your name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        aria-label="Your name"
                      />
                    </div>
                    <div className="wl-field">
                      <label className="wl-label">
                        {role === "shop" ? "Shop name" : "Company"}
                      </label>
                      <input
                        className="wl-input"
                        type="text"
                        placeholder={role === "shop" ? "Your shop" : "Your company"}
                        value={company}
                        onChange={(e) => setCompany(e.target.value)}
                        aria-label={role === "shop" ? "Shop name" : "Company name"}
                      />
                    </div>
                  </div>

                  <div className="wl-field">
                    <label className="wl-label">Email</label>
                    <input
                      className="wl-input"
                      type="email"
                      placeholder="your@email.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      aria-label="Email address"
                    />
                  </div>

                  {role === "shop" && (
                    <div className="wl-field">
                      <label className="wl-label">Location</label>
                      <input
                        className="wl-input"
                        type="text"
                        placeholder="City, State"
                        value={location}
                        onChange={(e) => setLocation(e.target.value)}
                        aria-label="Shop location"
                      />
                    </div>
                  )}

                  <button className="wl-submit" type="submit" disabled={loading}>
                    {loading ? "Submitting..." : "Join"}
                  </button>

                  <p className="wl-note">No spam. We'll reach out when your spot is ready.</p>
                </form>
              </>
            ) : (
              <div className="wl-success">
                <div className="wl-success-icon">✦</div>
                <div className="wl-success-title">You're on the list.</div>
                <p className="wl-success-sub">
                  {role === "shop"
                    ? "We'll reach out directly — not an automated email. Expect to hear from us soon."
                    : "We'll reach out shortly — no automated sequences, just a real conversation about your first job."}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

