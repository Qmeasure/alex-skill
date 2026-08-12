import io
import json
import threading
import time
import unittest
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def silent_wav(duration_seconds=2, sample_rate=8_000):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * duration_seconds * sample_rate)
    return output.getvalue()


WORD_RANGES = {
    "word-1": (0, 200),
    "word-2": (220, 500),
    "word-3": (1_000, 1_400),
}
WORD_ORDER = ["word-1", "word-2", "word-3"]


def deletion_ranges(selected_word_ids):
    groups = []
    current = []
    for word_id in WORD_ORDER:
        if word_id in selected_word_ids:
            current.append(word_id)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def cut_plan_for_selection(selected_word_ids, revision, cut_overrides=None, needs_review=False, can_cut=True):
    cut_overrides = cut_overrides or {}
    deletions = []
    ranges = []
    for group in deletion_ranges(selected_word_ids):
        raw_start = WORD_RANGES[group[0]][0]
        raw_end = WORD_RANGES[group[-1]][1]
        deletion_id = f"delete-{group[0]}-{group[-1]}"
        override = cut_overrides.get(deletion_id, {})
        start = int(override.get("startMs", raw_start))
        end = int(override.get("endMs", raw_end))
        if can_cut:
            ranges.append((start, end))
        deletions.append(
            {
                "id": deletion_id,
                "firstWordId": group[0],
                "lastWordId": group[-1],
                "rawStartMs": raw_start,
                "rawEndMs": raw_end,
                "startMs": start,
                "endMs": end,
                "minStartMs": max(0, raw_start - 120),
                "maxEndMs": min(2_000, raw_end + 120),
                "boundaryMode": "manual" if deletion_id in cut_overrides else "automatic",
                "scope": "global",
                "speakerId": None,
                "needsReview": bool(needs_review),
                "boundaryWarning": (
                    "当前选词无法安全剪切，请扩大或调整选词"
                    if not can_cut
                    else ("未找到稳定静音，请人工复核" if needs_review else None)
                ),
                "canCut": bool(can_cut),
            }
        )
    merged = []
    for start, end in ranges:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    kept = []
    cursor = 0
    target = 0
    for start, end in merged:
        if start > cursor:
            kept.append(
                {
                    "sourceStartMs": cursor,
                    "sourceEndMs": start,
                    "targetStartMs": target,
                    "targetEndMs": target + start - cursor,
                }
            )
            target += start - cursor
        cursor = end
    if cursor < 2_000:
        kept.append(
            {
                "sourceStartMs": cursor,
                "sourceEndMs": 2_000,
                "targetStartMs": target,
                "targetEndMs": target + 2_000 - cursor,
            }
        )
        target += 2_000 - cursor
    timeline = {"revision": revision, "durationMs": target, "segments": kept}
    selected = "-".join(sorted(selected_word_ids)) or "none"
    override_key = "-manual" if cut_overrides else ""
    return {
        "revision": revision,
        "planId": f"plan-{revision}-{selected}{override_key}",
        "deletions": deletions,
        "timeline": timeline,
        "globalDeletions": [{"startMs": start, "endMs": end} for start, end in ranges],
        "speakerDeletions": {},
        "tracks": [
            {
                "sourceId": "source-mix",
                "speakerId": None,
                "name": "合成音轨",
                "segments": list(kept),
            }
        ],
    }


def timeline_for_selection(selected_word_ids, revision, cut_overrides=None):
    return cut_plan_for_selection(selected_word_ids, revision, cut_overrides)["timeline"]


def playback_runs(plan, sources):
    runs = []
    for index, segment in enumerate(plan["timeline"]["segments"]):
        runs.append(
            {
                "id": f"{plan['planId']}-run-{index}",
                **segment,
                "sources": [
                    {
                        "sourceId": source["sourceId"],
                        "streamUrl": source["url"],
                        "sourceStartMs": segment["sourceStartMs"],
                        "sourceEndMs": segment["sourceEndMs"],
                    }
                    for source in sources
                ],
            }
        )
    return runs


def playback_payload(plan, sources):
    return {
        "strategy": "dual-audio-preload-v1",
        "revision": plan["revision"],
        "planId": plan["planId"],
        "timeline": plan["timeline"],
        "cutPlan": plan,
        "sources": sources,
        "runs": playback_runs(plan, sources),
        "tracks": plan["tracks"],
    }


def multitrack_cut_plan(selected_word_ids, revision):
    full_timeline = {
        "revision": revision,
        "durationMs": 2_000,
        "segments": [
            {
                "sourceStartMs": 0,
                "sourceEndMs": 2_000,
                "targetStartMs": 0,
                "targetEndMs": 2_000,
            }
        ],
    }
    speaker_one_ranges = [WORD_RANGES[word_id] for word_id in ("word-1", "word-2") if word_id in selected_word_ids]
    speaker_two_ranges = [WORD_RANGES["word-3"]] if "word-3" in selected_word_ids else []

    def track_segments(deletions):
        segments = []
        cursor = 0
        for start, end in deletions:
            if cursor < start:
                segments.append(
                    {
                        "sourceStartMs": cursor,
                        "sourceEndMs": start,
                        "targetStartMs": cursor,
                        "targetEndMs": start,
                    }
                )
            cursor = end
        if cursor < 2_000:
            segments.append(
                {
                    "sourceStartMs": cursor,
                    "sourceEndMs": 2_000,
                    "targetStartMs": cursor,
                    "targetEndMs": 2_000,
                }
            )
        return segments

    speaker_deletions = {}
    if speaker_one_ranges:
        speaker_deletions["speaker-1"] = [
            {"startMs": start, "endMs": end} for start, end in speaker_one_ranges
        ]
    if speaker_two_ranges:
        speaker_deletions["speaker-2"] = [
            {"startMs": start, "endMs": end} for start, end in speaker_two_ranges
        ]
    deletions = []
    for word_id in WORD_ORDER:
        if word_id not in selected_word_ids:
            continue
        start, end = WORD_RANGES[word_id]
        speaker_id = "speaker-2" if word_id == "word-3" else "speaker-1"
        deletions.append(
            {
                "id": f"delete-{word_id}-{word_id}",
                "firstWordId": word_id,
                "lastWordId": word_id,
                "rawStartMs": start,
                "rawEndMs": end,
                "startMs": start,
                "endMs": end,
                "minStartMs": max(0, start - 120),
                "maxEndMs": min(2_000, end + 120),
                "boundaryMode": "automatic",
                "scope": "speaker",
                "speakerId": speaker_id,
                "needsReview": False,
                "boundaryWarning": None,
                "canCut": True,
            }
        )
    selected = "-".join(sorted(selected_word_ids)) or "none"
    return {
        "revision": revision,
        "planId": f"plan-{revision}-{selected}-multitrack",
        "deletions": deletions,
        "timeline": full_timeline,
        "globalDeletions": [],
        "speakerDeletions": speaker_deletions,
        "tracks": [
            {
                "sourceId": "source-1",
                "speakerId": "speaker-1",
                "name": "嘉宾一",
                "segments": track_segments(speaker_one_ranges),
            },
            {
                "sourceId": "source-2",
                "speakerId": "speaker-2",
                "name": "嘉宾二",
                "segments": track_segments(speaker_two_ranges),
            },
        ],
    }


def multitrack_global_cut_plan(selected_word_ids, revision):
    plan = cut_plan_for_selection(selected_word_ids, revision)
    plan["planId"] += "-multitrack-global"
    plan["tracks"] = [
        {
            "sourceId": source_id,
            "speakerId": speaker_id,
            "name": name,
            "segments": list(plan["timeline"]["segments"]),
        }
        for source_id, speaker_id, name in (
            ("source-1", "speaker-1", "嘉宾一"),
            ("source-2", "speaker-2", "嘉宾二"),
        )
    ]
    return plan


def map_source_time(timeline, source_ms):
    for segment in timeline["segments"]:
        if source_ms < segment["sourceStartMs"]:
            return segment["targetStartMs"]
        if source_ms <= segment["sourceEndMs"]:
            return segment["targetStartMs"] + source_ms - segment["sourceStartMs"]
    return timeline["durationMs"]


def review_turns(utterances):
    turns = []
    for utterance in utterances:
        if turns and turns[-1]["speakerId"] == utterance["speakerId"]:
            turns[-1]["endMs"] = utterance["endMs"]
            turns[-1]["utteranceIds"].append(utterance["id"])
            continue
        turns.append(
            {
                "id": f"turn-{len(turns) + 1}",
                "speakerId": utterance["speakerId"],
                "startMs": utterance["startMs"],
                "endMs": utterance["endMs"],
                "utteranceIds": [utterance["id"]],
            }
        )
    return turns


class ReviewMockHandler(BaseHTTPRequestHandler):
    revision = 4
    saved_requests = []
    post_requests = []
    get_requests = []
    slow_operation = None
    active_operation = None
    cancel_event = threading.Event()
    selected_word_ids = set()
    speaker_overrides = {}
    cut_overrides = {}
    save_gate = None
    needs_review = False
    can_cut = True
    multitrack = False
    multitrack_global = False
    playback_mutation = None
    wav_bytes = silent_wav()

    project_payload = {
        "project": {
            "id": "browser-test",
            "name": "双人播客测试",
            "mode": "mixed",
            "durationMs": 2_000,
            "speakers": [
                {"id": "speaker-1", "name": "嘉宾一"},
                {"id": "speaker-2", "name": "嘉宾二"},
            ],
            "utterances": [
                {
                    "id": "utterance-1",
                    "speakerId": "speaker-1",
                    "startMs": 0,
                    "endMs": 900,
                    "words": [
                        {"id": "word-1", "text": "嗯", "startMs": 0, "endMs": 200, "selected": False},
                        {
                            "id": "word-2",
                            "text": "今天",
                            "startMs": 220,
                            "endMs": 500,
                            "punctuationAfter": "，",
                            "selected": False,
                        },
                    ],
                },
                {
                    "id": "utterance-2",
                    "speakerId": "speaker-2",
                    "startMs": 1_000,
                    "endMs": 1_900,
                    "words": [
                        {"id": "word-3", "text": "开始", "startMs": 1_000, "endMs": 1_400, "selected": False},
                    ],
                },
            ],
        },
        "state": {
            "revision": 4,
            "selectedWordIds": [],
            "speakerNames": {},
            "speakerOverrides": {},
            "cutOverrides": {},
        },
        "reviewTurns": [
            {
                "id": "turn-1",
                "speakerId": "speaker-1",
                "startMs": 0,
                "endMs": 900,
                "utteranceIds": ["utterance-1"],
            },
            {
                "id": "turn-2",
                "speakerId": "speaker-2",
                "startMs": 1_000,
                "endMs": 1_900,
                "utteranceIds": ["utterance-2"],
            },
        ],
        "playback": {
            "strategy": "dual-audio-preload-v1",
            "url": "/audio.wav",
            "sources": [
                {
                    "sourceId": "source-mix",
                    "speakerId": None,
                    "url": "/audio.wav?sourceId=source-mix",
                }
            ],
            "timeline": timeline_for_selection(set(), 4),
            "cutPlan": cut_plan_for_selection(set(), 4),
            "runs": playback_runs(
                cut_plan_for_selection(set(), 4),
                [{"sourceId": "source-mix", "speakerId": None, "url": "/audio.wav?sourceId=source-mix"}],
            ),
        },
    }

    def log_message(self, _format, *_args):
        return

    def send_bytes(self, content, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, payload, status=200):
        self.send_bytes(json.dumps(payload).encode("utf-8"), "application/json", status)

    def send_audio(self):
        content = self.wav_bytes
        range_header = self.headers.get("Range")
        if not range_header:
            self.send_response(200)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(content)
            return
        start_text, _, end_text = range_header.removeprefix("bytes=").partition("-")
        start = int(start_text or 0)
        end = min(int(end_text) if end_text else len(content) - 1, len(content) - 1)
        part = content[start : end + 1]
        self.send_response(206)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(part)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{len(content)}")
        self.end_headers()
        self.wfile.write(part)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        type(self).get_requests.append(self.path)
        if parsed.path == "/":
            self.send_bytes((ROOT / "assets" / "review.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/assets/review.css":
            self.send_bytes((ROOT / "assets" / "review.css").read_bytes(), "text/css; charset=utf-8")
        elif self.path == "/assets/review.js":
            self.send_bytes((ROOT / "assets" / "review.js").read_bytes(), "text/javascript; charset=utf-8")
        elif parsed.path == "/api/project":
            payload = json.loads(json.dumps(self.project_payload))
            if type(self).multitrack:
                payload["project"]["mode"] = "multitrack"
                payload["project"]["sources"] = [
                    {"id": "source-1", "speakerId": "speaker-1", "name": "嘉宾一"},
                    {"id": "source-2", "speakerId": "speaker-2", "name": "嘉宾二"},
                ]
                payload["playback"]["url"] = "/audio.wav?sourceId=source-1"
                payload["playback"]["sources"] = [
                    {
                        "sourceId": "source-1",
                        "speakerId": "speaker-1",
                        "url": "/audio.wav?sourceId=source-1",
                    },
                    {
                        "sourceId": "source-2",
                        "speakerId": "speaker-2",
                        "url": "/audio.wav?sourceId=source-2",
                    },
                ]
            payload["state"]["revision"] = type(self).revision
            payload["state"]["selectedWordIds"] = sorted(type(self).selected_word_ids)
            payload["state"]["speakerOverrides"] = dict(type(self).speaker_overrides)
            payload["state"]["cutOverrides"] = dict(type(self).cut_overrides)
            for utterance in payload["project"]["utterances"]:
                utterance["speakerId"] = type(self).speaker_overrides.get(
                    utterance["id"], utterance["speakerId"]
                )
            payload["reviewTurns"] = review_turns(payload["project"]["utterances"])
            if type(self).multitrack:
                cut_plan = (
                    multitrack_global_cut_plan(type(self).selected_word_ids, type(self).revision)
                    if type(self).multitrack_global
                    else multitrack_cut_plan(type(self).selected_word_ids, type(self).revision)
                )
            else:
                cut_plan = cut_plan_for_selection(
                    type(self).selected_word_ids,
                    type(self).revision,
                    type(self).cut_overrides,
                    type(self).needs_review,
                    type(self).can_cut,
                )
            payload["playback"]["cutPlan"] = cut_plan
            payload["playback"]["timeline"] = cut_plan["timeline"]
            payload["playback"].update(
                playback_payload(cut_plan, payload["playback"]["sources"])
            )
            mutation = type(self).playback_mutation
            if mutation == "revision":
                payload["playback"]["revision"] += 1
            elif mutation == "planId":
                payload["playback"]["planId"] = "plan-stale"
            elif mutation == "run":
                payload["playback"]["runs"][0]["targetEndMs"] += 1
            self.send_json(payload)
        elif parsed.path == "/api/waveform":
            query = parse_qs(parsed.query)
            start_ms = int(query["startMs"][0])
            end_ms = int(query["endMs"][0])
            point_count = int(query["points"][0])
            width = (end_ms - start_ms) / point_count
            self.send_json(
                {
                    "sourceId": "source-mix",
                    "startMs": start_ms,
                    "endMs": end_ms,
                    "points": [
                        {
                            "startMs": round(start_ms + index * width),
                            "endMs": round(start_ms + (index + 1) * width),
                            "peak": (index % 7) / 7,
                        }
                        for index in range(point_count)
                    ],
                }
            )
        elif parsed.path == "/audio.wav":
            self.send_audio()
        elif parsed.path == "/preview.wav":
            self.send_audio()
        else:
            self.send_json({"error": {"code": "NOT_FOUND", "message": "未找到"}}, 404)

    def do_PUT(self):
        if self.path != "/api/state":
            self.send_json({"error": {"code": "NOT_FOUND", "message": "未找到"}}, 404)
            return
        payload = self.read_json()
        if payload.get("revision") != type(self).revision:
            self.send_json({"error": {"code": "REVISION_CONFLICT", "message": "版本冲突"}}, 409)
            return
        gate = type(self).save_gate
        if gate is not None:
            gate.wait(timeout=2)
        type(self).revision += 1
        type(self).selected_word_ids = set(payload["selectedWordIds"])
        type(self).speaker_overrides = dict(payload.get("speakerOverrides", {}))
        type(self).cut_overrides = dict(payload.get("cutOverrides", {}))
        type(self).saved_requests.append(payload)
        project = json.loads(json.dumps(self.project_payload["project"]))
        for utterance in project["utterances"]:
            utterance["speakerId"] = type(self).speaker_overrides.get(
                utterance["id"], utterance["speakerId"]
            )
        cut_plan = (
            (
                multitrack_global_cut_plan(type(self).selected_word_ids, type(self).revision)
                if type(self).multitrack_global
                else multitrack_cut_plan(type(self).selected_word_ids, type(self).revision)
            )
            if type(self).multitrack
            else cut_plan_for_selection(
                type(self).selected_word_ids,
                type(self).revision,
                type(self).cut_overrides,
                type(self).needs_review,
                type(self).can_cut,
            )
        )
        sources = (
            [
                {"sourceId": "source-1", "speakerId": "speaker-1", "url": "/audio.wav?sourceId=source-1"},
                {"sourceId": "source-2", "speakerId": "speaker-2", "url": "/audio.wav?sourceId=source-2"},
            ]
            if type(self).multitrack
            else [{"sourceId": "source-mix", "speakerId": None, "url": "/audio.wav?sourceId=source-mix"}]
        )
        self.send_json(
            {
                "state": {
                    "revision": type(self).revision,
                    "selectedWordIds": payload["selectedWordIds"],
                    "speakerNames": payload["speakerNames"],
                    "speakerOverrides": dict(type(self).speaker_overrides),
                    "cutOverrides": dict(type(self).cut_overrides),
                },
                "project": project,
                "reviewTurns": review_turns(project["utterances"]),
                "savedAt": "2026-08-11T00:00:00Z",
                "cutPlan": cut_plan,
                "timeline": cut_plan["timeline"],
                "playback": playback_payload(cut_plan, sources),
            }
        )

    def do_POST(self):
        payload = self.read_json()
        type(self).post_requests.append({"path": self.path, "body": payload})
        if self.path == "/api/cancel":
            active = type(self).active_operation is not None
            if active:
                type(self).cancel_event.set()
            self.send_json(
                {
                    "cancellationRequested": active,
                    "status": {"phase": "cancelling" if active else "idle"},
                }
            )
            return

        current_plan = cut_plan_for_selection(
            type(self).selected_word_ids,
            type(self).revision,
            type(self).cut_overrides,
            type(self).needs_review,
            type(self).can_cut,
        )
        if self.path in {"/api/preview", "/api/export"} and (
            payload.get("revision") != type(self).revision
            or payload.get("planId") != current_plan["planId"]
        ):
            self.send_json(
                {"error": {"code": "REVISION_CONFLICT", "message": "内容版本已变化"}},
                409,
            )
            return

        if type(self).slow_operation == self.path:
            type(self).active_operation = self.path
            type(self).cancel_event.wait(timeout=2)
            type(self).active_operation = None
            if type(self).cancel_event.is_set():
                self.send_json(
                    {"error": {"code": "operation_cancelled", "message": "操作已取消"}},
                    409,
                )
                return

        if self.path == "/api/preview":
            timeline = current_plan["timeline"]
            preview_utterances = []
            for utterance in self.project_payload["project"]["utterances"]:
                words = []
                for word in utterance["words"]:
                    if word["id"] in type(self).selected_word_ids:
                        continue
                    words.append(
                        {
                            **word,
                            "startMs": map_source_time(timeline, word["startMs"]),
                            "endMs": map_source_time(timeline, word["endMs"]),
                        }
                    )
                if words:
                    preview_utterances.append(
                        {
                            "id": utterance["id"],
                            "speakerId": utterance["speakerId"],
                            "startMs": min(word["startMs"] for word in words),
                            "endMs": max(word["endMs"] for word in words),
                            "words": words,
                        }
                    )
            self.send_json(
                {
                    "url": "/preview.wav",
                    "revision": type(self).revision,
                    "planId": current_plan["planId"],
                    "utterances": preview_utterances,
                    "timeline": timeline,
                    "cutPlan": current_plan,
                }
            )
        elif self.path == "/api/export":
            time.sleep(0.25)
            self.send_json(
                {
                    "draftName": "双人播客测试_精剪",
                    "draftPath": "C:\\JianyingPro Drafts\\双人播客测试_精剪",
                    "revision": type(self).revision,
                }
            )
        else:
            self.send_json({"error": {"code": "NOT_FOUND", "message": "未找到"}}, 404)


class ReviewBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ReviewMockHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except PlaywrightError as bundled_error:
            if not CHROME_PATH.is_file():
                cls.playwright.stop()
                cls.server.shutdown()
                raise unittest.SkipTest(f"Chromium 不可用：{bundled_error}")
            try:
                cls.browser = cls.playwright.chromium.launch(
                    headless=True,
                    executable_path=str(CHROME_PATH),
                )
            except PlaywrightError as system_error:
                cls.playwright.stop()
                cls.server.shutdown()
                raise unittest.SkipTest(f"Chromium 不可用：{system_error}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "playwright"):
            cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        ReviewMockHandler.revision = 4
        ReviewMockHandler.saved_requests = []
        ReviewMockHandler.post_requests = []
        ReviewMockHandler.get_requests = []
        ReviewMockHandler.slow_operation = None
        ReviewMockHandler.active_operation = None
        ReviewMockHandler.cancel_event = threading.Event()
        ReviewMockHandler.selected_word_ids = set()
        ReviewMockHandler.speaker_overrides = {}
        ReviewMockHandler.cut_overrides = {}
        ReviewMockHandler.save_gate = None
        ReviewMockHandler.needs_review = False
        ReviewMockHandler.can_cut = True
        ReviewMockHandler.multitrack = False
        ReviewMockHandler.multitrack_global = False
        ReviewMockHandler.playback_mutation = None
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 900})
        self.page.goto(self.base_url)
        self.page.locator(".word").first.wait_for()

    def tearDown(self):
        self.page.close()

    def wait_for_save_count(self, count):
        for _ in range(40):
            if len(ReviewMockHandler.saved_requests) >= count:
                return
            self.page.wait_for_timeout(50)
        self.fail(f"等待第 {count} 次自动保存超时")

    def wait_for_waveform_count(self, count):
        for _ in range(40):
            requests = [path for path in ReviewMockHandler.get_requests if path.startswith("/api/waveform?")]
            if len(requests) >= count:
                return requests
            self.page.wait_for_timeout(50)
        self.fail(f"等待第 {count} 次波形请求超时")

    def test_complete_review_flow(self):
        page = self.page
        self.assertEqual(page.locator(".utterance").count(), 2)
        self.assertEqual(page.locator(".word").count(), 3)
        self.assertEqual(page.locator(".punctuation").count(), 1)

        first_word = page.locator('[data-word-id="word-1"]')
        first_word.click()
        self.assertTrue(first_word.evaluate("element => element.classList.contains('is-selected')"))
        self.assertIn("已划掉 1 字", page.locator("#selectionSummary").inner_text())
        self.wait_for_save_count(1)
        self.assertEqual(ReviewMockHandler.saved_requests[-1]["selectedWordIds"], ["word-1"])
        self.assertEqual(ReviewMockHandler.saved_requests[-1]["cutOverrides"], {})

        page.locator("#undoButton").click()
        self.assertFalse(first_word.evaluate("element => element.classList.contains('is-selected')"))
        self.wait_for_save_count(2)

        page.locator("#redoButton").click()
        self.assertTrue(first_word.evaluate("element => element.classList.contains('is-selected')"))
        self.wait_for_save_count(3)

        page.locator('[data-speaker-filter="speaker-2"]').click()
        self.assertFalse(page.locator('[data-utterance-id="utterance-1"]').is_visible())
        self.assertTrue(page.locator('[data-utterance-id="utterance-2"]').is_visible())
        page.locator('[data-speaker-filter="all"]').click()

        first_name = page.locator('[data-speaker-input="speaker-1"]')
        first_name.fill("小林")
        first_name.press("Tab")
        self.assertEqual(page.locator('[data-speaker-filter="speaker-1"]').inner_text(), "小林")
        self.assertEqual(
            page.locator('[data-turn-speaker="turn-1"] option[value="speaker-1"]').inner_text(),
            "小林",
        )
        page.locator("#audioPlayer").evaluate(
            "audio => { audio.currentTime = 0.1; audio.dispatchEvent(new Event('timeupdate')); }"
        )
        page.wait_for_function("document.querySelector('#audioPlayer').currentTime >= 0.08")
        page.locator("#audioPlayer").evaluate("audio => audio.dispatchEvent(new Event('timeupdate'))")
        self.assertEqual(page.locator("#nowSpeaker").inner_text(), "小林")
        self.wait_for_save_count(4)
        self.assertEqual(ReviewMockHandler.saved_requests[-1]["speakerNames"]["speaker-1"], "小林")

        page.locator("#exportButton").click()
        page.locator('#saveStatus[data-state="exporting"]').wait_for()
        page.locator("#exportResult").wait_for(state="visible")
        self.assertEqual(page.locator("#exportName").inner_text(), "双人播客测试_精剪")
        self.assertIn("JianyingPro Drafts", page.locator("#exportPath").inner_text())
        self.assertEqual(page.locator("#saveStatus").get_attribute("data-state"), "success")
        export_request = next(item for item in ReviewMockHandler.post_requests if item["path"] == "/api/export")
        self.assertEqual(
            export_request["body"],
            {
                "revision": ReviewMockHandler.revision,
                "planId": cut_plan_for_selection(
                    ReviewMockHandler.selected_word_ids,
                    ReviewMockHandler.revision,
                    ReviewMockHandler.cut_overrides,
                )["planId"],
            },
        )

    def test_mobile_layout_stays_inside_viewport(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.reload()
        self.page.locator(".word").first.wait_for()

        measurements = self.page.evaluate(
            """
            () => ({
              viewportWidth: window.innerWidth,
              documentWidth: document.documentElement.scrollWidth,
              controls: [
                '#previewButton',
                '#exportButton',
                '#playButton',
                '#undoButton',
                '#redoButton',
                '#waveformViewport',
                '#cutSelector',
                '#waveformZoomOut',
                '#waveformZoomIn',
                '#waveformResetView',
                '#cutResetButton',
                '[data-speaker-input="speaker-1"]',
                '[data-word-id="word-1"]'
              ].map(selector => {
                const element = document.querySelector(selector);
                const box = element.getBoundingClientRect();
                return {
                  selector,
                  left: box.left,
                  right: box.right,
                  clientWidth: element.clientWidth,
                  scrollWidth: element.scrollWidth
                };
              })
            })
            """
        )
        self.assertLessEqual(measurements["documentWidth"], measurements["viewportWidth"])
        for control in measurements["controls"]:
            self.assertGreaterEqual(control["left"], 0, control["selector"])
            self.assertLessEqual(control["right"], measurements["viewportWidth"], control["selector"])
            self.assertLessEqual(control["scrollWidth"], control["clientWidth"], control["selector"])

    def test_preview_caption_uses_remapped_timeline_and_edit_returns_to_live_cut(self):
        page = self.page
        original_word_count = page.locator(".word").count()

        page.locator('[data-word-id="word-1"]').click()
        self.wait_for_save_count(1)
        page.locator("#previewButton").click()
        page.locator("#saveStatus").filter(has_text="试听已更新").wait_for()

        self.assertTrue(page.locator("#audioPlayer").get_attribute("src").endswith("/preview.wav"))
        self.assertEqual(page.locator("#audioPlayer").get_attribute("data-timeline"), "preview")
        page.wait_for_function(
            """
            () => {
              const audio = document.querySelector('#audioPlayer');
              return audio.currentSrc.endsWith('/preview.wav') && audio.readyState >= 1;
            }
            """
        )
        page.locator("#audioPlayer").evaluate(
            "audio => { audio.currentTime = 0.1; audio.dispatchEvent(new Event('timeupdate')); }"
        )
        self.assertEqual(page.locator("#nowSpeaker").inner_text(), "嘉宾一")
        self.assertEqual(page.locator("#nowCaption").inner_text(), "今天，")
        self.assertEqual(page.locator(".word").count(), original_word_count)
        self.assertEqual(page.locator('[data-word-id="word-3"]').inner_text(), "开始")

        page.locator('[data-word-id="word-2"]').click()
        page.wait_for_function(
            "document.querySelector('#audioPlayer').getAttribute('src').includes('/audio.wav')"
        )
        self.wait_for_save_count(2)
        page.wait_for_function(
            "document.querySelector('#audioPlayer').dataset.timeline === 'live'"
        )
        self.assertIn("/audio.wav", page.locator("#audioPlayer").get_attribute("src"))
        self.assertEqual(page.locator("#audioPlayer").get_attribute("data-timeline"), "live")
        self.assertGreater(page.locator("#audioPlayer").evaluate("audio => audio.currentTime"), 0.45)
        self.assertEqual(page.locator("#nowSpeaker").inner_text(), "嘉宾一")
        self.assertEqual(page.locator("#nowCaption").inner_text(), "")
        self.assertEqual(page.locator(".word").count(), original_word_count)

    def test_live_playback_skips_a_word_deleted_while_playing(self):
        page = self.page
        page.locator("#audioPlayer").evaluate(
            "audio => { audio.currentTime = 0.25; audio.dispatchEvent(new Event('timeupdate')); }"
        )
        page.locator("#playButton").click()
        page.wait_for_function("!document.querySelector('#audioPlayer').paused")

        page.locator('[data-word-id="word-2"]').click()
        self.wait_for_save_count(1)
        page.wait_for_function("document.querySelector('#audioPlayer').currentTime >= 0.5")
        page.wait_for_function("document.querySelector('#playButton').ariaLabel === '暂停'")
        self.assertEqual(page.locator("#playButton").get_attribute("aria-label"), "暂停")
        self.assertEqual(page.locator("#audioPlayer").get_attribute("data-timeline"), "live")
        self.assertNotIn("今天", page.locator("#nowCaption").inner_text())

    def test_consecutive_selected_words_with_a_timestamp_gap_share_one_deletion(self):
        ReviewMockHandler.selected_word_ids = {"word-1", "word-2"}
        self.page.reload()
        self.page.locator(".word").first.wait_for()
        self.page.wait_for_function("!document.querySelector('#cutSelector').disabled")

        options = self.page.locator("#cutSelector option")
        self.assertEqual(options.count(), 1)
        self.assertEqual(options.first.get_attribute("value"), "delete-word-1-word-2")
        self.assertEqual(
            self.page.locator("#audioPlayer").get_attribute("data-plan-id"),
            cut_plan_for_selection({"word-1", "word-2"}, 4)["planId"],
        )
        plan = cut_plan_for_selection({"word-1", "word-2"}, 4)
        self.assertEqual(
            [(item["startMs"], item["endMs"]) for item in plan["deletions"]],
            [(0, 500)],
        )
        self.assertFalse(
            any(
                segment["sourceStartMs"] < 220 < segment["sourceEndMs"]
                for segment in plan["timeline"]["segments"]
            )
        )

    def test_edit_mutes_until_current_cut_plan_arrives_and_restores_logical_time(self):
        page = self.page
        initial_plan_id = page.locator("#audioPlayer").get_attribute("data-plan-id")
        gate = threading.Event()
        ReviewMockHandler.save_gate = gate
        page.locator("#audioPlayer").evaluate(
            "audio => { audio.currentTime = 1.2; audio.dispatchEvent(new Event('timeupdate')); }"
        )

        page.locator('[data-word-id="word-1"]').click()
        page.wait_for_function(
            "document.querySelector('#audioPlayer').dataset.cutPending === 'true'"
        )
        self.assertEqual(page.locator("#audioPlayer").get_attribute("data-plan-id"), initial_plan_id)

        page.locator('[data-word-id="word-2"]').click()
        self.assertEqual(page.locator("#audioPlayer").get_attribute("data-plan-id"), initial_plan_id)
        gate.set()
        self.wait_for_save_count(2)
        expected = cut_plan_for_selection({"word-1", "word-2"}, 6)
        page.wait_for_function(
            "expected => document.querySelector('#audioPlayer').dataset.planId === expected",
            arg=expected["planId"],
        )
        page.wait_for_function(
            "Math.abs(document.querySelector('#audioPlayer').currentTime - 1.7) < 0.08"
        )
        self.assertEqual(page.locator("#audioPlayer").get_attribute("data-cut-pending"), "false")
        self.assertAlmostEqual(
            page.locator("#audioPlayer").evaluate("audio => audio.currentTime"),
            1.7,
            delta=0.08,
        )

    def test_waveform_zoom_pan_manual_handles_and_reset(self):
        ReviewMockHandler.selected_word_ids = {"word-2"}
        self.page.reload()
        self.page.locator(".word").first.wait_for()
        self.page.wait_for_function("!document.querySelector('#cutSelector').disabled")
        requests = self.wait_for_waveform_count(1)
        initial_query = parse_qs(urlparse(requests[-1]).query)
        initial_span = int(initial_query["endMs"][0]) - int(initial_query["startMs"][0])

        self.page.locator("#waveformZoomIn").click()
        requests = self.wait_for_waveform_count(2)
        zoom_query = parse_qs(urlparse(requests[-1]).query)
        zoom_span = int(zoom_query["endMs"][0]) - int(zoom_query["startMs"][0])
        self.assertLess(zoom_span, initial_span)

        viewport = self.page.locator("#waveformViewport")
        box = viewport.bounding_box()
        self.page.mouse.move(box["x"] + box["width"] * 0.7, box["y"] + box["height"] * 0.5)
        self.page.mouse.down()
        self.page.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.5)
        self.page.mouse.up()
        requests = self.wait_for_waveform_count(3)
        pan_query = parse_qs(urlparse(requests[-1]).query)
        self.assertNotEqual(pan_query["startMs"], zoom_query["startMs"])

        end_handle = self.page.locator("#cutEndHandle")
        handle_box = end_handle.bounding_box()
        self.page.mouse.move(handle_box["x"] + handle_box["width"] / 2, handle_box["y"] + 4)
        self.page.mouse.down()
        self.page.mouse.move(handle_box["x"] + handle_box["width"] / 2 + 45, handle_box["y"] + 4)
        self.page.mouse.up()
        self.wait_for_save_count(1)
        override = ReviewMockHandler.saved_requests[-1]["cutOverrides"]["delete-word-2-word-2"]
        self.assertEqual(override["startMs"], 220)
        self.assertGreater(override["endMs"], 500)
        self.assertFalse(self.page.locator("#cutResetButton").is_disabled())

        self.page.locator("#cutResetButton").click()
        self.wait_for_save_count(2)
        self.assertEqual(ReviewMockHandler.saved_requests[-1]["cutOverrides"], {})

    def test_boundary_warning_is_visible_for_a_cut_needing_review(self):
        ReviewMockHandler.selected_word_ids = {"word-2"}
        ReviewMockHandler.needs_review = True
        self.page.reload()
        self.page.locator("#boundaryWarning").wait_for(state="visible")
        self.assertIn("人工复核", self.page.locator("#boundaryWarning").inner_text())

    def test_uncuttable_selection_stays_in_caption_and_blocks_output(self):
        ReviewMockHandler.selected_word_ids = {"word-2"}
        ReviewMockHandler.can_cut = False
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('#boundaryWarning').textContent.includes('扩大或调整选词')"
        )

        self.assertIn("扩大或调整选词", self.page.locator("#boundaryWarning").inner_text())
        self.assertTrue(self.page.locator("#cutStartHandle").is_disabled())
        self.assertTrue(self.page.locator("#cutEndHandle").is_disabled())
        self.assertTrue(self.page.locator("#cutResetButton").is_disabled())
        self.assertTrue(self.page.locator("#previewButton").is_disabled())
        self.assertTrue(self.page.locator("#exportButton").is_disabled())
        self.assertIn("扩大或调整选词", self.page.locator("#previewButton").get_attribute("title"))

        self.page.locator("#audioPlayer").evaluate(
            "audio => { audio.currentTime = 0.3; audio.dispatchEvent(new Event('timeupdate')); }"
        )
        self.assertIn("今天", self.page.locator("#nowCaption").inner_text())

    def test_selection_changes_clear_cut_overrides_including_undo_and_redo(self):
        ReviewMockHandler.selected_word_ids = {"word-2"}
        ReviewMockHandler.cut_overrides = {
            "delete-word-2-word-2": {"startMs": 220, "endMs": 560}
        }
        self.page.reload()
        self.page.locator("#cutResetButton").wait_for(state="visible")

        self.page.locator('[data-word-id="word-1"]').click()
        self.wait_for_save_count(1)
        self.assertEqual(ReviewMockHandler.saved_requests[-1]["cutOverrides"], {})

        self.page.locator("#undoButton").click()
        self.wait_for_save_count(2)
        self.assertEqual(ReviewMockHandler.saved_requests[-1]["cutOverrides"], {})

        self.page.locator("#redoButton").click()
        self.wait_for_save_count(3)
        self.assertEqual(ReviewMockHandler.saved_requests[-1]["cutOverrides"], {})

    def test_multitrack_live_playback_mutes_only_the_deleted_speaker(self):
        ReviewMockHandler.multitrack = True
        ReviewMockHandler.selected_word_ids = {"word-1"}
        self.page.reload()
        first = self.page.locator('[data-deck-id="a"] audio[data-source-id="source-1"]')
        second = self.page.locator('[data-deck-id="a"] audio[data-source-id="source-2"]')
        second.wait_for(state="attached")
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"]').dataset.deckState === 'ready'"
        )

        self.assertEqual(first.get_attribute("data-audible"), "false")
        self.assertEqual(second.get_attribute("data-audible"), "true")

        first.evaluate(
            "audio => { audio.currentTime = 0.3; audio.dispatchEvent(new Event('timeupdate')); }"
        )
        self.page.locator("#playButton").click()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"] audio[data-source-id=\"source-1\"]').dataset.audible === 'true'"
        )
        self.assertEqual(first.get_attribute("data-audible"), "true")
        self.assertEqual(second.get_attribute("data-audible"), "true")

    def test_multitrack_handoff_waits_for_every_source_to_reach_run_start(self):
        ReviewMockHandler.multitrack = True
        ReviewMockHandler.multitrack_global = True
        ReviewMockHandler.selected_word_ids = {"word-2"}
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'ready'"
        )
        self.page.locator("#playButton").click()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"]').dataset.deckState === 'playing'"
        )
        active_players = self.page.locator('[data-deck-id="a"] audio')
        standby_players = self.page.locator('[data-deck-id="b"] audio')
        active_players.evaluate_all(
            "players => players.forEach(audio => { audio.pause(); audio.currentTime = 0.12; })"
        )
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'playing'"
        )
        active_players.evaluate_all(
            "players => players.forEach(audio => { audio.pause(); audio.currentTime = 0.22; })"
        )
        standby_players.nth(0).evaluate("audio => { audio.pause(); audio.currentTime = 0.5; }")
        standby_players.nth(1).evaluate("audio => { audio.pause(); audio.currentTime = 0.485; }")
        self.page.wait_for_function(
            """
            document.querySelector('[data-deck-id="a"]').dataset.outputGain === '0'
            && document.querySelector('[data-deck-id="b"]').dataset.outputGain === '0'
            """
        )
        standby_players.nth(1).evaluate("audio => { audio.currentTime = 0.5; }")
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.outputGain === '1'"
        )
        self.assertTrue(
            all(abs(value - 0.22) <= 0.01 for value in active_players.evaluate_all("players => players.map(a => a.currentTime)"))
        )

    def test_multitrack_handoff_rejects_any_source_over_twenty_ms(self):
        ReviewMockHandler.multitrack = True
        ReviewMockHandler.multitrack_global = True
        ReviewMockHandler.selected_word_ids = {"word-2"}
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'ready'"
        )
        self.page.locator("#playButton").click()
        active_players = self.page.locator('[data-deck-id="a"] audio')
        standby_players = self.page.locator('[data-deck-id="b"] audio')
        active_players.evaluate_all(
            "players => players.forEach(audio => { audio.pause(); audio.currentTime = 0.12; })"
        )
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'playing'"
        )
        active_players.evaluate_all(
            "players => players.forEach(audio => { audio.pause(); audio.currentTime = 0.22; })"
        )
        standby_players.nth(0).evaluate("audio => { audio.pause(); audio.currentTime = 0.5; }")
        standby_players.nth(1).evaluate("audio => { audio.pause(); audio.currentTime = 0.525; }")
        self.page.locator('#saveStatus[data-state="error"]').wait_for()
        self.assertIn("20ms", self.page.locator("#saveStatusText").inner_text())
        self.assertEqual(
            self.page.locator('[data-deck-id="b"]').get_attribute("data-output-gain"),
            "0",
        )

    def test_multitrack_running_source_drift_is_muted_and_resynchronized(self):
        ReviewMockHandler.multitrack = True
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"]').dataset.deckState === 'ready'"
        )
        self.page.locator("#playButton").click()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"]').dataset.deckState === 'playing'"
        )
        master = self.page.locator('[data-deck-id="a"] audio[data-source-id="source-1"]')
        secondary = self.page.locator('[data-deck-id="a"] audio[data-source-id="source-2"]')
        master.evaluate("audio => { audio.pause(); audio.currentTime = 0.5; }")
        secondary.evaluate("audio => { audio.pause(); audio.currentTime = 0.1; }")
        self.page.wait_for_function(
            "Number(document.querySelector('[data-deck-id=\"a\"] audio[data-source-id=\"source-2\"]').dataset.resyncCount) >= 1"
        )
        self.page.wait_for_function(
            """
            Math.abs(
              document.querySelector('[data-deck-id="a"] audio[data-source-id="source-1"]').currentTime
              - document.querySelector('[data-deck-id="a"] audio[data-source-id="source-2"]').currentTime
            ) <= 0.02
            """
        )

    def test_live_playback_continues_across_an_existing_deleted_range(self):
        ReviewMockHandler.selected_word_ids = {"word-2"}
        self.page.reload()
        self.page.locator(".word").first.wait_for()
        self.page.locator("#audioPlayer").evaluate(
            "audio => { audio.currentTime = 0.1; audio.dispatchEvent(new Event('timeupdate')); }"
        )
        self.page.locator("#playButton").click()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"] audio').currentTime >= 0.52"
        )
        self.assertGreaterEqual(
            self.page.locator('[data-deck-id="b"] audio').first.evaluate("audio => audio.currentTime"),
            0.52,
        )
        self.assertLess(
            self.page.locator("#audioPlayer").evaluate("audio => audio.currentTime"),
            0.3,
        )
        self.assertNotIn("今天", self.page.locator("#nowCaption").inner_text())

    def test_standby_deck_is_ready_at_dynamic_preroll_before_playback(self):
        ReviewMockHandler.selected_word_ids = {"word-2"}
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'ready'"
        )
        standby = self.page.locator('[data-deck-id="b"] audio').first
        self.assertAlmostEqual(standby.evaluate("audio => audio.currentTime"), 0.4, delta=0.03)
        self.assertTrue(standby.evaluate("audio => audio.paused"))

    def test_late_preroll_keeps_both_decks_silent_until_standby_reaches_run_start(self):
        ReviewMockHandler.selected_word_ids = {"word-2"}
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'ready'"
        )
        self.page.locator("#playButton").click()
        active = self.page.locator('[data-deck-id="a"] audio').first
        standby = self.page.locator('[data-deck-id="b"] audio').first
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"]').dataset.deckState === 'playing'"
        )
        active.evaluate("audio => { audio.pause(); audio.currentTime = 0.12; }")
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'playing'"
        )
        active.evaluate("audio => { audio.pause(); audio.currentTime = 0.22; }")
        standby.evaluate("audio => { audio.pause(); audio.currentTime = 0.485; }")
        self.page.wait_for_function(
            """
            document.querySelector('[data-deck-id="a"]').dataset.outputGain === '0'
            && document.querySelector('[data-deck-id="b"]').dataset.outputGain === '0'
            """
        )
        self.assertAlmostEqual(active.evaluate("audio => audio.currentTime"), 0.22, delta=0.01)

        standby.evaluate("audio => { audio.currentTime = 0.5; }")
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.outputGain === '1'"
        )
        self.assertLessEqual(
            float(self.page.locator('[data-deck-id="b"]').get_attribute("data-overshoot-ms")),
            20,
        )
        self.assertAlmostEqual(active.evaluate("audio => audio.currentTime"), 0.22, delta=0.01)

    def test_stalled_playing_deck_enters_error_and_stays_paused(self):
        self.page.locator("#playButton").click()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"]').dataset.deckState === 'playing'"
        )
        self.page.locator("#audioPlayer").evaluate(
            "audio => audio.dispatchEvent(new Event('stalled'))"
        )
        self.page.locator('#saveStatus[data-state="error"]').wait_for()
        self.assertIn("停滞", self.page.locator("#saveStatusText").inner_text())
        self.assertTrue(self.page.locator("#audioPlayer").evaluate("audio => audio.paused"))
        self.assertEqual(
            self.page.locator('[data-deck-id="a"]').get_attribute("data-deck-state"),
            "error",
        )

    def test_starting_deck_reuses_one_delayed_play_promise_across_frames(self):
        ReviewMockHandler.selected_word_ids = {"word-2"}
        self.page.add_init_script(
            """
            (() => {
              const nativePlay = HTMLMediaElement.prototype.play;
              window.__deckPlayCalls = {};
              HTMLMediaElement.prototype.play = function () {
                const key = this.dataset.deckAudio || 'unknown';
                window.__deckPlayCalls[key] = (window.__deckPlayCalls[key] || 0) + 1;
                return new Promise((resolve, reject) => {
                  setTimeout(() => nativePlay.call(this).then(resolve, reject), 120);
                });
              };
            })();
            """
        )
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'ready'"
        )
        self.page.locator("#playButton").click()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"]').dataset.deckState === 'playing'"
        )
        self.page.locator("#audioPlayer").evaluate(
            "audio => { audio.pause(); audio.currentTime = 0.12; }"
        )
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'starting'"
        )
        self.page.wait_for_timeout(60)
        self.assertEqual(self.page.evaluate("window.__deckPlayCalls.b"), 1)

    def test_rejected_standby_play_fails_closed(self):
        ReviewMockHandler.selected_word_ids = {"word-2"}
        self.page.add_init_script(
            """
            (() => {
              const nativePlay = HTMLMediaElement.prototype.play;
              HTMLMediaElement.prototype.play = function () {
                return this.dataset.deckAudio === 'b'
                  ? Promise.reject(new Error('play rejected'))
                  : nativePlay.call(this);
              };
            })();
            """
        )
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"b\"]').dataset.deckState === 'ready'"
        )
        self.page.locator("#playButton").click()
        self.page.locator("#audioPlayer").evaluate("audio => { audio.currentTime = 0.12; }")
        self.page.locator('#saveStatus[data-state="error"]').wait_for()
        self.assertEqual(
            self.page.locator('[data-deck-id="b"]').get_attribute("data-output-gain"),
            "0",
        )
        self.assertTrue(self.page.locator('[data-deck-id="b"] audio').first.evaluate("audio => audio.paused"))

    def test_delayed_play_from_old_generation_cannot_revive_deck(self):
        self.page.add_init_script(
            """
            (() => {
              const nativePlay = HTMLMediaElement.prototype.play;
              HTMLMediaElement.prototype.play = function () {
                return new Promise((resolve, reject) => {
                  setTimeout(() => nativePlay.call(this).then(resolve, reject), 250);
                });
              };
            })();
            """
        )
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"]').dataset.deckState === 'ready'"
        )
        old_run_id = self.page.locator('[data-deck-id="a"]').get_attribute("data-run-id")
        old_generation = int(self.page.locator('[data-deck-id="a"]').get_attribute("data-generation"))
        self.page.locator("#playButton").click()
        self.page.wait_for_function(
            "document.querySelector('[data-deck-id=\"a\"]').dataset.deckState === 'starting'"
        )
        self.page.locator('[data-word-id="word-2"]').click()
        self.wait_for_save_count(1)
        self.page.wait_for_function(
            "oldRunId => document.querySelector('[data-deck-id=\"a\"]').dataset.runId !== oldRunId",
            arg=old_run_id,
        )
        self.assertGreater(
            int(self.page.locator('[data-deck-id="a"]').get_attribute("data-generation")),
            old_generation,
        )
        self.assertNotEqual(
            self.page.locator('[data-deck-id="a"]').get_attribute("data-run-id"),
            old_run_id,
        )

    def test_live_playback_without_audio_context_fails_closed_but_preview_works(self):
        self.page.add_init_script(
            """
            Object.defineProperty(window, 'AudioContext', {value: undefined, configurable: true});
            Object.defineProperty(window, 'webkitAudioContext', {value: undefined, configurable: true});
            """
        )
        self.page.reload()
        self.page.locator(".word").first.wait_for()
        self.page.locator("#playButton").click()
        self.page.locator('#saveStatus[data-state="error"]').wait_for()
        self.assertIn("生成精确试听", self.page.locator("#saveStatusText").inner_text())
        self.assertTrue(self.page.locator("#audioPlayer").evaluate("audio => audio.paused"))

        self.page.locator("#previewButton").click()
        self.page.locator("#saveStatus").filter(has_text="试听已更新").wait_for()
        self.assertEqual(self.page.locator("#audioPlayer").get_attribute("data-timeline"), "preview")

    def test_malformed_playback_contract_is_rejected(self):
        for mutation in ("revision", "planId", "run"):
            with self.subTest(mutation=mutation):
                ReviewMockHandler.playback_mutation = mutation
                self.page.reload()
                self.page.wait_for_function(
                    "document.querySelector('#projectTitle').textContent === '项目无法打开'"
                )
                self.assertIn("格式", self.page.locator("#saveStatusText").inner_text())
        ReviewMockHandler.playback_mutation = None

    def test_turn_speaker_override_is_saved_and_merges_adjacent_turns(self):
        selector = self.page.locator('[data-turn-speaker="turn-1"]')
        selector.select_option("speaker-2")
        self.wait_for_save_count(1)
        self.assertEqual(
            ReviewMockHandler.saved_requests[-1]["speakerOverrides"],
            {"utterance-1": "speaker-2"},
        )
        self.page.wait_for_function("document.querySelectorAll('.utterance').length === 1")
        self.assertEqual(self.page.locator(".utterance").get_attribute("data-speaker-id"), "speaker-2")

    def test_preview_and_export_reject_stale_revision(self):
        page = self.page
        ReviewMockHandler.revision = 5

        page.locator("#previewButton").click()
        page.locator('#saveStatus[data-state="error"]').wait_for()
        self.assertIn("版本", page.locator("#saveStatusText").inner_text())
        preview_request = next(item for item in ReviewMockHandler.post_requests if item["path"] == "/api/preview")
        self.assertEqual(
            preview_request["body"],
            {"revision": 4, "planId": cut_plan_for_selection(set(), 4)["planId"]},
        )
        self.assertIn("/audio.wav", page.locator("#audioPlayer").get_attribute("src"))

        ReviewMockHandler.post_requests = []
        page.reload()
        page.locator(".word").first.wait_for()
        ReviewMockHandler.revision = 6
        page.locator("#exportButton").click()
        page.locator('#saveStatus[data-state="error"]').wait_for()
        self.assertIn("版本", page.locator("#saveStatusText").inner_text())
        export_request = next(item for item in ReviewMockHandler.post_requests if item["path"] == "/api/export")
        self.assertEqual(
            export_request["body"],
            {"revision": 5, "planId": cut_plan_for_selection(set(), 5)["planId"]},
        )
        self.assertTrue(page.locator("#exportResult").is_hidden())

    def test_cancel_stops_preview_and_export_waits(self):
        page = self.page
        self.assertTrue(page.locator("#cancelButton").is_hidden())

        for endpoint, trigger, cancelled_text in (
            ("/api/preview", "#previewButton", "试听已取消"),
            ("/api/export", "#exportButton", "导出已取消"),
        ):
            ReviewMockHandler.slow_operation = endpoint
            ReviewMockHandler.cancel_event = threading.Event()
            page.locator(trigger).click()
            for _ in range(40):
                if ReviewMockHandler.active_operation == endpoint:
                    break
                page.wait_for_timeout(25)
            self.assertEqual(ReviewMockHandler.active_operation, endpoint)
            self.assertTrue(page.locator("#cancelButton").is_visible())
            page.locator("#cancelButton").click()
            page.locator('#saveStatus[data-state="cancelled"]').wait_for()
            self.assertEqual(page.locator("#saveStatusText").inner_text(), cancelled_text)
            self.assertTrue(page.locator("#cancelButton").is_hidden())
            self.assertTrue(any(item["path"] == "/api/cancel" for item in ReviewMockHandler.post_requests))
            ReviewMockHandler.slow_operation = None

    def test_preview_seek_uses_exact_timeline_without_leaving_preview(self):
        page = self.page
        page.locator("#previewButton").click()
        page.locator("#saveStatus").filter(has_text="试听已更新").wait_for()

        page.locator('[data-utterance-id="utterance-2"] [data-seek-ms]').click()
        page.wait_for_function("Math.abs(document.querySelector('#audioPlayer').currentTime - 1) < 0.03")
        utterance_time = page.locator("#audioPlayer").evaluate("audio => audio.currentTime")
        self.assertAlmostEqual(utterance_time, 1, delta=0.03)
        self.assertTrue(page.locator("#audioPlayer").get_attribute("src").endswith("/preview.wav"))

        page.locator('[data-word-id="word-3"]').dblclick()
        page.wait_for_function("Math.abs(document.querySelector('#audioPlayer').currentTime - 1) < 0.03")
        word_time = page.locator("#audioPlayer").evaluate("audio => audio.currentTime")
        self.assertAlmostEqual(word_time, 1, delta=0.03)
        self.assertTrue(page.locator("#audioPlayer").get_attribute("src").endswith("/preview.wav"))

        page.locator('[data-word-id="word-2"]').dblclick()
        page.wait_for_function(
            "Math.abs(document.querySelector('#audioPlayer').currentTime - 0.22) < 0.04"
        )
        preview_time = page.locator("#audioPlayer").evaluate("audio => audio.currentTime")
        self.assertAlmostEqual(preview_time, 0.22, delta=0.04)
        self.assertTrue(page.locator("#audioPlayer").get_attribute("src").endswith("/preview.wav"))


if __name__ == "__main__":
    unittest.main()
