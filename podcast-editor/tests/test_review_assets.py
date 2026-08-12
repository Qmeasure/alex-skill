import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "assets" / "review.html").read_text(encoding="utf-8")
CSS = (ROOT / "assets" / "review.css").read_text(encoding="utf-8")
JS = (ROOT / "assets" / "review.js").read_text(encoding="utf-8")


class ReviewAssetTests(unittest.TestCase):
    def test_assets_do_not_load_external_resources(self):
        combined = "\n".join((HTML, CSS, JS))
        self.assertNotRegex(combined, r"https?://")
        self.assertNotIn("url(", CSS.lower())

    def test_page_uses_required_endpoints(self):
        for endpoint in (
            "/api/project",
            "/api/state",
            "/api/waveform",
            "/api/preview",
            "/api/export",
            "/api/cancel",
        ):
            self.assertIn(endpoint, JS)

    def test_state_save_carries_revision_and_user_edits(self):
        save_payload = re.search(r"function savePayload\(\).*?\n  }", JS, re.S)
        self.assertIsNotNone(save_payload)
        payload_text = save_payload.group(0)
        self.assertIn("revision", payload_text)
        self.assertIn("selectedWordIds", payload_text)
        self.assertIn("speakerNames", payload_text)
        self.assertIn("speakerOverrides", payload_text)
        self.assertIn("cutOverrides", payload_text)

    def test_page_validates_and_installs_authoritative_playback(self):
        self.assertIn("function isCutPlan", JS)
        self.assertIn("function installPlayback", JS)
        self.assertIn("payload.playback.cutPlan", JS)
        self.assertIn("plan.timeline", JS)
        self.assertIn("savedVersion !== state.mutationVersion", JS)
        self.assertIn("deletion.canCut", JS)
        self.assertIn('playback.strategy !== "dual-audio-preload-v1"', JS)
        self.assertIn("state.playbackRuns = playback.runs", JS)

    def test_preview_and_export_send_revision_and_plan_id(self):
        preview_function = re.search(r"async function buildPreview\(\).*?\n  }", JS, re.S)
        export_function = re.search(r"async function exportDraft\(\).*?\n  }", JS, re.S)
        self.assertIsNotNone(preview_function)
        self.assertIsNotNone(export_function)
        for function in (preview_function.group(0), export_function.group(0)):
            self.assertIn("revision: state.revision", function)
            self.assertIn("planId: state.cutPlan.planId", function)

    def test_live_cut_uses_two_preloaded_decks_without_seek_fallback(self):
        self.assertIn('id="liveDeckA"', HTML)
        self.assertIn('id="liveDeckB"', HTML)
        self.assertIn("createMediaElementSource", JS)
        self.assertIn("createGain", JS)
        self.assertIn("linearRampToValueAtTime", JS)
        self.assertIn("const seekReady = waitForMedia(", JS)
        self.assertIn('"seeked"', JS)
        self.assertIn('waitForMedia(audio, "loadeddata"', JS)
        self.assertIn('waitForMedia(audio, "canplay"', JS)
        self.assertIn("function handoffDecks", JS)
        self.assertIn("function runSourceGate", JS)
        self.assertIn("sourceGate.waiting", JS)
        self.assertIn("sourceMs >= run.sourceEndMs", JS)
        self.assertIn("measuredOvershoot > 20", JS)
        self.assertIn("generation !== state.deckGeneration", JS)
        self.assertIn("run.sources.map", JS)
        self.assertIn('setDeckState(deck, "preparing")', JS)
        self.assertIn('setDeckState(deck, "ready")', JS)
        self.assertIn('setDeckState(deck, "starting")', JS)
        self.assertIn('setDeckState(deck, "playing")', JS)
        self.assertIn('setDeckState(oldDeck, "switching")', JS)
        self.assertIn('setDeckState(deck, "error")', JS)
        self.assertNotIn("window.setTimeout(finish, 160)", JS)
        self.assertNotIn("window.setTimeout(finish, 220)", JS)

    def test_playback_contract_rejects_stale_or_malformed_runs(self):
        self.assertIn("function validatePlaybackContract", JS)
        self.assertIn("playback.revision !== expectedRevision", JS)
        self.assertIn("playback.planId !== playback.cutPlan.planId", JS)
        self.assertIn("!timelinesEqual(playback.timeline, playback.cutPlan.timeline)", JS)
        self.assertIn("playback.runs.length !== playback.timeline.segments.length", JS)
        self.assertIn("previousRun.targetEndMs === run.targetStartMs", JS)

    def test_live_playback_requires_audio_context_but_exact_preview_does_not(self):
        self.assertIn("浏览器无法启用无缝试听，请使用“生成精确试听”", JS)
        preview_function = re.search(r"async function togglePlayback\(\).*?\n  }", JS, re.S)
        self.assertIsNotNone(preview_function)

    def test_export_waits_for_autosave(self):
        export_function = re.search(r"async function exportDraft\(\).*?\n  }", JS, re.S)
        self.assertIsNotNone(export_function)
        body = export_function.group(0)
        self.assertLess(body.index("await flushSave()"), body.index('request("/api/export"'))

    def test_interface_has_expected_review_controls(self):
        for element_id in (
            "playButton",
            "interactionModeButton",
            "interactionModeText",
            "nowSpeaker",
            "nowCaption",
            "undoButton",
            "redoButton",
            "speakerFilters",
            "speakerEditors",
            "transcript",
            "previewButton",
            "exportButton",
            "waveformViewport",
            "waveformCanvas",
            "waveformZoomOut",
            "waveformZoomIn",
            "waveformResetView",
            "cutStartHandle",
            "cutEndHandle",
            "cutResetButton",
        ):
            self.assertIn(f'id="{element_id}"', HTML)

    def test_toolbar_is_sticky_and_modes_have_separate_word_actions(self):
        self.assertIn('class="workspace-toolbar"', HTML)
        self.assertRegex(CSS, r"\.workspace-toolbar\s*\{[^}]*position:\s*sticky", re.S)
        self.assertIn('interactionMode: "play"', JS)
        self.assertIn('state.interactionMode === "play"', JS)
        self.assertIn('state.interactionMode !== "edit"', JS)
        self.assertIn('seekFromTranscript(Number(wordElement.dataset.startMs), true)', JS)

    def test_waveform_does_not_cover_audio_with_usage_instructions(self):
        self.assertNotIn('id="waveformEmpty"', HTML)
        self.assertNotIn("在逐字稿中点击", HTML)
        self.assertNotIn("在波形中点击", HTML)

    def test_waveform_controls_are_wired_to_real_data_and_overrides(self):
        self.assertIn('request(`/api/waveform?', JS)
        self.assertIn("state.cutOverrides", JS)
        self.assertIn("waveformDrag", JS)
        for element_name in (
            "waveformViewport",
            "waveformZoomOut",
            "waveformZoomIn",
            "waveformResetView",
            "cutStartHandle",
            "cutEndHandle",
            "cutResetButton",
        ):
            self.assertRegex(JS, rf"elements\.{element_name}\.addEventListener")

    def test_no_fake_percentage_progress(self):
        combined = "\n".join((HTML, JS))
        self.assertNotRegex(combined, r"\b(?:percent|percentage)\b")
        self.assertNotRegex(combined, r"\d+%")

    def test_page_exit_notifies_backend_before_aborting(self):
        pagehide_handler = re.search(r'addEventListener\("pagehide".*?\n    \}\);', JS, re.S)
        self.assertIsNotNone(pagehide_handler)
        handler_text = pagehide_handler.group(0)
        self.assertIn('sendBeacon(', handler_text)
        self.assertIn('"/api/cancel"', handler_text)
        self.assertLess(handler_text.index("sendBeacon("), handler_text.index("operationController.abort()"))
        self.assertLess(handler_text.index("sendBeacon("), handler_text.index("if (state.operationController)"))


if __name__ == "__main__":
    unittest.main()
