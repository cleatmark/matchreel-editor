/**
 * XbotGo Zoom Replay Editor - Frontend Controller
 * Follows ZOOM_EDITOR_SPEC.md Phase 1
 */

(function () {
  'use strict';

  // Constants
  const REF_W = 3840;
  const REF_H = 2160;
  const FRAME_STEP = 1 / 15; // 15 unique frames per second

  // State
  const state = {
    gameId: '',
    tokenOrClip: '',
    canonicalToken: '',
    clipNum: null,
    file: '',
    event: 0,
    actionEnd: null,
    start: 0,
    dur: 4.5,
    cutStart: 0.0,
    cutEnd: 0.0,
    cropX: 1152,
    cropY: 648,
    cropW: 1536, // 2.5x zoom default
    cropH: 864,
    zoomRatio: 2.5,
    speed: 0.5,
    holdEnd: 0.0,
    pans: [],
    zoomTo: null,
    homographies: null,
    allClips: [],
    isPlaying: false,
    isReplayPreview: false,
    previewRaf: null,
    status: 'auto-placed',
    finalExists: false,
    finalUrl: null,
  };

  // DOM Elements
  const el = {};

  function initElements() {
    el.clipTitleText = document.getElementById('clipTitleText');
    el.clipTokenText = document.getElementById('clipTokenText');
    el.clipStatusBadge = document.getElementById('clipStatusBadge');
    el.clipIndexIndicator = document.getElementById('clipIndexIndicator');
    el.btnPrevZoom = document.getElementById('btnPrevZoom');
    el.btnNextZoom = document.getElementById('btnNextZoom');
    el.btnWatchFinal = document.getElementById('btnWatchFinal');
    el.btnOpenDocs = document.getElementById('btnOpenDocs');
    el.btnBackToReview = document.getElementById('btnBackToReview');

    el.videoStage = document.getElementById('videoStage');
    el.mainVideo = document.getElementById('mainVideo');
    el.previewCanvas = document.getElementById('previewCanvas');
    el.cropOverlay = document.getElementById('cropOverlay');
    el.cropBox = document.getElementById('cropBox');
    el.cropTag = document.getElementById('cropTag');
    el.gridOverlay = document.getElementById('gridOverlay');

    el.btnSeekStart = document.getElementById('btnSeekStart');
    el.btnStepBack1s = document.getElementById('btnStepBack1s');
    el.btnStepBackHalf = document.getElementById('btnStepBackHalf');
    el.btnStepBackFrame = document.getElementById('btnStepBackFrame');
    el.btnPlayPause = document.getElementById('btnPlayPause');
    el.btnStepFwdFrame = document.getElementById('btnStepFwdFrame');
    el.btnStepFwdHalf = document.getElementById('btnStepFwdHalf');
    el.btnStepFwd1s = document.getElementById('btnStepFwd1s');
    el.btnSeekEnd = document.getElementById('btnSeekEnd');

    el.txtSourceTime = document.getElementById('txtSourceTime');
    el.txtEventTime = document.getElementById('txtEventTime');
    el.txtReplayTime = document.getElementById('txtReplayTime');
    el.txtSpeedLabel = document.getElementById('txtSpeedLabel');
    el.chkLoop = document.getElementById('chkLoop');
    el.chkGrid = document.getElementById('chkGrid');
    el.chkSnap = document.getElementById('chkSnap');

    el.scrubberTrack = document.getElementById('scrubberTrack');
    el.scrubberWindowRange = document.getElementById('scrubberWindowRange');
    el.scrubberTrimLeft = document.getElementById('scrubberTrimLeft');
    el.scrubberTrimRight = document.getElementById('scrubberTrimRight');
    el.scrubberKeyframes = document.getElementById('scrubberKeyframes');
    el.scrubberPlayhead = document.getElementById('scrubberPlayhead');

    el.zoomSlider = document.getElementById('zoomSlider');
    el.lblZoomVal = document.getElementById('lblZoomVal');
    el.lblCropW = document.getElementById('lblCropW');
    el.lblCropH = document.getElementById('lblCropH');
    el.lblCropX = document.getElementById('lblCropX');
    el.lblCropY = document.getElementById('lblCropY');

    el.inpWinStartOffset = document.getElementById('inpWinStartOffset');
    el.inpWinEndOffset = document.getElementById('inpWinEndOffset');
    el.lblWindowSummary = document.getElementById('lblWindowSummary');
    el.inpCutStart = document.getElementById('inpCutStart');
    el.inpCutEnd = document.getElementById('inpCutEnd');
    el.inpHoldEnd = document.getElementById('inpHoldEnd');

    el.keyframesList = document.getElementById('keyframesList');
    el.btnAddKeyframe = document.getElementById('btnAddKeyframe');
    el.lblHStatus = document.getElementById('lblHStatus');
    el.btnPrepareH = document.getElementById('btnPrepareH');

    el.btnAutoStart = document.getElementById('btnAutoStart');
    el.btnLooksGood = document.getElementById('btnLooksGood');
    el.btnSavePlan = document.getElementById('btnSavePlan');
    el.btnPreviewReplay = document.getElementById('btnPreviewReplay');
    el.selRenderScope = document.getElementById('selRenderScope');
    el.btnRenderExact = document.getElementById('btnRenderExact');
    el.btnRemoveZoom = document.getElementById('btnRemoveZoom');
    el.btnRestoreZoom = document.getElementById('btnRestoreZoom');
    el.btnReopenLogDrawer = document.getElementById('btnReopenLogDrawer');
    el.verifyResultBadge = document.getElementById('verifyResultBadge');
    el.lblKeyframeHint = document.getElementById('lblKeyframeHint');
    el.lblServerStart = document.getElementById('lblServerStart');
    el.staleServerBanner = document.getElementById('staleServerBanner');

    el.removeZoomModal = document.getElementById('removeZoomModal');
    el.removeZoomModalPrompt = document.getElementById('removeZoomModalPrompt');
    el.btnCancelRemoveZoomModal = document.getElementById('btnCancelRemoveZoomModal');
    el.btnCancelRemoveZoom = document.getElementById('btnCancelRemoveZoom');
    el.btnConfirmRemoveZoom = document.getElementById('btnConfirmRemoveZoom');

    el.unsavedZoomModal = document.getElementById('unsavedZoomModal');
    el.unsavedModalPrompt = document.getElementById('unsavedModalPrompt');
    el.btnCloseUnsavedModal = document.getElementById('btnCloseUnsavedModal');
    el.btnKeepEditingZoom = document.getElementById('btnKeepEditingZoom');
    el.btnDiscardZoom = document.getElementById('btnDiscardZoom');
    el.btnSaveAndLeaveZoom = document.getElementById('btnSaveAndLeaveZoom');

    el.logDrawer = document.getElementById('logDrawer');
    el.logDrawerTitle = document.getElementById('logDrawerTitle');
    el.logDrawerContent = document.getElementById('logDrawerContent');
    el.btnCloseLogDrawer = document.getElementById('btnCloseLogDrawer');
    el.logTaskSpinner = document.getElementById('logTaskSpinner');

    el.finalVideoModal = document.getElementById('finalVideoModal');
    el.finalVideoPlayer = document.getElementById('finalVideoPlayer');
    el.btnCloseFinalVideo = document.getElementById('btnCloseFinalVideo');

    el.shortcutsModal = document.getElementById('shortcutsModal');
    el.btnCloseShortcuts = document.getElementById('btnCloseShortcuts');

    el.unplacedNotice = document.getElementById('unplacedNotice');
    el.btnUnplacedAutoFrame = document.getElementById('btnUnplacedAutoFrame');
    el.btnUnplacedAutoFrameAll = document.getElementById('btnUnplacedAutoFrameAll');
    el.btnAutoFrame = document.getElementById('btnAutoFrame');
    el.productionLockBanner = document.getElementById('productionLockBanner');
    el.lblLockPid = document.getElementById('lblLockPid');

    el.blockedClipsModal = document.getElementById('blockedClipsModal');
    el.blockedModalTitle = document.getElementById('blockedModalTitle');
    el.blockedModalPrompt = document.getElementById('blockedModalPrompt');
    el.blockedClipsList = document.getElementById('blockedClipsList');
    el.btnCloseBlockedModal = document.getElementById('btnCloseBlockedModal');
    el.btnCancelBlockedModal = document.getElementById('btnCancelBlockedModal');
    el.btnRenderReviewedOnly = document.getElementById('btnRenderReviewedOnly');
  }

  // --- URL & Initialization ---
  function parseRoute() {
    // /zoom/<game_id>/<token_or_clip>
    const parts = window.location.pathname.split('/').filter(Boolean);
    if (parts.length >= 3 && parts[0] === 'zoom') {
      state.gameId = parts[1];
      state.tokenOrClip = parts[2];
    } else {
      console.warn('Unknown zoom path:', window.location.pathname);
    }
  }

  // --- In-Page Toast Notification System ---
  function showToast(message, type = 'info', durationMs = 3500, actionBtn = null) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const t = document.createElement('div');
    t.className = `app-toast toast-${type}`;

    const textSpan = document.createElement('span');
    textSpan.textContent = message;
    t.appendChild(textSpan);

    if (actionBtn && actionBtn.text && actionBtn.onClick) {
      const btn = document.createElement('button');
      btn.className = 'toast-action-btn';
      btn.textContent = actionBtn.text;
      btn.addEventListener('click', () => {
        actionBtn.onClick();
        t.remove();
      });
      t.appendChild(btn);
    }

    container.appendChild(t);

    let dismissTimer = null;
    let remainingMs = durationMs;
    let startTime = Date.now();

    function startTimer(delay) {
      dismissTimer = setTimeout(() => {
        t.classList.add('fade-out');
        setTimeout(() => t.remove(), 250);
      }, delay);
    }

    t.addEventListener('mouseenter', () => {
      if (dismissTimer) {
        clearTimeout(dismissTimer);
        dismissTimer = null;
        remainingMs -= (Date.now() - startTime);
        if (remainingMs < 1000) remainingMs = 1000;
      }
    });

    t.addEventListener('mouseleave', () => {
      startTime = Date.now();
      startTimer(remainingMs);
    });

    startTimer(durationMs);
  }

  async function loadData() {
    if (!state.gameId || !state.tokenOrClip) return;
    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/${state.tokenOrClip}`);
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        showToast(`Error loading zoom replay: ${err.description || resp.statusText}`, 'error');
        return;
      }
      const data = await resp.json();
      applyLoadedData(data);
    } catch (e) {
      console.error('Failed to load replay details:', e);
      showToast('Network error loading zoom replay.', 'error');
    }
  }

  function applyLoadedData(data) {
    state.canonicalToken = data.token;
    state.clipNum = data.clip;
    state.file = data.file;
    state.event = data.event || 0;
    state.actionEnd = data.action_end;
    state.allClips = data.all_zoom_clips || [];
    state.finalExists = data.final_exists;
    state.finalUrl = data.final_url;

    const r = data.replay || {};
    state.start = r.start !== undefined ? r.start : (data.default_window.start || (state.event - 2.5));
    state.dur = r.dur !== undefined ? r.dur : (data.default_window.dur || 4.5);
    state.cutStart = r.cut_start || 0.0;
    state.cutEnd = r.cut_end || 0.0;
    state.holdEnd = r.hold_end || 0.0;
    state.zoomTo = r.zoom_to || null;

    // Crop position & dimensions
    const cw = r.crop_w || (r.crop ? 1280 : 1536);
    state.cropW = cw;
    state.cropH = Math.round(cw * 9 / 16);
    state.zoomRatio = Number((REF_W / cw).toFixed(2));

    state.isUnplaced = (r.crop === null || r.crop === undefined);
    state.isReviewed = Boolean(r.reviewed);
    state.isAutoPlaced = Boolean(r.is_auto_placed);

    if (r.crop && Array.isArray(r.crop)) {
      state.baseCrop = [r.crop[0], r.crop[1]];
      // Clamp base crop to frame boundaries
      state.baseCrop[0] = Math.max(0, Math.min(REF_W - state.cropW, state.baseCrop[0]));
      state.baseCrop[1] = Math.max(0, Math.min(REF_H - state.cropH, state.baseCrop[1]));
      state.cropX = state.baseCrop[0];
      state.cropY = state.baseCrop[1];
    } else {
      state.baseCrop = null;
      state.cropX = 1280;
      state.cropY = 360;
    }

    // Pans
    state.pans = [];
    if (r.pan) {
      const pks = Array.isArray(r.pan[0]) ? r.pan : [r.pan];
      pks.forEach(k => {
        if (Array.isArray(k) && k.length >= 3) {
          const isGlide = k.length > 3 && k[3] > 0.05;
          const len = isGlide ? k[3] : 0.05;
          const at = k[2];
          const tArrival = isGlide ? Number((at + len / 2).toFixed(2)) : Number(at.toFixed(2));
          state.pans.push({
            mode: isGlide ? 'glide' : 'snap',
            x: k[0],
            y: k[1],
            at: at,
            len: len,
            tArrival: tArrival
          });
        }
      });
      state.pans.sort((a, b) => a.tArrival - b.tArrival);
    }

    state.isRemoved = Boolean(data.is_removed);

    // Status
    if (state.isRemoved) {
      state.status = 'removed';
    } else if (state.isUnplaced) {
      state.status = 'unplaced';
    } else if (!state.isReviewed) {
      state.status = 'unreviewed';
    } else if (state.finalExists && r.final_key) {
      let isPlanStale = Boolean(data.is_stale);
      if (r.history && r.history.length > 0) {
        const lastH = r.history[r.history.length - 1];
        if (lastH.window) {
          if (Math.abs(r.start - lastH.window[0]) > 0.05 || Math.abs(r.dur - lastH.window[1]) > 0.05) {
            isPlanStale = true;
          }
        }
        if (lastH.cut) {
          if (Math.abs((r.cut_start || 0) - lastH.cut[0]) > 0.05 || Math.abs((r.cut_end || 0) - lastH.cut[1]) > 0.05) {
            isPlanStale = true;
          }
        }
      }
      state.status = isPlanStale ? 'rendered (stale)' : 'rendered';
    } else if (r.history && r.history.length > 0) {
      state.status = r.reviewed ? 'reviewed' : 'edited';
    } else {
      state.status = 'needs render';
    }

    if (state.isRemoved) {
      if (el.btnRemoveZoom) el.btnRemoveZoom.style.display = 'none';
      if (el.btnRestoreZoom) el.btnRestoreZoom.style.display = 'inline-block';
      if (el.btnRenderExact) el.btnRenderExact.disabled = true;
    } else {
      if (el.btnRemoveZoom) el.btnRemoveZoom.style.display = 'inline-block';
      if (el.btnRestoreZoom) el.btnRestoreZoom.style.display = 'none';
      if (el.btnRenderExact) el.btnRenderExact.disabled = false;
    }

    // Homographies
    if (data.has_homographies) {
      if (data.exact_homographies === false) {
        el.lblHStatus.textContent = 'Ready (reused from older plan)';
        el.lblHStatus.style.color = '#E5C07B';
      } else {
        el.lblHStatus.textContent = 'Ready (H.json)';
        el.lblHStatus.style.color = '#72E098';
      }
      fetchHomographies();
    } else {
      el.lblHStatus.textContent = 'Not computed';
      el.lblHStatus.style.color = '#A6ADA8';
    }

    // Update Header
    el.clipTitleText.textContent = `Clip ${state.clipNum}`;
    el.clipTokenText.textContent = `(${state.canonicalToken})`;
    updateStatusBadge(state.status);

    if (state.finalExists) {
      el.btnWatchFinal.style.display = 'inline-block';
    } else {
      el.btnWatchFinal.style.display = 'none';
    }

    updateNavButtons();
    updateInspectorFields();

    // Load video
    if (data.video && data.video.url) {
      const doInitialSeek = () => {
        seekToSource(state.start);
        updateCropBoxScreen();
      };
      if (el.mainVideo.src && el.mainVideo.src.endsWith(data.video.url) && el.mainVideo.readyState >= 1) {
        doInitialSeek();
      } else {
        el.mainVideo.src = data.video.url;
        el.mainVideo.onloadedmetadata = doInitialSeek;
        if (el.mainVideo.readyState >= 1) {
          doInitialSeek();
        }
      }
    }
    state.hasUnsavedChanges = false;
  }

  function updateStatusBadge(status) {
    el.clipStatusBadge.className = 'status-badge';
    el.clipStatusBadge.textContent = `status: ${status}`;
    if (status === 'rendered') el.clipStatusBadge.classList.add('status-rendered');
    else if (status === 'rendered (stale)' || status === 'stale') {
      el.clipStatusBadge.classList.add('status-stale');
      el.clipStatusBadge.textContent = 'status: RENDERED (stale)';
    }
    else if (status === 'reviewed') {
      el.clipStatusBadge.classList.add('status-reviewed');
      el.clipStatusBadge.textContent = 'status: REVIEWED (not rendered yet)';
    }
    else if (status === 'edited') {
      el.clipStatusBadge.classList.add('status-edited');
      el.clipStatusBadge.textContent = 'status: EDITED (not reviewed)';
    }
    else if (status === 'needs render') el.clipStatusBadge.classList.add('status-needs-render');
    else if (status === 'unreviewed' || status === 'auto-placed') el.clipStatusBadge.classList.add('status-auto');
    else if (status === 'unplaced' || status === 'not started' || status === 'removed') el.clipStatusBadge.classList.add('status-not-started');
    else el.clipStatusBadge.classList.add('status-not-started');
  }

  function updateNavButtons() {
    const idx = state.allClips.findIndex(c => c.token === state.canonicalToken);
    const unrevCount = state.allClips.filter(c => !c.reviewed).length;
    if (idx !== -1) {
      let infoText = `${idx + 1} / ${state.allClips.length}`;
      if (unrevCount > 0) {
        infoText += ` (${unrevCount} unreviewed)`;
      }
      el.clipIndexIndicator.textContent = infoText;
      el.btnPrevZoom.disabled = idx <= 0;
      el.btnNextZoom.disabled = idx >= state.allClips.length - 1;
    } else {
      el.clipIndexIndicator.textContent = '-- / --';
      el.btnPrevZoom.disabled = true;
      el.btnNextZoom.disabled = true;
    }
  }

  function navigateToClip(delta) {
    const idx = state.allClips.findIndex(c => c.token === state.canonicalToken);
    if (idx === -1) return;
    const target = state.allClips[idx + delta];
    if (target) {
      window.location.href = `/zoom/${state.gameId}/${target.token}`;
    }
  }

  // --- Coordinate Mapping & Crop Box ---
  function getScale() {
    const rect = el.videoStage.getBoundingClientRect();
    return rect.width / REF_W;
  }

  function updateCropBoxScreen(overrideX, overrideY) {
    if (state.isUnplaced || state.baseCrop === null) {
      if (el.cropBox) el.cropBox.style.display = 'none';
      if (el.unplacedNotice) el.unplacedNotice.style.display = 'flex';
      return;
    } else {
      if (el.cropBox) el.cropBox.style.display = 'block';
      if (el.unplacedNotice) el.unplacedNotice.style.display = 'none';
    }

    const scale = getScale();
    if (!scale || scale <= 0) return;

    const curX = (overrideX !== undefined) ? overrideX : state.cropX;
    const curY = (overrideY !== undefined) ? overrideY : state.cropY;

    const screenX = curX * scale;
    const screenY = curY * scale;
    const screenW = state.cropW * scale;
    const screenH = state.cropH * scale;

    el.cropBox.style.left = `${screenX}px`;
    el.cropBox.style.top = `${screenY}px`;
    el.cropBox.style.width = `${screenW}px`;
    el.cropBox.style.height = `${screenH}px`;

    el.cropTag.textContent = `${state.zoomRatio.toFixed(2)}x | ${state.cropW}px`;
    el.lblZoomVal.textContent = `${state.zoomRatio.toFixed(2)}x`;
    el.lblCropW.textContent = `${state.cropW}`;
    el.lblCropH.textContent = `${state.cropH}`;
    el.lblCropX.textContent = `${Math.round(curX)}`;
    el.lblCropY.textContent = `${Math.round(curY)}`;
    el.zoomSlider.value = state.zoomRatio;

    // Highlight matching preset button if any
    document.querySelectorAll('.btn-preset').forEach(b => {
      const z = parseFloat(b.dataset.zoom);
      b.classList.toggle('active', Math.abs(z - state.zoomRatio) < 0.06);
    });
  }

  function setZoomRatio(zoom, preserveCenter = true) {
    state.hasUnsavedChanges = true;
    const z = Math.max(1.5, Math.min(5.0, zoom));
    state.zoomRatio = Number(z.toFixed(2));
    const newW = Math.round(REF_W / state.zoomRatio);
    const newH = Math.round(newW * 9 / 16);

    if (preserveCenter) {
      const centerX = state.cropX + state.cropW / 2;
      const centerY = state.cropY + state.cropH / 2;
      state.cropX = Math.round(centerX - newW / 2);
      state.cropY = Math.round(centerY - newH / 2);
    }

    state.cropW = newW;
    state.cropH = newH;
    clampCrop();
    const replaySec = (el.mainVideo && !isNaN(el.mainVideo.currentTime)) ? (el.mainVideo.currentTime - state.start) / state.speed : 0;
    if (state.pans.length === 0 || replaySec <= 0.2) {
      if (!state.baseCrop) state.baseCrop = [state.cropX, state.cropY];
      else {
        state.baseCrop[0] = state.cropX;
        state.baseCrop[1] = state.cropY;
      }
      state.isAutoPlaced = false;
    }
    updateCropBoxScreen();
  }

  function clampCrop() {
    const maxX = Math.max(0, REF_W - state.cropW);
    const maxY = Math.max(0, REF_H - state.cropH);
    state.cropX = Math.max(0, Math.min(maxX, state.cropX));
    state.cropY = Math.max(0, Math.min(maxY, state.cropY));
  }

  // --- Drag & Resize Handling ---
  let isDragging = false;
  let isResizing = false;
  let activeHandle = null;
  let dragStartX = 0;
  let dragStartY = 0;
  let initialCropX = 0;
  let initialCropY = 0;
  let initialCropW = 0;
  let dragStartBaseCrop = [0, 0];

  function initDragAndDrop() {
    el.cropBox.addEventListener('mousedown', (e) => {
      if (e.target.classList.contains('crop-handle')) return;
      isDragging = true;
      dragStartX = e.clientX;
      dragStartY = e.clientY;
      initialCropX = state.cropX;
      initialCropY = state.cropY;
      dragStartBaseCrop = state.baseCrop ? [state.baseCrop[0], state.baseCrop[1]] : [state.cropX, state.cropY];
      e.preventDefault();
    });

    el.cropOverlay.querySelectorAll('.crop-handle').forEach(h => {
      h.addEventListener('mousedown', (e) => {
        isResizing = true;
        activeHandle = h.dataset.handle;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        initialCropX = state.cropX;
        initialCropY = state.cropY;
        initialCropW = state.cropW;
        dragStartBaseCrop = state.baseCrop ? [state.baseCrop[0], state.baseCrop[1]] : [state.cropX, state.cropY];
        e.stopPropagation();
        e.preventDefault();
      });
    });

    window.addEventListener('mousemove', (e) => {
      const scale = getScale();
      if (!scale) return;

      if (isDragging) {
        const dx = (e.clientX - dragStartX) / scale;
        const dy = (e.clientY - dragStartY) / scale;
        state.cropX = Math.round(initialCropX + dx);
        state.cropY = Math.round(initialCropY + dy);

        if (el.chkSnap.checked) {
          // Snap to 6x6 tile grid (each tile is 640x360)
          const tileW = REF_W / 6;
          const tileH = REF_H / 6;
          state.cropX = Math.round(state.cropX / tileW) * tileW;
          state.cropY = Math.round(state.cropY / tileH) * tileH;
        }

        clampCrop();
        state.isAutoPlaced = false;
        state.isUnplaced = false;
        const replaySec = (el.mainVideo && !isNaN(el.mainVideo.currentTime)) ? (el.mainVideo.currentTime - state.start) / state.speed : 0;
        const existingKf = state.pans.find(p => Math.abs(p.tArrival - replaySec) <= 0.15);
        if (!existingKf) {
          if (!state.baseCrop) state.baseCrop = [state.cropX, state.cropY];
          else {
            state.baseCrop[0] = state.cropX;
            state.baseCrop[1] = state.cropY;
          }
        }
        updateCropBoxScreen();
      } else if (isResizing) {
        state.isAutoPlaced = false;
        state.isUnplaced = false;
        const dx = (e.clientX - dragStartX) / scale;
        let deltaW = 0;
        if (activeHandle === 'se' || activeHandle === 'ne') deltaW = dx;
        else deltaW = -dx;

        const candidateW = Math.max(REF_W / 5.0, Math.min(REF_W / 1.5, initialCropW + deltaW));
        setZoomRatio(REF_W / candidateW, false);
      }
    });

    window.addEventListener('mouseup', () => {
      if (isDragging || isResizing) {
        state.hasUnsavedChanges = true;
        const wasDragging = isDragging;
        isDragging = false;
        isResizing = false;
        activeHandle = null;

        if (wasDragging) {
          const replaySec = (el.mainVideo && !isNaN(el.mainVideo.currentTime)) ? (el.mainVideo.currentTime - state.start) / state.speed : 0;
          const distMoved = Math.hypot(state.cropX - initialCropX, state.cropY - initialCropY);
          const existingKf = state.pans.find(p => Math.abs(p.tArrival - replaySec) <= 0.15);

          updateKeyframeAtPlayheadIfExists();

          if (distMoved > 4 && replaySec > 0.3 && !existingKf) {
            const draggedX = state.cropX;
            const draggedY = state.cropY;
            showToast(
              'Moved the START box. Press K first to add a pan at this time',
              'info',
              10000,
              {
                text: 'Make this a pan keyframe instead',
                onClick: () => {
                  // 1. Undo the start move
                  state.baseCrop[0] = dragStartBaseCrop[0];
                  state.baseCrop[1] = dragStartBaseCrop[1];
                  // 2. Create the keyframe at replaySec with dragged coordinates
                  const len = 1.2;
                  const at = Math.max(len / 2, Number((replaySec - len / 2).toFixed(3)));
                  const tArrival = Number((at + len / 2).toFixed(2));
                  state.pans.push({
                    mode: 'glide',
                    x: draggedX,
                    y: draggedY,
                    at: at,
                    len: len,
                    tArrival: tArrival
                  });
                  state.pans.sort((a, b) => a.tArrival - b.tArrival);
                  renderKeyframesList();
                  renderScrubberKeyframes();
                  updateTimelineUI();
                  updateCropBoxScreen();
                }
              }
            );
          }
        }
      }
    });

    window.addEventListener('resize', () => {
      updateCropBoxScreen();
    });
  }

  // --- Transport & Timeline ---
  function formatTime(seconds) {
    if (isNaN(seconds) || seconds < 0) return '00:00.0';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m.toString().padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`;
  }

  function seekToSource(timeSec) {
    const t = Math.max(0, Math.min(el.mainVideo.duration || 99999, timeSec));
    el.mainVideo.currentTime = t;
    updateTimelineUI();
  }

  function stepSeconds(deltaSec) {
    seekToSource(el.mainVideo.currentTime + deltaSec);
  }

  function togglePlayPause() {
    if (el.mainVideo.paused) {
      // If past end of window, wrap to start
      if (el.mainVideo.currentTime >= state.start + state.dur - 0.05) {
        el.mainVideo.currentTime = state.start;
      }
      el.mainVideo.playbackRate = state.speed;
      el.mainVideo.play();
      el.btnPlayPause.textContent = '⏸ PAUSE';
      el.btnPlayPause.classList.add('playing');
      state.isPlaying = true;
    } else {
      el.mainVideo.pause();
      el.btnPlayPause.textContent = `▶ PLAY (${state.speed}x)`;
      el.btnPlayPause.classList.remove('playing');
      state.isPlaying = false;
    }
  }

  function updateTimelineUI() {
    const cur = el.mainVideo.currentTime;
    el.txtSourceTime.textContent = formatTime(cur);
    el.txtEventTime.textContent = formatTime(state.event);

    const replayElapsed = Math.max(0, (cur - state.start) / state.speed);
    const replayTotal = state.dur / state.speed;
    el.txtReplayTime.textContent = `${replayElapsed.toFixed(1)}s / ${replayTotal.toFixed(1)}s`;

    // Loop check
    if (state.isPlaying && el.chkLoop.checked) {
      if (cur >= state.start + state.dur) {
        el.mainVideo.currentTime = state.start;
      }
    }

    // Scrubber Playhead
    const progress = Math.max(0, Math.min(1.0, (cur - state.start) / Math.max(0.1, state.dur)));
    el.scrubberPlayhead.style.left = `${progress * 100}%`;

    // Trims UI
    const trimLeftPct = Math.min(50, (state.cutStart * state.speed / state.dur) * 100);
    const trimRightPct = Math.min(50, (state.cutEnd * state.speed / state.dur) * 100);
    el.scrubberTrimLeft.style.width = `${trimLeftPct}%`;
    el.scrubberTrimRight.style.width = `${trimRightPct}%`;
    el.scrubberTrimRight.style.right = '0';

    // When paused or seeking, update display box to interpolated position without mutating baseCrop
    if (!isDragging && !isResizing && !state.isReplayPreview) {
      const pos = interpolatePan(replayElapsed);
      state.cropX = pos.x;
      state.cropY = pos.y;
      updateCropBoxScreen(pos.x, pos.y);
    }

    // Keyframe hint and mode coloring (amber for START, blue for keyframe)
    if (el.lblKeyframeHint && el.cropBox) {
      const kf = state.pans.find(p => Math.abs(p.tArrival - replayElapsed) <= 0.15);
      if (kf) {
        el.lblKeyframeHint.textContent = `Editing keyframe at ${kf.tArrival.toFixed(1)}s`;
        el.lblKeyframeHint.className = 'keyframe-hint-bar kf-active';
        el.cropBox.classList.remove('mode-start');
        el.cropBox.classList.add('mode-keyframe');
      } else {
        el.lblKeyframeHint.textContent = 'Editing START box. Step to a later moment and press K to add a pan keyframe there, then drag the box.';
        el.lblKeyframeHint.className = 'keyframe-hint-bar start-active';
        el.cropBox.classList.remove('mode-keyframe');
        el.cropBox.classList.add('mode-start');
      }
    }
  }

  function initScrubber() {
    el.scrubberTrack.addEventListener('mousedown', (e) => {
      const rect = el.scrubberTrack.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      seekToSource(state.start + pct * state.dur);
    });
  }

  // --- Inspector & Settings Updates ---
  function updateInspectorFields() {
    el.inpWinStartOffset.value = (state.start - state.event).toFixed(1);
    el.inpWinEndOffset.value = (state.start + state.dur - state.event).toFixed(1);
    el.inpCutStart.value = state.cutStart.toFixed(1);
    el.inpCutEnd.value = state.cutEnd.toFixed(1);
    el.inpHoldEnd.value = state.holdEnd.toFixed(1);

    const totalReplay = (state.dur / state.speed).toFixed(1);
    el.lblWindowSummary.textContent = `${state.dur.toFixed(1)}s source = ${totalReplay}s replay`;
    el.txtSpeedLabel.textContent = `${state.speed}x`;

    renderKeyframesList();
    renderScrubberKeyframes();
    updateTimelineUI();
  }

  // --- Keyframes & Pans ---
  function renderKeyframesList() {
    el.keyframesList.innerHTML = '';

    // Always keyframe 0 at window start
    const kf0 = document.createElement('div');
    kf0.className = 'keyframe-row';
    const posStr = state.baseCrop ? `(${state.baseCrop[0]}, ${state.baseCrop[1]})` : '(Unplaced)';
    kf0.innerHTML = `
      <span class="kf-time">0.0s (Start)</span>
      <span class="kf-pos">${posStr}</span>
      <span class="kf-mode" style="color:var(--text-muted);">Anchor</span>
      <span style="width:20px;"></span>
    `;
    el.keyframesList.appendChild(kf0);

    state.pans.forEach((p, idx) => {
      const row = document.createElement('div');
      row.className = 'keyframe-row';
      row.innerHTML = `
        <span class="kf-time">${p.tArrival.toFixed(1)}s</span>
        <span class="kf-pos">(${Math.round(p.x)}, ${Math.round(p.y)})</span>
        <span class="kf-mode">
          <select data-idx="${idx}" class="sel-kf-mode">
            <option value="glide" ${p.mode === 'glide' ? 'selected' : ''}>Glide</option>
            <option value="snap" ${p.mode === 'snap' ? 'selected' : ''}>Snap</option>
          </select>
        </span>
        <button class="kf-del-btn" data-idx="${idx}" title="Delete keyframe">✕</button>
      `;
      el.keyframesList.appendChild(row);
    });

    el.keyframesList.querySelectorAll('.sel-kf-mode').forEach(sel => {
      sel.addEventListener('change', (e) => {
        state.hasUnsavedChanges = true;
        const i = parseInt(e.target.dataset.idx, 10);
        const p = state.pans[i];
        p.mode = e.target.value;
        if (p.mode === 'glide') {
          p.len = 1.2;
          p.at = Math.max(p.len / 2, Number((p.tArrival - p.len / 2).toFixed(3)));
          p.tArrival = Number((p.at + p.len / 2).toFixed(2));
        } else {
          p.mode = 'snap';
          p.len = 0.05;
          p.at = p.tArrival;
        }
        renderKeyframesList();
        renderScrubberKeyframes();
        updateTimelineUI();
      });
    });

    el.keyframesList.querySelectorAll('.kf-del-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        state.hasUnsavedChanges = true;
        const i = parseInt(e.target.dataset.idx, 10);
        state.pans.splice(i, 1);
        renderKeyframesList();
        renderScrubberKeyframes();
        updateTimelineUI();
      });
    });
  }

  function renderScrubberKeyframes() {
    el.scrubberKeyframes.innerHTML = '';
    const totalReplay = state.dur / state.speed;
    state.pans.forEach(p => {
      const pct = Math.max(0, Math.min(100, (p.tArrival / totalReplay) * 100));
      const m = document.createElement('div');
      m.className = 'keyframe-marker';
      m.style.left = `${pct}%`;
      m.title = `Keyframe @ ${p.tArrival.toFixed(1)}s (${p.mode})`;
      el.scrubberKeyframes.appendChild(m);
    });
  }

  function addKeyframeAtPlayhead() {
    state.hasUnsavedChanges = true;
    const cur = el.mainVideo.currentTime;
    const replaySec = Math.max(0.1, Number(((cur - state.start) / state.speed).toFixed(2)));
    const totalReplay = state.dur / state.speed;
    if (replaySec >= totalReplay) return;

    // Check if keyframe already exists nearby (by arrival time)
    const existing = state.pans.find(p => Math.abs(p.tArrival - replaySec) < 0.2);
    if (existing) {
      existing.x = state.cropX;
      existing.y = state.cropY;
    } else {
      const len = 1.2;
      const at = Math.max(len / 2, Number((replaySec - len / 2).toFixed(3)));
      const tArrival = Number((at + len / 2).toFixed(2));
      state.pans.push({
        mode: 'glide',
        x: state.cropX,
        y: state.cropY,
        at: at,
        len: len,
        tArrival: tArrival
      });
      state.pans.sort((a, b) => a.tArrival - b.tArrival);
    }
    renderKeyframesList();
    renderScrubberKeyframes();
    updateTimelineUI();
  }

  function updateKeyframeAtPlayheadIfExists() {
    const cur = el.mainVideo.currentTime;
    const replaySec = (cur - state.start) / state.speed;
    const existing = state.pans.find(p => Math.abs(p.tArrival - replaySec) < 0.2);
    if (existing) {
      existing.x = state.cropX;
      existing.y = state.cropY;
      state.isAutoPlaced = false;
      renderKeyframesList();
    } else if (state.pans.length === 0 || replaySec <= 0.2) {
      if (!state.baseCrop) state.baseCrop = [state.cropX, state.cropY];
      else {
        state.baseCrop[0] = state.cropX;
        state.baseCrop[1] = state.cropY;
      }
      state.isAutoPlaced = false;
      renderKeyframesList();
    }
  }

  // --- Preview Replay (Client-side animated preview) ---
  function playReplayPreview() {
    if (state.isReplayPreview) {
      stopReplayPreview();
      return;
    }

    state.isReplayPreview = true;
    el.btnPreviewReplay.textContent = '⏹ Stop Preview';
    seekToSource(state.start);
    el.mainVideo.playbackRate = state.speed;
    el.mainVideo.play();

    function tick() {
      if (!state.isReplayPreview) return;
      const cur = el.mainVideo.currentTime;
      if (cur >= state.start + state.dur) {
        seekToSource(state.start);
      }

      // Compute animated box position at current replay time
      const replaySec = (cur - state.start) / state.speed;
      const pos = interpolatePan(replaySec);
      // Move display box ONLY - DO NOT mutate state.baseCrop
      updateCropBoxScreen(pos.x, pos.y);

      state.previewRaf = requestAnimationFrame(tick);
    }
    state.previewRaf = requestAnimationFrame(tick);
  }

  function stopReplayPreview() {
    state.isReplayPreview = false;
    if (state.previewRaf) cancelAnimationFrame(state.previewRaf);
    el.btnPreviewReplay.textContent = '▶ Preview Replay (R)';
    el.mainVideo.pause();
    const cur = el.mainVideo.currentTime;
    const replaySec = Math.max(0, (cur - state.start) / state.speed);
    const pos = interpolatePan(replaySec);
    state.cropX = pos.x;
    state.cropY = pos.y;
    updateCropBoxScreen(pos.x, pos.y);
  }

  function interpolatePan(replaySec) {
    const fallbackX = state.baseCrop ? state.baseCrop[0] : (state.cropX || 1280);
    const fallbackY = state.baseCrop ? state.baseCrop[1] : (state.cropY || 360);
    if (!state.pans.length) return { x: fallbackX, y: fallbackY };

    let curX = fallbackX;
    let curY = fallbackY;
    let ox = fallbackX;
    let oy = fallbackY;

    // Evaluate each pan keyframe sequentially matching zoom_clip.py smoothstep logic
    for (let k = 0; k < state.pans.length; k++) {
      const p = state.pans[k];
      const rampDur = (p.len || 1.2);
      const startTime = p.at - rampDur / 2;
      const u = Math.min(1.0, Math.max(0.0, (replaySec - startTime) / rampDur));
      const m = u * u * (3 - 2 * u); // Smoothstep
      curX += (p.x - ox) * m;
      curY += (p.y - oy) * m;
      ox = p.x;
      oy = p.y;
    }
    return { x: Math.round(curX), y: Math.round(curY) };
  }

  // --- Homographies / Stabilization ---
  async function fetchHomographies() {
    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/${state.canonicalToken}/homographies`);
      if (resp.ok) {
        const data = await resp.json();
        state.homographies = data.homographies;
        if (data.exact === false) {
          el.lblHStatus.textContent = 'Ready (reused from older plan)';
          el.lblHStatus.style.color = '#E5C07B';
        } else {
          el.lblHStatus.textContent = `Ready (${data.count} frames)`;
          el.lblHStatus.style.color = '#72E098';
        }
      }
    } catch (e) {
      console.warn('Homographies fetch error:', e);
    }
  }

  async function prepareHomographies() {
    el.lblHStatus.textContent = 'Computing H.json...';
    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/${state.canonicalToken}/prepare`, {
        method: 'POST'
      });
      const data = await resp.json();
      if (data.status === 'ready') {
        el.lblHStatus.textContent = 'Ready (H.json)';
        el.lblHStatus.style.color = '#72E098';
        fetchHomographies();
      } else if (data.task_id) {
        openLogDrawer(data.task_id, 'Compute Homographies');
      }
    } catch (e) {
      showToast('Failed to launch homography preparation.', 'error');
    }
  }

  // --- Backend Persistence & Render ---
  function buildSpecPayload() {
    const payload = {
      token: state.canonicalToken,
      clip: state.clipNum,
      crop: state.baseCrop ? [state.baseCrop[0], state.baseCrop[1]] : null,
      is_auto_placed: state.isAutoPlaced,
      reviewed: state.isReviewed,
      start: Number(state.start.toFixed(3)),
      dur: Number(state.dur.toFixed(3)),
      cut_start: Number(state.cutStart.toFixed(3)),
      cut_end: Number(state.cutEnd.toFixed(3)),
      pans: state.pans.map(p => {
        if (p.mode === 'glide') {
          return [Number(p.x), Number(p.y), Number(p.at.toFixed(3)), Number((p.len || 1.2).toFixed(2))];
        } else {
          return [Number(p.x), Number(p.y), Number(p.at.toFixed(3)), 0.05];
        }
      }),
      zoom_to: state.zoomTo,
      hold_end: Number(state.holdEnd.toFixed(3)),
    };
    if (state.cropW !== 1280) {
      payload.crop_w = state.cropW;
    }
    return payload;
  }

  async function savePlan() {
    if (state.isUnplaced || !state.baseCrop) {
      showToast('Clip is unplaced. Click on the video stage to place the crop box before saving.', 'error');
      return;
    }
    // If auto-placed and user hasn't explicitly approved ("Looks Good") or nudged/adjusted the crop:
    // keep reviewed = false!
    if (state.isAutoPlaced && !state.hasExplicitApproval) {
      state.isReviewed = false;
    } else {
      state.isReviewed = true;
    }
    const payload = buildSpecPayload();
    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/${state.canonicalToken}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        showToast(`Error saving plan: ${err.error || resp.statusText}`, 'error');
        return;
      }
      const res = await resp.json();
      state.hasUnsavedChanges = false;
      const cur = state.allClips.find(c => c.token === state.canonicalToken);
      if (cur) {
        cur.reviewed = state.isReviewed;
        cur.is_auto_placed = state.isAutoPlaced;
      }
      if (state.finalExists) {
        state.status = 'rendered (stale)';
        updateStatusBadge('rendered (stale)');
      } else if (!state.isReviewed) {
        state.status = 'unreviewed';
        updateStatusBadge('unreviewed');
      } else {
        state.status = state.isAutoPlaced ? 'auto-placed' : (state.isReviewed ? 'reviewed' : 'edited');
        updateStatusBadge(state.status);
      }
      if (state.isReviewed) {
        flashBadge('Saved', '#72E098');
        showToast('Replay plan saved.', 'success');
      } else {
        flashBadge('Saved (Unreviewed)', '#F59E0B');
        showToast('Plan saved, but remains UNREVIEWED until nudged or approved via "Looks Good".', 'warning', 6000);
      }
      updateNavButtons();
      updateRenderButtonText();
      if (window.opener && window.opener.loadGame) {
        window.opener.loadGame(state.gameId);
      }
    } catch (e) {
      showToast('Network error saving plan.', 'error');
    }
  }

  function showBlockedClipsModal(data) {
    if (!el.blockedClipsModal) return;
    if (el.blockedModalTitle) {
      el.blockedModalTitle.textContent = `⚠️ ${(data.unreviewed_clips || []).length} Zoom Clips Unreviewed`;
    }
    if (el.blockedModalPrompt) {
      el.blockedModalPrompt.textContent = data.message || 'The following clips have not been reviewed or adjusted. To prevent misframed output, silent center crops cannot be rendered.';
    }

    if (el.blockedClipsList) {
      el.blockedClipsList.innerHTML = '';
      (data.unreviewed_clips || []).forEach(c => {
        const a = document.createElement('a');
        a.href = `/zoom.html?game=${encodeURIComponent(state.gameId)}&clip=${c.n}`;
        a.className = 'blocked-clip-link';
        a.style.display = 'flex';
        a.style.justifyContent = 'space-between';
        a.style.padding = '8px 10px';
        a.style.margin = '4px 0';
        a.style.borderRadius = '4px';
        a.style.background = 'rgba(255,255,255,0.06)';
        a.style.color = '#93C5FD';
        a.style.textDecoration = 'none';
        a.style.fontSize = '13px';
        a.innerHTML = `<span><strong>Clip ${c.n}</strong> (${c.token})</span> <span style="color:#FCA5A5; font-size:12px;">${c.reason} →</span>`;
        el.blockedClipsList.appendChild(a);
      });
    }

    if (data.reviewed_count > 0 && el.btnRenderReviewedOnly) {
      el.btnRenderReviewedOnly.style.display = 'inline-block';
      el.btnRenderReviewedOnly.textContent = `Render Reviewed Only (${data.reviewed_count} clips)`;
      el.btnRenderReviewedOnly.onclick = () => {
        closeBlockedClipsModal();
        renderExact({ reviewed_only: true });
      };
    } else if (el.btnRenderReviewedOnly) {
      el.btnRenderReviewedOnly.style.display = 'none';
    }

    el.blockedClipsModal.style.display = 'flex';
  }

  function closeBlockedClipsModal() {
    if (el.blockedClipsModal) el.blockedClipsModal.style.display = 'none';
  }

  async function renderExact(opts = {}) {
    const scope = el.selRenderScope.value;
    const reviewedOnly = Boolean(opts.reviewed_only);

    if (scope === 'current') {
      const isReviewed = state.currentReplay && state.currentReplay.reviewed;
      if (!isReviewed && !state.hasUnsavedChanges && state.currentReplay && state.currentReplay.is_auto_placed) {
        showToast('This clip is unreviewed. Please adjust the crop box and save plan before rendering.', 'warning', 4000);
        return;
      }
    }

    const payload = {
      scope: scope,
      spec: buildSpecPayload(),
      reviewed_only: reviewedOnly
    };

    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/${state.canonicalToken}/render`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        if (err.error === 'unreviewed_clips_exist') {
          showBlockedClipsModal(err);
          return;
        }
        showToast(`Error initiating render: ${err.message || err.description || resp.statusText}`, 'error', 4000);
        return;
      }
      const data = await resp.json();
      const taskLabel = scope === 'all'
        ? (reviewedOnly ? `Render Reviewed Zoom Clips` : 'Render All Zoom Clips')
        : `Render Clip ${state.clipNum}`;
      openLogDrawer(data.task_id, `${taskLabel} & Verify`);
    } catch (e) {
      showToast('Failed to launch render task.', 'error');
    }
  }

  // Warn before the tab is closed/reloaded with an unsaved zoom plan.
  window.addEventListener('beforeunload', (e) => {
    if (state.hasUnsavedChanges) {
      e.preventDefault();
      e.returnValue = '';
    }
  });

  function openUnsavedModal() {
    if (el.unsavedModalPrompt) {
      el.unsavedModalPrompt.textContent = `You have unsaved changes to clip ${state.clipNum}. Discard changes and return to the Review Editor?`;
    }
    if (el.unsavedZoomModal) {
      el.unsavedZoomModal.style.display = 'flex';
    }
  }

  function closeUnsavedModal() {
    if (el.unsavedZoomModal) {
      el.unsavedZoomModal.style.display = 'none';
    }
  }

  function closeOrReturnToReview(force = false) {
    if (!force && state.hasUnsavedChanges) {
      openUnsavedModal();
      return;
    }
    if (window.opener && !window.opener.closed) {
      try {
        if (typeof window.opener.loadGame === 'function') {
          window.opener.loadGame(state.gameId);
        } else {
          window.opener.location.reload();
        }
      } catch (e) {
        try { window.opener.location.reload(); } catch (_) {}
      }
      try {
        window.opener.focus();
      } catch (_) {}
      window.close();
      setTimeout(() => {
        if (!window.closed) {
          window.location.href = `/?game=${encodeURIComponent(state.gameId)}`;
        }
      }, 250);
    } else {
      window.location.href = `/?game=${encodeURIComponent(state.gameId)}`;
    }
  }

  async function restoreZoom() {
    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/${state.canonicalToken || state.tokenOrClip}/restore`, {
        method: 'POST'
      });
      if (resp.ok) {
        state.isRemoved = false;
        if (el.btnRemoveZoom) el.btnRemoveZoom.style.display = 'inline-block';
        if (el.btnRestoreZoom) el.btnRestoreZoom.style.display = 'none';
        if (el.btnRenderExact) el.btnRenderExact.disabled = false;
        showToast(`Zoom replay restored for clip ${state.clipNum}. Review table updated.`, 'success', 3000);
        await loadData();
        if (window.opener && !window.opener.closed) {
          try {
            if (typeof window.opener.loadGame === 'function') {
              window.opener.loadGame(state.gameId);
            }
          } catch (_) {}
        }
      } else {
        const err = await resp.json().catch(() => ({}));
        showToast(`Failed to restore zoom replay: ${err.description || resp.statusText}`, 'error');
      }
    } catch (e) {
      showToast('Network error restoring zoom replay.', 'error');
    }
  }

  function openRemoveZoomModal() {
    if (el.removeZoomModalPrompt) {
      el.removeZoomModalPrompt.textContent = `Remove zoom from clip ${state.clipNum}? The normal clip stays.`;
    }
    if (el.removeZoomModal) {
      el.removeZoomModal.style.display = 'flex';
    }
  }

  function closeRemoveZoomModal() {
    if (el.removeZoomModal) {
      el.removeZoomModal.style.display = 'none';
    }
  }

  async function executeRemoveZoom() {
    closeRemoveZoomModal();
    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/${state.canonicalToken}/remove`, {
        method: 'POST'
      });
      if (resp.ok) {
        showToast(`Zoom tag removed for clip ${state.clipNum}. Returning to Review Editor.`, 'success', 2000);
        setTimeout(() => {
          closeOrReturnToReview(true);
        }, 500);
      } else {
        const err = await resp.json().catch(() => ({}));
        showToast(`Failed to remove zoom tag: ${err.description || resp.statusText}`, 'error');
      }
    } catch (e) {
      showToast('Network error removing zoom tag.', 'error');
    }
  }

  function flashBadge(text, color) {
    el.verifyResultBadge.style.display = 'inline-block';
    el.verifyResultBadge.textContent = text;
    el.verifyResultBadge.style.borderColor = color;
    el.verifyResultBadge.style.color = color;
    setTimeout(() => {
      el.verifyResultBadge.style.display = 'none';
    }, 4500);
  }

  function updateRenderButtonText() {
    const unrevCount = (state.allClips || []).filter(c => !c.reviewed).length;
    const scope = el.selRenderScope ? el.selRenderScope.value : 'current';
    if (scope === 'all') {
      el.btnRenderExact.textContent = unrevCount > 0 ? `⚡ Render All (${unrevCount} unreviewed)` : '⚡ Render All';
    } else {
      el.btnRenderExact.textContent = '⚡ Render exact';
    }
  }

  async function applyAutoFrameCurrent() {
    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/auto-frame`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: state.canonicalToken })
      });
      const data = await resp.json();
      if (resp.ok && data.success) {
        state.baseCrop = [1152, 450];
        state.cropX = 1152;
        state.cropY = 450;
        state.cropW = 1536;
        state.cropH = 864;
        state.zoomRatio = 2.5;
        state.isUnplaced = false;
        state.isReviewed = false;
        state.isAutoPlaced = true;
        state.hasUnsavedChanges = true;
        updateStatusBadge('unreviewed');
        updateCropBoxScreen();
        updateNavButtons();
        updateRenderButtonText();
        showToast('Auto-framed at 2.5x default (1536x864). Review framing and click Save Plan to confirm.', 'success');
      } else {
        showToast(data.message || 'Failed to auto-frame clip', 'error');
      }
    } catch (e) {
      showToast('Network error while auto-framing.', 'error');
    }
  }

  async function applyAutoFrameAll() {
    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/auto-frame`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ all_unplaced: true })
      });
      const data = await resp.json();
      if (resp.ok && data.success) {
        showToast(`Auto-framed ${data.count} unplaced clips! Refreshing...`, 'success');
        setTimeout(() => location.reload(), 700);
      } else {
        showToast(data.message || 'Failed to auto-frame all clips', 'error');
      }
    } catch (e) {
      showToast('Network error while auto-framing all.', 'error');
    }
  }

  async function checkProductionLock() {
    if (!state.gameId) return;
    try {
      const resp = await fetch(`/api/game/${state.gameId}/production/status`);
      if (resp.ok) {
        const data = await resp.json();
        if (data.status === 'running') {
          if (el.productionLockBanner) {
            el.productionLockBanner.style.display = 'block';
            if (el.lblLockPid) el.lblLockPid.textContent = data.pid || '--';
          }
          if (el.btnRenderExact) {
            el.btnRenderExact.disabled = true;
            el.btnRenderExact.title = 'Zoom render locked while 4K production is running';
          }
        } else {
          if (el.productionLockBanner) el.productionLockBanner.style.display = 'none';
          if (el.btnRenderExact && !state.isRemoved) {
            el.btnRenderExact.disabled = false;
            el.btnRenderExact.title = 'Run background 720p render';
          }
        }
      }
    } catch (_) {}
  }

  // --- Streaming Log Drawer (SSE) ---
  let activeEventSource = null;
  let lastVerifyResult = null;

  function parseVerifyLine(line) {
    if (!line) return;
    if (line.includes('PASS:') || (line.includes('checked') && line.includes('0 flagged'))) {
      const m = line.match(/(PASS:[^,\n]+(?:,\s*\d+\s*flagged)?)/i) || [null, line.trim()];
      lastVerifyResult = { pass: true, text: m[1] || line.trim() };
    } else if (line.includes('MISSING') || line.includes('budget reached') || /\b[1-9]\d*\s*flagged\b/i.test(line) || line.startsWith('FLAGGED:')) {
      if (!line.includes('0 flagged')) {
        const m = line.match(/((?:FLAGGED|MISSING|budget reached):?[^\n]+)/i) || [null, line.trim()];
        lastVerifyResult = { pass: false, text: m[1] || line.trim() };
      }
    }
  }

  function handleTaskCompletion(taskId, exitCode, errorMsg) {
    const isPassing = (exitCode === 0) && (!lastVerifyResult || lastVerifyResult.pass);
    if (isPassing) {
      const badgeText = (lastVerifyResult && lastVerifyResult.pass) ? lastVerifyResult.text : 'PASS: Verified';
      flashBadge(badgeText, '#72E098');
      updateStatusBadge('rendered');
      loadData();
    } else {
      const badgeText = (lastVerifyResult && !lastVerifyResult.pass) ? lastVerifyResult.text : `FAILED / Exit ${exitCode}`;
      flashBadge(badgeText, '#F87171');
      el.logDrawerContent.textContent += `\n❌ Verification reported failures or missing clips (exit code ${exitCode})${errorMsg ? `: ${errorMsg}` : ''}\n`;
      el.logDrawerContent.scrollTop = el.logDrawerContent.scrollHeight;
    }
  }

  function openLogDrawer(taskId, title) {
    lastVerifyResult = null;
    el.logDrawer.style.display = 'flex';
    if (el.btnReopenLogDrawer) el.btnReopenLogDrawer.style.display = 'inline-block';
    el.logDrawerTitle.textContent = title;
    el.logDrawerContent.textContent = 'Connecting to task output stream...\n';
    el.logTaskSpinner.style.display = 'inline-block';

    try {
      if (state.gameId) {
        sessionStorage.setItem('lastZoomTask_' + state.gameId, JSON.stringify({ taskId, title }));
      }
    } catch (_) {}

    if (activeEventSource) activeEventSource.close();

    activeEventSource = new EventSource(`/api/tasks/${taskId}/stream`);
    activeEventSource.onmessage = (event) => {
      let msg = null;
      try {
        msg = JSON.parse(event.data);
      } catch (_) {
        msg = { line: event.data };
      }
      if (msg.done) {
        activeEventSource.close();
        activeEventSource = null;
        el.logTaskSpinner.style.display = 'none';
        handleTaskCompletion(taskId, msg.exit_code, msg.error);
        return;
      }
      if (msg.line !== undefined) {
        el.logDrawerContent.textContent += `${msg.line}\n`;
        el.logDrawerContent.scrollTop = el.logDrawerContent.scrollHeight;
        parseVerifyLine(msg.line);
      }
    };

    activeEventSource.onerror = () => {
      if (activeEventSource) activeEventSource.close();
      activeEventSource = null;
      el.logTaskSpinner.style.display = 'none';
    };
  }

  // --- Keyboard Shortcuts ---
  function initKeyboardShortcuts() {
    window.addEventListener('keydown', (e) => {
      const key = e.key.toUpperCase();

      // Escape always closes topmost open layer (video modal -> shortcuts -> log drawer -> return to review)
      // even if focus is currently inside an input field
      if (e.key === 'Escape' || e.code === 'Escape' || key === 'ESCAPE') {
        e.preventDefault();
        e.stopPropagation();
        if (document.activeElement && document.activeElement.blur) {
          document.activeElement.blur();
        }
        if (el.unsavedZoomModal && el.unsavedZoomModal.style.display !== 'none') {
          closeUnsavedModal();
        } else if (el.removeZoomModal && el.removeZoomModal.style.display !== 'none') {
          closeRemoveZoomModal();
        } else if (el.blockedClipsModal && el.blockedClipsModal.style.display !== 'none') {
          closeBlockedClipsModal();
        } else if (el.finalVideoModal && el.finalVideoModal.style.display !== 'none') {
          el.finalVideoPlayer.pause();
          el.finalVideoModal.style.display = 'none';
        } else if (el.shortcutsModal && el.shortcutsModal.style.display !== 'none') {
          el.shortcutsModal.style.display = 'none';
        } else if (el.logDrawer && el.logDrawer.style.display !== 'none') {
          el.logDrawer.style.display = 'none';
        } else {
          closeOrReturnToReview();
        }
        return;
      }

      // Ignore other hotkeys if inside an input or textarea
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

      if (e.ctrlKey && key === 'S') {
        e.preventDefault();
        savePlan();
        return;
      }

      switch (key) {
        case 'A': // Step frame back
          e.preventDefault();
          stepSeconds(-FRAME_STEP);
          break;
        case 'D': // Step frame forward
          e.preventDefault();
          stepSeconds(FRAME_STEP);
          break;
        case 'S': // Step 0.5s back
          e.preventDefault();
          stepSeconds(-0.5);
          break;
        case 'W': // Step 0.5s forward
          e.preventDefault();
          stepSeconds(0.5);
          break;
        case ' ': // Play / Pause
          e.preventDefault();
          togglePlayPause();
          break;
        case 'K': // Drop keyframe
          e.preventDefault();
          addKeyframeAtPlayhead();
          break;
        case 'R': // Replay preview
          e.preventDefault();
          playReplayPreview();
          break;
      }
    });
  }

  // --- Event Listeners Wiring ---
  function initEvents() {
    // Top Bar
    if (el.btnBackToReview) {
      el.btnBackToReview.addEventListener('click', (e) => {
        e.preventDefault();
        closeOrReturnToReview();
      });
    }
    el.btnPrevZoom.addEventListener('click', () => navigateToClip(-1));
    el.btnNextZoom.addEventListener('click', () => navigateToClip(1));
    el.btnWatchFinal.addEventListener('click', () => {
      if (state.finalUrl) {
        el.finalVideoPlayer.src = state.finalUrl;
        el.finalVideoModal.style.display = 'flex';
        el.finalVideoPlayer.play();
      }
    });
    el.btnCloseFinalVideo.addEventListener('click', () => {
      el.finalVideoPlayer.pause();
      el.finalVideoModal.style.display = 'none';
    });
    el.btnOpenDocs.addEventListener('click', () => {
      el.shortcutsModal.style.display = 'flex';
    });
    el.btnCloseShortcuts.addEventListener('click', () => {
      el.shortcutsModal.style.display = 'none';
    });

    // Transport buttons
    el.btnSeekStart.addEventListener('click', () => seekToSource(state.start));
    el.btnStepBack1s.addEventListener('click', () => stepSeconds(-1.0));
    el.btnStepBackHalf.addEventListener('click', () => stepSeconds(-0.5));
    el.btnStepBackFrame.addEventListener('click', () => stepSeconds(-FRAME_STEP));
    el.btnPlayPause.addEventListener('click', togglePlayPause);
    el.btnStepFwdFrame.addEventListener('click', () => stepSeconds(FRAME_STEP));
    el.btnStepFwdHalf.addEventListener('click', () => stepSeconds(0.5));
    el.btnStepFwd1s.addEventListener('click', () => stepSeconds(1.0));
    el.btnSeekEnd.addEventListener('click', () => seekToSource(state.start + state.dur));

    // Video events
    el.mainVideo.addEventListener('timeupdate', updateTimelineUI);
    el.mainVideo.addEventListener('ended', () => {
      if (el.chkLoop.checked) {
        seekToSource(state.start);
        el.mainVideo.play();
      } else {
        el.btnPlayPause.textContent = `▶ PLAY (${state.speed}x)`;
        el.btnPlayPause.classList.remove('playing');
        state.isPlaying = false;
      }
    });

    // Overlays toggles
    el.chkGrid.addEventListener('change', () => {
      el.gridOverlay.style.display = el.chkGrid.checked ? 'block' : 'none';
    });

    // Zoom slider & presets
    el.zoomSlider.addEventListener('input', (e) => {
      setZoomRatio(parseFloat(e.target.value), true);
    });
    document.querySelectorAll('.btn-preset').forEach(b => {
      b.addEventListener('click', () => {
        setZoomRatio(parseFloat(b.dataset.zoom), true);
      });
    });

    // Window offsets
    el.inpWinStartOffset.addEventListener('change', (e) => {
      state.hasUnsavedChanges = true;
      const off = parseFloat(e.target.value) || -2.5;
      const newStart = Math.max(0, state.event + off);
      const diff = state.start - newStart;
      const prevStart = state.start;
      state.start = newStart;
      state.dur = Math.max(2.0, state.dur + diff);
      updateInspectorFields();
      if (Math.abs(diff) > 0.1) {
        if (state.finalExists) {
          state.status = 'rendered (stale)';
          updateStatusBadge('rendered (stale)');
        }
        seekToSource(state.start);
        updateCropBoxScreen();
        showToast(`⚠️ Window start shifted by ${Math.abs(diff).toFixed(1)}s (to ${state.start.toFixed(1)}s). The START crop box was framed for ${prevStart.toFixed(1)}s — please verify framing at the new start moment.`, 'warning', 8000);
      }
    });
    el.inpWinEndOffset.addEventListener('change', (e) => {
      state.hasUnsavedChanges = true;
      const off = parseFloat(e.target.value) || 2.0;
      const newEnd = state.event + off;
      state.dur = Math.max(2.0, newEnd - state.start);
      updateInspectorFields();
      if (state.finalExists) {
        state.status = 'rendered (stale)';
        updateStatusBadge('rendered (stale)');
      }
    });

    // Trims & Hold
    el.inpCutStart.addEventListener('change', (e) => {
      state.hasUnsavedChanges = true;
      state.cutStart = Math.max(0, parseFloat(e.target.value) || 0);
      updateTimelineUI();
      if (state.finalExists) {
        state.status = 'rendered (stale)';
        updateStatusBadge('rendered (stale)');
      }
    });
    el.inpCutEnd.addEventListener('change', (e) => {
      state.hasUnsavedChanges = true;
      state.cutEnd = Math.max(0, parseFloat(e.target.value) || 0);
      updateTimelineUI();
      if (state.finalExists) {
        state.status = 'rendered (stale)';
        updateStatusBadge('rendered (stale)');
      }
    });
    el.inpHoldEnd.addEventListener('change', (e) => {
      state.hasUnsavedChanges = true;
      state.holdEnd = Math.max(0, parseFloat(e.target.value) || 0);
      if (state.finalExists) {
        state.status = 'rendered (stale)';
        updateStatusBadge('rendered (stale)');
      }
    });

    // Ensure input events also trigger unsaved changes flag
    [el.inpWinStartOffset, el.inpWinEndOffset, el.inpCutStart, el.inpCutEnd, el.inpHoldEnd].forEach(inp => {
      if (inp) {
        inp.addEventListener('input', () => { state.hasUnsavedChanges = true; });
      }
    });

    // Speed toggles
    document.querySelectorAll('.btn-speed').forEach(b => {
      b.addEventListener('click', () => {
        state.hasUnsavedChanges = true;
        document.querySelectorAll('.btn-speed').forEach(s => s.classList.remove('active'));
        b.classList.add('active');
        state.speed = parseFloat(b.dataset.speed);
        el.mainVideo.playbackRate = state.speed;
        updateInspectorFields();
        if (!state.isPlaying) {
          el.btnPlayPause.textContent = `▶ PLAY (${state.speed}x)`;
        }
      });
    });

    // Explicit Looks Good Approval Button
    if (el.btnLooksGood) {
      el.btnLooksGood.addEventListener('click', async () => {
        if (state.isUnplaced || !state.baseCrop) {
          showToast('Clip is unplaced. Click video stage to place framing first.', 'error');
          return;
        }
        state.isReviewed = true;
        state.isAutoPlaced = false;
        state.hasExplicitApproval = true;
        state.hasUnsavedChanges = true;
        await savePlan();
      });
    }

    // Keyframes
    el.btnAddKeyframe.addEventListener('click', addKeyframeAtPlayhead);

    // Auto-frame handlers
    if (el.btnAutoFrame) el.btnAutoFrame.addEventListener('click', applyAutoFrameCurrent);
    if (el.btnUnplacedAutoFrame) el.btnUnplacedAutoFrame.addEventListener('click', applyAutoFrameCurrent);
    if (el.btnUnplacedAutoFrameAll) el.btnUnplacedAutoFrameAll.addEventListener('click', applyAutoFrameAll);

    // Click on video stage to place unplaced crop box
    el.videoStage.addEventListener('click', (e) => {
      if (!state.isUnplaced) return;
      if (e.target.closest('#unplacedNotice button')) return;
      const rect = el.videoStage.getBoundingClientRect();
      const scale = getScale();
      const clickX = (e.clientX - rect.left) / scale;
      const clickY = (e.clientY - rect.top) / scale;
      const cw = state.cropW || 1280;
      const ch = state.cropH || 720;
      const x = Math.max(0, Math.min(REF_W - cw, Math.round(clickX - cw / 2)));
      const y = Math.max(0, Math.min(REF_H - ch, Math.round(clickY - ch / 2)));
      state.baseCrop = [x, y];
      state.cropX = x;
      state.cropY = y;
      state.isUnplaced = false;
      state.isReviewed = false;
      state.isAutoPlaced = false;
      updateStatusBadge('unreviewed');
      updateCropBoxScreen();
      showToast('Crop box placed! Adjust framing and click Save Plan to confirm.', 'info');
    });

    // Scope change updates button text
    if (el.selRenderScope) {
      el.selRenderScope.addEventListener('change', () => {
        updateRenderButtonText();
      });
    }

    // Bottom actions
    el.btnAutoStart.addEventListener('click', () => {
      setZoomRatio(2.5, false);
      state.cropX = Math.round((REF_W - state.cropW) / 2);
      state.cropY = Math.round((REF_H - state.cropH) / 2);
      clampCrop();
      updateCropBoxScreen();
    });
    el.btnSavePlan.addEventListener('click', savePlan);
    el.btnPreviewReplay.addEventListener('click', playReplayPreview);
    el.btnRenderExact.addEventListener('click', renderExact);
    el.btnRemoveZoom.addEventListener('click', openRemoveZoomModal);
    if (el.btnRestoreZoom) el.btnRestoreZoom.addEventListener('click', restoreZoom);
    if (el.btnCancelRemoveZoomModal) el.btnCancelRemoveZoomModal.addEventListener('click', closeRemoveZoomModal);
    if (el.btnCancelRemoveZoom) el.btnCancelRemoveZoom.addEventListener('click', closeRemoveZoomModal);
    if (el.btnConfirmRemoveZoom) el.btnConfirmRemoveZoom.addEventListener('click', executeRemoveZoom);
    if (el.btnCloseBlockedModal) el.btnCloseBlockedModal.addEventListener('click', closeBlockedClipsModal);
    if (el.btnCancelBlockedModal) el.btnCancelBlockedModal.addEventListener('click', closeBlockedClipsModal);
    if (el.btnCloseUnsavedModal) el.btnCloseUnsavedModal.addEventListener('click', closeUnsavedModal);
    if (el.btnKeepEditingZoom) el.btnKeepEditingZoom.addEventListener('click', closeUnsavedModal);
    if (el.btnDiscardZoom) el.btnDiscardZoom.addEventListener('click', () => {
      state.hasUnsavedChanges = false;
      closeUnsavedModal();
      closeOrReturnToReview(true);
    });
    if (el.btnSaveAndLeaveZoom) el.btnSaveAndLeaveZoom.addEventListener('click', async () => {
      await savePlan();
      closeUnsavedModal();
      closeOrReturnToReview(true);
    });
    el.btnPrepareH.addEventListener('click', prepareHomographies);

    // Log Drawer
    el.btnCloseLogDrawer.addEventListener('click', () => {
      el.logDrawer.style.display = 'none';
    });
    if (el.btnReopenLogDrawer) {
      // Check server-side persisted last task or session storage
      try {
        if (state.gameId) {
          fetch(`/api/game/${encodeURIComponent(state.gameId)}/last-task?type=zoom`)
            .then(r => r.ok ? r.json() : null)
            .then(data => {
              if (data && data.task) {
                el.btnReopenLogDrawer.style.display = 'inline-block';
                el.btnReopenLogDrawer.onclick = () => {
                  el.logDrawer.style.display = 'flex';
                  el.logDrawerTitle.textContent = data.task.name || 'Last Zoom Task';
                  el.logDrawerContent.textContent = (data.lines || []).join('\n') + '\n';
                  el.logDrawerContent.scrollTop = el.logDrawerContent.scrollHeight;
                  if (data.task.exit_code !== null) {
                    handleTaskCompletion(data.task.id, data.task.exit_code, data.task.error);
                  }
                };
              }
            })
            .catch(() => {});
        }
      } catch (_) {}

      el.btnReopenLogDrawer.addEventListener('click', () => {
        el.logDrawer.style.display = 'flex';
        if (!el.logDrawerContent.textContent || el.logDrawerContent.textContent.trim() === '') {
          try {
            if (state.gameId) {
              const saved = sessionStorage.getItem('lastZoomTask_' + state.gameId);
              if (saved) {
                const t = JSON.parse(saved);
                if (t && t.taskId) {
                  openLogDrawer(t.taskId, t.title || 'Task Log');
                }
              }
            }
          } catch (_) {}
        }
      });
    }

    // Close modals on background click
    el.finalVideoModal.addEventListener('click', (e) => {
      if (e.target === el.finalVideoModal) {
        el.finalVideoPlayer.pause();
        el.finalVideoModal.style.display = 'none';
      }
    });
    el.shortcutsModal.addEventListener('click', (e) => {
      if (e.target === el.shortcutsModal) el.shortcutsModal.style.display = 'none';
    });
    if (el.removeZoomModal) {
      el.removeZoomModal.addEventListener('click', (e) => {
        if (e.target === el.removeZoomModal) closeRemoveZoomModal();
      });
    }
    if (el.unsavedZoomModal) {
      el.unsavedZoomModal.addEventListener('click', (e) => {
        if (e.target === el.unsavedZoomModal) closeUnsavedModal();
      });
    }
  }

  async function checkBuildInfo() {
    try {
      const res = await fetch('/api/build-info');
      if (!res.ok) return;
      const data = await res.json();
      if (el.lblServerStart && (data.server_start_str || data.server_start)) {
        el.lblServerStart.textContent = data.server_start_str || formatTime(data.server_start);
        el.lblServerStart.title = data.server_start_datetime || '';
      }
      if (el.staleServerBanner) {
        if (data.is_stale) {
          el.staleServerBanner.style.display = 'block';
          el.staleServerBanner.textContent = `⚠️ Server process is stale! Server was started at ${data.server_start_str || ''}, but files were modified at ${data.build_time_str || ''}. Please restart review_editor.bat.`;
        } else {
          el.staleServerBanner.style.display = 'none';
        }
      }
    } catch (err) {
      console.debug('Failed to check build-info:', err);
    }
  }

  // Main entrypoint
  window.addEventListener('DOMContentLoaded', () => {
    initElements();
    parseRoute();
    initDragAndDrop();
    initScrubber();
    initKeyboardShortcuts();
    initEvents();
    loadData();
    checkBuildInfo();
    setInterval(checkBuildInfo, 60000);
    checkProductionLock();
    setInterval(checkProductionLock, 10000);
  });
})();
