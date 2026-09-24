"""Shared, stdlib-only checks for evidence, route eligibility and traceable records.

These checks establish recorded consistency, never engineering approval.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import math
import re
from pathlib import Path
from engineering_checks import comparable, benefit_with_units

RECORD_SCHEMAS = {"1.0", "1.1"}
STAGES = ["G0", "G1", "G1.5", "G2", "G3", "G4", "G5"]
MATURITY = {"V0": 0, "V1": 1, "V2": 2, "V3": 3}
TRACE_COLLECTIONS = ["inputs", "problems", "requirements", "mechanisms", "parameters", "decisions", "figure_specs", "research_tracks", "hazards"]
DEEP_RESEARCH_TRACKS = {"standard_regulation", "object_structure_material", "mature_products_process", "patent", "mechanism_literature", "cross_industry_analogy", "opposition_supersystem"}
PORTFOLIO_ROLES = {"baseline", "backup", "exploratory", "supersystem"}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("requires a finite number (not bool, NaN or infinity)")
    return value


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_file(root, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("requires a local artifact path")
    base = Path(root).resolve()
    path = (base / value).resolve()
    try:
        path.relative_to(base)
    except ValueError as exc:
        raise ValueError("artifact path leaves the research directory") from exc
    if not path.is_file():
        raise ValueError(f"artifact does not exist: {value}")
    return path


def rows(record, name):
    value = record.get(name, [])
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []


def resolve_ref(record, reference):
    """JSON-pointer-like reference; array segments resolve stable IDs, not positions."""
    if not isinstance(reference, str) or not reference.startswith("/"):
        raise ValueError(f"invalid record reference: {reference}")
    node = record
    for token in reference[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            matches = [v for v in node if isinstance(v, dict) and v.get("id") == token]
            if len(matches) != 1:
                raise ValueError(f"unresolved or ambiguous ID in {reference}: {token}")
            node = matches[0]
        elif isinstance(node, dict) and token in node:
            node = node[token]
        else:
            raise ValueError(f"unresolved reference: {reference}")
    return node


def scalar(value):
    if isinstance(value, (dict, list)) or value is None:
        raise ValueError("bound text requires a known scalar; use explicit wording for unknowns")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number(value)
        return format(value, ".12g")
    return str(value)


def fill_text(template, record):
    if not isinstance(template, str):
        raise ValueError("text_template must be a string")
    refs = []
    def replace(match):
        ref = match.group(1).strip(); refs.append(ref)
        return scalar(resolve_ref(record, ref))
    rendered = re.sub(r"\{\{\s*(/[^{}]+?)\s*\}\}", replace, template)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("unresolved template token")
    return rendered, refs


def calculate_benefit(model):
    """Unknown formulas are not evaluated. No arbitrary expression execution."""
    kind = model.get("formula_type")
    if kind == "linear_difference_rate":
        data = model.get("inputs", {})
        return ((number(data["baseline"]) - number(data["candidate"]))
                * number(data.get("quantity", 1)) * number(data.get("unit_rate", 1)))
    if kind == "net_benefit":
        unit = model.get("unit")
        def total(key):
            entries = model.get("inputs", {}).get(key)
            if not isinstance(entries, list):
                raise ValueError(f"net_benefit.{key} requires an array")
            if any(not isinstance(e, dict) or e.get("unit") != unit for e in entries):
                raise ValueError("net benefit items must use the result unit")
            return sum(number(e["value"]) for e in entries)
        return total("benefits") - total("costs")
    raise NotImplementedError(f"formula not checked: {kind}")


def _audit_record(record, manifest=None, root=None, public_documents=None):
    manifest = manifest or {}; public_documents = public_documents or {}
    errors, warnings, unchecked = [], [], []
    if not isinstance(record, dict):
        return {"errors": ["research record must be an object"], "warnings": [], "unchecked": [], "route_eligibility": {}, "maturity_support": {}, "research_progress": "unknown", "computational_consistency": "FAIL"}
    if record.get("schema_version") not in RECORD_SCHEMAS:
        errors.append("research record schema must be 1.0 or 1.1")
    current = record.get("schema_version") == "1.1"
    workflow = record.get("workflow", {})
    workflow = workflow if isinstance(workflow, dict) else {}
    complete_stage = workflow.get("completed_stage")
    complete = complete_stage == "G5" or manifest.get("status") == "complete"
    full_contract = complete and manifest.get("delivery_level", "standard") in {"standard", "engineering"}
    if complete_stage is not None and complete_stage not in STAGES:
        errors.append("workflow.completed_stage must be G0..G5 or null")
    if workflow.get("current_stage", "G0") not in STAGES:
        errors.append("workflow.current_stage must be G0..G5")
    reached = STAGES.index(complete_stage) if complete_stage in STAGES else -1
    if complete: reached = len(STAGES)-1

    # Query strings can contain dimensions (4×4 mm2). Attempt counts are metadata.
    for q in rows(record, "queries"):
        qid = q.get("id", "?")
        try:
            date = str(q.get("date", ""))
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date): raise ValueError()
            dt.date.fromisoformat(date)
        except ValueError:
            errors.append(f"query {qid} requires a real ISO date")
        if "filters" not in q or not isinstance(q.get("filters"), (str, dict)):
            errors.append(f"query {qid} requires explicit filters (none is allowed)")
        if not isinstance(q.get("excluded"), list):
            errors.append(f"query {qid} requires excluded records (empty is allowed)")
        if q.get("attempt_count", 1) != 1 or isinstance(q.get("attempt_count", 1), bool):
            errors.append(f"query {qid} must represent one attempt")
        for exclusion in q.get("excluded", []) if isinstance(q.get("excluded"), list) else []:
            if not isinstance(exclusion, dict) or not exclusion.get("item") or not exclusion.get("reason"):
                errors.append(f"query {qid} exclusion requires item and reason")
    queries = rows(record, "queries")
    if reached >= STAGES.index("G2") and not queries:
        errors.append("G2 completion requires executed query records; retain an earlier stage for offline plans")
    tracks = rows(record, "research_tracks")
    if current and reached >= STAGES.index("G2"):
        by_track = {}
        for item in tracks:
            track = item.get("track")
            if track not in DEEP_RESEARCH_TRACKS:
                errors.append(f"research track {item.get('id')} has invalid track")
                continue
            if track in by_track:
                errors.append(f"deep research track duplicated: {track}")
            by_track[track] = item
            status = item.get("status")
            if status not in {"completed", "not_applicable", "blocked"}:
                errors.append(f"research track {track} has invalid status")
            if status == "completed" and not item.get("query_ids"):
                errors.append(f"completed research track {track} requires query_ids")
            if status in {"not_applicable", "blocked"} and len(str(item.get("rationale", "")).strip()) < 6:
                errors.append(f"research track {track} {status} requires rationale")
            if status == "blocked" and reached >= STAGES.index("G2"):
                errors.append(f"G2 cannot be completed with blocked research track: {track}")
        missing_tracks = DEEP_RESEARCH_TRACKS - set(by_track)
        if missing_tracks:
            errors.append("G2 requires seven-track coverage or explicit not_applicable records: " + ", ".join(sorted(missing_tracks)))
        for q in queries:
            track = q.get("track")
            if track not in DEEP_RESEARCH_TRACKS:
                errors.append(f"query {q.get('id')} requires a valid deep-research track")
        for track, item in by_track.items():
            if item.get("status") == "completed":
                linked = set(item.get("query_ids", []))
                wrong = [q.get("id") for q in queries if q.get("id") in linked and q.get("track") != track]
                if wrong:
                    errors.append(f"research track {track} links queries assigned to another track: {wrong}")
    progress = complete_stage or ("working" if current else "legacy-unknown")

    routes = {str(r.get("id")): r for r in rows(record, "routes")}
    primary = set(map(str, manifest.get("primary_routes", [])))
    shortlisted = set(map(str, manifest.get("shortlisted_routes", [])))
    selected = primary | {rid for rid, r in routes.items() if r.get("role") == "primary"}
    eligibility = {rid: {"status": "pending", "reasons": []} for rid in routes}
    def block(rid, reason):
        if rid in eligibility:
            eligibility[rid]["status"] = "blocked"
            if reason not in eligibility[rid]["reasons"]: eligibility[rid]["reasons"].append(reason)
    assessments = record.get("assessments", {})
    assessments = assessments if isinstance(assessments, dict) else {}
    if current and full_contract:
        portfolio = assessments.get("route_portfolio")
        if not isinstance(portfolio, dict):
            errors.append("complete standard/engineering delivery requires assessments.route_portfolio")
            portfolio = {}
        covered_roles = set()
        for rid in shortlisted:
            route = routes.get(rid)
            if not isinstance(route, dict):
                continue
            roles = route.get("portfolio_roles")
            if not isinstance(roles, list) or not roles:
                errors.append(f"shortlisted route {rid} requires portfolio_roles")
                roles = []
            invalid = set(map(str, roles)) - PORTFOLIO_ROLES
            if invalid:
                errors.append(f"route {rid} has invalid portfolio_roles: {sorted(invalid)}")
            covered_roles.update(set(map(str, roles)) & PORTFOLIO_ROLES)
            if "baseline" not in roles:
                outlook = route.get("improvement_outlook")
                if not isinstance(outlook, dict):
                    errors.append(f"shortlisted route {rid} requires improvement_outlook")
                else:
                    status = outlook.get("status")
                    if status not in {"identified", "none_identified", "unknown"}:
                        errors.append(f"route {rid} improvement_outlook.status invalid")
                    if status == "identified" and (not isinstance(outlook.get("items"), list) or not outlook.get("items")):
                        errors.append(f"route {rid} identified improvement_outlook requires at least one item")
                    if status in {"none_identified", "unknown"} and len(str(outlook.get("rationale", "")).strip()) < 6:
                        errors.append(f"route {rid} {status} improvement_outlook requires rationale")
                    if len(str(outlook.get("validation_needed", "")).strip()) < 4:
                        errors.append(f"route {rid} improvement_outlook requires validation_needed")
        missing_roles = {"baseline", "backup", "exploratory"} - covered_roles
        if missing_roles:
            errors.append("complete route portfolio missing required roles: " + ", ".join(sorted(missing_roles)))
        supersystem = portfolio.get("supersystem_applicable")
        if not isinstance(supersystem, bool):
            errors.append("route_portfolio.supersystem_applicable must be true/false for complete delivery")
        elif supersystem and "supersystem" not in covered_roles:
            errors.append("supersystem is applicable but no shortlisted route carries portfolio role supersystem")
        elif not supersystem and len(str(portfolio.get("supersystem_rationale", "")).strip()) < 6:
            errors.append("non-applicable supersystem route requires rationale")

        robustness = assessments.get("robustness_review")
        if not isinstance(robustness, dict) or robustness.get("status") != "reviewed":
            errors.append("complete delivery requires reviewed robustness_review")
        else:
            for key in ["strongest_objection", "exit_condition", "rationale"]:
                if len(str(robustness.get(key, "")).strip()) < 6:
                    errors.append(f"robustness_review requires {key}")
            if robustness.get("objection_evidence_status") not in {"F", "M", "S", "H"}:
                errors.append("robustness_review objection_evidence_status must be F/M/S/H")
            if robustness.get("without_strongest_support") not in {"holds", "changes", "unknown"}:
                errors.append("robustness_review without_strongest_support invalid")
            if not robustness.get("strongest_support_claim_id"):
                errors.append("robustness_review requires strongest_support_claim_id")
            if robustness.get("objection_evidence_status") == "S" and not robustness.get("opposing_source_ids"):
                errors.append("source-based strongest objection requires opposing_source_ids")
    gates = assessments.get("gates", [])
    for gate in gates if isinstance(gates, list) else []:
        if not isinstance(gate, dict): continue
        if gate.get("status") not in {"pending", "pass", "fail", "conditional", "not-applicable"}:
            errors.append(f"gate {gate.get('id')} has invalid status")
        target = gate.get("target_id")
        affected = ([target] if target in routes else [rid for rid,r in routes.items() if target and any(c.get("id")==target for c in r.get("components",[]) if isinstance(c,dict))])
        if not target and gate.get("target_kind") == "proposed_system": affected = list(routes)
        if target and not affected: errors.append(f"gate {gate.get('id')} has unresolved target: {target}")
        if gate.get("status") == "fail" and gate.get("hard", True):
            for rid in affected: block(rid, "failed hard gate: "+str(gate.get("id")))
    for rid, route in routes.items():
        all_effects = {str(e.get("id")) for e in route.get("active_effects",[]) if isinstance(e,dict)}
        effects = {str(e.get("id")) for e in route.get("active_effects",[]) if isinstance(e,dict) and e.get("type") not in {"read","passive","information_read"}}
        covered = set(); pending = False
        interactions = route.get("interactions", [])
        if not isinstance(interactions,list): errors.append(f"route {rid} interactions must be an array"); interactions=[]
        for interaction in interactions:
            if not isinstance(interaction,dict): errors.append(f"route {rid} invalid interaction");continue
            ids = interaction.get("effect_ids", [])
            if not isinstance(ids,list) or not set(ids).issubset(all_effects):
                errors.append(f"route {rid} interaction has unresolved effect IDs");continue
            covered.update(tuple(sorted(pair)) for pair in itertools.combinations(set(ids),2))
            status = interaction.get("status")
            if status == "conflict": block(rid,"active effects conflict")
            elif status in {"unknown","conditional"}: pending=True
            elif status != "compatible": errors.append(f"route {rid} invalid interaction status")
        missing = set(itertools.combinations(sorted(effects),2))-covered
        if missing: errors.append(f"route {rid} lacks pairwise interaction review: {sorted(missing)}")
        if any(s.get("handoff_status")=="gap" for s in route.get("steps",[]) if isinstance(s,dict)):
            block(rid,"end-to-end handoff gap")
        if eligibility[rid]["status"] != "blocked" and pending:
            eligibility[rid] = {"status":"conditional", "reasons":["interaction conditions require validation"]}
    # Propagate failure along explicitly recorded route dependencies.
    for _ in routes:
        changed=False
        for rid,route in routes.items():
            for parent in route.get("depends_on_route_ids",[]):
                if parent not in routes: errors.append(f"route {rid} unresolved dependency {parent}")
                elif eligibility[parent]["status"]=="blocked" and eligibility[rid]["status"]!="blocked":
                    block(rid,"blocked upstream route: "+parent);changed=True
        if not changed:break
    for rid in selected:
        if rid in eligibility and eligibility[rid]["status"]=="blocked":
            errors.append(f"primary route {rid} is blocked; retain it as rejected/exploratory, not the selected recommendation")

    # A label M is not a test. Test records must point to real, hash-bound artifacts.
    models = record.get("models_and_tests", {})
    models = models if isinstance(models,dict) else {}
    protocols={p.get("id"):p for p in models.get("protocols",[]) if isinstance(p,dict)}
    valid_tests={}; passed_tests=set(); support={rid:"V0" for rid in routes}
    tests=models.get("tests",[])
    for test in tests if isinstance(tests,list) else []:
        if not isinstance(test,dict) or test.get("status")!="completed": continue
        tid=test.get("id");rid=test.get("route_id");level=test.get("maturity")
        local_errors=[];protocol=protocols.get(test.get("protocol_id"))
        if not tid or tid in valid_tests:local_errors.append("requires a unique test ID")
        if rid not in routes or test.get("target_kind") not in {"proposed_system", "baseline_system"}:local_errors.append("requires the target system route")
        if level not in {"V1","V2","V3"}:local_errors.append("completed test requires V1/V2/V3")
        if not isinstance(protocol,dict):local_errors.append("requires a predeclared protocol")
        else:
            for key in ["scope","sampling_plan","metrics","stop_rule"]:
                if not protocol.get(key):local_errors.append("protocol missing "+key)
            if rid not in protocol.get("route_ids",[]):local_errors.append("protocol route does not match")
            scopes={"V1":"short_sample","V2":"full_process","V3":"controlled_field"}
            if test.get('target_kind') == 'baseline_system':
                if protocol.get('scope') not in scopes.values():local_errors.append('invalid baseline protocol scope')
            elif protocol.get("scope")!=scopes.get(level):local_errors.append("protocol scope does not support maturity")
        if not isinstance(test.get("sample_count"),int) or isinstance(test.get("sample_count"),bool) or test.get("sample_count",0)<1:
            local_errors.append("requires actual sample count")
        if not test.get("conditions") or not test.get("date"):local_errors.append("requires actual conditions and date")
        try:dt.date.fromisoformat(str(test.get("date","")))
        except ValueError:local_errors.append("invalid test date")
        results=test.get("results",[])
        if not isinstance(results,list) or not results:local_errors.append("requires actual results")
        metrics={m.get("id"):m for m in (protocol or {}).get("metrics",[]) if isinstance(m,dict)}
        if not metrics or None in metrics or len(metrics)!=len((protocol or {}).get("metrics",[])):
            local_errors.append("protocol requires unique metric IDs")
        seen=set(); passed=True
        for result in results if isinstance(results,list) else []:
            if not isinstance(result,dict):local_errors.append("invalid result");continue
            metric=metrics.get(result.get("metric_id"));seen.add(result.get("metric_id"))
            try:
                value=number(result.get("value"))
                if metric is None or result.get("unit")!=metric.get("unit"):raise ValueError("metric/unit mismatch")
                criterion=metric.get("criterion",{});bound=number(criterion.get("value"));op=criterion.get("operator")
                if op not in {"<=",">=","=="}:raise ValueError("unsupported criterion operator")
                passed &= {"<=":value<=bound,">=":value>=bound,"==":value==bound}[op]
            except (ValueError,TypeError):local_errors.append("result needs a numeric value and matching predeclared criterion")
        if set(metrics)!=seen:local_errors.append("results do not cover protocol metrics")
        artifacts=test.get("raw_artifacts",[])
        if not isinstance(artifacts,list) or not artifacts:local_errors.append("requires raw measurement artifacts")
        for artifact in artifacts if isinstance(artifacts,list) else []:
            try:
                if root is None:raise ValueError("artifact checks require record directory")
                if not isinstance(artifact,dict):raise ValueError("invalid artifact binding")
                path=local_file(root,artifact.get("path"))
                if digest(path)!=artifact.get("sha256"):raise ValueError("raw artifact hash mismatch")
            except (ValueError,OSError) as exc:local_errors.append(str(exc))
        if level in {"V2","V3"} and not test.get("baseline_test_id"):local_errors.append("requires baseline comparison test")
        if level=="V3":
            decisions={d.get("id"):d for d in rows(record,"decisions")}
            decision=decisions.get(test.get("authorization_decision_id"),{})
            if decision.get("kind")!="field_authorization" or decision.get("status")!="confirmed" or not decision.get("evidence_ids"):
                local_errors.append("requires recorded field authorization evidence")
            evidence_ids={r.get('id') for name in ['sources','inputs','claims'] for r in rows(record,name)}
            if not all(isinstance(test.get("release_checks",{}).get(k),str) and test['release_checks'][k] in evidence_ids for k in ["risk","process","ip","benefit"]):
                local_errors.append("requires risk/process/IP/benefit review references")
        if local_errors:errors.extend(f"test {tid}: {e}" for e in local_errors)
        else:
            valid_tests[tid]=test
            if passed:passed_tests.add(tid)
            if not passed:warnings.append(f"test {tid} failed its predeclared criterion; it cannot support maturity")
    all_test_ids={t.get("id") for t in tests if isinstance(t,dict)} if isinstance(tests,list) else set()
    hazards = rows(record, "hazards")
    if current:
        for hazard in hazards:
            hid = hazard.get("id", "?")
            if not hazard.get("route_ids"):
                errors.append(f"hazard {hid} requires route_ids")
            for key in ["event", "residual_risk", "stop_condition"]:
                if len(str(hazard.get(key, "")).strip()) < 4:
                    errors.append(f"hazard {hid} requires {key}")
            for key in ["causes", "consequences", "controls"]:
                value = hazard.get(key)
                if not isinstance(value, list) or not value:
                    errors.append(f"hazard {hid} requires nonempty {key}")
            if not hazard.get("protocol_id"):
                errors.append(f"hazard {hid} requires validation protocol")
        if full_contract:
            covered_hazards = {rid for hazard in hazards for rid in hazard.get("route_ids", []) if isinstance(rid, str)}
            for rid in shortlisted:
                route = routes.get(rid, {})
                if "baseline" not in route.get("portfolio_roles", []) and rid not in covered_hazards:
                    errors.append(f"shortlisted route {rid} requires at least one FMEA/hazard record")
    for test in list(valid_tests.values()):
        baseline=test.get("baseline_test_id")
        if baseline and (baseline==test['id'] or baseline not in valid_tests):
            errors.append(f"test {test['id']} requires a distinct completed baseline with valid raw artifacts")
            passed_tests.discard(test['id'])
        elif baseline:
            comparison_errors = comparable(test, valid_tests[baseline], protocols)
            errors.extend(f"test {test['id']}: {e}" for e in comparison_errors)
            if comparison_errors: passed_tests.discard(test['id'])
    for tid in passed_tests:
        test=valid_tests[tid];rid=test['route_id'];level=test['maturity']
        if test.get('target_kind') == 'baseline_system': continue
        if MATURITY[level]>MATURITY[support[rid]]:support[rid]=level
    for claim in rows(record,"claims"):
        if claim.get("evidence_status") in {"M","measured","verified"} and claim.get("target_kind")=="proposed_system":
            attached=[valid_tests.get(t) for t in claim.get("test_ids",[])]
            if not any(t and t.get("route_id")==claim.get("target_id") and claim.get("id") in t.get("claim_ids",[]) for t in attached):
                errors.append(f"measured claim {claim.get('id')} lacks matching completed test and raw data")
    for rid,route in routes.items():
        if MATURITY.get(route.get("maturity"),-1)>MATURITY[support[rid]]:
            errors.append(f"route {rid} maturity exceeds validated test evidence ({support[rid]})")
        if eligibility[rid]["status"]=="blocked" and route.get("maturity")!="V0":
            errors.append(f"blocked route {rid} cannot retain elevated maturity")
    project=record.get("project",{})
    declared=manifest.get("maturity",project.get("maturity","V0"))
    if declared not in MATURITY:errors.append("project maturity must be V0-V3")
    if manifest.get("maturity") and project.get("maturity") and declared!=project["maturity"]:
        errors.append("manifest/project maturity mismatch")
    if selected and MATURITY.get(declared,0)>min(MATURITY.get(routes.get(r,{}).get("maturity"),0) for r in selected):
        errors.append("project maturity exceeds the selected route maturity")

    card=assessments.get("scorecard",{})
    if isinstance(card,dict) and card.get("used"):
        weights=[]
        for dimension in card.get("dimensions",[]):
            try:
                weight=number(dimension.get("weight"))
                if weight<0:raise ValueError()
                weights.append(weight)
            except (ValueError,AttributeError):errors.append("scorecard weight must be finite and nonnegative")
        if not weights or sum(weights)<=0:errors.append("scorecard requires a positive total weight")
        if card.get("normalized") is True and not math.isclose(sum(weights),1,abs_tol=1e-9):
            errors.append("normalized scorecard weights must sum to 1")

    benefit_assessment = models.get("benefit_assessment")
    if current and full_contract:
        if not isinstance(benefit_assessment, dict):
            errors.append("complete delivery requires models_and_tests.benefit_assessment")
            benefit_assessment = {}
        economic = benefit_assessment.get("economic", {}) if isinstance(benefit_assessment, dict) else {}
        social = benefit_assessment.get("social", {}) if isinstance(benefit_assessment, dict) else {}
        if not isinstance(economic, dict):
            economic = {}
            errors.append("benefit_assessment.economic must be an object")
        if not isinstance(social, dict):
            social = {}
            errors.append("benefit_assessment.social must be an object")
        economic_status = economic.get("status")
        if economic_status not in {"modeled", "pending-data", "not-applicable"}:
            errors.append("benefit_assessment.economic.status invalid")
        elif economic_status == "modeled" and not models.get("benefit_scenarios"):
            errors.append("modeled economic benefit requires benefit_scenarios")
        elif economic_status == "pending-data":
            if len(str(economic.get("formula", "")).strip()) < 4:
                errors.append("pending economic benefit requires formula")
            if not isinstance(economic.get("inputs_needed"), list) or not economic.get("inputs_needed"):
                errors.append("pending economic benefit requires inputs_needed")
            if len(str(economic.get("scenario_plan", "")).strip()) < 6:
                errors.append("pending economic benefit requires scenario_plan")
        elif economic_status == "not-applicable" and len(str(economic.get("rationale", "")).strip()) < 6:
            errors.append("not-applicable economic benefit requires rationale")

        social_status = social.get("status")
        metrics = social.get("metrics", [])
        if social_status not in {"defined", "pending-data", "not-applicable"}:
            errors.append("benefit_assessment.social.status invalid")
        elif social_status in {"defined", "pending-data"}:
            if not isinstance(metrics, list) or not metrics:
                errors.append("social benefit assessment requires at least one measurable metric")
            else:
                for index, metric in enumerate(metrics):
                    if not isinstance(metric, dict):
                        errors.append(f"social benefit metric[{index}] must be an object")
                        continue
                    for key in ["id", "name", "unit", "target_direction", "measurement", "validation_needed"]:
                        if len(str(metric.get(key, "")).strip()) < 2:
                            errors.append(f"social benefit metric[{index}] requires {key}")
                    if metric.get("evidence_status") not in {"F", "M", "S", "H"}:
                        errors.append(f"social benefit metric[{index}] evidence_status must be F/M/S/H")
        elif social_status == "not-applicable" and len(str(social.get("rationale", "")).strip()) < 6:
            errors.append("not-applicable social benefit requires rationale")

    for model in models.get("benefit_scenarios",[]):
        if not isinstance(model,dict):continue
        mid=str(model.get("id","?"));unit=str(model.get("unit",""))
        try:
            calculated=calculate_benefit(model);expected=number(model.get("expected_result"))
            try: calculated=number(benefit_with_units(model))
            except NotImplementedError as exc: unchecked.append(f"benefit {mid} dimensional consistency: {exc}")
            if not math.isclose(calculated,expected,rel_tol=1e-9,abs_tol=1e-9):errors.append(f"benefit {mid} arithmetic mismatch")
            if not unit:errors.append(f"benefit {mid} requires result unit")
            if model.get("formula_type")=="linear_difference_rate":
                units=model.get("input_units",{})
                if not units or not all(units.get(k) for k in ["baseline","candidate","quantity","unit_rate"]):
                    unchecked.append(f"benefit {mid} input dimensional consistency")
            # Legacy public values get an explicit limited check; new DOCX bindings use SDTs.
            for output in model.get("outputs",[]):
                if not isinstance(output,dict):continue
                role={"summary":"decision-summary","report":"main-report"}.get(output.get("artifact"),output.get("artifact"))
                text=public_documents.get(role,"")
                matches=re.findall(re.escape(mid)+r"[^\n\d]{0,48}([+-]?\d+(?:\.\d+)?)\s*"+re.escape(unit),text)
                if not matches:unchecked.append(f"benefit {mid} has no verifiable value anchor in {role}")
                elif any(not math.isclose(float(v),expected,rel_tol=1e-9,abs_tol=1e-9) for v in matches):
                    errors.append(f"benefit {mid} actual public value differs in {role}")
        except NotImplementedError as exc:unchecked.append(str(exc))
        except (ValueError,TypeError,KeyError) as exc:errors.append(f"benefit {mid}: {exc}")
    if complete and unchecked:errors.extend("complete delivery has unchecked calculation: "+u for u in unchecked)

    if current:
        indexes={}
        for collection in TRACE_COLLECTIONS:
            items=record.get(collection)
            if not isinstance(items,list):errors.append(f"{collection} must be an array");items=[]
            ids=[v.get("id") for v in items if isinstance(v,dict)]
            if len(ids)!=len(items) or any(not isinstance(i,str) or not i.strip() for i in ids) or len(set(ids))!=len(ids):
                errors.append(f"{collection} requires unique nonempty IDs")
            indexes[collection]={v.get("id"):v for v in items if isinstance(v,dict)}
        component_ids={c.get('id') for route in routes.values() for c in route.get('components',[]) if isinstance(c,dict)}
        allowed={name:set(index) for name,index in indexes.items()}
        allowed.update(routes=set(routes),claims={c.get('id') for c in rows(record,'claims')},
                       sources={s.get('id') for s in rows(record,'sources')},components=component_ids,
                       tests=all_test_ids,protocols=set(protocols))
        allowed['evidence']=allowed['inputs']|allowed['claims']|allowed['sources']|all_test_ids
        reference_fields={'input_ids':'inputs','problem_ids':'problems','requirement_ids':'requirements','route_ids':'routes',
                          'parameter_ids':'parameters','claim_ids':'claims','component_ids':'components','test_ids':'tests',
                          'supporting_source_ids':'sources','opposing_source_ids':'sources','evidence_ids':'evidence',
                          'protocol_id':'protocols','authorization_decision_id':'decisions','baseline_test_id':'tests',
                          'mechanism_id':'mechanisms','query_ids':'queries','source_ids':'sources',
                          'strongest_support_claim_id':'claims'}
        def check_refs(value,location='record'):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key in reference_fields:
                        values=item if isinstance(item,list) else [item]
                        if key.endswith('_ids') and not isinstance(item,list):errors.append(location+'.'+key+' must be an array')
                        if any(not isinstance(v,str) or v not in allowed[reference_fields[key]] for v in values):
                            errors.append(location+'.'+key+' has unresolved references')
                    check_refs(item,location+'.'+key)
            elif isinstance(value,list):
                for i,item in enumerate(value):check_refs(item,location+f'[{i}]')
        check_refs(record)
        if reached>=0:
            for name in ["inputs","problems","requirements"]:
                if not indexes[name]:errors.append(f"G0 completion requires {name}")
        for problem in indexes["problems"].values():
            if not problem.get("input_ids") or not set(problem["input_ids"]).issubset(indexes["inputs"]):errors.append(f"problem {problem.get('id')} needs original input references")
        for requirement in indexes["requirements"].values():
            if not requirement.get("problem_ids") or not set(requirement["problem_ids"]).issubset(indexes["problems"]):errors.append(f"requirement {requirement.get('id')} needs problem references")
            if not requirement.get("criterion"):errors.append(f"requirement {requirement.get('id')} needs a success criterion or explicit unknown")
        for item in indexes["inputs"].values():
            if not item.get("text") or not item.get("locator") or item.get("evidence_status") not in {"F","M","S","H"}:
                errors.append(f"input {item.get('id')} needs original text, locator and evidence status")
        symbols=set()
        for parameter in indexes["parameters"].values():
            symbol=parameter.get("symbol","")
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*",symbol) or symbol in symbols:errors.append(f"parameter {parameter.get('id')} invalid/duplicate symbol")
            symbols.add(symbol)
            if not parameter.get("unit") or parameter.get("evidence_status") not in {"F","M","S","H"}:errors.append(f"parameter {parameter.get('id')} needs unit/evidence status")
            if parameter.get("value") is not None:
                try:number(parameter["value"])
                except ValueError:errors.append(f"parameter {parameter.get('id')} needs finite numeric value or null")
        for mechanism in indexes["mechanisms"].values():
            mid=mechanism.get("id")
            for key in ["method","input","action_path","output","conditions","falsification"]:
                if not mechanism.get(key):errors.append(f"mechanism {mid} missing {key}")
            if not mechanism.get("requirement_ids") or not set(mechanism["requirement_ids"]).issubset(indexes["requirements"]):errors.append(f"mechanism {mid} needs requirement references")
            if not mechanism.get("route_ids") or not set(mechanism["route_ids"]).issubset(routes):errors.append(f"mechanism {mid} needs route references")
        if reached>=STAGES.index("G3"):
            covered={rid for m in indexes["mechanisms"].values() for rid in m.get("route_ids",[])}
            if not selected.issubset(covered):errors.append("selected routes require requirement-to-mechanism traceability")
        if reached>=STAGES.index("G2"):
            approvals=[d for d in indexes["decisions"].values() if d.get("kind") in {"direction_confirmation","delegated_direction"} and d.get("status")=="confirmed" and d.get("user_text") and d.get("scope")]
            if not approvals:errors.append("G2 requires recorded confirmation or explicit delegated direction scope")
    else:
        warnings.append("legacy record 1.0: intake/mechanism traceability not checked; migrate to 1.1")
    return {"errors":list(dict.fromkeys(errors)), "warnings":warnings, "unchecked":list(dict.fromkeys(unchecked)),
            "route_eligibility":eligibility, "maturity_support":support, "research_progress":progress,
            "computational_consistency":"FAIL" if errors else "NOT_CHECKED" if unchecked else "PASS",
            "check_scope":{"queries":len(queries),"completed_test_records":len(valid_tests),
                           "benefit_models":len(models.get('benefit_scenarios',[])),
                           "meaning":"PASS means no recorded consistency error; zero models means no calculation was performed."},
            "maturity_note":"No candidate mechanism assessed" if not routes else "Evidence support for recorded candidate routes only",
            "action_authorization":"not-inferred-from-report"}


def audit_record(record, manifest=None, root=None, public_documents=None):
    try:
        return _audit_record(record,manifest,root,public_documents)
    except (TypeError,KeyError,AttributeError,ValueError) as exc:
        return {'errors':['malformed research record: '+str(exc)],'warnings':[],'unchecked':[],
                'route_eligibility':{},'maturity_support':{},'research_progress':'unknown',
                'computational_consistency':'FAIL','action_authorization':'not-inferred-from-report'}


def change_impact(previous, current):
    """Conservative transitive impact over explicit IDs, refs and geometry symbols."""
    collections=TRACE_COLLECTIONS+["variables","contradictions","queries","sources","claims","routes"]
    before={r["id"]:r for name in collections for r in rows(previous,name) if isinstance(r.get("id"),str)}
    after={r["id"]:r for name in collections for r in rows(current,name) if isinstance(r.get("id"),str)}
    changed={rid for rid in before.keys()|after.keys() if before.get(rid)!=after.get(rid)}
    symbols={p.get("symbol"):p.get("id") for p in rows(current,"parameters")}
    edges={rid:set() for rid in after}
    def refs(value,key=""):
        result=set()
        if isinstance(value,dict):
            for k,v in value.items():result.update(refs(v,k))
        elif isinstance(value,list):
            for v in value:result.update(refs(v,key))
        elif isinstance(value,str):
            if key.endswith(("_id","_ids","_ref","_refs")) or key=="depends_on":
                if value in after:result.add(value)
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]*",value):
                if token in after and ("/" in value or key.endswith(("_id","_ids"))):result.add(token)
                if key=="expr" and token in symbols:result.add(symbols[token])
        return result
    for rid,item in after.items():edges[rid]=refs(item)-{rid}
    affected=set(changed)
    while True:
        more={rid for rid,deps in edges.items() if deps&affected}-affected
        if not more:break
        affected.update(more)
    return {"changed_ids":sorted(changed),"review_required_ids":sorted(affected-changed),
            "regenerate":"figures, reports and calculations bound to this record",
            "note":"Conservative recorded dependencies; unrecorded engineering effects still require review."}
