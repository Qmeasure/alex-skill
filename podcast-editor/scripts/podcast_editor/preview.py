from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from .contracts import ProjectJSON
from .errors import PodcastEditorError, raise_if_cancelled
from .media import require_binary
from .planning import CutPlan


def render_monitor_mix(
    project: ProjectJSON,
    output_path: str | Path,
    *,
    ffmpeg: str | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    executable = ffmpeg or require_binary("ffmpeg")
    command = [executable, "-y", "-v", "error"]
    for source in project["sources"]:
        command.extend(["-i", source["path"]])
    labels = "".join(f"[{index}:a]" for index in range(len(project["sources"])))
    command.extend(
        [
            "-filter_complex",
            f"{labels}amix=inputs={len(project['sources'])}:duration=longest:normalize=1[mix]",
            "-map",
            "[mix]",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    _run_ffmpeg(command, cancel_event=cancel_event)
    return output


def render_preview(
    project: ProjectJSON,
    plan: CutPlan,
    output_path: str | Path,
    *,
    ffmpeg: str | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    executable = ffmpeg or require_binary("ffmpeg")
    command = [executable, "-y", "-v", "error"]
    for source in project["sources"]:
        command.extend(["-i", source["path"]])

    filter_parts: list[str] = []
    output_labels: list[str] = []
    packed_single_track = project["mode"] == "mixed" and len(plan.tracks) == 1
    label_index = 0
    segment_count_by_source: dict[int, int] = {}
    for track in plan.tracks:
        segment_count_by_source[track.source_index] = segment_count_by_source.get(track.source_index, 0) + len(track.segments)
    source_labels: dict[int, list[str]] = {}
    for source_index, count in segment_count_by_source.items():
        if count == 1:
            source_labels[source_index] = [f"{source_index}:a"]
        else:
            labels = [f"source{source_index}_{branch}" for branch in range(count)]
            filter_parts.append(
                f"[{source_index}:a]asplit={count}" + "".join(f"[{label}]" for label in labels)
            )
            source_labels[source_index] = labels
    source_label_offsets = {source_index: 0 for source_index in source_labels}
    for track in plan.tracks:
        for segment in track.segments:
            duration_seconds = (segment.source_end_ms - segment.source_start_ms) / 1000
            if duration_seconds <= 0:
                continue
            fade = min(0.005, duration_seconds / 2)
            fade_out_start = max(0.0, duration_seconds - fade)
            label = f"piece{label_index}"
            label_index += 1
            input_label = source_labels[track.source_index][source_label_offsets[track.source_index]]
            source_label_offsets[track.source_index] += 1
            delay_filter = (
                ""
                if packed_single_track
                else f"adelay=delays={segment.target_start_ms}:all=1,"
            )
            filter_parts.append(
                f"[{input_label}]"
                f"atrim=start={segment.source_start_ms / 1000:.6f}:end={segment.source_end_ms / 1000:.6f},"
                "asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d={fade:.6f},"
                f"afade=t=out:st={fade_out_start:.6f}:d={fade:.6f},"
                f"{delay_filter}anull[{label}]"
            )
            output_labels.append(f"[{label}]")
    if not output_labels:
        raise PodcastEditorError("empty_output", "没有可供预览的音频片段。")
    if packed_single_track:
        if len(output_labels) == 1:
            filter_parts.append(output_labels[0] + "anull[preview]")
        else:
            filter_parts.append(
                "".join(output_labels)
                + f"concat=n={len(output_labels)}:v=0:a=1[preview]"
            )
    else:
        filter_parts.append(
            "".join(output_labels)
            + f"amix=inputs={len(output_labels)}:duration=longest:normalize=0,"
            "alimiter=limit=0.95[preview]"
        )
    command.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            "[preview]",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    _run_ffmpeg(command, cancel_event=cancel_event)
    return output


def _run_ffmpeg(
    command: list[str],
    *,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float = 7_200,
    poll_interval: float = 0.1,
) -> None:
    raise_if_cancelled(cancel_event)
    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        raise PodcastEditorError(
            "ffmpeg_failed", "无法启动 ffmpeg，请检查安装和 PATH。", status=500
        ) from exc
    deadline = time.monotonic() + timeout_seconds
    try:
        while process.poll() is None:
            if cancel_event is not None and cancel_event.wait(poll_interval):
                _stop_process(process)
                raise_if_cancelled(cancel_event)
            if time.monotonic() >= deadline:
                _stop_process(process)
                raise PodcastEditorError("ffmpeg_timeout", "音频处理超时。", status=504)
        raise_if_cancelled(cancel_event)
    except BaseException:
        if process.poll() is None:
            _stop_process(process)
        raise
    if process.returncode != 0:
        raise PodcastEditorError("ffmpeg_failed", "音频处理失败，请检查 ffmpeg 和输入文件。", status=500)


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
