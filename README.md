# Asset Validator

Asset Validator is a Blender addon for checking 3D assets against common game-engine import requirements. It will eventually identify issues and apply safe fixes before export.

This initial version is intentionally a loadable addon skeleton only: it adds an **Asset Validator** tab in the 3D Viewport sidebar with a placeholder **Run Validation** button. No validation or auto-fix logic has been implemented.

## Install for local testing

1. Zip the `asset_validator` directory, preserving the directory itself at the root of the archive.
2. In Blender, open **Edit > Preferences > Add-ons**.
3. Use the dropdown menu in the top-right of the Add-ons page and choose **Install from Disk**.
4. Select the zip file and enable **Asset Validator**.
5. In the 3D Viewport, press `N` and select the **Asset Validator** tab.

The addon is developed against Blender 4.5.0 LTS; see [DEVELOPMENT.md](DEVELOPMENT.md).
