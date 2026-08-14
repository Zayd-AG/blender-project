"""Run with: blender --background --python run_benchmark.py"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import bpy

from asset_validator.agent.triage import AgentConfig, BuildReport, TriageSession
from asset_validator.checks import load_roblox_profile, validate_assets, validate_roblox_compatibility
from asset_validator.checks.validation import ValidationConfig
from test.fixtures.benchmark_fixtures import build_fixtures, cleanup


class ScriptedAgent:
    """Deterministic benchmark double; never contacts an LLM API."""

    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        finding_id = "finding-0" if self.calls == 0 else "finding-1"
        self.calls += 1
        if finding_id == "finding-0":
            payload = {"finding_id": finding_id, "resolution": {"action": "rename_object", "new_name": "SM_Cube"}, "confidence": 0.99, "reasoning": "Fixture naming label."}
            name = "propose_resolution"
        else:
            payload = {"finding_id": finding_id, "reason": "Rig mapping requires human confirmation."}
            name = "escalate"
        return {"content": [{"type": "tool_use", "id": str(self.calls), "name": name, "input": payload}]}


def metrics(expected, actual):
    true_positive = len(expected & actual)
    false_positive = len(actual - expected)
    false_negative = len(expected - actual)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def run_geometry(fixtures):
    expected, actual = set(), set()
    for object_index, (obj, labels) in enumerate(fixtures):
        expected |= {(object_index, issue) for issue in labels}
        generic = ValidationConfig(
            triangle_budget=11 if obj.name == "SM_Budget" else 50_000,
            max_texture_size=2048 if obj.name == "SM_Texture" else 4096,
        )
        profile = load_roblox_profile("R15")
        roblox = type(profile)(
            profile.meters_per_stud,
            profile.min_studs,
            1.0 if obj.name == "SM_RobloxScale" else 100.0,
            profile.rig_type,
            profile.required_bones if obj.name == "SM_RigMesh" else (),
        )
        findings = validate_assets([obj], generic) + validate_roblox_compatibility([obj], roblox)
        actual |= {(object_index, finding["issue"]) for finding in findings}
    return metrics(expected, actual), len(fixtures)


def run_agent():
    findings = [
        {"object_name": "Cube.001", "issue": "naming_convention", "auto_fixable": False},
        {"object_name": "FixtureRig", "issue": "roblox_rig_structure", "auto_fixable": False},
    ]
    contexts = {"finding-0": {"name": "Cube.001", "pattern": "^SM_"}, "finding-1": {"expected_bones": ["Head"]}}
    session = TriageSession(findings, contexts)
    report = ROOT / ".benchmark_agent_report.jsonl"
    session.run(ScriptedAgent(), AgentConfig("benchmark-mock", 0.85, 2, report), BuildReport(report))
    if report.exists():
        report.unlink()
    expected = {("finding-0", "rename_object"), ("finding-1", "escalate")}
    actual = set()
    for state in session.states.values():
        if state.proposal:
            actual.add((state.finding_id, state.proposal["resolution"]["action"]))
        if state.escalation_reason:
            actual.add((state.finding_id, "escalate"))
    return metrics(expected, actual)


def write_markdown(geometry, fixture_count, agent):
    text = f"""# Benchmarks

Regenerate after validator or agent changes:

```powershell
blender --background --python run_benchmark.py
```

Fixtures are programmatically built in `test/fixtures/benchmark_fixtures.py` and include clean controls plus generic-engine and Roblox anti-patterns.

## Geometry and compatibility checks

| Fixtures | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: |
| {fixture_count} | {geometry[0]:.3f} | {geometry[1]:.3f} | {geometry[2]:.3f} |

## Agent triage (deterministic mocked LLM)

| Labeled ambiguous findings | Precision | Recall | F1 |
| ---: | ---: | ---: | ---: |
| 2 | {agent[0]:.3f} | {agent[1]:.3f} | {agent[2]:.3f} |

Agent scoring compares the proposed action or escalation against human labels; it is intentionally separate from geometry detection.
"""
    (ROOT / "docs" / "BENCHMARKS.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    cleanup()
    fixtures = build_fixtures()
    geometry, count = run_geometry(fixtures)
    agent = run_agent()
    write_markdown(geometry, count, agent)
    print(f"Geometry F1: {geometry[2]:.3f}; Agent F1: {agent[2]:.3f}")
    cleanup()
