from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from importlib import metadata
from pathlib import Path

from .contracts import ProjectJSON
from .errors import PodcastEditorError, raise_if_cancelled
from .planning import CutPlan


PINNED_VERSION = "0.3.0"


def detect_draft_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        if candidate.is_dir():
            return candidate
        raise PodcastEditorError("draft_root_not_found", f"剪映草稿目录不存在：{candidate}")

    import os

    configured = os.environ.get("JY_PROJECTS_ROOT", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        candidates.append(Path(local_app_data) / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft")
    candidates.append(
        Path.home() / "AppData" / "Local" / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise PodcastEditorError(
        "draft_root_not_found",
        "没有找到剪映 5.9 草稿目录。请设置 JY_PROJECTS_ROOT 或使用 --draft-root。",
    )


def export_jianying_draft(
    project: ProjectJSON,
    plan: CutPlan,
    draft_root: str | Path,
    *,
    draft_name: str | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[str, Path]:
    raise_if_cancelled(cancel_event)
    _require_library()
    try:
        from pyJianYingDraft import AudioMaterial, AudioSegment, DraftFolder, Timerange, TrackSpec, TrackType
    except ImportError as exc:
        raise PodcastEditorError(
            "missing_dependency", "无法载入 pyJianYingDraft==0.3.0。", status=500
        ) from exc

    raise_if_cancelled(cancel_event)
    root = detect_draft_root(draft_root)
    name = _draft_name(draft_name or f"剪播客_{project['title']}_{datetime.now():%Y%m%d_%H%M%S}")
    folder = DraftFolder(str(root))
    raise_if_cancelled(cancel_event)
    try:
        script = folder.create_draft(name, 1920, 1080, fps=30, maintrack_adsorb=False)
    except FileExistsError as exc:
        raise PodcastEditorError("draft_exists", f"剪映草稿已存在：{name}", status=409) from exc

    draft_path = root / name
    try:
        raise_if_cancelled(cancel_event)
        materials = {
            index: AudioMaterial(source["path"], material_name=Path(source["path"]).name)
            for index, source in enumerate(project["sources"])
        }
        for track_plan in plan.tracks:
            raise_if_cancelled(cancel_event)
            track_ref = script.append_track(TrackSpec(TrackType.audio, track_plan.name))
            material = materials[track_plan.source_index]
            for segment_plan in track_plan.segments:
                raise_if_cancelled(cancel_event)
                duration_us = (segment_plan.source_end_ms - segment_plan.source_start_ms) * 1000
                if duration_us <= 0:
                    continue
                segment = AudioSegment(
                    material,
                    Timerange(segment_plan.target_start_ms * 1000, duration_us),
                    source_timerange=Timerange(segment_plan.source_start_ms * 1000, duration_us),
                )
                fade_us = min(10_000, duration_us // 2)
                if fade_us > 0:
                    segment.add_fade(fade_us, fade_us)
                script.add_segment(segment, track_ref)
        raise_if_cancelled(cancel_event)
        script.save()
        raise_if_cancelled(cancel_event)
        _validate_audio_only_draft(draft_path / "draft_content.json", plan, project)
        raise_if_cancelled(cancel_event)
    except BaseException:
        if draft_path.exists():
            import shutil

            shutil.rmtree(draft_path)
        raise
    return name, draft_path


def _require_library() -> None:
    try:
        installed = metadata.version("pyJianYingDraft")
    except metadata.PackageNotFoundError as exc:
        raise PodcastEditorError(
            "missing_dependency", "请先安装 pyJianYingDraft==0.3.0。", status=500
        ) from exc
    if installed != PINNED_VERSION:
        raise PodcastEditorError(
            "wrong_dependency_version",
            f"pyJianYingDraft 版本必须是 {PINNED_VERSION}，当前为 {installed}。",
            status=500,
        )


def _draft_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    if not cleaned:
        raise PodcastEditorError("invalid_draft_name", "剪映草稿名称不能为空。")
    return cleaned[:120]


def _validate_audio_only_draft(path: Path, plan: CutPlan, project: ProjectJSON) -> None:
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PodcastEditorError("invalid_draft", "剪映草稿未能正确写入。", status=500) from exc
    tracks = content.get("tracks")
    if not isinstance(tracks, list) or any(
        not isinstance(track, dict) or track.get("type") != "audio" for track in tracks
    ):
        raise PodcastEditorError("invalid_draft", "剪映草稿包含非音频轨道。", status=500)
    if len(tracks) != len(plan.tracks):
        raise PodcastEditorError("invalid_draft", "剪映草稿的轨道或片段数量不符。", status=500)
    material_section = content.get("materials")
    if not isinstance(material_section, dict) or not isinstance(material_section.get("audios"), list):
        raise PodcastEditorError("invalid_draft", "剪映草稿的音频素材信息无效。", status=500)
    materials = material_section["audios"]
    material_paths = {
        material.get("id"): str(Path(material.get("path", "")).expanduser().resolve())
        for material in materials
        if isinstance(material, dict) and material.get("id")
    }
    for track_json, track_plan in zip(tracks, plan.tracks, strict=True):
        actual_segments = track_json.get("segments")
        if not isinstance(actual_segments, list) or len(actual_segments) != len(track_plan.segments):
            raise PodcastEditorError("invalid_draft", "剪映草稿的轨道或片段数量不符。", status=500)
        expected_source_path = str(Path(project["sources"][track_plan.source_index]["path"]).resolve())
        for segment_json, segment_plan in zip(actual_segments, track_plan.segments, strict=True):
            if not isinstance(segment_json, dict):
                raise PodcastEditorError("invalid_draft", "剪映草稿的音频片段格式无效。", status=500)
            duration_us = (segment_plan.source_end_ms - segment_plan.source_start_ms) * 1000
            expected_source = {"start": segment_plan.source_start_ms * 1000, "duration": duration_us}
            expected_target = {"start": segment_plan.target_start_ms * 1000, "duration": duration_us}
            if segment_json.get("source_timerange") != expected_source:
                raise PodcastEditorError("invalid_draft", "剪映草稿的来源时间范围不符。", status=500)
            if segment_json.get("target_timerange") != expected_target:
                raise PodcastEditorError("invalid_draft", "剪映草稿的目标时间范围不符。", status=500)
            if material_paths.get(segment_json.get("material_id")) != expected_source_path:
                raise PodcastEditorError("invalid_draft", "剪映草稿引用的原音频不符。", status=500)
