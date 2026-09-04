# TRIZ Worker Innovation Research v2.4.0

## Engineering Report & Figure Upgrade

v2.4.0 strengthens the final-report layer without changing the classic 39×39 matrix, G0–G5 workflow, evidence labels, maturity scale, Deep Research protocol or engineering safety gates.

### What changed

- Added a single authoritative Engineering Figure Planning reference with nine figure types (F1–F9).
- Core physical or dynamic concepts now require a mechanism section and a 3–6 frame motion sequence. Safety risks require a separate safety-boundary figure; multi-step work requires an operation figure.
- Architecture diagrams can no longer stand in for mechanical mechanism figures.
- Figure Plans now record the decision question, main message, confirmed/hypothetical/unknown elements, motion, force or energy paths, protected objects, hazards, barriers, evidence, maturity and claim limits.
- The report blueprint puts the recommended mechanism on the first summary page and moves detailed audit material to appendices.
- The deterministic DOCX fallback now carries figure type, V0–V3 status, a plain-language takeaway and one-line evidence boundary.

### Validation added

- Deliverable manifest schema 1.1.
- SVG width/height/viewBox/title/description and required-label checks.
- Minimum font-size and box-only mechanical-diagram warnings.
- Figure numbering, motion-frame count and main-report caption checks.
- Engineer-view, first-time-reader, figure/text consistency and black-and-white legibility review evidence.
- Negative regression cases for architecture-only output, missing motion/safety figures, missing labels, reversed numbering and unreadable text.

### Compatibility and boundaries

The package remains standalone and standard-library-first. Python, Node and row-shard matrix lookup paths are unchanged. A host without diagram or document rendering capability must provide real capability evidence and mark the delivery as degraded; it must not claim that visual QA was completed.
