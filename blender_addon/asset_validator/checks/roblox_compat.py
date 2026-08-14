"""Roblox-specific import compatibility checks and deterministic repairs."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Literal, TypedDict

import bmesh

Severity = Literal["low", "medium", "high"]


class RobloxFinding(TypedDict):
    """A Roblox compatibility finding."""

    object_name: str
    issue: str
    severity: Severity
    description: str
    auto_fixable: bool


@dataclass(frozen=True)
class RobloxConfig:
    """Project-level Roblox importer expectations loaded from the profile."""

    meters_per_stud: float
    min_studs: float
    max_studs: float
    rig_type: str
    required_bones: tuple[str, ...]
    influence_epsilon: float = 0.00001


def load_roblox_profile(rig_type: str | None = None) -> RobloxConfig:
    """Load the packaged profile, optionally choosing R6 or R15."""
    profile_path = Path(__file__).parent.parent / "config" / "roblox_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    selected_rig = rig_type or profile["target_rig"]
    if selected_rig not in profile["rigs"]:
        raise ValueError(f"Unknown Roblox rig type: {selected_rig}")
    return RobloxConfig(
        meters_per_stud=float(profile["meters_per_stud"]),
        min_studs=float(profile["stud_range"]["min"]),
        max_studs=float(profile["stud_range"]["max"]),
        rig_type=selected_rig,
        required_bones=tuple(profile["rigs"][selected_rig]["required_bones"]),
    )


def validate_roblox_compatibility(
    objects: Iterable[object], config: RobloxConfig | None = None
) -> list[RobloxFinding]:
    """Return Roblox-specific findings without reading selection or UI state.

    Rig validation intentionally checks required bone names and structure only.
    It does not perform retargeting, infer bone orientation, or rename bones.
    """
    settings = config or load_roblox_profile()
    findings: list[RobloxFinding] = []
    checked_armatures: set[str] = set()

    for obj in objects:
        object_type = getattr(obj, "type", None)
        if object_type == "ARMATURE":
            _check_rig(obj, settings, findings, checked_armatures)
        elif object_type == "MESH":
            _check_scale(obj, settings, findings)
            _check_bone_influences(obj, settings, findings)
            _check_materials(obj, findings)
            for modifier in obj.modifiers:
                if modifier.type == "ARMATURE" and modifier.object is not None:
                    _check_rig(modifier.object, settings, findings, checked_armatures)

    return findings


def scale_object_to_stud_range(obj, config: RobloxConfig | None = None) -> bool:
    """Uniformly scale an object into the configured stud range when possible."""
    settings = config or load_roblox_profile()
    dimensions = [abs(value) / settings.meters_per_stud for value in obj.dimensions]
    non_zero = [value for value in dimensions if value > 0]
    if not non_zero:
        return False
    lower_factor = max(settings.min_studs / value for value in non_zero)
    upper_factor = min(settings.max_studs / value for value in non_zero)
    if lower_factor > upper_factor:
        return False
    factor = 1.0
    if min(non_zero) < settings.min_studs:
        factor = lower_factor
    elif max(non_zero) > settings.max_studs:
        factor = upper_factor
    if factor == 1.0:
        return False
    obj.scale = tuple(value * factor for value in obj.scale)
    return True


def prune_bone_influences(obj, max_influences: int = 4, epsilon: float = 0.00001) -> int:
    """Keep highest vertex-group weights and normalize each affected vertex."""
    pruned_vertices = 0
    for vertex in obj.data.vertices:
        influences = [group for group in vertex.groups if group.weight > epsilon]
        if len(influences) <= max_influences:
            continue
        influences.sort(key=lambda group: group.weight, reverse=True)
        kept = influences[:max_influences]
        total = sum(group.weight for group in kept)
        for group in influences:
            obj.vertex_groups[group.group].remove([vertex.index])
        for group in kept:
            obj.vertex_groups[group.group].add([vertex.index], group.weight / total, "REPLACE")
        pruned_vertices += 1
    return pruned_vertices


def _add(
    findings: list[RobloxFinding],
    object_name: str,
    issue: str,
    severity: Severity,
    description: str,
    auto_fixable: bool,
) -> None:
    findings.append(
        {
            "object_name": object_name,
            "issue": issue,
            "severity": severity,
            "description": description,
            "auto_fixable": auto_fixable,
        }
    )


def _check_scale(obj, config: RobloxConfig, findings: list[RobloxFinding]) -> None:
    dimensions = tuple(abs(value) / config.meters_per_stud for value in obj.dimensions)
    if any(value < config.min_studs or value > config.max_studs for value in dimensions):
        formatted = ", ".join(f"{value:.3f}" for value in dimensions)
        _add(
            findings,
            obj.name,
            "roblox_scale_out_of_range",
            "medium",
            f"Scaled dimensions are ({formatted}) studs; expected {config.min_studs}-{config.max_studs}.",
            True,
        )


def _check_bone_influences(obj, config: RobloxConfig, findings: list[RobloxFinding]) -> None:
    if not any(modifier.type == "ARMATURE" for modifier in obj.modifiers):
        return
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        over_limit = sum(
            sum(group.weight > config.influence_epsilon for group in obj.data.vertices[vert.index].groups) > 4
            for vert in bm.verts
        )
    finally:
        bm.free()
    if over_limit:
        _add(
            findings,
            obj.name,
            "roblox_bone_influence_limit",
            "high",
            f"{over_limit} vertex/vertices have more than 4 bone influences.",
            True,
        )


def _check_rig(
    armature, config: RobloxConfig, findings: list[RobloxFinding], checked_armatures: set[str]
) -> None:
    if armature.name in checked_armatures:
        return
    checked_armatures.add(armature.name)
    bone_names = {bone.name for bone in armature.data.bones}
    missing = [bone for bone in config.required_bones if bone not in bone_names]
    if not missing:
        return
    suggestions = []
    for required in missing:
        close = get_close_matches(required, bone_names, n=1, cutoff=0.6)
        if close:
            suggestions.append(f"{required} (possible match: {close[0]})")
    description = f"{config.rig_type} is missing required bones: {', '.join(missing)}."
    if suggestions:
        description += f" Possible name matches: {', '.join(suggestions)}."
    _add(findings, armature.name, "roblox_rig_structure", "high", description, False)


def _check_materials(obj, findings: list[RobloxFinding]) -> None:
    for material in obj.data.materials:
        if material is None or not _has_base_color_image(material):
            material_name = "empty material slot" if material is None else material.name
            _add(
                findings,
                obj.name,
                "roblox_missing_albedo_image",
                "medium",
                f"Material '{material_name}' has no connected base color/albedo image.",
                False,
            )


def _has_base_color_image(material) -> bool:
    if not material.use_nodes or material.node_tree is None:
        return False
    principled_nodes = [node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"]
    for node in principled_nodes:
        base_color = node.inputs.get("Base Color")
        if base_color is not None and any(link.from_node.type == "TEX_IMAGE" for link in base_color.links):
            return True
    return False
