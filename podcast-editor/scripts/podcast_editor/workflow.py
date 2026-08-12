from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .contracts import ProjectJSON, SourceJSON, StateJSON
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
) -> ProjectStore:
    if not inputs:
        raise ValueError("至少需要一个音频文件")
    paths = [Path(item).expanduser().resolve() for item in inputs]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)

    mode = "mixed" if len(paths) == 1 else "multitrack"
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
    for index, path in enumerate(paths):
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
