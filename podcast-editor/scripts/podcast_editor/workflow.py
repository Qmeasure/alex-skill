from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .contracts import ProjectJSON, SourceJSON, StateJSON
from .errors import PodcastEditorError
from .media import AudioProbe, probe_audio, validate_aligned_durations
from .storage import ProjectStore, write_json_atomic
from .transcript import build_transcript, filler_word_ids, parse_asr_words
from .volcengine import VolcengineASR, load_api_key


class Transcriber(Protocol):
    def transcribe(self, audio_path: str | Path, *, identify_speakers: bool) -> dict[str, Any]: ...


def default_workdir(first_input: str | Path) -> Path:
    source = Path(first_input).expanduser()
    return Path.home() / "Desktop" / "output" / f"{datetime.now():%Y%m%d_%H%M%S}_{source.stem}" / "剪播客"


def prepare_project(
    inputs: list[str | Path],
    workdir: str | Path | None = None,
    *,
    transcriber: Transcriber | None = None,
    probes: list[AudioProbe] | None = None,
    transcription_inputs: list[str | Path] | None = None,
) -> ProjectStore:
    if not inputs:
        raise ValueError("至少需要一个音频文件")
    paths = [Path(item).expanduser().resolve() for item in inputs]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)

    mode = "mixed" if len(paths) == 1 else "multitrack"
    asr_paths = (
        [Path(item).expanduser().resolve() for item in transcription_inputs]
        if transcription_inputs is not None
        else paths
    )
    if len(asr_paths) != len(paths) or any(not path.is_file() for path in asr_paths):
        raise ValueError("转录输入必须与原始音频逐一对应")
    audio_probes = probes or [probe_audio(path) for path in paths]
    if len(audio_probes) != len(paths):
        raise ValueError("probes 数量必须与输入文件数量一致")
    if mode == "multitrack":
        validate_aligned_durations(audio_probes)

    client = transcriber or VolcengineASR(load_api_key())
    root = Path(workdir).expanduser().resolve() if workdir else default_workdir(paths[0]).resolve()
    transcription_dir = root / "transcription"
    raw_results: list[dict[str, Any]] = []
    per_source_words = []
    for index, path in enumerate(asr_paths):
        identify_speakers = mode == "mixed"
        result = client.transcribe(path, identify_speakers=identify_speakers)
        raw_results.append(result)
        forced_speaker = None if mode == "mixed" else f"speaker-{index + 1:02d}"
        per_source_words.append(
            parse_asr_words(result, force_speaker=forced_speaker, require_speaker=mode == "mixed")
        )

    speakers, utterances = build_transcript(mode, per_source_words)
    sources: list[SourceJSON] = []
    for index, (path, audio_probe) in enumerate(zip(paths, audio_probes, strict=True)):
        sources.append(
            {
                "id": f"source-{index + 1:02d}",
                "path": str(path),
                "durationMs": audio_probe.duration_ms,
                "frameDurationMs": audio_probe.frame_duration_ms,
                "speakerId": None if mode == "mixed" else speakers[index]["id"],
            }
        )
    project: ProjectJSON = {
        "schemaVersion": 1,
        "id": f"podcast-{datetime.now():%Y%m%d%H%M%S}",
        "name": paths[0].stem,
        "title": paths[0].stem,
        "mode": mode,
        "durationMs": max(probe.duration_ms for probe in audio_probes),
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sources": sources,
        "speakers": speakers,
        "utterances": utterances,
    }
    state: StateJSON = {
        "revision": 0,
        "selectedWordIds": filler_word_ids(utterances),
        "speakerNames": {speaker["id"]: speaker["name"] for speaker in speakers},
        "speakerOverrides": {},
    }
    store = ProjectStore(root)
    store.create(project, state)
    for index, result in enumerate(raw_results):
        write_json_atomic(transcription_dir / f"source-{index + 1:02d}.json", result)
    return store


def retranscribe_project(
    project_root: str | Path,
    *,
    transcriber: Transcriber | None = None,
    probes: list[AudioProbe] | None = None,
) -> ProjectStore:
    """Rebuild a project from its original sources, then replace its directory."""

    root = Path(project_root).expanduser().resolve()
    current_store = ProjectStore(root)
    current = current_store.load_project()
    inputs = [source["path"] for source in current["sources"]]
    stage = Path(tempfile.mkdtemp(prefix=f".{root.name}.retranscribe-", dir=root.parent))
    replaced = root.parent / f".{root.name}.replaced-{uuid.uuid4().hex}"
    try:
        proxy_paths = (
            [
                _build_asr_proxy(path, stage / "cache" / f"asr-proxy-source-{index + 1:02d}.mp3")
                for index, path in enumerate(inputs)
            ]
            if transcriber is None
            else inputs
        )
        candidate_store = prepare_project(
            inputs,
            stage,
            transcriber=transcriber,
            probes=probes,
            transcription_inputs=proxy_paths,
        )
        candidate = candidate_store.load_project()
        candidate_state = candidate_store.load_state(candidate)
        _namespace_transcript_ids(candidate, candidate_state, uuid.uuid4().hex[:12])
        candidate["id"] = current["id"]
        candidate["name"] = current["name"]
        candidate["title"] = current["title"]
        candidate["createdAt"] = current["createdAt"]
        candidate_store.create(candidate, candidate_state)

        _link_preserved_directory(root / "cache" / "audio-analysis", stage / "cache" / "audio-analysis")
        _link_preserved_directory(root / "剪映草稿", stage / "剪映草稿")

        os.replace(root, replaced)
        try:
            os.replace(stage, root)
        except BaseException:
            os.replace(replaced, root)
            raise
        shutil.rmtree(replaced)
        return ProjectStore(root)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if replaced.exists() and root.exists():
            shutil.rmtree(replaced)


def _link_preserved_directory(source: Path, destination: Path) -> None:
    if not source.is_dir():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, copy_function=os.link)


def _namespace_transcript_ids(project: ProjectJSON, state: StateJSON, namespace: str) -> None:
    selected = set(state["selectedWordIds"])
    renamed_selected: list[str] = []
    word_index = 0
    for utterance_index, utterance in enumerate(project["utterances"], start=1):
        utterance["id"] = f"utterance-rt-{namespace}-{utterance_index:06d}"
        for word in utterance["words"]:
            word_index += 1
            previous_id = word["id"]
            word["id"] = f"word-rt-{namespace}-{word_index:07d}"
            if previous_id in selected:
                renamed_selected.append(word["id"])
    state["selectedWordIds"] = renamed_selected


def _build_asr_proxy(source: str | Path, destination: Path) -> Path:
    original = Path(source).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(original),
                "-map",
                "0:a:0",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "64k",
                str(destination),
            ],
            capture_output=True,
            text=True,
            timeout=7200,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PodcastEditorError("asr_proxy_failed", "无法生成转录用音频。") from exc
    if result.returncode != 0 or not destination.is_file():
        raise PodcastEditorError(
            "asr_proxy_failed",
            "无法生成转录用音频。",
            details={"message": result.stderr.strip()[-500:]},
        )
    original_probe = probe_audio(original)
    proxy_probe = probe_audio(destination)
    tolerance = max(original_probe.frame_duration_ms, proxy_probe.frame_duration_ms)
    if abs(original_probe.duration_ms - proxy_probe.duration_ms) > tolerance:
        raise PodcastEditorError("asr_proxy_duration_mismatch", "转录用音频与原音频时长不一致。")
    return destination
