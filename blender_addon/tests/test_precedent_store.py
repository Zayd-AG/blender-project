"""Offline precedent retrieval and agent-outcome tests with fixed embeddings."""

import numpy as np

from asset_validator.agent.precedent_store import PrecedentStore
from asset_validator.agent.triage import AgentConfig, BuildReport, TriageSession


class KeywordEmbedder:
    def embed(self, text):
        return np.array([text.lower().count("head"), text.lower().count("bone"), text.lower().count("name")], dtype=np.float32)


class PrecedentAwareClient:
    def create(self, *, messages, **kwargs):
        tool_calls = [block for message in messages for block in message.get("content", []) if isinstance(block, dict) and block.get("type") == "tool_result"]
        if not tool_calls:
            return {"content": [{"type": "tool_use", "id": "1", "name": "query_precedent", "input": {"finding_context": {"case": "head bone"}}}]}
        has_precedent = '"id": 1' in tool_calls[-1]["content"]
        return {"content": [{"type": "tool_use", "id": "2", "name": "propose_resolution" if has_precedent else "escalate", "input": ({"finding_id": "finding-0", "resolution": {"action": "rename_object", "new_name": "SM_Head"}, "confidence": 0.95, "reasoning": "Supported by precedent."} if has_precedent else {"finding_id": "finding-0", "reason": "No precedent."})}]}


def test_nearest_precedent_is_returned(tmp_path):
    store = PrecedentStore(tmp_path / "precedents.sqlite", KeywordEmbedder())
    store.add("rig", "head bone case", {"action": "map"}, 1.0, "human")
    store.add("naming", "mesh name prefix", {"action": "rename"}, 1.0, "human")
    assert store.query({"case": "head bone"})[0]["context_text"] == "head bone case"


def test_precedent_changes_mocked_agent_outcome(tmp_path):
    finding = {"object_name": "Head", "issue": "roblox_rig_structure", "auto_fixable": False}
    config = AgentConfig("test", 0.8, 4, tmp_path / "report.jsonl")
    store = PrecedentStore(tmp_path / "precedents.sqlite", KeywordEmbedder())
    empty = TriageSession([finding], {"finding-0": {"case": "head bone"}}, precedent_store=store)
    empty.run(PrecedentAwareClient(), config, BuildReport(config.build_report))
    assert empty.states["finding-0"].escalation_reason
    store.add("rig", "head bone", {"action": "map"}, 1.0, "human")
    informed = TriageSession([finding], {"finding-0": {"case": "head bone"}}, precedent_store=store)
    informed.run(PrecedentAwareClient(), config, BuildReport(config.build_report))
    assert informed.states["finding-0"].proposal is not None
    assert informed.states["finding-0"].precedent_ids == [1]
