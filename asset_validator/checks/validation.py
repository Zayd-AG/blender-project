"""Mesh validation checks with no Blender UI or context dependencies."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Literal, TypedDict

import bmesh


Severity = Literal["low", "medium", "high"]


class Finding(TypedDict):
    """A single asset-validation result."""

    object_name: str
    issue: str
    severity: Severity
    description: str
    auto_fixable: bool


@dataclass(frozen=True)
class ValidationConfig:
    """Project-specific expectations used by :func:`validate_assets`."""

    expected_location: tuple[float, float, float] = (0.0, 0.0, 0.0)
    expected_rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    expected_scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    transform_tolerance: float = 0.00001
    name_pattern: str = r"^SM_[A-Za-z0-9_]+$"
    triangle_budget: int = 50_000
    max_texture_size: int = 4096
    uv_area_epsilon: float = 0.00000001


def validate_assets(
    objects: Iterable[object], config: ValidationConfig | None = None
) -> list[Finding]:
    """Validate mesh objects and return findings without using UI context.

    ``objects`` may contain Blender mesh objects, or ``(name, bmesh)`` tuples
    when a caller already owns BMesh data. Non-mesh objects are ignored.
    """
    settings = config or ValidationConfig()
    pattern = re.compile(settings.name_pattern)
    findings: list[Finding] = []

    for item in objects:
        target = _as_target(item)
        if target is None:
            continue
        object_name, mesh_name, bm, obj, owns_bmesh = target
        try:
            _check_non_manifold(bm, object_name, findings)
            _check_uvs(bm, object_name, settings, findings)
            _check_ngons(bm, object_name, findings)
            _check_triangle_budget(bm, object_name, settings, findings)
            _check_name(object_name, mesh_name, pattern, findings)
            if obj is not None:
                _check_transforms(obj, object_name, settings, findings)
                _check_textures(obj, object_name, settings, findings)
        finally:
            if owns_bmesh:
                bm.free()

    return findings


def _as_target(item: object):
    if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], bmesh.types.BMesh):
        return item[0], item[0], item[1], None, False

    if getattr(item, "type", None) != "MESH":
        return None

    bm = bmesh.new()
    bm.from_mesh(item.data)
    return item.name, item.data.name, bm, item, True


def _add(
    findings: list[Finding],
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


def _check_non_manifold(bm, object_name: str, findings: list[Finding]) -> None:
    edge_count = sum(not edge.is_manifold for edge in bm.edges)
    vert_count = sum(not vert.is_manifold for vert in bm.verts)
    if edge_count:
        _add(
            findings,
            object_name,
            "non_manifold_edges",
            "high",
            f"Contains {edge_count} non-manifold edge(s).",
            False,
        )
    if vert_count:
        _add(
            findings,
            object_name,
            "non_manifold_vertices",
            "high",
            f"Contains {vert_count} non-manifold vertex/vertices.",
            False,
        )


def _check_uvs(bm, object_name: str, config: ValidationConfig, findings: list[Finding]) -> None:
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        _add(findings, object_name, "missing_uv_map", "high", "Mesh has no UV map.", False)
        return

    degenerate_faces = sum(_uv_face_area(face, uv_layer) <= config.uv_area_epsilon for face in bm.faces)
    if degenerate_faces:
        _add(
            findings,
            object_name,
            "degenerate_uvs",
            "high",
            f"Contains {degenerate_faces} face(s) with zero-area UVs.",
            True,
        )


def _uv_face_area(face, uv_layer) -> float:
    points = [loop[uv_layer].uv for loop in face.loops]
    return abs(
        sum(
            point.x * points[(index + 1) % len(points)].y
            - points[(index + 1) % len(points)].x * point.y
            for index, point in enumerate(points)
        )
    ) * 0.5


def _check_ngons(bm, object_name: str, findings: list[Finding]) -> None:
    ngon_count = sum(len(face.verts) > 4 for face in bm.faces)
    if ngon_count:
        _add(
            findings,
            object_name,
            "ngons",
            "medium",
            f"Contains {ngon_count} face(s) with more than four vertices.",
            True,
        )


def _check_triangle_budget(
    bm, object_name: str, config: ValidationConfig, findings: list[Finding]
) -> None:
    triangle_count = sum(max(0, len(face.verts) - 2) for face in bm.faces)
    if triangle_count > config.triangle_budget:
        _add(
            findings,
            object_name,
            "triangle_budget_exceeded",
            "medium",
            f"Has {triangle_count} triangles; budget is {config.triangle_budget}.",
            False,
        )


def _check_name(
    object_name: str, mesh_name: str, pattern: re.Pattern[str], findings: list[Finding]
) -> None:
    invalid = [name for name in (object_name, mesh_name) if not pattern.fullmatch(name)]
    if invalid:
        _add(
            findings,
            object_name,
            "naming_convention",
            "low",
            f"Name(s) do not match the configured pattern: {', '.join(invalid)}.",
            True,
        )


def _check_transforms(obj, object_name: str, config: ValidationConfig, findings: list[Finding]) -> None:
    expected_values = (
        ("location", obj.location, config.expected_location),
        ("rotation", obj.rotation_euler, config.expected_rotation),
        ("scale", obj.scale, config.expected_scale),
    )
    for label, actual, expected in expected_values:
        if any(abs(value - expected[index]) > config.transform_tolerance for index, value in enumerate(actual)):
            _add(
                findings,
                object_name,
                f"unapplied_{label}",
                "medium",
                f"{label.title()} is {tuple(actual)}; expected {expected}.",
                True,
            )


def _check_textures(obj, object_name: str, config: ValidationConfig, findings: list[Finding]) -> None:
    seen_images: set[object] = set()
    for material in obj.data.materials:
        if material is None or not material.use_nodes or material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            image = getattr(node, "image", None)
            is_connected_image = node.type == "TEX_IMAGE" and any(
                socket.is_linked for socket in node.outputs
            )
            if not is_connected_image or image is None or image in seen_images:
                continue
            seen_images.add(image)
            width, height = image.size
            if max(width, height) > config.max_texture_size:
                _add(
                    findings,
                    object_name,
                    "texture_resolution_exceeded",
                    "medium",
                    f"Image '{image.name}' is {width}x{height}; maximum is {config.max_texture_size}px.",
                    False,
                )
