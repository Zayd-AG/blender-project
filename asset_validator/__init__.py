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

from dataclasses import replace
from pathlib import Path

import bpy

from .agent import (
    AnthropicClaudeClient,
    BuildReport,
    TriageSession,
    apply_approved_agent_resolutions,
    build_finding_contexts,
    load_agent_config,
)
from .checks import load_roblox_profile, validate_assets, validate_roblox_compatibility
from .checks.validation import ValidationConfig
from .fixes import apply_safe_fixes


def _target_objects(context):
    selected_meshes = [obj for obj in context.selected_objects if obj.type == "MESH"]
    return selected_meshes or [obj for obj in context.scene.objects if obj.type == "MESH"]


def _roblox_target_objects(context):
    return list(context.selected_objects) or list(context.scene.objects)


_triage_session: TriageSession | None = None


class ASSETVALIDATOR_Preferences(bpy.types.AddonPreferences):
    """User-selectable Roblox rig target used by the compatibility check."""

    bl_idname = __package__

    roblox_rig_type: bpy.props.EnumProperty(
        name="Roblox Rig Type",
        items=(("R15", "R15", "Roblox R15 rig"), ("R6", "R6", "Roblox R6 rig")),
        default="R15",
    )
    claude_model: bpy.props.StringProperty(
        name="Claude Model",
        description="Optional model override; leave blank to use the project profile or environment",
        default="",
    )

    def draw(self, context):
        self.layout.prop(self, "roblox_rig_type")
        self.layout.prop(self, "claude_model")


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
        global _triage_session
        agent_applied = []
        if _triage_session is not None:
            config = load_agent_config()
            agent_applied = apply_approved_agent_resolutions(
                _triage_session, config.confidence_threshold
            )
        after = validate_assets(_target_objects(context))
        context.window_manager.asset_validator_before_count = result.before_count
        context.window_manager.asset_validator_after_count = len(after)
        self.report(
            {"INFO"},
            f"Safe fixes: {result.before_count} -> {len(after)} finding(s); agent proposals applied: {len(agent_applied)}",
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


class ASSETVALIDATOR_OT_run_agent_triage(bpy.types.Operator):
    """Ask Claude to propose (but never directly apply) ambiguous resolutions."""

    bl_idname = "asset_validator.run_agent_triage"
    bl_label = "Run Agent Triage"

    def execute(self, context):
        global _triage_session
        preferences = context.preferences.addons[__package__].preferences
        general_objects = _target_objects(context)
        roblox_objects = _roblox_target_objects(context)
        validation_config = ValidationConfig()
        roblox_config = load_roblox_profile(preferences.roblox_rig_type)
        findings = [
            finding
            for finding in validate_assets(general_objects, validation_config)
            + validate_roblox_compatibility(roblox_objects, roblox_config)
            if not finding["auto_fixable"]
        ]
        objects = {obj.name: obj for obj in context.scene.objects}
        _triage_session = TriageSession(
            findings,
            build_finding_contexts(findings, objects, validation_config, roblox_config),
            objects,
        )
        config = load_agent_config(preferences.claude_model or None)
        report_path = Path(bpy.path.abspath(f"//{config.build_report}"))
        config = replace(config, build_report=report_path)
        try:
            _triage_session.run(AnthropicClaudeClient(), config, BuildReport(config.build_report))
        except (RuntimeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        proposed = sum(state.proposal is not None for state in _triage_session.states.values())
        escalated = sum(state.escalation_reason is not None for state in _triage_session.states.values())
        context.window_manager.asset_validator_triage_summary = f"{proposed} proposed, {escalated} escalated"
        self.report({"INFO"}, f"Agent triage: {proposed} proposed, {escalated} escalated")
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
        layout.operator(ASSETVALIDATOR_OT_run_agent_triage.bl_idname)
        layout.operator(ASSETVALIDATOR_OT_apply_safe_fixes.bl_idname)
        before = context.window_manager.asset_validator_before_count
        after = context.window_manager.asset_validator_after_count
        if before >= 0:
            layout.label(text=f"Findings: {before} → {after}")
        if context.window_manager.asset_validator_triage_summary:
            layout.label(text=f"Agent: {context.window_manager.asset_validator_triage_summary}")
        if _triage_session is not None:
            for state in _triage_session.states.values():
                row = layout.box()
                row.label(text=f"{state.finding['issue']}: {state.finding['object_name']}")
                if state.proposal is not None:
                    row.label(text=f"Confidence: {state.proposal['confidence']:.0%}")
                    row.label(text=state.proposal["reasoning"])
                elif state.escalation_reason:
                    row.label(text=f"Escalated: {state.escalation_reason}")
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
    ASSETVALIDATOR_OT_run_agent_triage,
    ASSETVALIDATOR_OT_check_roblox_compatibility,
    ASSETVALIDATOR_PT_sidebar,
)


def register():
    """Register addon classes with Blender."""
    bpy.types.WindowManager.asset_validator_before_count = bpy.props.IntProperty(default=-1)
    bpy.types.WindowManager.asset_validator_after_count = bpy.props.IntProperty(default=-1)
    bpy.types.WindowManager.asset_validator_roblox_count = bpy.props.IntProperty(default=-1)
    bpy.types.WindowManager.asset_validator_triage_summary = bpy.props.StringProperty(default="")
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister addon classes from Blender."""
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.asset_validator_roblox_count
    del bpy.types.WindowManager.asset_validator_triage_summary
    del bpy.types.WindowManager.asset_validator_after_count
    del bpy.types.WindowManager.asset_validator_before_count
