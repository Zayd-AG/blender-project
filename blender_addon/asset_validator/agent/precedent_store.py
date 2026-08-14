"""Small local RAG store: SQLite records plus NumPy cosine retrieval."""

from __future__ import annotations

import io
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.request import Request, urlopen

import numpy as np


class EmbeddingClient(Protocol):
    def embed(self, text: str) -> np.ndarray: ...


@dataclass(frozen=True)
class EmbeddingConfig:
    endpoint: str | None
    model: str | None
    api_key: str | None
    top_k: int = 3


def load_precedent_profile() -> dict[str, Any]:
    """Load local-store and embedding defaults without fixing a provider/model."""
    profile_path = Path(__file__).parent.parent / "config" / "precedent_profile.json"
    return json.loads(profile_path.read_text(encoding="utf-8"))


class OpenAICompatibleEmbeddingClient:
    """Configurable embedding endpoint; no provider or model is hardcoded."""

    def __init__(self, config: EmbeddingConfig):
        if not config.endpoint or not config.model or not config.api_key:
            raise ValueError("Configure embedding endpoint, model, and API key for precedent retrieval.")
        self.config = config

    def embed(self, text: str) -> np.ndarray:
        payload = json.dumps({"model": self.config.model, "input": text}).encode()
        request = Request(
            self.config.endpoint,
            data=payload,
            headers={"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=20) as response:  # nosec B310 - configured HTTPS endpoint
            vector = json.loads(response.read())["data"][0]["embedding"]
        return np.asarray(vector, dtype=np.float32)


class PrecedentStore:
    def __init__(self, path: Path, embedder: EmbeddingClient):
        self.path = path
        self.embedder = embedder
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS precedents (
                id INTEGER PRIMARY KEY,
                finding_type TEXT NOT NULL,
                context_text TEXT NOT NULL,
                resolution TEXT NOT NULL,
                confidence REAL NOT NULL,
                resolved_by TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                embedding BLOB NOT NULL
            )"""
        )
        self.connection.commit()

    def add(
        self,
        finding_type: str,
        context_text: str,
        resolution: dict[str, Any],
        confidence: float,
        resolved_by: str,
        timestamp: str | None = None,
    ) -> int:
        vector = self.embedder.embed(context_text)
        cursor = self.connection.execute(
            "INSERT INTO precedents VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)",
            (
                finding_type,
                context_text,
                json.dumps(resolution),
                confidence,
                resolved_by,
                timestamp or datetime.now(UTC).isoformat(),
                _serialize(vector),
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def query(self, finding_context: dict[str, Any], top_k: int = 3) -> list[dict[str, Any]]:
        context_text = context_to_text(finding_context)
        query_vector = self.embedder.embed(context_text)
        candidates = []
        for row in self.connection.execute("SELECT id, context_text, resolution, confidence, resolved_by, embedding FROM precedents"):
            similarity = _cosine(query_vector, _deserialize(row[5]))
            candidates.append({"id": row[0], "context_text": row[1], "resolution": json.loads(row[2]), "confidence": row[3], "resolved_by": row[4], "similarity": similarity})
        return sorted(candidates, key=lambda item: item["similarity"], reverse=True)[:top_k]

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM precedents").fetchone()[0])

    def close(self) -> None:
        self.connection.close()


def context_to_text(context: dict[str, Any]) -> str:
    return json.dumps(context, sort_keys=True, separators=(",", ":"))


def _serialize(vector: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, vector.astype(np.float32), allow_pickle=False)
    return buffer.getvalue()


def _deserialize(value: bytes) -> np.ndarray:
    return np.load(io.BytesIO(value), allow_pickle=False)


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator else 0.0
