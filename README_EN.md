# TRIZ Worker Innovation Research

**Evidence-based Engineering Innovation Agent Skill**

[简体中文](README.md) · [Install](#quick-start) · [Demo](#from-one-field-problem-to-an-auditable-research-package) · [Contributing](CONTRIBUTING.md)

[![Release](https://img.shields.io/github/v/release/luchi2333/triz-worker-innovation-research?label=release)](https://github.com/luchi2333/triz-worker-innovation-research/releases)
[![Validation](https://github.com/luchi2333/triz-worker-innovation-research/actions/workflows/validate.yml/badge.svg)](https://github.com/luchi2333/triz-worker-innovation-research/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a085.svg)](LICENSE)

> **Not a prompt that generates more ideas. A reproducible workflow that turns a field problem into evidence-backed, falsifiable and testable engineering concepts.**

**Problem framing → TRIZ contradictions → deterministic 39×39 matrix → Deep Research → engineering concepts → risk/FMEA → validation → benefits → technical report**

![TRIZ Worker Innovation Research: from field problem to testable engineering concept](assets/triz-worker-innovation-research-hero-v3.png)

Built for tool improvement, equipment optimization, maintenance processes and frontline Engineering Innovation. OpenAI Codex has a documented installation path. The package also uses a portable `SKILL.md` structure that can be adapted by Agent platforms able to load Skill folders or persistent task context.

## v2.6: linked field records and illustrated reports

Stable IDs connect raw inputs, requirements, mechanisms, parameters and tests. Bound Word text, tables and SVG/PNG diagrams share one record; checks detect changed document content and stale figures after parameter edits. A fully hypothetical tutorial produces DOCX, editable SVG and a step-by-step HTML explainer using the standard library, with optional Chromium PNG rendering. See [upgrade and migration notes](docs/v2.6-upgrade.md).

```bash
cd triz-worker-innovation-research
python scripts/run_tutorial.py --output tutorial-output
```

The preliminary design is a two-dimensional concept, not a manufacturing release or an automatic CAD/STEP export.

## Quick Start

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

No separate contradiction-matrix or Deep Research Skill is required. Live Product Research, Patent Research, Standards Research and literature research still require the host Agent to have Web/Search access.

## Why this Skill?

A normal AI conversation can jump from a short problem statement directly to attractive concepts. This project makes the Engineering Research chain inspectable:

```text
field facts → process and system boundary → TRIZ model → deterministic matrix
            → user confirmation → technical research → concepts → counter-evidence
            → safety/FMEA → decisive experiment → report
```

| Prompt or matrix lookup tool | This Skill |
|---|---|
| Returns principles or brainstormed ideas | Reconstructs the process, root cause, system boundary and constraints first |
| May answer a matrix cell from model memory | Uses bundled JSON, Python, Node or human-readable row shards |
| Treats retrieved pages as conclusions | Records search strings and verifies identity, source quality and applicability |
| Optimizes one proposed concept | Preserves a mature baseline, low-risk fallback, exploration route and supersystem alternative |
| Stops after concept generation | Adds FMEA, acceptance/stop criteria, decisive experiments and claim limits |
| Declares success after Markdown | Probes capabilities, generates required figures and DOCX, then validates a delivery manifest |

The goal is not more prose. The goal is traceable Inventive Problem Solving and testable Engineering Design.

## From one field problem to an auditable research package

This is a **fully fictional training example**. It contains no company, site, product model, unpublished data or measured performance. See [examples/thin-wall-tube-clamping.md](examples/thin-wall-tube-clamping.md) for the full walkthrough.

> A training workshop clamps thin-wall copper tube in a bench vise for sawing. The tube often becomes oval and needs rework or is scrapped. The grip must become more stable without increasing deformation.

1. **Evidence-labelled problem model.** Field reports are tagged `F`; controlled measurements `M`; traceable external sources `S`; engineering hypotheses `H`.
2. **TRIZ model.** The main contradiction is mapped as improving **#10 Force (intensity)** while worsening **#12 Shape**, queried in the fixed **10×12** direction.
3. **Deterministic matrix result.** The bundled classical matrix returns principles **#10 Preliminary action, #35 Parameter changes, #40 Composite materials, #34 Discarding and recovering**.
4. **Mechanisms, not principle names.** Candidate mechanisms include a pre-installed sacrificial liner, a contact-profile change, a rigid-support/soft-surface composite, and a replaceable wear insert.
5. **Human confirmation.** At `G1.5`, record the user's direction choice or existing explicit delegation. Wait when authorization is missing; do not request the same confirmation twice.
6. **Research and synthesis.** Products, patents, standards, papers, manufacturer documents, cross-industry analogies and negative evidence are tied to explicit claims.
7. **Decision package.** Concepts are compared with risks, FMEA, decisive experiments, benefit scenarios and a formal technical report.

This demo illustrates the workflow. It does not claim field performance, patentability or deployability.

## What You Get

| Deliverable | Purpose |
|---|---|
| Problem model | Preserves raw identifiers, labels `F/M/S/H`, and freezes process boundaries and hard constraints |
| TRIZ analysis | Cause/function analysis, IFR, resources, technical and physical contradictions, substance-field and evolution directions |
| Deterministic matrix record | Improving parameter as row, worsening parameter as column, with reproducible lookup evidence |
| Deep Research evidence pack | Products, patents, standards, papers, manufacturer documents, analogies and negative evidence |
| Concept decision table | For every route: method, problem addressed, mechanism, source, novelty boundary, risk and test |
| Validation and FMEA | Sample, metric, acceptance/stop criteria, decisive experiment and V0–V3 maturity |
| Benefit model | Separates field reports, controlled measurements and scenario assumptions |
| Technical report | Figure Plan first, then structure/motion/action/safety figures, decision summary, main report, evidence appendix, ledger, DOCX and an inspectable manifest |

## Human-in-the-loop by Design

```text
G0 Problem Definition → G1 TRIZ Modeling → G1.5 USER CONFIRMATION
                      → G2 Deep Research → G3 Concepts
                      → G4 Validation/Safety/Benefits → G5 Report
```

After the first complete direction draft, the user can correct boundaries, mappings and research priorities. Record existing explicit delegation and continue within its scope; otherwise wait for the direction choice. Silence is not approval, and research delegation does not authorize field implementation.

## Reliability by construction

- **Deterministic contradiction matrix:** 39 parameters, 40 inventive principles, a classical 39×39 matrix and 1,248 populated cells; Python, Node and readable row shards can be cross-checked.
- **Claim-level evidence:** conclusions remain attached to field facts, measurements, traceable sources or hypotheses; search logs retain raw queries and inclusion/exclusion decisions.
- **Applicability and counter-evidence:** similar products are not treated as target fit, cross-industry analogies are not treated as proven feasibility, and “not found” is not expanded into “does not exist.”
- **Hard gates before scoring:** failures in identity, evidence, applicability, transfer, safety, patent scope or validation reduce downstream maturity.
- **Execution support for ordinary models:** a state machine, decision trees, fill-in templates and stage checks reduce omission and improvisation.
- **Artifacts are not an afterthought:** G5 probes diagram, DOCX and rendering capabilities first. Available capabilities must be used; real blockers produce an explicit degraded delivery.
- **Engineering figures are planned before drawing:** nine figure types answer different questions; dynamic mechanisms use 3–6 frames, safety boundaries are separate, and architecture diagrams cannot stand in for mechanical mechanism figures.
- **Generated work is machine-checkable:** `validate_deliverables.py` checks required figure types, SVG/PNG pairs, labels, numbering, minimum font size, figure-text consistency, query logs, score maturity, DOCX media/links and page-review evidence.

## Installation and portability

### OpenAI Codex

The one-line instruction above is recommended. The bundled installer can also be invoked directly:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo luchi2333/triz-worker-innovation-research \
  --path triz-worker-innovation-research
```

### Claude Code and other Agent platforms

Copy the complete `triz-worker-innovation-research/` folder into the platform's Skill directory and load `SKILL.md` as the entrypoint. On a platform without a Skill mechanism, load `SKILL.md` as top-level task context and follow its resource routing into `references/`.

This describes the intended adaptation path, not a blanket compatibility claim. Platform versions, permission systems and tool interfaces differ. Please submit real results through the [Compatibility Report](https://github.com/luchi2333/triz-worker-innovation-research/issues/new?template=compatibility_report.md).

## Validation

```bash
python triz-worker-innovation-research/scripts/validate_skill.py --strict
node triz-worker-innovation-research/scripts/lookup_matrix.mjs --self-test
python triz-worker-innovation-research/scripts/build_report.py --self-test
python triz-worker-innovation-research/scripts/validate_deliverables.py --self-test
```

Strict validation covers the release manifest, version, matrix hash, golden cells, 39 row shards, the README example, 18 Python/Node parity cases, the DOCX builder and the generated-deliverable validator. Deliverable schema 1.2 reads `research-record.json` and verifies actual query/source/score counts, resolvable evidence IDs, end-to-end route coverage, domain-appropriate figures, effective font size, actual DOCX caption order, hashes and page-level review evidence. After a real research run, copy and fill `assets/research-record-template.json`, then copy the deliverables manifest template and run:

```bash
python triz-worker-innovation-research/scripts/validate_deliverables.py \
  --root <research-output-directory> \
  --manifest <research-output-directory>/deliverables-manifest.json \
  --strict
```

## What this Skill does not claim

This is an **AI-assisted engineering research workflow**, not an automatic invention generator. It does not:

- treat model output as controlled measurement;
- claim efficiency, zero damage or field benefit without `M` evidence;
- treat a similar product as proof of target applicability;
- treat a cross-industry analogy as demonstrated feasibility;
- provide patentability or freedom-to-operate legal opinions;
- claim deployment readiness without validation and approval;
- replace the engineer's final safety decision.

## Roadmap

- [x] Classical 39×39 matrix with three deterministic lookup paths
- [x] G0–G5 workflow with a G1.5 user confirmation gate
- [x] Deep Research, evidence labels, validation and FMEA
- [x] Python/Node parity regression and GitHub Actions
- [x] Bilingual project pages, a public fictional demo and community templates
- [x] Engineering Figure Planning, motion sequences, safety boundaries and deterministic figure-contract validation
- [ ] More public, de-identified engineering examples
- [ ] Tested compatibility records for more Agent platforms
- [ ] A community-contributed regression problem set

## Contributing and license

Bug reports, matrix corrections, installation feedback, compatibility reports, documentation improvements and fully public fictional examples are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting any field material.

Original code, workflows, templates and explanatory text are released under the [MIT License](LICENSE). Classical TRIZ concepts remain attributed to their original authors and rights holders; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
