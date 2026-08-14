"""Asset Validator Blender addon."""

bl_info = {
    "name": "Asset Validator",
    "author": "Asset Validator Contributors",
    "version": (0, 1, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Asset Validator",
    "description": "Validate game-ready assets and safely fix supported issues",
    "category": "3D View",
}

import bpy


class ASSETVALIDATOR_OT_run_validation(bpy.types.Operator):
    """Placeholder for the future asset-validation workflow."""

    bl_idname = "asset_validator.run_validation"
    bl_label = "Run Validation"
    bl_description = "Run asset validation (not implemented yet)"

    def execute(self, context):
        self.report({"INFO"}, "Asset validation is not implemented yet")
        return {"FINISHED"}


class ASSETVALIDATOR_PT_sidebar(bpy.types.Panel):
    """3D View sidebar panel for the addon."""

    bl_label = "Asset Validator"
    bl_idname = "ASSETVALIDATOR_PT_sidebar"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Validator"

    def draw(self, context):
        self.layout.operator(ASSETVALIDATOR_OT_run_validation.bl_idname)


CLASSES = (
    ASSETVALIDATOR_OT_run_validation,
    ASSETVALIDATOR_PT_sidebar,
)


def register():
    """Register addon classes with Blender."""
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister addon classes from Blender."""
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
