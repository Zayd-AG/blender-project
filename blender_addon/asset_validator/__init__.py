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

from .batch_export import RobloxUploadConfig, batch_export
from .lod import append_lod_report, generate_lods

from .agent import (
    AnthropicClaudeClient,
    BuildReport,
    EmbeddingConfig,
    OpenAICompatibleEmbeddingClient,
    PrecedentStore,
    TriageSession,
    apply_approved_agent_resolutions,
    build_finding_contexts,
    load_agent_config,
    load_precedent_profile,
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
_precedent_store: PrecedentStore | None = None


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
    embedding_endpoint: bpy.props.StringProperty(name="Embedding Endpoint", default="")
    embedding_model: bpy.props.StringProperty(name="Embedding Model", default="")
    roblox_api_key: bpy.props.StringProperty(name="Roblox API Key", subtype="PASSWORD", default="")
    roblox_creator_user_id: bpy.props.StringProperty(name="Roblox Creator User ID", default="")

    def draw(self, context):
        self.layout.prop(self, "roblox_rig_type")
        self.layout.prop(self, "claude_model")
        self.layout.prop(self, "embedding_endpoint")
        self.layout.prop(self, "embedding_model")
        self.layout.prop(self, "roblox_api_key")
        self.layout.prop(self, "roblox_creator_user_id")


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
        global _triage_session, _precedent_store
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
        precedent_profile = load_precedent_profile()
        precedent_path = Path(bpy.path.abspath(f"//{precedent_profile['database']}"))
        try:
            _precedent_store = PrecedentStore(
                precedent_path,
                OpenAICompatibleEmbeddingClient(
                    EmbeddingConfig(
                        preferences.embedding_endpoint or precedent_profile["embedding_endpoint"],
                        preferences.embedding_model or precedent_profile["embedding_model"],
                        __import__("os").getenv("ASSET_VALIDATOR_EMBEDDING_API_KEY"),
                        int(precedent_profile["top_k"]),
                    )
                ),
            )
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        _triage_session = TriageSession(
            findings,
            build_finding_contexts(findings, objects, validation_config, roblox_config),
            objects,
            _precedent_store,
            int(precedent_profile["top_k"]),
        )
        context.window_manager.asset_validator_precedent_count = _precedent_store.count()
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


class ASSETVALIDATOR_OT_record_human_resolution(bpy.types.Operator):
    """Record a human accept, reject, or override as a reusable precedent."""

    bl_idname = "asset_validator.record_human_resolution"
    bl_label = "Record Resolution"
    finding_id: bpy.props.StringProperty()
    decision: bpy.props.EnumProperty(items=(("accept", "Accept", "Accept suggestion"), ("reject", "Reject", "Reject suggestion"), ("override", "Override", "Enter a different resolution")))
    override_text: bpy.props.StringProperty(name="Override resolution", default="")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self) if self.decision == "override" else self.execute(context)

    def draw(self, context):
        self.layout.prop(self, "override_text")

    def execute(self, context):
        if _triage_session is None or _precedent_store is None:
            self.report({"ERROR"}, "Run Agent Triage before recording a resolution.")
            return {"CANCELLED"}
        state = _triage_session.states[self.finding_id]
        resolution = state.proposal["resolution"] if self.decision == "accept" and state.proposal else {"action": self.decision, "text": self.override_text}
        _precedent_store.add(state.finding["issue"], __import__("json").dumps(state.context), resolution, state.proposal["confidence"] if state.proposal else 1.0, "human")
        context.window_manager.asset_validator_precedent_count = _precedent_store.count()
        self.report({"INFO"}, "Human resolution added to precedents")
        return {"FINISHED"}


class ASSETVALIDATOR_OT_batch_export(bpy.types.Operator):
    """Validate every mesh in a collection and export passing assets."""

    bl_idname = "asset_validator.batch_export"
    bl_label = "Batch Export"

    def execute(self, context):
        collection = context.scene.asset_validator_export_collection
        if collection is None:
            self.report({"ERROR"}, "Choose an export collection first.")
            return {"CANCELLED"}
        output_dir = Path(bpy.path.abspath(context.scene.asset_validator_output_directory))
        preferences = context.preferences.addons[__package__].preferences
        config = RobloxUploadConfig(
            preferences.roblox_api_key or __import__("os").getenv("ROBLOX_OPEN_CLOUD_API_KEY"),
            preferences.roblox_creator_user_id or __import__("os").getenv("ROBLOX_CREATOR_USER_ID"),
        )
        report = batch_export(
            collection,
            output_dir,
            upload_to_roblox=context.scene.asset_validator_upload_to_roblox,
            upload_config=config,
            roblox_rig_type=preferences.roblox_rig_type,
        )
        passed = sum(asset["status"] == "passed" for asset in report["assets"])
        self.report({"INFO"}, f"Batch export complete: {passed}/{len(report['assets'])} passed")
        return {"FINISHED"}


class ASSETVALIDATOR_OT_generate_lods(bpy.types.Operator):
    """Generate optional decimated LOD copies for the active mesh."""

    bl_idname = "asset_validator.generate_lods"
    bl_label = "Generate LODs"

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a mesh object first.")
            return {"CANCELLED"}
        try:
            reductions = tuple(float(value.strip()) for value in context.scene.asset_validator_lod_ratios.split(","))
            if not 2 <= len(reductions) <= 3 or any(not 0 < value < 1 for value in reductions):
                raise ValueError
        except ValueError:
            self.report({"ERROR"}, "Use two or three comma-separated ratios between 0 and 1.")
            return {"CANCELLED"}
        results = generate_lods(obj, reductions)
        append_lod_report(Path(bpy.path.abspath(context.scene.asset_validator_output_directory)), obj.name, results)
        self.report({"INFO"}, f"Generated {len(results)} LOD levels")
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
                for decision, label in (("accept", "Accept"), ("reject", "Reject"), ("override", "Override")):
                    action = row.operator(ASSETVALIDATOR_OT_record_human_resolution.bl_idname, text=label)
                    action.finding_id = state.finding_id
                    action.decision = decision
        roblox_box = layout.box()
        roblox_box.label(text="Roblox Compatibility")
        roblox_box.operator(ASSETVALIDATOR_OT_check_roblox_compatibility.bl_idname)
        roblox_count = context.window_manager.asset_validator_roblox_count
        if roblox_count >= 0:
            roblox_box.label(text=f"Findings: {roblox_count}")
        layout.label(text=f"Precedents learned: {context.window_manager.asset_validator_precedent_count}")
        export_box = layout.box()
        export_box.label(text="Batch Export")
        export_box.prop(context.scene, "asset_validator_export_collection")
        export_box.prop(context.scene, "asset_validator_output_directory")
        export_box.prop(context.scene, "asset_validator_upload_to_roblox", text="Upload to Roblox")
        export_box.operator(ASSETVALIDATOR_OT_batch_export.bl_idname)
        lod_box = layout.box()
        lod_box.label(text="LOD Generation")
        lod_box.prop(context.scene, "asset_validator_lod_ratios", text="Ratios")
        lod_box.operator(ASSETVALIDATOR_OT_generate_lods.bl_idname)


CLASSES = (
    ASSETVALIDATOR_Preferences,
    ASSETVALIDATOR_OT_run_validation,
    ASSETVALIDATOR_OT_apply_safe_fixes,
    ASSETVALIDATOR_OT_run_agent_triage,
    ASSETVALIDATOR_OT_record_human_resolution,
    ASSETVALIDATOR_OT_batch_export,
    ASSETVALIDATOR_OT_generate_lods,
    ASSETVALIDATOR_OT_check_roblox_compatibility,
    ASSETVALIDATOR_PT_sidebar,
)


def register():
    """Register addon classes with Blender."""
    bpy.types.WindowManager.asset_validator_before_count = bpy.props.IntProperty(default=-1)
    bpy.types.WindowManager.asset_validator_after_count = bpy.props.IntProperty(default=-1)
    bpy.types.WindowManager.asset_validator_roblox_count = bpy.props.IntProperty(default=-1)
    bpy.types.WindowManager.asset_validator_triage_summary = bpy.props.StringProperty(default="")
    bpy.types.WindowManager.asset_validator_precedent_count = bpy.props.IntProperty(default=0)
    bpy.types.Scene.asset_validator_export_collection = bpy.props.PointerProperty(type=bpy.types.Collection)
    bpy.types.Scene.asset_validator_output_directory = bpy.props.StringProperty(subtype="DIR_PATH", default="//exports")
    bpy.types.Scene.asset_validator_upload_to_roblox = bpy.props.BoolProperty(default=False)
    bpy.types.Scene.asset_validator_lod_ratios = bpy.props.StringProperty(default="0.5, 0.25, 0.1")
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister addon classes from Blender."""
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.asset_validator_roblox_count
    del bpy.types.WindowManager.asset_validator_triage_summary
    del bpy.types.WindowManager.asset_validator_precedent_count
    del bpy.types.Scene.asset_validator_upload_to_roblox
    del bpy.types.Scene.asset_validator_output_directory
    del bpy.types.Scene.asset_validator_export_collection
    del bpy.types.Scene.asset_validator_lod_ratios
    del bpy.types.WindowManager.asset_validator_after_count
    del bpy.types.WindowManager.asset_validator_before_count
