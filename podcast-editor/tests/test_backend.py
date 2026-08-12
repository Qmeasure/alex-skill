from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import subprocess
import importlib.metadata
import io
import wave
from unittest import mock
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from podcast_editor.contracts import ApiStateUpdate  # noqa: E402
from podcast_editor.errors import PodcastEditorError, RevisionConflict, raise_if_cancelled  # noqa: E402
from podcast_editor.media import (  # noqa: E402
    AudioAnalysis,
    AudioAnalysisCache,
    AudioProbe,
    BoundaryResolution,
    validate_aligned_durations,
)
from podcast_editor.planning import (  # noqa: E402
    build_cut_plan,
    build_preview_utterances,
    cut_plan_payload,
    timeline_from_plan,
)
from podcast_editor.draft import export_jianying_draft  # noqa: E402
from podcast_editor.server import PodcastService, ReviewRequestHandler, create_server  # noqa: E402
from podcast_editor.preview import _run_ffmpeg, render_preview  # noqa: E402
from podcast_editor.storage import ProjectStore  # noqa: E402
from podcast_editor.transcript import (  # noqa: E402
    apply_punctuation,
    build_review_turns,
    build_transcript,
    filler_word_ids,
    parse_asr_words,
)
from podcast_editor.volcengine import (  # noqa: E402
    MAX_LOCAL_AUDIO_BYTES,
    QUERY_URL,
    SUBMIT_URL,
    VolcengineASR,
    build_request,
)
from podcast_editor.workflow import prepare_project, retranscribe_project  # noqa: E402


def asr_result(words, speaker="0"):
    return {
        "result": {
            "utterances": [
                {
                    "speaker_id": speaker,
                    "words": [
                        {"text": text, "start_time": start, "end_time": end, "confidence": 0.9}
                        for text, start, end in words
                    ],
                }
            ]
        }
    }


class FakeTranscriber:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def transcribe(self, audio_path, *, identify_speakers):
        self.calls.append((Path(audio_path), identify_speakers))
        return next(self.results)


class FakeResponse:
    def __init__(self, status_code=200, headers=None, body=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body or {}

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def _package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


class BackendTests(unittest.TestCase):
    def test_request_has_required_flags_and_never_splits_channels(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "stereo.mp3"
            audio.write_bytes(b"audio")
            request = build_request(audio, identify_speakers=True)
        options = request["request"]
        self.assertTrue(options["show_utterances"])
        self.assertFalse(options["enable_ddc"])
        self.assertTrue(options["enable_punc"])
        self.assertFalse(options["enable_channel_split"])
        self.assertTrue(options["enable_speaker_info"])

    def test_punctuation_is_display_only_and_filler_words_are_preselected(self):
        result = {
            "result": {
                "utterances": [
                    {
                        "speaker_id": "0",
                        "text": "呃，大家好！",
                        "words": [
                            {"text": "呃", "start_time": 0, "end_time": 100},
                            {"text": "大", "start_time": 120, "end_time": 200},
                            {"text": "家", "start_time": 200, "end_time": 280},
                            {"text": "好", "start_time": 280, "end_time": 400},
                        ],
                    }
                ]
            }
        }
        speakers, utterances = build_transcript("mixed", [parse_asr_words(result, require_speaker=True)])
        self.assertEqual(len(speakers), 1)
        words = utterances[0]["words"]
        self.assertEqual([word["text"] for word in words], ["呃", "大", "家", "好"])
        self.assertEqual(words[0]["punctuationAfter"], "，")
        self.assertEqual(words[-1]["punctuationAfter"], "！")
        self.assertEqual(filler_word_ids(utterances), ["word-0000001"])

    def test_apply_punctuation_keeps_existing_word_ids_and_times(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
        before = [dict(word) for utterance in project["utterances"] for word in utterance["words"]]
        result = {
            "result": {
                "utterances": [
                    {
                        "speaker_id": "0",
                        "text": "嗯。",
                        "words": [{"text": "嗯", "start_time": 100, "end_time": 200}],
                    }
                ]
            }
        }
        self.assertEqual(apply_punctuation(project, result), 1)
        after = [dict(word) for utterance in project["utterances"] for word in utterance["words"]]
        self.assertEqual([{k: v for k, v in word.items() if k != "punctuationAfter"} for word in after], before)
        self.assertEqual(after[0]["punctuationAfter"], "。")

    def test_apply_punctuation_rejects_changed_transcript_text(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
        result = {
            "result": {
                "utterances": [
                    {
                        "speaker_id": "0",
                        "text": "啊。",
                        "words": [{"text": "啊", "start_time": 100, "end_time": 200}],
                    }
                ]
            }
        }
        with self.assertRaises(PodcastEditorError) as raised:
            apply_punctuation(project, result)
        self.assertEqual(raised.exception.code, "punctuation_text_mismatch")
        self.assertNotIn("punctuationAfter", project["utterances"][0]["words"][0])

    def test_review_turns_split_only_when_speaker_changes(self):
        utterances = [
            {"id": "u1", "speakerId": "s1", "startMs": 0, "endMs": 100, "words": []},
            {"id": "u2", "speakerId": "s1", "startMs": 10_000, "endMs": 11_000, "words": []},
            {"id": "u3", "speakerId": "s2", "startMs": 12_000, "endMs": 13_000, "words": []},
        ]
        turns = build_review_turns(utterances)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["utteranceIds"], ["u1", "u2"])
        self.assertEqual(turns[0]["endMs"], 11_000)

    def test_local_audio_over_100_mib_is_rejected_before_base64(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "large.mp3"
            with audio.open("wb") as stream:
                stream.truncate(MAX_LOCAL_AUDIO_BYTES + 1)
            with self.assertRaises(PodcastEditorError) as raised:
                build_request(audio, identify_speakers=True)
        self.assertEqual(raised.exception.code, "audio_too_large")

    def test_asr_uses_approved_headers_and_reuses_request_id(self):
        session = FakeSession(
            [
                FakeResponse(headers={"X-Api-Status-Code": "20000000", "X-Tt-Logid": "log"}),
                FakeResponse(
                    headers={"X-Api-Status-Code": "20000000"},
                    body=asr_result([("好", 0, 100)]),
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "audio.mp3"
            audio.write_bytes(b"audio")
            client = VolcengineASR("secret", session=session, sleep=lambda _: None, poll_interval=0)
            client.transcribe(audio, identify_speakers=True)
        self.assertEqual([call[0] for call in session.calls], [SUBMIT_URL, QUERY_URL])
        submit_headers = session.calls[0][1]["headers"]
        query_headers = session.calls[1][1]["headers"]
        self.assertEqual(submit_headers["X-Api-Key"], "secret")
        self.assertEqual(submit_headers["X-Api-Resource-Id"], "volc.bigasr.auc")
        self.assertEqual(submit_headers["X-Api-Request-Id"], query_headers["X-Api-Request-Id"])
        self.assertEqual(query_headers["X-Tt-Logid"], "log")

    def test_one_file_is_mixed_even_when_filename_says_mix(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "MIX_stereo.mp3"
            audio.write_bytes(b"audio")
            transcriber = FakeTranscriber([asr_result([("你", 0, 100)], speaker="host")])
            store = prepare_project(
                [audio],
                Path(folder) / "work",
                transcriber=transcriber,
                probes=[AudioProbe(1000, 26.0, "mp3", 44100)],
            )
            project = store.load_project()
        self.assertEqual(project["mode"], "mixed")
        self.assertEqual(transcriber.calls[0][1], True)
        self.assertIsNone(project["sources"][0]["speakerId"])

    def test_retranscribe_replaces_state_and_preserves_every_speaker_cluster(self):
        result = {
            "result": {
                "utterances": [
                    {
                        "speaker_id": speaker,
                        "text": text,
                        "words": [{"text": text, "start_time": index * 200, "end_time": index * 200 + 100}],
                    }
                    for index, (speaker, text) in enumerate(
                        (("voice-a", "嗯"), ("voice-b", "你"), ("voice-c", "好"), ("voice-a", "啊"))
                    )
                ]
            }
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "project"
            audio = Path(folder) / "mix.mp3"
            audio.write_bytes(b"audio")
            prepare_project(
                [audio],
                root,
                transcriber=FakeTranscriber([asr_result([("旧", 0, 100)], speaker="old")]),
                probes=[AudioProbe(1000, 1.0, "mp3", 1000)],
            )
            old_project = ProjectStore(root).load_project()
            old_word_ids = {
                word["id"] for utterance in old_project["utterances"] for word in utterance["words"]
            }
            (root / "selection-seed.json").write_text("{}", encoding="utf-8")
            (root / "selection-notes.json").write_text("{}", encoding="utf-8")
            (root / "cache").mkdir(exist_ok=True)
            (root / "cache" / "preview-old.wav").write_bytes(b"preview")
            analysis = root / "cache" / "audio-analysis" / "source.bin"
            analysis.parent.mkdir(parents=True)
            analysis.write_bytes(b"analysis")
            draft = root / "剪映草稿" / "keep.txt"
            draft.parent.mkdir()
            draft.write_text("draft", encoding="utf-8")

            store = retranscribe_project(
                root,
                transcriber=FakeTranscriber([result]),
                probes=[AudioProbe(1000, 1.0, "mp3", 1000)],
            )
            project = store.load_project()
            state = store.load_state(project)

            self.assertEqual([speaker["name"] for speaker in project["speakers"]], ["嘉宾一", "嘉宾二", "嘉宾三"])
            self.assertEqual(
                [utterance["speakerId"] for utterance in project["utterances"]],
                ["speaker-01", "speaker-02", "speaker-03", "speaker-01"],
            )
            self.assertEqual(len(state["selectedWordIds"]), 2)
            self.assertTrue(all(word_id.startswith("word-rt-") for word_id in state["selectedWordIds"]))
            self.assertTrue(all(utterance["id"].startswith("utterance-rt-") for utterance in project["utterances"]))
            new_word_ids = {
                word["id"] for utterance in project["utterances"] for word in utterance["words"]
            }
            self.assertTrue(old_word_ids.isdisjoint(new_word_ids))
            self.assertEqual(state["speakerOverrides"], {})
            self.assertEqual(state["cutOverrides"], {})
            self.assertFalse((root / "selection-seed.json").exists())
            self.assertFalse((root / "selection-notes.json").exists())
            self.assertFalse((root / "cache" / "preview-old.wav").exists())
            self.assertEqual((root / "cache" / "audio-analysis" / "source.bin").read_bytes(), b"analysis")
            self.assertEqual((root / "剪映草稿" / "keep.txt").read_text(encoding="utf-8"), "draft")

    def test_failed_retranscription_leaves_existing_project_unchanged(self):
        class FailedTranscriber:
            def transcribe(self, audio_path, *, identify_speakers):
                raise PodcastEditorError("asr_failed", "识别失败")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "project"
            audio = Path(folder) / "mix.mp3"
            audio.write_bytes(b"audio")
            store = prepare_project(
                [audio],
                root,
                transcriber=FakeTranscriber([asr_result([("旧", 0, 100)], speaker="old")]),
                probes=[AudioProbe(1000, 1.0, "mp3", 1000)],
            )
            before_project = store.project_path.read_bytes()
            before_state = store.state_path.read_bytes()
            with self.assertRaises(PodcastEditorError):
                retranscribe_project(
                    root,
                    transcriber=FailedTranscriber(),
                    probes=[AudioProbe(1000, 1.0, "mp3", 1000)],
                )
            self.assertEqual(store.project_path.read_bytes(), before_project)
            self.assertEqual(store.state_path.read_bytes(), before_state)

    def test_mixed_mode_requires_diarization_label(self):
        result = {"result": {"utterances": [{"words": [{"text": "你", "start_time": 0, "end_time": 100}]}]}}
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "mix.mp3"
            audio.write_bytes(b"audio")
            with self.assertRaises(PodcastEditorError) as raised:
                prepare_project(
                    [audio],
                    Path(folder) / "work",
                    transcriber=FakeTranscriber([result]),
                    probes=[AudioProbe(1000, 1.0, "mp3", 1000)],
                )
        self.assertEqual(raised.exception.code, "missing_speaker_info")

    def test_multiple_files_are_fixed_speaker_tracks_and_time_merged(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / "a.wav", Path(folder) / "b.wav"]
            for path in paths:
                path.write_bytes(b"audio")
            transcriber = FakeTranscriber(
                [asr_result([("后", 200, 300)]), asr_result([("先", 100, 180)])]
            )
            store = prepare_project(
                paths,
                Path(folder) / "work",
                transcriber=transcriber,
                probes=[AudioProbe(1000, 1.0, "pcm", 1000), AudioProbe(1000, 1.0, "pcm", 1000)],
            )
            project = store.load_project()
        self.assertEqual(project["mode"], "multitrack")
        self.assertEqual([call[1] for call in transcriber.calls], [False, False])
        self.assertEqual(
            [word["text"] for utterance in project["utterances"] for word in utterance["words"]],
            ["先", "后"],
        )
        self.assertEqual([source["speakerId"] for source in project["sources"]], ["speaker-01", "speaker-02"])

    def test_duration_mismatch_stops_instead_of_padding(self):
        with self.assertRaises(PodcastEditorError) as raised:
            validate_aligned_durations(
                [AudioProbe(1000, 10.0, "a", 1000), AudioProbe(1011, 10.0, "a", 1000)]
            )
        self.assertEqual(raised.exception.code, "duration_mismatch")

    def test_within_frame_duration_skew_preserves_each_track_tail(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / "a.wav", Path(folder) / "b.wav"]
            for path in paths:
                path.write_bytes(b"audio")
            store = prepare_project(
                paths,
                Path(folder) / "work",
                transcriber=FakeTranscriber(
                    [asr_result([("甲", 100, 200)]), asr_result([("乙", 300, 400)])]
                ),
                probes=[
                    AudioProbe(1000, 10.0, "pcm", 1000),
                    AudioProbe(1005, 10.0, "pcm", 1000),
                ],
            )
            project = store.load_project()
            plan = build_cut_plan(project, store.load_state(project))
        self.assertEqual(plan.duration_ms, 1005)
        self.assertEqual([track.segments[-1].source_end_ms for track in plan.tracks], [1000, 1005])

    def test_state_revision_and_rename_are_atomic(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            state = store.update_state(ApiStateUpdate(0, ["word-0000001"], {"speaker-01": "主持人"}))
            self.assertEqual(state["revision"], 1)
            self.assertEqual(state["speakerNames"]["speaker-01"], "主持人")
            with self.assertRaises(RevisionConflict):
                store.update_state(ApiStateUpdate(0, [], {}))

    def test_speaker_override_changes_review_payload_without_rewriting_project(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed", two_speakers=True)
            service = PodcastService(store)
            saved = service.update_state(
                {
                    "revision": 0,
                    "selectedWordIds": [],
                    "speakerNames": {"speaker-01": "Lester", "speaker-02": "Alex"},
                    "speakerOverrides": {"u2": "speaker-02"},
                }
            )
            payload = service.project_payload()
            raw_project = store.load_project()

        self.assertEqual(saved["state"]["speakerOverrides"], {"u2": "speaker-02"})
        self.assertEqual(saved["project"]["utterances"][1]["speakerId"], "speaker-02")
        self.assertEqual(saved["reviewTurns"][1]["speakerId"], "speaker-02")
        self.assertEqual(payload["project"]["utterances"][1]["speakerId"], "speaker-02")
        self.assertEqual(raw_project["utterances"][1]["speakerId"], "speaker-01")

    def test_speaker_override_rejects_unknown_utterance_or_speaker(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed", two_speakers=True)
            for overrides in ({"missing": "speaker-02"}, {"u2": "missing"}):
                with self.subTest(overrides=overrides), self.assertRaises(PodcastEditorError):
                    store.update_state(ApiStateUpdate(0, [], {}, overrides))

    def test_duplicate_display_names_are_allowed_but_export_tracks_stay_unique(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="multitrack")
            state = store.update_state(
                ApiStateUpdate(0, [], {"speaker-01": "Alex", "speaker-02": "Alex"})
            )
            plan = build_cut_plan(store.load_project(), state)
        self.assertEqual([track.name for track in plan.tracks], ["Alex", "Alex (2)"])

    def test_mixed_selection_is_global_and_packed(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
        self.assertEqual([(r.start_ms, r.end_ms) for r in plan.global_deletions], [(100, 200)])
        self.assertEqual(
            [(s.source_start_ms, s.source_end_ms, s.target_start_ms) for s in plan.tracks[0].segments],
            [(0, 100, 0), (200, 1000, 100)],
        )

    def test_mixed_consecutive_selected_words_merge_across_speakers_and_long_gaps(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed", two_speakers=True)
            project = store.load_project()
            project["utterances"][0]["words"][0].update(startMs=100, endMs=180)
            project["utterances"][1]["speakerId"] = "speaker-02"
            project["utterances"][1]["words"][0].update(startMs=1_180, endMs=1_260)
            project["utterances"][1].update(startMs=1_180, endMs=1_260)
            project["durationMs"] = 2_000
            project["sources"][0]["durationMs"] = 2_000
            state = store.load_state(store.load_project())
            state["speakerNames"]["speaker-02"] = "嘉宾二"
            state["selectedWordIds"] = ["word-0000001", "word-0000002"]
            plan = build_cut_plan(project, state)
        self.assertEqual([(item.start_ms, item.end_ms) for item in plan.global_deletions], [(100, 1260)])
        self.assertEqual(len(plan.deletions), 1)
        self.assertEqual(plan.deletions[0].first_word_id, "word-0000001")
        self.assertEqual(plan.deletions[0].last_word_id, "word-0000002")

    def test_unselected_real_word_breaks_mixed_deletion_group(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            project["utterances"][0]["words"] = [
                {"id": "w1", "text": "删", "startMs": 100, "endMs": 180},
                {"id": "w2", "text": "留", "startMs": 400, "endMs": 480},
                {"id": "w3", "text": "删", "startMs": 900, "endMs": 980},
            ]
            project["utterances"][0].update(startMs=100, endMs=980)
            state = store.load_state(store.load_project())
            state["selectedWordIds"] = ["w1", "w3"]
            plan = build_cut_plan(project, state)
        self.assertEqual([(item.start_ms, item.end_ms) for item in plan.global_deletions], [(100, 180), (900, 980)])

    def test_cut_plan_payload_has_stable_deletion_and_plan_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            state["revision"] = 4
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
        first = cut_plan_payload(project, state, plan, audio_fingerprints={"source-01": "fp"})
        second = cut_plan_payload(project, state, plan, audio_fingerprints={"source-01": "fp"})
        self.assertEqual(first, second)
        self.assertRegex(first["planId"], r"^plan-[0-9a-f]{20}$")
        self.assertRegex(first["deletions"][0]["id"], r"^del-[0-9a-f]{20}$")
        self.assertEqual(first["revision"], 4)
        self.assertEqual(first["timeline"]["revision"], 4)

    def test_cut_override_must_cover_raw_range_and_not_cross_retained_words(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            project["utterances"][0]["words"].append(
                {"id": "kept", "text": "保留", "startMs": 250, "endMs": 350}
            )
            project["utterances"][0]["endMs"] = 350
            state = store.load_state(store.load_project())
            state["selectedWordIds"] = ["word-0000001"]
            base = build_cut_plan(project, state)
            cut_id = base.deletions[0].id
            state["cutOverrides"] = {cut_id: {"startMs": 90, "endMs": 240}}
            valid = build_cut_plan(project, state)
            self.assertEqual((valid.deletions[0].start_ms, valid.deletions[0].end_ms), (90, 240))
            state["cutOverrides"] = {cut_id: {"startMs": 110, "endMs": 240}}
            with self.assertRaises(PodcastEditorError) as raised:
                build_cut_plan(project, state)
            self.assertEqual(raised.exception.code, "invalid_cut_override")
            state["cutOverrides"] = {cut_id: {"startMs": 90, "endMs": 260}}
            with self.assertRaises(PodcastEditorError) as raised:
                build_cut_plan(project, state)
            self.assertEqual(raised.exception.code, "invalid_cut_override")

    def test_audio_analysis_uses_sustained_quiet_run_and_returns_waveform_points(self):
        analysis = AudioAnalysis(
            fingerprint="fp",
            duration_ms=1000,
            frame_ms=10,
            rms=(900,) * 20 + (10,) * 16 + (1200,) * 28 + (8,) * 16 + (700,) * 20,
            peaks=tuple(range(100)),
        )
        resolution = analysis.adjust_deletion(400, 600, None, None)
        self.assertLess(resolution.start_ms, 400)
        self.assertGreater(resolution.end_ms, 600)
        self.assertEqual(resolution.mode, "acoustic")
        points = analysis.waveform(100, 900, 16)
        self.assertEqual(len(points), 16)
        self.assertEqual(points[0]["startMs"], 100)
        self.assertEqual(points[-1]["endMs"], 900)

    def test_continuous_speech_marks_boundary_for_review_and_protects_next_word(self):
        rms = (5,) * 38 + (1200,) * 44 + (5,) * 18
        analysis = AudioAnalysis("fp", 1000, 10, rms, rms)
        next_word = {"id": "kept", "startMs": 600, "endMs": 800}
        resolution = analysis.adjust_deletion(400, 600, None, next_word)
        next_onset = analysis.speech_bounds(600, 800, within_word=True)[0]
        self.assertTrue(resolution.needs_review)
        self.assertIsNotNone(resolution.warning)
        self.assertLessEqual(resolution.end_ms, next_onset)
        self.assertLessEqual(resolution.max_end_ms, next_onset)

    def test_zero_safe_range_and_nine_ms_raw_tail_are_not_cuttable(self):
        analysis = AudioAnalysis("fp", 1000, 10, (1200,) * 100, (1200,) * 100)
        zero_safe = analysis.adjust_deletion(
            200,
            400,
            {"startMs": 100, "endMs": 300},
            {"startMs": 300, "endMs": 500},
        )
        nine_ms_tail = analysis.adjust_deletion(
            100,
            200,
            None,
            {"startMs": 191, "endMs": 300},
        )
        self.assertFalse(zero_safe.can_cut)
        self.assertFalse(nine_ms_tail.can_cut)
        self.assertTrue(zero_safe.needs_review)
        self.assertIn("不会自动剪切", nine_ms_tail.warning)

    def test_snap_that_misses_nine_ms_expands_to_raw_tail_when_safe_range_allows_it(self):
        analysis = AudioAnalysis("fp", 1000, 10, (1000,) * 100, (1000,) * 100)
        with mock.patch.object(
            AudioAnalysis, "speech_bounds", return_value=(100, 209, 100)
        ), mock.patch.object(
            AudioAnalysis,
            "_nearest_low_run",
            side_effect=[None, (200, 210)],
        ):
            resolution = analysis.adjust_deletion(100, 209, None, None)
        self.assertTrue(resolution.can_cut)
        self.assertTrue(resolution.needs_review)
        self.assertLessEqual(resolution.start_ms, 100)
        self.assertGreaterEqual(resolution.end_ms, 209)

        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state, boundary_resolver=lambda *args: resolution)
            payload = cut_plan_payload(
                project, state, plan, audio_fingerprints={"source-01": "fp"}
            )
            store.update_state(ApiStateUpdate(0, ["word-0000001"], {}))
            service = PodcastService(store)
            fake_analysis = mock.Mock()
            fake_analysis.adjust_deletion.return_value = resolution
            with mock.patch.object(service, "_analysis_for_source", return_value=fake_analysis):
                api_payload = service.project_payload()
        self.assertTrue(payload["deletions"][0]["canCut"])
        self.assertEqual(payload["globalDeletions"], [{"startMs": 100, "endMs": 209}])
        self.assertTrue(api_payload["playback"]["cutPlan"]["deletions"][0]["canCut"])

    def test_word_9715_equivalent_safe_range_cuts_full_raw_interval(self):
        raw_start, raw_end = 2_093_899, 2_094_219
        analysis = AudioAnalysis("fp", 2_100_000, 10, (1000,) * 100, (1000,) * 100)
        previous = {"startMs": 2_093_000, "endMs": 2_093_600}
        following = {"startMs": 2_094_800, "endMs": 2_095_200}
        with mock.patch.object(
            AudioAnalysis,
            "speech_bounds",
            side_effect=[
                (raw_start, raw_end, 100),
                (2_093_000, 2_093_539, 100),
                (2_094_960, 2_095_200, 100),
            ],
        ), mock.patch.object(
            AudioAnalysis,
            "_nearest_low_run",
            side_effect=[(2_093_800, 2_093_890), (2_094_210, 2_094_300)],
        ):
            resolution = analysis.adjust_deletion(raw_start, raw_end, previous, following)
        self.assertTrue(resolution.can_cut)
        self.assertLessEqual(resolution.start_ms, raw_start)
        self.assertGreaterEqual(resolution.end_ms, raw_end)
        self.assertEqual((resolution.min_start_ms, resolution.max_end_ms), (2_093_539, 2_094_960))

    def test_cut_plan_exposes_boundary_warning(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            project["utterances"][0]["words"].append(
                {"id": "kept", "text": "后", "startMs": 200, "endMs": 300}
            )
            project["utterances"][0]["endMs"] = 300
            state = store.load_state(store.load_project())
            state["selectedWordIds"] = ["word-0000001"]
            analysis = AudioAnalysis("fp", 1000, 10, (1000,) * 100, (1000,) * 100)
            plan = build_cut_plan(
                project,
                state,
                boundary_resolver=lambda path, start, end, previous, following: analysis.adjust_deletion(
                    start, end, previous, following
                ),
            )
            payload = cut_plan_payload(project, state, plan, audio_fingerprints={"source-01": "fp"})
        deletion = payload["deletions"][0]
        self.assertTrue(deletion["needsReview"])
        self.assertTrue(deletion["boundaryWarning"])
        self.assertLessEqual(deletion["endMs"], deletion["maxEndMs"])

    def test_uncuttable_selection_creates_no_range_and_remains_in_preview_transcript(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            resolution = BoundaryResolution(100, 100, 150, 100, "acoustic-review", True, "无安全切点", False)
            plan = build_cut_plan(
                project,
                state,
                boundary_resolver=lambda *args: resolution,
            )
            utterances = build_preview_utterances(project, state, plan)
        self.assertFalse(plan.deletions[0].can_cut)
        self.assertEqual(plan.global_deletions, ())
        self.assertEqual(utterances[0]["words"][0]["id"], "word-0000001")

    def test_mixed_cuttable_deletions_cover_raw_selection_without_touching_kept_words(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            project["utterances"][0]["words"] = [
                {"id": "w1", "text": "删", "startMs": 100, "endMs": 180},
                {"id": "w2", "text": "删", "startMs": 300, "endMs": 380},
                {"id": "kept", "text": "留", "startMs": 500, "endMs": 580},
            ]
            project["utterances"][0].update(startMs=100, endMs=580)
            state = store.load_state(store.load_project())
            state["selectedWordIds"] = ["w1", "w2"]
            plan = build_cut_plan(project, state)
        deletion = plan.deletions[0]
        self.assertTrue(deletion.can_cut)
        self.assertLessEqual(deletion.start_ms, deletion.raw_start_ms)
        self.assertGreaterEqual(deletion.end_ms, deletion.raw_end_ms)
        self.assertFalse(any(500 < item.end_ms and 580 > item.start_ms for item in plan.global_deletions))

    def test_audio_analysis_cache_decodes_each_fingerprint_once(self):
        class TrackingStream(io.BytesIO):
            def __init__(self, value):
                super().__init__(value)
                self.read_sizes = []

            def read(self, size=-1):
                self.read_sizes.append(size)
                return super().read(size)

        pcm = b"\x00\x00" * 1600
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "source.wav"
            audio.write_bytes(b"source")
            cache = AudioAnalysisCache(root / "cache", ffmpeg="ffmpeg")
            stdout = TrackingStream(pcm)
            process = mock.Mock(returncode=0, stdout=stdout)
            process.wait.return_value = 0
            process.poll.return_value = 0
            with mock.patch("podcast_editor.media.subprocess.Popen", return_value=process) as run:
                first = cache.get(audio)
                second = cache.get(audio)
        self.assertIs(first, second)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(process.stdout.closed, True)
        self.assertTrue(stdout.read_sizes)
        self.assertTrue(all(size == 64 * 1024 for size in stdout.read_sizes))

    def test_audio_analysis_failure_is_not_silently_replaced_with_raw_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            broken = root / "broken.wav"
            broken.write_bytes(b"not audio")
            store = _make_store(root / "project", mode="mixed", source_paths=[str(broken)])
            store.update_state(ApiStateUpdate(0, ["word-0000001"], {}))
            with self.assertRaises(PodcastEditorError) as raised:
                PodcastService(store).project_payload()
        self.assertEqual(raised.exception.code, "audio_analysis_failed")

    def test_preview_utterances_omit_deleted_words_and_map_global_time(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            project["utterances"].append(
                {
                    "id": "u2",
                    "speakerId": "speaker-01",
                    "startMs": 300,
                    "endMs": 400,
                    "words": [
                        {"id": "word-0000002", "text": "好", "startMs": 300, "endMs": 400}
                    ],
                }
            )
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
            utterances = build_preview_utterances(project, state, plan)
        self.assertEqual(len(utterances), 1)
        self.assertEqual(utterances[0]["id"], "u2")
        self.assertEqual((utterances[0]["startMs"], utterances[0]["endMs"]), (200, 300))
        self.assertEqual((utterances[0]["words"][0]["startMs"], utterances[0]["words"][0]["endMs"]), (200, 300))

    def test_timeline_maps_source_ranges_to_packed_playback(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            state["revision"] = 3
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
        timeline = timeline_from_plan(plan, state["revision"])
        self.assertEqual(timeline["revision"], 3)
        self.assertEqual(timeline["durationMs"], 900)
        self.assertEqual(
            timeline["segments"],
            [
                {"sourceStartMs": 0, "sourceEndMs": 100, "targetStartMs": 0, "targetEndMs": 100},
                {"sourceStartMs": 200, "sourceEndMs": 1000, "targetStartMs": 100, "targetEndMs": 900},
            ],
        )

    def test_project_and_state_responses_include_live_timeline_and_review_turns(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            service = PodcastService(store)
            payload = service.project_payload()
            self.assertEqual(len(payload["reviewTurns"]), 1)
            self.assertEqual(payload["playback"]["timeline"]["durationMs"], 1000)
            self.assertEqual(payload["playback"]["cutPlan"]["timeline"], payload["playback"]["timeline"])
            self.assertEqual(payload["playback"]["strategy"], "dual-audio-preload-v1")
            self.assertEqual(payload["playback"]["revision"], 0)
            self.assertEqual(payload["playback"]["planId"], payload["playback"]["cutPlan"]["planId"])
            saved = service.update_state(
                {
                    "revision": 0,
                    "selectedWordIds": ["word-0000001"],
                    "speakerNames": {"speaker-01": "嘉宾一"},
                }
            )
        self.assertEqual(saved["timeline"]["revision"], 1)
        self.assertEqual(saved["timeline"]["durationMs"], 860)
        self.assertEqual(saved["cutPlan"]["timeline"], saved["timeline"])
        self.assertEqual(saved["playback"]["planId"], saved["cutPlan"]["planId"])

    def test_mixed_playback_runs_follow_kept_timeline_without_bridging_deleted_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            store.update_state(ApiStateUpdate(0, ["word-0000001"], {}))
            service = PodcastService(store)
            payload = service.project_payload()["playback"]
        self.assertEqual(len(payload["runs"]), 2)
        first, second = payload["runs"]
        self.assertEqual(first["sourceEndMs"], 80)
        self.assertEqual(second["sourceStartMs"], 220)
        self.assertEqual(first["targetEndMs"], second["targetStartMs"])
        self.assertEqual(first["sources"][0]["sourceId"], "source-01")
        self.assertNotEqual(first["id"], second["id"])

    def test_multitrack_playback_uses_global_runs_and_keeps_speaker_mute_in_tracks(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="multitrack", overlap=True)
            store.update_state(ApiStateUpdate(0, ["word-0000001"], {}))
            service = PodcastService(store)
            playback = service.project_payload()["playback"]
        self.assertEqual(len(playback["runs"]), len(playback["timeline"]["segments"]))
        self.assertTrue(all(len(run["sources"]) == 2 for run in playback["runs"]))
        self.assertEqual(
            [source["sourceStartMs"] for source in playback["runs"][0]["sources"]],
            [playback["runs"][0]["sourceStartMs"]] * 2,
        )
        self.assertIn("speaker-01", playback["cutPlan"]["speakerDeletions"])
        self.assertEqual(playback["tracks"], playback["cutPlan"]["tracks"])

    def test_playback_run_id_is_stable_for_plan_and_bound_to_plan_id(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            service = PodcastService(store)
            first = service.project_payload()["playback"]
            second = service.project_payload()["playback"]
            changed = service.update_state(
                {"revision": 0, "selectedWordIds": [], "speakerNames": {"speaker-01": "新名字"}}
            )["playback"]
        self.assertEqual(first["runs"][0]["id"], second["runs"][0]["id"])
        self.assertNotEqual(first["planId"], changed["planId"])
        self.assertNotEqual(first["runs"][0]["id"], changed["runs"][0]["id"])

    def test_preview_and_export_require_current_revision_and_plan_id(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = _make_store(root / "project", mode="mixed")
            service = PodcastService(store)
            cut_plan = service.project_payload()["playback"]["cutPlan"]
            for body in ({}, {"revision": 0}, {"revision": 0, "planId": "plan-stale"}):
                with self.subTest(body=body), self.assertRaises(PodcastEditorError) as raised:
                    service.render_preview(body)
                self.assertIn(raised.exception.code, {"invalid_revision", "invalid_plan_id", "plan_conflict"})
            with mock.patch("podcast_editor.server.render_preview") as rendered:
                rendered.side_effect = lambda project, plan, output, cancel_event=None: Path(output).write_bytes(b"preview")
                response = service.render_preview({"revision": 0, "planId": cut_plan["planId"]})
            self.assertEqual(response["planId"], cut_plan["planId"])

    def test_preview_and_export_reject_uncuttable_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = _make_store(root / "project", mode="mixed")
            store.update_state(ApiStateUpdate(0, ["word-0000001"], {}))
            service = PodcastService(store, draft_root=root)
            analysis = AudioAnalysis("fp", 1000, 10, (1200,) * 100, (1200,) * 100)
            project = store.load_project()
            project["utterances"][0]["words"].append(
                {"id": "kept", "text": "后", "startMs": 191, "endMs": 300}
            )
            project["utterances"][0]["endMs"] = 300
            store.create(project, store.load_state())
            with mock.patch.object(service, "_analysis_for_source", return_value=analysis):
                cut_plan = service.project_payload()["playback"]["cutPlan"]
                self.assertFalse(cut_plan["deletions"][0]["canCut"])
                for action in (service.render_preview, service.export):
                    with self.subTest(action=action.__name__), self.assertRaises(PodcastEditorError) as raised:
                        action({"revision": 1, "planId": cut_plan["planId"]})
                    self.assertEqual(raised.exception.code, "uncuttable_selection")
                    self.assertEqual(
                        raised.exception.details["deletionIds"],
                        [cut_plan["deletions"][0]["id"]],
                    )

    def test_state_persists_cut_overrides(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            service = PodcastService(store)
            cut_id = service.project_payload()["playback"]["cutPlan"]["deletions"]
            self.assertEqual(cut_id, [])
            initial = service.update_state(
                {
                    "revision": 0,
                    "selectedWordIds": ["word-0000001"],
                    "speakerNames": {"speaker-01": "嘉宾一"},
                    "cutOverrides": {},
                }
            )
            deletion = initial["cutPlan"]["deletions"][0]
            saved = service.update_state(
                {
                    "revision": 1,
                    "selectedWordIds": ["word-0000001"],
                    "speakerNames": {"speaker-01": "嘉宾一"},
                    "cutOverrides": {
                        deletion["id"]: {"startMs": 90, "endMs": 240}
                    },
                }
            )
        self.assertEqual(saved["state"]["cutOverrides"], saved["cutOverrides"])

    def test_invalid_candidate_cut_override_does_not_modify_saved_state(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            service = PodcastService(store)
            selected = service.update_state(
                {
                    "revision": 0,
                    "selectedWordIds": ["word-0000001"],
                    "speakerNames": {"speaker-01": "嘉宾一"},
                }
            )
            deletion = selected["cutPlan"]["deletions"][0]
            with self.assertRaises(PodcastEditorError):
                service.update_state(
                    {
                        "revision": 1,
                        "selectedWordIds": ["word-0000001"],
                        "speakerNames": {"speaker-01": "嘉宾一"},
                        "cutOverrides": {
                            deletion["id"]: {"startMs": deletion["rawStartMs"] + 1, "endMs": 240}
                        },
                    }
                )
            persisted = store.load_state()
        self.assertEqual(persisted["revision"], 1)
        self.assertEqual(persisted["cutOverrides"], {})

    def test_stale_cut_overrides_are_removed_when_selection_groups_merge_split_and_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            project["utterances"][0]["words"] = [
                {"id": "w1", "text": "一", "startMs": 100, "endMs": 150},
                {"id": "w2", "text": "二", "startMs": 200, "endMs": 250},
                {"id": "w3", "text": "三", "startMs": 300, "endMs": 350},
            ]
            project["utterances"][0].update(startMs=100, endMs=350)
            store.create(project, store.load_state())
            service = PodcastService(store)

            split = service.update_state(
                {"revision": 0, "selectedWordIds": ["w1", "w3"], "speakerNames": {"speaker-01": "嘉宾一"}}
            )
            split_overrides = {
                item["id"]: {"startMs": item["startMs"], "endMs": item["endMs"]}
                for item in split["cutPlan"]["deletions"]
            }
            merged = service.update_state(
                {
                    "revision": 1,
                    "selectedWordIds": ["w1", "w2", "w3"],
                    "speakerNames": {"speaker-01": "嘉宾一"},
                    "cutOverrides": split_overrides,
                }
            )
            self.assertEqual(merged["cutOverrides"], {})
            merged_deletion = merged["cutPlan"]["deletions"][0]
            merged_override = {
                merged_deletion["id"]: {
                    "startMs": merged_deletion["startMs"],
                    "endMs": merged_deletion["endMs"],
                }
            }
            split_again = service.update_state(
                {
                    "revision": 2,
                    "selectedWordIds": ["w1", "w3"],
                    "speakerNames": {"speaker-01": "嘉宾一"},
                    "cutOverrides": merged_override,
                }
            )
            self.assertEqual(split_again["cutOverrides"], {})
            restored = service.update_state(
                {
                    "revision": 3,
                    "selectedWordIds": ["w1", "w2", "w3"],
                    "speakerNames": {"speaker-01": "嘉宾一"},
                    "cutOverrides": split_overrides,
                }
            )
            persisted = store.load_state()
        self.assertEqual(restored["cutOverrides"], {})
        self.assertEqual(persisted["revision"], 4)
        self.assertEqual(persisted["cutOverrides"], {})

    def test_plan_id_ignores_display_names_but_tracks_audio_fingerprint(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            plan = build_cut_plan(project, state)
        first = cut_plan_payload(project, state, plan, audio_fingerprints={"source-01": "a"})
        renamed = dict(state)
        renamed["speakerNames"] = {"speaker-01": "主持人"}
        second = cut_plan_payload(project, renamed, plan, audio_fingerprints={"source-01": "a"})
        changed_audio = cut_plan_payload(project, renamed, plan, audio_fingerprints={"source-01": "b"})
        self.assertEqual(first["planId"], second["planId"])
        self.assertNotEqual(second["planId"], changed_audio["planId"])

    def test_plan_id_changes_when_actual_resolution_or_can_cut_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            precise = BoundaryResolution(90, 210, 0, 1000, "acoustic", False, None, True)
            blocked = BoundaryResolution(
                100, 100, 150, 100, "acoustic-review", True, "无安全切点", False
            )
            precise_plan = build_cut_plan(project, state, boundary_resolver=lambda *args: precise)
            blocked_plan = build_cut_plan(project, state, boundary_resolver=lambda *args: blocked)
        precise_payload = cut_plan_payload(
            project, state, precise_plan, audio_fingerprints={"source-01": "same"}
        )
        blocked_payload = cut_plan_payload(
            project, state, blocked_plan, audio_fingerprints={"source-01": "same"}
        )
        self.assertNotEqual(precise_payload["planId"], blocked_payload["planId"])

    def test_preview_cache_key_changes_when_actual_plan_changes_at_same_revision(self):
        class MutableAnalysis:
            def __init__(self):
                self.resolution = BoundaryResolution(
                    90, 210, 0, 1000, "acoustic", False, None, True
                )

            def adjust_deletion(self, *args):
                return self.resolution

        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            store.update_state(ApiStateUpdate(0, ["word-0000001"], {}))
            service = PodcastService(store)
            analysis = MutableAnalysis()

            def fake_render(project, plan, output, cancel_event=None):
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_bytes(b"preview")

            with mock.patch.object(service, "_analysis_for_source", return_value=analysis), mock.patch(
                "podcast_editor.server.render_preview", side_effect=fake_render
            ) as rendered:
                first_plan = service.project_payload()["playback"]["cutPlan"]
                first = service.render_preview({"revision": 1, "planId": first_plan["planId"]})
                analysis.resolution = BoundaryResolution(
                    80, 220, 0, 1000, "acoustic", False, None, True
                )
                second_plan = service.project_payload()["playback"]["cutPlan"]
                second = service.render_preview({"revision": 1, "planId": second_plan["planId"]})
        self.assertNotEqual(first["planId"], second["planId"])
        self.assertEqual(rendered.call_count, 2)

    def test_waveform_endpoint_validates_source_and_point_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = _make_store(root / "project", mode="multitrack")
            service = PodcastService(store)
            fake = mock.Mock()
            fake.waveform.return_value = [{"startMs": 0, "endMs": 100, "peak": 0.5}]
            with mock.patch.object(service, "_analysis_for_source", return_value=fake):
                with self.assertRaises(PodcastEditorError) as raised:
                    service.waveform({"startMs": ["0"], "endMs": ["100"], "points": ["16"]})
                self.assertEqual(raised.exception.code, "source_required")
                payload = service.waveform(
                    {"sourceId": ["source-01"], "startMs": ["0"], "endMs": ["100"], "points": ["16"]}
                )
            self.assertEqual(payload["sourceId"], "source-01")
            self.assertEqual(len(payload["points"]), 1)

    def test_multitrack_payload_exposes_per_source_audio_and_track_segments(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="multitrack", overlap=True)
            store.update_state(ApiStateUpdate(0, ["word-0000001"], {}))
            service = PodcastService(store)
            payload = service.project_payload()
            cut_plan = payload["playback"]["cutPlan"]
            sources = payload["playback"]["sources"]
            second_path = Path(store.load_project()["sources"][1]["path"])
            self.assertEqual(service.source_audio("source-02"), second_path)
        self.assertEqual([item["sourceId"] for item in sources], ["source-01", "source-02"])
        self.assertTrue(all("sourceId=" in item["url"] for item in sources))
        self.assertEqual([item["sourceId"] for item in cut_plan["tracks"]], ["source-01", "source-02"])
        self.assertIn("speaker-01", cut_plan["speakerDeletions"])
        self.assertTrue(all(item["segments"] for item in cut_plan["tracks"]))

    def test_preview_utterances_keep_time_for_speaker_only_deletion(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="multitrack", overlap=True)
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
            utterances = build_preview_utterances(project, state, plan)
        other = next(item for item in utterances if item["speakerId"] == "speaker-02")
        self.assertEqual((other["startMs"], other["endMs"]), (100, 200))
        self.assertEqual(other["words"][0]["text"], "好")

    def test_mixed_preview_omits_unselected_word_cut_by_global_overlap(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            project["speakers"].append({"id": "speaker-02", "name": "嘉宾二", "sourceIndex": None})
            project["utterances"].append(
                {
                    "id": "u2",
                    "speakerId": "speaker-02",
                    "startMs": 150,
                    "endMs": 400,
                    "words": [
                        {"id": "word-0000002", "text": "重叠", "startMs": 150, "endMs": 250},
                        {"id": "word-0000003", "text": "保留", "startMs": 300, "endMs": 400},
                    ],
                }
            )
            state["speakerNames"]["speaker-02"] = "嘉宾二"
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
            utterances = build_preview_utterances(project, state, plan)
        other = next(item for item in utterances if item["speakerId"] == "speaker-02")
        self.assertEqual([word["id"] for word in other["words"]], ["word-0000003"])
        self.assertEqual((other["startMs"], other["endMs"]), (200, 300))

    def test_preview_service_response_includes_mapped_utterances(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            store.update_state(ApiStateUpdate(0, ["word-0000001"], {}))
            service = PodcastService(store)

            def fake_render(project, plan, output, cancel_event=None):
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_bytes(b"preview")

            cut_plan = service.project_payload()["playback"]["cutPlan"]
            with mock.patch("podcast_editor.server.render_preview", side_effect=fake_render):
                response = service.render_preview({"revision": 1, "planId": cut_plan["planId"]})
        self.assertEqual(response["revision"], 1)
        self.assertIn("url", response)
        self.assertIn("utterances", response)
        self.assertIn("timeline", response)
        self.assertEqual(response["utterances"], [])

    def test_preview_cache_avoids_rendering_same_revision_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            service = PodcastService(store)

            def fake_render(project, plan, output, cancel_event=None):
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_bytes(b"preview")

            cut_plan = service.project_payload()["playback"]["cutPlan"]
            with mock.patch("podcast_editor.server.render_preview", side_effect=fake_render) as rendered:
                first = service.render_preview({"revision": 0, "planId": cut_plan["planId"]})
                second = service.render_preview({"revision": 0, "planId": cut_plan["planId"]})
        self.assertEqual(first, second)
        self.assertEqual(rendered.call_count, 1)

    def test_mixed_preview_concatenates_short_faded_pieces(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
            with mock.patch("podcast_editor.preview._run_ffmpeg") as run:
                render_preview(project, plan, Path(folder) / "preview.wav", ffmpeg="ffmpeg")
        command = run.call_args.args[0]
        filters = command[command.index("-filter_complex") + 1]
        self.assertIn("d=0.005000", filters)
        self.assertIn("concat=n=2:v=0:a=1[preview]", filters)
        self.assertNotIn("adelay", filters)
        self.assertNotIn("amix", filters)

    def test_multitrack_preview_mixes_without_normalizing_delayed_pieces(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="multitrack")
            project = store.load_project()
            plan = build_cut_plan(project, store.load_state(project))
            with mock.patch("podcast_editor.preview._run_ffmpeg") as run:
                render_preview(project, plan, Path(folder) / "preview.wav", ffmpeg="ffmpeg")
        command = run.call_args.args[0]
        filters = command[command.index("-filter_complex") + 1]
        self.assertIn("normalize=0", filters)
        self.assertIn("alimiter=limit=0.95", filters)
        self.assertNotIn("normalize=1[preview]", filters)

    def test_multitrack_overlap_mutes_only_selected_speaker(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="multitrack", overlap=True)
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
        self.assertEqual(
            [(r.start_ms, r.end_ms) for r in plan.global_deletions], [(100, 150)]
        )
        self.assertEqual(
            [(r.start_ms, r.end_ms) for r in plan.speaker_deletions["speaker-01"]], [(150, 200)]
        )
        first, second = plan.tracks
        self.assertEqual(first.segments[1].target_start_ms, 150)
        self.assertEqual(len(second.segments), 2)

    def test_partial_overlap_splits_global_and_speaker_only_ranges(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="multitrack", overlap=True)
            project = store.load_project()
            project["utterances"][0]["words"][0]["endMs"] = 300
            project["utterances"][0]["endMs"] = 300
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
        self.assertEqual([(item.start_ms, item.end_ms) for item in plan.global_deletions], [(100, 150), (250, 300)])
        self.assertEqual([(item.start_ms, item.end_ms) for item in plan.speaker_deletions["speaker-01"]], [(150, 250)])

    def test_overlap_selected_by_both_speakers_becomes_global(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="multitrack", overlap=True)
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001", "word-0000002"]
            plan = build_cut_plan(project, state)
        self.assertEqual([(item.start_ms, item.end_ms) for item in plan.global_deletions], [(100, 250)])
        self.assertEqual(plan.speaker_deletions, {})

    def test_low_energy_adjustment_never_keeps_part_of_selected_word(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            calls = []
            def finder(path, center, lower, upper):
                calls.append((center, lower, upper))
                return upper if len(calls) == 1 else lower
            plan = build_cut_plan(project, state, boundary_finder=finder)
        self.assertEqual([(item.start_ms, item.end_ms) for item in plan.global_deletions], [(100, 200)])
        self.assertLessEqual(calls[0][2], 100)
        self.assertGreaterEqual(calls[1][1], 200)

    def test_nested_project_api_and_http_range(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "a.wav"
            audio.write_bytes(b"0123456789")
            store = _make_store(root / "project", mode="mixed", source_paths=[str(audio)])
            static_root = root / "assets"
            static_root.mkdir()
            (static_root / "review.html").write_text("ok", encoding="utf-8")
            server = create_server(store, static_root=static_root)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urllib.request.urlopen(base + "/api/project") as response:
                    payload = json.load(response)
                self.assertEqual(set(("project", "state", "playback")) - set(payload), set())
                request = urllib.request.Request(base + "/api/audio/source", headers={"Range": "bytes=2-5"})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.read(), b"2345")
                    self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")
                    etag = response.headers["ETag"]
                    self.assertTrue(etag)
                    self.assertIn("max-age", response.headers["Cache-Control"])
                conditional = urllib.request.Request(
                    base + "/api/audio/source", headers={"If-None-Match": etag}
                )
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(conditional)
                self.assertEqual(raised.exception.code, 304)
                raised.exception.close()
                conditional_range = urllib.request.Request(
                    base + "/api/audio/source",
                    headers={"If-None-Match": etag, "Range": "bytes=0-1"},
                )
                with urllib.request.urlopen(conditional_range) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(response.read(), b"01")
                    self.assertEqual(response.headers["ETag"], etag)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_audio_client_disconnect_ends_file_response_without_error(self):
        class DisconnectedWriter:
            def write(self, _chunk):
                raise BrokenPipeError

        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "audio.wav"
            audio.write_bytes(b"audio")
            handler = object.__new__(ReviewRequestHandler)
            handler.headers = {}
            handler.wfile = DisconnectedWriter()
            handler.send_response = lambda _status: None
            handler.send_header = lambda _name, _value: None
            handler.end_headers = lambda: None
            handler._send_file(audio)

    def test_state_update_response_has_utc_saved_at(self):
        with tempfile.TemporaryDirectory() as folder:
            store = _make_store(Path(folder), mode="mixed")
            result = PodcastService(store).update_state(
                {"revision": 0, "selectedWordIds": [], "speakerNames": {"speaker-01": "嘉宾一"}}
            )
        self.assertEqual(result["revision"], 1)
        self.assertTrue(result["savedAt"].endswith("+00:00"))

    def test_cancel_endpoint_sets_real_cancellation_event(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = _make_store(root / "project", mode="mixed")
            server = create_server(store)
            server.service.set_status("rendering_preview", "正在生成审核试听音频。")
            server.service._pending_operations = 1
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/api/cancel",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request) as response:
                    payload = json.load(response)
                self.assertEqual(
                    payload,
                    {
                        "cancellationRequested": True,
                        "status": {"phase": "cancelling", "message": "正在取消操作。"},
                    },
                )
                self.assertTrue(server.service._cancel_event.is_set())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_cancelled_monitor_stops_preview_already_waiting_for_operation_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = _make_store(root / "project", mode="multitrack")
            service = PodcastService(store)
            plan_id = service.project_payload()["playback"]["cutPlan"]["planId"]
            monitor_started = threading.Event()
            preview_called = threading.Event()
            errors = []

            def fake_monitor(project, output, cancel_event=None):
                monitor_started.set()
                cancel_event.wait(timeout=2)
                raise_if_cancelled(cancel_event)

            def fake_preview(project, plan, output, cancel_event=None):
                preview_called.set()
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_bytes(b"preview")

            def run(action):
                try:
                    action()
                except PodcastEditorError as exc:
                    errors.append(exc.code)

            with mock.patch("podcast_editor.server.render_monitor_mix", side_effect=fake_monitor), mock.patch(
                "podcast_editor.server.render_preview", side_effect=fake_preview
            ):
                monitor_thread = threading.Thread(target=lambda: run(service.source_audio))
                preview_thread = threading.Thread(
                    target=lambda: run(lambda: service.render_preview({"revision": 0, "planId": plan_id}))
                )
                monitor_thread.start()
                self.assertTrue(monitor_started.wait(timeout=1))
                preview_thread.start()
                time.sleep(0.05)
                service.cancel({})
                monitor_thread.join(timeout=2)
                preview_thread.join(timeout=2)
                queued_preview_called = preview_called.is_set()
                preview_called.clear()
                fresh_response = service.render_preview({"revision": 0, "planId": plan_id})

        self.assertEqual(sorted(errors), ["operation_cancelled", "operation_cancelled"])
        self.assertFalse(queued_preview_called)
        self.assertTrue(preview_called.is_set())
        self.assertEqual(fresh_response["revision"], 0)

    def test_cancel_during_idle_status_gap_still_stops_queued_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = _make_store(root / "project", mode="multitrack")
            service = PodcastService(store)
            plan_id = service.project_payload()["playback"]["cutPlan"]["planId"]
            monitor_started = threading.Event()
            allow_monitor_finish = threading.Event()
            idle_gap_started = threading.Event()
            allow_lock_release = threading.Event()
            preview_called = threading.Event()
            outcomes = {}

            def fake_monitor(project, output, cancel_event=None):
                monitor_started.set()
                allow_monitor_finish.wait(timeout=2)
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_bytes(b"monitor")

            def fake_preview(project, plan, output, cancel_event=None):
                preview_called.set()
                Path(output).parent.mkdir(parents=True, exist_ok=True)
                Path(output).write_bytes(b"preview")

            original_finish = service._finish_operation

            def delayed_finish(error):
                original_finish(error)
                idle_gap_started.set()
                allow_lock_release.wait(timeout=2)

            def run(name, action):
                try:
                    outcomes[name] = action()
                except PodcastEditorError as exc:
                    outcomes[name] = exc.code

            with mock.patch("podcast_editor.server.render_monitor_mix", side_effect=fake_monitor), mock.patch(
                "podcast_editor.server.render_preview", side_effect=fake_preview
            ), mock.patch.object(
                service, "_finish_operation", side_effect=delayed_finish
            ):
                monitor_thread = threading.Thread(
                    target=lambda: run("monitor", service.source_audio)
                )
                preview_thread = threading.Thread(
                    target=lambda: run(
                        "preview", lambda: service.render_preview({"revision": 0, "planId": plan_id})
                    )
                )
                monitor_thread.start()
                self.assertTrue(monitor_started.wait(timeout=1))
                preview_thread.start()
                time.sleep(0.05)
                allow_monitor_finish.set()
                self.assertTrue(idle_gap_started.wait(timeout=1))
                cancellation = service.cancel({})
                allow_lock_release.set()
                monitor_thread.join(timeout=2)
                preview_thread.join(timeout=2)

        self.assertTrue(cancellation["cancellationRequested"])
        self.assertEqual(outcomes["preview"], "operation_cancelled")
        self.assertFalse(preview_called.is_set())
        self.assertEqual(service.status()["phase"], "cancelled")

    def test_ffmpeg_runner_terminates_process_when_cancelled(self):
        cancel_event = threading.Event()
        timer = threading.Timer(0.1, cancel_event.set)
        started = time.monotonic()
        timer.start()
        try:
            with self.assertRaises(PodcastEditorError) as raised:
                _run_ffmpeg(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    cancel_event=cancel_event,
                    timeout_seconds=5,
                    poll_interval=0.02,
                )
        finally:
            timer.cancel()
        self.assertEqual(raised.exception.code, "operation_cancelled")
        self.assertLess(time.monotonic() - started, 2)

    def test_export_removes_draft_when_cancel_arrives_before_response(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = _make_store(root / "project", mode="mixed")
            draft_root = root / "drafts"
            draft_root.mkdir()
            service = PodcastService(store, draft_root=draft_root)
            plan_id = service.project_payload()["playback"]["cutPlan"]["planId"]

            def fake_export(project, plan, output_root, draft_name=None, cancel_event=None):
                draft_path = Path(output_root) / "partial-draft"
                draft_path.mkdir()
                cancel_event.set()
                return "partial-draft", draft_path

            with mock.patch("podcast_editor.server.export_jianying_draft", side_effect=fake_export):
                with self.assertRaises(PodcastEditorError) as raised:
                    service.export({"revision": 0, "planId": plan_id})
        self.assertEqual(raised.exception.code, "operation_cancelled")
        self.assertFalse((draft_root / "partial-draft").exists())
        self.assertEqual(service.status()["phase"], "cancelled")

    def test_missing_project_http_error_does_not_expose_absolute_path(self):
        with tempfile.TemporaryDirectory() as folder:
            project_root = Path(folder) / "private" / "project"
            server = create_server(ProjectStore(project_root))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{server.server_address[1]}/api/project"
                    )
                payload = json.loads(raised.exception.read().decode("utf-8"))
                raised.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
        self.assertEqual(payload["error"]["code"], "project_not_found")
        self.assertNotIn(str(project_root), json.dumps(payload, ensure_ascii=False))

    def test_missing_draft_root_http_error_does_not_expose_absolute_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            private_root = root / "private" / "drafts"
            store = _make_store(root / "project", mode="mixed")
            server = create_server(store, draft_root=private_root)
            cut_plan = server.service.project_payload()["playback"]["cutPlan"]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{server.server_address[1]}/api/export",
                    data=json.dumps({"revision": 0, "planId": cut_plan["planId"]}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(request)
                payload = json.loads(raised.exception.read().decode("utf-8"))
                raised.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
        self.assertEqual(payload["error"]["code"], "draft_root_not_found")
        self.assertNotIn(str(private_root), json.dumps(payload, ensure_ascii=False))

    def test_default_static_routes_serve_review_page_css_and_js(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "a.wav"
            audio.write_bytes(b"audio")
            store = _make_store(root / "project", mode="mixed", source_paths=[str(audio)])
            server = create_server(store)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urllib.request.urlopen(base + "/") as response:
                    html = response.read().decode("utf-8")
                    self.assertEqual(response.headers.get_content_type(), "text/html")
                with urllib.request.urlopen(base + "/assets/review.css") as response:
                    css = response.read().decode("utf-8")
                    self.assertEqual(response.headers.get_content_type(), "text/css")
                with urllib.request.urlopen(base + "/assets/review.js") as response:
                    javascript = response.read().decode("utf-8")
                    self.assertIn("javascript", response.headers.get_content_type())
                self.assertIn('/assets/review.css', html)
                self.assertIn('/assets/review.js', html)
                self.assertIn(".app-shell", css)
                self.assertIn('"use strict"', javascript)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_seed_selection_cli_validates_and_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = _make_store(root / "project", mode="mixed")
            command = [
                sys.executable,
                str(SCRIPT_DIR / "podcast_editor.py"),
                "seed-selection",
                "--project",
                str(store.root),
                "--word-id",
                "word-0000001",
            ]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            saved = store.load_state()
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["selectedWordIds"], ["word-0000001"])
        self.assertEqual(store.state_path.name, "review-state.json")

    def test_cli_checks_python_version_before_backend_imports(self):
        source = (SCRIPT_DIR / "podcast_editor.py").read_text(encoding="utf-8")
        self.assertLess(source.index("sys.version_info < (3, 10)"), source.index("from podcast_editor"))

    def test_project_groups_words_under_stable_utterances(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "mix.mp3"
            audio.write_bytes(b"audio")
            result = {
                "result": {
                    "utterances": [
                        {"additions": {"speaker": "A"}, "words": [
                            {"text": "你", "start_time": 0, "end_time": 100},
                            {"text": "好", "start_time": 100, "end_time": 200},
                        ]}
                    ]
                }
            }
            store = prepare_project(
                [audio], Path(folder) / "work", transcriber=FakeTranscriber([result]),
                probes=[AudioProbe(1000, 1.0, "mp3", 1000)],
            )
            project = store.load_project()
        self.assertEqual(len(project["utterances"]), 1)
        self.assertEqual([word["text"] for word in project["utterances"][0]["words"]], ["你", "好"])

    @unittest.skipUnless(
        _package_version("pyJianYingDraft") == "0.3.0", "pyJianYingDraft 0.3.0 is not installed"
    )
    def test_actual_pyjianyingdraft_audio_only_multisegment_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "source.wav"
            with wave.open(str(audio), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(b"\x00\x00" * 8000)
            store = _make_store(root / "project", mode="mixed", source_paths=[str(audio)])
            project = store.load_project()
            state = store.load_state(project)
            state["selectedWordIds"] = ["word-0000001"]
            plan = build_cut_plan(project, state)
            draft_root = root / "drafts"
            draft_root.mkdir()
            _, draft_path = export_jianying_draft(project, plan, draft_root, draft_name="audio-test")
            content = json.loads((draft_path / "draft_content.json").read_text(encoding="utf-8"))
        self.assertEqual([track["type"] for track in content["tracks"]], ["audio"])
        self.assertEqual(len(content["tracks"][0]["segments"]), 2)
        material_paths = {
            item["id"]: str(Path(item["path"]).resolve()) for item in content["materials"]["audios"]
        }
        for segment_json, segment_plan in zip(
            content["tracks"][0]["segments"], plan.tracks[0].segments, strict=True
        ):
            duration_us = (segment_plan.source_end_ms - segment_plan.source_start_ms) * 1000
            self.assertEqual(
                segment_json["source_timerange"],
                {"start": segment_plan.source_start_ms * 1000, "duration": duration_us},
            )
            self.assertEqual(
                segment_json["target_timerange"],
                {"start": segment_plan.target_start_ms * 1000, "duration": duration_us},
            )
            self.assertEqual(material_paths[segment_json["material_id"]], str(audio.resolve()))


def _make_store(
    root: Path,
    *,
    mode: str,
    overlap: bool = False,
    source_paths=None,
    two_speakers: bool = False,
) -> ProjectStore:
    speakers = [{"id": "speaker-01", "name": "嘉宾一", "sourceIndex": None if mode == "mixed" else 0}]
    if source_paths is None:
        root.parent.mkdir(parents=True, exist_ok=True)
        generated = [root.parent / "a.wav", root.parent / "b.wav"]
        frames = b"\x00\x00" * 800 + b"\x10\x27" * 800 + b"\x00\x00" * 800
        frames += b"\x10\x27" * 800 + b"\x00\x00" * 4800
        for path in generated:
            with wave.open(str(path), "wb") as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(8000)
                stream.writeframes(frames)
        source_paths = [str(path) for path in generated]
    sources = [{"id": "source-01", "path": source_paths[0], "durationMs": 1000, "frameDurationMs": 1.0, "speakerId": None if mode == "mixed" else "speaker-01"}]
    utterances = [{"id": "u1", "speakerId": "speaker-01", "startMs": 100, "endMs": 200, "words": [{"id": "word-0000001", "text": "嗯", "startMs": 100, "endMs": 200}]}]
    if mode == "mixed" and two_speakers:
        speakers.append({"id": "speaker-02", "name": "嘉宾二", "sourceIndex": None})
        utterances.append({"id": "u2", "speakerId": "speaker-01", "startMs": 300, "endMs": 400, "words": [{"id": "word-0000002", "text": "好", "startMs": 300, "endMs": 400}]})
    if mode == "multitrack":
        speakers.append({"id": "speaker-02", "name": "嘉宾二", "sourceIndex": 1})
        sources.append({"id": "source-02", "path": source_paths[1], "durationMs": 1000, "frameDurationMs": 1.0, "speakerId": "speaker-02"})
        utterances.append({"id": "u2", "speakerId": "speaker-02", "startMs": 150 if overlap else 300, "endMs": 250 if overlap else 400, "words": [{"id": "word-0000002", "text": "好", "startMs": 150 if overlap else 300, "endMs": 250 if overlap else 400}]})
    project = {"schemaVersion": 1, "id": "test", "name": "test", "title": "test", "mode": mode, "durationMs": 1000, "createdAt": "now", "sources": sources, "speakers": speakers, "utterances": utterances}
    state = {"revision": 0, "selectedWordIds": [], "speakerNames": {speaker["id"]: speaker["name"] for speaker in speakers}}
    store = ProjectStore(root)
    store.create(project, state)
    return store


if __name__ == "__main__":
    unittest.main()
