from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from .contracts import ProjectJSON, StateJSON, iter_project_words
from .errors import PodcastEditorError
from .media import BoundaryResolution


@dataclass(frozen=True, order=True)
class TimeRange:
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True)
class SegmentPlan:
    source_start_ms: int
    source_end_ms: int
    target_start_ms: int
    target_end_ms: int


@dataclass(frozen=True)
class TrackPlan:
    source_index: int
    speaker_id: str | None
    name: str
    segments: tuple[SegmentPlan, ...]


@dataclass(frozen=True)
class DeletionPlan:
    id: str
    first_word_id: str
    last_word_id: str
    raw_start_ms: int
    raw_end_ms: int
    start_ms: int
    end_ms: int
    min_start_ms: int
    max_end_ms: int
    boundary_mode: str
    scope: str
    speaker_id: str | None
    needs_review: bool
    boundary_warning: str | None
    can_cut: bool


@dataclass(frozen=True)
class CutPlan:
    mode: str
    duration_ms: int
    output_duration_ms: int
    global_deletions: tuple[TimeRange, ...]
    speaker_deletions: dict[str, tuple[TimeRange, ...]]
    tracks: tuple[TrackPlan, ...]
    deletions: tuple[DeletionPlan, ...]

    def as_dict(self) -> dict:
        return asdict(self)


def timeline_from_plan(plan: CutPlan, revision: int) -> dict:
    segments = []
    for kept in subtract_ranges(plan.duration_ms, plan.global_deletions):
        target_start = kept.start_ms - removed_before(kept.start_ms, plan.global_deletions)
        target_end = kept.end_ms - removed_before(kept.end_ms, plan.global_deletions)
        segments.append(
            {
                "sourceStartMs": kept.start_ms,
                "sourceEndMs": kept.end_ms,
                "targetStartMs": target_start,
                "targetEndMs": target_end,
            }
        )
    return {"revision": revision, "durationMs": plan.output_duration_ms, "segments": segments}


def build_preview_utterances(
    project: ProjectJSON, state: StateJSON, plan: CutPlan
) -> list[dict]:
    """Return the kept transcript on the packed global playback timeline."""

    selected = set(state["selectedWordIds"])
    result: list[dict] = []
    for utterance in project["utterances"]:
        mapped_words: list[dict] = []
        for word in utterance["words"]:
            effective_deletions = (
                *plan.global_deletions,
                *plan.speaker_deletions.get(utterance["speakerId"], ()),
            )
            overlaps_deletion = any(
                word["startMs"] < deletion.end_ms and word["endMs"] > deletion.start_ms
                for deletion in effective_deletions
            )
            if word["id"] in selected and overlaps_deletion:
                continue
            if any(
                word["startMs"] < deletion.end_ms and word["endMs"] > deletion.start_ms
                for deletion in plan.global_deletions
            ):
                continue
            mapped_start = word["startMs"] - removed_before(word["startMs"], plan.global_deletions)
            mapped_end = word["endMs"] - removed_before(word["endMs"], plan.global_deletions)
            if mapped_end <= mapped_start:
                continue
            mapped_words.append({**word, "startMs": mapped_start, "endMs": mapped_end})
        if not mapped_words:
            continue
        result.append(
            {
                "id": utterance["id"],
                "speakerId": utterance["speakerId"],
                "startMs": min(word["startMs"] for word in mapped_words),
                "endMs": max(word["endMs"] for word in mapped_words),
                "words": mapped_words,
            }
        )
    return result


BoundaryFinder = Callable[[str | Path, int, int, int], int]
BoundaryResolver = Callable[[str | Path, int, int, dict | None, dict | None], BoundaryResolution]


CUT_PLAN_CONTRACT_VERSION = 2


def merge_ranges(ranges: Iterable[TimeRange]) -> tuple[TimeRange, ...]:
    ordered = sorted((item for item in ranges if item.end_ms > item.start_ms), key=lambda item: item.start_ms)
    merged: list[TimeRange] = []
    for item in ordered:
        if not merged or item.start_ms > merged[-1].end_ms:
            merged.append(item)
        else:
            merged[-1] = TimeRange(merged[-1].start_ms, max(merged[-1].end_ms, item.end_ms))
    return tuple(merged)


def subtract_ranges(duration_ms: int, deletions: Iterable[TimeRange]) -> tuple[TimeRange, ...]:
    cursor = 0
    kept: list[TimeRange] = []
    for deletion in merge_ranges(deletions):
        start = min(max(deletion.start_ms, 0), duration_ms)
        end = min(max(deletion.end_ms, 0), duration_ms)
        if start > cursor:
            kept.append(TimeRange(cursor, start))
        cursor = max(cursor, end)
    if cursor < duration_ms:
        kept.append(TimeRange(cursor, duration_ms))
    return tuple(kept)


def removed_before(time_ms: int, deletions: Iterable[TimeRange]) -> int:
    removed = 0
    for item in merge_ranges(deletions):
        if time_ms >= item.end_ms:
            removed += item.duration_ms
        elif time_ms > item.start_ms:
            removed += time_ms - item.start_ms
            break
        else:
            break
    return removed


def build_cut_plan(
    project: ProjectJSON,
    state: StateJSON,
    *,
    boundary_finder: BoundaryFinder | None = None,
    boundary_resolver: BoundaryResolver | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> CutPlan:
    if cancel_check:
        cancel_check()
    selected_ids = set(state["selectedWordIds"])
    project_words = list(iter_project_words(project))
    known_ids = {word["id"] for word in project_words}
    unknown = selected_ids - known_ids
    if unknown:
        raise PodcastEditorError("unknown_words", "选择中包含未知词条。", details=sorted(unknown))

    selected_groups = _selected_groups(
        project,
        selected_ids,
        boundary_finder=boundary_finder,
        boundary_resolver=boundary_resolver,
        cut_overrides=state.get("cutOverrides", {}),
    )
    global_ranges: list[TimeRange] = []
    speaker_ranges: dict[str, list[TimeRange]] = {speaker["id"]: [] for speaker in project["speakers"]}
    if project["mode"] == "mixed":
        global_ranges.extend(
            TimeRange(group.start_ms, group.end_ms) for group in selected_groups if group.can_cut
        )
    else:
        for group in selected_groups:
            if not group.can_cut:
                continue
            speaker_id = group.speaker_id
            assert speaker_id is not None
            interval = TimeRange(group.start_ms, group.end_ms)
            if cancel_check:
                cancel_check()
            preserved_overlap = merge_ranges(
                TimeRange(
                    max(interval.start_ms, word["startMs"]),
                    min(interval.end_ms, word["endMs"]),
                )
                for word in project_words
                if word["speakerId"] != speaker_id
                and word["id"] not in selected_ids
                and word["startMs"] < interval.end_ms
                and word["endMs"] > interval.start_ms
            )
            speaker_ranges[speaker_id].extend(preserved_overlap)
            global_ranges.extend(_subtract_from_interval(interval, preserved_overlap))

    global_deletions = merge_ranges(global_ranges)
    speaker_deletions = {
        speaker_id: merge_ranges(ranges) for speaker_id, ranges in speaker_ranges.items() if ranges
    }
    output_duration = project["durationMs"] - sum(item.duration_ms for item in global_deletions)
    tracks: list[TrackPlan] = []

    if project["mode"] == "mixed":
        track_name = "、".join(state["speakerNames"][speaker["id"]] for speaker in project["speakers"])
        tracks.append(
            TrackPlan(
                source_index=0,
                speaker_id=None,
                name=track_name,
                segments=_build_segments(project["durationMs"], global_deletions, global_deletions),
            )
        )
    else:
        track_names = _unique_track_names(
            [(source["speakerId"], state["speakerNames"][source["speakerId"]]) for source in project["sources"]]
        )
        for source_index, source in enumerate(project["sources"]):
            if cancel_check:
                cancel_check()
            speaker_id = source["speakerId"]
            assert speaker_id is not None
            all_deletions = merge_ranges((*global_deletions, *speaker_deletions.get(speaker_id, ())))
            tracks.append(
                TrackPlan(
                    source_index=source_index,
                    speaker_id=speaker_id,
                    name=track_names[speaker_id],
                    segments=_build_segments(source["durationMs"], all_deletions, global_deletions),
                )
            )

    if cancel_check:
        cancel_check()
    if not any(track.segments for track in tracks):
        raise PodcastEditorError("empty_output", "全部音频都被删除，无法生成剪映草稿。")
    return CutPlan(
        mode=project["mode"],
        duration_ms=project["durationMs"],
        output_duration_ms=output_duration,
        global_deletions=global_deletions,
        speaker_deletions=speaker_deletions,
        tracks=tuple(tracks),
        deletions=tuple(selected_groups),
    )


def _build_segments(
    duration_ms: int, all_deletions: Iterable[TimeRange], global_deletions: Iterable[TimeRange]
) -> tuple[SegmentPlan, ...]:
    segments: list[SegmentPlan] = []
    for kept in subtract_ranges(duration_ms, all_deletions):
        target_start = kept.start_ms - removed_before(kept.start_ms, global_deletions)
        target_end = kept.end_ms - removed_before(kept.end_ms, global_deletions)
        segments.append(SegmentPlan(kept.start_ms, kept.end_ms, target_start, target_end))
    return tuple(segments)


def _subtract_from_interval(interval: TimeRange, removals: Iterable[TimeRange]) -> tuple[TimeRange, ...]:
    cursor = interval.start_ms
    result: list[TimeRange] = []
    for removal in merge_ranges(removals):
        start = max(interval.start_ms, removal.start_ms)
        end = min(interval.end_ms, removal.end_ms)
        if end <= start:
            continue
        if start > cursor:
            result.append(TimeRange(cursor, start))
        cursor = max(cursor, end)
    if cursor < interval.end_ms:
        result.append(TimeRange(cursor, interval.end_ms))
    return tuple(result)


def _unique_track_names(items: list[tuple[str | None, str]]) -> dict[str, str]:
    counts: dict[str, int] = {}
    result: dict[str, str] = {}
    for speaker_id, name in items:
        assert speaker_id is not None
        folded = name.casefold()
        counts[folded] = counts.get(folded, 0) + 1
        suffix = "" if counts[folded] == 1 else f" ({counts[folded]})"
        result[speaker_id] = name + suffix
    return result


def _deletion_id(
    project: ProjectJSON, scope: str, first_word_id: str, last_word_id: str
) -> str:
    raw = "|".join(
        (
            str(project["schemaVersion"]),
            project["id"],
            project["mode"],
            scope,
            first_word_id,
            last_word_id,
        )
    )
    return "del-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _canonical_words(project: ProjectJSON) -> list[dict]:
    words: list[dict] = []
    for utterance_index, utterance in enumerate(project["utterances"]):
        for word_index, word in enumerate(utterance["words"]):
            words.append(
                {
                    **word,
                    "speakerId": utterance["speakerId"],
                    "utteranceIndex": utterance_index,
                    "wordIndex": word_index,
                }
            )
    return sorted(
        words,
        key=lambda word: (
            word["startMs"],
            word["endMs"],
            word["utteranceIndex"],
            word["wordIndex"],
            word["id"],
        ),
    )


def _selected_groups(
    project: ProjectJSON,
    selected_ids: set[str],
    *,
    boundary_finder: BoundaryFinder | None,
    boundary_resolver: BoundaryResolver | None,
    cut_overrides: dict[str, dict[str, int]],
) -> list[DeletionPlan]:
    canonical = _canonical_words(project)
    if project["mode"] == "mixed":
        word_sequences = [("global", None, canonical)]
    else:
        by_speaker: dict[str, list[dict]] = {}
        for word in canonical:
            by_speaker.setdefault(word["speakerId"], []).append(word)
        word_sequences = [
            ("speaker", source["speakerId"], by_speaker.get(source["speakerId"], []))
            for source in project["sources"]
        ]

    source_for_speaker = {
        source["speakerId"]: source["path"] for source in project["sources"] if source["speakerId"] is not None
    }
    if project["mode"] == "mixed":
        for speaker in project["speakers"]:
            source_for_speaker[speaker["id"]] = project["sources"][0]["path"]

    groups: list[DeletionPlan] = []
    for scope, speaker_id, words in word_sequences:
        current: list[dict] = []
        for word in words:
            if word["id"] in selected_ids:
                current.append(word)
            elif current:
                groups.append(
                    _finish_group(
                        project,
                        scope,
                        speaker_id,
                        words,
                        current,
                        source_for_speaker,
                        boundary_finder,
                        boundary_resolver,
                        cut_overrides,
                    )
                )
                current = []
        if current:
            groups.append(
                _finish_group(
                    project,
                    scope,
                    speaker_id,
                    words,
                    current,
                    source_for_speaker,
                    boundary_finder,
                    boundary_resolver,
                    cut_overrides,
                )
            )
    return groups


def _finish_group(
    project: ProjectJSON,
    scope: str,
    speaker_id: str | None,
    speaker_words: list[dict],
    group: list[dict],
    source_for_speaker: dict[str, str],
    boundary_finder: BoundaryFinder | None,
    boundary_resolver: BoundaryResolver | None,
    cut_overrides: dict[str, dict[str, int]],
) -> DeletionPlan:
    first_index = speaker_words.index(group[0])
    last_index = speaker_words.index(group[-1])
    raw_start = group[0]["startMs"]
    raw_end = group[-1]["endMs"]
    previous_word = speaker_words[first_index - 1] if first_index else None
    next_word = speaker_words[last_index + 1] if last_index + 1 < len(speaker_words) else None
    min_start = previous_word["endMs"] if previous_word is not None else 0
    max_end = next_word["startMs"] if next_word is not None else project["durationMs"]
    min_start = min(min_start, raw_start)
    max_end = max(max_end, raw_end)
    path_key = speaker_id if speaker_id is not None else project["speakers"][0]["id"]
    path = source_for_speaker[path_key]
    start, end, boundary_mode = raw_start, raw_end, "raw"
    needs_review = False
    boundary_warning = None
    can_cut = True
    if boundary_resolver is not None:
        resolution = boundary_resolver(path, raw_start, raw_end, previous_word, next_word)
        min_start = resolution.min_start_ms
        max_end = resolution.max_end_ms
        start = resolution.start_ms
        end = resolution.end_ms
        boundary_mode = resolution.mode
        needs_review = resolution.needs_review
        boundary_warning = resolution.warning
        can_cut = resolution.can_cut
    elif boundary_finder is not None:
        start = min(raw_start, boundary_finder(path, raw_start, min_start, raw_start))
        end = max(raw_end, boundary_finder(path, raw_end, raw_end, max_end))
        boundary_mode = "low-energy"
    cut_id = _deletion_id(project, scope, group[0]["id"], group[-1]["id"])
    override = cut_overrides.get(cut_id)
    if override is not None:
        if not can_cut:
            raise PodcastEditorError(
                "invalid_cut_override",
                "这段所选文字没有完整的声学安全范围，不能手动扩大删除区间。",
                details={"cutId": cut_id},
            )
        override_start = override["startMs"]
        override_end = override["endMs"]
        required_start = max(min_start, raw_start)
        required_end = min(max_end, raw_end)
        if (
            override_start < min_start
            or override_start > required_start
            or override_end < required_end
            or override_end > max_end
            or override_end <= override_start
        ):
            raise PodcastEditorError(
                "invalid_cut_override",
                "手动切点必须覆盖所选文字，且不能越过相邻保留词。",
                details={"cutId": cut_id, "minStartMs": min_start, "maxEndMs": max_end},
            )
        start, end, boundary_mode = override_start, override_end, "manual"
        needs_review = False
        boundary_warning = None
        can_cut = True
    if can_cut and not (start <= raw_start and end >= raw_end):
        raise PodcastEditorError(
            "invalid_cut_plan",
            "自动切点没有完整覆盖所选文字。",
            details={"cutId": cut_id},
            status=500,
        )
    return DeletionPlan(
        id=cut_id,
        first_word_id=group[0]["id"],
        last_word_id=group[-1]["id"],
        raw_start_ms=raw_start,
        raw_end_ms=raw_end,
        start_ms=start,
        end_ms=end,
        min_start_ms=min_start,
        max_end_ms=max_end,
        boundary_mode=boundary_mode,
        scope=scope,
        speaker_id=speaker_id,
        needs_review=needs_review,
        boundary_warning=boundary_warning,
        can_cut=can_cut,
    )


def cut_plan_payload(
    project: ProjectJSON,
    state: StateJSON,
    plan: CutPlan,
    *,
    audio_fingerprints: dict[str, str],
    audio_analysis_version: str = "audio-analysis-v2",
) -> dict:
    timeline = timeline_from_plan(plan, state["revision"])
    project_fingerprint = hashlib.sha256(
        json.dumps(project, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    canonical_selected = [word["id"] for word in _canonical_words(project) if word["id"] in set(state["selectedWordIds"])]
    deletions = [
        {
            "id": item.id,
            "firstWordId": item.first_word_id,
            "lastWordId": item.last_word_id,
            "rawStartMs": item.raw_start_ms,
            "rawEndMs": item.raw_end_ms,
            "startMs": item.start_ms,
            "endMs": item.end_ms,
            "minStartMs": item.min_start_ms,
            "maxEndMs": item.max_end_ms,
            "boundaryMode": item.boundary_mode,
            "scope": item.scope,
            "speakerId": item.speaker_id,
            "needsReview": item.needs_review,
            "boundaryWarning": item.boundary_warning,
            "canCut": item.can_cut,
        }
        for item in plan.deletions
    ]
    tracks = [
        {
            "sourceId": project["sources"][track.source_index]["id"],
            "speakerId": track.speaker_id,
            "name": track.name,
            "segments": [
                {
                    "sourceStartMs": segment.source_start_ms,
                    "sourceEndMs": segment.source_end_ms,
                    "targetStartMs": segment.target_start_ms,
                    "targetEndMs": segment.target_end_ms,
                }
                for segment in track.segments
            ],
        }
        for track in plan.tracks
    ]
    global_deletions = [
        {"startMs": item.start_ms, "endMs": item.end_ms}
        for item in sorted(plan.global_deletions)
    ]
    speaker_deletions = {
        speaker_id: [
            {"startMs": item.start_ms, "endMs": item.end_ms}
            for item in sorted(plan.speaker_deletions[speaker_id])
        ]
        for speaker_id in sorted(plan.speaker_deletions)
    }
    actual_plan = {
        "deletions": deletions,
        "globalDeletions": global_deletions,
        "speakerDeletions": speaker_deletions,
        "tracks": [
            {
                "sourceId": track["sourceId"],
                "speakerId": track["speakerId"],
                "segments": track["segments"],
            }
            for track in tracks
        ],
        "timeline": timeline,
    }
    plan_material = {
        "contractVersion": CUT_PLAN_CONTRACT_VERSION,
        "projectFingerprint": project_fingerprint,
        "revision": state["revision"],
        "selectedWordIds": canonical_selected,
        "speakerOverrides": state.get("speakerOverrides", {}),
        "cutOverrides": state.get("cutOverrides", {}),
        "audioAnalysisVersion": audio_analysis_version,
        "audioFingerprints": audio_fingerprints,
        "actualPlan": actual_plan,
    }
    plan_id = "plan-" + hashlib.sha256(
        json.dumps(plan_material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "revision": state["revision"],
        "planId": plan_id,
        "deletions": deletions,
        "timeline": timeline,
        "globalDeletions": global_deletions,
        "speakerDeletions": speaker_deletions,
        "tracks": tracks,
    }
