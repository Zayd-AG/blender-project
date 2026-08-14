"""Blender-runtime pytest coverage for the validation module."""

import bmesh
import bpy
import pytest

from asset_validator.checks import ValidationConfig, validate_assets


def _add_uvs(bm, degenerate: bool = False) -> None:
    uv_layer = bm.loops.layers.uv.new("UVMap")
    coordinates = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    for face in bm.faces:
        for index, loop in enumerate(face.loops):
            loop[uv_layer].uv = (0.0, 0.0) if degenerate else coordinates[index]


def _object_from_bmesh(name: str = "SM_Clean", with_uvs: bool = True, degenerate_uvs: bool = False):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    if with_uvs:
        _add_uvs(bm, degenerate_uvs)
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


@pytest.fixture
def objects():
    created = []
    yield created
    for obj in created:
        bpy.data.objects.remove(obj, do_unlink=True)


def _issues(obj, config: ValidationConfig | None = None):
    return {finding["issue"] for finding in validate_assets([obj], config)}


def test_clean_mesh_has_no_findings(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    assert validate_assets([obj]) == []


def test_missing_uv_map(objects):
    obj = _object_from_bmesh(with_uvs=False)
    objects.append(obj)
    findings = validate_assets([obj])
    assert _issues(obj) == {"missing_uv_map"}
    assert set(findings[0]) == {"object_name", "issue", "severity", "description", "auto_fixable"}


def test_degenerate_uvs(objects):
    obj = _object_from_bmesh(degenerate_uvs=True)
    objects.append(obj)
    assert "degenerate_uvs" in _issues(obj)


def test_exactly_one_non_manifold_edge(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    first = bm.verts.new((3, 0, 0))
    second = bm.verts.new((4, 0, 0))
    bm.edges.new((first, second))
    bm.to_mesh(obj.data)
    bm.free()
    findings = validate_assets([obj])
    edge_finding = next(item for item in findings if item["issue"] == "non_manifold_edges")
    assert edge_finding["description"] == "Contains 1 non-manifold edge(s)."


def test_open_mesh_non_manifold(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.delete(bm, geom=[next(iter(bm.faces))], context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    assert {"non_manifold_edges", "non_manifold_vertices"} <= _issues(obj)


@pytest.mark.parametrize(
    ("attribute", "value", "issue"),
    [
        ("location", (1.0, 0.0, 0.0), "unapplied_location"),
        ("rotation_euler", (0.1, 0.0, 0.0), "unapplied_rotation"),
        ("scale", (2.0, 1.0, 1.0), "unapplied_scale"),
    ],
)
def test_unapplied_transforms(objects, attribute, value, issue):
    obj = _object_from_bmesh()
    objects.append(obj)
    setattr(obj, attribute, value)
    assert issue in _issues(obj)


def test_project_transform_defaults_are_configurable(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    obj.location = (1.0, 0.0, 0.0)
    config = ValidationConfig(expected_location=(1.0, 0.0, 0.0))
    assert "unapplied_location" not in _issues(obj, config)


def test_ngon_is_reported(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    verts = [bm.verts.new((index, 3, 0)) for index in range(5)]
    bm.faces.new(verts)
    bm.to_mesh(obj.data)
    bm.free()
    assert "ngons" in _issues(obj)


def test_quad_mesh_is_not_an_ngon(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    assert "ngons" not in _issues(obj)


def test_default_blender_name_is_rejected(objects):
    obj = _object_from_bmesh("Cube.001")
    objects.append(obj)
    assert "naming_convention" in _issues(obj)


def test_configured_name_pattern_is_accepted(objects):
    obj = _object_from_bmesh("GEO_Hero")
    objects.append(obj)
    obj.data.name = "GEO_HeroMesh"
    assert "naming_convention" not in _issues(obj, ValidationConfig(name_pattern=r"^GEO_[A-Za-z]+$"))


def test_triangle_budget_exactly_at_limit_is_allowed(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    assert "triangle_budget_exceeded" not in _issues(obj, ValidationConfig(triangle_budget=12))


def test_triangle_budget_over_limit_is_reported(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    assert "triangle_budget_exceeded" in _issues(obj, ValidationConfig(triangle_budget=11))


def _add_connected_image(obj, name: str, size: int):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    texture = tree.nodes.new("ShaderNodeTexImage")
    image = bpy.data.images.new(name, width=size, height=size)
    texture.image = image
    principled = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    tree.links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    obj.data.materials.append(material)
    return material, image


def test_oversized_connected_texture_is_reported(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    material, image = _add_connected_image(obj, "LargeTexture", 2049)
    assert "texture_resolution_exceeded" in _issues(obj, ValidationConfig(max_texture_size=2048))
    bpy.data.images.remove(image)
    bpy.data.materials.remove(material)


def test_texture_at_limit_is_allowed(objects):
    obj = _object_from_bmesh()
    objects.append(obj)
    material, image = _add_connected_image(obj, "LimitTexture", 2048)
    assert "texture_resolution_exceeded" not in _issues(obj, ValidationConfig(max_texture_size=2048))
    bpy.data.images.remove(image)
    bpy.data.materials.remove(material)


def test_non_mesh_objects_are_ignored():
    light = bpy.data.lights.new("Light", "POINT")
    obj = bpy.data.objects.new("Light", light)
    bpy.context.collection.objects.link(obj)
    try:
        assert validate_assets([obj]) == []
    finally:
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.lights.remove(light)


def test_bmesh_target_is_supported():
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2)
    _add_uvs(bm)
    try:
        assert validate_assets([("SM_BMesh", bm)]) == []
    finally:
        bm.free()
