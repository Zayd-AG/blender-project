"""Collection-scoped validation, export, reporting, and opt-in Roblox upload."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import bpy

from .checks import load_roblox_profile, validate_assets, validate_roblox_compatibility
from .checks.validation import ValidationConfig


@dataclass(frozen=True)
class RobloxUploadConfig:
    api_key: str | None
    creator_user_id: str | None


def batch_export(
    collection,
    output_directory: Path,
    *,
    upload_to_roblox: bool = False,
    upload_config: RobloxUploadConfig | None = None,
    roblox_rig_type: str = "R15",
) -> dict[str, Any]:
    """Export only assets with no high-severity generic or Roblox findings."""
    output_directory.mkdir(parents=True, exist_ok=True)
    assets = []
    generic_config = ValidationConfig()
    roblox_config = load_roblox_profile(roblox_rig_type)
    for obj in collection.all_objects:
        if obj.type != "MESH":
            continue
        findings = validate_assets([obj], generic_config) + validate_roblox_compatibility([obj], roblox_config)
        high_findings = [finding for finding in findings if finding["severity"] == "high"]
        entry: dict[str, Any] = {"object_name": obj.name, "findings": findings, "status": "failed" if high_findings else "passed"}
        if high_findings:
            entry["skip_reason"] = "High-severity validation finding(s)"
            assets.append(entry)
            continue
        fbx_path = output_directory / f"{obj.name}.fbx"
        gltf_path = output_directory / f"{obj.name}.gltf"
        _export_object(obj, fbx_path, gltf_path)
        entry["exports"] = {"fbx": str(fbx_path), "gltf": str(gltf_path)}
        if upload_to_roblox:
            entry["roblox_upload"] = upload_fbx_to_roblox(fbx_path, obj.name, upload_config)
        assets.append(entry)
    report = {"generated_at": datetime.now(UTC).isoformat(), "collection": collection.name, "assets": assets}
    _write_reports(output_directory, report)
    return report


def _export_object(obj, fbx_path: Path, gltf_path: Path) -> None:
    view_layer = bpy.context.view_layer
    previous_active = view_layer.objects.active
    previous_selected = [item for item in view_layer.objects if item.select_get()]
    try:
        for item in previous_selected:
            item.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        bpy.ops.export_scene.fbx(filepath=str(fbx_path), use_selection=True)
        bpy.ops.export_scene.gltf(filepath=str(gltf_path), use_selection=True, export_format="GLTF_SEPARATE")
    finally:
        obj.select_set(False)
        for item in previous_selected:
            item.select_set(True)
        view_layer.objects.active = previous_active


def upload_fbx_to_roblox(
    fbx_path: Path, display_name: str, config: RobloxUploadConfig | None
) -> dict[str, Any]:
    """Create a Roblox Model asset from an FBX; never persist credentials."""
    if config is None or not config.api_key or not config.creator_user_id:
        return {"status": "skipped", "message": "Missing Roblox API key or creator user ID."}
    metadata = {"assetType": "Model", "displayName": display_name, "creationContext": {"creator": {"userId": config.creator_user_id}}}
    body, content_type = _multipart_request(metadata, fbx_path)
    request = Request(
        "https://apis.roblox.com/assets/v1/assets",
        data=body,
        headers={"x-api-key": config.api_key, "Content-Type": content_type},
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:  # nosec B310 - fixed Roblox HTTPS endpoint
            response_data = json.loads(response.read())
        asset_id = response_data.get("assetId") or response_data.get("response", {}).get("assetId")
        return {"status": "success", "asset_id": asset_id, "operation": response_data.get("path")}
    except HTTPError as error:
        return {"status": "error", "http_status": error.code, "message": error.read().decode("utf-8", "replace")[:500]}
    except URLError as error:
        return {"status": "error", "message": str(error.reason)}


def _multipart_request(metadata: dict[str, Any], fbx_path: Path) -> tuple[bytes, str]:
    boundary = f"----AssetValidator{uuid4().hex}"
    file_bytes = fbx_path.read_bytes()
    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"request\"\r\n\r\n{json.dumps(metadata)}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"fileContent\"; filename=\"{fbx_path.name}\"\r\nContent-Type: model/fbx\r\n\r\n".encode(),
        file_bytes,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _write_reports(output_directory: Path, report: dict[str, Any]) -> None:
    (output_directory / "build_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Batch Export Build Report", "", f"Collection: `{report['collection']}`", ""]
    for asset in report["assets"]:
        lines.extend((f"## {asset['object_name']} — {asset['status'].upper()}", ""))
        if asset["findings"]:
            lines.extend(f"- **{finding['severity']}** `{finding['issue']}`: {finding['description']}" for finding in asset["findings"])
        else:
            lines.append("- No findings.")
        if "skip_reason" in asset:
            lines.append(f"- Skipped: {asset['skip_reason']}")
        if "roblox_upload" in asset:
            lines.append(f"- Roblox upload: `{asset['roblox_upload']['status']}` — {asset['roblox_upload']}")
        lines.append("")
    (output_directory / "build_report.md").write_text("\n".join(lines), encoding="utf-8")
