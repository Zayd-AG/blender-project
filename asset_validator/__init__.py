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

from .checks import load_roblox_profile, validate_assets, validate_roblox_compatibility
from .fixes import apply_safe_fixes


def _target_objects(context):
    selected_meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
    return selected_meshes or [obj for obj in context.scene.objects if obj.type == "MESH"]


def _roblox_target_objects(context):
    return list(context.selected_objects) or list(context.scene.objects)


class ASSETVALIDATOR_Preferences(bpy.types.AddonPreferences):
    """User-selectable Roblox rig target used by the compatibility check."""

    bl_idname = __package__

    roblox_rig_type: bpy.props.EnumProperty(
        name="Roblox Rig Type",
        items=(("R15", "R15", "Roblox R15 rig"), ("R6", "R6", "Roblox R6 rig")),
        default="R15",
    )

    def draw(self, context):
        self.layout.prop(self, "roblox_rig_type")


class ASSETVALIDATOR_OT_run_validation(bpy.types.Operator):
    """Run validation on selected meshes, or all meshes when none are selected."""

    bl_idname = "asset_validator.run_validation"
    bl_label = "Run Validation"
    bl_description = "Run validation on selected meshes, or all scene meshes"

    def execute(self, context):
        findings = validate_assets(_target_objects(context))
        context.window_manager.asset_validator_before_count = len(findings)
        context.window_manager.asset_validator_after_count = len(findings)
        self.report({"INFO"}, f"Validation found {len(findings)} finding(s)")
        return {"FINISHED"}


class ASSETVALIDATOR_OT_apply_safe_fixes(bpy.types.Operator):
    """Apply safe fixes and show the validation finding-count diff."""

    bl_idname = "asset_validator.apply_safe_fixes"
    bl_label = "Apply Safe Fixes"
    bl_description = "Apply deterministic fixes and validate again"

    def execute(self, context):
        result = apply_safe_fixes(_target_objects(context))
        context.window_manager.asset_validator_before_count = result.before_count
        context.window_manager.asset_validator_after_count = result.after_count
        self.report(
            {"INFO"},
            f"Safe fixes: {result.before_count} -> {result.after_count} finding(s)",
        )
        return {"FINISHED"}


class ASSETVALIDATOR_OT_check_roblox_compatibility(bpy.types.Operator):
    """Run Roblox-specific checks separately from general validation."""

    bl_idname = "asset_validator.check_roblox_compatibility"
    bl_label = "Check Roblox Compatibility"

    def execute(self, context):
        preferences = context.preferences.addons[__package__].preferences
        findings = validate_roblox_compatibility(
            _roblox_target_objects(context), load_roblox_profile(preferences.roblox_rig_type)
        )
        context.window_manager.asset_validator_roblox_count = len(findings)
        self.report({"INFO"}, f"Roblox compatibility found {len(findings)} finding(s)")
        return {"FINISHED"}


class ASSETVALIDATOR_PT_sidebar(bpy.types.Panel):
    """3D View sidebar panel for the addon."""

    bl_label = "Asset Validator"
    bl_idname = "ASSETVALIDATOR_PT_sidebar"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Asset Validator"

    def draw(self, context):
        layout = self.layout
        layout.operator(ASSETVALIDATOR_OT_run_validation.bl_idname)
        layout.operator(ASSETVALIDATOR_OT_apply_safe_fixes.bl_idname)
        before = context.window_manager.asset_validator_before_count
        after = context.window_manager.asset_validator_after_count
        if before >= 0:
            layout.label(text=f"Findings: {before} → {after}")
        roblox_box = layout.box()
        roblox_box.label(text="Roblox Compatibility")
        roblox_box.operator(ASSETVALIDATOR_OT_check_roblox_compatibility.bl_idname)
        roblox_count = context.window_manager.asset_validator_roblox_count
        if roblox_count >= 0:
            roblox_box.label(text=f"Findings: {roblox_count}")


CLASSES = (
    ASSETVALIDATOR_Preferences,
    ASSETVALIDATOR_OT_run_validation,
    ASSETVALIDATOR_OT_apply_safe_fixes,
    ASSETVALIDATOR_OT_check_roblox_compatibility,
    ASSETVALIDATOR_PT_sidebar,
)


def register():
    """Register addon classes with Blender."""
    bpy.types.WindowManager.asset_validator_before_count = bpy.props.IntProperty(default=-1)
    bpy.types.WindowManager.asset_validator_after_count = bpy.props.IntProperty(default=-1)
    bpy.types.WindowManager.asset_validator_roblox_count = bpy.props.IntProperty(default=-1)
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister addon classes from Blender."""
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.asset_validator_roblox_count
    del bpy.types.WindowManager.asset_validator_after_count
    del bpy.types.WindowManager.asset_validator_before_count
