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
    invertedHomographies: null,
    isPitchAnchored: false,
    allClips: [],
    isPlaying: false,
    isReplayPreview: false,
    previewRaf: null,
    status: 'auto-placed',
    finalExists: false,
    finalUrl: null,
    userStagedCrop: null,
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
    el.btnSetStart = document.getElementById('btnSetStart');
    el.btnSetEnd = document.getElementById('btnSetEnd');
    el.btnSetStartTransport = document.getElementById('btnSetStartTransport');
    el.btnSetEndTransport = document.getElementById('btnSetEndTransport');
    el.lblWindowSummary = document.getElementById('lblWindowSummary');
    el.inpCutStart = document.getElementById('inpCutStart');
    el.inpCutEnd = document.getElementById('inpCutEnd');
    el.inpHoldEnd = document.getElementById('inpHoldEnd');

    el.keyframesList = document.getElementById('keyframesList');
    el.btnAddKeyframe = document.getElementById('btnAddKeyframe');
    el.btnToggleAnchor = document.getElementById('btnToggleAnchor');
    el.lblWorkflowNotice = document.getElementById('lblWorkflowNotice');
    el.lblHStatus = document.getElementById('lblHStatus');
    el.btnPrepareH = document.getElementById('btnPrepareH');

    el.btnResetClipWindow = document.getElementById('btnResetClipWindow');
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
    el.zoomLogAutoClose = document.getElementById('zoomLogAutoClose');

    el.finalVideoModal = document.getElementById('finalVideoModal');
    el.finalVideoPlayer = document.getElementById('finalVideoPlayer');
    el.btnCloseFinalVideo = document.getElementById('btnCloseFinalVideo');
    el.finalVideoModalTitle = document.getElementById('finalVideoModalTitle');
    el.btnFinalVideoTogglePlay = document.getElementById('btnFinalVideoTogglePlay');
    el.btnFinalVideoClose = document.getElementById('btnFinalVideoClose');

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

    // Remove any existing toast to prevent stacking or text overlapping
    container.querySelectorAll('.app-toast').forEach(t => t.remove());

    const t = document.createElement('div');
    t.className = `app-toast toast-${type}`;
    t.style.cursor = 'pointer';

    const textSpan = document.createElement('span');
    textSpan.textContent = message;
    t.appendChild(textSpan);

    if (actionBtn && actionBtn.text && actionBtn.onClick) {
      const btn = document.createElement('button');
      btn.className = 'toast-action-btn';
      btn.textContent = actionBtn.text;
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        actionBtn.onClick();
        t.remove();
      });
      t.appendChild(btn);
    }

    t.addEventListener('click', () => {
      t.remove();
    });

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

  function updateWorkflowNotice(message, type = 'info') {
    if (!el.lblWorkflowNotice) return;
    el.lblWorkflowNotice.textContent = message;
    el.lblWorkflowNotice.className = `workflow-notice-box ${type}`;
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
    state.defaultWindow = data.default_window || { start: Math.max(0, state.event - 2.5), dur: 5.0 };
    state.start = r.start !== undefined ? r.start : state.defaultWindow.start;
    state.dur = r.dur !== undefined ? r.dur : state.defaultWindow.dur;
    state.cutStart = r.cut_start || 0.0;
    state.cutEnd = r.cut_end || 0.0;
    state.holdEnd = r.hold_end || 0.0;
    state.zoomTo = r.zoom_to || null;

    // Crop position & dimensions
    const cw = r.crop_w || (r.crop ? 1280 : 1536);
    state.cropW = cw;
    state.cropH = Math.round(cw * 9 / 16);
    state.zoomRatio = Number((REF_W / cw).toFixed(2));

    state.isReviewed = Boolean(r.reviewed);

    if (r.crop && Array.isArray(r.crop)) {
      state.baseCrop = [r.crop[0], r.crop[1]];
      // Clamp base crop to frame boundaries
      state.baseCrop[0] = Math.max(0, Math.min(REF_W - state.cropW, state.baseCrop[0]));
      state.baseCrop[1] = Math.max(0, Math.min(REF_H - state.cropH, state.baseCrop[1]));
      state.cropX = state.baseCrop[0];
      state.cropY = state.baseCrop[1];
      state.isUnplaced = false;
      state.isAutoPlaced = Boolean(r.is_auto_placed);
    } else {
      // Auto-place immediately so the user can jump straight into adjusting framing and pressing S
      state.cropX = Math.round((REF_W - state.cropW) / 2);
      state.cropY = Math.round((REF_H - state.cropH) / 2);
      state.baseCrop = [state.cropX, state.cropY];
      state.isUnplaced = false;
      state.isAutoPlaced = true;
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
    state.staleReasons = [];
    if (state.isRemoved) {
      state.status = 'removed';
    } else if (state.isUnplaced) {
      state.status = 'unplaced';
    } else if (!state.isReviewed) {
      state.status = 'unreviewed';
    } else if (state.finalExists && r.final_key) {
      let isPlanStale = Boolean(data.is_stale);
      let staleReasons = Array.isArray(data.stale_reasons) ? [...data.stale_reasons] : [];
      if (r.history && r.history.length > 0) {
        const lastH = r.history[r.history.length - 1];
        if (lastH.window) {
          if (Math.abs(r.start - lastH.window[0]) > 0.05 || Math.abs(r.dur - lastH.window[1]) > 0.05) {
            isPlanStale = true;
            if (!staleReasons.includes('Replay start/duration was modified')) staleReasons.push('Replay start/duration was modified');
          }
        }
        if (lastH.cut) {
          if (Math.abs((r.cut_start || 0) - lastH.cut[0]) > 0.05 || Math.abs((r.cut_end || 0) - lastH.cut[1]) > 0.05) {
            isPlanStale = true;
            if (!staleReasons.includes('Trim cut in/out was modified')) staleReasons.push('Trim cut in/out was modified');
          }
        }
        if (lastH.crop && r.crop) {
          if (r.crop[0] !== lastH.crop[0] || r.crop[1] !== lastH.crop[1]) {
            isPlanStale = true;
            if (!staleReasons.includes('Crop position was modified')) staleReasons.push('Crop position was modified');
          }
        }
      }
      if (isPlanStale && staleReasons.length === 0) {
        staleReasons.push('Plan was modified since the last video render');
      }
      state.staleReasons = staleReasons;
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
      el.lblHStatus.textContent = 'Auto on render';
      el.lblHStatus.style.color = '#94A3B8';
    }

    // Update Header
    el.clipTitleText.textContent = `Clip ${state.clipNum}`;
    el.clipTokenText.textContent = `(${state.canonicalToken})`;
    updateStatusBadge(state.status);
    updateSavePlanButtonState();
    updateRenderButtonText();
    updateAnchorButtonUI();

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
    updateSavePlanButtonState();
    updateRenderButtonText();
  }

  function updateSavePlanButtonState() {
    if (!el.btnSavePlan) return;
    const isUnsaved = state.hasUnsavedChanges || !state.isReviewed;
    if (isUnsaved) {
      el.btnSavePlan.classList.remove('btn-save-saved');
      el.btnSavePlan.classList.add('btn-save-unsaved');
      el.btnSavePlan.title = 'Save replay plan to zoom_state.json (Ctrl+S) — changes are unsaved';
    } else {
      el.btnSavePlan.classList.remove('btn-save-unsaved');
      el.btnSavePlan.classList.add('btn-save-saved');
      el.btnSavePlan.title = 'Replay plan is saved (Ctrl+S)';
    }
  }

  function markPlanModified(reason) {
    state.hasUnsavedChanges = true;
    if (state.finalExists) {
      state.status = 'rendered (stale)';
      if (reason) {
        if (!state.staleReasons) state.staleReasons = [];
        if (!state.staleReasons.includes(reason)) {
          state.staleReasons.unshift(reason);
        }
      }
      updateStatusBadge('rendered (stale)');
    } else if (state.isReviewed) {
      state.status = 'reviewed';
      updateStatusBadge('reviewed');
    }
    updateSavePlanButtonState();
    updateRenderButtonText();
  }

  function updateStatusBadge(status, customTip) {
    el.clipStatusBadge.className = 'status-badge';
    el.clipStatusBadge.textContent = `status: ${status}`;
    if (status === 'rendered') {
      el.clipStatusBadge.classList.add('status-rendered');
      el.clipStatusBadge.title = customTip || 'The rendered 720p replay matches the current saved plan.';
    }
    else if (status === 'rendered (stale)' || status === 'stale') {
      el.clipStatusBadge.classList.add('status-stale');
      el.clipStatusBadge.textContent = 'status: RENDERED (stale)';
      let reasonText = '';
      if (customTip) {
        reasonText = customTip;
      } else if (state.staleReasons && state.staleReasons.length > 0) {
        reasonText = state.staleReasons.join('; ');
      } else if (state.hasUnsavedChanges) {
        reasonText = 'Unsaved modifications made in editor';
      } else {
        reasonText = 'Plan was modified after the last video render';
      }
      el.clipStatusBadge.title = `Why stale: ${reasonText}. Click '⚡ Render exact' to re-render the 720p video.`;
    }
    else if (status === 'reviewed') {
      el.clipStatusBadge.classList.add('status-reviewed');
      el.clipStatusBadge.textContent = 'status: REVIEWED (not rendered yet)';
      el.clipStatusBadge.title = customTip || 'Plan is saved and approved, but the replay video has not been rendered yet. Click ⚡ Render exact.';
    }
    else if (status === 'edited') {
      el.clipStatusBadge.classList.add('status-edited');
      el.clipStatusBadge.textContent = 'status: EDITED (not reviewed)';
      el.clipStatusBadge.title = customTip || 'Plan has been edited but not yet approved or saved.';
    }
    else if (status === 'needs render') {
      el.clipStatusBadge.classList.add('status-needs-render');
      el.clipStatusBadge.title = customTip || 'Crop is placed, but video needs to be rendered.';
    }
    else if (status === 'unreviewed' || status === 'auto-placed') {
      el.clipStatusBadge.classList.add('status-auto');
      el.clipStatusBadge.title = customTip || 'Initial framing applied; review framing before rendering.';
    }
    else if (status === 'unplaced' || status === 'not started' || status === 'removed') {
      el.clipStatusBadge.classList.add('status-not-started');
      el.clipStatusBadge.title = customTip || 'Clip has not been placed or is removed.';
    }
    else {
      el.clipStatusBadge.classList.add('status-not-started');
      el.clipStatusBadge.title = customTip || '';
    }
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
    if (el.cropBox) el.cropBox.style.display = 'block';
    if (el.unplacedNotice) el.unplacedNotice.style.display = 'none';

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
    markPlanModified('Zoom ratio adjusted');
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

  // --- Keyframe Timing Calculator ---
  function computeKeyframeTiming(replaySec) {
    const tArrival = Number(replaySec.toFixed(2));
    const prevKf = state.pans
      .filter(p => p.tArrival < tArrival - 0.05)
      .sort((a, b) => b.tArrival - a.tArrival)[0];
    const prevArrival = prevKf ? prevKf.tArrival : 0.0;
    const availableTime = Math.max(0.1, tArrival - prevArrival);
    const len = Number(Math.max(0.2, Math.min(1.2, availableTime)).toFixed(2));
    const at = Number((tArrival - len / 2).toFixed(3));
    return { at, len, tArrival };
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
        const isStart = (replaySec <= 0.15);
        if (isStart) {
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
        const wasDragging = isDragging;
        const wasResizing = isResizing;
        isDragging = false;
        isResizing = false;
        activeHandle = null;
        markPlanModified(wasResizing ? 'Crop box resized' : 'Crop box moved');

        const replaySec = (el.mainVideo && !isNaN(el.mainVideo.currentTime)) ? (el.mainVideo.currentTime - state.start) / state.speed : 0;
        const isStart = (replaySec <= 0.2);

        if (state.isPitchAnchored && state.homographies && state.homographies.length) {
          // Pitch Anchor active: transform placement at current moment into reference frame coordinates
          const progress = Math.max(0, Math.min(1.0, (el.mainVideo.currentTime - state.start) / Math.max(0.1, state.dur)));
          const idx = Math.min(state.homographies.length - 1, Math.max(0, Math.floor(progress * state.homographies.length)));
          const H = state.homographies[idx];
          const refPt = H ? transformPoint(H, state.cropX, state.cropY) : { x: state.cropX, y: state.cropY };
          state.baseCrop = [Math.round(refPt.x), Math.round(refPt.y)];
          state.userStagedCrop = null;
          state.isAutoPlaced = false;
          showToast(`⚓ Anchored pitch landmark at (${state.baseCrop[0]}, ${state.baseCrop[1]})`, 'success', 2500);
          renderKeyframesList();
          updateTimelineUI();
          updateCropBoxScreen();
        } else if (isStart) {
          // At the start of the replay: update the START box anchor
          if (!state.baseCrop) state.baseCrop = [state.cropX, state.cropY];
          else {
            state.baseCrop[0] = state.cropX;
            state.baseCrop[1] = state.cropY;
          }
          state.userStagedCrop = null;
          state.isAutoPlaced = false;
          renderKeyframesList();
          updateTimelineUI();
          updateCropBoxScreen();
        } else {
          // At a later moment in the replay:
          const existingKf = state.pans.find(p => Math.abs(p.tArrival - replaySec) <= 0.2);
          if (existingKf) {
            // If already parked at a keyframe, update its target crop coordinates
            existingKf.x = state.cropX;
            existingKf.y = state.cropY;
            state.userStagedCrop = null;
            showToast(`Updated pan keyframe at ${existingKf.tArrival.toFixed(1)}s`, 'info', 2000);
            renderKeyframesList();
            renderScrubberKeyframes();
            updateTimelineUI();
            updateCropBoxScreen();
          } else {
            // User moved/resized box at a new timestamp.
            // DO NOT automatically create a keyframe per explicit workflow design.
            // Stage the manual placement so it stays on screen until user presses K or scrubs away.
            state.userStagedCrop = { replaySec, x: state.cropX, y: state.cropY };
            showToast(`Box positioned at ${replaySec.toFixed(1)}s. Press K or click '+ Keyframe' to record`, 'info', 3000);
            updateCropBoxScreen();
          }
          state.isAutoPlaced = false;
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
      if (state.userStagedCrop && Math.abs(state.userStagedCrop.replaySec - replayElapsed) < 0.05) {
        state.cropX = state.userStagedCrop.x;
        state.cropY = state.userStagedCrop.y;
        updateCropBoxScreen(state.cropX, state.cropY);
      } else {
        if (state.userStagedCrop) {
          state.userStagedCrop = null;
        }
        const pos = interpolatePan(replayElapsed);
        state.cropX = pos.x;
        state.cropY = pos.y;
        updateCropBoxScreen(pos.x, pos.y);
      }
    }

    // Keyframe hint and mode coloring (amber for START, blue for keyframe)
    if (el.lblKeyframeHint && el.cropBox) {
      const kf = state.pans.find(p => Math.abs(p.tArrival - replayElapsed) <= 0.15);
      if (state.userStagedCrop && Math.abs(state.userStagedCrop.replaySec - replayElapsed) < 0.05) {
        el.lblKeyframeHint.textContent = `Box staged at ${state.userStagedCrop.replaySec.toFixed(1)}s — press K to record keyframe`;
        el.lblKeyframeHint.className = 'keyframe-hint-bar kf-active';
        el.cropBox.classList.remove('mode-start');
        el.cropBox.classList.add('mode-keyframe');
        updateWorkflowNotice(`📍 Box staged at ${state.userStagedCrop.replaySec.toFixed(1)}s. Press K (or '+ Keyframe') to record, or move playhead to cancel.`, 'info');
      } else if (kf) {
        el.lblKeyframeHint.textContent = `Editing keyframe at ${kf.tArrival.toFixed(1)}s (glide arrives here)`;
        el.lblKeyframeHint.className = 'keyframe-hint-bar kf-active';
        el.cropBox.classList.remove('mode-start');
        el.cropBox.classList.add('mode-keyframe');
        updateWorkflowNotice(`🎯 Editing keyframe at ${kf.tArrival.toFixed(1)}s. Move box to update position, or click ✕ in list to remove.`, 'info');
      } else {
        const isStart = (replayElapsed <= 0.2);
        if (isStart) {
          el.lblKeyframeHint.textContent = 'Framing START position (0.0s). Move box and press S (or Start button) to lock.';
          el.lblKeyframeHint.className = 'keyframe-hint-bar start-active';
          el.cropBox.classList.remove('mode-keyframe');
          el.cropBox.classList.add('mode-start');
          updateWorkflowNotice('🎯 Framing Start (0.0s). Move box and press S (or Start button) to lock initial shot.', 'info');
        } else {
          el.lblKeyframeHint.textContent = `At ${replayElapsed.toFixed(1)}s — position box and press K to record glide keyframe`;
          el.lblKeyframeHint.className = 'keyframe-hint-bar kf-active';
          el.cropBox.classList.remove('mode-start');
          el.cropBox.classList.add('mode-keyframe');
          updateWorkflowNotice(`⏱️ At ${replayElapsed.toFixed(1)}s. Move box and press K to record glide keyframe, or step with W (+0.5s).`, 'info');
        }
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
    el.inpWinStartOffset.value = Math.abs(state.event - state.start).toFixed(1);
    el.inpWinEndOffset.value = Math.max(0, (state.start + state.dur) - state.event).toFixed(1);
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
        markPlanModified('Pan keyframe mode changed');
        const i = parseInt(e.target.dataset.idx, 10);
        const p = state.pans[i];
        p.mode = e.target.value;
        if (p.mode === 'glide') {
          const timing = computeKeyframeTiming(p.tArrival);
          p.len = timing.len;
          p.at = timing.at;
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
        markPlanModified('Pan keyframe deleted');
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
    markPlanModified('Pan keyframe added');
    state.userStagedCrop = null;
    state.isAutoPlaced = false;
    const cur = el.mainVideo.currentTime;
    const replaySec = Math.max(0.0, Number(((cur - state.start) / state.speed).toFixed(2)));
    const totalReplay = state.dur / state.speed;
    if (replaySec >= totalReplay) {
      showToast('Cannot place keyframe at or after clip end', 'warning', 3000);
      updateWorkflowNotice('⚠️ Cannot place keyframe at or after clip end.', 'warning');
      return;
    }

    // 1. If at or near 0.0s Start: lock the Start base crop framing
    if (replaySec <= 0.2) {
      state.baseCrop = [state.cropX, state.cropY];
      updateCropBoxScreen();
      showToast('Start framing anchored (0.0s). To add a pan glide, step forward in seconds (W: +0.5s) and press K.', 'info', 4000);
      updateWorkflowNotice('🎯 Start framing anchored. Step forward in seconds (W: +0.5s or Space) and press K to add a pan waypoint.', 'info');
      renderKeyframesList();
      renderScrubberKeyframes();
      updateTimelineUI();
      return;
    }

    // 2. If too close to 0.0s Start for a pan glide:
    if (replaySec < 0.4) {
      showToast('Too close to Start (0.0s). Camera needs time to glide — step forward in seconds (W: +0.5s).', 'warning', 4500);
      updateWorkflowNotice('⚠️ Too close to Start (0.0s). Increment in seconds (W: +0.5s) so the camera has time to glide smoothly.', 'warning');
      return;
    }

    // 3. If sitting right on an existing keyframe: update its coordinates
    const exactExisting = state.pans.find(p => Math.abs(p.tArrival - replaySec) <= 0.08);
    if (exactExisting) {
      exactExisting.x = state.cropX;
      exactExisting.y = state.cropY;
      showToast(`Updated keyframe at ${exactExisting.tArrival.toFixed(1)}s`, 'info', 2000);
      updateWorkflowNotice(`✨ Updated keyframe at ${exactExisting.tArrival.toFixed(1)}s.`, 'info');
      renderKeyframesList();
      renderScrubberKeyframes();
      updateTimelineUI();
      return;
    }

    // 4. If too close to an existing keyframe (< 0.4s apart): guard warning!
    const nearbyExisting = state.pans.find(p => Math.abs(p.tArrival - replaySec) < 0.4);
    if (nearbyExisting) {
      showToast('Time between keyframes is too small (< 0.4s). Increment in seconds (W: +0.5s) for smooth glide.', 'warning', 4500);
      updateWorkflowNotice('⚠️ Time between keyframes is too small (< 0.4s). Step forward in seconds (W: +0.5s) to add a smooth waypoint.', 'warning');
      return;
    }

    // 5. Valid keyframe timestamp: add glide keyframe
    const timing = computeKeyframeTiming(replaySec);
    state.pans.push({
      mode: 'glide',
      x: state.cropX,
      y: state.cropY,
      at: timing.at,
      len: timing.len,
      tArrival: timing.tArrival
    });
    state.pans.sort((a, b) => a.tArrival - b.tArrival);
    showToast(`Added keyframe at ${timing.tArrival.toFixed(1)}s`, 'info', 2000);
    updateWorkflowNotice(`✨ Added keyframe at ${timing.tArrival.toFixed(1)}s. The camera will smoothly glide from the previous point.`, 'success');
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

    // If Pitch Anchored and homographies are available and no manual pan keyframes:
    if (state.isPitchAnchored && state.invertedHomographies && state.invertedHomographies.length && !state.pans.length) {
      const curSourceSec = state.start + replaySec * state.speed;
      const progress = Math.max(0, Math.min(1.0, (curSourceSec - state.start) / Math.max(0.1, state.dur)));
      const idx = Math.min(state.invertedHomographies.length - 1, Math.max(0, Math.floor(progress * state.invertedHomographies.length)));
      const invH = state.invertedHomographies[idx];
      if (invH) {
        const pt = transformPoint(invH, fallbackX, fallbackY);
        const maxX = Math.max(0, REF_W - state.cropW);
        const maxY = Math.max(0, REF_H - state.cropH);
        return {
          x: Math.max(0, Math.min(maxX, Math.round(pt.x))),
          y: Math.max(0, Math.min(maxY, Math.round(pt.y)))
        };
      }
    }

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
  function invert3x3(m) {
    if (!m || m.length < 3) return null;
    const [a, b, c] = m[0];
    const [d, e, f] = m[1];
    const [g, h, i] = m[2];
    const A = e * i - f * h;
    const B = -(d * i - f * g);
    const C = d * h - e * g;
    const det = a * A + b * B + c * C;
    if (Math.abs(det) < 1e-8) return null;
    const invDet = 1.0 / det;
    return [
      [A * invDet, (c * h - b * i) * invDet, (b * f - c * e) * invDet],
      [B * invDet, (a * i - c * g) * invDet, (c * d - a * f) * invDet],
      [C * invDet, (b * g - a * h) * invDet, (a * e - b * d) * invDet]
    ];
  }

  function transformPoint(M, x, y) {
    if (!M) return { x, y };
    const X = M[0][0] * x + M[0][1] * y + M[0][2];
    const Y = M[1][0] * x + M[1][1] * y + M[1][2];
    const W = M[2][0] * x + M[2][1] * y + M[2][2];
    if (Math.abs(W) < 1e-8) return { x, y };
    return { x: X / W, y: Y / W };
  }

  async function togglePitchAnchor() {
    state.isPitchAnchored = !state.isPitchAnchored;
    updateAnchorButtonUI();
    if (state.isPitchAnchored) {
      if (!state.homographies || !state.homographies.length) {
        showToast('⚓ Pitch Anchor enabled. Pre-computing stabilization matrices...', 'info', 3000);
        updateWorkflowNotice('⚓ Pitch Anchor enabled: computing camera stabilization to lock onto pitch...', 'info');
        await prepareHomographies();
      } else {
        showToast('⚓ Pitch Anchor active: crop box tracks stationary goals/pitch counteracting camera pan', 'success', 3000);
        updateWorkflowNotice('⚓ Pitch Anchor active: crop box locked to stationary pitch coordinates.', 'info');
      }
      updateTimelineUI();
    } else {
      showToast('Pitch Anchor disabled (fixed screen framing)', 'info', 2000);
      updateWorkflowNotice('Pitch Anchor disabled: using standard framing and manual keyframes.', 'info');
      updateTimelineUI();
    }
  }

  function updateAnchorButtonUI() {
    if (!el.btnToggleAnchor) return;
    if (state.isPitchAnchored) {
      el.btnToggleAnchor.classList.add('btn-anchor-active');
      el.btnToggleAnchor.textContent = '⚓ Anchored (A)';
      el.btnToggleAnchor.title = 'Pitch Anchor is active: crop tracks stationary pitch/goals counteracting camera pan. Press A to toggle off.';
    } else {
      el.btnToggleAnchor.classList.remove('btn-anchor-active');
      el.btnToggleAnchor.textContent = '⚓ Anchor (A)';
      el.btnToggleAnchor.title = 'Anchor crop box to stationary pitch landmark (goals/field) using camera stabilization (A)';
    }
  }

  async function fetchHomographies() {
    try {
      const resp = await fetch(`/api/zoom/${state.gameId}/${state.canonicalToken}/homographies`);
      if (resp.ok) {
        const data = await resp.json();
        state.homographies = data.homographies;
        state.invertedHomographies = Array.isArray(state.homographies)
          ? state.homographies.map(H => invert3x3(H))
          : null;
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
        state.staleReasons = ['Plan was modified and saved after video render'];
        updateStatusBadge('rendered (stale)');
      } else if (!state.isReviewed) {
        state.status = 'unreviewed';
        updateStatusBadge('unreviewed');
      } else {
        state.status = state.isAutoPlaced ? 'auto-placed' : (state.isReviewed ? 'reviewed' : 'edited');
        updateStatusBadge(state.status);
      }
      updateSavePlanButtonState();
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

  function isReadyPreview() {
    const scope = el.selRenderScope ? el.selRenderScope.value : 'current';
    return (scope === 'current') && Boolean(state.finalExists && state.finalUrl) && (state.status === 'rendered') && !state.hasUnsavedChanges && !state.isRemoved;
  }

  function updateRenderButtonText() {
    if (!el.btnRenderExact) return;
    const scope = el.selRenderScope ? el.selRenderScope.value : 'current';
    if (scope === 'all') {
      const unrevCount = (state.allClips || []).filter(c => !c.reviewed).length;
      el.btnRenderExact.textContent = unrevCount > 0 ? `⚡ Render All (${unrevCount} unreviewed)` : '⚡ Render All';
      el.btnRenderExact.title = 'Run background 720p render on all clips and verify';
      el.btnRenderExact.classList.remove('btn-view-preview');
      el.btnRenderExact.classList.add('btn-accent');
    } else if (isReadyPreview()) {
      el.btnRenderExact.textContent = '▶ View preview';
      el.btnRenderExact.title = 'Watch rendered 720p replay in HTML5 loop player';
      el.btnRenderExact.classList.remove('btn-accent');
      el.btnRenderExact.classList.add('btn-view-preview');
    } else {
      el.btnRenderExact.textContent = '⚡ Render exact';
      el.btnRenderExact.title = 'Run background 720p render and automated verify_zoom.py';
      el.btnRenderExact.classList.remove('btn-view-preview');
      el.btnRenderExact.classList.add('btn-accent');
    }
  }

  function openPreviewPlayer() {
    if (!state.finalUrl) {
      showToast('No rendered preview MP4 found. Click "Render exact" first.', 'warning');
      return;
    }
    if (el.finalVideoModalTitle) {
      el.finalVideoModalTitle.textContent = `Replay Preview — Clip ${state.clipNum} (${state.canonicalToken || state.tokenOrClip})`;
    }
    const cacheBuster = (state.finalUrl.includes('?') ? '&' : '?') + 't=' + Date.now();
    el.finalVideoPlayer.src = state.finalUrl + cacheBuster;
    el.finalVideoPlayer.loop = true;
    el.finalVideoModal.style.display = 'flex';
    if (el.btnFinalVideoTogglePlay) {
      el.btnFinalVideoTogglePlay.textContent = '❚❚ Pause';
    }
    el.finalVideoPlayer.play().catch(() => {});
  }

  function closePreviewPlayer() {
    if (el.finalVideoPlayer) {
      el.finalVideoPlayer.pause();
      el.finalVideoPlayer.removeAttribute('src');
      el.finalVideoPlayer.load();
    }
    if (el.finalVideoModal) {
      el.finalVideoModal.style.display = 'none';
    }
  }

  function togglePreviewPlayer() {
    if (!el.finalVideoPlayer) return;
    if (el.finalVideoPlayer.paused) {
      el.finalVideoPlayer.play().catch(() => {});
      if (el.btnFinalVideoTogglePlay) el.btnFinalVideoTogglePlay.textContent = '❚❚ Pause';
    } else {
      el.finalVideoPlayer.pause();
      if (el.btnFinalVideoTogglePlay) el.btnFinalVideoTogglePlay.textContent = '▶ Play';
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

  let drawerAutoCloseTimer = null;

  async function handleTaskCompletion(taskId, exitCode, errorMsg) {
    const isPassing = (exitCode === 0) && (!lastVerifyResult || lastVerifyResult.pass);
    if (isPassing) {
      const badgeText = (lastVerifyResult && lastVerifyResult.pass) ? lastVerifyResult.text : 'PASS: Verified';
      flashBadge(badgeText, '#72E098');
      state.status = 'rendered';
      state.staleReasons = [];
      state.hasUnsavedChanges = false;
      updateStatusBadge('rendered');
      updateSavePlanButtonState();
      await loadData();
      updateRenderButtonText();

      // Auto-close log drawer on success if enabled
      const shouldAutoClose = !el.zoomLogAutoClose || el.zoomLogAutoClose.checked;
      if (shouldAutoClose) {
        if (drawerAutoCloseTimer) clearTimeout(drawerAutoCloseTimer);
        drawerAutoCloseTimer = setTimeout(() => {
          if (el.logDrawer && el.logDrawer.style.display !== 'none') {
            el.logDrawer.style.display = 'none';
            const scope = el.selRenderScope ? el.selRenderScope.value : 'current';
            if (scope === 'current' && isReadyPreview()) {
              openPreviewPlayer();
            } else {
              showToast('Preview rendered successfully. Click "▶ View preview" to watch.', 'success', 3000);
            }
          }
        }, 1200);
      }
    } else {
      const badgeText = (lastVerifyResult && !lastVerifyResult.pass) ? lastVerifyResult.text : `FAILED / Exit ${exitCode}`;
      flashBadge(badgeText, '#F87171');
      el.logDrawerContent.textContent += `\n❌ Verification reported failures or missing clips (exit code ${exitCode})${errorMsg ? `: ${errorMsg}` : ''}\n`;
      el.logDrawerContent.scrollTop = el.logDrawerContent.scrollHeight;
      // Stays open on failure so user can read error
    }
  }

  function openLogDrawer(taskId, title) {
    if (drawerAutoCloseTimer) {
      clearTimeout(drawerAutoCloseTimer);
      drawerAutoCloseTimer = null;
    }
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

  // --- Quick Set Window Start and End from video playhead ---
  function setWindowStartFromPlayhead() {
    const cur = el.mainVideo.currentTime;
    if (cur >= state.start + state.dur - 1.0) {
      showToast('Start cannot be after or within 1s of window end', 'warning');
      return;
    }
    const prevStart = state.start;
    const newStart = Math.max(0, Number(cur.toFixed(1)));
    const timeDiff = Math.abs(prevStart - newStart);
    const coordsChanged = !state.baseCrop ||
      Math.abs(state.baseCrop[0] - state.cropX) > 0.5 ||
      Math.abs(state.baseCrop[1] - state.cropY) > 0.5;

    // If both playhead time and crop coordinates are in the same position, ignore the press
    if (timeDiff < 0.05 && !coordsChanged) {
      return;
    }

    // Anchor current crop box placement as replay START framing
    state.baseCrop = [state.cropX, state.cropY];
    state.isAutoPlaced = false;
    state.userStagedCrop = null;

    if (timeDiff >= 0.05) {
      const diff = state.start - newStart;
      state.start = newStart;
      state.dur = Math.max(2.0, state.dur + diff);
      seekToSource(state.start);
      renderKeyframesList();
      renderScrubberKeyframes();
      updateTimelineUI();
      markPlanModified('Replay start window set from playhead');
    } else {
      markPlanModified('Replay start framing coordinates updated');
    }

    updateInspectorFields();
    updateCropBoxScreen();
  }

  function setWindowEndFromPlayhead() {
    const cur = el.mainVideo.currentTime;
    if (cur <= state.start + 1.0) {
      showToast('End cannot be before or within 1s of window start', 'warning');
      return;
    }
    const newEnd = Number(cur.toFixed(1));
    const currentEnd = Number((state.start + state.dur).toFixed(1));
    if (Math.abs(newEnd - currentEnd) < 0.05) {
      return; // Ignore if at the same position
    }
    state.dur = Math.max(2.0, newEnd - state.start);
    state.userStagedCrop = null;
    updateInspectorFields();
    markPlanModified('Replay end window set from playhead');
    renderKeyframesList();
    renderScrubberKeyframes();
    updateTimelineUI();
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
          closePreviewPlayer();
        } else if (el.shortcutsModal && el.shortcutsModal.style.display !== 'none') {
          el.shortcutsModal.style.display = 'none';
        } else if (el.logDrawer && el.logDrawer.style.display !== 'none') {
          if (drawerAutoCloseTimer) {
            clearTimeout(drawerAutoCloseTimer);
            drawerAutoCloseTimer = null;
          }
          el.logDrawer.style.display = 'none';
        } else {
          closeOrReturnToReview();
        }
        return;
      }

      // Pressing Enter inside an input or select commits value and returns focus to keyboard shortcuts
      if (e.key === 'Enter' && ['INPUT', 'SELECT'].includes(document.activeElement.tagName)) {
        document.activeElement.blur();
        return;
      }

      // Ignore other hotkeys if inside an input or textarea
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

      if ((e.ctrlKey || e.metaKey) && key === 'S') {
        e.preventDefault();
        savePlan();
        return;
      }

      // Allow all other Ctrl/Meta/Alt browser combinations (e.g. Ctrl+C to copy log, Ctrl+A to select all)
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      // Do not trigger single-key action shortcuts if user has selected text on screen (e.g. in log drawer)
      const selection = window.getSelection();
      if (selection && selection.toString().trim().length > 0) return;

      switch (key) {
        case 'A': // Toggle pitch anchor
          e.preventDefault();
          togglePitchAnchor();
          break;
        case 'ARROWLEFT':
          e.preventDefault();
          stepSeconds(-FRAME_STEP);
          break;
        case 'D': // Step frame forward
        case 'ARROWRIGHT':
          e.preventDefault();
          stepSeconds(FRAME_STEP);
          break;
        case 'Q': // Step 0.5s back
          e.preventDefault();
          stepSeconds(-0.5);
          break;
        case 'W': // Step 0.5s forward
          e.preventDefault();
          stepSeconds(0.5);
          break;
        case 'S': // Set window start from playhead (anchors start framing)
          e.preventDefault();
          setWindowStartFromPlayhead();
          break;
        case 'E': // Set window end from playhead
          e.preventDefault();
          setWindowEndFromPlayhead();
          break;
        case ' ': // Play / Pause
          e.preventDefault();
          if (el.finalVideoModal && el.finalVideoModal.style.display !== 'none') {
            togglePreviewPlayer();
          } else {
            togglePlayPause();
          }
          break;
        case 'K': // Drop or update keyframe at playhead
          e.preventDefault();
          addKeyframeAtPlayhead();
          break;
        case 'R': // Replay preview
          e.preventDefault();
          playReplayPreview();
          break;
        case '[': // Also set window start from playhead
          e.preventDefault();
          setWindowStartFromPlayhead();
          break;
        case ']': // Also set window end from playhead
          e.preventDefault();
          setWindowEndFromPlayhead();
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
    if (el.btnWatchFinal) el.btnWatchFinal.addEventListener('click', openPreviewPlayer);
    if (el.btnCloseFinalVideo) el.btnCloseFinalVideo.addEventListener('click', closePreviewPlayer);
    if (el.btnFinalVideoClose) el.btnFinalVideoClose.addEventListener('click', closePreviewPlayer);
    if (el.btnFinalVideoTogglePlay) el.btnFinalVideoTogglePlay.addEventListener('click', togglePreviewPlayer);
    if (el.finalVideoPlayer) {
      el.finalVideoPlayer.addEventListener('play', () => {
        if (el.btnFinalVideoTogglePlay) el.btnFinalVideoTogglePlay.textContent = '❚❚ Pause';
      });
      el.finalVideoPlayer.addEventListener('pause', () => {
        if (el.btnFinalVideoTogglePlay) el.btnFinalVideoTogglePlay.textContent = '▶ Play';
      });
    }
    el.btnOpenDocs.addEventListener('click', () => {
      el.shortcutsModal.style.display = 'flex';
    });
    el.btnCloseShortcuts.addEventListener('click', () => {
      el.shortcutsModal.style.display = 'none';
    });

    // Transport buttons
    el.btnSeekStart.addEventListener('click', () => seekToSource(state.start));
    if (el.btnSetStartTransport) el.btnSetStartTransport.addEventListener('click', setWindowStartFromPlayhead);
    if (el.btnStepBack1s) el.btnStepBack1s.addEventListener('click', () => stepSeconds(-1.0));
    el.btnStepBackHalf.addEventListener('click', () => stepSeconds(-0.5));
    el.btnStepBackFrame.addEventListener('click', () => stepSeconds(-FRAME_STEP));
    el.btnPlayPause.addEventListener('click', togglePlayPause);
    el.btnStepFwdFrame.addEventListener('click', () => stepSeconds(FRAME_STEP));
    el.btnStepFwdHalf.addEventListener('click', () => stepSeconds(0.5));
    if (el.btnStepFwd1s) el.btnStepFwd1s.addEventListener('click', () => stepSeconds(1.0));
    if (el.btnSetEndTransport) el.btnSetEndTransport.addEventListener('click', setWindowEndFromPlayhead);
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
    let windowShiftDebounceTimer = null;

    function applyWindowStartChange(val) {
      const parsed = parseFloat(val);
      const preRoll = isNaN(parsed) ? 2.5 : Math.abs(parsed);
      const newStart = Math.max(0, state.event - preRoll);
      const prevStart = state.start;
      const diff = state.start - newStart;
      state.start = newStart;
      const prevEnd = prevStart + state.dur;
      state.dur = Math.max(2.0, prevEnd - newStart);
      updateInspectorFields();
      markPlanModified('Window start offset adjusted');
      seekToSource(state.start);
      updateCropBoxScreen();

      if (Math.abs(diff) > 0.1) {
        updateWorkflowNotice(`⚠️ Window start shifted to ${state.start.toFixed(1)}s (${preRoll.toFixed(1)}s before event). Verify framing at start.`, 'warning');
        if (windowShiftDebounceTimer) clearTimeout(windowShiftDebounceTimer);
        windowShiftDebounceTimer = setTimeout(() => {
          showToast(`⚠️ Window start shifted by ${Math.abs(diff).toFixed(1)}s (to ${state.start.toFixed(1)}s). Please verify START crop framing.`, 'warning', 3500);
        }, 500);
      }
    }

    function applyWindowEndChange(val) {
      const parsed = parseFloat(val);
      const postRoll = isNaN(parsed) ? 2.5 : Math.abs(parsed);
      const newEnd = state.event + postRoll;
      state.dur = Math.max(2.0, newEnd - state.start);
      updateInspectorFields();
      markPlanModified('Window end offset adjusted');
    }

    el.inpWinStartOffset.addEventListener('change', (e) => {
      applyWindowStartChange(e.target.value);
    });
    el.inpWinStartOffset.addEventListener('input', (e) => {
      applyWindowStartChange(e.target.value);
    });

    el.inpWinEndOffset.addEventListener('change', (e) => {
      applyWindowEndChange(e.target.value);
    });
    el.inpWinEndOffset.addEventListener('input', (e) => {
      applyWindowEndChange(e.target.value);
    });

    if (el.btnSetStart) el.btnSetStart.addEventListener('click', setWindowStartFromPlayhead);
    if (el.btnSetEnd) el.btnSetEnd.addEventListener('click', setWindowEndFromPlayhead);

    // Trims & Hold
    el.inpCutStart.addEventListener('change', (e) => {
      state.cutStart = Math.max(0, parseFloat(e.target.value) || 0);
      updateTimelineUI();
      markPlanModified('In-trim (cut start) adjusted');
    });

    el.inpCutEnd.addEventListener('change', (e) => {
      state.cutEnd = Math.max(0, parseFloat(e.target.value) || 0);
      updateTimelineUI();
      markPlanModified('Out-trim (cut end) adjusted');
    });

    el.inpHoldEnd.addEventListener('change', (e) => {
      state.holdEnd = Math.max(0, parseFloat(e.target.value) || 0);
      markPlanModified('End hold duration adjusted');
    });

    // Ensure input events also trigger unsaved changes flag
    [el.inpCutStart, el.inpCutEnd, el.inpHoldEnd].forEach(inp => {
      if (inp) {
        inp.addEventListener('input', () => { markPlanModified('Inspector parameter adjusted'); });
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

    // Keyframes & Pitch Anchor
    el.btnAddKeyframe.addEventListener('click', addKeyframeAtPlayhead);
    if (el.btnToggleAnchor) el.btnToggleAnchor.addEventListener('click', togglePitchAnchor);

    // Auto-frame handlers
    if (el.btnAutoFrame) el.btnAutoFrame.addEventListener('click', applyAutoFrameCurrent);
    if (el.btnUnplacedAutoFrame) el.btnUnplacedAutoFrame.addEventListener('click', applyAutoFrameCurrent);
    if (el.btnUnplacedAutoFrameAll) el.btnUnplacedAutoFrameAll.addEventListener('click', applyAutoFrameAll);

    // Click on video stage or unplaced overlay to place unplaced crop box
    function handleUnplacedStageClick(e) {
      if (!state.isUnplaced) return;
      if (e.target.closest('#unplacedNotice button') || e.target.closest('.unplaced-box')) return;
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
      state.hasUnsavedChanges = true;
      updateStatusBadge('unreviewed');
      updateCropBoxScreen();
      showToast('Crop box placed! Adjust position and press S (or Start button) to lock.', 'info', 4000);
      updateWorkflowNotice('🎯 Crop box placed. Adjust framing and press S to lock the Start position.', 'info');
    }

    el.videoStage.addEventListener('click', handleUnplacedStageClick);
    if (el.unplacedNotice) el.unplacedNotice.addEventListener('click', handleUnplacedStageClick);

    // Scope change updates button text
    if (el.selRenderScope) {
      el.selRenderScope.addEventListener('change', () => {
        updateRenderButtonText();
      });
    }

    // Reset Clip: restore default window start/end, clear trims, clear pans, and restore 2.5x center framing
    function resetClipToDefaults() {
      markPlanModified('Clip reset to default window and framing');
      const def = state.defaultWindow || { start: Math.max(0, state.event - 2.5), dur: 4.5 };
      state.start = def.start;
      state.dur = def.dur;
      state.cutStart = 0.0;
      state.cutEnd = 0.0;
      state.holdEnd = 0.0;
      state.pans = [];
      state.zoomTo = null;
      state.userStagedCrop = null;
      state.isPitchAnchored = false;
      updateAnchorButtonUI();
      setZoomRatio(2.5, false);
      state.cropX = Math.round((REF_W - state.cropW) / 2);
      state.cropY = Math.round((REF_H - state.cropH) / 2);
      state.baseCrop = [state.cropX, state.cropY];
      state.isAutoPlaced = false;
      clampCrop();
      renderKeyframesList();
      renderScrubberKeyframes();
      updateInspectorFields();
      seekToSource(state.start);
      updateTimelineUI();
      updateCropBoxScreen();
      updateWorkflowNotice('↺ Clip reset: default window, trims, framing, and keyframes restored.', 'info');
      showToast('Clip reset: default window (start/end), trims, framing, and keyframes restored', 'info', 3000);
    }

    if (el.btnResetClipWindow) el.btnResetClipWindow.addEventListener('click', resetClipToDefaults);
    if (el.btnAutoStart) el.btnAutoStart.addEventListener('click', resetClipToDefaults);
    el.btnSavePlan.addEventListener('click', savePlan);
    el.btnPreviewReplay.addEventListener('click', playReplayPreview);
    el.btnRenderExact.addEventListener('click', () => {
      if (isReadyPreview()) {
        openPreviewPlayer();
      } else {
        renderExact();
      }
    });
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
    if (el.zoomLogAutoClose) {
      if (localStorage.getItem('xbotgo.zoomLogAutoClose') === '0') {
        el.zoomLogAutoClose.checked = false;
      }
      el.zoomLogAutoClose.addEventListener('change', () => {
        try {
          localStorage.setItem('xbotgo.zoomLogAutoClose', el.zoomLogAutoClose.checked ? '1' : '0');
        } catch (_) {}
      });
    }
    el.btnCloseLogDrawer.addEventListener('click', () => {
      if (drawerAutoCloseTimer) {
        clearTimeout(drawerAutoCloseTimer);
        drawerAutoCloseTimer = null;
      }
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
        closePreviewPlayer();
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
