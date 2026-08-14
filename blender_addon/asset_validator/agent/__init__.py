"""Auditable, proposal-only agent triage for ambiguous findings."""

from .precedent_store import (
    EmbeddingConfig,
    OpenAICompatibleEmbeddingClient,
    PrecedentStore,
    load_precedent_profile,
)
from .triage import (
    AgentConfig,
    AnthropicClaudeClient,
    BuildReport,
    TriageSession,
    apply_approved_agent_resolutions,
    build_finding_contexts,
    load_agent_config,
)

__all__ = (
    "AgentConfig",
    "AnthropicClaudeClient",
    "BuildReport",
    "TriageSession",
    "apply_approved_agent_resolutions",
    "build_finding_contexts",
    "load_agent_config",
    "EmbeddingConfig",
    "OpenAICompatibleEmbeddingClient",
    "PrecedentStore",
    "load_precedent_profile",
)
