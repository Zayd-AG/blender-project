# Import Validator Studio Plugin

Import Validator checks 3D assets after they arrive in Roblox Studio. It complements the Blender addon by validating model structure, naming, mesh totals, rig requirements, PrimaryPart assignment, and scale in the imported Studio hierarchy.

## Architecture

- `src/Checks/ImportValidator.luau` is UI-independent validation.
- `src/Fixes/SafeFixes.luau` contains constrained, user-invoked repairs.
- `src/Reporting/ScanReport.luau` exports schema-compatible JSON.
- `src/Shared/RuntimeConfig.luau` decodes the Rojo-synced shared naming contract.

## Screenshots

> Screenshot/GIF placeholder: dock widget showing mesh totals, rig status, grouped findings, and explicit root insertion.

## Install

1. Install Rojo 7.5.1 and run `rojo build -o ImportValidator.rbxmx default.project.json`.
2. In Studio, use **Plugins > Plugins Folder** or **Install from Disk** to install the built plugin model.
3. Click **Import Validator** in the Asset Validator toolbar.
