"""Unit tests use scripted tool calls only; no real LLM API is contacted."""

import json

from asset_validator.agent.triage import (
    AgentConfig,
    BuildReport,
    TriageSession,
    apply_approved_agent_resolutions,
)


class ScriptedClient:
    def __init__(self, responses):
        self.responses = iter(responses)

    def create(self, **kwargs):
        return next(self.responses)


def _tool(name, tool_id, arguments):
    return {"content": [{"type": "tool_use", "id": tool_id, "name": name, "input": arguments}]}


def test_low_confidence_proposal_escalates_and_logs_trace(tmp_path):
    finding = {"object_name": "Cube", "issue": "naming_convention", "auto_fixable": False}
    session = TriageSession([finding], {"finding-0": {"name": "Cube", "pattern": "^SM_"}})
    client = ScriptedClient([
        _tool("get_finding_context", "1", {"finding_id": "finding-0"}),
        _tool("propose_resolution", "2", {"finding_id": "finding-0", "resolution": {"action": "rename_object", "new_name": "SM_Cube"}, "confidence": 0.2, "reasoning": "Prefix is obvious, but context is incomplete."}),
    ])
    report_path = tmp_path / "build.jsonl"
    session.run(client, AgentConfig("test-model", 0.8, 4, report_path), BuildReport(report_path))
    state = session.states["finding-0"]
    assert state.escalation_reason
    record = json.loads(report_path.read_text(encoding="utf-8"))
    assert record["reasoning_trace"][-1]["event"] == "threshold_escalation"


def test_agent_proposal_never_applies_a_fix(tmp_path):
    object_ref = type("Object", (), {"name": "Cube", "data": type("Mesh", (), {"name": "Cube"})()})()
    finding = {"object_name": "Cube", "issue": "naming_convention", "auto_fixable": False}
    session = TriageSession([finding], {"finding-0": {}}, {"Cube": object_ref})
    client = ScriptedClient([_tool("propose_resolution", "1", {"finding_id": "finding-0", "resolution": {"action": "rename_object", "new_name": "SM_Cube"}, "confidence": 0.99, "reasoning": "Compliant prefix."})])
    report_path = tmp_path / "build.jsonl"
    session.run(client, AgentConfig("test-model", 0.8, 2, report_path), BuildReport(report_path))
    assert object_ref.name == "Cube"
    assert session.states["finding-0"].proposal["reasoning"] == "Compliant prefix."


def test_apply_flow_requires_high_confidence(tmp_path):
    object_ref = type("Object", (), {"name": "Cube", "data": type("Mesh", (), {"name": "Cube"})()})()
    finding = {"object_name": "Cube", "issue": "naming_convention", "auto_fixable": False}
    session = TriageSession([finding], {"finding-0": {}}, {"Cube": object_ref})
    client = ScriptedClient([_tool("propose_resolution", "1", {"finding_id": "finding-0", "resolution": {"action": "rename_object", "new_name": "SM_Cube"}, "confidence": 0.99, "reasoning": "Compliant prefix."})])
    report_path = tmp_path / "build.jsonl"
    session.run(client, AgentConfig("test-model", 0.8, 2, report_path), BuildReport(report_path))
    assert apply_approved_agent_resolutions(session, 0.8) == ["finding-0"]
    assert object_ref.name == "SM_Cube"
