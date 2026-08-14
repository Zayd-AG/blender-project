# Asset Validator

Asset Validator is a Blender 5.x addon for preparing game-ready 3D assets. It validates generic engine constraints and Roblox-specific import requirements, provides constrained automatic repairs, and produces auditable batch-export reports.

## Problem

Production assets routinely reach export with topology, UV, transform, naming, texture, skinning, or rig-profile issues. This addon catches those checks in Blender, blocks broken assets from batch export, and keeps human judgment visible for ambiguous decisions.

## Architecture

- `blender_addon/` contains the Blender Python addon, its tests, benchmarks, and Ruff configuration.
- `roblox_plugin/` contains the independent Rojo/Selene Luau companion-plugin toolchain.
- `shared/` holds the naming and build-report JSON contracts used by both sides.

## Screenshots

> Screenshot/GIF placeholder: Asset Validator N-panel showing validation, agent triage reasoning, safe fixes, Roblox compatibility, and Batch Export.

> Screenshot/GIF placeholder: Batch build report showing exported assets, validation skips, Roblox upload status, and LOD metrics.

Replace these placeholders with real captures before publishing your portfolio.

## Install

1. Create the distributable zip with `cd blender_addon; zip -r ../dist/asset_validator.zip asset_validator`.
2. In Blender, use **Edit > Preferences > Add-ons > Install from Disk**.
3. Select the zip, enable **Asset Validator**, then open the 3D Viewport sidebar with `N`.

## Results

The deterministic benchmark suite currently records placeholders from [the benchmark report](blender_addon/docs/BENCHMARKS.md):

| Suite | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Geometry / compatibility | 1.000 | 1.000 | 1.000 |
| Agent triage | 1.000 | 1.000 | 1.000 |

Run `cd blender_addon; blender --background --python run_benchmark.py` to regenerate the numbers after changing validators or agent behavior.
