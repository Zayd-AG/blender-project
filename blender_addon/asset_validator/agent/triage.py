"""Claude tool-use loop for reviewing findings that need human judgment."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from typing import Any, Iterable, Protocol


@dataclass(frozen=True)
class AgentConfig:
    """Model and safety settings loaded from the project agent profile."""

    model: str | None
    confidence_threshold: float
    max_turns_per_finding: int
    build_report: Path


def load_agent_config(model: str | None = None) -> AgentConfig:
    """Load project defaults; a user-selected model overrides the profile."""
    profile_path = Path(__file__).parent.parent / "config" / "agent_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    selected_model = model or os.getenv("ASSET_VALIDATOR_CLAUDE_MODEL") or profile["model"]
    return AgentConfig(
        model=selected_model,
        confidence_threshold=float(profile["confidence_threshold"]),
        max_turns_per_finding=int(profile["max_turns_per_finding"]),
        build_report=Path(profile["build_report"]),
    )


class ClaudeClient(Protocol):
    """Small testable boundary around the Claude Messages API."""

    def create(self, *, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        """Return a normalized Claude response with content blocks."""


class AnthropicClaudeClient:
    """Optional live client; tests inject a scripted client instead."""

    def __init__(self, api_key: str | None = None):
        try:
            import anthropic
        except ImportError as error:
            raise RuntimeError("Install the 'anthropic' package to run agent triage.") from error
        self._client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    def create(self, *, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict:
        response = self._client.messages.create(
            model=model,
            max_tokens=1024,
            messages=messages,
            tools=tools,
        )
        content = [block.model_dump() for block in response.content]
        return {"content": content, "stop_reason": response.stop_reason}


@dataclass
class FindingState:
    finding_id: str
    finding: dict[str, Any]
    context: dict[str, Any]
    object_ref: object | None = None
    proposal: dict[str, Any] | None = None
    escalation_reason: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)
    precedent_ids: list[int] = field(default_factory=list)


class BuildReport:
    """Append one JSON audit record per triaged finding."""

    def __init__(self, path: Path):
        self.path = path

    def log(self, state: FindingState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "finding_id": state.finding_id,
            "finding": state.finding,
            "context": state.context,
            "proposal": state.proposal,
            "escalation_reason": state.escalation_reason,
            "reasoning_trace": state.trace,
            "precedent_ids": state.precedent_ids,
        }
        with self.path.open("a", encoding="utf-8") as report:
            report.write(json.dumps(record) + "\n")


class TriageSession:
    """Owns finding context, tool implementations, proposals, and audit traces."""

    def __init__(
        self,
        findings: Iterable[dict[str, Any]],
        contexts: dict[str, dict[str, Any]],
        objects_by_name: dict[str, object] | None = None,
        precedent_store: Any | None = None,
        precedent_top_k: int = 3,
    ):
        self.states = {
            finding_id: FindingState(
                finding_id, finding, contexts.get(finding_id, {}),
                (objects_by_name or {}).get(finding.get("object_name")),
            )
            for finding_id, finding in ((f"finding-{index}", finding) for index, finding in enumerate(findings))
        }
        self.precedent_store = precedent_store
        self.precedent_top_k = precedent_top_k

    def get_finding_context(self, finding_id: str) -> dict[str, Any]:
        return self.states[finding_id].context

    def propose_resolution(
        self, finding_id: str, resolution: dict[str, Any], confidence: float, reasoning: str
    ) -> dict[str, Any]:
        state = self.states[finding_id]
        state.proposal = {"resolution": resolution, "confidence": confidence, "reasoning": reasoning}
        return {"recorded": True}

    def query_precedent(self, finding_context: dict[str, Any]) -> list[dict[str, Any]]:
        if self.precedent_store is None:
            return []
        records = self.precedent_store.query(finding_context, self.precedent_top_k)
        finding_id = next(
            (state.finding_id for state in self.states.values() if state.context == finding_context), None
        )
        if finding_id is not None:
            self.states[finding_id].precedent_ids = [record["id"] for record in records]
        return records

    def escalate(self, finding_id: str, reason: str) -> dict[str, Any]:
        self.states[finding_id].escalation_reason = reason
        return {"escalated": True}

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            _tool("get_finding_context", "Get full data for one flagged finding.", {"finding_id": "string"}, ["finding_id"]),
            _tool("propose_resolution", "Record a proposed fix; never apply it.", {"finding_id": "string", "resolution": "object", "confidence": "number", "reasoning": "string"}, ["finding_id", "resolution", "confidence", "reasoning"]),
            _tool("query_precedent", "Query prior approved decisions; currently returns no results.", {"finding_context": "object"}, ["finding_context"]),
            _tool("escalate", "Explicitly defer a finding to a human.", {"finding_id": "string", "reason": "string"}, ["finding_id", "reason"]),
        ]

    def run(self, client: ClaudeClient, config: AgentConfig, report: BuildReport) -> None:
        if not config.model:
            raise ValueError("Configure a Claude model in addon preferences or ASSET_VALIDATOR_CLAUDE_MODEL.")
        for state in self.states.values():
            self._run_one(state, client, config)
            report.log(state)

    def _run_one(self, state: FindingState, client: ClaudeClient, config: AgentConfig) -> None:
        messages: list[dict[str, Any]] = [{"role": "user", "content": _prompt(state.finding_id)}]
        for _ in range(config.max_turns_per_finding):
            response = client.create(model=config.model, messages=messages, tools=self.tool_definitions())
            blocks = response.get("content", [])
            tool_uses = [block for block in blocks if block.get("type") == "tool_use"]
            if not tool_uses:
                state.trace.append({"event": "assistant_text", "content": blocks})
                break
            state.trace.append({"event": "assistant_tool_use", "content": tool_uses})
            results = []
            for use in tool_uses:
                result = self._call_tool(use["name"], use.get("input", {}))
                state.trace.append({"event": "tool_result", "tool": use["name"], "result": result})
                results.append({"type": "tool_result", "tool_use_id": use["id"], "content": json.dumps(result)})
            messages.extend(({"role": "assistant", "content": blocks}, {"role": "user", "content": results}))
            if state.proposal is not None or state.escalation_reason is not None:
                break
        if state.proposal is not None and state.proposal["confidence"] < config.confidence_threshold:
            self.escalate(state.finding_id, "Proposal confidence is below the configured threshold.")
            state.trace.append({"event": "threshold_escalation", "threshold": config.confidence_threshold})
        elif state.proposal is None and state.escalation_reason is None:
            self.escalate(state.finding_id, "Agent returned no confident structured resolution.")
            state.trace.append({"event": "implicit_escalation"})

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return getattr(self, name)(**arguments)


def build_finding_contexts(
    findings: Iterable[dict[str, Any]],
    objects_by_name: dict[str, object],
    validation_config: Any,
    roblox_config: Any,
) -> dict[str, dict[str, Any]]:
    """Build precise context for the two ambiguous finding types we support."""
    contexts = {}
    for index, finding in enumerate(findings):
        obj = objects_by_name.get(finding["object_name"])
        if finding["issue"] == "naming_convention":
            contexts[f"finding-{index}"] = {
                "issue": finding["issue"],
                "object_name": finding["object_name"],
                "mesh_name": getattr(getattr(obj, "data", None), "name", None),
                "pattern": validation_config.name_pattern,
            }
        elif finding["issue"] == "roblox_rig_structure":
            contexts[f"finding-{index}"] = {
                "issue": finding["issue"],
                "rig_type": roblox_config.rig_type,
                "expected_bones": list(roblox_config.required_bones),
                "actual_bones": [bone.name for bone in getattr(getattr(obj, "data", None), "bones", ())],
            }
        else:
            contexts[f"finding-{index}"] = {"finding": finding}
    return contexts


def apply_approved_agent_resolutions(session: TriageSession, threshold: float) -> list[str]:
    """Apply only visible, high-confidence, explicitly supported proposals.

    The agent cannot call this function. It is invoked only by the existing
    Apply Safe Fixes operator after the panel has shown the proposal reasoning.
    """
    applied = []
    for state in session.states.values():
        if state.escalation_reason or state.proposal is None or state.object_ref is None:
            continue
        proposal = state.proposal
        if proposal["confidence"] < threshold:
            continue
        resolution = proposal["resolution"]
        if resolution.get("action") == "rename_object" and resolution.get("new_name"):
            state.object_ref.name = resolution["new_name"]
            applied.append(state.finding_id)
        elif resolution.get("action") == "rename_mesh" and resolution.get("new_name"):
            state.object_ref.data.name = resolution["new_name"]
            applied.append(state.finding_id)
    return applied


def _tool(name: str, description: str, properties: dict[str, str], required: list[str]) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {"type": "object", "properties": {key: {"type": value} for key, value in properties.items()}, "required": required},
    }


def _prompt(finding_id: str) -> str:
    return (
        f"Triage {finding_id}. Call get_finding_context and query_precedent first. "
        "Then call propose_resolution with structured resolution, confidence, and reasoning, "
        "or call escalate when uncertain. You may propose but must never apply a change."
    )
