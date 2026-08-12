from __future__ import annotations

import array
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from .errors import PodcastEditorError


@dataclass(frozen=True)
class AudioProbe:
    duration_ms: int
    frame_duration_ms: float
    codec_name: str
    sample_rate: int


AUDIO_ANALYSIS_VERSION = "audio-analysis-v2"


@dataclass(frozen=True)
class BoundaryResolution:
    start_ms: int
    end_ms: int
    min_start_ms: int
    max_end_ms: int
    mode: str
    needs_review: bool
    warning: str | None
    can_cut: bool


@dataclass(frozen=True)
class AudioAnalysis:
    fingerprint: str
    duration_ms: int
    frame_ms: int
    rms: tuple[int, ...]
    peaks: tuple[int, ...]
    silences: tuple[tuple[int, int], ...] = ()

    def adjust_deletion(
        self,
        raw_start_ms: int,
        raw_end_ms: int,
        previous_word: dict | None,
        next_word: dict | None,
    ) -> BoundaryResolution:
        selected_onset, selected_offset, threshold = self.speech_bounds(raw_start_ms, raw_end_ms)
        previous_offset = (
            self.speech_bounds(
                previous_word["startMs"], previous_word["endMs"], within_word=True
            )[1]
            if previous_word is not None
            else 0
        )
        next_onset = (
            self.speech_bounds(next_word["startMs"], next_word["endMs"], within_word=True)[0]
            if next_word is not None
            else self.duration_ms
        )
        safe_start = max(0, previous_offset)
        safe_end = min(self.duration_ms, next_onset)
        warnings: list[str] = []

        if safe_end <= safe_start:
            warning = "相邻保留词的发声范围重叠，没有安全的自动切点"
            point = max(0, min(self.duration_ms, safe_end))
            return BoundaryResolution(
                start_ms=point,
                end_ms=point,
                min_start_ms=safe_start,
                max_end_ms=safe_end,
                mode="acoustic-review",
                needs_review=True,
                warning=warning,
                can_cut=False,
            )

        if selected_onset < safe_start:
            warnings.append("所选内容与前一个保留词连读，左切点需要复核")
        if selected_offset > safe_end:
            warnings.append("所选内容与后一个保留词连读，右切点需要复核")

        start_gap_end = max(safe_start, min(selected_onset, raw_start_ms))
        start_run = self._nearest_low_run(safe_start, start_gap_end, threshold, prefer_last=True)
        end_gap_start = min(safe_end, max(selected_offset, raw_end_ms))
        end_run = self._nearest_low_run(end_gap_start, safe_end, threshold, prefer_last=False)
        if start_run is None:
            start = max(safe_start, min(selected_onset, raw_start_ms))
            if previous_word is not None:
                warnings.append("左侧没有可靠的低能量间隔")
        else:
            start = start_run[1]
        if end_run is None:
            end = min(safe_end, max(selected_offset, raw_end_ms))
            if next_word is not None:
                warnings.append("右侧没有可靠的低能量间隔")
        else:
            end = end_run[0]
        snapped_start, snapped_end = start, end
        safe_covers_raw = safe_start <= raw_start_ms and safe_end >= raw_end_ms
        if safe_covers_raw:
            start = max(safe_start, min(start, raw_start_ms))
            end = min(safe_end, max(end, raw_end_ms, start + 1))
            if snapped_start > raw_start_ms or snapped_end < raw_end_ms:
                warnings.append("低能量切点未覆盖完整文字，已按原始时间边界扩展")
        can_cut = safe_covers_raw
        if not can_cut:
            warnings.append("声学安全范围无法完整覆盖所选文字，本段不会自动剪切")
            start = end = max(safe_start, min(safe_end, raw_start_ms))
        warning = "；".join(dict.fromkeys(warnings)) or None
        return BoundaryResolution(
            start_ms=start,
            end_ms=end,
            min_start_ms=safe_start,
            max_end_ms=safe_end,
            mode="acoustic" if warning is None else "acoustic-review",
            needs_review=warning is not None,
            warning=warning,
            can_cut=can_cut,
        )

    def speech_bounds(
        self, start_ms: int, end_ms: int, *, within_word: bool = False
    ) -> tuple[int, int, int]:
        start_frame = max(0, start_ms // self.frame_ms)
        end_frame = min(len(self.rms), max(start_frame + 1, (end_ms + self.frame_ms - 1) // self.frame_ms))
        window_start = start_frame if within_word else max(0, start_frame - 30)
        window_end = end_frame if within_word else min(len(self.rms), end_frame + 30)
        pooled = self._max_pooled(window_start, window_end, radius=2)
        word_left = start_frame - window_start
        word_right = max(word_left + 1, end_frame - window_start)
        local_peak = max(pooled[word_left:word_right], default=max(pooled, default=0))
        threshold = max(24, round(local_peak * 0.2511886432))
        minimum_voice_frames = max(1, 30 // self.frame_ms)
        runs = self._runs(pooled, lambda value: value > threshold, minimum_voice_frames)
        absolute_runs = [
            ((window_start + left) * self.frame_ms, (window_start + right) * self.frame_ms)
            for left, right in runs
        ]
        overlaps = [
            run for run in absolute_runs if run[0] < end_ms and run[1] > start_ms
        ]
        if not overlaps:
            return start_ms, end_ms, threshold
        onset = min(run[0] for run in overlaps)
        offset = max(run[1] for run in overlaps)
        if within_word:
            onset = max(start_ms, onset)
            offset = min(end_ms, offset)
        return onset, offset, threshold

    def _nearest_low_run(
        self, start_ms: int, end_ms: int, threshold: int, *, prefer_last: bool
    ) -> tuple[int, int] | None:
        if end_ms - start_ms < 30:
            return None
        start_frame = max(0, start_ms // self.frame_ms)
        end_frame = min(len(self.rms), max(start_frame, (end_ms + self.frame_ms - 1) // self.frame_ms))
        pooled = self._max_pooled(start_frame, end_frame, radius=2)
        runs = self._runs(pooled, lambda value: value <= threshold, max(1, 30 // self.frame_ms))
        if not runs:
            return None
        left, right = runs[-1] if prefer_last else runs[0]
        return (start_frame + left) * self.frame_ms, min(end_ms, (start_frame + right) * self.frame_ms)

    @staticmethod
    def _runs(values: list[int], predicate, minimum: int) -> list[tuple[int, int]]:
        runs: list[tuple[int, int]] = []
        cursor: int | None = None
        for index, value in enumerate(values):
            if predicate(value) and cursor is None:
                cursor = index
            elif not predicate(value) and cursor is not None:
                if index - cursor >= minimum:
                    runs.append((cursor, index))
                cursor = None
        if cursor is not None and len(values) - cursor >= minimum:
            runs.append((cursor, len(values)))
        return runs

    def _max_pooled(self, start_frame: int, end_frame: int, *, radius: int) -> list[int]:
        result: list[int] = []
        for index in range(start_frame, end_frame):
            left = max(0, index - radius)
            right = min(len(self.rms), index + radius + 1)
            result.append(max(self.rms[left:right], default=0))
        return result

    def waveform(self, start_ms: int, end_ms: int, points: int) -> list[dict[str, float | int]]:
        start_ms = max(0, min(start_ms, self.duration_ms))
        end_ms = max(start_ms + 1, min(end_ms, self.duration_ms))
        result: list[dict[str, float | int]] = []
        for index in range(points):
            bucket_start = start_ms + (end_ms - start_ms) * index // points
            bucket_end = start_ms + (end_ms - start_ms) * (index + 1) // points
            first_frame = max(0, bucket_start // self.frame_ms)
            last_frame = min(
                len(self.peaks), max(first_frame + 1, (bucket_end + self.frame_ms - 1) // self.frame_ms)
            )
            peak = max(self.peaks[first_frame:last_frame], default=0) / 32767
            result.append(
                {"startMs": bucket_start, "endMs": bucket_end, "peak": round(min(1.0, peak), 6)}
            )
        return result


def audio_fingerprint(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    try:
        stat = resolved.stat()
        material = f"{resolved}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        material = f"missing|{resolved}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class AudioAnalysisCache:
    def __init__(self, root: str | Path, *, ffmpeg: str | None = None):
        self.root = Path(root).expanduser().resolve()
        self.ffmpeg = ffmpeg
        self._lock = threading.RLock()
        self._memory: dict[str, AudioAnalysis] = {}

    def get(self, path: str | Path) -> AudioAnalysis:
        fingerprint = audio_fingerprint(path)
        with self._lock:
            cached = self._memory.get(fingerprint)
            if cached is not None:
                return cached
            cache_path = self.root / f"analysis-{fingerprint[:20]}.json"
            loaded = self._load(cache_path, fingerprint)
            if loaded is None:
                loaded = self._decode(path, fingerprint)
                self._save(cache_path, loaded)
            self._memory[fingerprint] = loaded
            return loaded

    def _decode(self, path: str | Path, fingerprint: str) -> AudioAnalysis:
        executable = self.ffmpeg or require_binary("ffmpeg")
        command = [
            executable,
            "-v",
            "error",
            "-i",
            str(Path(path).expanduser().resolve()),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "s16le",
            "pipe:1",
        ]
        frame_samples = 160
        frame_bytes = frame_samples * 2
        rms_values: list[int] = []
        peaks: list[int] = []
        pending = b""
        total_samples = 0
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            assert process.stdout is not None
            try:
                while True:
                    chunk = process.stdout.read(64 * 1024)
                    if not chunk:
                        break
                    pending += chunk
                    complete = len(pending) // frame_bytes * frame_bytes
                    for offset in range(0, complete, frame_bytes):
                        frame = array.array("h")
                        frame.frombytes(pending[offset : offset + frame_bytes])
                        if sys.byteorder == "big":
                            frame.byteswap()
                        rms_values.append(
                            round(math.sqrt(sum(sample * sample for sample in frame) / len(frame)))
                        )
                        peaks.append(max(abs(sample) for sample in frame))
                        total_samples += len(frame)
                    pending = pending[complete:]
            finally:
                process.stdout.close()
            if pending:
                usable = len(pending) // 2 * 2
                frame = array.array("h")
                frame.frombytes(pending[:usable])
                if sys.byteorder == "big":
                    frame.byteswap()
                if frame:
                    rms_values.append(
                        round(math.sqrt(sum(sample * sample for sample in frame) / len(frame)))
                    )
                    peaks.append(max(abs(sample) for sample in frame))
                    total_samples += len(frame)
            return_code = process.wait(timeout=7_200)
        except (OSError, subprocess.SubprocessError) as exc:
            if "process" in locals() and process.poll() is None:
                process.kill()
                process.wait()
            raise PodcastEditorError("audio_analysis_failed", "无法分析音频切点。", status=500) from exc
        if return_code != 0 or not rms_values:
            raise PodcastEditorError("audio_analysis_failed", "无法分析音频切点。", status=500)
        duration_ms = max(1, round(total_samples * 1000 / 16000))
        silences = _sustained_silences(rms_values, frame_ms=10)
        return AudioAnalysis(fingerprint, duration_ms, 10, tuple(rms_values), tuple(peaks), silences)

    def _load(self, path: Path, fingerprint: str) -> AudioAnalysis | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("version") != AUDIO_ANALYSIS_VERSION or value.get("fingerprint") != fingerprint:
                return None
            return AudioAnalysis(
                fingerprint=fingerprint,
                duration_ms=int(value["durationMs"]),
                frame_ms=int(value["frameMs"]),
                rms=tuple(int(item) for item in value["rms"]),
                peaks=tuple(int(item) for item in value["peaks"]),
                silences=tuple((int(item[0]), int(item[1])) for item in value.get("silences", [])),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _save(self, path: Path, analysis: AudioAnalysis) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        value = {
            "version": AUDIO_ANALYSIS_VERSION,
            "fingerprint": analysis.fingerprint,
            "durationMs": analysis.duration_ms,
            "frameMs": analysis.frame_ms,
            "rms": analysis.rms,
            "peaks": analysis.peaks,
            "silences": analysis.silences,
        }
        handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(value, stream, separators=(",", ":"))
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _sustained_silences(values: list[int], *, frame_ms: int) -> tuple[tuple[int, int], ...]:
    if not values:
        return ()
    sorted_values = sorted(values)
    noise_floor = sorted_values[max(0, len(sorted_values) // 10 - 1)]
    threshold = max(24, min(800, noise_floor * 3))
    minimum = max(1, 120 // frame_ms)
    result: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value <= threshold and start is None:
            start = index
        elif value > threshold and start is not None:
            if index - start >= minimum:
                result.append((start * frame_ms, index * frame_ms))
            start = None
    if start is not None and len(values) - start >= minimum:
        result.append((start * frame_ms, len(values) * frame_ms))
    return tuple(result)


CODEC_FRAME_SAMPLES = {
    "aac": 1024,
    "aac_latm": 1024,
    "mp3": 1152,
    "mp2": 1152,
    "opus": 960,
    "vorbis": 1024,
}


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise PodcastEditorError("missing_dependency", f"找不到 {name}，请先安装并加入 PATH。", status=500)
    return path


def probe_audio(path: str | Path, *, ffprobe: str | None = None) -> AudioProbe:
    audio_path = Path(path).expanduser().resolve()
    if not audio_path.is_file():
        raise PodcastEditorError("input_not_found", f"找不到音频文件：{audio_path}")
    executable = ffprobe or require_binary("ffprobe")
    command = [
        executable,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,frame_size,duration:format=duration",
        "-of",
        "json",
        str(audio_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if completed.returncode != 0:
        raise PodcastEditorError(
            "invalid_audio", f"无法读取音频信息：{audio_path.name}", details=completed.stderr.strip()
        )
    try:
        result = json.loads(completed.stdout)
        stream = result["streams"][0]
        duration_seconds = float(stream.get("duration") or result["format"]["duration"])
        sample_rate = int(stream.get("sample_rate") or 0)
        codec = str(stream.get("codec_name") or "unknown")
        frame_size = int(stream.get("frame_size") or 0)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PodcastEditorError("invalid_audio", f"音频信息不完整：{audio_path.name}") from exc
    if duration_seconds <= 0 or sample_rate <= 0:
        raise PodcastEditorError("invalid_audio", f"音频时长或采样率无效：{audio_path.name}")
    frame_samples = frame_size or CODEC_FRAME_SAMPLES.get(codec, 1)
    return AudioProbe(
        duration_ms=round(duration_seconds * 1000),
        frame_duration_ms=frame_samples * 1000 / sample_rate,
        codec_name=codec,
        sample_rate=sample_rate,
    )


def validate_aligned_durations(probes: list[AudioProbe]) -> float:
    if len(probes) < 2:
        return probes[0].frame_duration_ms if probes else 0.0
    tolerance = max(probe.frame_duration_ms for probe in probes)
    durations = [probe.duration_ms for probe in probes]
    difference = max(durations) - min(durations)
    if difference > tolerance:
        raise PodcastEditorError(
            "duration_mismatch",
            "多人分轨长度不一致，已停止处理；不会自动裁尾或补静音。",
            details={"durationsMs": durations, "allowedDifferenceMs": tolerance, "actualDifferenceMs": difference},
        )
    return tolerance


def find_low_energy_boundary(
    path: str | Path,
    center_ms: int,
    lower_ms: int,
    upper_ms: int,
    *,
    ffmpeg: str | None = None,
    sample_rate: int = 16000,
    frame_ms: int = 10,
) -> int:
    """Find the quietest short PCM window without leaving the supplied bounds."""

    lower_ms = max(0, int(lower_ms))
    upper_ms = max(lower_ms, int(upper_ms))
    center_ms = min(max(int(center_ms), lower_ms), upper_ms)
    if upper_ms - lower_ms < frame_ms:
        return center_ms
    try:
        executable = ffmpeg or require_binary("ffmpeg")
        command = [
            executable,
            "-v",
            "error",
            "-ss",
            f"{lower_ms / 1000:.6f}",
            "-t",
            f"{(upper_ms - lower_ms) / 1000:.6f}",
            "-i",
            str(Path(path).resolve()),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "pipe:1",
        ]
        completed = subprocess.run(command, capture_output=True, timeout=30, check=False)
        if completed.returncode != 0 or not completed.stdout:
            return center_ms
        frame_bytes = max(2, round(sample_rate * frame_ms / 1000) * 2)
        best_score: float | None = None
        best_offset = center_ms - lower_ms
        for byte_offset in range(0, max(0, len(completed.stdout) - frame_bytes + 1), frame_bytes):
            frame = completed.stdout[byte_offset : byte_offset + frame_bytes]
            samples = array.array("h")
            samples.frombytes(frame)
            if sys.byteorder == "big":
                samples.byteswap()
            if not samples:
                continue
            rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
            offset_ms = byte_offset / 2 * 1000 / sample_rate
            distance_penalty = abs((lower_ms + offset_ms) - center_ms) * 0.01
            score = math.log1p(rms) + distance_penalty
            if best_score is None or score < best_score:
                best_score = score
                best_offset = round(offset_ms + frame_ms / 2)
        return min(max(lower_ms + best_offset, lower_ms), upper_ms)
    except (OSError, subprocess.SubprocessError, ValueError):
        return center_ms
