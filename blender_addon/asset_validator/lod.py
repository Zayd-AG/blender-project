"""Optional Decimate-based LOD generation with lightweight fidelity metrics."""

from __future__ import annotations

import json
from pathlib import Path

import bpy


def generate_lods(obj, reductions: tuple[float, ...] = (0.5, 0.25, 0.1)) -> list[dict]:
    """Create LOD object copies and return actual triangle/fidelity measurements."""
    if obj.type != "MESH":
        raise ValueError("LOD generation requires a mesh object.")
    original_vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    results = []
    for ratio in reductions:
        lod = obj.copy()
        lod.data = obj.data.copy()
        lod.name = f"{obj.name}_LOD{round(ratio * 100)}"
        for collection in obj.users_collection:
            collection.objects.link(lod)
        modifier = lod.modifiers.new("LOD Decimate", "DECIMATE")
        modifier.ratio = ratio
        _apply_modifier(lod, modifier.name)
        triangles = sum(max(0, len(polygon.vertices) - 2) for polygon in lod.data.polygons)
        results.append(
            {"object_name": lod.name, "target_ratio": ratio, "triangles": triangles,
             "mean_vertex_distance": _mean_nearest_distance(original_vertices, lod)},
        )
    return results


def append_lod_report(output_directory: Path, source_name: str, results: list[dict]) -> None:
    """Append the LOD table to the existing batch build report and JSON report."""
    output_directory.mkdir(parents=True, exist_ok=True)
    lines = [f"\n## LOD Generation: {source_name}", "", "| LOD | Target reduction | Actual triangles | Mean vertex distance |", "| --- | ---: | ---: | ---: |"]
    lines.extend(f"| {item['object_name']} | {item['target_ratio']:.0%} | {item['triangles']} | {item['mean_vertex_distance']:.6f} |" for item in results)
    markdown_path = output_directory / "build_report.md"
    with markdown_path.open("a", encoding="utf-8") as report:
        report.write("\n".join(lines) + "\n")
    json_path = output_directory / "build_report.json"
    payload = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
    payload.setdefault("lod_reports", {})[source_name] = results
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _apply_modifier(obj, modifier_name: str) -> None:
    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previous_selected = [item for item in view_layer.objects if item.select_get()]
    try:
        for item in previous_selected:
            item.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=modifier_name)
    finally:
        obj.select_set(False)
        for item in previous_selected:
            item.select_set(True)
        view_layer.objects.active = previous_active


def _mean_nearest_distance(original_vertices, lod) -> float:
    lod_vertices = [lod.matrix_world @ vertex.co for vertex in lod.data.vertices]
    if not original_vertices or not lod_vertices:
        return 0.0
    return sum(min((source - target).length for target in lod_vertices) for source in original_vertices) / len(original_vertices)
