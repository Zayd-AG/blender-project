"""Blender-runtime pytest coverage for Roblox compatibility checks.

Rig tests are intentionally name/structure checks, not retargeting tests.
"""

import bmesh
import bpy
import pytest

from asset_validator.checks.roblox_compat import (
    RobloxConfig,
    load_roblox_profile,
    prune_bone_influences,
    validate_roblox_compatibility,
)


def _mesh_object(name="SM_Roblox"):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _armature(name, bone_names):
    armature_data = bpy.data.armatures.new(f"{name}_Data")
    armature = bpy.data.objects.new(name, armature_data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name in bone_names:
        armature_data.edit_bones.new(bone_name)
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    return armature


@pytest.fixture
def created():
    objects = []
    yield objects
    for obj in objects:
        bpy.data.objects.remove(obj, do_unlink=True)


def test_r15_compliant_armature_has_no_rig_finding(created):
    config = load_roblox_profile("R15")
    armature = _armature("R15", config.required_bones)
    created.append(armature)
    assert validate_roblox_compatibility([armature], config) == []


def test_missing_r15_bones_include_close_name_suggestion(created):
    config = load_roblox_profile("R15")
    armature = _armature("IncompleteR15", ["head", "UpperTorso"])
    created.append(armature)
    finding = validate_roblox_compatibility([armature], config)[0]
    assert finding["issue"] == "roblox_rig_structure"
    assert "HumanoidRootPart" in finding["description"]
    assert "Head (possible match: head)" in finding["description"]
    assert finding["auto_fixable"] is False


def test_six_bone_influences_are_reported_and_pruned(created):
    mesh = _mesh_object()
    armature = _armature("InfluenceRig", [f"Bone{index}" for index in range(6)])
    created.extend((mesh, armature))
    modifier = mesh.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature
    for index in range(6):
        group = mesh.vertex_groups.new(name=f"Bone{index}")
        group.add([0], index + 1, "REPLACE")
    config = load_roblox_profile("R15")
    issues = {finding["issue"] for finding in validate_roblox_compatibility([mesh], config)}
    assert "roblox_bone_influence_limit" in issues
    assert prune_bone_influences(mesh) == 1
    assert len(mesh.data.vertices[0].groups) == 4
    assert sum(group.weight for group in mesh.data.vertices[0].groups) == pytest.approx(1.0)


def test_scaled_dimensions_outside_stud_range_are_reported(created):
    mesh = _mesh_object()
    created.append(mesh)
    config = RobloxConfig(0.28, 0.1, 1.0, "R15", ())
    issues = {finding["issue"] for finding in validate_roblox_compatibility([mesh], config)}
    assert "roblox_scale_out_of_range" in issues


def test_clean_mesh_control_case_has_no_findings(created):
    mesh = _mesh_object()
    created.append(mesh)
    config = RobloxConfig(0.28, 0.1, 100.0, "R15", ())
    assert validate_roblox_compatibility([mesh], config) == []
