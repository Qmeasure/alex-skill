(function () {
  "use strict";

  const SPEAKER_COLORS = ["#18794e", "#a05c17", "#256aa3", "#934b75", "#5d6d2e", "#8a4d38"];
  const SAVE_DELAY_MS = 420;
  const SHORT_REQUEST_TIMEOUT_MS = 30_000;
  const CANCEL_REQUEST_TIMEOUT_MS = 15_000;
  const LONG_REQUEST_TIMEOUT_MS = 2 * 60 * 60 * 1000;
  const DECK_HANDOFF_SECONDS = 0.005;
  const MAX_PRE_ROLL_MS = 100;
  const DECK_READY_TIMEOUT_MS = 15_000;

  const elements = {
    shell: document.querySelector(".app-shell"),
    projectTitle: document.querySelector("#projectTitle"),
    saveStatus: document.querySelector("#saveStatus"),
    saveStatusText: document.querySelector("#saveStatusText"),
    retrySaveButton: document.querySelector("#retrySaveButton"),
    previewButton: document.querySelector("#previewButton"),
    cancelButton: document.querySelector("#cancelButton"),
    exportButton: document.querySelector("#exportButton"),
    playButton: document.querySelector("#playButton"),
    interactionModeButton: document.querySelector("#interactionModeButton"),
    interactionModeText: document.querySelector("#interactionModeText"),
    nowSpeaker: document.querySelector("#nowSpeaker"),
    nowCaption: document.querySelector("#nowCaption"),
    seekSlider: document.querySelector("#seekSlider"),
    currentTime: document.querySelector("#currentTime"),
    durationTime: document.querySelector("#durationTime"),
    audio: document.querySelector("#audioPlayer"),
    liveDecks: document.querySelector("#liveDecks"),
    liveDeckA: document.querySelector("#liveDeckA"),
    liveDeckB: document.querySelector("#liveDeckB"),
    undoButton: document.querySelector("#undoButton"),
    redoButton: document.querySelector("#redoButton"),
    speakerFilters: document.querySelector("#speakerFilters"),
    speakerEditors: document.querySelector("#speakerEditors"),
    transcript: document.querySelector("#transcript"),
    selectionSummary: document.querySelector("#selectionSummary"),
    waveformPanel: document.querySelector("#waveformPanel"),
    waveformViewport: document.querySelector("#waveformViewport"),
    waveformCanvas: document.querySelector("#waveformCanvas"),
    waveformRange: document.querySelector("#waveformRange"),
    cutSelector: document.querySelector("#cutSelector"),
    waveformRawRange: document.querySelector("#waveformRawRange"),
    waveformActualRange: document.querySelector("#waveformActualRange"),
    waveformZoomOut: document.querySelector("#waveformZoomOut"),
    waveformZoomIn: document.querySelector("#waveformZoomIn"),
    waveformResetView: document.querySelector("#waveformResetView"),
    cutResetButton: document.querySelector("#cutResetButton"),
    cutStartHandle: document.querySelector("#cutStartHandle"),
    cutEndHandle: document.querySelector("#cutEndHandle"),
    boundaryWarning: document.querySelector("#boundaryWarning"),
    exportResult: document.querySelector("#exportResult"),
    exportName: document.querySelector("#exportName"),
    exportPath: document.querySelector("#exportPath")
  };

  const state = {
    project: null,
    reviewTurns: [],
    utteranceTurnIds: {},
    playbackUrl: "",
    originalPlaybackUrl: "",
    liveTimeline: null,
    cutPlan: null,
    cutOverrides: {},
    previewTimeline: null,
    playbackMode: "live",
    interactionMode: "play",
    playbackFrame: null,
    previewUtterances: null,
    revision: 0,
    selectedWordIds: new Set(),
    speakerNames: {},
    speakerOverrides: {},
    activeSpeakerId: "all",
    history: [],
    future: [],
    mutationVersion: 0,
    savedMutationVersion: 0,
    saveTimer: null,
    saveRequested: false,
    savePromise: null,
    lastSaveFailed: false,
    activeUtteranceIds: new Set(),
    previewBusy: false,
    exportBusy: false,
    operationPhase: null,
    operationController: null,
    operationCancelled: false,
    cancelBusy: false,
    pendingSeekMs: null,
    pendingSeekBound: false,
    audioContext: null,
    playbackStrategy: "",
    playbackRuns: [],
    deckGeneration: 0,
    decks: [],
    activeDeckIndex: 0,
    activeRunIndex: -1,
    livePlaying: false,
    deckError: null,
    playbackSources: [],
    masterMuted: false,
    timelineEdit: null,
    selectedDeletionId: null,
    focusWordId: null,
    waveformStartMs: 0,
    waveformEndMs: 0,
    waveformPoints: [],
    waveformRequestVersion: 0,
    waveformSourceId: null
  };

  const drag = {
    active: false,
    targetSelected: false,
    visited: new Set(),
    changed: false,
    started: false,
    originElement: null
  };

  const waveformDrag = {
    active: false,
    mode: null,
    pointerId: null,
    originX: 0,
    originStartMs: 0,
    originEndMs: 0,
    deletion: null,
    historySnapshot: null
  };

  function setStatus(kind, message, canRetry) {
    elements.saveStatus.dataset.state = kind;
    elements.saveStatusText.textContent = message;
    elements.retrySaveButton.hidden = !canRetry;
  }

  function parseErrorPayload(payload, fallback) {
    if (payload && payload.error && payload.error.message) {
      return payload.error.message;
    }
    return fallback;
  }

  async function request(path, options) {
    const config = Object.assign({ headers: {} }, options || {});
    const timeoutMs = config.timeoutMs || SHORT_REQUEST_TIMEOUT_MS;
    const externalSignal = config.signal || null;
    delete config.timeoutMs;
    delete config.signal;

    const controller = new AbortController();
    let timedOut = false;
    const abortFromExternalSignal = () => controller.abort(externalSignal.reason);
    if (externalSignal) {
      if (externalSignal.aborted) {
        controller.abort(externalSignal.reason);
      } else {
        externalSignal.addEventListener("abort", abortFromExternalSignal, { once: true });
      }
    }
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    config.signal = controller.signal;

    if (config.body !== undefined) {
      config.headers = Object.assign({ "Content-Type": "application/json" }, config.headers);
      if (typeof config.body !== "string") {
        config.body = JSON.stringify(config.body);
      }
    }

    try {
      const response = await fetch(path, config);
      let payload = null;
      const responseText = await response.text();
      if (responseText) {
        try {
          payload = JSON.parse(responseText);
        } catch (_error) {
          payload = null;
        }
      }

      if (!response.ok) {
        const error = new Error(parseErrorPayload(payload, `请求失败（${response.status}）`));
        error.status = response.status;
        error.code = payload && payload.error ? payload.error.code : "HTTP_ERROR";
        error.details = payload && payload.error ? payload.error.details : null;
        throw error;
      }
      return payload || {};
    } catch (error) {
      if (error.name === "AbortError") {
        const abortedError = new Error(timedOut ? "请求超时" : "请求已取消");
        abortedError.code = timedOut ? "REQUEST_TIMEOUT" : "CLIENT_ABORTED";
        throw abortedError;
      }
      if (error.status || error.code) {
        throw error;
      }
      const networkError = new Error("无法连接本地服务");
      networkError.cause = error;
      throw networkError;
    } finally {
      window.clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener("abort", abortFromExternalSignal);
      }
    }
  }

  function normalizedSpeakerNames(project, savedNames) {
    const names = {};
    project.speakers.forEach((speaker, index) => {
      names[speaker.id] = speaker.name || `嘉宾${index + 1}`;
    });
    if (savedNames && typeof savedNames === "object") {
      Object.entries(savedNames).forEach(([speakerId, name]) => {
        if (typeof name === "string" && name.trim()) {
          names[speakerId] = name.trim();
        }
      });
    }
    return names;
  }

  function speakerName(speakerId) {
    return state.speakerNames[speakerId] || "未识别嘉宾";
  }

  function effectiveSpeakerId(utterance) {
    return state.speakerOverrides[utterance.id] || utterance.speakerId;
  }

  function speakerColor(speakerId) {
    const index = state.project.speakers.findIndex((speaker) => speaker.id === speakerId);
    return SPEAKER_COLORS[(index < 0 ? 0 : index) % SPEAKER_COLORS.length];
  }

  function formatTime(milliseconds) {
    const totalSeconds = Math.max(0, Math.floor((Number(milliseconds) || 0) / 1000));
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    if (hours) {
      return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function wordCountLabel() {
    elements.selectionSummary.textContent = `已划掉 ${state.selectedWordIds.size} 字`;
  }

  function setInteractionMode(mode) {
    state.interactionMode = mode === "edit" ? "edit" : "play";
    const editing = state.interactionMode === "edit";
    elements.interactionModeButton.setAttribute("aria-pressed", String(editing));
    elements.interactionModeButton.title = editing ? "当前为编辑模式" : "当前为播放模式";
    elements.interactionModeText.textContent = editing ? "编辑模式" : "播放模式";
    elements.interactionModeButton.querySelector(".mode-icon").innerHTML = editing ? "&#9998;" : "&#9654;";
    elements.transcript.dataset.interactionMode = state.interactionMode;
    syncWordSelectionClasses();
  }

  function snapshot() {
    return {
      selectedWordIds: Array.from(state.selectedWordIds),
      speakerNames: Object.assign({}, state.speakerNames),
      speakerOverrides: Object.assign({}, state.speakerOverrides),
      cutOverrides: JSON.parse(JSON.stringify(state.cutOverrides))
    };
  }

  function pushHistory(savedSnapshot) {
    state.history.push(savedSnapshot || snapshot());
    if (state.history.length > 100) {
      state.history.shift();
    }
    state.future = [];
    updateHistoryButtons();
  }

  function restoreSnapshot(savedSnapshot) {
    const selectionChanged = !setsEqual(state.selectedWordIds, new Set(savedSnapshot.selectedWordIds));
    const cutsChanged = JSON.stringify(state.cutOverrides) !== JSON.stringify(savedSnapshot.cutOverrides || {});
    state.selectedWordIds = new Set(savedSnapshot.selectedWordIds);
    state.speakerNames = Object.assign({}, savedSnapshot.speakerNames);
    state.speakerOverrides = Object.assign({}, savedSnapshot.speakerOverrides || {});
    state.cutOverrides = selectionChanged
      ? {}
      : JSON.parse(JSON.stringify(savedSnapshot.cutOverrides || {}));
    if (selectionChanged || cutsChanged) {
      resetPreviewAfterWordEdit();
    }
    syncWordSelectionClasses();
    syncSpeakerNames();
    wordCountLabel();
    renderNowPlaying();
    markChanged(true);
  }

  function undo() {
    if (!state.history.length || isBusy()) {
      return;
    }
    state.future.push(snapshot());
    restoreSnapshot(state.history.pop());
    updateHistoryButtons();
  }

  function redo() {
    if (!state.future.length || isBusy()) {
      return;
    }
    state.history.push(snapshot());
    restoreSnapshot(state.future.pop());
    updateHistoryButtons();
  }

  function updateHistoryButtons() {
    elements.undoButton.disabled = !state.history.length || isBusy();
    elements.redoButton.disabled = !state.future.length || isBusy();
  }

  function isBusy() {
    return state.previewBusy || state.exportBusy;
  }

  function setActionButtons() {
    const ready = Boolean(state.project);
    const blocked = hasUncuttableDeletions();
    const blockedMessage = blocked ? cutBlockMessage() : "";
    elements.previewButton.disabled = !ready || blocked || isBusy();
    elements.exportButton.disabled = !ready || blocked || isBusy();
    elements.previewButton.title = blockedMessage;
    elements.exportButton.title = blockedMessage;
    elements.cancelButton.hidden = !isBusy();
    elements.cancelButton.disabled = !isBusy() || state.cancelBusy;
    updateHistoryButtons();
  }

  function markChanged(immediate) {
    state.mutationVersion += 1;
    scheduleSave(immediate ? 0 : SAVE_DELAY_MS);
  }

  function scheduleSave(delayMs) {
    state.saveRequested = true;
    state.lastSaveFailed = false;
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(() => {
      drainSaveQueue().catch(() => {});
    }, delayMs);
  }

  function savePayload() {
    return {
      revision: state.revision,
      selectedWordIds: Array.from(state.selectedWordIds),
      speakerNames: Object.assign({}, state.speakerNames),
      speakerOverrides: Object.assign({}, state.speakerOverrides),
      cutOverrides: JSON.parse(JSON.stringify(state.cutOverrides))
    };
  }

  async function drainSaveQueue() {
    if (state.savePromise) {
      return state.savePromise;
    }

    state.savePromise = (async () => {
      while (state.saveRequested) {
        state.saveRequested = false;
        window.clearTimeout(state.saveTimer);
        const savedVersion = state.mutationVersion;
        setStatus("saving", "正在保存", false);
        try {
          const result = await request("/api/state", {
            method: "PUT",
            body: savePayload()
          });
          if (!result.state || typeof result.state.revision !== "number") {
            throw new Error("保存结果缺少版本号");
          }
          state.revision = result.state.revision;
          if (!isCutPlan(result.cutPlan)) {
            throw new Error("保存结果缺少切割计划");
          }
          if (state.mutationVersion === savedVersion) {
            state.speakerOverrides = Object.assign({}, result.state.speakerOverrides || {});
            state.cutOverrides = JSON.parse(JSON.stringify(result.state.cutOverrides || result.cutOverrides || {}));
            if (result.project && Array.isArray(result.reviewTurns)) {
              state.project = result.project;
              setReviewTurns(result.reviewTurns);
              renderTranscript();
            }
            if (!installPlayback(result.playback, savedVersion)) {
              throw new Error("保存结果中的播放计划不一致");
            }
          }
          state.savedMutationVersion = savedVersion;
          state.lastSaveFailed = false;
          if (state.mutationVersion === savedVersion && !state.saveRequested) {
            setCutReadyStatus("已保存");
          }
        } catch (error) {
          state.lastSaveFailed = true;
          state.saveRequested = false;
          if (error.status === 409) {
            setStatus("error", "内容版本已变化，请刷新页面", false);
          } else {
            setStatus("error", error.message || "保存失败", true);
          }
          throw error;
        }
      }
    })();

    try {
      await state.savePromise;
    } finally {
      state.savePromise = null;
      if (state.saveRequested && !state.lastSaveFailed) {
        return drainSaveQueue();
      }
    }
  }

  async function flushSave() {
    window.clearTimeout(state.saveTimer);
    if (state.savedMutationVersion !== state.mutationVersion) {
      state.saveRequested = true;
    }
    if (state.saveRequested || state.savePromise) {
      await drainSaveQueue();
    }
  }

  function makeButton(label, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    return button;
  }

  function setReviewTurns(turns) {
    state.reviewTurns = turns;
    state.utteranceTurnIds = {};
    turns.forEach((turn) => {
      turn.utteranceIds.forEach((utteranceId) => {
        state.utteranceTurnIds[utteranceId] = turn.id;
      });
    });
  }

  function renderSpeakerControls() {
    elements.speakerFilters.replaceChildren();
    elements.speakerEditors.replaceChildren();

    const allButton = makeButton("全部", "filter-button");
    allButton.dataset.speakerFilter = "all";
    allButton.setAttribute("aria-pressed", String(state.activeSpeakerId === "all"));
    elements.speakerFilters.appendChild(allButton);

    state.project.speakers.forEach((speaker) => {
      const filter = makeButton(speakerName(speaker.id), "filter-button");
      filter.dataset.speakerFilter = speaker.id;
      filter.dataset.speakerName = speaker.id;
      filter.setAttribute("aria-pressed", String(state.activeSpeakerId === speaker.id));
      elements.speakerFilters.appendChild(filter);

      const editor = document.createElement("label");
      editor.className = "speaker-editor";
      editor.style.setProperty("--speaker-color", speakerColor(speaker.id));

      const hiddenLabel = document.createElement("span");
      hiddenLabel.className = "sr-only";
      hiddenLabel.textContent = `修改${speakerName(speaker.id)}的名称`;

      const swatch = document.createElement("span");
      swatch.className = "speaker-swatch";
      swatch.setAttribute("aria-hidden", "true");

      const input = document.createElement("input");
      input.type = "text";
      input.maxLength = 40;
      input.value = speakerName(speaker.id);
      input.dataset.speakerInput = speaker.id;
      input.setAttribute("aria-label", `修改${speakerName(speaker.id)}的名称`);

      editor.append(hiddenLabel, swatch, input);
      elements.speakerEditors.appendChild(editor);
    });
  }

  function renderTranscript() {
    const fragment = document.createDocumentFragment();
    const utteranceById = new Map(state.project.utterances.map((utterance) => [utterance.id, utterance]));
    state.reviewTurns.forEach((turn) => {
      const section = document.createElement("section");
      section.className = "utterance";
      section.dataset.turnId = turn.id;
      section.dataset.utteranceId = turn.utteranceIds[0];
      section.dataset.speakerId = turn.speakerId;
      section.style.setProperty("--speaker-color", speakerColor(turn.speakerId));

      const meta = document.createElement("div");
      meta.className = "utterance-meta";

      const speaker = document.createElement("select");
      speaker.className = "utterance-speaker";
      speaker.dataset.turnSpeaker = turn.id;
      speaker.dataset.utteranceIds = JSON.stringify(turn.utteranceIds);
      speaker.setAttribute("aria-label", `修改 ${formatTime(turn.startMs)} 发言的嘉宾`);
      state.project.speakers.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = speakerName(item.id);
        option.dataset.speakerOption = item.id;
        speaker.appendChild(option);
      });
      speaker.value = turn.speakerId;

      const seek = makeButton(formatTime(turn.startMs), "utterance-seek");
      seek.dataset.seekMs = String(turn.startMs);
      seek.title = `从 ${formatTime(turn.startMs)} 播放`;

      const words = document.createElement("div");
      words.className = "words";
      words.dataset.wordList = turn.id;
      turn.utteranceIds.forEach((utteranceId) => {
        const utterance = utteranceById.get(utteranceId);
        if (!utterance) {
          return;
        }
        utterance.words.forEach((word) => {
          const wordButton = makeButton(word.text, "word");
          wordButton.dataset.wordId = word.id;
          wordButton.dataset.startMs = String(word.startMs);
          wordButton.dataset.endMs = String(word.endMs);
          const selected = state.selectedWordIds.has(word.id);
          wordButton.classList.toggle("is-selected", selected);
          wordButton.setAttribute("aria-pressed", String(selected));
          wordButton.title = state.interactionMode === "edit"
            ? (selected ? "保留这个字词" : "划掉这个字词")
            : "从这个字词开始播放";
          words.appendChild(wordButton);
          if (word.punctuationAfter) {
            const punctuation = document.createElement("span");
            punctuation.className = "punctuation";
            punctuation.textContent = word.punctuationAfter;
            punctuation.setAttribute("aria-hidden", "true");
            words.appendChild(punctuation);
          }
        });
      });

      meta.append(speaker, seek);
      section.append(meta, words);
      fragment.appendChild(section);
    });

    elements.transcript.replaceChildren(fragment);
    applySpeakerFilter();
    wordCountLabel();
  }

  function syncWordSelectionClasses() {
    elements.transcript.querySelectorAll("[data-word-id]").forEach((wordElement) => {
      const selected = state.selectedWordIds.has(wordElement.dataset.wordId);
      wordElement.classList.toggle("is-selected", selected);
      wordElement.setAttribute("aria-pressed", String(selected));
      wordElement.title = state.interactionMode === "edit"
        ? (selected ? "保留这个字词" : "划掉这个字词")
        : "从这个字词开始播放";
    });
  }

  function syncSpeakerNames() {
    document.querySelectorAll("[data-speaker-name]").forEach((nameElement) => {
      nameElement.textContent = speakerName(nameElement.dataset.speakerName);
    });
    elements.speakerEditors.querySelectorAll("[data-speaker-input]").forEach((input) => {
      if (document.activeElement !== input) {
        input.value = speakerName(input.dataset.speakerInput);
      }
      input.setAttribute("aria-label", `修改${speakerName(input.dataset.speakerInput)}的名称`);
    });
    elements.transcript.querySelectorAll("[data-speaker-option]").forEach((option) => {
      option.textContent = speakerName(option.dataset.speakerOption);
    });
    renderNowPlaying();
  }

  function applySpeakerFilter() {
    elements.speakerFilters.querySelectorAll("[data-speaker-filter]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.speakerFilter === state.activeSpeakerId));
    });
    elements.transcript.querySelectorAll("[data-speaker-id]").forEach((utterance) => {
      utterance.hidden = state.activeSpeakerId !== "all" && utterance.dataset.speakerId !== state.activeSpeakerId;
    });
  }

  function setWordSelected(wordId, selected) {
    const wasSelected = state.selectedWordIds.has(wordId);
    if (wasSelected === selected) {
      return false;
    }
    beginCutPlanEdit();
    state.cutOverrides = {};
    if (selected) {
      state.focusWordId = wordId;
    }
    if (selected) {
      state.selectedWordIds.add(wordId);
    } else {
      state.selectedWordIds.delete(wordId);
    }
    resetPreviewAfterWordEdit();
    const wordElement = elements.transcript.querySelector(`[data-word-id="${CSS.escape(wordId)}"]`);
    if (wordElement) {
      wordElement.classList.toggle("is-selected", selected);
      wordElement.setAttribute("aria-pressed", String(selected));
      wordElement.title = selected ? "保留这个字词" : "划掉这个字词";
    }
    wordCountLabel();
    renderNowPlaying();
    return true;
  }

  function toggleWordSelection(wordId) {
    pushHistory();
    setWordSelected(wordId, !state.selectedWordIds.has(wordId));
    markChanged(true);
  }

  function startWordDrag(event, wordElement) {
    if (state.interactionMode !== "edit" || event.button !== 0 || isBusy()) {
      return;
    }
    event.preventDefault();
    drag.active = true;
    drag.targetSelected = !state.selectedWordIds.has(wordElement.dataset.wordId);
    drag.visited = new Set();
    drag.changed = false;
    drag.started = true;
    drag.originElement = wordElement;
    pushHistory();
    visitDraggedWord(wordElement);
  }

  function visitDraggedWord(wordElement) {
    if (!drag.active || !wordElement || !wordElement.dataset.wordId) {
      return;
    }
    if (!drag.started) {
      if (wordElement.dataset.wordId === drag.originElement.dataset.wordId) {
        return;
      }
      pushHistory();
      drag.started = true;
      const originElement = drag.originElement;
      visitDraggedWord(originElement);
    }
    const wordId = wordElement.dataset.wordId;
    if (drag.visited.has(wordId)) {
      return;
    }
    drag.visited.add(wordId);
    drag.changed = setWordSelected(wordId, drag.targetSelected) || drag.changed;
  }

  function finishWordDrag() {
    if (!drag.active) {
      return;
    }
    drag.active = false;
    if (drag.started && drag.changed) {
    markChanged(true);
    } else if (drag.started) {
      state.history.pop();
      updateHistoryButtons();
    }
    drag.started = false;
    drag.originElement = null;
  }

  function setAudioTime(milliseconds) {
    const nextMilliseconds = Math.max(0, Number(milliseconds) || 0);
    const nextSeconds = nextMilliseconds / 1000;
    if (elements.audio.readyState === 0) {
      state.pendingSeekMs = nextMilliseconds;
      if (!state.pendingSeekBound) {
        state.pendingSeekBound = true;
        elements.audio.addEventListener("loadedmetadata", () => {
          state.pendingSeekBound = false;
          const pendingMilliseconds = state.pendingSeekMs;
          state.pendingSeekMs = null;
          setAudioTime(pendingMilliseconds);
        }, { once: true });
      }
      return;
    }
    try {
      elements.audio.currentTime = nextSeconds;
    } catch (_error) {
      elements.audio.addEventListener("loadedmetadata", () => {
        elements.audio.currentTime = nextSeconds;
        updatePlaybackTime();
      }, { once: true });
    }
    updatePlaybackTime();
  }

  function isTimeline(value) {
    return Boolean(
      value
      && Number.isFinite(value.durationMs)
      && Array.isArray(value.segments)
      && value.segments.every((segment) => (
        Number.isFinite(segment.sourceStartMs)
        && Number.isFinite(segment.sourceEndMs)
        && Number.isFinite(segment.targetStartMs)
        && Number.isFinite(segment.targetEndMs)
      ))
    );
  }

  function isCutPlan(value) {
    return Boolean(
      value
      && typeof value.planId === "string"
      && Number.isFinite(value.revision)
      && Array.isArray(value.deletions)
      && value.deletions.every((deletion) => (
        typeof deletion.id === "string"
        && Number.isFinite(deletion.rawStartMs)
        && Number.isFinite(deletion.rawEndMs)
        && Number.isFinite(deletion.startMs)
        && Number.isFinite(deletion.endMs)
        && Number.isFinite(deletion.minStartMs)
        && Number.isFinite(deletion.maxEndMs)
        && typeof deletion.canCut === "boolean"
      ))
      && isTimeline(value.timeline)
      && (!value.tracks || (
        Array.isArray(value.tracks)
        && value.tracks.every((track) => (
          typeof track.sourceId === "string"
          && Array.isArray(track.segments)
          && track.segments.every((segment) => (
            Number.isFinite(segment.sourceStartMs)
            && Number.isFinite(segment.sourceEndMs)
            && Number.isFinite(segment.targetStartMs)
            && Number.isFinite(segment.targetEndMs)
          ))
        ))
      ))
    );
  }

  function uncuttableDeletions() {
    return isCutPlan(state.cutPlan)
      ? state.cutPlan.deletions.filter((deletion) => !deletion.canCut)
      : [];
  }

  function hasUncuttableDeletions() {
    return uncuttableDeletions().length > 0;
  }

  function cutBlockMessage() {
    const deletion = uncuttableDeletions()[0];
    return deletion && deletion.boundaryWarning
      ? deletion.boundaryWarning
      : "当前选词无法安全剪切，请扩大或调整选词";
  }

  function setCutReadyStatus(successMessage) {
    if (hasUncuttableDeletions()) {
      setStatus("error", cutBlockMessage(), false);
    } else {
      setStatus("success", successMessage, false);
    }
  }

  function deletionAtSource(plan, sourceMs) {
    if (!isCutPlan(plan)) {
      return null;
    }
    return plan.deletions.find((deletion) => (
      sourceMs >= deletion.startMs && sourceMs < deletion.endMs
    )) || null;
  }

  function beginCutPlanEdit() {
    if (!state.project) {
      return;
    }
    if (!state.timelineEdit) {
      state.timelineEdit = {
        logicalMs: currentLogicalMs(),
        sourceMs: state.playbackMode === "preview"
          ? targetToSource(state.liveTimeline, currentLogicalMs())
          : (() => {
              const master = deckMaster(activeDeck());
              return master ? master.currentTime * 1000 : 0;
            })(),
        resume: state.playbackMode === "preview" ? !elements.audio.paused : state.livePlaying
      };
    }
    invalidateDeckWork();
    elements.audio.dataset.cutPending = "true";
    pauseLivePlayback(true);
    if (state.playbackMode === "preview") {
      switchToLivePlayback(state.timelineEdit.logicalMs, false, true);
    }
  }

  function installPlayback(playback, savedVersion) {
    const plan = playback && playback.cutPlan;
    if (
      !isCutPlan(plan)
      || savedVersion !== state.mutationVersion
      || !validatePlaybackContract(playback, state.revision)
    ) {
      return false;
    }
    const pending = state.timelineEdit;
    state.cutPlan = plan;
    state.liveTimeline = plan.timeline;
    state.playbackStrategy = playback.strategy;
    state.playbackRuns = playback.runs;
    state.playbackSources = playback.sources || state.playbackSources;
    elements.audio.dataset.planId = plan.planId;
    elements.audio.dataset.cutPending = "false";
    state.timelineEdit = null;
    syncSelectedDeletion();
    setActionButtons();
    if (!pending) {
      return true;
    }
    const deleted = deletionAtSource(plan, pending.sourceMs);
    const logicalMs = deleted
      ? sourceToTarget(plan.timeline, deleted.endMs)
      : Math.min(pending.logicalMs, plan.timeline.durationMs);
    prepareLiveAt(logicalMs, pending.resume).catch((error) => enterDeckError(error));
    return true;
  }

  function projectWord(wordId) {
    for (const utterance of state.project.utterances) {
      const word = utterance.words.find((item) => item.id === wordId);
      if (word) {
        return word;
      }
    }
    return null;
  }

  function deletionLabel(deletion, index) {
    const first = projectWord(deletion.firstWordId);
    const last = projectWord(deletion.lastWordId);
    const text = first && last
      ? (first.id === last.id ? first.text : `${first.text}…${last.text}`)
      : `删除段 ${index + 1}`;
    return `${formatTime(deletion.rawStartMs)} ${text}`;
  }

  function sourceIdForDeletion(deletion) {
    if (!state.project || state.project.mode !== "multitrack") {
      return null;
    }
    const source = (state.project.sources || []).find((item) => (
      item.speakerId === deletion.speakerId
    ));
    const fallback = (state.project.sources || [])[0];
    return source ? source.id : (fallback ? fallback.id : null);
  }

  function selectedDeletion() {
    if (!isCutPlan(state.cutPlan)) {
      return null;
    }
    return state.cutPlan.deletions.find((deletion) => deletion.id === state.selectedDeletionId) || null;
  }

  function syncSelectedDeletion() {
    if (!isCutPlan(state.cutPlan)) {
      return;
    }
    const deletions = state.cutPlan.deletions;
    if (state.focusWordId) {
      const word = projectWord(state.focusWordId);
      const focused = word && deletions.find((deletion) => (
        word.startMs >= deletion.rawStartMs && word.endMs <= deletion.rawEndMs
      ));
      if (focused) {
        state.selectedDeletionId = focused.id;
      }
      state.focusWordId = null;
    }
    if (!deletions.some((deletion) => deletion.id === state.selectedDeletionId)) {
      state.selectedDeletionId = deletions.length ? deletions[0].id : null;
    }
    elements.cutSelector.replaceChildren();
    deletions.forEach((deletion, index) => {
      const option = document.createElement("option");
      option.value = deletion.id;
      option.textContent = deletionLabel(deletion, index);
      option.selected = deletion.id === state.selectedDeletionId;
      elements.cutSelector.appendChild(option);
    });
    elements.cutSelector.disabled = !deletions.length;
    elements.waveformZoomIn.disabled = !deletions.length;
    elements.waveformZoomOut.disabled = !deletions.length;
    elements.waveformResetView.disabled = !deletions.length;
    resetWaveformView();
  }

  function resetWaveformView() {
    const deletion = selectedDeletion();
    if (!deletion || !state.project) {
      state.waveformPoints = [];
      elements.waveformRawRange.hidden = true;
      elements.waveformActualRange.hidden = true;
      elements.cutStartHandle.disabled = true;
      elements.cutEndHandle.disabled = true;
      elements.cutResetButton.disabled = true;
      elements.boundaryWarning.hidden = true;
      drawWaveform();
      return;
    }
    const padding = Math.max(800, deletion.endMs - deletion.startMs);
    const desiredStart = Math.max(0, deletion.startMs - padding);
    const desiredEnd = Math.min(state.project.durationMs, deletion.endMs + padding);
    state.waveformStartMs = Math.max(0, desiredEnd - Math.max(2000, desiredEnd - desiredStart));
    state.waveformEndMs = Math.min(state.project.durationMs, Math.max(desiredEnd, state.waveformStartMs + 2000));
    loadWaveform();
  }

  async function loadWaveform() {
    const deletion = selectedDeletion();
    if (!deletion || state.waveformEndMs <= state.waveformStartMs) {
      return;
    }
    const requestVersion = ++state.waveformRequestVersion;
    const width = Math.max(320, Math.round(elements.waveformViewport.clientWidth || 800));
    const params = new URLSearchParams({
      startMs: String(Math.round(state.waveformStartMs)),
      endMs: String(Math.round(state.waveformEndMs)),
      points: String(Math.min(1600, Math.max(160, width)))
    });
    const sourceId = sourceIdForDeletion(deletion);
    if (sourceId) {
      params.set("sourceId", sourceId);
    }
    try {
      const result = await request(`/api/waveform?${params.toString()}`);
      if (requestVersion !== state.waveformRequestVersion || deletion.id !== state.selectedDeletionId) {
        return;
      }
      if (!Array.isArray(result.points)) {
        throw new Error("波形数据格式不正确");
      }
      state.waveformPoints = result.points;
      state.waveformSourceId = result.sourceId || sourceId;
      drawWaveform();
    } catch (error) {
      if (requestVersion !== state.waveformRequestVersion) {
        return;
      }
      state.waveformPoints = [];
      setStatus("error", error.message || "波形载入失败", false);
      drawWaveform();
    }
  }

  function waveformPercent(milliseconds) {
    const duration = state.waveformEndMs - state.waveformStartMs;
    return duration > 0 ? ((milliseconds - state.waveformStartMs) / duration) * 100 : 0;
  }

  function positionWaveformRange(element, startMs, endMs) {
    const left = Math.max(0, Math.min(100, waveformPercent(startMs)));
    const right = Math.max(0, Math.min(100, waveformPercent(endMs)));
    element.style.left = `${Math.min(left, right)}%`;
    element.style.width = `${Math.max(0, Math.abs(right - left))}%`;
    element.hidden = right <= 0 || left >= 100 || right <= left;
  }

  function drawWaveform() {
    const canvas = elements.waveformCanvas;
    const bounds = elements.waveformViewport.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(bounds.width));
    const height = Math.max(1, Math.round(bounds.height));
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    context.strokeStyle = "#c5cdc7";
    context.beginPath();
    context.moveTo(0, height / 2);
    context.lineTo(width, height / 2);
    context.stroke();
    const points = state.waveformPoints;
    if (points.length) {
      context.strokeStyle = "#345c48";
      context.lineWidth = 1;
      context.beginPath();
      points.forEach((point, index) => {
        const x = (index + 0.5) * width / points.length;
        const peak = Math.max(0, Math.min(1, Number(point.peak) || 0));
        const half = Math.max(1, peak * (height * 0.43));
        context.moveTo(x, height / 2 - half);
        context.lineTo(x, height / 2 + half);
      });
      context.stroke();
    }
    const deletion = selectedDeletion();
    if (!deletion) {
      return;
    }
    positionWaveformRange(elements.waveformRawRange, deletion.rawStartMs, deletion.rawEndMs);
    positionWaveformRange(elements.waveformActualRange, deletion.startMs, deletion.endMs);
    elements.waveformRange.textContent = `${formatTime(deletion.startMs)}.${String(deletion.startMs % 1000).padStart(3, "0")} – ${formatTime(deletion.endMs)}.${String(deletion.endMs % 1000).padStart(3, "0")}`;
    elements.cutStartHandle.disabled = !deletion.canCut;
    elements.cutEndHandle.disabled = !deletion.canCut;
    elements.cutResetButton.disabled = !deletion.canCut || deletion.boundaryMode !== "manual";
    const needsReview = Boolean(!deletion.canCut || deletion.needsReview || deletion.boundaryWarning);
    elements.boundaryWarning.hidden = !needsReview;
    if (needsReview) {
      elements.boundaryWarning.textContent = deletion.boundaryWarning || "切点需要人工复核";
    }
  }

  function changeWaveformZoom(factor) {
    const deletion = selectedDeletion();
    if (!deletion) {
      return;
    }
    const current = state.waveformEndMs - state.waveformStartMs;
    const next = Math.max(500, Math.min(state.project.durationMs, current * factor));
    const center = (deletion.startMs + deletion.endMs) / 2;
    state.waveformStartMs = Math.max(0, center - next / 2);
    state.waveformEndMs = Math.min(state.project.durationMs, state.waveformStartMs + next);
    state.waveformStartMs = Math.max(0, state.waveformEndMs - next);
    loadWaveform();
  }

  function waveformMsAt(clientX) {
    const bounds = elements.waveformViewport.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - bounds.left) / Math.max(1, bounds.width)));
    return Math.round(state.waveformStartMs + ratio * (state.waveformEndMs - state.waveformStartMs));
  }

  function startWaveformDrag(event, mode) {
    const deletion = selectedDeletion();
    if (!deletion || !deletion.canCut || event.button !== 0 || isBusy()) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    waveformDrag.active = true;
    waveformDrag.mode = mode;
    waveformDrag.pointerId = event.pointerId;
    waveformDrag.originX = event.clientX;
    waveformDrag.originStartMs = state.waveformStartMs;
    waveformDrag.originEndMs = state.waveformEndMs;
    waveformDrag.deletion = Object.assign({}, deletion);
    waveformDrag.historySnapshot = snapshot();
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function moveWaveformDrag(event) {
    if (!waveformDrag.active || event.pointerId !== waveformDrag.pointerId) {
      return;
    }
    const deletion = selectedDeletion();
    if (!deletion) {
      return;
    }
    if (waveformDrag.mode === "pan") {
      const bounds = elements.waveformViewport.getBoundingClientRect();
      const span = waveformDrag.originEndMs - waveformDrag.originStartMs;
      const delta = (event.clientX - waveformDrag.originX) / Math.max(1, bounds.width) * span;
      let start = waveformDrag.originStartMs - delta;
      start = Math.max(0, Math.min(state.project.durationMs - span, start));
      state.waveformStartMs = Math.round(start);
      state.waveformEndMs = Math.round(start + span);
      drawWaveform();
      return;
    }
    const nextMs = waveformMsAt(event.clientX);
    if (waveformDrag.mode === "start") {
      deletion.startMs = Math.max(deletion.minStartMs, Math.min(deletion.rawStartMs, nextMs));
    } else {
      deletion.endMs = Math.min(deletion.maxEndMs, Math.max(deletion.rawEndMs, nextMs));
    }
    drawWaveform();
  }

  function finishWaveformDrag(event) {
    if (!waveformDrag.active || (event && event.pointerId !== waveformDrag.pointerId)) {
      return;
    }
    const mode = waveformDrag.mode;
    const deletion = selectedDeletion();
    waveformDrag.active = false;
    waveformDrag.mode = null;
    waveformDrag.pointerId = null;
    if (mode === "pan") {
      loadWaveform();
      return;
    }
    if (!deletion || !waveformDrag.deletion) {
      return;
    }
    const changed = deletion.startMs !== waveformDrag.deletion.startMs
      || deletion.endMs !== waveformDrag.deletion.endMs;
    if (!changed) {
      return;
    }
    pushHistory(waveformDrag.historySnapshot);
    state.cutOverrides[deletion.id] = {
      startMs: Math.round(deletion.startMs),
      endMs: Math.round(deletion.endMs)
    };
    deletion.boundaryMode = "manual";
    beginCutPlanEdit();
    markChanged(true);
  }

  function resetSelectedCut() {
    const deletion = selectedDeletion();
    if (!deletion || !deletion.canCut || !state.cutOverrides[deletion.id] || isBusy()) {
      return;
    }
    pushHistory();
    delete state.cutOverrides[deletion.id];
    beginCutPlanEdit();
    markChanged(true);
  }

  function sourceToTarget(timeline, sourceMs) {
    const value = Math.max(0, Number(sourceMs) || 0);
    if (!isTimeline(timeline) || !timeline.segments.length) {
      return 0;
    }
    for (const segment of timeline.segments) {
      if (value < segment.sourceStartMs) {
        return segment.targetStartMs;
      }
      if (value <= segment.sourceEndMs) {
        return Math.min(segment.targetEndMs, segment.targetStartMs + value - segment.sourceStartMs);
      }
    }
    return timeline.durationMs;
  }

  function targetToSource(timeline, targetMs) {
    const value = Math.max(0, Number(targetMs) || 0);
    if (!isTimeline(timeline) || !timeline.segments.length) {
      return 0;
    }
    for (const segment of timeline.segments) {
      if (value <= segment.targetEndMs) {
        return Math.min(segment.sourceEndMs, segment.sourceStartMs + Math.max(0, value - segment.targetStartMs));
      }
    }
    return timeline.segments[timeline.segments.length - 1].sourceEndMs;
  }

  function currentLogicalMs() {
    if (state.playbackMode === "preview") {
      return (elements.audio.currentTime || 0) * 1000;
    }
    const deck = activeDeck();
    const run = state.playbackRuns[state.activeRunIndex];
    const master = deckMaster(deck);
    if (!run || !master) {
      return 0;
    }
    return Math.min(
      run.targetEndMs,
      run.targetStartMs + Math.max(0, master.currentTime * 1000 - run.sourceStartMs)
    );
  }

  function ensureAudioGraph() {
    if (state.audioContext) {
      if (state.audioContext.state === "suspended") {
        state.audioContext.resume().catch(() => {});
      }
      return true;
    }
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) {
      return false;
    }
    try {
      state.audioContext = new AudioContextClass();
      state.decks.forEach((deck) => connectDeckGraph(deck));
      return true;
    } catch (_error) {
      if (state.audioContext && typeof state.audioContext.close === "function") {
        state.audioContext.close().catch(() => {});
      }
      state.audioContext = null;
      return false;
    }
  }

  function connectDeckGraph(deck) {
    if (!state.audioContext) {
      return;
    }
    if (!deck.gainNode) {
      deck.gainNode = state.audioContext.createGain();
      deck.gainNode.gain.setValueAtTime(deck.outputGain, state.audioContext.currentTime);
      deck.gainNode.connect(state.audioContext.destination);
    }
    deck.players.forEach((player) => {
      if (player.sourceNode) {
        return;
      }
      player.sourceNode = state.audioContext.createMediaElementSource(player.audio);
      player.gainNode = state.audioContext.createGain();
      player.gainNode.gain.setValueAtTime(1, state.audioContext.currentTime);
      player.sourceNode.connect(player.gainNode);
      player.gainNode.connect(deck.gainNode);
      player.audio.muted = false;
    });
  }

  function setGain(node, value, rampSeconds) {
    if (node && state.audioContext) {
      const now = state.audioContext.currentTime;
      const gain = node.gain;
      gain.cancelScheduledValues(now);
      gain.setValueAtTime(gain.value, now);
      if (rampSeconds > 0) {
        gain.linearRampToValueAtTime(value, now + rampSeconds);
      } else {
        gain.setValueAtTime(value, now);
      }
    }
  }

  function setDeckGain(deck, value, rampSeconds) {
    deck.outputGain = value;
    deck.root.dataset.outputGain = String(value);
    if (deck.gainNode) {
      setGain(deck.gainNode, value, rampSeconds);
    } else {
      deck.players.forEach((player) => {
        player.audio.muted = value === 0;
      });
    }
  }

  function setDeckState(deck, status) {
    deck.status = status;
    deck.root.dataset.deckState = status;
  }

  function makeDeck(root, id, primaryAudio) {
    return {
      id,
      root,
      status: "idle",
      generation: 0,
      runIndex: -1,
      preRollMs: 0,
      boundaryScheduledFor: "",
      startPromise: null,
      syncPromise: null,
      outputGain: 0,
      players: new Map([["__primary__", { audio: primaryAudio, sourceNode: null, gainNode: null }]]),
      gainNode: null
    };
  }

  function configureDecks(sources) {
    state.decks.forEach((deck) => {
      deck.players.forEach((player, key) => {
        player.audio.pause();
        if (key !== "__primary__" && player.audio !== elements.audio) {
          player.audio.remove();
        }
      });
    });
    state.playbackSources = Array.isArray(sources) ? sources : [];
    const roots = [elements.liveDeckA, elements.liveDeckB];
    const primaryAudios = [elements.audio, elements.liveDeckB.querySelector("audio")];
    state.decks = roots.map((root, index) => makeDeck(root, index === 0 ? "a" : "b", primaryAudios[index]));
    state.decks.forEach((deck) => {
      deck.players = new Map();
      state.playbackSources.forEach((source, sourceIndex) => {
        const audio = sourceIndex === 0 ? primaryAudios[deck.id === "a" ? 0 : 1] : document.createElement("audio");
        audio.preload = "auto";
        audio.dataset.deckAudio = deck.id;
        audio.dataset.sourceId = source.sourceId;
        audio.hidden = true;
        audio.addEventListener("waiting", () => {
          if (deck.status === "playing" && deck.generation === state.deckGeneration) {
            enterDeckError(new Error("音频缓冲中断，已停止播放"));
          }
        });
        audio.addEventListener("stalled", () => {
          if (["preparing", "playing"].includes(deck.status) && deck.generation === state.deckGeneration) {
            enterDeckError(new Error("音频载入停滞，已停止播放"));
          }
        });
        if (sourceIndex > 0) {
          deck.root.appendChild(audio);
        }
        deck.players.set(source.sourceId, { audio, source, sourceNode: null, gainNode: null });
      });
      setDeckState(deck, "idle");
    });
    if (state.audioContext) {
      state.decks.forEach((deck) => connectDeckGraph(deck));
    }
  }

  function liveTrackAt(sourceId) {
    if (!isCutPlan(state.cutPlan) || !Array.isArray(state.cutPlan.tracks)) {
      return null;
    }
    return state.cutPlan.tracks.find((track) => track.sourceId === sourceId) || null;
  }

  function activeDeck() {
    return state.decks[state.activeDeckIndex] || null;
  }

  function standbyDeck() {
    return state.decks[state.activeDeckIndex === 0 ? 1 : 0] || null;
  }

  function deckMaster(deck) {
    if (!deck || !deck.players.size) {
      return null;
    }
    return deck.players.values().next().value.audio;
  }

  function sourceAudibleAt(sourceId, logicalMs) {
    const track = liveTrackAt(sourceId);
    return !track || track.segments.some((segment) => (
      logicalMs >= segment.targetStartMs && logicalMs < segment.targetEndMs
    ));
  }

  function updateDeckTrackGains(deck, logicalMs) {
    if (!deck) {
      return;
    }
    deck.players.forEach((player, sourceId) => {
      const audible = player.audio.dataset.resyncing !== "true"
        && sourceAudibleAt(sourceId, logicalMs);
      player.audio.dataset.audible = String(audible && !state.masterMuted && deck.outputGain > 0);
      if (player.gainNode) {
        setGain(player.gainNode, audible ? 1 : 0, 0);
      } else {
        player.audio.muted = state.masterMuted || deck.outputGain === 0 || !audible;
      }
    });
  }

  function setPlayerAudible(player, audible) {
    player.audio.dataset.audible = String(audible);
    if (player.gainNode) {
      setGain(player.gainNode, audible ? 1 : 0, 0);
    } else {
      player.audio.muted = !audible;
    }
  }

  function runSourceGate(deck, run) {
    let waiting = false;
    let maxOvershootMs = 0;
    for (const runSource of run.sources) {
      const player = deck.players.get(runSource.sourceId);
      if (!player) {
        return { error: new Error(`缺少音频来源：${runSource.sourceId}`) };
      }
      const deltaMs = player.audio.currentTime * 1000 - runSource.sourceStartMs;
      if (deltaMs < 0) {
        waiting = true;
      } else {
        maxOvershootMs = Math.max(maxOvershootMs, deltaMs);
      }
    }
    if (maxOvershootMs > 20) {
      return { error: new Error("下一段存在音轨错过切点超过 20ms，已停止播放") };
    }
    return { waiting, maxOvershootMs };
  }

  function resyncDriftedPlayers(deck, run) {
    if (!deck || !run || deck.syncPromise || deck.status !== "playing") {
      return;
    }
    const masterSource = run.sources[0];
    const masterPlayer = masterSource && deck.players.get(masterSource.sourceId);
    if (!masterPlayer) {
      enterDeckError(new Error("主音轨不存在，已停止播放"));
      return;
    }
    const drifted = run.sources.slice(1).filter((runSource) => {
      const player = deck.players.get(runSource.sourceId);
      return player && Math.abs(player.audio.currentTime - masterPlayer.audio.currentTime) * 1000 > 20;
    });
    if (!drifted.length) {
      return;
    }
    const generation = state.deckGeneration;
    const runIndex = deck.runIndex;
    const syncPromise = (async () => {
      try {
        for (const runSource of drifted) {
          const player = deck.players.get(runSource.sourceId);
          player.audio.dataset.resyncing = "true";
          player.audio.dataset.resyncCount = String(
            (Number(player.audio.dataset.resyncCount) || 0) + 1
          );
          setPlayerAudible(player, false);
          player.audio.pause();
          const targetMs = masterPlayer.audio.currentTime * 1000;
          if (Math.abs(player.audio.currentTime * 1000 - targetMs) > 2) {
            const seekReady = waitForMedia(
              player.audio,
              "seeked",
              () => Math.abs(player.audio.currentTime * 1000 - targetMs) <= 20,
              generation
            );
            player.audio.currentTime = targetMs / 1000;
            await seekReady;
          }
          await waitForMedia(player.audio, "canplay", () => player.audio.readyState >= 3, generation);
          if (
            generation !== state.deckGeneration
            || deck.runIndex !== runIndex
            || deck.status !== "playing"
          ) {
            throw Object.assign(new Error("播放计划已更新"), { code: "STALE_DECK" });
          }
          await player.audio.play();
          const logicalMs = currentLogicalMs();
          setPlayerAudible(player, sourceAudibleAt(runSource.sourceId, logicalMs));
          player.audio.dataset.resyncing = "false";
        }
      } catch (error) {
        if (error.code !== "STALE_DECK") {
          enterDeckError(error);
        }
      } finally {
        drifted.forEach((runSource) => {
          const player = deck.players.get(runSource.sourceId);
          if (player) {
            player.audio.dataset.resyncing = "false";
          }
        });
        if (deck.syncPromise === syncPromise) {
          deck.syncPromise = null;
        }
      }
    })();
    deck.syncPromise = syncPromise;
  }

  function invalidateDeckWork() {
    state.deckGeneration += 1;
  }

  function waitForMedia(audio, eventName, predicate, generation) {
    if (predicate()) {
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      let settled = false;
      const cleanup = () => {
        window.clearTimeout(timeoutId);
        audio.removeEventListener(eventName, ready);
        audio.removeEventListener("error", failed);
        audio.removeEventListener("stalled", failed);
      };
      const ready = () => {
        if (!predicate()) {
          return;
        }
        settled = true;
        cleanup();
        if (generation !== state.deckGeneration) {
          reject(Object.assign(new Error("播放计划已更新"), { code: "STALE_DECK" }));
        } else {
          resolve();
        }
      };
      const failed = () => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        reject(new Error("下一段音频未能预载，已保持静音"));
      };
      const timeoutId = window.setTimeout(failed, DECK_READY_TIMEOUT_MS);
      audio.addEventListener(eventName, ready);
      audio.addEventListener("error", failed, { once: true });
      audio.addEventListener("stalled", failed, { once: true });
    });
  }

  function preRollForRun(runIndex) {
    if (runIndex <= 0) {
      return 0;
    }
    const previous = state.playbackRuns[runIndex - 1];
    const current = state.playbackRuns[runIndex];
    const gapMs = Math.max(0, current.sourceStartMs - previous.sourceEndMs);
    return Math.min(MAX_PRE_ROLL_MS, gapMs * 0.7);
  }

  async function prepareDeck(deck, runIndex, generation, requestedSourceMs) {
    const run = state.playbackRuns[runIndex];
    if (!deck || !run || generation !== state.deckGeneration) {
      throw Object.assign(new Error("播放计划已更新"), { code: "STALE_DECK" });
    }
    if (deck.startPromise) {
      try {
        await deck.startPromise;
      } catch (_error) {
        // 旧启动必须先收尾，随后再准备新计划。
      }
      if (generation !== state.deckGeneration) {
        throw Object.assign(new Error("播放计划已更新"), { code: "STALE_DECK" });
      }
    }
    if (deck.runIndex === runIndex && deck.generation === generation && ["ready", "playing"].includes(deck.status)) {
      return deck;
    }
    setDeckState(deck, "preparing");
    deck.generation = generation;
    deck.runIndex = runIndex;
    deck.root.dataset.generation = String(generation);
    deck.root.dataset.runId = run.id;
    deck.boundaryScheduledFor = "";
    deck.root.dataset.overshootMs = "0";
    deck.preRollMs = requestedSourceMs == null ? preRollForRun(runIndex) : 0;
    const defaultStart = Math.max(
      runIndex > 0 ? state.playbackRuns[runIndex - 1].sourceEndMs : run.sourceStartMs,
      run.sourceStartMs - deck.preRollMs
    );
    const sourceMs = requestedSourceMs == null ? defaultStart : requestedSourceMs;
    await Promise.all(run.sources.map(async (runSource) => {
      const player = deck.players.get(runSource.sourceId);
      if (!player) {
        throw new Error(`缺少音频来源：${runSource.sourceId}`);
      }
      const audio = player.audio;
      if (audio.getAttribute("src") !== runSource.streamUrl) {
        audio.src = runSource.streamUrl;
        audio.load();
      }
      await waitForMedia(audio, "loadedmetadata", () => audio.readyState >= 1, generation);
      if (generation !== state.deckGeneration) {
        throw Object.assign(new Error("播放计划已更新"), { code: "STALE_DECK" });
      }
      if (Math.abs(audio.currentTime * 1000 - sourceMs) > 2) {
        const seekReady = waitForMedia(
          audio,
          "seeked",
          () => Math.abs(audio.currentTime * 1000 - sourceMs) <= 25,
          generation
        );
        audio.currentTime = sourceMs / 1000;
        await seekReady;
      }
      await waitForMedia(audio, "loadeddata", () => audio.readyState >= 2, generation);
      await waitForMedia(audio, "canplay", () => audio.readyState >= 3, generation);
    }));
    if (generation !== state.deckGeneration || deck.generation !== generation) {
      throw Object.assign(new Error("播放计划已更新"), { code: "STALE_DECK" });
    }
    setDeckGain(deck, 0, 0);
    setDeckState(deck, "ready");
    return deck;
  }

  function playDeck(deck) {
    if (deck.startPromise) {
      return deck.startPromise;
    }
    if (deck.status === "playing") {
      return Promise.resolve(deck);
    }
    const generation = state.deckGeneration;
    const runIndex = deck.runIndex;
    setDeckState(deck, "starting");
    const startPromise = (async () => {
      try {
        await Promise.all(Array.from(deck.players.values()).map((player) => player.audio.play()));
        if (
          generation !== state.deckGeneration
          || deck.generation !== generation
          || deck.runIndex !== runIndex
          || deck.status !== "starting"
        ) {
          deck.players.forEach((player) => player.audio.pause());
          setDeckGain(deck, 0, 0);
          throw Object.assign(new Error("播放计划已更新"), { code: "STALE_DECK" });
        }
        setDeckState(deck, "playing");
        return deck;
      } catch (error) {
        deck.players.forEach((player) => player.audio.pause());
        setDeckGain(deck, 0, 0);
        if (error.code !== "STALE_DECK") {
          setDeckState(deck, "error");
        }
        throw error;
      } finally {
        if (deck.startPromise === startPromise) {
          deck.startPromise = null;
        }
      }
    })();
    deck.startPromise = startPromise;
    return startPromise;
  }

  function pauseDeck(deck) {
    if (!deck) {
      return;
    }
    deck.players.forEach((player) => player.audio.pause());
    if (["playing", "switching"].includes(deck.status)) {
      setDeckState(deck, "ready");
    } else if (deck.status === "starting") {
      setDeckState(deck, "idle");
    }
  }

  function pauseLivePlayback(keepMuted) {
    state.livePlaying = false;
    state.decks.forEach((deck) => {
      pauseDeck(deck);
      setDeckGain(deck, keepMuted ? 0 : deck === activeDeck() ? 1 : 0, 0);
    });
  }

  function enterDeckError(error) {
    if (error && error.code === "STALE_DECK") {
      return;
    }
    state.deckError = error || new Error("音频预载失败");
    state.decks.forEach((deck) => {
      setDeckGain(deck, 0, 0);
      pauseDeck(deck);
      setDeckState(deck, "error");
    });
    state.livePlaying = false;
    setStatus("error", state.deckError.message || "音频预载失败", false);
    updatePlayButton();
  }

  function runIndexForLogical(logicalMs) {
    const value = Math.max(0, Number(logicalMs) || 0);
    const index = state.playbackRuns.findIndex((run) => value < run.targetEndMs);
    return index < 0 ? Math.max(0, state.playbackRuns.length - 1) : index;
  }

  async function prepareLiveAt(logicalMs, resume) {
    if (!state.playbackRuns.length) {
      return;
    }
    invalidateDeckWork();
    const generation = state.deckGeneration;
    state.playbackMode = "live";
    state.previewUtterances = null;
    state.previewTimeline = null;
    state.deckError = null;
    const runIndex = runIndexForLogical(logicalMs);
    const run = state.playbackRuns[runIndex];
    const sourceMs = Math.min(run.sourceEndMs, run.sourceStartMs + Math.max(0, logicalMs - run.targetStartMs));
    const deck = activeDeck() || state.decks[0];
    state.activeDeckIndex = state.decks.indexOf(deck);
    state.activeRunIndex = runIndex;
    pauseLivePlayback(true);
    await prepareDeck(deck, runIndex, generation, sourceMs);
    if (generation !== state.deckGeneration) {
      return;
    }
    setDeckGain(deck, 1, 0);
    updateDeckTrackGains(deck, logicalMs);
    elements.audio.dataset.timeline = "live";
    elements.audio.dataset.planId = state.cutPlan.planId;
    if (resume) {
      if (!ensureAudioGraph()) {
        throw new Error("浏览器无法启用无缝试听，请使用“生成精确试听”");
      }
      await playDeck(deck);
      state.livePlaying = true;
      runPlaybackFrame();
    }
    prepareStandby(generation);
    updatePlayButton();
    updatePlaybackTime();
  }

  function prepareStandby(generation) {
    const nextIndex = state.activeRunIndex + 1;
    const deck = standbyDeck();
    if (!deck || nextIndex >= state.playbackRuns.length) {
      return;
    }
    if (deck.runIndex === nextIndex && deck.generation === generation && ["preparing", "ready", "playing"].includes(deck.status)) {
      return;
    }
    prepareDeck(deck, nextIndex, generation, null).catch((error) => enterDeckError(error));
  }

  function scheduleBoundaryMute(deck, run, remainingMs) {
    if (!deck || !run || deck.boundaryScheduledFor === run.id) {
      return;
    }
    deck.boundaryScheduledFor = run.id;
    deck.root.dataset.boundaryMuteScheduled = run.id;
    if (!deck.gainNode || !state.audioContext) {
      return;
    }
    const now = state.audioContext.currentTime;
    const boundaryTime = now + Math.max(0, remainingMs) / 1000;
    const fadeStart = Math.max(now, boundaryTime - DECK_HANDOFF_SECONDS);
    const gain = deck.gainNode.gain;
    gain.cancelScheduledValues(now);
    gain.setValueAtTime(gain.value, now);
    gain.setValueAtTime(1, fadeStart);
    gain.linearRampToValueAtTime(0, boundaryTime);
  }

  function handoffDecks(overshootMs) {
    const generation = state.deckGeneration;
    const oldDeck = activeDeck();
    const nextDeck = standbyDeck();
    const nextIndex = state.activeRunIndex + 1;
    const nextRun = state.playbackRuns[nextIndex];
    const nextMaster = deckMaster(nextDeck);
    const sourceGate = nextDeck && nextRun ? runSourceGate(nextDeck, nextRun) : null;
    if (
      !oldDeck
      || !nextDeck
      || !nextRun
      || !nextMaster
      || nextDeck.status !== "playing"
      || !sourceGate
    ) {
      enterDeckError(new Error("下一段音频尚未准备好，已停止播放"));
      return;
    }
    if (sourceGate.error) {
      enterDeckError(sourceGate.error);
      return;
    }
    if (sourceGate.waiting) {
      return;
    }
    const measuredOvershoot = Math.max(
      0,
      Number.isFinite(overshootMs)
        ? overshootMs
        : sourceGate.maxOvershootMs
    );
    nextDeck.root.dataset.overshootMs = measuredOvershoot.toFixed(3);
    if (measuredOvershoot > 20) {
      enterDeckError(new Error("下一段音频错过切点超过 20ms，已停止播放"));
      return;
    }
    setDeckState(oldDeck, "switching");
    setDeckState(nextDeck, "switching");
    setDeckGain(oldDeck, 0, 0);
    setDeckGain(nextDeck, 1, DECK_HANDOFF_SECONDS);
    state.activeDeckIndex = state.activeDeckIndex === 0 ? 1 : 0;
    state.activeRunIndex = nextIndex;
    updateDeckTrackGains(nextDeck, nextRun.targetStartMs);
    window.setTimeout(() => {
      if (generation !== state.deckGeneration) {
        return;
      }
      pauseDeck(oldDeck);
      setDeckState(nextDeck, "playing");
      setDeckState(oldDeck, "idle");
      prepareStandby(generation);
    }, Math.ceil(DECK_HANDOFF_SECONDS * 1000) + 2);
  }

  function enforceDeckTimeline() {
    if (state.playbackMode !== "live" || !state.livePlaying) {
      return;
    }
    const deck = activeDeck();
    const master = deckMaster(deck);
    const run = state.playbackRuns[state.activeRunIndex];
    if (!deck || !master || !run) {
      return;
    }
    const sourceMs = master.currentTime * 1000;
    const logicalMs = currentLogicalMs();
    updateDeckTrackGains(deck, logicalMs);
    resyncDriftedPlayers(deck, run);
    const nextDeck = standbyDeck();
    const nextRun = state.playbackRuns[state.activeRunIndex + 1];
    if (!nextRun) {
      if (sourceMs >= run.sourceEndMs) {
        pauseLivePlayback(false);
        updatePlayButton();
      }
      return;
    }
    const preRollMs = nextDeck ? nextDeck.preRollMs : 0;
    if (
      nextDeck
      && nextDeck.status === "ready"
      && sourceMs >= run.sourceEndMs - preRollMs
    ) {
      playDeck(nextDeck).catch((error) => enterDeckError(error));
    }
    if (sourceMs >= run.sourceEndMs - preRollMs) {
      scheduleBoundaryMute(deck, run, run.sourceEndMs - sourceMs);
    }
    if (sourceMs >= run.sourceEndMs) {
      setDeckGain(deck, 0, 0);
      const nextMaster = deckMaster(nextDeck);
      const sourceGate = nextDeck && nextRun ? runSourceGate(nextDeck, nextRun) : null;
      if (sourceGate && sourceGate.error) {
        enterDeckError(sourceGate.error);
        return;
      }
      if (
        nextDeck
        && nextDeck.status === "playing"
        && nextMaster
        && sourceGate
        && !sourceGate.waiting
      ) {
        handoffDecks(sourceGate.maxOvershootMs);
      }
    }
  }

  function runPlaybackFrame() {
    if (state.playbackFrame !== null) {
      window.cancelAnimationFrame(state.playbackFrame);
    }
    const frame = () => {
      state.playbackFrame = null;
      enforceDeckTimeline();
      updatePlaybackTime();
      if ((state.playbackMode === "live" && state.livePlaying) || (state.playbackMode === "preview" && !elements.audio.paused)) {
        state.playbackFrame = window.requestAnimationFrame(frame);
      }
    };
    state.playbackFrame = window.requestAnimationFrame(frame);
  }

  function switchToLivePlayback(logicalMs, resume, keepMuted) {
    window.clearTimeout(state.pendingWordClickTimer);
    elements.audio.pause();
    state.previewUtterances = null;
    state.previewTimeline = null;
    state.playbackMode = "live";
    state.playbackUrl = state.originalPlaybackUrl;
    state.activeUtteranceIds = new Set();
    elements.transcript.querySelectorAll("[data-turn-id]").forEach((utteranceElement) => {
      utteranceElement.classList.remove("is-active");
    });
    prepareLiveAt(logicalMs || 0, resume).catch((error) => enterDeckError(error));
  }

  async function seekFromTranscript(originalMs, startPlayback = false) {
    const timeline = state.playbackMode === "preview" ? state.previewTimeline : state.liveTimeline;
    const logicalMs = sourceToTarget(timeline, originalMs);
    if (state.playbackMode === "preview") {
      setAudioTime(logicalMs);
      if (startPlayback && elements.audio.paused) {
        try {
          await elements.audio.play();
          runPlaybackFrame();
        } catch (_error) {
          setStatus("error", "音频无法播放", false);
        }
      }
    } else {
      await prepareLiveAt(logicalMs, startPlayback || state.livePlaying);
    }
  }

  function wordsNeedSpace(previousText, currentText) {
    return /[A-Za-z0-9]$/.test(previousText) && /^[A-Za-z0-9]/.test(currentText);
  }

  function renderNowPlaying() {
    if (!state.project) {
      return;
    }
    const nowMs = state.playbackMode === "preview"
      ? elements.audio.currentTime * 1000
      : (() => {
          const master = deckMaster(activeDeck());
          return master ? master.currentTime * 1000 : 0;
        })();
    const captionUtterances = state.previewUtterances || state.project.utterances;
    const activeUtterances = captionUtterances.filter((utterance) => (
      utterance.startMs <= nowMs && utterance.endMs >= nowMs
    ));
    const nextIds = new Set(
      activeUtterances
        .map((utterance) => state.utteranceTurnIds[utterance.id])
        .filter(Boolean)
    );

    if (!setsEqual(nextIds, state.activeUtteranceIds)) {
      state.activeUtteranceIds = nextIds;
      elements.transcript.querySelectorAll("[data-turn-id]").forEach((utteranceElement) => {
        utteranceElement.classList.toggle("is-active", nextIds.has(utteranceElement.dataset.turnId));
      });
    }

    if (!activeUtterances.length) {
      elements.nowSpeaker.textContent = nowMs > 0 ? "间隔" : "尚未播放";
      elements.nowCaption.textContent = "";
      return;
    }

    const uniqueNames = [];
    activeUtterances.forEach((utterance) => {
      const name = speakerName(effectiveSpeakerId(utterance));
      if (!uniqueNames.includes(name)) {
        uniqueNames.push(name);
      }
    });
    elements.nowSpeaker.textContent = uniqueNames.join(" / ");
    elements.nowCaption.replaceChildren();
    activeUtterances.forEach((utterance, utteranceIndex) => {
      if (utteranceIndex) {
        elements.nowCaption.appendChild(document.createTextNode("　"));
      }
      let previousText = "";
      utterance.words.forEach((word) => {
        const removedByPlan = state.playbackMode === "live"
          && isCutPlan(state.cutPlan)
          && state.cutPlan.deletions.some((deletion) => (
            deletion.canCut
            && (deletion.scope !== "speaker" || deletion.speakerId === effectiveSpeakerId(utterance))
            &&
            word.startMs < deletion.endMs && word.endMs > deletion.startMs
          ));
        if (removedByPlan) {
          return;
        }
        if (previousText && wordsNeedSpace(previousText, word.text)) {
          elements.nowCaption.appendChild(document.createTextNode(" "));
        }
        const span = document.createElement("span");
        span.textContent = word.text + (word.punctuationAfter || "");
        elements.nowCaption.appendChild(span);
        previousText = word.text;
      });
    });
  }

  function setsEqual(first, second) {
    if (first.size !== second.size) {
      return false;
    }
    for (const value of first) {
      if (!second.has(value)) {
        return false;
      }
    }
    return true;
  }

  function updatePlaybackTime() {
    const timeline = state.playbackMode === "preview" ? state.previewTimeline : state.liveTimeline;
    const durationSeconds = isTimeline(timeline)
      ? timeline.durationMs / 1000
      : (state.project ? state.project.durationMs / 1000 : 0);
    const logicalSeconds = currentLogicalMs() / 1000;
    elements.seekSlider.max = String(Math.max(0, durationSeconds));
    elements.seekSlider.value = String(Math.min(logicalSeconds, durationSeconds));
    elements.currentTime.textContent = formatTime(logicalSeconds * 1000);
    elements.durationTime.textContent = formatTime(durationSeconds * 1000);
    renderNowPlaying();
  }

  async function togglePlayback() {
    if (state.playbackMode === "preview") {
      if (!elements.audio.src) {
        return;
      }
      if (elements.audio.paused) {
        try {
          await elements.audio.play();
          runPlaybackFrame();
        } catch (_error) {
          setStatus("error", "音频无法播放", false);
        }
      } else {
        elements.audio.pause();
      }
      updatePlayButton();
      return;
    }
    if (!state.livePlaying) {
      try {
        if (!ensureAudioGraph()) {
          throw new Error("浏览器无法启用无缝试听，请使用“生成精确试听”");
        }
        let deck = activeDeck();
        if (!deck || !["ready", "playing"].includes(deck.status)) {
          await prepareLiveAt(currentLogicalMs(), false);
          deck = activeDeck();
        }
        await playDeck(deck);
        setDeckGain(deck, 1, 0);
        state.livePlaying = true;
        prepareStandby(state.deckGeneration);
        runPlaybackFrame();
      } catch (error) {
        enterDeckError(error);
      }
    } else {
      pauseLivePlayback(false);
    }
    updatePlayButton();
  }

  function updatePlayButton() {
    const playing = state.playbackMode === "preview" ? !elements.audio.paused : state.livePlaying;
    elements.playButton.innerHTML = playing
      ? "<span aria-hidden=\"true\">&#10074;&#10074;</span>"
      : "<span aria-hidden=\"true\">&#9654;</span>";
    elements.playButton.title = playing ? "暂停" : "播放";
    elements.playButton.setAttribute("aria-label", playing ? "暂停" : "播放");
  }

  function cancellationError() {
    const error = new Error("请求已取消");
    error.code = "CLIENT_ABORTED";
    return error;
  }

  function isCancellationError(error) {
    return error && (error.code === "CLIENT_ABORTED" || error.code === "operation_cancelled");
  }

  function beginOperation(phase) {
    const controller = new AbortController();
    state.operationPhase = phase;
    state.operationController = controller;
    state.operationCancelled = false;
    state.cancelBusy = false;
    state.previewBusy = phase === "preview";
    state.exportBusy = phase === "export";
    setActionButtons();
    return controller;
  }

  function finishOperation(controller) {
    if (state.operationController !== controller) {
      return;
    }
    state.previewBusy = false;
    state.exportBusy = false;
    state.operationPhase = null;
    state.operationController = null;
    state.operationCancelled = false;
    state.cancelBusy = false;
    setActionButtons();
  }

  async function cancelOperation() {
    if (!isBusy() || state.cancelBusy) {
      return;
    }
    const phase = state.operationPhase;
    const controller = state.operationController;
    state.operationCancelled = true;
    state.cancelBusy = true;
    setActionButtons();
    setStatus(phase === "preview" ? "saving" : "exporting", "正在取消", false);

    const cancelRequest = request("/api/cancel", {
      method: "POST",
      body: {},
      timeoutMs: CANCEL_REQUEST_TIMEOUT_MS
    });
    if (controller) {
      controller.abort();
    }

    try {
      await cancelRequest;
      setStatus("cancelled", phase === "preview" ? "试听已取消" : "导出已取消", false);
    } catch (error) {
      setStatus("error", `已停止等待，取消失败：${error.message}`, false);
    } finally {
      state.cancelBusy = false;
      setActionButtons();
    }
  }

  async function buildPreview() {
    if (isBusy()) {
      return;
    }
    const controller = beginOperation("preview");
    try {
      await flushSave();
      if (controller.signal.aborted) {
        throw cancellationError();
      }
      setStatus("saving", "正在生成试听", false);
      if (!isCutPlan(state.cutPlan)) {
        throw new Error("当前切割计划不可用");
      }
      if (hasUncuttableDeletions()) {
        throw new Error(cutBlockMessage());
      }
      const result = await request("/api/preview", {
        method: "POST",
        body: { revision: state.revision, planId: state.cutPlan.planId },
        signal: controller.signal,
        timeoutMs: LONG_REQUEST_TIMEOUT_MS
      });
      if (
        !result.url
        || !Array.isArray(result.utterances)
        || result.planId !== state.cutPlan.planId
        || !isCutPlan(result.cutPlan)
      ) {
        throw new Error("试听结果缺少音频或时间轴");
      }
      const logicalMs = currentLogicalMs();
      const resume = state.playbackMode === "preview" ? !elements.audio.paused : state.livePlaying;
      invalidateDeckWork();
      pauseLivePlayback(true);
      state.previewUtterances = result.utterances;
      state.previewTimeline = result.cutPlan.timeline;
      state.playbackMode = "preview";
      setDeckGain(state.decks[0], 1, 0);
      setDeckGain(state.decks[1], 0, 0);
      elements.audio.src = result.url;
      elements.audio.load();
      elements.audio.dataset.timeline = "preview";
      state.playbackUrl = result.url;
      const seek = () => {
        setAudioTime(Math.min(logicalMs, state.previewTimeline.durationMs));
        if (resume) {
          elements.audio.play().then(() => {
            updatePlayButton();
            runPlaybackFrame();
          }).catch(() => setStatus("error", "精确试听无法继续播放", false));
        }
      };
      if (elements.audio.readyState >= 1) {
        seek();
      } else {
        elements.audio.addEventListener("loadedmetadata", seek, { once: true });
      }
      setStatus("success", "试听已更新", false);
    } catch (error) {
      if (isCancellationError(error) || state.operationCancelled) {
        setStatus("cancelled", "试听已取消", false);
      } else {
        setStatus("error", error.message || "试听生成失败", false);
      }
    } finally {
      finishOperation(controller);
    }
  }

  function resetPreviewAfterWordEdit() {
    beginCutPlanEdit();
  }

  async function exportDraft() {
    if (isBusy()) {
      return;
    }
    const controller = beginOperation("export");
    elements.exportResult.hidden = true;
    setStatus("exporting", "正在导出剪映草稿", false);
    try {
      await flushSave();
      if (controller.signal.aborted) {
        throw cancellationError();
      }
      if (!isCutPlan(state.cutPlan)) {
        throw new Error("当前切割计划不可用");
      }
      if (hasUncuttableDeletions()) {
        throw new Error(cutBlockMessage());
      }
      const result = await request("/api/export", {
        method: "POST",
        body: { revision: state.revision, planId: state.cutPlan.planId },
        signal: controller.signal,
        timeoutMs: LONG_REQUEST_TIMEOUT_MS
      });
      if (!result.draftName || !result.draftPath) {
        throw new Error("导出结果缺少草稿目录");
      }
      elements.exportName.textContent = result.draftName;
      elements.exportPath.textContent = result.draftPath;
      elements.exportPath.title = result.draftPath;
      elements.exportResult.hidden = false;
      setStatus("success", "剪映草稿已导出", false);
    } catch (error) {
      if (isCancellationError(error) || state.operationCancelled) {
        setStatus("cancelled", "导出已取消", false);
      } else {
        setStatus("error", error.message || "导出失败", false);
      }
    } finally {
      finishOperation(controller);
    }
  }

  function bindEvents() {
    elements.undoButton.addEventListener("click", undo);
    elements.redoButton.addEventListener("click", redo);
    elements.retrySaveButton.addEventListener("click", () => {
      state.lastSaveFailed = false;
      state.saveRequested = true;
      drainSaveQueue().catch(() => {});
    });
    elements.previewButton.addEventListener("click", buildPreview);
    elements.cancelButton.addEventListener("click", cancelOperation);
    elements.exportButton.addEventListener("click", exportDraft);
    elements.playButton.addEventListener("click", togglePlayback);
    elements.cutSelector.addEventListener("change", () => {
      state.selectedDeletionId = elements.cutSelector.value || null;
      resetWaveformView();
    });
    elements.waveformZoomIn.addEventListener("click", () => changeWaveformZoom(0.6));
    elements.waveformZoomOut.addEventListener("click", () => changeWaveformZoom(1.7));
    elements.waveformResetView.addEventListener("click", resetWaveformView);
    elements.cutResetButton.addEventListener("click", resetSelectedCut);
    elements.cutStartHandle.addEventListener("pointerdown", (event) => startWaveformDrag(event, "start"));
    elements.cutEndHandle.addEventListener("pointerdown", (event) => startWaveformDrag(event, "end"));
    elements.waveformViewport.addEventListener("pointerdown", (event) => {
      if (!event.target.closest(".cut-handle")) {
        startWaveformDrag(event, "pan");
      }
    });
    window.addEventListener("pointermove", moveWaveformDrag);
    window.addEventListener("pointerup", finishWaveformDrag);
    window.addEventListener("pointercancel", finishWaveformDrag);

    elements.speakerFilters.addEventListener("click", (event) => {
      const button = event.target.closest("[data-speaker-filter]");
      if (!button) {
        return;
      }
      state.activeSpeakerId = button.dataset.speakerFilter;
      applySpeakerFilter();
    });

    elements.speakerEditors.addEventListener("focusin", (event) => {
      const input = event.target.closest("[data-speaker-input]");
      if (!input) {
        return;
      }
      input._renameSnapshot = snapshot();
      input._historyPushed = false;
    });

    elements.speakerEditors.addEventListener("input", (event) => {
      const input = event.target.closest("[data-speaker-input]");
      if (!input) {
        return;
      }
      const nextName = input.value.trim();
      if (!nextName) {
        return;
      }
      if (!input._historyPushed) {
        pushHistory(input._renameSnapshot || snapshot());
        input._historyPushed = true;
      }
      state.speakerNames[input.dataset.speakerInput] = nextName;
      syncSpeakerNames();
      markChanged();
    });

    elements.speakerEditors.addEventListener("focusout", (event) => {
      const input = event.target.closest("[data-speaker-input]");
      if (!input) {
        return;
      }
      if (!input.value.trim()) {
        const originalName = input._renameSnapshot
          ? input._renameSnapshot.speakerNames[input.dataset.speakerInput]
          : speakerName(input.dataset.speakerInput);
        input.value = originalName;
        state.speakerNames[input.dataset.speakerInput] = originalName;
        syncSpeakerNames();
        if (input._historyPushed) {
          markChanged();
        }
      }
      input._renameSnapshot = null;
      input._historyPushed = false;
    });

    elements.transcript.addEventListener("change", (event) => {
      const select = event.target.closest("[data-turn-speaker]");
      if (!select || isBusy()) {
        return;
      }
      let utteranceIds;
      try {
        utteranceIds = JSON.parse(select.dataset.utteranceIds || "[]");
      } catch (_error) {
        return;
      }
      if (!Array.isArray(utteranceIds) || !utteranceIds.length) {
        return;
      }
      pushHistory();
      utteranceIds.forEach((utteranceId) => {
        state.speakerOverrides[utteranceId] = select.value;
      });
      markChanged(true);
    });

    elements.transcript.addEventListener("pointerdown", (event) => {
      const wordElement = event.target.closest("[data-word-id]");
      if (wordElement) {
        startWordDrag(event, wordElement);
      }
    });

    window.addEventListener("pointermove", (event) => {
      if (!drag.active) {
        return;
      }
      const target = document.elementFromPoint(event.clientX, event.clientY);
      visitDraggedWord(target && target.closest ? target.closest("[data-word-id]") : null);
    });
    window.addEventListener("pointerup", finishWordDrag);
    window.addEventListener("pointercancel", finishWordDrag);

    elements.transcript.addEventListener("click", (event) => {
      const seekButton = event.target.closest("[data-seek-ms]");
      if (seekButton) {
        seekFromTranscript(Number(seekButton.dataset.seekMs), state.interactionMode === "play")
          .catch((error) => enterDeckError(error));
        return;
      }
      const wordElement = event.target.closest("[data-word-id]");
      if (!wordElement || isBusy()) {
        return;
      }
      if (state.interactionMode === "play") {
        seekFromTranscript(Number(wordElement.dataset.startMs), true)
          .catch((error) => enterDeckError(error));
      } else if (event.detail === 0) {
        toggleWordSelection(wordElement.dataset.wordId);
      }
    });

    elements.interactionModeButton.addEventListener("click", () => {
      if (!isBusy()) {
        setInteractionMode(state.interactionMode === "play" ? "edit" : "play");
      }
    });

    elements.seekSlider.addEventListener("input", () => {
      const logicalMs = Number(elements.seekSlider.value) * 1000;
      if (state.playbackMode === "preview") {
        setAudioTime(logicalMs);
      } else {
        prepareLiveAt(logicalMs, state.livePlaying).catch((error) => enterDeckError(error));
      }
    });
    elements.audio.addEventListener("timeupdate", updatePlaybackTime);
    elements.audio.addEventListener("loadedmetadata", updatePlaybackTime);
    elements.audio.addEventListener("play", () => {
      if (state.playbackMode === "preview") {
        updatePlayButton();
        runPlaybackFrame();
      }
    });
    elements.audio.addEventListener("pause", () => {
      if (state.playbackMode === "preview" && state.playbackFrame !== null) {
        window.cancelAnimationFrame(state.playbackFrame);
        state.playbackFrame = null;
      }
      updatePlayButton();
    });
    elements.audio.addEventListener("error", () => {
      setStatus("error", "音频载入失败", false);
    });
    window.addEventListener("pagehide", () => {
      if (typeof navigator.sendBeacon === "function") {
        try {
          navigator.sendBeacon(
            "/api/cancel",
            new Blob(["{}"], { type: "application/json" })
          );
        } catch (_error) {
          // 页面退出不能等待补救请求。
        }
      }
      if (state.operationController) {
        state.operationController.abort();
      }
    });
    if (typeof ResizeObserver === "function") {
      new ResizeObserver(() => drawWaveform()).observe(elements.waveformViewport);
    }
  }

  function validateProjectPayload(payload) {
    if (!payload || !payload.project || !payload.state || !payload.playback) {
      throw new Error("项目数据不完整");
    }
    const project = payload.project;
    if (
      !Array.isArray(project.speakers)
      || !Array.isArray(project.utterances)
      || !Array.isArray(payload.reviewTurns)
      || !isCutPlan(payload.playback.cutPlan)
      || !isTimeline(payload.playback.timeline)
      || !validatePlaybackContract(payload.playback, Number(payload.state.revision))
    ) {
      throw new Error("逐字稿格式不正确");
    }
    project.utterances.forEach((utterance) => {
      if (!utterance.id || !utterance.speakerId || !Array.isArray(utterance.words)) {
        throw new Error("逐字稿段落格式不正确");
      }
    });
    payload.reviewTurns.forEach((turn) => {
      if (!turn.id || !turn.speakerId || !Array.isArray(turn.utteranceIds)) {
        throw new Error("发言轮次格式不正确");
      }
    });
  }

  function timelinesEqual(first, second) {
    if (!isTimeline(first) || !isTimeline(second)) {
      return false;
    }
    if (
      first.revision !== second.revision
      || first.durationMs !== second.durationMs
      || first.segments.length !== second.segments.length
    ) {
      return false;
    }
    return first.segments.every((segment, index) => {
      const other = second.segments[index];
      return segment.sourceStartMs === other.sourceStartMs
        && segment.sourceEndMs === other.sourceEndMs
        && segment.targetStartMs === other.targetStartMs
        && segment.targetEndMs === other.targetEndMs;
    });
  }

  function validatePlaybackContract(playback, expectedRevision) {
    if (
      !playback
      || playback.strategy !== "dual-audio-preload-v1"
      || !Number.isFinite(expectedRevision)
      || playback.revision !== expectedRevision
      || !isCutPlan(playback.cutPlan)
      || playback.cutPlan.revision !== expectedRevision
      || playback.planId !== playback.cutPlan.planId
      || !timelinesEqual(playback.timeline, playback.cutPlan.timeline)
      || !Array.isArray(playback.sources)
      || !playback.sources.length
      || !Array.isArray(playback.runs)
      || playback.runs.length !== playback.timeline.segments.length
    ) {
      return false;
    }
    const sourceIds = playback.sources.map((source) => source.sourceId);
    if (
      !playback.sources.every((source) => (
        typeof source.sourceId === "string"
        && source.sourceId.length > 0
        && typeof source.url === "string"
        && source.url.length > 0
      ))
      || new Set(sourceIds).size !== sourceIds.length
    ) {
      return false;
    }
    let previousRun = null;
    return playback.runs.every((run, index) => {
      const segment = playback.timeline.segments[index];
      const runSourceIds = Array.isArray(run.sources)
        ? run.sources.map((source) => source.sourceId)
        : [];
      const continuous = !previousRun || (
        previousRun.targetEndMs === run.targetStartMs
        && previousRun.sourceEndMs <= run.sourceStartMs
      );
      const matches = typeof run.id === "string"
        && (index > 0 || run.targetStartMs === 0)
        && run.sourceStartMs === segment.sourceStartMs
        && run.sourceEndMs === segment.sourceEndMs
        && run.targetStartMs === segment.targetStartMs
        && run.targetEndMs === segment.targetEndMs
        && run.sourceEndMs > run.sourceStartMs
        && run.targetEndMs - run.targetStartMs === run.sourceEndMs - run.sourceStartMs
        && (index < playback.runs.length - 1 || run.targetEndMs === playback.timeline.durationMs)
        && continuous
        && runSourceIds.length === sourceIds.length
        && runSourceIds.every((sourceId, sourceIndex) => sourceId === sourceIds[sourceIndex])
        && run.sources.every((source) => (
          typeof source.streamUrl === "string"
          && source.streamUrl.length > 0
          && source.sourceStartMs === run.sourceStartMs
          && source.sourceEndMs === run.sourceEndMs
        ));
      previousRun = run;
      return matches;
    });
  }

  async function loadProject() {
    setStatus("idle", "正在读取", false);
    try {
      const payload = await request("/api/project");
      validateProjectPayload(payload);
      state.project = payload.project;
      setReviewTurns(payload.reviewTurns);
      state.revision = Number(payload.state.revision) || 0;
      state.selectedWordIds = new Set(payload.state.selectedWordIds || []);
      state.speakerNames = normalizedSpeakerNames(payload.project, payload.state.speakerNames);
      state.speakerOverrides = Object.assign({}, payload.state.speakerOverrides || {});
      state.cutOverrides = JSON.parse(JSON.stringify(payload.state.cutOverrides || {}));
      state.playbackUrl = payload.playback.url || "";
      const playbackSources = Array.isArray(payload.playback.sources) && payload.playback.sources.length
        ? payload.playback.sources
        : [{ sourceId: "source", speakerId: null, url: state.playbackUrl }];
      configureDecks(playbackSources);
      state.originalPlaybackUrl = playbackSources[0].url || state.playbackUrl;
      state.playbackUrl = state.originalPlaybackUrl;
      state.cutPlan = payload.playback.cutPlan;
      state.liveTimeline = state.cutPlan.timeline;
      state.playbackStrategy = payload.playback.strategy;
      state.playbackRuns = payload.playback.runs || [];
      state.previewTimeline = null;
      state.playbackMode = "live";
      state.previewUtterances = null;
      setInteractionMode("play");
      elements.audio.dataset.timeline = "live";
      elements.audio.dataset.planId = state.cutPlan.planId;
      elements.audio.dataset.cutPending = "false";
      state.savedMutationVersion = state.mutationVersion;
      await prepareLiveAt(0, false);

      const displayName = payload.project.name || payload.project.id || "播客逐字稿";
      elements.projectTitle.textContent = displayName;
      renderSpeakerControls();
      renderTranscript();
      syncSelectedDeletion();

      if (state.playbackUrl) {
        elements.playButton.disabled = false;
        elements.seekSlider.disabled = false;
      }
      elements.durationTime.textContent = formatTime(state.liveTimeline.durationMs);
      elements.seekSlider.max = String(Math.max(0, state.liveTimeline.durationMs / 1000));
      elements.shell.setAttribute("aria-busy", "false");
      setCutReadyStatus("已载入");
      setActionButtons();
      renderNowPlaying();
    } catch (error) {
      elements.transcript.innerHTML = "";
      const message = document.createElement("p");
      message.className = "empty-state";
      message.textContent = error.message || "项目载入失败";
      elements.transcript.appendChild(message);
      elements.projectTitle.textContent = "项目无法打开";
      elements.shell.setAttribute("aria-busy", "false");
      setStatus("error", error.message || "项目载入失败", false);
    }
  }

  bindEvents();
  loadProject();
})();
