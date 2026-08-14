"""Safe, non-interactive repairs for supported validation findings."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable

import bmesh
import bpy

from .checks.validation import Finding, ValidationConfig, validate_assets


SAFE_FIXABLE_ISSUES = frozenset(
    {
        "ngons",
        "unapplied_location",
        "unapplied_rotation",
        "unapplied_scale",
    }
)


@dataclass(frozen=True)
class SafeFixResult:
    """Validation counts and findings from one safe-fix pass."""

    before: list[Finding]
    after: list[Finding]
    fixed_object_names: tuple[str, ...]

    @property
    def before_count(self) -> int:
        return len(self.before)

    @property
    def after_count(self) -> int:
        return len(self.after)


def apply_safe_fixes(
    objects: Iterable[object], config: ValidationConfig | None = None
) -> SafeFixResult:
    """Apply deterministic fixes, then validate again and return the diff.

    Objects with naming, UV, texture, topology, or any other ambiguous finding
    are never changed merely because of that finding. The only actions are
    merging nearby duplicate vertices, triangulating n-gons, recalculating
    normals, and applying transforms on objects with relevant safe findings.
    """
    mesh_objects = [obj for obj in objects if getattr(obj, "type", None) == "MESH"]
    settings = config or ValidationConfig()
    before = validate_assets(mesh_objects, settings)
    fixable_names = {
        finding["object_name"]
        for finding in before
        if finding["issue"] in SAFE_FIXABLE_ISSUES and finding["auto_fixable"]
    }
    fixed_names = []

    for obj in mesh_objects:
        if obj.name not in fixable_names:
            continue
        _fix_mesh_geometry(obj, settings.merge_distance)
        _apply_transforms(obj)
        _recalculate_normals(obj)
        fixed_names.append(obj.name)

    after = validate_assets(mesh_objects, settings)
    return SafeFixResult(before, after, tuple(fixed_names))


def _fix_mesh_geometry(obj, merge_distance: float) -> None:
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_distance)
        ngons = [face for face in bm.faces if len(face.verts) > 4]
        if ngons:
            bmesh.ops.triangulate(bm, faces=ngons)
        bm.to_mesh(obj.data)
        obj.data.update()
    finally:
        bm.free()


@contextmanager
def _active_mesh_object(obj):
    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previous_selected = tuple(item for item in view_layer.objects if item.select_get())
    try:
        for item in previous_selected:
            item.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        yield
    finally:
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        obj.select_set(False)
        for item in previous_selected:
            if item.name in view_layer.objects:
                item.select_set(True)
        view_layer.objects.active = previous_active


def _apply_transforms(obj) -> None:
    with _active_mesh_object(obj):
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def _recalculate_normals(obj) -> None:
    with _active_mesh_object(obj):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
