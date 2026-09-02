# TRIZ Worker Innovation Research v2.3.0

v2.3.0 closes a delivery gap found in an ordinary-model regression: a model could finish the research text, declare G5 complete, and create figures or Word files only after an extra user request.

## What changed

- G5 now begins with an observable capability probe for file writing, diagrams, DOCX creation and rendering.
- Standard and engineering runs must proactively generate required figures and a DOCX whenever those capabilities are available.
- A machine-readable delivery manifest records actual files, figure coverage, reproducible query counts, stable source identifiers, score maturity and page-review evidence.
- `validate_deliverables.py` validates generated research packages; `validate_skill.py` remains the package validator.
- A dependency-free Python DOCX builder and reusable JSON/SVG templates provide a portable fallback for ordinary agents.
- Scoring, V2/V3 boundaries, measurement-method matching and patent citation-chain rules are stricter.

## Important boundary

The Skill still does not claim that a generated concept is field-ready, patentable or safe without the required measurements, approvals and professional review. A platform that genuinely cannot create or render DOCX may deliver complete Markdown and figures, but the manifest must label that result `degraded` rather than `complete`.

## Validate

```bash
python triz-worker-innovation-research/scripts/validate_skill.py --strict
python triz-worker-innovation-research/scripts/build_report.py --self-test
python triz-worker-innovation-research/scripts/validate_deliverables.py --self-test
```
