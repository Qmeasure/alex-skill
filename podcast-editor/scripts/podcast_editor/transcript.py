from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass
from typing import Any

from .contracts import InputMode, SpeakerJSON, WordJSON
from .errors import PodcastEditorError


@dataclass(frozen=True)
class RawWord:
    text: str
    start_ms: int
    end_ms: int
    raw_speaker: str
    utterance_index: int
    confidence: float | None
    punctuation_after: str = ""


FILLER_WORDS = frozenset({"呃", "啊", "嗯", "额", "哦", "哎", "呐"})


def _speaker_label(utterance: dict[str, Any]) -> str | None:
    additions = utterance.get("additions")
    candidates = [
        utterance.get("speaker_id"),
        utterance.get("speakerId"),
        utterance.get("speaker"),
    ]
    if isinstance(additions, dict):
        candidates.extend(
            [additions.get("speaker_id"), additions.get("speakerId"), additions.get("speaker")]
        )
    for candidate in candidates:
        if candidate is not None and str(candidate).strip():
            return str(candidate).strip()
    return None


def parse_asr_words(
    result: dict[str, Any], *, force_speaker: str | None = None, require_speaker: bool = False
) -> list[RawWord]:
    payload = result.get("result") if isinstance(result.get("result"), dict) else result
    utterances = payload.get("utterances") if isinstance(payload, dict) else None
    if not isinstance(utterances, list):
        raise PodcastEditorError("invalid_asr_response", "转录结果没有 utterances。", status=502)
    parsed: list[RawWord] = []
    for utterance_index, utterance in enumerate(utterances):
        if not isinstance(utterance, dict):
            continue
        speaker = force_speaker or _speaker_label(utterance)
        if speaker is None:
            if require_speaker:
                raise PodcastEditorError(
                    "missing_speaker_info",
                    "合成音轨的转录结果没有说话人标签，无法按嘉宾审核。",
                    status=502,
                )
            speaker = "speaker-unknown"
        words = utterance.get("words")
        if not isinstance(words, list):
            continue
        valid_words: list[dict[str, Any]] = []
        for word in words:
            if not isinstance(word, dict):
                continue
            text = str(word.get("text") or "")
            try:
                start = int(word.get("start_time"))
                end = int(word.get("end_time"))
            except (TypeError, ValueError):
                continue
            if not text or start < 0 or end <= start:
                continue
            confidence_value = word.get("confidence")
            try:
                confidence = float(confidence_value) if confidence_value is not None else None
            except (TypeError, ValueError):
                confidence = None
            valid_words.append(
                {
                    "text": text,
                    "start": start,
                    "end": end,
                    "confidence": confidence,
                }
            )
        punctuation = _punctuation_by_word(str(utterance.get("text") or ""), valid_words)
        for word_index, word in enumerate(valid_words):
            parsed.append(
                RawWord(
                    word["text"],
                    word["start"],
                    word["end"],
                    speaker,
                    utterance_index,
                    word["confidence"],
                    punctuation.get(word_index, ""),
                )
            )
    if not parsed:
        raise PodcastEditorError("empty_transcript", "转录结果没有可用的字级时间戳。", status=422)
    return parsed


def build_transcript(
    mode: InputMode, per_source_words: list[list[RawWord]]
) -> tuple[list[SpeakerJSON], list[dict[str, Any]]]:
    if mode == "mixed":
        raw_order: list[str] = []
        for word in per_source_words[0]:
            if word.raw_speaker not in raw_order:
                raw_order.append(word.raw_speaker)
        raw_to_id = {raw: f"speaker-{index + 1:02d}" for index, raw in enumerate(raw_order)}
        speakers: list[SpeakerJSON] = [
            {"id": raw_to_id[raw], "name": f"嘉宾{_chinese_number(index + 1)}", "sourceIndex": None}
            for index, raw in enumerate(raw_order)
        ]
        combined = [(0, raw_word) for raw_word in per_source_words[0]]
    else:
        speakers = [
            {"id": f"speaker-{index + 1:02d}", "name": f"嘉宾{_chinese_number(index + 1)}", "sourceIndex": index}
            for index in range(len(per_source_words))
        ]
        raw_to_id = {f"speaker-{index + 1:02d}": f"speaker-{index + 1:02d}" for index in range(len(per_source_words))}
        combined = [
            (source_index, raw_word)
            for source_index, source_words in enumerate(per_source_words)
            for raw_word in source_words
        ]
        combined.sort(key=lambda item: (item[1].start_ms, item[1].end_ms, item[0], item[1].utterance_index))

    utterance_order: list[tuple[int, int, str]] = []
    utterances_by_key: dict[tuple[int, int, str], dict[str, Any]] = {}
    for index, (source_index, raw_word) in enumerate(combined):
        speaker_id = raw_to_id.get(raw_word.raw_speaker)
        if speaker_id is None:
            speaker_id = f"speaker-{source_index + 1:02d}"
        item: WordJSON = {
            "id": f"word-{index + 1:07d}",
            "text": raw_word.text,
            "startMs": raw_word.start_ms,
            "endMs": raw_word.end_ms,
        }
        if raw_word.confidence is not None:
            item["confidence"] = raw_word.confidence
        if raw_word.punctuation_after:
            item["punctuationAfter"] = raw_word.punctuation_after
        key = (source_index, raw_word.utterance_index, speaker_id)
        if key not in utterances_by_key:
            utterance_order.append(key)
            utterances_by_key[key] = {
                "id": f"utterance-{len(utterance_order):06d}",
                "speakerId": speaker_id,
                "startMs": raw_word.start_ms,
                "endMs": raw_word.end_ms,
                "words": [],
            }
        utterance = utterances_by_key[key]
        utterance["startMs"] = min(utterance["startMs"], raw_word.start_ms)
        utterance["endMs"] = max(utterance["endMs"], raw_word.end_ms)
        utterance["words"].append(item)
    utterances = [utterances_by_key[key] for key in utterance_order]
    utterances.sort(key=lambda item: (item["startMs"], item["endMs"], item["id"]))
    return speakers, utterances


def filler_word_ids(utterances: list[dict[str, Any]]) -> list[str]:
    return [
        word["id"]
        for utterance in utterances
        for word in utterance["words"]
        if word.get("text", "").strip() in FILLER_WORDS
    ]


def build_review_turns(utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(utterances, key=lambda item: (item["startMs"], item["endMs"], item["id"]))
    turns: list[dict[str, Any]] = []
    for utterance in ordered:
        if not turns or turns[-1]["speakerId"] != utterance["speakerId"]:
            turns.append(
                {
                    "id": f"turn-{len(turns) + 1:06d}",
                    "speakerId": utterance["speakerId"],
                    "startMs": utterance["startMs"],
                    "endMs": utterance["endMs"],
                    "utteranceIds": [utterance["id"]],
                }
            )
            continue
        turns[-1]["endMs"] = max(turns[-1]["endMs"], utterance["endMs"])
        turns[-1]["utteranceIds"].append(utterance["id"])
    return turns


def apply_speaker_overrides(
    project: dict[str, Any], overrides: dict[str, str]
) -> dict[str, Any]:
    if not overrides:
        return project
    utterances = [
        {**utterance, "speakerId": overrides.get(utterance["id"], utterance["speakerId"])}
        for utterance in project["utterances"]
    ]
    return {**project, "utterances": utterances}


def apply_punctuation(project: dict[str, Any], result: dict[str, Any]) -> int:
    """Copy punctuation from a new ASR pass without replacing existing words."""

    punctuated = parse_asr_words(result, require_speaker=False)
    existing = [word for utterance in project["utterances"] for word in utterance["words"]]
    original_text = "".join(str(word["text"]) for word in existing)
    punctuated_text = "".join(word.text for word in punctuated)
    similarity = difflib.SequenceMatcher(a=original_text, b=punctuated_text, autojunk=False).ratio()
    if similarity < 0.98:
        raise PodcastEditorError(
            "punctuation_text_mismatch",
            "标点转录与原逐字稿不一致，未写入项目。",
            details={
                "originalLength": len(original_text),
                "punctuatedLength": len(punctuated_text),
                "similarity": round(similarity, 6),
            },
            status=422,
        )

    original_word_fields = [
        (word["id"], word["text"], word["startMs"], word["endMs"]) for word in existing
    ]
    for word in existing:
        word.pop("punctuationAfter", None)

    used: set[str] = set()
    count = 0
    for raw_word in punctuated:
        if not raw_word.punctuation_after:
            continue
        nearby = [
            word
            for word in existing
            if word["id"] not in used
            and word["startMs"] < raw_word.end_ms + 1_000
            and word["endMs"] > raw_word.start_ms - 1_000
        ]
        exact = [word for word in nearby if word["text"] == raw_word.text]
        candidates = exact or nearby
        if not candidates:
            continue
        target = min(
            candidates,
            key=lambda word: abs(word["startMs"] - raw_word.start_ms)
            + abs(word["endMs"] - raw_word.end_ms),
        )
        target["punctuationAfter"] = raw_word.punctuation_after
        used.add(target["id"])
        count += len(raw_word.punctuation_after)

    final_word_fields = [
        (word["id"], word["text"], word["startMs"], word["endMs"]) for word in existing
    ]
    if final_word_fields != original_word_fields:
        raise PodcastEditorError(
            "punctuation_changed_words",
            "标点对齐改变了原逐字稿，未写入项目。",
            status=500,
        )
    return count


def _is_punctuation(character: str) -> bool:
    return bool(character) and unicodedata.category(character).startswith("P")


def _punctuation_by_word(text: str, words: list[dict[str, Any]]) -> dict[int, str]:
    if not text or not words:
        return {}
    source_characters: list[str] = []
    source_word_indexes: list[int] = []
    for word_index, word in enumerate(words):
        for character in str(word["text"]):
            if not character.isspace():
                source_characters.append(character)
                source_word_indexes.append(word_index)

    display_characters: list[str] = []
    punctuation_after_character: dict[int, str] = {}
    last_base_index: int | None = None
    for character in text:
        if character.isspace():
            continue
        if _is_punctuation(character):
            if last_base_index is not None:
                punctuation_after_character[last_base_index] = (
                    punctuation_after_character.get(last_base_index, "") + character
                )
            continue
        display_characters.append(character)
        last_base_index = len(display_characters) - 1

    matcher = difflib.SequenceMatcher(a=display_characters, b=source_characters, autojunk=False)
    display_to_source: dict[int, int] = {}
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            display_to_source[block.a + offset] = block.b + offset

    result: dict[int, str] = {}
    matched_display = sorted(display_to_source)
    for display_index, punctuation in punctuation_after_character.items():
        source_index = display_to_source.get(display_index)
        if source_index is None and matched_display:
            nearest = min(matched_display, key=lambda index: abs(index - display_index))
            source_index = display_to_source[nearest]
        if source_index is None or source_index >= len(source_word_indexes):
            continue
        word_index = source_word_indexes[source_index]
        result[word_index] = result.get(word_index, "") + punctuation
    return result


def _chinese_number(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 20:
        return "十" + (digits[value % 10] if value % 10 else "")
    if value < 100:
        return digits[value // 10] + "十" + (digits[value % 10] if value % 10 else "")
    return str(value)
