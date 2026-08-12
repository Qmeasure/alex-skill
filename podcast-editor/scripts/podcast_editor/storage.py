from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from .contracts import ApiStateUpdate, ProjectJSON, StateJSON, project_word_ids, validate_project, validate_state
from .errors import PodcastEditorError, RevisionConflict


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except FileNotFoundError as exc:
        raise PodcastEditorError("project_not_found", f"找不到项目文件：{path}", status=404) from exc
    except json.JSONDecodeError as exc:
        raise PodcastEditorError("invalid_json", f"JSON 文件损坏：{path}", status=500) from exc


class ProjectStore:
    PROJECT_FILE = "project.json"
    STATE_FILE = "review-state.json"

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self._lock = threading.RLock()

    @property
    def project_path(self) -> Path:
        return self.root / self.PROJECT_FILE

    @property
    def state_path(self) -> Path:
        return self.root / self.STATE_FILE

    def create(self, project: ProjectJSON, state: StateJSON) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        valid_project = validate_project(project)
        valid_state = validate_state(state, valid_project)
        write_json_atomic(self.project_path, valid_project)
        write_json_atomic(self.state_path, valid_state)

    def load_project(self) -> ProjectJSON:
        return validate_project(read_json(self.project_path))

    def load_state(self, project: ProjectJSON | None = None) -> StateJSON:
        current_project = project or self.load_project()
        return validate_state(read_json(self.state_path), current_project)

    def update_state(
        self,
        update: ApiStateUpdate,
        *,
        validate_candidate: Callable[[ProjectJSON, StateJSON], None] | None = None,
    ) -> StateJSON:
        with self._lock:
            project = self.load_project()
            current = self.load_state(project)
            if update.revision != current["revision"]:
                raise RevisionConflict(update.revision, current["revision"])

            word_ids = project_word_ids(project)
            unknown = sorted(set(update.selected_word_ids) - word_ids)
            if unknown:
                raise PodcastEditorError("unknown_words", "选择中包含未知词条。", details=unknown)

            speaker_ids = {speaker["id"] for speaker in project["speakers"]}
            unknown_speakers = sorted(set(update.speaker_names) - speaker_ids)
            if unknown_speakers:
                raise PodcastEditorError(
                    "unknown_speakers", "名称修改包含未知说话人。", details=unknown_speakers
                )
            names = dict(current["speakerNames"])
            for speaker_id, name in update.speaker_names.items():
                cleaned = name.strip()
                if not cleaned or len(cleaned) > 80:
                    raise PodcastEditorError("invalid_speaker_name", "嘉宾名不能为空，且不得超过 80 个字符。")
                names[speaker_id] = cleaned
            utterance_ids = {utterance["id"] for utterance in project["utterances"]}
            unknown_utterances = sorted(set(update.speaker_overrides) - utterance_ids)
            unknown_override_speakers = sorted(set(update.speaker_overrides.values()) - speaker_ids)
            if unknown_utterances or unknown_override_speakers:
                raise PodcastEditorError(
                    "invalid_speaker_overrides",
                    "嘉宾修正包含未知句段或说话人。",
                    details={
                        "utteranceIds": unknown_utterances,
                        "speakerIds": unknown_override_speakers,
                    },
                )
            next_state: StateJSON = {
                "revision": current["revision"] + 1,
                "selectedWordIds": update.selected_word_ids,
                "speakerNames": names,
                "speakerOverrides": dict(update.speaker_overrides),
                "cutOverrides": dict(update.cut_overrides),
            }
            validate_state(next_state, project)
            if validate_candidate is not None:
                validate_candidate(project, next_state)
            write_json_atomic(self.state_path, next_state)
            return next_state

    def api_project(self, status: dict[str, Any]) -> dict[str, Any]:
        project = self.load_project()
        state = self.load_state(project)
        return {
            "project": project,
            "state": state,
            "playback": {"url": "/api/audio/source"},
            "status": status,
        }
