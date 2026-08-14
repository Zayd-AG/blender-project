"""Programmatic Blender fixtures with known validator ground-truth labels."""

import bmesh
import bpy


def _cube(name, *, uvs=True, degenerate=False):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    if uvs:
        layer = bm.loops.layers.uv.new("UVMap")
        points = ((0, 0), (1, 0), (1, 1), (0, 1))
        for face in bm.faces:
            for index, loop in enumerate(face.loops):
                loop[layer].uv = (0, 0) if degenerate else points[index]
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def build_fixtures():
    """Return ``[(object, expected_issue_set)]`` and leave objects in the scene."""
    fixtures = []
    fixtures.append((_cube("SM_CleanA"), set()))
    fixtures.append((_cube("SM_CleanB"), set()))
    fixtures.append((_cube("SM_NoUV", uvs=False), {"missing_uv_map"}))
    fixtures.append((_cube("SM_DegenerateUV", degenerate=True), {"degenerate_uvs"}))
    bad_name = _cube("Cube.001")
    fixtures.append((bad_name, {"naming_convention"}))
    scaled = _cube("SM_Scaled")
    scaled.scale = (2, 1, 1)
    fixtures.append((scaled, {"unapplied_scale"}))
    budget = _cube("SM_Budget")
    fixtures.append((budget, {"triangle_budget_exceeded"}))
    texture = _cube("SM_Texture")
    material = bpy.data.materials.new("TextureMaterial")
    material.use_nodes = True
    image = bpy.data.images.new("LargeTexture", width=2049, height=2049)
    node = material.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    bsdf = next(item for item in material.node_tree.nodes if item.type == "BSDF_PRINCIPLED")
    material.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    texture.data.materials.append(material)
    fixtures.append((texture, {"texture_resolution_exceeded"}))
    roblox_scale = _cube("SM_RobloxScale")
    fixtures.append((roblox_scale, {"roblox_scale_out_of_range"}))
    arm_data = bpy.data.armatures.new("FixtureRigData")
    armature = bpy.data.objects.new("FixtureRig", arm_data)
    bpy.context.collection.objects.link(armature)
    influence = _cube("SM_Influences")
    modifier = influence.modifiers.new("Armature", "ARMATURE")
    modifier.object = armature
    for index in range(6):
        group = influence.vertex_groups.new(name=f"Bone{index}")
        group.add([0], 1 / 6, "REPLACE")
    fixtures.append((influence, {"roblox_bone_influence_limit"}))
    no_albedo = _cube("SM_NoAlbedo")
    no_albedo.data.materials.append(bpy.data.materials.new("PlainMaterial"))
    fixtures.append((no_albedo, {"roblox_missing_albedo_image"}))
    rig_mesh = _cube("SM_RigMesh")
    rig_modifier = rig_mesh.modifiers.new("Armature", "ARMATURE")
    rig_modifier.object = armature
    fixtures.append((rig_mesh, {"roblox_rig_structure"}))
    return fixtures


def cleanup():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
