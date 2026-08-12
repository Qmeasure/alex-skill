from __future__ import annotations

import json
import hashlib
import mimetypes
import os
import shutil
import threading
import urllib.parse
from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .contracts import ApiStateUpdate
from .draft import detect_draft_root, export_jianying_draft
from .errors import PodcastEditorError, RevisionConflict, raise_if_cancelled
from .media import AUDIO_ANALYSIS_VERSION, AudioAnalysisCache, audio_fingerprint
from .planning import build_cut_plan, build_preview_utterances, cut_plan_payload
from .preview import render_monitor_mix, render_preview
from .storage import ProjectStore, read_json, write_json_atomic
from .transcript import apply_speaker_overrides, build_review_turns


class PodcastService:
    def __init__(self, store: ProjectStore, *, draft_root: str | Path | None = None):
        self.store = store
        self.draft_root = Path(draft_root).expanduser().resolve() if draft_root else None
        self._status: dict[str, Any] = {"phase": "idle"}
        self._status_lock = threading.RLock()
        self._operation_lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._cancel_generation = 0
        self._pending_operations = 0
        self._analysis_cache = AudioAnalysisCache(self.store.root / "cache" / "audio-analysis")

    def status(self) -> dict[str, Any]:
        with self._status_lock:
            return dict(self._status)

    def set_status(self, phase: str, message: str | None = None) -> None:
        with self._status_lock:
            self._status = {"phase": phase}
            if message:
                self._status["message"] = message

    def project_payload(self) -> dict[str, Any]:
        project = self.store.load_project()
        state = self.store.load_state(project)
        effective_project = apply_speaker_overrides(project, state["speakerOverrides"])
        payload = self.store.api_project(self.status())
        payload["project"] = effective_project
        payload["reviewTurns"] = build_review_turns(effective_project["utterances"])
        _, cut_plan = self._current_cut_plan(project, state)
        payload["playback"].update(self._playback_payload(project, cut_plan))
        return payload

    def update_state(self, body: Any) -> dict[str, Any]:
        update = ApiStateUpdate.parse(body)
        candidate_plan: dict[str, Any] = {}

        def validate_candidate(project, candidate_state):
            plan, _ = self._current_cut_plan(project, candidate_state)
            valid_ids = {item.id for item in plan.deletions}
            candidate_state["cutOverrides"] = {
                cut_id: interval
                for cut_id, interval in candidate_state.get("cutOverrides", {}).items()
                if cut_id in valid_ids
            }
            _, payload = self._current_cut_plan(project, candidate_state)
            candidate_plan.update(payload)

        state = self.store.update_state(update, validate_candidate=validate_candidate)
        project = self.store.load_project()
        effective_project = apply_speaker_overrides(project, state["speakerOverrides"])
        return {
            "state": state,
            "revision": state["revision"],
            "selectedWordIds": state["selectedWordIds"],
            "speakerNames": state["speakerNames"],
            "speakerOverrides": state["speakerOverrides"],
            "cutOverrides": state["cutOverrides"],
            "project": effective_project,
            "reviewTurns": build_review_turns(effective_project["utterances"]),
            "savedAt": datetime.now(timezone.utc).isoformat(),
            "cutPlan": candidate_plan,
            "timeline": candidate_plan["timeline"],
            "playback": self._playback_payload(project, candidate_plan),
        }

    @staticmethod
    def _playback_payload(project, cut_plan) -> dict[str, Any]:
        sources = [
            {
                "sourceId": source["id"],
                "speakerId": source["speakerId"],
                "url": f"/api/audio/source?sourceId={urllib.parse.quote(source['id'])}",
            }
            for source in project["sources"]
        ]
        runs = _playback_runs(cut_plan, sources)
        return {
            "strategy": "dual-audio-preload-v1",
            "revision": cut_plan["revision"],
            "planId": cut_plan["planId"],
            "timeline": cut_plan["timeline"],
            "cutPlan": cut_plan,
            "sources": sources,
            "runs": runs,
            "tracks": cut_plan["tracks"],
        }

    def _current_cut_plan(self, project, state):
        sources_by_path = {str(Path(source["path"]).expanduser().resolve()): source for source in project["sources"]}

        def resolve(path, raw_start, raw_end, previous_word, next_word):
            source = sources_by_path[str(Path(path).expanduser().resolve())]
            return self._analysis_for_source(source).adjust_deletion(
                raw_start, raw_end, previous_word, next_word
            )

        plan = build_cut_plan(project, state, boundary_resolver=resolve)
        fingerprints = {source["id"]: audio_fingerprint(source["path"]) for source in project["sources"]}
        payload = cut_plan_payload(
            project,
            state,
            plan,
            audio_fingerprints=fingerprints,
            audio_analysis_version=AUDIO_ANALYSIS_VERSION,
        )
        return plan, payload

    def _analysis_for_source(self, source):
        return self._analysis_cache.get(source["path"])

    def waveform(self, query: dict[str, list[str]]) -> dict[str, Any]:
        project = self.store.load_project()
        source_id = _single_query_value(query, "sourceId", required=False)
        if project["mode"] == "multitrack" and not source_id:
            raise PodcastEditorError("source_required", "多人分轨查看波形时必须指定 sourceId。")
        if not source_id:
            source = project["sources"][0]
        else:
            source = next((item for item in project["sources"] if item["id"] == source_id), None)
            if source is None:
                raise PodcastEditorError("unknown_source", "sourceId 不属于当前项目。")
        start_ms = _query_integer(query, "startMs", minimum=0)
        end_ms = _query_integer(query, "endMs", minimum=1)
        points = _query_integer(query, "points", minimum=16, maximum=4000)
        if end_ms <= start_ms or end_ms > source["durationMs"]:
            raise PodcastEditorError("invalid_waveform_range", "波形时间范围无效。")
        analysis = self._analysis_for_source(source)
        return {
            "sourceId": source["id"],
            "startMs": start_ms,
            "endMs": end_ms,
            "points": analysis.waveform(start_ms, end_ms, points),
        }

    def cancel(self, body: Any) -> dict[str, Any]:
        if body is not None and not isinstance(body, dict):
            raise PodcastEditorError("invalid_request", "请求内容必须是 JSON 对象。")
        with self._status_lock:
            active = self._pending_operations > 0
            if active:
                self._cancel_generation += 1
                self._cancel_event.set()
                self._status = {"phase": "cancelling", "message": "正在取消操作。"}
            status = dict(self._status)
        return {"cancellationRequested": active, "status": status}

    @contextmanager
    def _queued_operation(self):
        with self._status_lock:
            self._pending_operations += 1
            cancel_generation = self._cancel_generation
        acquired = False
        try:
            self._operation_lock.acquire()
            acquired = True
            yield cancel_generation
        except PodcastEditorError as exc:
            if exc.code == "operation_cancelled":
                self.set_status("cancelled", "操作已取消。")
            raise
        finally:
            with self._status_lock:
                self._pending_operations -= 1
                if self._pending_operations == 0 and self._status.get("phase") == "cancelling":
                    self._status = {"phase": "cancelled", "message": "操作已取消。"}
            if acquired:
                self._operation_lock.release()

    def _check_cancel_generation(self, expected_generation: int) -> None:
        with self._status_lock:
            if expected_generation != self._cancel_generation:
                raise PodcastEditorError("operation_cancelled", "操作已取消。", status=409)

    def _start_operation(self, phase: str, message: str, expected_generation: int) -> None:
        with self._status_lock:
            if expected_generation != self._cancel_generation:
                raise PodcastEditorError("operation_cancelled", "操作已取消。", status=409)
            self._cancel_event.clear()
            self._status = {"phase": phase, "message": message}

    def _raise_if_cancelled(self) -> None:
        raise_if_cancelled(self._cancel_event)

    def _finish_operation(self, error: BaseException | None) -> None:
        if isinstance(error, PodcastEditorError) and error.code == "operation_cancelled":
            self.set_status("cancelled", "操作已取消。")
        elif error is not None:
            self.set_status("error", "操作失败。")
        else:
            self.set_status("idle")

    def source_audio(self, source_id: str | None = None) -> Path:
        project = self.store.load_project()
        if source_id is not None:
            source = next((item for item in project["sources"] if item["id"] == source_id), None)
            if source is None:
                raise PodcastEditorError("unknown_source", "sourceId 不属于当前项目。", status=404)
            return Path(source["path"])
        if project["mode"] == "mixed":
            return Path(project["sources"][0]["path"])
        output = self.store.root / "cache" / "monitor.wav"
        if not output.is_file():
            with self._queued_operation() as cancel_generation:
                self._check_cancel_generation(cancel_generation)
                if not output.is_file():
                    self._start_operation(
                        "rendering_monitor",
                        "正在生成多人分轨试听音频。",
                        cancel_generation,
                    )
                    temporary = output.with_name("monitor.tmp.wav")
                    operation_error: BaseException | None = None
                    try:
                        render_monitor_mix(project, temporary, cancel_event=self._cancel_event)
                        self._raise_if_cancelled()
                        os.replace(temporary, output)
                    except BaseException as exc:
                        operation_error = exc
                        raise
                    finally:
                        temporary.unlink(missing_ok=True)
                        self._finish_operation(operation_error)
        return output

    def render_preview(self, body: Any) -> dict[str, Any]:
        revision, requested_plan_id = _required_plan_identity(body)
        project = self.store.load_project()
        state = self.store.load_state(project)
        effective_project = apply_speaker_overrides(project, state["speakerOverrides"])
        if revision != state["revision"]:
            raise RevisionConflict(revision, state["revision"])
        plan, current_cut_plan = self._current_cut_plan(project, state)
        _require_matching_plan(requested_plan_id, current_cut_plan["planId"])
        _require_cuttable_plan(plan)
        output = self.store.root / "cache" / f"preview-{state['revision']}-{current_cut_plan['planId']}.wav"
        metadata = self.store.root / "cache" / f"preview-{state['revision']}-{current_cut_plan['planId']}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.is_file() and metadata.is_file():
            cached = read_json(metadata)
            if (
                isinstance(cached, dict)
                and cached.get("revision") == state["revision"]
                and cached.get("planId") == current_cut_plan["planId"]
                and isinstance(cached.get("utterances"), list)
                and isinstance(cached.get("timeline"), dict)
            ):
                return cached

        with self._queued_operation() as cancel_generation:
            self._start_operation(
                "rendering_preview",
                "正在生成审核试听音频。",
                cancel_generation,
            )
            temporary = output.with_name(f"preview-{state['revision']}.tmp.wav")
            operation_error: BaseException | None = None
            try:
                self._raise_if_cancelled()
                self._raise_if_cancelled()
                render_preview(project, plan, temporary, cancel_event=self._cancel_event)
                self._raise_if_cancelled()
                self._assert_plan_current(revision, requested_plan_id)
                os.replace(temporary, output)
            except BaseException as exc:
                operation_error = exc
                raise
            finally:
                temporary.unlink(missing_ok=True)
                self._finish_operation(operation_error)
        response = {
            "revision": state["revision"],
            "planId": current_cut_plan["planId"],
            "url": f"/api/audio/preview?revision={state['revision']}&planId={current_cut_plan['planId']}",
            "utterances": build_preview_utterances(effective_project, state, plan),
            "timeline": current_cut_plan["timeline"],
            "cutPlan": current_cut_plan,
        }
        write_json_atomic(metadata, response)
        return response

    def preview_audio(self, revision: int, plan_id: str) -> Path:
        output = self.store.root / "cache" / f"preview-{revision}-{plan_id}.wav"
        if not output.is_file():
            raise PodcastEditorError("preview_not_found", "预览音频不存在，请重新生成。", status=404)
        return output

    def export(self, body: Any) -> dict[str, Any]:
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise PodcastEditorError("invalid_request", "请求内容必须是 JSON 对象。")
        revision, requested_plan_id = _required_plan_identity(body)
        draft_name = body.get("draftName")
        if draft_name is not None and not isinstance(draft_name, str):
            raise PodcastEditorError("invalid_draft_name", "draftName 必须是字符串。")
        project = self.store.load_project()
        state = self.store.load_state(project)
        if revision != state["revision"]:
            raise RevisionConflict(revision, state["revision"])
        plan, current_cut_plan = self._current_cut_plan(project, state)
        _require_matching_plan(requested_plan_id, current_cut_plan["planId"])
        _require_cuttable_plan(plan)
        root = detect_draft_root(self.draft_root)
        with self._queued_operation() as cancel_generation:
            self._start_operation("exporting", "正在生成剪映草稿。", cancel_generation)
            operation_error: BaseException | None = None
            path: Path | None = None
            try:
                self._raise_if_cancelled()
                self._raise_if_cancelled()
                name, path = export_jianying_draft(
                    project,
                    plan,
                    root,
                    draft_name=draft_name,
                    cancel_event=self._cancel_event,
                )
                try:
                    self._raise_if_cancelled()
                    self._assert_plan_current(revision, requested_plan_id)
                except PodcastEditorError:
                    if path.exists():
                        shutil.rmtree(path)
                    raise
            except BaseException as exc:
                operation_error = exc
                raise
            finally:
                self._finish_operation(operation_error)
        return {
            "revision": state["revision"],
            "planId": current_cut_plan["planId"],
            "draftName": name,
            "draftPath": str(path),
        }

    def _assert_plan_current(self, revision: int, plan_id: str) -> None:
        project = self.store.load_project()
        state = self.store.load_state(project)
        if state["revision"] != revision:
            raise RevisionConflict(revision, state["revision"])
        _, current = self._current_cut_plan(project, state)
        _require_matching_plan(plan_id, current["planId"])


def _playback_runs(cut_plan: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, int]] = []
    deletions = cut_plan.get("globalDeletions", [])
    for segment in cut_plan["timeline"]["segments"]:
        current = {
            "sourceStartMs": int(segment["sourceStartMs"]),
            "sourceEndMs": int(segment["sourceEndMs"]),
            "targetStartMs": int(segment["targetStartMs"]),
            "targetEndMs": int(segment["targetEndMs"]),
        }
        if merged:
            previous = merged[-1]
            source_gap = current["sourceStartMs"] - previous["sourceEndMs"]
            target_gap = current["targetStartMs"] - previous["targetEndMs"]
            crosses_deletion = any(
                int(item["startMs"]) < current["sourceStartMs"]
                and int(item["endMs"]) > previous["sourceEndMs"]
                for item in deletions
            )
            if (
                0 <= source_gap <= 2
                and 0 <= target_gap <= 2
                and not crosses_deletion
            ):
                previous["sourceEndMs"] = current["sourceEndMs"]
                previous["targetEndMs"] = current["targetEndMs"]
                continue
        merged.append(current)

    runs: list[dict[str, Any]] = []
    for interval in merged:
        identity = "|".join(
            (
                cut_plan["planId"],
                str(interval["sourceStartMs"]),
                str(interval["sourceEndMs"]),
                str(interval["targetStartMs"]),
                str(interval["targetEndMs"]),
            )
        )
        run_sources = [
            {
                "sourceId": source["sourceId"],
                "streamUrl": source["url"],
                "sourceStartMs": interval["sourceStartMs"],
                "sourceEndMs": interval["sourceEndMs"],
            }
            for source in sources
        ]
        runs.append(
            {
                "id": "run-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
                **interval,
                "sources": run_sources,
            }
        )
    return runs


def _optional_revision(body: Any) -> int | None:
    if body is None:
        return None
    if not isinstance(body, dict):
        raise PodcastEditorError("invalid_request", "请求内容必须是 JSON 对象。")
    revision = body.get("revision")
    if revision is not None and (not isinstance(revision, int) or revision < 0):
        raise PodcastEditorError("invalid_revision", "revision 必须是非负整数。")
    return revision


def _required_plan_identity(body: Any) -> tuple[int, str]:
    if not isinstance(body, dict):
        raise PodcastEditorError("invalid_request", "请求内容必须是 JSON 对象。")
    revision = body.get("revision")
    if not isinstance(revision, int) or revision < 0:
        raise PodcastEditorError("invalid_revision", "revision 必须是非负整数。")
    plan_id = body.get("planId")
    if not isinstance(plan_id, str) or not plan_id.startswith("plan-"):
        raise PodcastEditorError("invalid_plan_id", "planId 无效。")
    return revision, plan_id


def _require_matching_plan(requested: str, current: str) -> None:
    if requested != current:
        raise PodcastEditorError(
            "plan_conflict",
            "剪辑计划已变化，请刷新后重试。",
            details={"expected": requested, "actual": current},
            status=409,
        )


def _require_cuttable_plan(plan) -> None:
    uncuttable = [item.id for item in plan.deletions if not item.can_cut]
    if uncuttable:
        raise PodcastEditorError(
            "uncuttable_selection",
            "有些选中文字无法在不影响保留内容的前提下剪掉，请先调整选词。",
            details={"deletionIds": uncuttable},
            status=409,
        )


def _single_query_value(query: dict[str, list[str]], name: str, *, required: bool = True) -> str | None:
    values = query.get(name, [])
    if len(values) != 1 or not values[0]:
        if required:
            raise PodcastEditorError("invalid_query", f"{name} 参数缺失或重复。")
        return None
    return values[0]


def _query_integer(
    query: dict[str, list[str]], name: str, *, minimum: int, maximum: int | None = None
) -> int:
    raw = _single_query_value(query, name)
    try:
        value = int(raw or "")
    except ValueError as exc:
        raise PodcastEditorError("invalid_query", f"{name} 必须是整数。") from exc
    if value < minimum or (maximum is not None and value > maximum):
        raise PodcastEditorError("invalid_query", f"{name} 超出允许范围。")
    return value


class ReviewRequestHandler(BaseHTTPRequestHandler):
    server_version = "PodcastEditor/1"

    @property
    def service(self) -> PodcastService:
        return self.server.service  # type: ignore[attr-defined, no-any-return]

    @property
    def static_root(self) -> Path:
        return self.server.static_root  # type: ignore[attr-defined, no-any-return]

    def do_GET(self) -> None:
        try:
            self._validate_host()
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.path == "/api/project":
                self._send_json(self.service.project_payload())
                return
            if parsed.path == "/api/waveform":
                self._send_json(self.service.waveform(urllib.parse.parse_qs(parsed.query)))
                return
            if parsed.path == "/api/audio/source":
                query = urllib.parse.parse_qs(parsed.query)
                source_id = _single_query_value(query, "sourceId", required=False)
                source_path = self.service.source_audio(source_id)
                etag = '"audio-' + audio_fingerprint(source_path) + '"'
                self._send_file(
                    source_path,
                    etag=etag,
                    cache_control="private, max-age=3600, must-revalidate",
                )
                return
            if parsed.path == "/api/audio/preview":
                query = urllib.parse.parse_qs(parsed.query)
                try:
                    revision = int(query.get("revision", [""])[0])
                except ValueError as exc:
                    raise PodcastEditorError("invalid_revision", "preview revision 无效。") from exc
                plan_id = query.get("planId", [""])[0]
                if not plan_id:
                    raise PodcastEditorError("invalid_plan_id", "preview planId 无效。")
                self._send_file(self.service.preview_audio(revision, plan_id))
                return
            self._send_static(parsed.path)
        except PodcastEditorError as exc:
            self._send_error(exc)
        except Exception:
            self._send_json(
                PodcastEditorError("internal_error", "本地服务发生错误。", status=500).as_dict(), status=500
            )

    def do_PUT(self) -> None:
        self._handle_json_route({"/api/state": self.service.update_state})

    def do_POST(self) -> None:
        self._handle_json_route(
            {
                "/api/preview": self.service.render_preview,
                "/api/export": self.service.export,
                "/api/cancel": self.service.cancel,
            }
        )

    def _handle_json_route(self, routes: dict[str, Any]) -> None:
        try:
            self._validate_host()
            parsed = urllib.parse.urlsplit(self.path)
            action = routes.get(parsed.path)
            if action is None:
                raise PodcastEditorError("not_found", "接口不存在。", status=404)
            body = self._read_json_body()
            self._send_json(action(body))
        except PodcastEditorError as exc:
            self._send_error(exc)
        except Exception:
            self._send_json(
                PodcastEditorError("internal_error", "本地服务发生错误。", status=500).as_dict(), status=500
            )

    def _read_json_body(self) -> Any:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise PodcastEditorError("invalid_request", "Content-Length 无效。") from exc
        if length > 2_000_000:
            raise PodcastEditorError("request_too_large", "请求内容过大。", status=413)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PodcastEditorError("invalid_json", "请求内容不是合法 JSON。") from exc

    def _validate_host(self) -> None:
        hostname = self.headers.get("Host", "").partition(":")[0].strip("[]").lower()
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise PodcastEditorError("invalid_host", "本地审核服务只接受回环地址访问。", status=403)

    def _send_json(self, value: Any, *, status: int = 200) -> None:
        encoded = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error(self, error: PodcastEditorError) -> None:
        if error.code == "project_not_found":
            error = PodcastEditorError("project_not_found", "找不到审核项目文件。", status=404)
        elif error.code == "invalid_json" and error.status == 500:
            error = PodcastEditorError("invalid_json", "审核项目文件损坏。", status=500)
        elif error.code == "draft_root_not_found":
            error = PodcastEditorError(
                "draft_root_not_found",
                "找不到剪映草稿目录，请检查 --draft-root 或 JY_PROJECTS_ROOT。",
                status=error.status,
            )
        self._send_json(error.as_dict(), status=error.status)

    def _send_static(self, request_path: str) -> None:
        if request_path == "/":
            relative = "review.html"
        elif request_path.startswith("/assets/"):
            relative = request_path.removeprefix("/assets/")
        else:
            relative = request_path.lstrip("/")
        target = (self.static_root / relative).resolve()
        try:
            target.relative_to(self.static_root.resolve())
        except ValueError as exc:
            raise PodcastEditorError("not_found", "文件不存在。", status=404) from exc
        if not target.is_file():
            raise PodcastEditorError("not_found", "文件不存在。", status=404)
        self._send_file(target, allow_range=False)

    def _send_file(
        self,
        path: Path,
        *,
        allow_range: bool = True,
        etag: str | None = None,
        cache_control: str | None = None,
    ) -> None:
        if not path.is_file():
            raise PodcastEditorError("not_found", "文件不存在。", status=404)
        total = path.stat().st_size
        start, end = 0, max(0, total - 1)
        status = HTTPStatus.OK
        range_header = self.headers.get("Range") if allow_range else None
        if etag and not range_header and self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            if cache_control:
                self.send_header("Cache-Control", cache_control)
            self.end_headers()
            return
        if range_header:
            start, end = _parse_range(range_header, total)
            status = HTTPStatus.PARTIAL_CONTENT
        length = max(0, end - start + 1)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if etag:
            self.send_header("ETag", etag)
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.end_headers()
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = length
            while remaining:
                chunk = stream.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return
                remaining -= len(chunk)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def _parse_range(value: str, total: int) -> tuple[int, int]:
    if not value.startswith("bytes=") or "," in value or total <= 0:
        raise PodcastEditorError("invalid_range", "Range 请求无效。", status=416)
    start_text, separator, end_text = value[6:].partition("-")
    if not separator:
        raise PodcastEditorError("invalid_range", "Range 请求无效。", status=416)
    try:
        if not start_text:
            suffix = int(end_text)
            if suffix <= 0:
                raise ValueError
            start, end = max(0, total - suffix), total - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else total - 1
    except ValueError as exc:
        raise PodcastEditorError("invalid_range", "Range 请求无效。", status=416) from exc
    if start < 0 or end < start or start >= total:
        raise PodcastEditorError("invalid_range", "Range 超出文件范围。", status=416)
    return start, min(end, total - 1)


def create_server(
    store: ProjectStore,
    *,
    port: int = 0,
    draft_root: str | Path | None = None,
    static_root: str | Path | None = None,
) -> ThreadingHTTPServer:
    skill_root = Path(__file__).resolve().parents[2]
    assets = Path(static_root).resolve() if static_root else skill_root / "assets"
    server = ThreadingHTTPServer(("127.0.0.1", port), ReviewRequestHandler)
    server.service = PodcastService(store, draft_root=draft_root)  # type: ignore[attr-defined]
    server.static_root = assets  # type: ignore[attr-defined]
    return server
