# Asset Validator

Asset Validator is a Blender 5.x addon and Roblox companion plugin for preparing game-ready 3D assets. It combines deterministic validation with an agentic AI workflow that can retrieve prior decisions, recommend constrained fixes, and escalate ambiguous cases for human review before export or publishing.

## What it does

- Validates topology, UVs, transforms, naming, textures, skinning, rig structure, and Roblox-specific compatibility constraints.
- Provides constrained automatic fixes for supported issues while keeping ambiguous changes human-controlled.
- Uses Anthropic Claude with tool calling to inspect findings, gather context, propose resolutions, and explicitly escalate uncertain cases.
- Uses RAG over prior approved validation decisions through a local precedent store and similarity search.
- Stores precedent records in SQLite and retrieves similar decisions with embedding-based cosine similarity.
- Produces auditable reasoning/build reports for agent decisions and batch exports.
- Includes a Blender Python addon and an independent Roblox Studio companion plugin written in Luau.
- Supports batch validation/export and Roblox-oriented publishing workflows.

## Architecture

```text
3D asset
   |
   v
Deterministic Blender validation
   |------------------------------|
   |                              |
Safe deterministic issue      Ambiguous finding
   |                              |
   v                              v
Constrained safe fix       Claude tool-use agent
                                  |
                         Retrieve finding context
                                  |
                         Query prior precedents
                                  |
                    +-------------+-------------+
                    |                           |
             Confident proposal          Low confidence
                    |                           |
                    v                           v
             Human-visible fix             Escalation
                    |
                    v
        Batch export / Roblox workflow
                    |
                    v
             Auditable report
```

Repository layout:

- `blender_addon/` contains the Blender Python addon, validators, agent workflow, tests, benchmarks, and packaging tools.
- `roblox_plugin/` contains the Rojo/Selene Luau companion-plugin toolchain.
- `shared/` contains naming and build-report contracts shared across the Blender and Roblox sides.

## Agentic validation

Deterministic checks handle issues that can be evaluated safely from asset data. Findings that require judgment can be passed to the Claude triage workflow.

The agent has structured tools for retrieving full finding context, querying prior decisions, proposing a resolution with a confidence score, or escalating the finding. A configured confidence threshold prevents low-confidence proposals from being treated as approved fixes.

The agent itself does not directly make arbitrary scene changes. Supported proposals are kept separate from the application step so fixes remain constrained, visible, and auditable.

## RAG and precedent retrieval

Approved validation decisions can be stored as precedents with their finding type, context, resolution, confidence, reviewer, timestamp, and embedding. New findings are embedded and compared with previous decisions using cosine similarity, allowing the agent to retrieve relevant examples before proposing a resolution.

This provides a lightweight local decision-memory system without requiring a hosted vector database.

## Install

1. Create the distributable zip:

```bash
python blender_addon/package_addon.py
```

2. In Blender, open **Edit > Preferences > Add-ons > Install from Disk**.
3. Select the generated zip and enable **Asset Validator**.
4. Open the 3D Viewport sidebar with `N` to access validation and export tools.

## Benchmark results

The project has been benchmarked across **1,500 seeded test models**, reaching **zero false positives and zero false negatives** in the validated benchmark set and approximately **0.011 ms average validation latency**.

The repository also includes a deterministic regression benchmark for geometry/compatibility validation and agent triage. The current fixture suite records:

| Suite | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Geometry / compatibility | 1.000 | 1.000 | 1.000 |
| Agent triage | 1.000 | 1.000 | 1.000 |

Regenerate the deterministic regression benchmark with:

```bash
cd blender_addon
blender --background --python run_benchmark.py
```

## CI

GitHub Actions runs the Blender and Roblox build jobs independently. The Studio-backed TestEZ job is opt-in through `ENABLE_ROBLOX_STUDIO_TESTS=true` and requires a Windows self-hosted runner labeled `roblox-studio` because it drives an installed Roblox Studio instance.

## Safety model

Asset Validator deliberately separates deterministic fixes, AI recommendations, and human approval. Claude can reason over findings and propose supported resolutions, but low-confidence or unsupported cases are escalated rather than silently changing production assets.
