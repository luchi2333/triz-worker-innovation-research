# TRIZ Worker Innovation Research

**An engineering-research Agent Skill for tool, equipment, maintenance and process innovation**

[简体中文](README.md) · [Quick start](#quick-start) · [Teaching example](#from-a-field-description-to-an-inspectable-study) · [Workflow](#how-the-research-progresses) · [Contributing](CONTRIBUTING.md)

[![Release](https://img.shields.io/github/v/release/luchi2333/triz-worker-innovation-research?label=release)](https://github.com/luchi2333/triz-worker-innovation-research/releases)
[![Validation](https://github.com/luchi2333/triz-worker-innovation-research/actions/workflows/validate.yml/badge.svg)](https://github.com/luchi2333/triz-worker-innovation-research/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a085.svg)](LICENSE)

Turn a field problem into traceable, falsifiable and testable engineering research. Reconstruct the process, system boundary and constraints first; then use TRIZ analysis, deterministic matrix lookup and technical research to develop concepts, FMEA, decisive experiments and a technical report.

![TRIZ Worker Innovation Research for tool, equipment, maintenance and process innovation. Concept illustration of a tube-clamping teaching example. The 10×12 lookup returns Preliminary action, Parameter changes, Composite materials, and Discarding and recovering in that order.](assets/readme/hero-en.png)

## From a field description to an inspectable study

This **fully fictional thin-wall tube teaching example** shows how the research chain unfolds. See [examples/thin-wall-tube-clamping.md](examples/thin-wall-tube-clamping.md) for the complete walkthrough.

> A training workshop clamps thin-wall copper tube in a bench vise for sawing. The tube often becomes oval. The grip must become more stable without increasing deformation.

The Skill first organizes the description into a problem model and separates evidence states with `F/M/S/H`:

| Label | Meaning | In this example |
|---|---|---|
| `F` | Field-reported fact | The object, process and report that clamping causes ovality |
| `M` | Controlled measurement | Tube diameter, wall thickness, clamping force and scrap rate; unknown values remain unmeasured |
| `S` | Traceable external source | Standards, products, patents and papers found in subsequent real research |
| `H` | Engineering hypothesis or derivation | Explanations and candidate mechanisms to test, such as uneven contact pressure |

The main contradiction maps improving **#10 Force (intensity)** to worsening **#12 Shape**, queried in the fixed **10×12** direction. The bundled classical matrix returns, in order:

1. **#10 Preliminary action** — investigate a pre-installed removable liner;
2. **#35 Parameter changes** — investigate jaw curvature, contact length and surface hardness;
3. **#40 Composite materials** — investigate a rigid support combined with a compliant surface;
4. **#34 Discarding and recovering** — investigate a replaceable wear surface.

These principles move into source verification, route comparison, risk analysis and decisive experiments rather than becoming a finalized design. The teaching example contains no real company, model, project data, external research results or measured performance.

## Quick start

Copy this instruction to Codex:

```text
Use skill-installer to install the Skill from this URL, then tell me how to start:
https://github.com/luchi2333/triz-worker-innovation-research/tree/main/triz-worker-innovation-research
```

Then describe the field problem:

```text
Use $triz-worker-innovation-research to investigate this engineering innovation problem:
Current process: ...
Main difficulty: ...
Desired improvement: ...
Must not sacrifice: ...
```

No prior TRIZ knowledge or separate matrix or Deep Research Skill is required. Live product, patent, standards and literature research still requires the host Agent to have Web/Search access.

After the first complete TRIZ draft, the Skill pauses at `G1.5` to confirm the research direction. You can correct facts and boundaries, retain, pause or add directions. Existing explicit delegation is recorded with its scope; silence is not approval.

## How the research progresses

```text
G0 Problem Definition → G1 System & TRIZ Modeling → G1.5 USER CONFIRMATION
                      → G2 Deep Research → G3 Concepts
                      → G4 Validation / Safety / Benefits → G5 Report
```

| Stage | What you receive |
|---|---|
| Problem and contradiction | Original identifiers and terminology, complete process, system boundary, constraints and an `F/M/S/H` problem model |
| Deterministic analysis | 39 engineering parameters, 40 inventive principles and the classical 39×39 matrix, with Python, Node and readable row-shard lookup paths |
| Deep research | Products, patents, standards, papers, manufacturer documentation, cross-industry analogies and counter-evidence, with reproducible search logs |
| Candidate decisions | A mature baseline, engineering fallback, exploratory route and supersystem alternative, with action chains, sources, risks and exit conditions |
| Validation and benefits | FMEA, samples and metrics, acceptance/stop criteria, V0–V3 maturity, and reproducible economic and social benefit models |
| Formal delivery | Decision summary, engineering figures, main report, technical evidence appendix, research ledger, DOCX and delivery manifest |

Key facts live in `research-record.json`. Summaries, prose, parameters, calculations and figures read from the same source of truth. G5 plans the figure set before drawing and selects mechanical, electrical/measurement, control/software, thermal/fluid or process representations as appropriate. Structure, computational consistency and engineering review are reported separately.

## Why not ask AI to brainstorm directly?

A normal AI conversation can jump from a short field description to plausible-looking concepts while leaving the system boundary, matrix source, applicability checks and validation conditions unexamined. This Skill connects those steps:

| Prompt or matrix lookup tool | This Skill |
|---|---|
| Returns principles or brainstormed ideas | Reconstructs the process, root cause, system boundary and constraints first |
| May answer a matrix cell from model memory | Uses bundled JSON, Python, Node or 39 human-readable row shards for reproducible lookup |
| Treats retrieved pages as conclusions | Records search strings and verifies identity, applicability and counter-evidence |
| Optimizes one proposed concept | Compares a mature baseline, low-risk fallback, exploration route and supersystem alternative |
| Stops after concept generation | Continues with FMEA, decisive experiments, stop criteria and evidence maturity |
| Declares success after Markdown | Produces required figures and DOCX, then validates a delivery manifest |

## Installation, portability and local validation

### OpenAI Codex

Use the Quick Start above, or invoke the bundled installer directly:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo luchi2333/triz-worker-innovation-research \
  --path triz-worker-innovation-research
```

Windows PowerShell:

```powershell
python "$env:USERPROFILE\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py" `
  --repo luchi2333/triz-worker-innovation-research `
  --path triz-worker-innovation-research
```

### Claude Code and other Agent platforms

Copy the complete `triz-worker-innovation-research/` folder into the platform's Skill directory and load `SKILL.md` as the entrypoint. On a platform without a Skill mechanism, use it as top-level task context and follow its resource routing into `references/`. This describes the intended adaptation path, not a blanket compatibility claim. Submit real results through the [Compatibility Report](https://github.com/luchi2333/triz-worker-innovation-research/issues/new?template=compatibility_report.md).

### Local validation

```bash
python triz-worker-innovation-research/scripts/validate_skill.py --strict
node triz-worker-innovation-research/scripts/lookup_matrix.mjs --self-test
python triz-worker-innovation-research/scripts/build_report.py --self-test
python triz-worker-innovation-research/scripts/validate_deliverables.py --self-test
```

Strict validation covers the release manifest, version, matrix hash, golden cells, 39 row shards, README example, Python/Node parity, and self-tests for the DOCX builder and deliverable validator.

After a real research run, copy and complete `triz-worker-innovation-research/assets/research-record-template.json`, copy the deliverables manifest template, then run:

```bash
python triz-worker-innovation-research/scripts/validate_deliverables.py \
  --root <research-output-directory> \
  --manifest <research-output-directory>/deliverables-manifest.json \
  --strict
```

## Research, validation and field responsibilities

The Skill keeps evidence origins clear with `F/M/S/H`: field benefits rely on `M` controlled measurements, while product parameters and cross-industry mechanisms go through target-fit and feasibility checks. Patentability and FTO questions belong to the appropriate legal review process. Structure, computational consistency and engineering-content review are reported separately; users and field engineers retain validation, approval and final safety decisions. A research commission covers analysis and reporting, with field implementation confirmed separately.

## Documentation and repository map

```text
.
├── README.md / README_EN.md       # Chinese and English homepages
├── examples/                      # Fully fictional, de-identified workflow examples
├── assets/readme/                 # Homepage images and editable sources
├── triz-worker-innovation-research/
│   ├── SKILL.md                   # Skill entrypoint and execution contract
│   ├── references/                # Workflow, matrix, research, templates and delivery gates
│   ├── scripts/                   # Lookup, DOCX, deliverable and skill validation
│   └── assets/                    # Research record, report source and SVG templates
└── docs/                          # Upgrade notes and release material
```

- [Complete fictional teaching example](examples/thin-wall-tube-clamping.md)
- [CHANGELOG and migration history](triz-worker-innovation-research/CHANGELOG.md): current development changes appear under `Unreleased`, separate from published releases.
- [Contributing guide](CONTRIBUTING.md): report matrix or script errors, installation issues and compatibility results, or contribute public, de-identified test problems.
- [Update and rollback](triz-worker-innovation-research/references/skill-update.md): run `python scripts/update_skill.py --check` in the installed Skill directory. Before `--apply`, verify the release package, per-file hashes and backup. Stable Releases are the default; use `--channel main` explicitly for the development branch.

## License and attribution

Original code, workflows, templates and explanatory text are released under the [MIT License](LICENSE). Classical TRIZ concepts, parameters, inventive principles and the matrix remain attributed to their original authors and rights holders. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for sources and redistribution notices.
