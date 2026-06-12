# Facet — Reflection

*A supplier-side DFM and quoting tool, built as the entry point to a two-sided sourcing marketplace. Built end-to-end, tested on 50+ parts and with 2 machine shops. It did not reach traction. This is an honest account of why.*

---

## The outcome, stated plainly

I built a working geometry-analysis engine and report. The engineering worked — it does what it claims on real parts. The business did not reach traction. Those are independent facts, and the failure was on the demand and distribution side, not the code. Everything below is about why the demand side stalled and what I'd do differently.

---

## Where the idea came from

The idea came from a structural problem I saw firsthand in precision-equipment manufacturing. IP-heavy OEMs build large, complex assemblies with exotic materials and tight features, and tend to source each submodule from a single trusted supplier. That dependence carries real risk:

- **Price capture** — a sole supplier can charge more, with no competitive tension.
- **No production learning loop** — a third party does the manufacturing, so the design team can't iterate on what it would learn from actually making the part until something fails in the field.
- **Single point of failure** — if the supplier has a quality or capacity problem, production stops.
- **Slow, lossy communication** — quoting times, time zones, language barriers, and misaligned incentives between vendor and designer make information transfer hard.

OEMs avoid multi-sourcing anyway, because onboarding a new supplier is slow and expensive, they don't want to destabilize trusted relationships they've invested in, and every new supplier is another IP exposure. So the pain is real *and* the obvious fix — just use more suppliers — is structurally blocked. That gap is what Facet was meant to fill.

---

## The idea

Facet started as a two-sided marketplace where an IP-heavy design firm could get competitive bids from multiple vetted suppliers without exposing its IP. The platform reads the part geometry and abstracts it into a manufacturability profile — what processes, features, tolerances, and special requirements the part needs to be made — without revealing design intent. Suppliers bid on the profile. It does the work of the sourcing team while creating competitive tension and removing the lossy back-and-forth between engineers, sourcing, sales reps, and machinists where parts go out of spec.

The core insight — that you can describe *what a part requires to manufacture* without exposing *how it was designed* — is the part I still believe in.

---

## GTM, pivots, and the problems each surfaced

**Three problems were visible from the start:** acquiring both suppliers and designers (two-sided cold start), disintermediation and monetization (once a designer finds suppliers through us, what stops them transacting off-platform, and how do we keep getting paid), and the difficulty of the tech itself.

**First attempt — be the sourcing agent.** Aggregate several design firms, find suppliers for them, and earn trust by delivering good suppliers. This ran straight into the cold-start problem (no suppliers yet) and, more importantly, into deep distrust from the design firms. They would not route sourcing of mission-critical, IP-loaded parts through an unknown two-person team. Suppliers, by contrast, were willing to talk about their problems.

**Pivot — supplier quoting tool.** Since suppliers would engage, build a tool they'd want, accumulate a supplier network and a map of their capabilities, then evolve into the marketplace from the supply side. We built the analysis tool: setups, tool changes, complex geometry, tight tolerances, hole inventory, DFM flags.

**The problem that surfaced.** What we'd built was a substitute for a machinist's years of experience. The shops we talked to mostly don't have a streamlined quoting procedure — they do the checks our software does in their heads, fast, and trust their own judgment. Their real bottleneck in quoting is *administrative*, not technical, and they price by feel. So the tool gave suppliers little value: the best it could do was organize what they already knew and auto-calculate a price they'd rather set by instinct. I realized the tool was primarily valuable to *designers* — to understand the cost drivers in their own designs — not to the suppliers I'd pivoted toward. I'd pivoted away from the side I understand best.

**The detour.** Instead of pivoting the *customer* back to designers, I went after a hard technical feature: reading engineering drawings, extracting tolerances and GD&T, and mapping them to the STEP file. It was genuinely powerful and reusable (it feeds my tolerance-stack tool and other use cases), but it was an engineering answer to what was really a demand problem. It's also still experimental — I haven't proven the hard stage, mapping a drawing callout to the correct STEP face, at scale.

---

## Why it stalled

"A bit of everything" is true but not useful. Here's the weighting.

1. **I solved the interesting problem, not the blocking one.** The blocker was always demand and distribution. I spent the effort on geometry reasoning because it was tractable and I'm good at it. Every increment of geometric accuracy had near-zero effect on adoption, because adoption was blocked one layer up. This is the pattern across my work — I find the hardest tractable technical problem and solve it cleanly — and in a company context that instinct is a trap.

2. **I targeted the user who felt the pain least.** The supplier tool competed with the estimator's judgment, which is the shop's competitive asset, and addressed their non-bottleneck (technical) instead of their real one (administrative). A tool that tells experts what they already know gets ignored.

3. **The pain and the unsellability are the same coin.** The properties that make buyer-side pain acute — IP paranoia, supply-chain risk-aversion, regulatory weight — are exactly what make those buyers nearly impossible for a two-person unknown to sell. The designer distrust wasn't an execution miss; I picked the most defensive buyer in the economy as a first customer.

4. **The structural marketplace problems were never answered.** Two-sided cold start and disintermediation are hard, and I deferred them rather than solving them. I still don't have a clean answer to "what stops the designer taking the supplier off-platform once we've introduced them."

5. **GTM was the hardest possible motion, and under-invested.** A two-person team, one of us technical, doing cold outreach to a non-software-buying customer culture, with long trust cycles. I put my hours into the build instead.

**The honest caveat:** this experiment was underpowered. Two shops, part-time, over a short window cannot cleanly separate "the idea is bad" from "the GTM was wrong" from "it needed more at-bats." The defensible conclusion is narrow — *this product, this user, this motion didn't pull in this small sample* — not that the underlying idea is dead.

---

## Direction I'd take it

I still believe in the marketplace as the north star. What I'd change is the path to it.

**Lead with a designer-facing DFM + cost-driver tool.** DFM is a real bottleneck on the design side: parts get designed in cost-suboptimal ways that force harder specs, cause field issues, and cost money — and there's no tool that optimizes a design *for cost*. The closest thing in practice is rough Excel estimators. I'm the user for this, which is an unfair advantage: I'm a design engineer in exactly this domain, which makes both dogfooding and demand validation cheap.

One precise distinction: build the **relative** cost tool, not the **absolute** one. An absolute dollar estimate is a data problem nobody has solved — cost depends on machine rates, material, volume, region, and overhead, there's no public dataset, and shops price by feel. A relative tool — "this tolerance adds a setup," "this pocket forces a ball-nose and more cycle time," "loosening this saves roughly this much" — is tractable, plays to the geometry strength, and is exactly the kind of argument that justifies loosening an over-tight tolerance: showing that a spec costs real money the function doesn't need. The value is a defensible number on a specific tradeoff at design time: justification ammunition, not DFM education.

**Treat drawing-to-STEP mapping as the reusable keystone — but validate it before building a product around it.** Extracting all manufacturing information at the STEP-plus-drawing level is CAD-agnostic: it sidesteps the kernel and file-format fragmentation that plagues CAD tooling, so it works regardless of source CAD. That's a real moat candidate. The tradeoff is that STEP-level extraction is harder than reading a native feature tree (you reverse-engineer features from B-rep), and the hard mapping stage is still unproven. So it's the next *experiment*, not the next product.

**The route back to the marketplace.** The designer tool is a tool→network wedge: land with something an engineer uses solo, expand into sourcing. The alternative wedge worth weighing is a supplier qualification/compliance system — tracking suppliers through prototype, certification, compliance, first article, and volume. That one fits my own evidence better than the quoting tool did: suppliers' real bottleneck is administrative, this is an administrative system, it's stickier than point analysis, it builds the supplier-capability and outcome data the marketplace needs, and owning the compliance spine is the natural disintermediation defense in regulated manufacturing. The honest counter is that it's enterprise workflow software, further from my strength, and I don't want to build another CRM — a valid founder-fit filter, but I have to admit it's also pushing me toward the work I enjoy.

**The discipline either way:** gauge demand before building. I'm positioned to do this without writing code — take one real part, do the cost-driver analysis by hand, put it in front of colleagues, and watch whether the number changes a design decision. If it doesn't move behavior, I've learned that for free.

---

## Lessons learned

- **Solve the blocking problem, not the interesting one.** My strength — finding and cleanly solving the hardest tractable technical problem — is also my failure mode in a company. The discipline is to keep asking which problem is actually blocking the business, and to notice when I've drifted to the one that's more fun.

- **Technical dependency is not commercial sequencing.** The marketplace needs the geometry engine, but "we'll need it eventually" is not a reason to *sell* it first. Build order and validation order are different questions.

- **Building a good tool is not the same as finding the right product to sell.** I focused on the tech — on making the engine strong — instead of on finding the right product: who the customer was and whether they'd actually pay. The work that mattered most, validating demand and choosing what to build, got the least of my time.

- **Validate demand before building, especially when you can do it cheaply.** Being an insider at the target customer is leverage I didn't use. I built instead of asking.

- **Relative value beats absolute precision when the data doesn't exist.** Don't promise a number you can't ground; deliver the comparison that's both useful and buildable.

- **Pick a first customer you can actually reach.** The most IP-sensitive, risk-averse buyer feels the pain most and is the hardest first sale. Acuteness of pain and ease of selling can be inversely correlated.

- **Be honest about the learning-vehicle tradeoff.** I treated Facet partly as a way to learn hard tech, and that choice cost me commercially — I built the wrong product as a result. The upside is real and transferable: the geometry engine, the tolerance-stack tool, and the drawing-mapping work all came out of it. Owning that tradeoff is more credible than pretending it was a pure commercial swing.
