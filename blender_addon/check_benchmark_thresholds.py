"""Fail CI when benchmark metrics fall below configured thresholds."""

import os
from pathlib import Path


def _row_after(heading):
    text = Path("docs/BENCHMARKS.md").read_text(encoding="utf-8")
    section = text.split(heading, 1)[1]
    row = next(line for line in section.splitlines() if line.startswith("| 12") or line.startswith("| 2"))
    return [float(value.strip()) for value in row.strip("|").split("|")[1:]]


geometry = _row_after("## Geometry and compatibility checks")
agent = _row_after("## Agent triage")
thresholds = [float(os.getenv(name, default)) for name, default in (("MIN_GEOMETRY_PRECISION", ".95"), ("MIN_GEOMETRY_RECALL", ".95"), ("MIN_AGENT_F1", "1.0"))]
if geometry[0] < thresholds[0] or geometry[1] < thresholds[1] or agent[2] < thresholds[2]:
    raise SystemExit(f"Benchmark threshold failure: geometry={geometry}, agent={agent}, thresholds={thresholds}")
