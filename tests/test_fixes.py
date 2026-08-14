"""Blender-runtime pytest coverage for safe automatic fixes."""

import bmesh
import bpy
import pytest

from asset_validator.checks import ValidationConfig
from asset_validator.fixes import apply_safe_fixes


def _object_with_ngon(name="SM_FixTarget"):
    bm = bmesh.new()
    vertices = [
        bm.verts.new((0, 0, 0)),
        bm.verts.new((2, 0, 0)),
        bm.verts.new((3, 1, 0)),
        bm.verts.new((1, 2, 0)),
        bm.verts.new((-1, 1, 0)),
    ]
    bm.faces.new(vertices)
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for index, loop in enumerate(next(iter(bm.faces)).loops):
        loop[uv_layer].uv = ((0, 0), (1, 0), (1, 1), (0, 1), (0.5, 1.5))[index]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


@pytest.fixture
def fix_target():
    obj = _object_with_ngon()
    yield obj
    bpy.data.objects.remove(obj, do_unlink=True)


def test_safe_fixes_triangulate_and_apply_transforms(fix_target):
    fix_target.scale = (2.0, 1.0, 1.0)
    result = apply_safe_fixes([fix_target])
    after_issues = {finding["issue"] for finding in result.after}
    assert "ngons" in {finding["issue"] for finding in result.before}
    assert "ngons" not in after_issues
    assert "unapplied_scale" not in after_issues
    assert result.after_count < result.before_count


def test_naming_and_texture_findings_are_not_auto_fixed(fix_target):
    fix_target.name = "Bad Name"
    material = bpy.data.materials.new("TextureMaterial")
    material.use_nodes = True
    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
    image = bpy.data.images.new("Large", width=2049, height=2049)
    texture.image = image
    principled = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    material.node_tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    fix_target.data.materials.append(material)
    try:
        result = apply_safe_fixes([fix_target], ValidationConfig(max_texture_size=2048))
        after_issues = {finding["issue"] for finding in result.after}
        assert "naming_convention" in after_issues
        assert "texture_resolution_exceeded" in after_issues
    finally:
        bpy.data.images.remove(image)
        bpy.data.materials.remove(material)
