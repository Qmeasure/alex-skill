from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from .errors import PodcastEditorError


SCHEMA_VERSION = 1
InputMode = Literal["mixed", "multitrack"]


class SpeakerJSON(TypedDict):
    id: str
    name: str
    sourceIndex: int | None


class WordJSON(TypedDict, total=False):
    id: str
    text: str
    startMs: int
    endMs: int
    confidence: float
    punctuationAfter: str


class SourceJSON(TypedDict):
    id: str
    path: str
    durationMs: int
    frameDurationMs: float
    speakerId: str | None


class ProjectJSON(TypedDict):
    schemaVersion: int
    id: str
    name: str
    title: str
    mode: InputMode
    durationMs: int
    createdAt: str
    sources: list[SourceJSON]
    speakers: list[SpeakerJSON]
    utterances: list[dict[str, Any]]


class StateJSON(TypedDict):
    revision: int
    selectedWordIds: list[str]
    speakerNames: dict[str, str]
    speakerOverrides: dict[str, str]
    cutOverrides: dict[str, dict[str, int]]


@dataclass(frozen=True)
class ApiStateUpdate:
    revision: int
    selected_word_ids: list[str]
    speaker_names: dict[str, str]
    speaker_overrides: dict[str, str] = field(default_factory=dict)
    cut_overrides: dict[str, dict[str, int]] = field(default_factory=dict)

    @classmethod
    def parse(cls, value: Any) -> "ApiStateUpdate":
        if not isinstance(value, dict):
            raise PodcastEditorError("invalid_request", "请求内容必须是 JSON 对象。")
        revision = value.get("revision")
        selected = value.get("selectedWordIds")
        names = value.get("speakerNames")
        overrides = value.get("speakerOverrides", {})
        cut_overrides = value.get("cutOverrides", {})
        if not isinstance(revision, int) or revision < 0:
            raise PodcastEditorError("invalid_revision", "revision 必须是非负整数。")
        if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
            raise PodcastEditorError("invalid_selection", "selectedWordIds 必须是字符串数组。")
        if not isinstance(names, dict) or any(
            not isinstance(key, str) or not isinstance(name, str) for key, name in names.items()
        ):
            raise PodcastEditorError("invalid_speaker_names", "speakerNames 必须是说话人 ID 到名称的映射。")
        if not isinstance(overrides, dict) or any(
            not isinstance(utterance_id, str) or not isinstance(speaker_id, str)
            for utterance_id, speaker_id in overrides.items()
        ):
            raise PodcastEditorError(
                "invalid_speaker_overrides", "speakerOverrides 必须是句段 ID 到说话人 ID 的映射。"
            )
        if not isinstance(cut_overrides, dict):
            raise PodcastEditorError("invalid_cut_overrides", "cutOverrides 必须是删除段 ID 到时间范围的映射。")
        normalized_cut_overrides: dict[str, dict[str, int]] = {}
        for cut_id, interval in cut_overrides.items():
            if (
                not isinstance(cut_id, str)
                or not isinstance(interval, dict)
                or set(interval) != {"startMs", "endMs"}
                or not isinstance(interval.get("startMs"), int)
                or not isinstance(interval.get("endMs"), int)
            ):
                raise PodcastEditorError(
                    "invalid_cut_overrides", "每个手动切点必须包含整数 startMs 和 endMs。"
                )
            normalized_cut_overrides[cut_id] = {
                "startMs": interval["startMs"],
                "endMs": interval["endMs"],
            }
        return cls(
            revision,
            list(dict.fromkeys(selected)),
            dict(names),
            dict(overrides),
            normalized_cut_overrides,
        )


def validate_project(project: Any) -> ProjectJSON:
    if not isinstance(project, dict):
        raise PodcastEditorError("invalid_project", "project.json 不是 JSON 对象。", status=500)
    if project.get("schemaVersion") != SCHEMA_VERSION:
        raise PodcastEditorError("unsupported_project", "项目文件版本不受支持。", status=500)
    if project.get("mode") not in ("mixed", "multitrack"):
        raise PodcastEditorError("invalid_project", "项目输入模式无效。", status=500)
    sources = project.get("sources")
    speakers = project.get("speakers")
    utterances = project.get("utterances")
    if not isinstance(sources, list) or not sources:
        raise PodcastEditorError("invalid_project", "项目没有音频来源。", status=500)
    if project.get("mode") == "mixed" and len(sources) != 1:
        raise PodcastEditorError("invalid_project", "合成音轨项目必须只有一个输入文件。", status=500)
    if project.get("mode") == "multitrack" and len(sources) < 2:
        raise PodcastEditorError("invalid_project", "多人分轨项目至少需要两个输入文件。", status=500)
    if not isinstance(speakers, list) or not speakers:
        raise PodcastEditorError("invalid_project", "项目没有说话人。", status=500)
    if not isinstance(utterances, list):
        raise PodcastEditorError("invalid_project", "项目逐字稿格式无效。", status=500)
    if any(not isinstance(speaker, dict) or not isinstance(speaker.get("id"), str) for speaker in speakers):
        raise PodcastEditorError("invalid_project", "项目说话人格式无效。", status=500)
    speaker_ids = {speaker["id"] for speaker in speakers}
    if len(speaker_ids) != len(speakers):
        raise PodcastEditorError("invalid_project", "项目说话人 ID 重复。", status=500)
    word_ids: set[str] = set()
    utterance_ids: set[str] = set()
    for utterance in utterances:
        if not isinstance(utterance, dict) or utterance.get("speakerId") not in speaker_ids:
            raise PodcastEditorError("invalid_project", "逐字稿引用了未知说话人。", status=500)
        utterance_id = utterance.get("id")
        if not isinstance(utterance_id, str) or utterance_id in utterance_ids:
            raise PodcastEditorError("invalid_project", "句段 ID 缺失或重复。", status=500)
        utterance_ids.add(utterance_id)
        words = utterance.get("words")
        if not isinstance(words, list):
            raise PodcastEditorError("invalid_project", "句段词条格式无效。", status=500)
        for word in words:
            if not isinstance(word, dict):
                raise PodcastEditorError("invalid_project", "逐字稿中存在无效词条。", status=500)
            word_id = word.get("id")
            if not isinstance(word_id, str) or word_id in word_ids:
                raise PodcastEditorError("invalid_project", "逐字稿词条 ID 缺失或重复。", status=500)
            if not isinstance(word.get("startMs"), int) or not isinstance(word.get("endMs"), int):
                raise PodcastEditorError("invalid_project", "逐字稿时间戳无效。", status=500)
            if word["startMs"] < 0 or word["endMs"] <= word["startMs"]:
                raise PodcastEditorError("invalid_project", "逐字稿时间范围无效。", status=500)
            punctuation = word.get("punctuationAfter", "")
            if not isinstance(punctuation, str) or any(
                not unicodedata.category(character).startswith("P") for character in punctuation
            ):
                raise PodcastEditorError("invalid_project", "逐字稿标点格式无效。", status=500)
            word_ids.add(word_id)
    return project  # type: ignore[return-value]


def validate_state(state: Any, project: ProjectJSON) -> StateJSON:
    if not isinstance(state, dict):
        raise PodcastEditorError("invalid_state", "review-state.json 不是 JSON 对象。", status=500)
    revision = state.get("revision")
    selected = state.get("selectedWordIds")
    names = state.get("speakerNames")
    overrides = state.get("speakerOverrides", {})
    cut_overrides = state.get("cutOverrides", {})
    if not isinstance(revision, int) or revision < 0:
        raise PodcastEditorError("invalid_state", "审核版本号无效。", status=500)
    if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
        raise PodcastEditorError("invalid_state", "已选词条格式无效。", status=500)
    valid_word_ids = project_word_ids(project)
    unknown_words = sorted(set(selected) - valid_word_ids)
    if unknown_words:
        raise PodcastEditorError(
            "invalid_state", "审核状态引用了未知词条。", details=unknown_words, status=500
        )
    if not isinstance(names, dict):
        raise PodcastEditorError("invalid_state", "说话人名称格式无效。", status=500)
    speaker_ids = {speaker["id"] for speaker in project["speakers"]}
    if set(names) != speaker_ids or any(not isinstance(name, str) or not name.strip() for name in names.values()):
        raise PodcastEditorError("invalid_state", "说话人名称与项目不一致。", status=500)
    utterance_ids = {utterance["id"] for utterance in project["utterances"]}
    if not isinstance(overrides, dict) or any(
        not isinstance(utterance_id, str) or not isinstance(speaker_id, str)
        for utterance_id, speaker_id in overrides.items()
    ):
        raise PodcastEditorError("invalid_state", "说话人修正格式无效。", status=500)
    if set(overrides) - utterance_ids or set(overrides.values()) - speaker_ids:
        raise PodcastEditorError("invalid_state", "说话人修正引用了未知句段或说话人。", status=500)
    if not isinstance(cut_overrides, dict) or any(
        not isinstance(cut_id, str)
        or not isinstance(interval, dict)
        or set(interval) != {"startMs", "endMs"}
        or not isinstance(interval.get("startMs"), int)
        or not isinstance(interval.get("endMs"), int)
        for cut_id, interval in cut_overrides.items()
    ):
        raise PodcastEditorError("invalid_state", "手动切点格式无效。", status=500)
    normalized = dict(state)
    normalized["speakerOverrides"] = dict(overrides)
    normalized["cutOverrides"] = {
        cut_id: {"startMs": interval["startMs"], "endMs": interval["endMs"]}
        for cut_id, interval in cut_overrides.items()
    }
    return normalized  # type: ignore[return-value]


def iter_project_words(project: ProjectJSON):
    for utterance in project["utterances"]:
        for word in utterance["words"]:
            yield {**word, "speakerId": utterance["speakerId"], "utteranceId": utterance["id"]}


def project_word_ids(project: ProjectJSON) -> set[str]:
    return {word["id"] for word in iter_project_words(project)}
