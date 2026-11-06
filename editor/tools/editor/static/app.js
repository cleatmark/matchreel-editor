/**
 * XbotGo Review Editor - Frontend Application
 */

// Application State
const state = {
  games: [],
  currentGameId: null,
  headers: [],
  rows: [],
  pristineRows: [], // Snapshot of rows when loaded or saved
  videos: {},
  selectedRowIndex: 0,
  activeTimeField: 'video_time',
  filterHalf: 'all',
  filterType: 'all',
  showSkipped: true,
  undoStack: [],
  clipUndoHistory: {}, // rowIndex -> array of row snapshots for per-clip undo
  isDirty: false,
  loopingAction: false,
  loopTimer: null,
  editingInspectorField: null,
  timelineZoom: {
    isZoomed: true, // true: 30s around mark; false: full video
    startSec: 0,
    endSec: 30,
  },
  activeTimelineLine: null,
  gameInfo: null,
  availableLogos: [],
  roster: [],
  featuredPlayer: '',
  playerSelectRowIndex: null,
  autoPlayOnSelect: true,
  currentMediaCategory: 'clips720',
  mediaFiles: [],
  selectedMediaIndex: 0,
};

// HTML Escaping Utility (available globally across entire script)
function escapeSafe(str) {
  return String(str || '').replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[c] || c));
}
function escapeHtml(str) {
  return escapeSafe(str);
}
window.escapeSafe = escapeSafe;
window.escapeHtml = escapeHtml;

// DOM Elements
const el = {
  gameSelect: document.getElementById('gameSelect'),
  halfFilter: document.getElementById('halfFilter'),
  filterHalfAll: document.getElementById('filterHalfAll'),
  filterHalf1: document.getElementById('filterHalf1'),
  filterHalf2: document.getElementById('filterHalf2'),
  typeFilter: document.getElementById('typeFilter'),
  toggleSkippedBtn: document.getElementById('toggleSkipped'),
  toggleSkippedCheck: document.getElementById('toggleSkippedCheck'),
  saveStatus: document.getElementById('saveStatus'),
  sheetSyncStatus: document.getElementById('sheetSyncStatus'),
  saveBtn: document.getElementById('saveBtn'),
  recutBtn: document.getElementById('recutBtn'),
  recutDropdownMenu: document.getElementById('recutDropdownMenu'),
  mediaReviewModal: document.getElementById('mediaReviewModal'),
  mediaReviewVideo: document.getElementById('mediaReviewVideo'),
  chkAutoPlayOnSelect: document.getElementById('chkAutoPlayOnSelect'),
  pushSheetBtn: document.getElementById('pushSheetBtn'),
  autoSyncSheet: document.getElementById('autoSyncSheet'),
  undoBtn: document.getElementById('undoBtn'),
  undoClipBtn: document.getElementById('undoClipBtn'),
  rowCountDisplay: document.getElementById('rowCountDisplay'),
  timesPanel: document.getElementById('timesPanel'),
  videoPanel: document.getElementById('videoPanel'),
  paneResizer: document.getElementById('paneResizer'),
  videoResizer: document.getElementById('videoResizer'),
  playerWrapper: document.getElementById('playerWrapper'),
  videoFitPill: document.getElementById('videoFitPill'),
  videoZoomPill: document.getElementById('videoZoomPill'),
  timesTableBody: document.getElementById('timesTableBody'),
  mainVideo: document.getElementById('mainVideo'),
  currentVideoFile: document.getElementById('currentVideoFile'),
  videoCurrentTime: document.getElementById('videoCurrentTime'),
  videoOverlayMsg: document.getElementById('videoOverlayMsg'),
  timelineContainer: document.getElementById('timelineContainer'),
  timelineActionWindow: document.getElementById('timelineActionWindow'),
  timelinePlayhead: document.getElementById('timelinePlayhead'),
  timelineRuler: document.getElementById('timelineRuler'),
  timelineWindowLabel: document.getElementById('timelineWindowLabel'),
  btnModeZoom: document.getElementById('btnModeZoom'),
  btnModeFull: document.getElementById('btnModeFull'),
  timelineMarkLine: document.getElementById('timelineMarkLine'),
  timelineStartLine: document.getElementById('timelineStartLine'),
  timelineEventLine: document.getElementById('timelineEventLine'),
  timelineEndLine: document.getElementById('timelineEndLine'),
  playPauseBtn: document.getElementById('playPauseBtn'),
  speed1x: document.getElementById('speed1x'),
  
  // Modals
  calendarModal: document.getElementById('calendarModal'),
  calendarDateInput: document.getElementById('calendarDateInput'),
  availableDatesList: document.getElementById('availableDatesList'),
  calendarModalFeedback: document.getElementById('calendarModalFeedback'),
  calendarSubmitBtn: document.getElementById('calendarSubmitBtn'),
  logModal: document.getElementById('logModal'),
  logModalTitle: document.getElementById('logModalTitle'),
  logModalPre: document.getElementById('logModalPre'),
  logModalStatus: document.getElementById('logModalStatus'),
  logModalCloseBtn: document.getElementById('logModalCloseBtn'),
  logAutoClose: document.getElementById('logAutoClose'),

  // Row Inspector
  inspectorClipLabel: document.getElementById('inspectorClipLabel'),
  inspectorTypeBadge: document.getElementById('inspectorTypeBadge'),
  inspectorRowLabel: document.getElementById('inspectorRowLabel'),
  inspectorWarning: document.getElementById('inspectorWarning'),
  lblMark: document.getElementById('lblMark'),
  lblStart: document.getElementById('lblStart'),
  lblEvent: document.getElementById('lblEvent'),
  lblEnd: document.getElementById('lblEnd'),
  inspValMark: document.getElementById('inspValMark'),
  inspWrapMark: document.getElementById('inspWrapMark'),
  markTimeBtnRow: document.getElementById('markTimeBtnRow'),
  inspMarkEditHint: document.getElementById('inspMarkEditHint'),
  inspValStart: document.getElementById('inspValStart'),
  inspValEvent: document.getElementById('inspValEvent'),
  inspValEnd: document.getElementById('inspValEnd'),
  inspPlayer: document.getElementById('inspPlayer'),
  inspNotes: document.getElementById('inspNotes'),
  inspToggleZoom: document.getElementById('inspToggleZoom'),
  inspToggleSkip: document.getElementById('inspToggleSkip'),

  // Player Multi-Select Modal
  playerSelectModal: document.getElementById('playerSelectModal'),
  playerSelectList: document.getElementById('playerSelectList'),
  playerSelectTitle: document.getElementById('playerSelectTitle'),
  playerSelectDesc: document.getElementById('playerSelectDesc'),
  playerSelectSummary: document.getElementById('playerSelectSummary'),
  btnSavePlayerSelect: document.getElementById('btnSavePlayerSelect'),
};

// Utilities: Seconds <-> MM:SS
function parseTime(val) {
  if (!val) return null;
  const s = String(val).trim();
  if (!s || s === '-') return null;
  const parts = s.split(':').map(Number);
  if (parts.some(isNaN)) return null;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) {
    if (parts[0] === 0) return parts[1] * 60 + parts[2];
    return parts[0] * 60 + parts[1]; // Sheets mangled
  }
  return null;
}

function formatTime(totalSec) {
  if (totalSec === null || totalSec === undefined || totalSec < 0 || isNaN(totalSec)) return '';
  const roundedTenth = Math.round(totalSec * 10) / 10;
  const isWhole = Math.abs(roundedTenth - Math.round(roundedTenth)) < 0.001;
  if (isWhole) {
    const tot = Math.round(roundedTenth);
    const m = Math.floor(tot / 60);
    const s = tot % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  } else {
    const m = Math.floor(roundedTenth / 60);
    const rem = roundedTenth % 60;
    const s = Math.floor(rem);
    const tenth = Math.round((rem - s) * 10);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${tenth}`;
  }
}

function formatTimeFraction(sec) {
  if (sec === null || sec === undefined || isNaN(sec)) return '00:00.0';
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  const tenths = Math.floor((sec % 1) * 10);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${tenths}`;
}

// 24-hour time formatting (HH:MM:SS) for UI timestamps
function format24hTime(d = new Date()) {
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// In-Page Toast Notifications
function showToast(message, type = 'info', durationMs = 3500) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const t = document.createElement('div');
  t.className = `app-toast toast-${type}`;
  t.textContent = message;
  container.appendChild(t);
  setTimeout(() => {
    t.classList.add('fade-out');
    setTimeout(() => t.remove(), 250);
  }, durationMs);
}

// In-Page Confirm Dialog
let confirmResolver = null;
function showConfirm(promptText, title = 'Confirm Action', okText = 'OK', okClass = 'btn-danger') {
  return new Promise((resolve) => {
    confirmResolver = resolve;
    const modal = document.getElementById('confirmModal');
    if (!modal) {
      resolve(false);
      return;
    }
    document.getElementById('confirmModalTitle').textContent = title;
    document.getElementById('confirmModalPrompt').textContent = promptText;
    const okBtn = document.getElementById('confirmModalOkBtn');
    okBtn.textContent = okText;
    okBtn.className = `btn btn-sm ${okClass}`;
    modal.style.display = 'flex';
  });
}

function closeConfirmModal(result) {
  const modal = document.getElementById('confirmModal');
  if (modal) modal.style.display = 'none';
  if (confirmResolver) {
    confirmResolver(result);
    confirmResolver = null;
  }
}
window.showConfirm = showConfirm;
window.closeConfirmModal = closeConfirmModal;

// Parse 24-hour clock string (HH:MM:SS) into seconds from midnight
function parseClockTime(ctStr) {
  if (!ctStr || typeof ctStr !== 'string') return null;
  const parts = ctStr.trim().split(':');
  if (parts.length === 3) {
    const h = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    const s = parseInt(parts[2], 10);
    if (!isNaN(h) && !isNaN(m) && !isNaN(s)) {
      return h * 3600 + m * 60 + s;
    }
  }
  return null;
}

function hasAssignedPlayer(playerStr) {
  if (!playerStr) return false;
  const tokens = String(playerStr)
    .split(/[,;/&+]+/)
    .map((t) => t.trim())
    .filter((t) => t && !['op', '?'].includes(t.toLowerCase()));
  return tokens.length > 0;
}
window.hasAssignedPlayer = hasAssignedPlayer;

// Renumber clips sequentially 1..N across active rows
// Rows skipped without an assigned player get empty clip numbers.
// Rows with skip + an assigned player get numbered so their personal highlight clips can be cut.
function recomputeClips() {
  let clipNum = 1;
  state.rows.forEach((r) => {
    if (isRowSkipped(r) && !hasAssignedPlayer(r.player)) {
      r.clip = '';
    } else {
      r.clip = clipNum++;
    }
  });
}

// Insert row at current video playhead
function insertRowAtPlayhead() {
  if (!state.rows || state.rows.length === 0) return;

  const currentSec = Math.round(el.mainVideo.currentTime || 0);
  const dur = el.mainVideo.duration && !isNaN(el.mainVideo.duration) ? Math.round(el.mainVideo.duration) : null;

  // Active video filename and game
  const currentFile = state.currentVideoFile || (state.rows[state.selectedRowIndex] ? state.rows[state.selectedRowIndex].file : state.rows[0].file);
  const game = state.rows[0].game || state.currentGameId;

  // Timings: start = playhead - 10s, event = playhead, end = playhead + 0s
  const actionStartSec = Math.max(0, currentSec - 10);
  const eventSec = currentSec;
  const actionEndSec = dur ? Math.min(dur, currentSec) : currentSec;

  const actionStartStr = formatTime(actionStartSec);
  const eventStr = formatTime(eventSec);
  const actionEndStr = formatTime(actionEndSec);
  const videoTimeStr = formatTime(currentSec);

  // Derive file start time from neighbouring rows in same file
  const sameFileRows = state.rows.filter(r => r.file === currentFile);
  let fileStartSec = null;
  for (const r of sameFileRows) {
    if (r.clock_time && r.video_sec !== undefined && r.video_sec !== '') {
      const ctSec = parseClockTime(r.clock_time);
      const vs = Number(r.video_sec);
      if (ctSec !== null && !isNaN(vs)) {
        fileStartSec = ctSec - vs;
        break;
      }
    }
  }

  // Fallback to video filename timestamp (e.g. 2026-03-29-10-41-31...)
  if (fileStartSec === null && currentFile) {
    const fnMatch = currentFile.match(/\d{4}-\d{2}-\d{2}-(\d{2})-(\d{2})-(\d{2})/);
    if (fnMatch) {
      fileStartSec = parseInt(fnMatch[1], 10) * 3600 + parseInt(fnMatch[2], 10) * 60 + parseInt(fnMatch[3], 10);
    }
  }

  // Derive 24-hour clock_time (HH:MM:SS)
  let clockTimeStr = '';
  if (fileStartSec !== null) {
    const totalClockSec = ((fileStartSec + currentSec) % 86400 + 86400) % 86400;
    const hh = String(Math.floor(totalClockSec / 3600)).padStart(2, '0');
    const mm = String(Math.floor((totalClockSec % 3600) / 60)).padStart(2, '0');
    const ss = String(totalClockSec % 60).padStart(2, '0');
    clockTimeStr = `${hh}:${mm}:${ss}`;
  }

  // Determine half
  let half = '1';
  const sortedSameFile = [...sameFileRows].sort((a, b) => Number(a.video_sec || 0) - Number(b.video_sec || 0));
  let predecessor = null;
  let successor = null;
  for (const r of sortedSameFile) {
    const vs = Number(r.video_sec || 0);
    if (vs <= currentSec) {
      predecessor = r;
    } else if (!successor) {
      successor = r;
    }
  }

  if (predecessor && successor && predecessor.half === successor.half) {
    half = predecessor.half;
  } else if (predecessor) {
    half = predecessor.half;
  } else if (successor) {
    half = successor.half;
  } else if (state.rows[state.selectedRowIndex]) {
    half = state.rows[state.selectedRowIndex].half;
  }

  // Derive game_clock from nearest earlier row in the same half
  let gameClockStr = '';
  for (let i = state.rows.length - 1; i >= 0; i--) {
    const r = state.rows[i];
    if (String(r.half) === String(half) && Number(r.video_sec || 0) <= currentSec && r.game_clock) {
      const priorGcSec = parseTime(r.game_clock);
      if (priorGcSec !== null) {
        const gap = currentSec - Number(r.video_sec || 0);
        const newGcSec = Math.max(0, priorGcSec + gap);
        const gm = Math.floor(newGcSec / 60);
        const gs = newGcSec % 60;
        gameClockStr = `${gm}:${String(gs).padStart(2, '0')}`;
        break;
      }
    }
  }

  // Construct new row object with all 16 columns
  const newRow = {
    game: game,
    half: half,
    type: 'mark',
    label: '',
    file: currentFile,
    video_time: videoTimeStr,
    video_sec: currentSec,
    clock_time: clockTimeStr,
    game_clock: gameClockStr,
    notes: 'manual',
    action_start: actionStartStr,
    event: eventStr,
    action_end: actionEndStr,
    player: '',
    instructions: '',
    clip: '',
    _manual: true,
  };

  recordHistory();

  // Insert in chronological order by video_sec
  let insertIdx = state.rows.length;
  for (let i = 0; i < state.rows.length; i++) {
    const r = state.rows[i];
    if (r.file === currentFile) {
      if (Number(r.video_sec || 0) > currentSec) {
        insertIdx = i;
        break;
      }
    }
  }

  state.rows.splice(insertIdx, 0, newRow);
  recomputeClips();
  setDirty(true);

  renderTable();
  selectRow(insertIdx);
  updateInspector();
  updateTimelineActionWindow();

  // Scroll inserted row into view
  setTimeout(() => {
    const tr = el.timesTableBody.querySelector(`tr[data-row-index="${insertIdx}"]`);
    if (tr) tr.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, 30);
}

// Delete user-added row
async function deleteManualRow(idx, e) {
  if (e) e.stopPropagation();
  const row = state.rows[idx];
  if (!row) return;

  const isManual = Boolean(row._manual || (row.notes && row.notes.toLowerCase().includes('manual')));
  if (!isManual) return;

  const timeLabel = row.video_time || row.event || `Row ${idx + 1}`;
  const ok = await showConfirm(`Delete added row at ${timeLabel}?`, 'Delete Row', 'Delete', 'btn-danger');
  if (!ok) return;

  recordHistory();
  state.rows.splice(idx, 1);
  recomputeClips();
  setDirty(true);

  const nextSelected = Math.max(0, Math.min(idx, state.rows.length - 1));
  renderTable();
  selectRow(nextSelected);
  updateInspector();
  updateTimelineActionWindow();
}

// Open Zoom Replay Editor in single dedicated window/tab
function onZoomChipClick(e, url) {
  if (e) e.preventDefault();
  const win = window.open(url, 'xbotgo_zoom');
  if (win) {
    win.focus();
  } else {
    window.location.href = url;
  }
}

// Push undo state before mutation
function recordHistory(rowIndex = state.selectedRowIndex) {
  // Global undo stack
  const snapshot = JSON.stringify({
    rows: state.rows,
    selectedRowIndex: state.selectedRowIndex,
  });
  state.undoStack.push(snapshot);
  if (state.undoStack.length > 50) state.undoStack.shift();
  setDirty(true);
  el.undoBtn.disabled = false;

  // Per-clip undo stack
  if (rowIndex !== null && rowIndex !== undefined && state.rows[rowIndex]) {
    state.clipUndoHistory[rowIndex] = state.clipUndoHistory[rowIndex] || [];
    state.clipUndoHistory[rowIndex].push(JSON.stringify(state.rows[rowIndex]));
    if (state.clipUndoHistory[rowIndex].length > 50) state.clipUndoHistory[rowIndex].shift();
    if (rowIndex === state.selectedRowIndex && el.undoClipBtn) {
      el.undoClipBtn.disabled = false;
    }
  }
}

// Undo only changes made to the currently selected clip
function undoClip() {
  const idx = state.selectedRowIndex;
  if (!state.clipUndoHistory[idx] || state.clipUndoHistory[idx].length === 0) return;

  // skip snapshots identical to the current row (a no-op step must not eat an Undo click)
  const currentStr = JSON.stringify(state.rows[idx]);
  let prevStr = state.clipUndoHistory[idx].pop();
  while (prevStr === currentStr && state.clipUndoHistory[idx].length > 0) prevStr = state.clipUndoHistory[idx].pop();
  if (prevStr === currentStr) {
    if (el.undoClipBtn) el.undoClipBtn.disabled = true;
    return;
  }
  const previousClipState = JSON.parse(prevStr);
  state.rows[idx] = previousClipState;

  const wasLooping = state.loopingAction;     // selectRow() stops the loop; keep it running like before the undo
  renderTable();
  selectRow(idx);
  updateInspector();
  if (wasLooping) toggleActionLoop();

  if (el.undoClipBtn) {
    el.undoClipBtn.disabled = state.clipUndoHistory[idx].length === 0;
  }
}

function setDirty(dirty) {
  state.isDirty = dirty;
  if (dirty) {
    el.saveStatus.className = 'status-badge status-dirty';
    el.saveStatus.textContent = 'Unsaved changes';
  } else {
    el.saveStatus.className = 'status-badge status-clean';
    el.saveStatus.textContent = 'All changes saved';
  }
}

// Warn before the tab is closed/reloaded with unsaved edits (browsers show their own generic text).
window.addEventListener('beforeunload', (e) => {
  if (state.isDirty) {
    e.preventDefault();
    e.returnValue = '';
    return '';
  }
});

// Initialize Application
async function init() {
  await loadGlobalDefaults();
  window.loadGame = loadGame;
  window.checkBuildInfo = checkBuildInfo;
  checkBuildInfo();
  setInterval(checkBuildInfo, 60000);
  setupEventListeners();
  setupPaneResizer();
  setupVideoResizer();
  setupVideoViewportZoom();

  // Initialize auto-play on select preference (P3)
  try {
    const savedAutoPlay = localStorage.getItem('review_editor_autoplay_on_select');
    if (savedAutoPlay !== null) {
      state.autoPlayOnSelect = savedAutoPlay === 'true';
    } else {
      state.autoPlayOnSelect = true;
    }
  } catch (e) {
    state.autoPlayOnSelect = true;
  }
  const chkAutoPlay = document.getElementById('chkAutoPlayOnSelect');
  if (chkAutoPlay) chkAutoPlay.checked = state.autoPlayOnSelect;

  // Initialize Auto-push on save preference (default to false to protect production sheets)
  if (el.autoSyncSheet) {
    try {
      const savedAutoPush = localStorage.getItem('xbotgo.autoPushSheet');
      el.autoSyncSheet.checked = (savedAutoPush === '1');
    } catch (_) {
      el.autoSyncSheet.checked = false;
    }
    el.autoSyncSheet.addEventListener('change', () => {
      try {
        localStorage.setItem('xbotgo.autoPushSheet', el.autoSyncSheet.checked ? '1' : '0');
      } catch (_) {}
    });
  }

  // Load roster data for quick player chips and modals
  loadRosterData().catch(() => {});

  setupWindowFocusSync();
  await loadGamesList();
}

async function checkBuildInfo() {
  try {
    const res = await fetch('/api/build-info');
    if (!res.ok) return;
    const data = await res.json();
    const lbl = document.getElementById('lblServerStart');
    if (lbl && (data.server_start_str || data.server_start)) {
      lbl.textContent = data.server_start_str || formatTime(data.server_start);
      lbl.title = data.server_start_datetime || '';
    }
    const banner = document.getElementById('staleServerBanner');
    if (banner) {
      if (data.is_stale) {
        banner.style.display = 'block';
        banner.textContent = `⚠️ Server process is stale! Server was started at ${data.server_start_str || ''}, but files were modified at ${data.build_time_str || ''}. Please restart review_editor.bat.`;
      } else {
        banner.style.display = 'none';
      }
    }
  } catch (err) {
    console.debug('Failed to check build-info:', err);
  }
}

// Load List of Games
async function loadGamesList(selectedId) {
  try {
    const res = await fetch('/api/games');
    const data = await res.json();
    state.games = data.games || [];
    el.gameSelect.innerHTML = '<option value="__pick__">📅 Pick game...</option>';
    state.games.forEach((g) => {
      const opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = g.name;
      el.gameSelect.appendChild(opt);
    });

    const urlParam = (new URLSearchParams(window.location.search)).get('game');
    const targetId = selectedId || (urlParam && state.games.some(g => g.id === urlParam) ? urlParam : null);
    if (targetId) {
      el.gameSelect.value = targetId;
      await loadGame(targetId);
    } else {
      el.gameSelect.value = '__pick__';
    }
  } catch (err) {
    console.error('Failed to load games:', err);
  }
}

function onGameSelectChange() {
  const val = el.gameSelect.value;
  if (val === '__pick__') {
    openCalendarModal();
  } else if (val) {
    loadGame(val);
  }
}

// Check if a row was manually added by user in editor
function isManualRow(row) {
  if (!row) return false;
  return Boolean(row._manual || (row.notes && row.notes.toLowerCase().includes('manual')));
}
window.isManualRow = isManualRow;

// Check if a row has unsaved modifications
function isRowModified(idx) {
  if (!state.pristineRows || !state.pristineRows[idx]) return true; // Newly added rows are modified/dirty
  const pristine = state.pristineRows[idx];
  const current = state.rows[idx];
  if (!current) return false;
  if (Boolean(current._manual) !== Boolean(pristine._manual)) return true;
  const fields = ['action_start', 'event', 'action_end', 'video_time', 'player', 'notes', 'instructions', 'skip'];
  return fields.some((f) => (current[f] || '').trim() !== (pristine[f] || '').trim());
}

// Check if a row has been adjusted / modified from raw unreviewed import
function isRowAdjusted(row, idx) {
  if (!row || isRowSkipped(row)) return false;
  if (row._adjusted) return true;
  if ((row.player || '').trim().length > 0) return true;
  const inst = (row.instructions || '').toLowerCase();
  if (inst.includes('zoom')) return true;
  const notes = (row.notes || '').trim();
  if (notes && !notes.startsWith('mark+goal') && !notes.startsWith('goal') && notes !== 'mark') return true;
  if (isManualRow(row)) return true;

  // Compare timing against raw unreviewed import defaults (m - 12s, m, m + 4s)
  const m = parseTime(row.video_time);
  if (m !== null) {
    const rawStart = formatTime(Math.max(0, m - 12));
    const rawEvent = formatTime(m);
    const rawEnd = formatTime(m + 4);
    if (row.action_start && row.action_start !== rawStart) return true;
    if (row.event && row.event !== rawEvent && row.event !== row.video_time) return true;
    if (row.action_end && row.action_end !== rawEnd) return true;
  }
  return false;
}

function refreshDirtyStatus() {
  const countChanged = state.pristineRows && state.rows.length !== state.pristineRows.length;
  const anyModified = countChanged || state.rows.some((_, i) => isRowModified(i));
  setDirty(anyModified);
}

// Load Selected Game
async function loadGame(gameId) {
  try {
    state.currentGameId = gameId;
    el.gameSelect.value = gameId;
    try {
      const url = new URL(window.location);
      if (url.searchParams.get('game') !== gameId) {
        url.searchParams.set('game', gameId);
        window.history.replaceState({ gameId }, '', url.toString());
      }
    } catch (_) {}
    const res = await fetch(`/api/game/${gameId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    state.headers = data.headers;
    state.rows = data.rows || [];
    state.csvRevision = data.revision || '';
    state.pristineRows = JSON.parse(JSON.stringify(state.rows));
    state.videos = data.videos || {};
    state.undoStack = [];
    state.clipUndoHistory = {};
    state.selectedRowIndex = 0;
    setDirty(false);
    el.undoBtn.disabled = true;
    if (el.undoClipBtn) el.undoClipBtn.disabled = true;
    if (el.sheetSyncStatus) {
      el.sheetSyncStatus.style.display = 'none';
      el.sheetSyncStatus.removeAttribute('href');
    }

    renderTable();
    if (state.rows.length > 0) {
      selectRow(0);
    }

    state.gameInfo = data.game_info || null;

    // Load zoom replays state for unreviewed chips
    fetch(`/api/zoom/${gameId}`)
      .then(r => r.ok ? r.json() : null)
      .then(zData => {
        if (zData && zData.replays) {
          state.zoomReplaysMap = {};
          zData.replays.forEach(r => {
            state.zoomReplaysMap[String(r.clip)] = r;
            state.zoomReplaysMap[r.token] = r;
          });
          renderTable();
        }
      })
      .catch(() => {});

    // Check production lock status
    checkProductionStatus();

    // Quick setup wizard for brand-new games missing opponent or away_logo
    const needsSetup = !data.game_info ||
      !data.game_info.away_logo ||
      data.game_info.away_logo === null ||
      !data.game_info.opponent ||
      data.game_info.opponent.trim() === '';
    if (needsSetup) {
      setTimeout(() => openGameInfoModal(true), 400);
    }
  } catch (err) {
    console.error(`Failed to load game ${gameId}:`, err);
    showToast(`Could not load game data for ${gameId}`, 'error');
  }
}

// Render Left Pane Times Table
function renderTable() {
  el.timesTableBody.innerHTML = '';
  let visibleCount = 0;

  state.rows.forEach((row, idx) => {
    // Filter by Half
    if (state.filterHalf !== 'all' && String(row.half).trim() !== String(state.filterHalf).trim()) {
      return;
    }
    // Filter by Type
    if (state.filterType !== 'all' && String(row.type).trim().toLowerCase() !== state.filterType.toLowerCase()) {
      return;
    }
    // Filter Skipped: completely skipped rows (no player) are hidden when showSkipped is false.
    // Rows with skip + assigned player are kept visible so they can be worked on for personal reels.
    const isSkipped = isRowSkipped(row);
    const hasPlayer = hasAssignedPlayer(row.player);
    if (!state.showSkipped && isSkipped && !hasPlayer) {
      return;
    }

    visibleCount++;
    const tr = document.createElement('tr');
    tr.dataset.rowIndex = idx;
    if (idx === state.selectedRowIndex) tr.classList.add('selected');
    if (isSkipped) tr.classList.add('skipped');

    // Check if this row is modified compared to saved state (unsaved) or already adjusted & saved
    const modified = isRowModified(idx);
    const adjusted = isRowAdjusted(row, idx);

    let clipHtml = '';
    if (row.clip) {
      if (modified) {
        clipHtml = `<span class="clip-dirty" title="Unsaved changes">${row.clip}*</span>`;
      } else if (adjusted) {
        clipHtml = `<span class="clip-num">${row.clip}</span><span class="clip-adjusted" title="Clip adjusted">†</span>`;
      } else {
        clipHtml = `<span class="clip-num">${row.clip}</span>`;
      }
    } else {
      if (modified) {
        clipHtml = `<span class="clip-dirty" title="Unsaved changes">*</span>`;
      } else if (adjusted) {
        clipHtml = `<span class="clip-adjusted" title="Clip adjusted">†</span>`;
      }
    }

    const rowStatusText = modified ? ' (Unsaved changes)' : (adjusted ? ' (Clip adjusted)' : '');
    const clipCellTitle = `Row ${idx + 1}${row.clip ? ` (Clip #${row.clip})` : ' (Skipped)'}${rowStatusText}`;

    // Check if user-added manual row
    const isManual = Boolean(row._manual || (row.notes && row.notes.toLowerCase().includes('manual')));
    const manualBadge = isManual ? '<span class="badge-manual" title="Manual row added in editor">manual</span>' : '';
    const deleteBtn = isManual ? `<button class="btn-delete-row" onclick="deleteManualRow(${idx}, event)" title="Delete manual row">✕</button>` : '';

    // Type Badge Class & Compact Combined Pill (e.g. M (2:43), G (8:48))
    let badgeClass = 'badge-mark';
    let typeLetter = 'M';
    const typeStr = (row.type || '').toLowerCase();
    if (typeStr.includes('goal')) {
      badgeClass = 'badge-goal';
      typeLetter = 'G';
    } else if (typeStr.includes('attempt')) {
      badgeClass = 'badge-attempt';
      typeLetter = 'A';
    }
    const typeMarkText = `${typeLetter} (${row.video_time || '--:--'})`;

    // Instructions chips
    let instChips = '';
    const instStr = (row.instructions || '').toLowerCase();
    if (instStr.includes('zoom')) {
      const clipId = row.clip || (idx + 1);
      instChips += `<a href="/zoom/${state.currentGameId}/${clipId}" target="xbotgo_zoom" rel="opener" onclick="onZoomChipClick(event, this.href)" class="chip-tag chip-zoom" title="Open in Zoom Replay Editor">ZOOM 🔍</a>`;
      const rep = state.zoomReplaysMap && (state.zoomReplaysMap[String(clipId)] || state.zoomReplaysMap[clipId]);
      const isReviewed = Boolean(rep && rep.reviewed === true && rep.crop !== null);
      if (!isReviewed) {
        instChips += `<span class="chip-tag" style="background:#D97706;color:#FFF;font-size:10px;padding:1px 5px;border-radius:3px;margin-left:3px;font-weight:600;" title="Crop not yet reviewed or unplaced">UNREV</span>`;
      } else if (rep && (rep.is_stale || rep.status === 'rendered (stale)')) {
        instChips += `<span class="chip-tag" style="background:#F59E0B;color:#1E293B;font-size:10px;padding:1px 5px;border-radius:3px;margin-left:3px;font-weight:700;" title="Replay plan modified after render - needs re-rendering">STALE</span>`;
      }
    }
    if (instStr.includes('skip') || row.skip) instChips += '<span class="chip-tag chip-skip">SKIP</span>';

    // Timing order validation check
    const sSec = parseTime(row.action_start);
    const eSec = parseTime(row.event);
    const endSec = parseTime(row.action_end);
    let timingInvalid = false;
    let timingWarn = '';
    if (sSec !== null && eSec !== null && sSec > eSec) {
      timingInvalid = true; timingWarn = `⚠️ Start (${row.action_start}) > Event (${row.event})`;
    } else if (eSec !== null && endSec !== null && eSec > endSec) {
      timingInvalid = true; timingWarn = `⚠️ Event (${row.event}) > End (${row.action_end})`;
    } else if (sSec !== null && endSec !== null && sSec > endSec) {
      timingInvalid = true; timingWarn = `⚠️ Start (${row.action_start}) > End (${row.action_end})`;
    }
    if (timingInvalid) {
      tr.classList.add('row-timing-invalid');
    } else {
      // Plausibility warning (action > 30s or start/end > 20s from mark)
      const mSec = parseTime(row.video_time);
      if (sSec !== null && endSec !== null && (endSec - sSec) > 30) {
        timingWarn = `⚠️ Long clip: ${endSec - sSec}s duration (>30s)`;
        tr.classList.add('row-timing-soft-warn');
      } else if (mSec !== null && sSec !== null && Math.abs(mSec - sSec) > 20) {
        timingWarn = `⚠️ Start is ${Math.abs(mSec - sSec)}s from mark (${row.video_time})`;
        tr.classList.add('row-timing-soft-warn');
      } else if (mSec !== null && endSec !== null && Math.abs(endSec - mSec) > 25) {
        timingWarn = `⚠️ End is ${Math.abs(endSec - mSec)}s from mark (${row.video_time})`;
        tr.classList.add('row-timing-soft-warn');
      }
    }

    tr.innerHTML = `
      <td class="col-clip" title="${clipCellTitle}">${clipHtml}${manualBadge}${deleteBtn}</td>
      <td class="col-type">
        <button type="button" class="type-mark-pill ${badgeClass}" title="Mark reference: ${escapeSafe(row.type || 'mark')} at ${escapeSafe(row.video_time || '--:--')} (Click to seek)" onclick="onTimeCellClick(${idx}, 'video_time', event)">
          ${typeMarkText}
        </button>
      </td>
      <td class="col-times">
        <div class="time-cells-grid-3" title="${timingWarn}">
          <button type="button" class="time-cell-btn" data-field="action_start" onclick="onTimeCellClick(${idx}, 'action_start', event)">${row.action_start || '--:--'}</button>
          <button type="button" class="time-cell-btn" data-field="event" onclick="onTimeCellClick(${idx}, 'event', event)">${row.event || '--:--'}</button>
          <button type="button" class="time-cell-btn" data-field="action_end" onclick="onTimeCellClick(${idx}, 'action_end', event)">${row.action_end || '--:--'}</button>
        </div>
      </td>
      <td class="col-player"><span class="player-tag" title="Double-click to edit player">${row.player || '-'}</span></td>
      <td class="col-instructions">
        <div class="flags-cell-wrapper" onclick="toggleFlagsDropdown(event, ${idx})" title="Click to edit flags (skip / zoom)">
          <span class="flags-chips">${instChips || '<span class="flags-empty">—</span>'}</span>
          <span class="flags-dropdown-arrow">▾</span>
        </div>
      </td>
      <td class="col-notes">${row.notes || row.label || ''}</td>
    `;

    // Row selection on click -> seeks video to action_start and starts playing on loop mode
    tr.addEventListener('click', (e) => {
      if (e.target.closest('button') || e.target.closest('a') || e.target.closest('input') || e.target.closest('.flags-cell-wrapper')) {
        return;
      }
      selectRow(idx, 'action_start');
      if (state.autoPlayOnSelect) {
        startActionLoop(idx);
      }
    });

    // In-place double-click editing on time cells
    const timeBtns = tr.querySelectorAll('.time-cell-btn');
    timeBtns.forEach((btn) => {
      btn.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        startInlineEdit(btn, idx, btn.dataset.field);
      });
    });

    // Double-click on player cell opens player selector modal
    const colPlayer = tr.querySelector('.col-player');
    if (colPlayer) {
      colPlayer.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        openPlayerSelectModal(idx);
      });
    }

    el.timesTableBody.appendChild(tr);
  });

  el.rowCountDisplay.textContent = `${visibleCount} of ${state.rows.length} rows`;
  refreshDirtyStatus();
}

function isRowSkipped(row) {
  const inst = (row.instructions || '').toLowerCase();
  const sk = String(row.skip || '').toLowerCase();
  return inst.includes('skip') || ['1', 'true', 'yes', 'skip', 'x'].includes(sk);
}

// Select a Row & Seek Video to Action Start (or specified targetField)
function selectRow(idx, targetField = 'action_start') {
  if (idx < 0 || idx >= state.rows.length) return;
  state.selectedRowIndex = idx;

  if (state.loopingAction || !state.autoPlayOnSelect) {
    stopActionLoop();
    if (!state.autoPlayOnSelect && el.mainVideo && !el.mainVideo.paused) {
      el.mainVideo.pause();
      if (el.playPauseBtn) el.playPauseBtn.textContent = '▶ Play';
    }
  }

  // Update visual selection in table
  const allRows = el.timesTableBody.querySelectorAll('tr');
  allRows.forEach((r) => {
    if (Number(r.dataset.rowIndex) === idx) {
      r.classList.add('selected');
      r.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } else {
      r.classList.remove('selected');
    }
  });

  state.timelineZoom.isZoomed = true; // Auto-focus to 30s zoom window on selection
  updateInspector();
  updateTimelineZoomWindow();

  if (el.undoClipBtn) {
    el.undoClipBtn.disabled = !(state.clipUndoHistory[idx] && state.clipUndoHistory[idx].length > 0);
  }

  const row = state.rows[idx];
  if (!row) return;

  // Load video segment file if needed
  if (row.file) {
    loadVideoSegment(row.file);
  }

  // Seek video: Row selection defaults to action_start (fall back to video_time if start not set)
  const seekField = targetField || 'action_start';
  state.activeTimeField = seekField;
  const timeStr = row[seekField] || row.action_start || row.video_time || '';
  const tSec = parseTime(timeStr);
  if (tSec !== null) {
    seekVideo(tSec);
  }
  setActiveTimelineLine(seekField);
}

// Handle time cell click: Seek video & select row
function onTimeCellClick(rowIndex, field, evt) {
  if (evt) {
    evt.stopPropagation();
  }
  state.activeTimeField = field;
  selectRow(rowIndex, field);
  if (field === 'video_time' && state.autoPlayOnSelect) {
    startActionLoop(rowIndex);
  }
}

// Seek Video Helper
function seekVideo(sec) {
  if (sec === null || sec === undefined || isNaN(sec)) return;
  const dur = el.mainVideo.duration;
  const maxDur = (dur && !isNaN(dur) && dur > 0) ? dur : 86400;
  const clamped = Math.max(0, Math.min(maxDur, sec));

  function applySeek() {
    try {
      el.mainVideo.currentTime = clamped;
    } catch (e) {
      console.warn('currentTime seek error:', e);
    }
    updatePlayheadPosition(clamped);
    if (el.videoCurrentTime) {
      el.videoCurrentTime.textContent = formatTimeFraction(clamped);
    }
  }

  if (el.mainVideo.readyState >= 1) {
    applySeek();
  } else {
    // If readyState is 0 (video loading metadata), seek once metadata or canplay fires
    const onReady = () => {
      applySeek();
      el.mainVideo.removeEventListener('loadedmetadata', onReady);
      el.mainVideo.removeEventListener('canplay', onReady);
    };
    el.mainVideo.addEventListener('loadedmetadata', onReady, { once: true });
    el.mainVideo.addEventListener('canplay', onReady, { once: true });
  }
}

// Load Video Segment File
function loadVideoSegment(filename) {
  const vInfo = state.videos[filename];
  if (!vInfo || !vInfo.url) {
    el.currentVideoFile.textContent = filename + ' (Video not found on disk)';
    el.videoOverlayMsg.style.display = 'block';
    el.videoOverlayMsg.textContent = `File ${filename} not found in dump folder`;
    return;
  }

  el.videoOverlayMsg.style.display = 'none';
  el.currentVideoFile.textContent = filename;

  const currentSrc = el.mainVideo.getAttribute('src');
  if (currentSrc !== vInfo.url) {
    resetVideoZoom();
    el.mainVideo.src = vInfo.url;
    el.mainVideo.load();
  }
}

// Tab / Shift+Tab inside a time editor: commit, then edit the next / previous time of the same row
// (never let focus drop to the page, where typed digits would fire the 1/2/3/Z/X hotkeys).
const TIME_EDIT_ORDER = ['action_start', 'event', 'action_end'];
const TIME_EDIT_ORDER_MANUAL = ['video_time', 'action_start', 'event', 'action_end'];
function nextTimeField(field, back, isManual = false) {
  const order = isManual ? TIME_EDIT_ORDER_MANUAL : TIME_EDIT_ORDER;
  const i = order.indexOf(field);
  if (i < 0) return null;
  return order[i + (back ? -1 : 1)] || null;
}

// Inline editing of time or player cells
function startInlineEdit(btn, rowIndex, field) {
  if (field === 'video_time') return; // Mark is match reference, non-editable
  const currentVal = state.rows[rowIndex][field] || '';
  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentVal;
  input.className = 'input-text-sm';
  input.style.width = field === 'player' ? '70px' : '54px';
  input.style.textAlign = 'center';
  input.style.fontFamily = 'var(--font-mono)';

  btn.replaceWith(input);
  input.focus();
  input.select();

  let cancelled = false;

  function commit() {
    if (cancelled) return;
    const wasLooping = Boolean(state.loopingAction);
    const newVal = input.value.trim();
    if (newVal !== currentVal) {
      if (field === 'player') {
        recordHistory();
        state.rows[rowIndex].player = newVal;
        setDirty(true);
        updateInspector();
      } else {
        const parsed = parseTime(newVal);
        if (parsed !== null) {
          recordHistory();
          state.rows[rowIndex][field] = formatTime(parsed);
          setDirty(true);
        }
      }
    }
    renderTable();
    selectRow(rowIndex);
    if (wasLooping) {
      startActionLoop(rowIndex);
    }
  }

  function cancel() {
    cancelled = true;
    const wasLooping = Boolean(state.loopingAction);
    renderTable();
    selectRow(rowIndex);
    if (wasLooping) {
      startActionLoop(rowIndex);
    }
  }

  input.addEventListener('blur', commit);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      e.stopPropagation();
      commit();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      e.stopPropagation();
      if (field === 'player') {
        commit();
      } else {
        const nxt = nextTimeField(field, e.shiftKey);
        commit();
        if (nxt) startInspectorTimeEdit(nxt);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      cancel();
    }
  });
}

// Update Inspector Card
function updateInspector() {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;

  const isManual = isManualRow(row);

  el.inspectorClipLabel.textContent = row.clip ? `Clip #${row.clip} (Row ${state.selectedRowIndex + 1})` : `Row ${state.selectedRowIndex + 1} (Skipped)`;
  el.inspectorTypeBadge.textContent = (row.type || 'MARK').toUpperCase();
  el.inspectorTypeBadge.className = 'type-badge ' + (row.type === 'goal' ? 'badge-goal' : 'badge-mark');
  el.inspectorRowLabel.textContent = row.notes || row.label || '';

  if (el.inspValMark) el.inspValMark.textContent = row.video_time || '--:--';
  if (el.inspValStart) el.inspValStart.textContent = row.action_start || '--:--';
  if (el.inspValEvent) el.inspValEvent.textContent = row.event || '--:--';
  if (el.inspValEnd) el.inspValEnd.textContent = row.action_end || '--:--';

  // Toggle Mark editability and controls based on whether this row is manual
  const wrapMark = el.inspWrapMark || document.getElementById('inspWrapMark');
  const btnRowMark = el.markTimeBtnRow || document.getElementById('markTimeBtnRow');
  const hintMark = el.inspMarkEditHint || document.getElementById('inspMarkEditHint');

  if (wrapMark) {
    if (isManual) {
      wrapMark.classList.remove('val-readonly');
      wrapMark.setAttribute('title', 'Click to edit');
    } else {
      wrapMark.classList.add('val-readonly');
      wrapMark.setAttribute('title', 'Mark is reference only (what happened during game)');
    }
  }
  if (hintMark) {
    hintMark.style.display = isManual ? 'inline' : 'none';
  }
  if (btnRowMark) {
    btnRowMark.style.display = isManual ? 'inline-flex' : 'none';
  }

  el.inspPlayer.value = row.player || '';
  el.inspNotes.value = row.notes || '';

  const isSkipped = isRowSkipped(row);
  const isZoom = (row.instructions || '').toLowerCase().includes('zoom');

  if (isSkipped) el.inspToggleSkip.classList.add('active');
  else el.inspToggleSkip.classList.remove('active');

  if (isZoom) el.inspToggleZoom.classList.add('active');
  else el.inspToggleZoom.classList.remove('active');

  // Update per-clip undo button state
  if (el.undoClipBtn) {
    const history = state.clipUndoHistory[state.selectedRowIndex];
    el.undoClipBtn.disabled = !(history && history.length > 0);
  }

  // Update loop button state to be strictly reflective of active loop mode
  updateLoopButtonState(Boolean(state.loopingAction));

  // Validate timing order
  validateTimingDisplay(row);
  renderQuickPlayerChips();
}

// Fetch and cache team roster data
async function loadRosterData() {
  if (state.roster && state.roster.length > 0) return state.roster;
  try {
    const res = await fetch('/api/roster');
    if (res.ok) {
      const data = await res.json();
      state.roster = data.roster || [];
      renderQuickPlayerChips();
    }
  } catch (err) {
    console.warn('Failed to fetch roster:', err);
  }
  return state.roster || [];
}
window.loadRosterData = loadRosterData;

// Render quick player tagging chips under the Player field in the inspector
function renderQuickPlayerChips() {
  const container = document.getElementById('quickPlayerChips');
  if (!container) return;
  const row = state.rows[state.selectedRowIndex];
  if (!row) {
    container.innerHTML = '';
    return;
  }

  const currPlayers = (row.player || '')
    .split(/[,;\s]+/)
    .map((s) => s.trim().replace(/^#/, ''))
    .filter(Boolean);

  // 1. Gather player options: from state.roster first
  let playerOptions = [];
  if (state.roster && Array.isArray(state.roster)) {
    playerOptions = state.roster
      .filter((p) => p && ((p.no !== undefined && p.no !== null && String(p.no).trim()) || (p.number !== undefined && p.number !== null && String(p.number).trim())))
      .map((p) => ({
        num: String(p.no !== undefined && p.no !== null ? p.no : p.number).trim(),
        name: p.short_name || p.name || '',
      }));
  }

  // 2. If roster has fewer than 8 players, supplement with numbers already tagged across current match rows
  if (playerOptions.length < 8 && Array.isArray(state.rows)) {
    const existingNums = new Set(playerOptions.map((p) => p.num));
    state.rows.forEach((r) => {
      if (!r || !r.player) return;
      const nums = r.player.split(/[,;\s]+/).map((s) => s.trim().replace(/^#/, '')).filter(Boolean);
      nums.forEach((n) => {
        if (!existingNums.has(n)) {
          existingNums.add(n);
          playerOptions.push({ num: n, name: '' });
        }
      });
    });
  }

  // Sort by integer jersey number
  playerOptions.sort((a, b) => (parseInt(a.num, 10) || 0) - (parseInt(b.num, 10) || 0));

  // Take top 8 chips
  const displayChips = playerOptions.slice(0, 8);

  if (displayChips.length === 0) {
    container.innerHTML = `<button type="button" class="quick-player-chip" onclick="openRosterModal()" title="Add players to team roster" style="font-style: italic; opacity: 0.85;">+ Roster</button>`;
    return;
  }

  let html = '';
  displayChips.forEach((p) => {
    const isActive = currPlayers.includes(p.num);
    const label = p.name ? `#${p.num} ${p.name}` : `#${p.num}`;
    html += `<button type="button" class="quick-player-chip ${isActive ? 'active' : ''}" onclick="toggleQuickPlayer('${escapeSafe(p.num)}')" title="${isActive ? 'Remove' : 'Tag'} player #${escapeSafe(p.num)}${p.name ? ' (' + escapeSafe(p.name) + ')' : ''}">${escapeSafe(label)}</button>`;
  });

  container.innerHTML = html;
}
window.renderQuickPlayerChips = renderQuickPlayerChips;

// Toggle a player number on the currently selected row
function toggleQuickPlayer(jerseyNum) {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;

  recordHistory(state.selectedRowIndex);
  let curr = (row.player || '')
    .split(/[,;\s]+/)
    .map((s) => s.trim().replace(/^#/, ''))
    .filter(Boolean);

  const idx = curr.indexOf(String(jerseyNum));
  if (idx >= 0) {
    curr.splice(idx, 1);
  } else {
    curr.push(String(jerseyNum));
  }

  row.player = curr.join(', ');
  setDirty(true);
  const inp = document.getElementById('inspPlayer');
  if (inp) inp.value = row.player;
  renderQuickPlayerChips();
  renderTable();
}
window.toggleQuickPlayer = toggleQuickPlayer;

// Handler when clicking the Mark value wrap in the inspector
function onInspectorMarkValClick() {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;
  if (isManualRow(row)) {
    startInspectorTimeEdit('video_time');
  } else {
    onInspectorLabelClick('video_time');
  }
}
window.onInspectorMarkValClick = onInspectorMarkValClick;

// Start inline editing of a time value in the inspector on click
function startInspectorTimeEdit(field) {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;
  if (field === 'video_time' && !isManualRow(row)) return; // Only manual marks are editable

  const fieldElementMap = {
    'video_time': document.getElementById('inspValMark'),
    'action_start': document.getElementById('inspValStart'),
    'event': document.getElementById('inspValEvent'),
    'action_end': document.getElementById('inspValEnd'),
  };

  const spanEl = fieldElementMap[field];
  if (!spanEl) return;
  const wrap = spanEl.parentElement;
  if (!wrap || wrap.querySelector('input')) return; // already editing

  const currentVal = row[field] || '';
  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentVal;
  input.className = 'time-block-input';
  input.placeholder = 'mm:ss';

  wrap.innerHTML = '';
  wrap.appendChild(input);
  input.focus();
  input.select();

  let committed = false;
  function commit() {
    if (committed) return;
    committed = true;
    const newVal = input.value.trim();
    if (newVal && newVal !== currentVal) {
      const parsed = parseTime(newVal);
      if (parsed !== null) {
        recordHistory(state.selectedRowIndex);
        row[field] = formatTime(parsed);
        if (field === 'video_time') {
          row['video_sec'] = parsed;
        }
        setDirty(true);
        seekVideo(parsed);
      }
    }
    restoreWrap();
  }

  function restoreWrap() {
    const isManual = isManualRow(row);
    const showEditIcon = field !== 'video_time' || isManual;
    wrap.innerHTML = `
      <span class="time-block-val" id="${spanEl.id}">${row[field] || '--:--'}</span>
      ${showEditIcon ? '<span class="edit-hint-icon">✎</span>' : ''}
    `;
    // Rebind cached references
    if (field === 'video_time') el.inspValMark = document.getElementById('inspValMark');
    if (field === 'action_start') el.inspValStart = document.getElementById('inspValStart');
    if (field === 'event') el.inspValEvent = document.getElementById('inspValEvent');
    if (field === 'action_end') el.inspValEnd = document.getElementById('inspValEnd');

    renderTable();
    updateInspector();
    updateTimelineActionWindow(true);
  }

  input.addEventListener('blur', commit);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      e.stopPropagation();
      commit();
    } else if (e.key === 'Tab') {
      e.preventDefault();
      e.stopPropagation();
      const nxt = nextTimeField(field, e.shiftKey, isManualRow(row));
      commit();
      if (nxt) startInspectorTimeEdit(nxt);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      committed = true;
      restoreWrap();
    }
  });
}

function validateTimingDisplay(row) {
  const s = parseTime(row.action_start);
  const e = parseTime(row.event);
  const end = parseTime(row.action_end);
  const m = parseTime(row.video_time);

  let invalid = false;
  let warnMsg = '';
  if (s !== null && e !== null && s > e) {
    invalid = true;
    warnMsg = `⚠️ Start (${row.action_start}) > Event (${row.event})`;
  } else if (e !== null && end !== null && e > end) {
    invalid = true;
    warnMsg = `⚠️ Event (${row.event}) > End (${row.action_end})`;
  } else if (s !== null && end !== null && s > end) {
    invalid = true;
    warnMsg = `⚠️ Start (${row.action_start}) > End (${row.action_end})`;
  }

  if (invalid) {
    el.inspectorWarning.style.display = 'block';
    el.inspectorWarning.className = 'inspector-warning';
    el.inspectorWarning.textContent = warnMsg;
  } else {
    // Plausibility checks (action > 30s or start/end > 20s from mark)
    let softWarn = '';
    if (s !== null && end !== null && (end - s) > 30) {
      softWarn = `⚠️ Long clip: ${end - s}s duration (>30s)`;
    } else if (m !== null && s !== null && Math.abs(m - s) > 20) {
      softWarn = `⚠️ Start (${row.action_start}) is ${Math.abs(m - s)}s from mark (${row.video_time})`;
    } else if (m !== null && end !== null && Math.abs(end - m) > 25) {
      softWarn = `⚠️ End (${row.action_end}) is ${Math.abs(end - m)}s from mark (${row.video_time})`;
    }

    if (softWarn) {
      el.inspectorWarning.style.display = 'block';
      el.inspectorWarning.className = 'inspector-warning warning-soft';
      el.inspectorWarning.textContent = softWarn;
    } else {
      el.inspectorWarning.style.display = 'none';
    }
  }
}

// --- Timeline Zoom, Visible Ruler & Draggable Handles ---

function secToTimelinePct(sec) {
  const { startSec, endSec } = state.timelineZoom;
  if (endSec <= startSec) return 0;
  return ((sec - startSec) / (endSec - startSec)) * 100;
}

function timelinePctToSec(pct) {
  const { startSec, endSec } = state.timelineZoom;
  return startSec + (pct / 100) * (endSec - startSec);
}

function updateTimelineZoomWindow() {
  const row = state.rows[state.selectedRowIndex];
  const dur = (el.mainVideo && el.mainVideo.duration && !isNaN(el.mainVideo.duration) && el.mainVideo.duration > 0)
    ? el.mainVideo.duration
    : 3600;

  if (state.timelineZoom.isZoomed) {
    // Zoom window: ensure all valid row times (mark, start, event, end) are comfortably visible.
    // Base window is 30s centered around mark/event/start, but expands or shifts if start or end exceed the bounds.
    const markSec = row ? parseTime(row.video_time) : null;
    const startSec = row ? parseTime(row.action_start) : null;
    const evSec = row ? parseTime(row.event) : null;
    const endSec = row ? parseTime(row.action_end) : null;

    const anchor = (markSec ?? evSec ?? startSec ?? Math.round(el.mainVideo.currentTime || 0));

    let windowMin = Math.max(0, anchor - 15);
    let windowMax = Math.min(dur, windowMin + 30);
    if (windowMax - windowMin < 30) {
      windowMin = Math.max(0, windowMax - 30);
    }

    // Include all active times for the selected row with a 2-second safety margin
    const validTimes = [markSec, startSec, evSec, endSec].filter((t) => t !== null && !isNaN(t));
    if (validTimes.length > 0) {
      const minRequired = Math.max(0, Math.min(...validTimes) - 2);
      const maxRequired = Math.min(dur, Math.max(...validTimes) + 2);
      const spanRequired = maxRequired - minRequired;

      if (spanRequired <= 30) {
        // Fits within 30s: shift the 30s window so all points are fully inside
        if (minRequired < windowMin) {
          windowMin = minRequired;
          windowMax = Math.min(dur, windowMin + 30);
        } else if (maxRequired > windowMax) {
          windowMax = maxRequired;
          windowMin = Math.max(0, windowMax - 30);
        }
      } else {
        // Wider than 30s: expand window to encompass all points with margins
        windowMin = minRequired;
        windowMax = maxRequired;
      }
    }

    state.timelineZoom.startSec = windowMin;
    state.timelineZoom.endSec = windowMax;
    const span = Math.round(windowMax - windowMin);

    if (el.timelineWindowLabel) {
      el.timelineWindowLabel.textContent = `Zoom: ${formatTime(windowMin)} – ${formatTime(windowMax)} (${span}s)`;
    }
    el.btnModeZoom?.classList.add('active');
    el.btnModeFull?.classList.remove('active');
  } else {
    // Full match video view
    state.timelineZoom.startSec = 0;
    state.timelineZoom.endSec = dur;

    if (el.timelineWindowLabel) {
      el.timelineWindowLabel.textContent = `Full Match (${formatTime(dur)})`;
    }
    el.btnModeFull?.classList.add('active');
    el.btnModeZoom?.classList.remove('active');
  }

  renderTimelineRuler();
  updateTimelineActionWindow();
}

function setTimelineZoomMode(zoomed) {
  state.timelineZoom.isZoomed = zoomed;
  updateTimelineZoomWindow();
}

function toggleTimelineZoom() {
  setTimelineZoomMode(!state.timelineZoom.isZoomed);
}

function renderTimelineRuler() {
  if (!el.timelineRuler) return;
  el.timelineRuler.innerHTML = '';
  const { startSec, endSec, isZoomed } = state.timelineZoom;
  const span = endSec - startSec;
  if (span <= 0) return;

  if (isZoomed) {
    // 30s Zoom: Major tick every 5s, minor tick every 1s, sub-tick every 0.5s
    const firstSub = Math.ceil(startSec / 0.5) * 0.5;
    for (let t = firstSub; t <= endSec + 0.001; t += 0.5) {
      const roundedT = Math.round(t * 10) / 10;
      const pct = secToTimelinePct(roundedT);
      if (pct < 0 || pct > 100) continue;
      const isMajor = Math.abs(roundedT % 5) < 0.001 || Math.abs((roundedT % 5) - 5) < 0.001;
      const isMinor = !isMajor && (Math.abs(roundedT % 1) < 0.001 || Math.abs((roundedT % 1) - 1) < 0.001);
      const tick = document.createElement('div');
      tick.className = isMajor ? 'ruler-tick ruler-tick-major' : (isMinor ? 'ruler-tick' : 'ruler-tick ruler-tick-sub');
      tick.style.left = `${pct}%`;
      el.timelineRuler.appendChild(tick);

      if (isMajor) {
        const lbl = document.createElement('div');
        lbl.className = 'ruler-tick-label';
        lbl.textContent = formatTime(roundedT);
        lbl.style.left = `${pct}%`;
        el.timelineRuler.appendChild(lbl);
      }
    }
  } else {
    // Full Match: Clean 5m (300s) intervals as requested, 1m (60s) minor ticks
    let stepMajor, stepMinor;
    if (span > 900) { // match half > 15 mins
      stepMajor = 300; // 5 minutes!
      stepMinor = 60;  // 1 minute
    } else if (span > 300) { // 5-15 mins
      stepMajor = 120; // 2 minutes
      stepMinor = 30;  // 30s
    } else { // <= 5 mins
      stepMajor = 60;  // 1 minute
      stepMinor = 10;  // 10s
    }

    const firstMinor = Math.ceil(startSec / stepMinor) * stepMinor;
    for (let t = firstMinor; t <= endSec; t += stepMinor) {
      const pct = secToTimelinePct(t);
      if (pct < 0 || pct > 100) continue;
      const isMajor = (t % stepMajor === 0);
      const tick = document.createElement('div');
      tick.className = isMajor ? 'ruler-tick ruler-tick-major' : 'ruler-tick';
      tick.style.left = `${pct}%`;
      el.timelineRuler.appendChild(tick);

      if (isMajor) {
        const lbl = document.createElement('div');
        lbl.className = 'ruler-tick-label';
        lbl.textContent = formatTime(t);
        lbl.style.left = `${pct}%`;
        el.timelineRuler.appendChild(lbl);
      }
    }
  }
}

// Playhead position and 60fps smooth RAF updater
let playheadRafId = null;

function updatePlayheadPosition(explicitSec) {
  if (!el.timelinePlayhead) return;
  const curr = (explicitSec !== undefined && explicitSec !== null)
    ? explicitSec
    : (el.mainVideo ? (el.mainVideo.currentTime || 0) : 0);
  const playPct = secToTimelinePct(curr);
  el.timelinePlayhead.style.left = `${playPct}%`;
  el.timelinePlayhead.style.display = (playPct >= -3 && playPct <= 103) ? 'block' : 'none';
}

function startPlayheadRaf() {
  if (playheadRafId) cancelAnimationFrame(playheadRafId);
  function rafStep() {
    if (el.mainVideo && !el.mainVideo.paused) {
      updatePlayheadPosition();
      if (el.videoCurrentTime) {
        el.videoCurrentTime.textContent = formatTimeFraction(el.mainVideo.currentTime);
      }
      playheadRafId = requestAnimationFrame(rafStep);
    } else {
      playheadRafId = null;
    }
  }
  playheadRafId = requestAnimationFrame(rafStep);
}

function stopPlayheadRaf() {
  if (playheadRafId) {
    cancelAnimationFrame(playheadRafId);
    playheadRafId = null;
  }
  updatePlayheadPosition();
  if (el.videoCurrentTime && el.mainVideo) {
    el.videoCurrentTime.textContent = formatTimeFraction(el.mainVideo.currentTime);
  }
}

// Timeline strip update
function updateTimelineActionWindow(recomputeZoomWindow = false) {
  if (recomputeZoomWindow && state.timelineZoom.isZoomed) {
    updateTimelineZoomWindow();
    return;
  }

  const row = state.rows[state.selectedRowIndex];
  if (!row) {
    if (el.timelineActionWindow) el.timelineActionWindow.style.display = 'none';
    return;
  }

  const s = parseTime(row.action_start);
  const ev = parseTime(row.event);
  const end = parseTime(row.action_end);
  const mark = parseTime(row.video_time);

  // Shaded action window
  if (s !== null && end !== null && end > s) {
    const leftPct = Math.max(-5, Math.min(105, secToTimelinePct(s)));
    const rightPct = Math.max(-5, Math.min(105, secToTimelinePct(end)));
    const widthPct = Math.max(0, rightPct - leftPct);
    el.timelineActionWindow.style.left = `${leftPct}%`;
    el.timelineActionWindow.style.width = `${widthPct}%`;
    el.timelineActionWindow.style.display = 'block';
  } else {
    el.timelineActionWindow.style.display = 'none';
  }

  // Helper to place lines
  function placeLine(lineEl, secVal) {
    if (!lineEl) return;
    if (secVal !== null && secVal !== undefined) {
      const pct = secToTimelinePct(secVal);
      lineEl.style.left = `${pct}%`;
      lineEl.style.display = (pct >= -2 && pct <= 102) ? 'block' : 'none';
    } else {
      lineEl.style.display = 'none';
    }
  }

  placeLine(el.timelineStartLine, s);
  placeLine(el.timelineEventLine, ev);
  placeLine(el.timelineEndLine, end);
  placeLine(el.timelineMarkLine, mark);

  // Playhead
  updatePlayheadPosition();
}

function onInspectorLabelClick(field) {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;
  const t = parseTime(row[field]);
  if (t !== null) {
    seekVideo(t);
  }
  setActiveTimelineLine(field);
  if (field === 'video_time' && state.autoPlayOnSelect) {
    startActionLoop(state.selectedRowIndex);
  } else if (!state.autoPlayOnSelect && el.mainVideo && !el.mainVideo.paused) {
    el.mainVideo.pause();
    if (el.playPauseBtn) el.playPauseBtn.textContent = '▶ Play';
  }
}

function setActiveTimelineLine(field) {
  state.activeTimelineLine = field;
  const lines = [el.timelineStartLine, el.timelineEventLine, el.timelineEndLine, el.timelineMarkLine];
  lines.forEach((l) => l?.classList.remove('active-line'));

  const labels = [
    document.getElementById('lblMark'),
    document.getElementById('lblStart'),
    document.getElementById('lblEvent'),
    document.getElementById('lblEnd')
  ];
  labels.forEach((lbl) => lbl?.classList.remove('active-label'));

  if (field === 'action_start') {
    el.timelineStartLine?.classList.add('active-line');
    document.getElementById('lblStart')?.classList.add('active-label');
  } else if (field === 'event') {
    el.timelineEventLine?.classList.add('active-line');
    document.getElementById('lblEvent')?.classList.add('active-label');
  } else if (field === 'action_end') {
    el.timelineEndLine?.classList.add('active-line');
    document.getElementById('lblEnd')?.classList.add('active-label');
  } else if (field === 'video_time') {
    el.timelineMarkLine?.classList.add('active-line');
    document.getElementById('lblMark')?.classList.add('active-label');
  }
}

function setupDraggableTimeline() {
  let activeDrag = null;
  let hasDragged = false;

  function getSecFromEvent(e, snapHalf = true) {
    const rect = el.timelineContainer.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
    const rawSec = timelinePctToSec(pct);
    const sec = snapHalf ? (Math.round(rawSec * 2) / 2) : Math.round(rawSec);
    const maxDur = el.mainVideo.duration || 3600;
    return Math.max(0, Math.min(maxDur, sec));
  }

  function onPointerDown(lineType, e) {
    e.preventDefault();
    e.stopPropagation();
    activeDrag = lineType;
    hasDragged = false;
    setActiveTimelineLine(lineType);

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  }

  function onPointerMove(e) {
    if (!activeDrag) return;
    const isHandle = activeDrag !== 'playhead';
    const sec = getSecFromEvent(e, isHandle);
    const row = state.rows[state.selectedRowIndex];
    if (!row) return;
    // Undo snapshot must be taken BEFORE the first change of a drag (it used to be taken at pointer-up, after the
    // change, so Undo / Undo Clip restored the already-edited state and appeared to do nothing)
    if (!hasDragged && activeDrag !== 'playhead') recordHistory(state.selectedRowIndex);
    hasDragged = true;

    if (activeDrag === 'playhead') {
      el.mainVideo.currentTime = sec;
    } else if (activeDrag === 'video_time') {
      row.video_time = formatTime(sec);
      row.video_sec = sec;
      seekVideo(sec);
    } else if (activeDrag === 'action_start') {
      row.action_start = formatTime(sec);
      seekVideo(sec);
    } else if (activeDrag === 'event') {
      row.event = formatTime(sec);
      seekVideo(sec);
    } else if (activeDrag === 'action_end') {
      row.action_end = formatTime(sec);
      seekVideo(sec);
    }

    updateInspector();
    updateTimelineActionWindow(true);
  }

  function onPointerUp() {
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);

    if (activeDrag && hasDragged && activeDrag !== 'playhead') {
      setDirty(true);
      renderTable();
      updateInspector();
      updateTimelineActionWindow(true);
    }
    activeDrag = null;
  }

  el.timelineStartLine?.addEventListener('pointerdown', (e) => onPointerDown('action_start', e));
  el.timelineEventLine?.addEventListener('pointerdown', (e) => onPointerDown('event', e));
  el.timelineEndLine?.addEventListener('pointerdown', (e) => onPointerDown('action_end', e));
  // Mark line: draggable if manual row; clicking jumps playhead to mark and loops action
  el.timelineMarkLine?.addEventListener('pointerdown', (e) => {
    const row = state.rows[state.selectedRowIndex];
    if (isManualRow(row)) {
      onPointerDown('video_time', e);
    }
  });
  el.timelineMarkLine?.addEventListener('click', (e) => {
    if (hasDragged) return;
    e.stopPropagation();
    const row = state.rows[state.selectedRowIndex];
    if (row && row.video_time) {
      const sec = parseTime(row.video_time);
      if (sec !== null) seekVideo(sec);
    }
    setActiveTimelineLine('video_time');
    startActionLoop(state.selectedRowIndex);
  });
  el.timelinePlayhead?.addEventListener('pointerdown', (e) => onPointerDown('playhead', e));

  // Clicking on background track directly seeks and drags playhead
  el.timelineContainer?.addEventListener('pointerdown', (e) => {
    if (e.target.closest('.timeline-line') || e.target.closest('.timeline-playhead')) return;
    const sec = getSecFromEvent(e, true);
    seekVideo(sec);
    onPointerDown('playhead', e);
  });
}

// Set time from video playhead (Keys 1, 2, 3)
function setTimeFromPlayhead(field) {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;
  if (field === 'video_time' && !isManualRow(row)) return;

  const currentSec = Math.round((el.mainVideo.currentTime || 0) * 2) / 2;
  const oldVal = row[field];
  const newVal = formatTime(currentSec);
  if (oldVal === newVal) return;

  recordHistory();
  row[field] = newVal;
  if (field === 'video_time') {
    row.video_sec = currentSec;
  }
  setDirty(true);

  renderTable();
  updateInspector();
  updateTimelineActionWindow(true);

  const labelMap = { action_start: 'Start', event: 'Event', action_end: 'End', video_time: 'Mark' };
  showToast(`Set ${labelMap[field] || field} to ${newVal} from playhead (Row ${state.selectedRowIndex + 1})`, 'info', 2500);
}

// Nudge time (+/- 1s)
function nudgeTime(field, deltaSec) {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;
  if (field === 'video_time' && !isManualRow(row)) return;

  const curr = parseTime(row[field]);
  if (curr === null) return;

  const updated = Math.max(0, curr + deltaSec);
  recordHistory();
  row[field] = formatTime(updated);
  if (field === 'video_time') {
    row.video_sec = updated;
  }
  setDirty(true);

  renderTable();
  updateInspector();
  updateTimelineActionWindow(true);
  seekVideo(updated);
}

// Seek to active time from inspector
function seekToActiveTime(field) {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;
  const sec = parseTime(row[field]);
  if (sec !== null) seekVideo(sec);
}

// Playhead step time
function stepTime(seconds) {
  if (isNaN(el.mainVideo.duration)) return;
  el.mainVideo.currentTime = Math.max(0, Math.min(el.mainVideo.duration, el.mainVideo.currentTime + seconds));
}

// Step frame (1/30 second)
function stepFrame(delta) {
  stepTime(delta * (1 / 30));
}

// Play / Pause toggle
function togglePlayPause() {
  if (el.mainVideo.paused) {
    el.mainVideo.play();
    el.playPauseBtn.textContent = '❚❚ Pause';
  } else {
    el.mainVideo.pause();
    el.playPauseBtn.textContent = '▶ Play';
    if (state.loopingAction) {
      stopActionLoop();
    }
  }
}

// Playback speed
function setPlaybackSpeed(speed) {
  el.mainVideo.playbackRate = speed;
  const speedBtns = document.querySelectorAll('.speed-btn');
  speedBtns.forEach((b) => b.classList.remove('active'));
  event.target.classList.add('active');
}

// Update Loop Button State (changes icon between Play and Pause)
function updateLoopButtonState(isLooping) {
  const loopBtn = document.getElementById('loopActionBtn');
  if (!loopBtn) return;
  if (isLooping) {
    loopBtn.textContent = '❚❚ Pause Loop';
    loopBtn.title = 'Pause action loop (Ctrl+Enter)';
    loopBtn.classList.add('btn-danger', 'active');
  } else {
    loopBtn.textContent = '▶ Loop Action';
    loopBtn.title = 'Play action loop (Ctrl+Enter)';
    loopBtn.classList.remove('btn-danger', 'active');
  }
}

// Stop Action Loop
function stopActionLoop() {
  state.loopingAction = false;
  if (state.loopTimer) {
    clearInterval(state.loopTimer);
    state.loopTimer = null;
  }
  updateLoopButtonState(false);
  if (state._pendingLoopPlay && el.mainVideo) {
    el.mainVideo.removeEventListener('loadedmetadata', state._pendingLoopPlay);
    el.mainVideo.removeEventListener('canplay', state._pendingLoopPlay);
    state._pendingLoopPlay = null;
  }
}

// Toggle Auto-play on select setting
function toggleAutoPlayOnSelect(evt) {
  if (evt && evt.stopPropagation) evt.stopPropagation();
  const chk = document.getElementById('chkAutoPlayOnSelect');
  state.autoPlayOnSelect = chk ? Boolean(chk.checked) : true;
  try {
    localStorage.setItem('review_editor_autoplay_on_select', String(state.autoPlayOnSelect));
  } catch (e) {}
  if (!state.autoPlayOnSelect) {
    stopActionLoop();
    if (el.mainVideo && !el.mainVideo.paused) {
      el.mainVideo.pause();
      if (el.playPauseBtn) el.playPauseBtn.textContent = '▶ Play';
    }
  }
}
window.toggleAutoPlayOnSelect = toggleAutoPlayOnSelect;

// Start Action Loop on a target row
function startActionLoop(targetRowIndex, force = false) {
  if (targetRowIndex !== undefined && targetRowIndex !== null && targetRowIndex !== state.selectedRowIndex) {
    selectRow(targetRowIndex);
  }
  const loopRowIndex = state.selectedRowIndex;
  const row = state.rows[loopRowIndex];
  if (!row) return;

  if (!force && state.autoPlayOnSelect === false) {
    stopActionLoop();
    if (el.mainVideo && !el.mainVideo.paused) {
      el.mainVideo.pause();
      if (el.playPauseBtn) el.playPauseBtn.textContent = '▶ Play';
    }
    updateLoopButtonState(false);
    return;
  }

  let s = parseTime(row.action_start);
  let end = parseTime(row.action_end);
  if (s === null || end === null || end <= s) {
    const markSec = parseTime(row.video_time) ?? 0;
    const dur = (el.mainVideo && el.mainVideo.duration && !isNaN(el.mainVideo.duration))
      ? el.mainVideo.duration
      : 86400;
    s = Math.max(0, markSec - 12);
    end = Math.min(dur, markSec + 4);
    if (end <= s) end = s + 16;
  }

  state.loopingAction = true;
  updateLoopButtonState(true);

  const loopStartedAt = Date.now();
  const playSegment = () => {
    state._pendingLoopPlay = null;
    if (!state.loopingAction) return;
    try {
      el.mainVideo.currentTime = s;
    } catch (e) {}
    el.mainVideo.play().catch((e) => console.warn('Video play error on loop start:', e));
    if (el.playPauseBtn) el.playPauseBtn.textContent = '❚❚ Pause';
  };

  if (state._pendingLoopPlay && el.mainVideo) {
    el.mainVideo.removeEventListener('loadedmetadata', state._pendingLoopPlay);
    el.mainVideo.removeEventListener('canplay', state._pendingLoopPlay);
  }
  state._pendingLoopPlay = playSegment;

  if (el.mainVideo.readyState >= 1) {
    playSegment();
  } else {
    el.mainVideo.addEventListener('loadedmetadata', playSegment, { once: true });
    el.mainVideo.addEventListener('canplay', playSegment, { once: true });
  }

  if (state.loopTimer) clearInterval(state.loopTimer);
  state.loopTimer = setInterval(() => {
    if (!state.loopingAction) {
      stopActionLoop();
      return;
    }
    if (el.mainVideo.paused && !el.mainVideo.seeking && Date.now() - loopStartedAt > 500) {
      stopActionLoop();
      return;
    }
    // Re-read the boundaries every tick so moving START/END while looping takes effect at once
    const lr = state.rows[loopRowIndex];
    let ls = lr ? parseTime(lr.action_start) : null;
    let le = lr ? parseTime(lr.action_end) : null;
    if (ls === null || le === null || le <= ls) {
      ls = s;
      le = end;
    }
    const t = el.mainVideo.currentTime;
    if (t >= le || t < ls - 0.25) {
      el.mainVideo.currentTime = ls;
    }
  }, 80);
}

// Toggle Play Action Window and Loop (Play <-> Stop)
function toggleActionLoop() {
  if (state.loopingAction) {
    stopActionLoop();
    el.mainVideo.pause();
    if (el.playPauseBtn) el.playPauseBtn.textContent = '▶ Play';
    return;
  }
  startActionLoop(state.selectedRowIndex, true);
}

// Backward compatibility alias
function playActionLoop() {
  toggleActionLoop();
}

// Toggles: Zoom and Skip
function toggleRowZoom(idx) {
  const row = state.rows[idx];
  if (!row) return;

  recordHistory();
  let inst = (row.instructions || '').trim();
  if (inst.toLowerCase().includes('zoom')) {
    inst = inst.replace(/\bzoom\b/gi, '').replace(/\s+/g, ' ').trim();
  } else {
    inst = inst ? `${inst} zoom` : 'zoom';
  }
  row.instructions = inst;
  setDirty(true);

  renderTable();
  if (state.selectedRowIndex === idx) updateInspector();
}
window.toggleRowZoom = toggleRowZoom;

function toggleRowSkip(idx) {
  const row = state.rows[idx];
  if (!row) return;

  recordHistory();
  let inst = (row.instructions || '').trim();
  if (isRowSkipped(row)) {
    inst = inst.replace(/\bskip\b/gi, '').replace(/\s+/g, ' ').trim();
    row.skip = '';
  } else {
    inst = inst ? `${inst} skip` : 'skip';
  }
  row.instructions = inst;

  recomputeClips();
  setDirty(true);

  renderTable();
  if (state.selectedRowIndex === idx) updateInspector();
}
window.toggleRowSkip = toggleRowSkip;

function toggleZoomCurrentRow() {
  if (state.selectedRowIndex >= 0) toggleRowZoom(state.selectedRowIndex);
}

function toggleSkipCurrentRow() {
  if (state.selectedRowIndex >= 0) toggleRowSkip(state.selectedRowIndex);
}

// Flags Dropdown Menu (Skip / Zoom)
function toggleFlagsDropdown(event, rowIndex) {
  if (event.target.closest('a.chip-zoom')) {
    // Let zoom link click open Zoom Editor tab
    return;
  }
  event.stopPropagation();
  const wrapper = event.currentTarget;
  const menu = document.getElementById('flagsDropdownMenu');
  if (menu && menu.style.display !== 'none' && state.activeFlagsDropdownRow === rowIndex) {
    closeFlagsDropdown();
  } else {
    openFlagsDropdown(rowIndex, wrapper);
  }
}
window.toggleFlagsDropdown = toggleFlagsDropdown;

function openFlagsDropdown(rowIndex, anchorEl) {
  state.activeFlagsDropdownRow = rowIndex;
  let menu = document.getElementById('flagsDropdownMenu');
  if (!menu) {
    menu = document.createElement('div');
    menu.id = 'flagsDropdownMenu';
    menu.className = 'flags-dropdown-menu';
    document.body.appendChild(menu);
  }

  function renderMenuContent() {
    const row = state.rows[rowIndex];
    if (!row) return;
    const isSkip = isRowSkipped(row);
    const isZoom = (row.instructions || '').toLowerCase().includes('zoom');

    menu.innerHTML = `
      <div class="flags-menu-item ${isSkip ? 'is-active' : ''}" data-flag="skip">
        <span class="flags-menu-check">${isSkip ? '✓' : ''}</span>
        <span class="flags-menu-label">Skip</span>
      </div>
      <div class="flags-menu-item ${isZoom ? 'is-active' : ''}" data-flag="zoom">
        <span class="flags-menu-check">${isZoom ? '✓' : ''}</span>
        <span class="flags-menu-label">Zoom</span>
      </div>
    `;

    menu.querySelectorAll('.flags-menu-item').forEach((item) => {
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        const flag = item.dataset.flag;
        if (flag === 'skip') {
          toggleRowSkip(rowIndex);
        } else if (flag === 'zoom') {
          toggleRowZoom(rowIndex);
        }
        renderMenuContent();
      });
    });
  }

  renderMenuContent();
  menu.style.display = 'block';

  const rect = anchorEl.getBoundingClientRect();
  const menuW = 120;
  let left = rect.left;
  if (left + menuW > window.innerWidth - 10) {
    left = window.innerWidth - menuW - 10;
  }
  let top = rect.bottom + 3;
  if (top + 75 > window.innerHeight) {
    top = rect.top - 75;
  }
  menu.style.left = `${Math.max(10, Math.round(left))}px`;
  menu.style.top = `${Math.max(10, Math.round(top))}px`;
}
window.openFlagsDropdown = openFlagsDropdown;

function closeFlagsDropdown() {
  const menu = document.getElementById('flagsDropdownMenu');
  if (menu && menu.style.display !== 'none') {
    menu.style.display = 'none';
    state.activeFlagsDropdownRow = null;
    return true;
  }
  return false;
}
window.closeFlagsDropdown = closeFlagsDropdown;

// Inspector Player / Notes Change
function onInspectorPlayerChange() {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;
  recordHistory();
  row.player = el.inspPlayer.value.trim();
  renderTable();
}

function onInspectorNotesChange() {
  const row = state.rows[state.selectedRowIndex];
  if (!row) return;
  recordHistory();
  row.notes = el.inspNotes.value.trim();
  renderTable();
}

// Filters
function setHalfFilter(half) {
  state.filterHalf = half;
  if (el.halfFilter && el.halfFilter.value !== half) {
    el.halfFilter.value = half;
  }
  [el.filterHalfAll, el.filterHalf1, el.filterHalf2].forEach((btn) => {
    if (btn) btn.classList.remove('active');
  });
  if (half === 'all' && el.filterHalfAll) el.filterHalfAll.classList.add('active');
  if (half === '1' && el.filterHalf1) el.filterHalf1.classList.add('active');
  if (half === '2' && el.filterHalf2) el.filterHalf2.classList.add('active');
  renderTable();
}

function onFilterChange() {
  state.filterType = el.typeFilter.value;
  renderTable();
}

function toggleShowSkipped() {
  state.showSkipped = !state.showSkipped;
  if (el.toggleSkippedBtn) {
    el.toggleSkippedBtn.classList.toggle('active', state.showSkipped);
    el.toggleSkippedBtn.innerHTML = state.showSkipped
      ? '<span id="toggleSkippedCheck" class="skipped-check">✓</span> Skipped'
      : '<span id="toggleSkippedCheck" class="skipped-check"></span> Skipped';
  }
  renderTable();
}

// Undo
function undo() {
  if (state.undoStack.length === 0) return;
  const currentSnapshot = JSON.stringify({
    rows: state.rows,
    selectedRowIndex: state.selectedRowIndex,
  });
  let lastStateStr = state.undoStack.pop();
  while (lastStateStr === currentSnapshot && state.undoStack.length > 0) {
    lastStateStr = state.undoStack.pop();
  }
  if (lastStateStr === currentSnapshot) {
    if (state.undoStack.length === 0) el.undoBtn.disabled = true;
    return;
  }
  const lastState = JSON.parse(lastStateStr);
  const wasLooping = state.loopingAction;
  state.rows = lastState.rows;
  state.selectedRowIndex = lastState.selectedRowIndex;
  renderTable();
  selectRow(state.selectedRowIndex);
  if (wasLooping) toggleActionLoop();         // selectRow() stopped the loop (button said Loop Action while video kept playing)
  if (state.undoStack.length === 0) el.undoBtn.disabled = true;
}

// Game Setup rewrites the CSV "game" column on disk: take over the new revision and name so the next Save is not seen as stale.
function applyInfoSaveResult(data) {
  if (!data) return;
  if (data.revision) state.csvRevision = data.revision;
  if (data.match_name) {
    [state.rows, state.pristineRows].forEach(list => {
      (list || []).forEach(r => { if (r && 'game' in r) r.game = data.match_name; });
    });
  }
}

// Save CSV (and optionally auto-push to Google Sheet)
async function save(force = false) {
  if (!state.currentGameId) return;

  // Validate timing order across all rows before saving
  const invalidRows = [];
  state.rows.forEach((r, idx) => {
    const sSec = parseTime(r.action_start);
    const eSec = parseTime(r.event);
    const endSec = parseTime(r.action_end);
    if ((sSec !== null && eSec !== null && sSec > eSec) ||
        (eSec !== null && endSec !== null && eSec > endSec) ||
        (sSec !== null && endSec !== null && sSec > endSec)) {
      invalidRows.push(idx + 1);
    }
  });

  if (invalidRows.length > 0) {
    const ok = await showConfirm(
      `${invalidRows.length} row(s) (Row ${invalidRows.join(', ')}) have invalid timing (e.g. End before Event or Start after End).\n\nSave locally anyway? (Auto-push to Google Sheets will be skipped for invalid rows).`,
      'Invalid Timings Warning',
      'Save Anyway',
      'btn-warning'
    );
    if (!ok) return;
  }

  let shouldAutoPush = el.autoSyncSheet ? el.autoSyncSheet.checked : false;
  if (invalidRows.length > 0) {
    shouldAutoPush = false;
  }

  el.saveBtn.disabled = true;
  el.saveStatus.className = 'status-badge status-dirty';
  el.saveStatus.textContent = shouldAutoPush ? 'Saving & Pushing...' : 'Saving...';

  try {
    const res = await fetch(`/api/game/${state.currentGameId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        headers: state.headers,
        rows: state.rows,
        auto_push: shouldAutoPush,
        base_revision: state.csvRevision || '',
        force: force,
      }),
    });

    if (res.status === 409) {
      el.saveBtn.disabled = false;
      setDirty(true);
      const overwrite = await showConfirm(
        'The reviewed file changed on disk after this page loaded it (another browser tab, the zoom editor, or a manual edit).\n\nOverwrite it with what you see here? Choose Cancel, copy anything you need, then reload the page to see the newer version.',
        'File Changed Elsewhere', 'Overwrite', 'btn-danger');
      if (overwrite) return save(true);
      return;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (data.revision) state.csvRevision = data.revision;

    // Update clip numbers returned from server
    if (data.clips && data.clips.length === state.rows.length) {
      data.clips.forEach((clip, i) => {
        state.rows[i].clip = clip;
      });
    }

    // Flag rows modified during this session as adjusted so they display cross (†) upon save (excluding skipped rows)
    state.rows.forEach((r, i) => {
      if (isRowModified(i) && !isRowSkipped(r)) {
        r._adjusted = true;
      }
    });

    state.pristineRows = JSON.parse(JSON.stringify(state.rows));
    state.clipUndoHistory = {};
    if (el.undoClipBtn) el.undoClipBtn.disabled = true;

    setDirty(false);
    renderTable();
    updateInspector();

    if (invalidRows.length > 0) {
      showToast('Saved locally. Auto-push to Sheet was skipped due to invalid timing rows.', 'warning', 4000);
      setSheetSyncPill({ isError: true, text: 'Auto-push skipped (invalid timing rows)' });
    } else if (shouldAutoPush && data.sheet) {
      if (data.sheet.error) {
        setSheetSyncPill({ isError: true, text: `Auto-push failed: ${data.sheet.error}` });
      } else if (data.sheet.tab_name) {
        setSheetSyncPill({
          tabName: data.sheet.tab_name,
          url: data.sheet.url,
          text: `Pushed to ${data.sheet.tab_name} at ${format24hTime()}`,
        });
      }
    }
  } catch (err) {
    console.error('Save failed:', err);
    showToast('Failed to save CSV file. Check console for details.', 'error');
    setDirty(true);
  } finally {
    el.saveBtn.disabled = false;
  }
}

// Update Google Sheet sync pill (status / link to spreadsheet tab)
function setSheetSyncPill({ text, tabName, url, isError = false, isLoading = false } = {}) {
  if (!el.sheetSyncStatus) return;
  el.sheetSyncStatus.style.display = 'inline-flex';
  if (isError) {
    el.sheetSyncStatus.className = 'sheet-sync-pill error';
    el.sheetSyncStatus.removeAttribute('href');
    el.sheetSyncStatus.removeAttribute('target');
    el.sheetSyncStatus.removeAttribute('rel');
    el.sheetSyncStatus.removeAttribute('title');
    el.sheetSyncStatus.textContent = text || 'Error';
  } else if (isLoading) {
    el.sheetSyncStatus.className = 'sheet-sync-pill';
    el.sheetSyncStatus.removeAttribute('href');
    el.sheetSyncStatus.removeAttribute('target');
    el.sheetSyncStatus.removeAttribute('rel');
    el.sheetSyncStatus.removeAttribute('title');
    el.sheetSyncStatus.textContent = text || 'Pushing to Sheet...';
  } else {
    el.sheetSyncStatus.className = 'sheet-sync-pill';
    const displayTab = tabName || '';
    const displayText = text || (displayTab ? `Pushed to ${displayTab} at ${format24hTime()}` : `Pushed at ${format24hTime()}`);
    const sheetUrl = url || (globalDefaults && globalDefaults.sheet_id ? `https://docs.google.com/spreadsheets/d/${globalDefaults.sheet_id}/edit` : '');
    if (sheetUrl) {
      el.sheetSyncStatus.href = sheetUrl;
      el.sheetSyncStatus.target = '_blank';
      el.sheetSyncStatus.rel = 'noopener noreferrer';
      el.sheetSyncStatus.title = displayTab ? `Open Google Sheet (${displayTab}) in new tab` : 'Open Google Sheet in new tab';
      el.sheetSyncStatus.innerHTML = `<span>${escapeSafe(displayText)}</span> <span class="sheet-link-icon" aria-hidden="true">↗</span>`;
    } else {
      el.sheetSyncStatus.removeAttribute('href');
      el.sheetSyncStatus.removeAttribute('target');
      el.sheetSyncStatus.removeAttribute('rel');
      el.sheetSyncStatus.removeAttribute('title');
      el.sheetSyncStatus.textContent = displayText;
    }
  }
}

// Push the ENTIRE reviewed table to Google Sheet (cols A..P)
async function pushToGoogleSheet() {
  if (!state.currentGameId) return;

  if (el.pushSheetBtn) el.pushSheetBtn.disabled = true;
  setSheetSyncPill({ isLoading: true, text: 'Pushing to Sheet...' });

  try {
    const res = await fetch(`/api/sheet/push/${state.currentGameId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        headers: state.headers,
        rows: state.rows,
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.error) {
      setSheetSyncPill({ isError: true, text: `Push failed: ${data.error}` });
      showToast(`Google Sheet push failed: ${data.error}`, 'error');
    } else {
      setSheetSyncPill({
        tabName: data.tab_name,
        url: data.url,
        text: `Pushed to ${data.tab_name} at ${format24hTime()}`,
      });
    }
  } catch (err) {
    console.error('Sheet push failed:', err);
    setSheetSyncPill({ isError: true, text: 'Push failed' });
    showToast('Failed to push to Google Sheet. Check console for details.', 'error');
  } finally {
    if (el.pushSheetBtn) el.pushSheetBtn.disabled = false;
  }
}

// Trigger Re-cut (sync_game.py in --local mode)
async function triggerRecut() {
  if (!state.currentGameId) return;

  if (state.isDirty) {
    await save();
  }

  openLogModal(`✂️ Re-cut: ${state.currentGameId}`);
  if (el.recutBtn) el.recutBtn.disabled = true;

  try {
    const res = await fetch(`/api/recut/${state.currentGameId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.task_id) {
      streamTaskLogs(data.task_id, (exitCode, error) => {
        if (el.recutBtn) el.recutBtn.disabled = false;
        if (exitCode === 0) {
          if (el.saveStatus) {
            el.saveStatus.className = 'status-badge status-clean';
            el.saveStatus.textContent = `Re-cut complete (${format24hTime()})`;
          }
          showToast('Re-cut completed successfully.', 'success');
        } else {
          if (el.saveStatus) {
            el.saveStatus.className = 'status-badge status-dirty';
            el.saveStatus.textContent = `Re-cut failed (${format24hTime()})`;
          }
          showToast(`Re-cut failed with exit code ${exitCode}. Check logs for details.`, 'error');
        }
      });
    }
  } catch (err) {
    console.error('Re-cut failed to start:', err);
    showToast('Failed to start Re-cut. Check console for details.', 'error');
    if (el.recutBtn) el.recutBtn.disabled = false;
  }
}

// --- Re-cut & Review Dropdown Menu (P2) ---
function toggleRecutMenu(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const menu = document.getElementById('recutDropdownMenu');
  if (!menu) return;
  const isHidden = menu.style.display === 'none' || !menu.style.display;
  menu.style.display = isHidden ? 'block' : 'none';
}
window.toggleRecutMenu = toggleRecutMenu;

function closeRecutMenu() {
  const menu = document.getElementById('recutDropdownMenu');
  if (menu) menu.style.display = 'none';
}
window.closeRecutMenu = closeRecutMenu;

// --- Two-Pane Media Review Modal (P2) ---
function openMediaReviewModal(category = 'clips720') {
  if (!state.currentGameId) {
    showToast('No game loaded.', 'error');
    return;
  }
  closeRecutMenu();
  const modal = document.getElementById('mediaReviewModal');
  if (!modal) return;
  modal.style.display = 'flex';
  switchMediaCategory(category);
}
window.openMediaReviewModal = openMediaReviewModal;

function closeMediaReviewModal() {
  const modal = document.getElementById('mediaReviewModal');
  if (modal) modal.style.display = 'none';
  const vid = document.getElementById('mediaReviewVideo');
  if (vid) {
    try {
      vid.pause();
      vid.removeAttribute('src');
      vid.load();
    } catch (e) {}
  }
}
window.closeMediaReviewModal = closeMediaReviewModal;

function switchMediaCategory(category) {
  if (category === 'player_reels') category = 'reels4k';
  state.currentMediaCategory = category;
  const catNames = {
    clips720: 'Review 720p Clips (preview720/)',
    clips4k: 'Review 4K Clips (clips/)',
    reels720: 'Review 720p Reels (preview_reel)',
    reels4k: 'Review 4K Reels (Full Match, Team & Player)'
  };

  const title = document.getElementById('mediaReviewModalTitle');
  if (title) title.textContent = catNames[category] || 'Review Media';

  // Update category tab button classes
  const tabBtns = document.querySelectorAll('.media-cat-btn');
  tabBtns.forEach((btn) => {
    const catId = btn.id.replace('catBtn', '').toLowerCase();
    const cleanTarget = category.toLowerCase().replace('_', '');
    if (catId === cleanTarget || btn.dataset.cat === category) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  loadMediaFiles(category);
}
window.switchMediaCategory = switchMediaCategory;

async function loadMediaFiles(category = state.currentMediaCategory) {
  if (!state.currentGameId) return;
  const listEl = document.getElementById('mediaFileList');
  const countLabel = document.getElementById('mediaFileCountLabel');
  if (listEl) {
    listEl.innerHTML = '<div style="padding: 16px; font-size: 12px; color: #94A3B8; text-align: center;">Scanning for video files...</div>';
  }

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/media?category=${category}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.mediaFiles = data.files || [];
    state.selectedMediaIndex = 0;

    if (countLabel) {
      countLabel.textContent = `${state.mediaFiles.length} file${state.mediaFiles.length === 1 ? '' : 's'}`;
    }

    renderMediaFileList();
    if (state.mediaFiles.length > 0) {
      selectMediaFile(0);
    } else {
      const vid = document.getElementById('mediaReviewVideo');
      if (vid) {
        try { vid.pause(); } catch (_) {}
        vid.removeAttribute('src');
        vid.load();
      }
      const fnLabel = document.getElementById('mediaCurrentFileName');
      const detLabel = document.getElementById('mediaCurrentFileDetails');
      if (fnLabel) fnLabel.textContent = 'No files found in this category';
      if (detLabel) detLabel.textContent = `No output videos yet for ${category}. Run Re-cut or Final 4K Production to generate them.`;
    }
  } catch (err) {
    console.error('Failed to load media files:', err);
    if (listEl) {
      listEl.innerHTML = `<div style="padding: 16px; font-size: 12px; color: #F87171; text-align: center;">Failed to load files: ${err.message}</div>`;
    }
  }
}
window.loadMediaFiles = loadMediaFiles;

function renderMediaFileList() {
  const listEl = document.getElementById('mediaFileList');
  if (!listEl) return;
  if (!state.mediaFiles || state.mediaFiles.length === 0) {
    listEl.innerHTML = '<div style="padding: 18px; font-size: 12px; color: #64748B; text-align: center;">No files found.</div>';
    return;
  }

  let html = '';
  state.mediaFiles.forEach((f, idx) => {
    const isSelected = idx === state.selectedMediaIndex;
    const label = f.label || f.name;
    const metaStr = f.size_mb ? `${f.size_mb} MB` : (f.mtime_str || '');
    const titleAttr = `${escapeSafe(label)}${f.size_mb ? ' (' + f.size_mb + ' MB)' : ''}${f.mtime_str ? ' - ' + f.mtime_str : ''}`;
    html += `
      <div class="media-file-item ${isSelected ? 'active' : ''}" data-idx="${idx}" onclick="selectMediaFile(${idx})" title="${titleAttr}">
        <span class="media-file-title">${escapeSafe(label)}</span>
        <span class="media-file-meta">${escapeSafe(metaStr)}</span>
      </div>
    `;
  });
  listEl.innerHTML = html;

  // Ensure selected item is scrolled into view
  const activeEl = listEl.querySelector(`.media-file-item[data-idx="${state.selectedMediaIndex}"]`);
  if (activeEl) {
    activeEl.scrollIntoView({ block: 'nearest' });
  }
}
window.renderMediaFileList = renderMediaFileList;

function selectMediaFile(index) {
  if (!state.mediaFiles || index < 0 || index >= state.mediaFiles.length) return;
  state.selectedMediaIndex = index;
  const f = state.mediaFiles[index];

  // Update UI item selection
  const listEl = document.getElementById('mediaFileList');
  if (listEl) {
    const items = listEl.querySelectorAll('.media-file-item');
    items.forEach((it) => {
      const idx = Number(it.dataset.idx);
      if (idx === index) {
        it.classList.add('active');
        it.scrollIntoView({ block: 'nearest' });
      } else {
        it.classList.remove('active');
      }
    });
  }

  // Load into video player
  const vid = document.getElementById('mediaReviewVideo');
  const fnLabel = document.getElementById('mediaCurrentFileName');
  const detLabel = document.getElementById('mediaCurrentFileDetails');

  if (fnLabel) fnLabel.textContent = f.label || f.name;
  if (detLabel) {
    detLabel.textContent = `${f.name} • ${f.size_mb || 0} MB • ${f.mtime_str || ''}`;
  }

  if (vid) {
    vid.src = f.url;
    vid.load();
    const playPromise = vid.play();
    if (playPromise !== undefined) {
      playPromise.catch((e) => console.warn('Autoplay prevented or video load error:', e));
    }
  }
}
window.selectMediaFile = selectMediaFile;

function stepMediaFile(delta) {
  if (!state.mediaFiles || state.mediaFiles.length === 0) return;
  const newIndex = Math.max(0, Math.min(state.mediaFiles.length - 1, state.selectedMediaIndex + delta));
  if (newIndex !== state.selectedMediaIndex) {
    selectMediaFile(newIndex);
  }
}
window.stepMediaFile = stepMediaFile;

// --- Pull from Google Sheet (P6) ---
async function pullFromGoogleSheet() {
  if (!state.currentGameId) {
    showToast('No game loaded.', 'error');
    return;
  }

  if (state.isDirty) {
    const proceed = await showConfirm(
      'You have unsaved changes in the review table. Pulling from Google Sheet will overwrite local edits with the sheet data.\n\nContinue and pull from sheet?',
      'Unsaved Changes', 'Pull from Sheet', 'btn-warning'
    );
    if (!proceed) return;
  }

  showToast('Pulling reviewed rows from Google Sheet...', 'info');
  try {
    const res = await fetch(`/api/sheet/pull/${state.currentGameId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      throw new Error(data.message || data.error || `HTTP ${res.status}`);
    }

    state.rows = data.rows || state.rows;
    state.headers = data.headers || state.headers;
    state.pristineRows = JSON.parse(JSON.stringify(state.rows));
    if (data.revision) state.csvRevision = data.revision;

    if (data.clips && data.clips.length === state.rows.length) {
      data.clips.forEach((clip, i) => {
        state.rows[i].clip = clip;
      });
    }

    setDirty(false);
    renderTable();
    updateInspector();
    updateTimelineActionWindow();

    const changeCount = data.changes ? data.changes.length : 0;
    showToast(`Pulled ${data.pulled_rows || state.rows.length} rows from Google Sheet tab "${data.tab}". ${changeCount ? `(${changeCount} changes)` : ''}`, 'success');
  } catch (err) {
    console.error('Failed to pull from Google Sheet:', err);
    showToast(`Pull from Google Sheet failed: ${err.message}`, 'error');
  }
}
window.pullFromGoogleSheet = pullFromGoogleSheet;

// --- Quick Unlock 4K Production (P7) ---
function quickUnlockProduction() {
  const inp = document.getElementById('inpProductionConfirm');
  if (inp) {
    inp.value = 'START';
    onProductionConfirmInput();
  }
  const hint = document.getElementById('productionConfirmHint');
  if (hint) {
    hint.textContent = '✅ Quick Unlocked! Click Start 4K Production below (or press Enter)';
    hint.style.color = '#10B981';
  }
  const btn = document.getElementById('btnStartProduction');
  if (btn && !btn.disabled) {
    btn.focus();
  }
}
window.quickUnlockProduction = quickUnlockProduction;

// --- Silent Window Focus & Tab Visibility Sync (P1) ---
function setupWindowFocusSync() {
  let isSyncing = false;
  let lastSyncTime = 0;
  async function syncOnFocus() {
    if (!state.currentGameId || isSyncing) return;
    if (document.visibilityState !== 'visible') return;
    const now = Date.now();
    if (now - lastSyncTime < 10000) return; // Throttle to at most once per 10s
    isSyncing = true;
    lastSyncTime = now;
    try {
      // 1. Silently refresh zoom replays map and table badges
      const zoomRes = await fetch(`/api/zoom/${state.currentGameId}`);
      if (zoomRes.ok) {
        const data = await zoomRes.json();
        const replays = data.replays || (Array.isArray(data) ? data : []);
        state.zoomReplaysMap = {};
        if (Array.isArray(replays)) {
          replays.forEach((r) => {
            state.zoomReplaysMap[String(r.clip)] = r;
            state.zoomReplaysMap[r.token] = r;
          });
        }
        renderTable();
        updateInspector();
      }

      // 2. Check if disk CSV revision changed while we have NO dirty edits
      if (!state.isDirty) {
        const gameRes = await fetch(`/api/game/${state.currentGameId}`);
        if (gameRes.ok) {
          const gameData = await gameRes.json();
          if (gameData.revision && gameData.revision !== state.csvRevision) {
            state.csvRevision = gameData.revision;
            state.headers = gameData.headers || state.headers;
            state.rows = gameData.rows || state.rows;
            state.pristineRows = JSON.parse(JSON.stringify(state.rows));
            renderTable();
            updateInspector();
            updateTimelineActionWindow();
          }
        }
      }
    } catch (e) {
      console.warn('Silent focus sync error:', e);
    } finally {
      isSyncing = false;
    }
  }

  window.addEventListener('focus', syncOnFocus);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') syncOnFocus();
  });
}
window.setupWindowFocusSync = setupWindowFocusSync;

// Draggable Resizer Splitter between Left Table and Right Video Pane
function setupPaneResizer() {
  const resizer = el.paneResizer;
  const panel = el.timesPanel;
  if (!resizer || !panel) return;

  // Restore saved width from localStorage
  try {
    const saved = localStorage.getItem('review_editor_table_width');
    if (saved) {
      const w = parseInt(saved, 10);
      if (!isNaN(w) && w >= 270 && w <= 650) {
        panel.style.width = `${w}px`;
        panel.style.flex = `0 0 ${w}px`;
      }
    }
  } catch (e) {}

  let isDragging = false;
  resizer.addEventListener('pointerdown', (e) => {
    isDragging = true;
    resizer.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';

    const onPointerMove = (ev) => {
      if (!isDragging) return;
      const containerLeft = panel.parentElement.getBoundingClientRect().left;
      const newWidth = Math.max(275, Math.min(window.innerWidth - 450, ev.clientX - containerLeft));
      panel.style.width = `${newWidth}px`;
      panel.style.flex = `0 0 ${newWidth}px`;
    };

    const onPointerUp = () => {
      if (!isDragging) return;
      isDragging = false;
      resizer.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);

      try {
        const finalW = parseInt(panel.style.width, 10);
        if (!isNaN(finalW)) {
          localStorage.setItem('review_editor_table_width', finalW);
        }
      } catch (e) {}
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  });
}

// Horizontal Draggable Resizer between Video Player and Timeline/Editing Controls
function setupVideoResizer() {
  const resizer = document.getElementById('videoResizer');
  const wrapper = document.getElementById('playerWrapper');
  const pill = document.getElementById('videoFitPill');
  const card = document.querySelector('.video-card');
  if (!resizer || !wrapper) return;

  function setAutoFitMode() {
    try { localStorage.removeItem('review_editor_video_height'); } catch (e) {}
    wrapper.style.flex = '1 1 0';
    wrapper.style.height = '';
    wrapper.style.minHeight = '0';
    if (card) card.classList.remove('has-custom-height');
    if (pill) {
      pill.textContent = 'Fit: Auto ⤢';
      pill.classList.add('active');
      pill.title = 'Auto Maximum Fill (16:9). Click to reset or adjust.';
    }
  }

  function setCustomHeight(h) {
    if (!card) return;
    const metaBar = card.querySelector('.video-meta-bar');
    const timeline = card.querySelector('.timeline-wrapper');
    const bottomControls = card.querySelector('.video-bottom-controls');
    const bottomControlsChildrenH = bottomControls && bottomControls.children.length
      ? Array.from(bottomControls.children).reduce((sum, el) => sum + el.offsetHeight, 0) + 12
      : 72;
    const nonVideoH = (metaBar ? metaBar.offsetHeight : 28) +
                      (resizer ? resizer.offsetHeight : 8) +
                      (timeline ? timeline.offsetHeight : 64) +
                      Math.max(68, Math.min(100, bottomControlsChildrenH)) + 4;
    const maxH = Math.max(160, card.clientHeight - nonVideoH);
    const clampedH = Math.max(160, Math.min(maxH, h));

    wrapper.style.flex = 'none';
    wrapper.style.height = `${clampedH}px`;
    card.classList.add('has-custom-height');
    try { localStorage.setItem('review_editor_video_height', String(clampedH)); } catch (e) {}

    if (pill) {
      pill.textContent = 'Fit: Custom ↕';
      pill.classList.remove('active');
      pill.title = 'Custom video height applied. Double-click splitter to reset Auto Fill.';
    }
  }

  // Restore saved state or default to Auto Max Fill
  let saved = null;
  try { saved = localStorage.getItem('review_editor_video_height'); } catch (e) {}
  if (saved && !isNaN(parseInt(saved, 10)) && parseInt(saved, 10) > 180) {
    setCustomHeight(parseInt(saved, 10));
  } else {
    setAutoFitMode();
  }

  // Draggable Splitter
  let isDragging = false;
  let startY = 0;
  let startHeight = 0;

  resizer.addEventListener('pointerdown', (e) => {
    isDragging = true;
    try { resizer.setPointerCapture(e.pointerId); } catch (err) {}
    startY = e.clientY;
    startHeight = wrapper.getBoundingClientRect().height;
    resizer.classList.add('dragging');
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';

    const onPointerMove = (ev) => {
      if (!isDragging) return;
      const delta = ev.clientY - startY;
      setCustomHeight(startHeight + delta);
    };

    const onPointerUp = (ev) => {
      if (!isDragging) return;
      isDragging = false;
      try { resizer.releasePointerCapture(ev.pointerId); } catch (err) {}
      resizer.classList.remove('dragging');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
  });

  // Double-click resizer resets to Auto Maximum Fill
  resizer.addEventListener('dblclick', () => {
    setAutoFitMode();
  });
}

function toggleVideoFit16x9() {
  const wrapper = document.getElementById('playerWrapper');
  const pill = document.getElementById('videoFitPill');
  const card = document.querySelector('.video-card');
  if (!wrapper) return;

  let saved = null;
  try { saved = localStorage.getItem('review_editor_video_height'); } catch (e) {}

  if (saved || (card && card.classList.contains('has-custom-height'))) {
    // Reset back to pure Auto Max Fill
    try { localStorage.removeItem('review_editor_video_height'); } catch (e) {}
    wrapper.style.flex = '1 1 0';
    wrapper.style.height = '';
    wrapper.style.minHeight = '0';
    if (card) card.classList.remove('has-custom-height');
    if (pill) {
      pill.textContent = 'Fit: Auto ⤢';
      pill.classList.add('active');
      pill.title = 'Auto Maximum Fill (16:9). Click to reset or adjust.';
    }
    showToast('Reset to Auto Maximum Fill (fits viewport with zero scrollbars).', 'info');
  } else {
    showToast('Auto Maximum Fill is active. Drag horizontal bar to customize height.', 'info');
  }
}
window.toggleVideoFit16x9 = toggleVideoFit16x9;

// Video Viewport Zoom & Pan
const videoZoomState = {
  scale: 1.0,
  panX: 0,
  panY: 0,
  isPanning: false,
  hasDragged: false,
  startX: 0,
  startY: 0,
  startPanX: 0,
  startPanY: 0,
};

function isVideoZoomed() {
  return videoZoomState.scale > 1.001;
}

function updateVideoZoomUI() {
  const pill = el.videoZoomPill || document.getElementById('videoZoomPill');
  const wrapper = el.playerWrapper || document.getElementById('playerWrapper');
  const video = el.mainVideo || document.getElementById('mainVideo');

  if (isVideoZoomed()) {
    if (pill) {
      pill.style.display = 'inline-flex';
      pill.textContent = `🔍 ${videoZoomState.scale.toFixed(1)}× (Reset)`;
      pill.classList.add('active');
    }
    if (wrapper) {
      wrapper.classList.add('is-zoomed');
      wrapper.style.cursor = videoZoomState.isPanning ? 'grabbing' : 'grab';
    }
    if (video) {
      video.classList.add('is-zoomed');
      video.style.cursor = videoZoomState.isPanning ? 'grabbing' : 'grab';
    }
  } else {
    if (pill) {
      pill.style.display = 'none';
      pill.classList.remove('active');
    }
    if (wrapper) {
      wrapper.classList.remove('is-zoomed', 'is-panning');
      wrapper.style.cursor = '';
    }
    if (video) {
      video.classList.remove('is-zoomed');
      video.style.cursor = '';
    }
  }
}

function applyVideoZoomTransform(immediate = false) {
  const video = el.mainVideo || document.getElementById('mainVideo');
  if (!video) return;

  if (!isVideoZoomed()) {
    videoZoomState.scale = 1.0;
    videoZoomState.panX = 0;
    videoZoomState.panY = 0;
    video.style.transition = immediate ? 'none' : 'transform 0.15s ease-out';
    video.style.transform = '';
  } else {
    video.style.transformOrigin = 'center center';
    video.style.transition = immediate ? 'none' : 'transform 0.08s ease-out';
    video.style.transform = `translate(${videoZoomState.panX.toFixed(2)}px, ${videoZoomState.panY.toFixed(2)}px) scale(${videoZoomState.scale.toFixed(3)})`;
  }
  updateVideoZoomUI();
}

function clampVideoPan(rect) {
  if (!isVideoZoomed()) {
    videoZoomState.panX = 0;
    videoZoomState.panY = 0;
    return;
  }
  const wrapper = el.playerWrapper || document.getElementById('playerWrapper');
  const r = rect || (wrapper ? wrapper.getBoundingClientRect() : null);
  if (!r) return;

  const maxPanX = Math.max(0, (r.width * (videoZoomState.scale - 1)) / 2 + 40);
  const maxPanY = Math.max(0, (r.height * (videoZoomState.scale - 1)) / 2 + 40);

  videoZoomState.panX = Math.max(-maxPanX, Math.min(maxPanX, videoZoomState.panX));
  videoZoomState.panY = Math.max(-maxPanY, Math.min(maxPanY, videoZoomState.panY));
}

function resetVideoZoom() {
  if (videoZoomState.scale === 1.0 && videoZoomState.panX === 0 && videoZoomState.panY === 0) return;
  videoZoomState.scale = 1.0;
  videoZoomState.panX = 0;
  videoZoomState.panY = 0;
  videoZoomState.isPanning = false;
  applyVideoZoomTransform(false);
}
window.resetVideoZoom = resetVideoZoom;

function zoomVideoAt(deltaY, clientX, clientY) {
  const wrapper = el.playerWrapper || document.getElementById('playerWrapper');
  if (!wrapper) return;
  const rect = wrapper.getBoundingClientRect();

  const cursorX = clientX - (rect.left + rect.width / 2);
  const cursorY = clientY - (rect.top + rect.height / 2);

  const prevScale = videoZoomState.scale;
  const prevPanX = videoZoomState.panX;
  const prevPanY = videoZoomState.panY;

  const worldX = (cursorX - prevPanX) / prevScale;
  const worldY = (cursorY - prevPanY) / prevScale;

  const factor = deltaY < 0 ? 1.18 : (1 / 1.18);
  let nextScale = prevScale * factor;

  if (nextScale <= 1.04) {
    nextScale = 1.0;
  } else if (nextScale > 6.0) {
    nextScale = 6.0;
  }

  videoZoomState.scale = nextScale;

  if (nextScale === 1.0) {
    videoZoomState.panX = 0;
    videoZoomState.panY = 0;
  } else {
    videoZoomState.panX = cursorX - worldX * nextScale;
    videoZoomState.panY = cursorY - worldY * nextScale;
    clampVideoPan(rect);
  }

  applyVideoZoomTransform(false);
}

function setupVideoViewportZoom() {
  const wrapper = el.playerWrapper || document.getElementById('playerWrapper');
  const video = el.mainVideo || document.getElementById('mainVideo');
  if (!wrapper || !video) return;

  // Wheel with Ctrl or Shift (also captures trackpad pinch-zoom)
  wrapper.addEventListener('wheel', (e) => {
    if (e.ctrlKey || e.shiftKey || e.metaKey) {
      e.preventDefault();
      e.stopPropagation();
      zoomVideoAt(e.deltaY, e.clientX, e.clientY);
    }
  }, { passive: false });

  // Panning when zoomed in
  wrapper.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !isVideoZoomed()) return;

    videoZoomState.isPanning = true;
    videoZoomState.hasDragged = false;
    videoZoomState.startX = e.clientX;
    videoZoomState.startY = e.clientY;
    videoZoomState.startPanX = videoZoomState.panX;
    videoZoomState.startPanY = videoZoomState.panY;

    try { wrapper.setPointerCapture(e.pointerId); } catch (err) {}
    wrapper.classList.add('is-panning');
    updateVideoZoomUI();
  });

  wrapper.addEventListener('pointermove', (e) => {
    if (!videoZoomState.isPanning) return;
    const dx = e.clientX - videoZoomState.startX;
    const dy = e.clientY - videoZoomState.startY;

    if (Math.hypot(dx, dy) > 3) {
      videoZoomState.hasDragged = true;
    }

    videoZoomState.panX = videoZoomState.startPanX + dx;
    videoZoomState.panY = videoZoomState.startPanY + dy;
    clampVideoPan();
    applyVideoZoomTransform(true);
  });

  const stopPanning = (e) => {
    if (!videoZoomState.isPanning) return;
    videoZoomState.isPanning = false;
    try { wrapper.releasePointerCapture(e.pointerId); } catch (err) {}
    wrapper.classList.remove('is-panning');
    updateVideoZoomUI();
    applyVideoZoomTransform(false);
  };

  wrapper.addEventListener('pointerup', stopPanning);
  wrapper.addEventListener('pointercancel', stopPanning);

  // Double-click resets zoom
  wrapper.addEventListener('dblclick', (e) => {
    if (isVideoZoomed()) {
      e.preventDefault();
      e.stopPropagation();
      resetVideoZoom();
    }
  });

  window.addEventListener('resize', () => {
    if (isVideoZoomed()) {
      clampVideoPan();
      applyVideoZoomTransform(true);
    }
  });
}

// Log Terminal Modal
// Log window: auto-close on success (checkbox, remembered) + a toolbar "Log" button to look at the last job again.
state.logSeq = 0;
try {
  if (el.logAutoClose && localStorage.getItem('xbotgo.logAutoClose') === '0') el.logAutoClose.checked = false;
} catch (e) { /* storage may be unavailable */ }
if (el.logAutoClose) {
  el.logAutoClose.addEventListener('change', () => {
    try { localStorage.setItem('xbotgo.logAutoClose', el.logAutoClose.checked ? '1' : '0'); } catch (e) { /* ignore */ }
  });
}

function maybeAutoCloseLog(exitCode, seq) {
  if (exitCode !== 0 || !el.logAutoClose || !el.logAutoClose.checked) return;
  setTimeout(() => {
    // still the same job's window, still ticked (the user may untick it while the job runs or right after)
    if (seq === state.logSeq && el.logAutoClose.checked && el.logModal && el.logModal.style.display !== 'none') {
      closeLogModal();
      showToast('Finished - click 📋 Log to see the log again.', 'success', 3000);
    }
  }, 1500);
}

async function viewLastLog() {
  if (state.logSeq > 0 && el.logModal) {          // a job ran in this page: its text is still in the window
    el.logModal.style.display = 'flex';
    return;
  }
  if (!state.currentGameId) { showToast('No log yet.', 'info'); return; }
  try {
    const res = await fetch(`/api/game/${state.currentGameId}/last-task`);
    const d = await res.json();
    if (!d.has_task) { showToast('No log for this game yet.', 'info'); return; }
    openLogModal(`📋 ${d.task_name || 'Last job'}`);
    el.logModalPre.textContent = (d.lines || []).join('\n') + '\n';
    el.logModalPre.scrollTop = el.logModalPre.scrollHeight;
    el.logModalCloseBtn.disabled = false;
    el.logModalStatus.className = d.exit_code === 0 ? 'log-status success' : 'log-status error';
    el.logModalStatus.textContent = d.done ? (d.exit_code === 0 ? '✅ Completed successfully' : `❌ Failed (code ${d.exit_code})`) : 'Running...';
  } catch (e) {
    showToast('Could not load the last log.', 'error');
  }
}
window.viewLastLog = viewLastLog;

function openLogModal(title) {
  state.logSeq += 1;
  if (el.logModal) {
    el.logModalTitle.textContent = title;
    el.logModalPre.textContent = 'Initializing process...\n';
    el.logModalStatus.textContent = 'Running...';
    el.logModalCloseBtn.disabled = true;
    el.logModal.style.display = 'flex';
  }
}

function closeLogModal() {
  if (productionLogModalPoll) {
    clearInterval(productionLogModalPoll);
    productionLogModalPoll = null;
  }
  if (el.logModal) {
    el.logModal.style.display = 'none';
  }
}

function streamTaskLogs(taskId, onFinish) {
  const seq = state.logSeq;
  let eventSource = null;
  let isDone = false;

  const appendLine = (txt) => {
    if (el.logModalPre) {
      el.logModalPre.textContent += txt + '\n';
      el.logModalPre.scrollTop = el.logModalPre.scrollHeight;
    }
  };

  try {
    eventSource = new EventSource(`/api/tasks/${taskId}/stream`);
    eventSource.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data);
        if (d.line) appendLine(d.line);
        if (d.done) {
          isDone = true;
          eventSource.close();
          if (el.logModalCloseBtn) el.logModalCloseBtn.disabled = false;
          if (el.logModalStatus) {
            el.logModalStatus.className = d.exit_code === 0 ? 'log-status success' : 'log-status error';
            el.logModalStatus.textContent = d.exit_code === 0 ? '✅ Completed successfully' : `❌ Failed (code ${d.exit_code})`;
          }
          if (onFinish) onFinish(d.exit_code, d.error);
          maybeAutoCloseLog(d.exit_code, seq);
        }
      } catch (err) {
        console.error('Error parsing SSE event:', err);
      }
    };

    eventSource.onerror = (err) => {
      if (isDone) return;
      console.warn('SSE connection closed or error, falling back to polling:', err);
      if (eventSource) eventSource.close();
      pollTaskStatus(taskId, onFinish, appendLine, seq);
    };
  } catch (e) {
    console.warn('EventSource failed, using polling:', e);
    pollTaskStatus(taskId, onFinish, appendLine, seq);
  }
}

function pollTaskStatus(taskId, onFinish, appendLine, seq) {
  let offset = 0;
  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}/status?offset=${offset}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();
      if (d.lines && d.lines.length > 0) {
        d.lines.forEach(appendLine);
        offset = d.next_offset;
      }
      if (d.done) {
        clearInterval(timer);
        if (el.logModalCloseBtn) el.logModalCloseBtn.disabled = false;
        if (el.logModalStatus) {
          el.logModalStatus.textContent = d.exit_code === 0 ? '✅ Completed successfully' : `❌ Failed (code ${d.exit_code})`;
        }
        if (onFinish) onFinish(d.exit_code, d.error);
        maybeAutoCloseLog(d.exit_code, seq);
      }
    } catch (err) {
      clearInterval(timer);
      console.error('Polling task status failed:', err);
      if (el.logModalCloseBtn) el.logModalCloseBtn.disabled = false;
    }
  }, 400);
}

// Calendar Date Picker Modal & Reload Warnings
function updateCalendarReloadNote(dateVal) {
  const noteTitle = document.getElementById('calendarReloadNoteTitle');
  const noteDetail = document.getElementById('calendarReloadNoteDetail');
  const noteBox = document.getElementById('calendarReloadNoteBox');
  if (!noteTitle || !noteDetail || !noteBox) return;

  if (!dateVal || !/^\d{4}-\d{2}-\d{2}$/.test(dateVal)) {
    noteBox.style.backgroundColor = '#EFF6FF';
    noteBox.style.borderColor = '#93C5FD';
    noteBox.style.color = '#1E40AF';
    noteTitle.textContent = 'Opening a date reloads all data for that game.';
    noteDetail.textContent = 'Select a date above to preview the load action.';
    return;
  }

  const isCurrent = Boolean(state.currentGameId && state.currentGameId.startsWith(dateVal));
  const meta = state.availableDatesMeta ? state.availableDatesMeta[dateVal] : null;

  if (!isCurrent && state.isDirty) {
    noteBox.style.backgroundColor = '#FEE2E2';
    noteBox.style.borderColor = '#EF4444';
    noteBox.style.color = '#991B1B';
    noteTitle.textContent = `⚠️ Unsaved changes in ${state.currentGameId} will be lost if you open ${dateVal}.`;
    noteDetail.textContent = 'Close this dialog and press Save first to keep them.';
  } else if (isCurrent) {
    if (state.isDirty) {
      noteBox.style.backgroundColor = '#FEE2E2';
      noteBox.style.borderColor = '#EF4444';
      noteBox.style.color = '#991B1B';
      noteTitle.textContent = `⚠️ Current game ${dateVal} will be reloaded; unsaved changes will be lost!`;
      noteDetail.textContent = 'You have unsaved changes in the active table. Reloading will discard all unsaved edits and restore the last saved version from disk.';
    } else {
      noteBox.style.backgroundColor = '#EFF6FF';
      noteBox.style.borderColor = '#93C5FD';
      noteBox.style.color = '#1E40AF';
      noteTitle.textContent = `Game ${dateVal} is already open.`;
      noteDetail.textContent = 'Nothing to overwrite: you have no unsaved changes. Open / Generate just refreshes it from disk.';
    }
  } else if (meta && meta.status === 'reviewed') {
    noteBox.style.backgroundColor = '#ECFDF5';
    noteBox.style.borderColor = '#10B981';
    noteBox.style.color = '#065F46';
    noteTitle.textContent = `Reviewed table for ${dateVal} will be loaded from disk.`;
    noteDetail.textContent = `Existing reviewed CSV (out/reviewed/${dateVal}_reviewed.csv) and match videos will open directly in the editor.`;
  } else if (meta && meta.status === 'dump') {
    noteBox.style.backgroundColor = '#EFF6FF';
    noteBox.style.borderColor = '#93C5FD';
    noteBox.style.color = '#1E40AF';
    noteTitle.textContent = `New game: a review table will be created from the dump for ${dateVal}.`;
    noteDetail.textContent = 'Nothing exists for this date yet, so nothing can be overwritten. This reads the video and app log (about a minute).';
  } else {
    noteBox.style.backgroundColor = '#EFF6FF';
    noteBox.style.borderColor = '#93C5FD';
    noteBox.style.color = '#1E40AF';
    noteTitle.textContent = `All data for ${dateVal} will be reloaded into the workspace.`;
    noteDetail.textContent = 'The editor will open an existing reviewed table if present, or generate one from the recording dump.';
  }
}

function onCalendarDateInputChange() {
  const d = el.calendarDateInput.value.trim();
  if (el.availableDatesList) {
    el.availableDatesList.querySelectorAll('.date-pill').forEach(p => {
      if (p.textContent === d) p.classList.add('selected');
      else p.classList.remove('selected');
    });
  }
  cancelCalendarConfirm();
  updateCalendarReloadNote(d);
}

window.onCalendarDateInputChange = onCalendarDateInputChange;

async function openCalendarModal() {
  if (!el.calendarModal) return;
  cancelCalendarConfirm();
  el.calendarModal.style.display = 'flex';
  el.calendarModalFeedback.style.display = 'none';

  // Pre-fill input with current game date if valid
  if (state.currentGameId && /^\d{4}-\d{2}-\d{2}/.test(state.currentGameId)) {
    el.calendarDateInput.value = state.currentGameId.substring(0, 10);
  }

  await loadAvailableDates();
  updateCalendarReloadNote(el.calendarDateInput.value);
}

function closeCalendarModal() {
  cancelCalendarConfirm();
  if (el.calendarModal) {
    el.calendarModal.style.display = 'none';
  }
  // Restore dropdown to selected game if cancelled
  if (el.gameSelect && state.currentGameId) {
    el.gameSelect.value = state.currentGameId;
  }
}

async function loadAvailableDates() {
  if (!el.availableDatesList) return;
  el.availableDatesList.innerHTML = '<span class="status-loading">Loading dates...</span>';

  const hintEl = document.getElementById('calendarHoverHint');
  const defaultHint = 'Hover over a date to view format and status.';
  if (hintEl) {
    hintEl.textContent = defaultHint;
    hintEl.classList.remove('is-warning');
  }

  state.availableDatesMeta = {};

  try {
    const res = await fetch('/api/calendar/available-dates');
    const data = await res.json();

    el.availableDatesList.innerHTML = '';

    // If rich dates array is returned from server
    if (data.dates && Array.isArray(data.dates) && data.dates.length > 0) {
      data.dates.forEach((item) => {
        state.availableDatesMeta[item.date] = item;
        const pill = document.createElement('button');
        pill.className = 'date-pill';
        pill.textContent = item.date;
        pill.title = item.hint; // Native hover tooltip

        if (el.calendarDateInput && el.calendarDateInput.value === item.date) {
          pill.classList.add('selected');
        }

        if (!item.enabled) {
          pill.classList.add('is-disabled');
          pill.setAttribute('aria-disabled', 'true');
          pill.onmouseenter = () => {
            if (hintEl) {
              hintEl.textContent = `⚠️ ${item.date}: ${item.hint}`;
              hintEl.classList.add('is-warning');
            }
          };
          pill.onmouseleave = () => {
            if (hintEl) {
              hintEl.textContent = defaultHint;
              hintEl.classList.remove('is-warning');
            }
          };
          pill.onclick = (e) => {
            e.preventDefault();
            if (el.calendarModalFeedback) {
              el.calendarModalFeedback.style.display = 'block';
              el.calendarModalFeedback.className = 'modal-feedback error';
              el.calendarModalFeedback.textContent = `Cannot open ${item.date}: ${item.hint}`;
            }
          };
        } else {
          if (item.status === 'reviewed') {
            pill.classList.add('has-reviewed');
          } else if (item.status === 'dump') {
            pill.classList.add('has-dump');
          }
          pill.onmouseenter = () => {
            if (hintEl) {
              hintEl.textContent = `✓ ${item.date}: ${item.hint}`;
              hintEl.classList.remove('is-warning');
            }
          };
          pill.onmouseleave = () => {
            if (hintEl) {
              hintEl.textContent = defaultHint;
              hintEl.classList.remove('is-warning');
            }
          };
          pill.onclick = () => {
            el.calendarDateInput.value = item.date;
            el.availableDatesList.querySelectorAll('.date-pill').forEach(p => p.classList.remove('selected'));
            pill.classList.add('selected');
            cancelCalendarConfirm();
            if (el.calendarModalFeedback) {
              el.calendarModalFeedback.style.display = 'none';
            }
            updateCalendarReloadNote(item.date);
          };
        }

        el.availableDatesList.appendChild(pill);
      });
      return;
    }

    // Fallback if data.dates not available
    const reviewed = new Set(data.reviewed_dates || []);
    const dumps = new Set(data.dump_dates || []);
    const allDates = Array.from(new Set([...reviewed, ...dumps, ...(data.out_dates || [])])).sort().reverse();

    if (allDates.length === 0) {
      el.availableDatesList.innerHTML = '<span class="text-muted">No match dates detected on disk.</span>';
      return;
    }

    allDates.forEach((d) => {
      const isRev = reviewed.has(d);
      const isDump = dumps.has(d);
      state.availableDatesMeta[d] = {
        date: d,
        status: isRev ? 'reviewed' : (isDump ? 'dump' : 'other'),
        enabled: true,
        hint: isRev ? 'Reviewed CSV available' : 'Video dump detected'
      };

      const pill = document.createElement('button');
      pill.className = 'date-pill';
      if (isRev) {
        pill.classList.add('has-reviewed');
        pill.title = 'Reviewed CSV available';
      } else if (isDump) {
        pill.classList.add('has-dump');
        pill.title = 'Video dump detected (will auto-generate)';
      }
      if (el.calendarDateInput && el.calendarDateInput.value === d) {
        pill.classList.add('selected');
      }
      pill.textContent = d;
      pill.onclick = () => {
        el.calendarDateInput.value = d;
        el.availableDatesList.querySelectorAll('.date-pill').forEach(p => p.classList.remove('selected'));
        pill.classList.add('selected');
        cancelCalendarConfirm();
        updateCalendarReloadNote(d);
      };
      el.availableDatesList.appendChild(pill);
    });
  } catch (err) {
    console.error('Failed to load available dates:', err);
    el.availableDatesList.innerHTML = '<span class="text-muted">Error loading dates.</span>';
  }
}

function cancelCalendarConfirm() {
  const confirmBox = document.getElementById('calendarConfirmBox');
  const footer = document.getElementById('calendarModalFooter');
  if (confirmBox) confirmBox.style.display = 'none';
  if (footer) footer.style.display = 'flex';
}

window.cancelCalendarConfirm = cancelCalendarConfirm;

function submitCalendarPick() {
  const dateVal = el.calendarDateInput.value.trim();
  if (!dateVal || !/^\d{4}-\d{2}-\d{2}$/.test(dateVal)) {
    el.calendarModalFeedback.style.display = 'block';
    el.calendarModalFeedback.className = 'modal-feedback error';
    el.calendarModalFeedback.textContent = 'Please enter or select a valid date (YYYY-MM-DD).';
    return;
  }

  // Only ask when something can actually be lost: unsaved edits in the open game.
  // New games, reviewed games and a clean reload overwrite nothing, so no confirmation (and no red box).
  const confirmBox = document.getElementById('calendarConfirmBox');
  const confirmTitle = document.getElementById('calendarConfirmTitle');
  const confirmDesc = document.getElementById('calendarConfirmDesc');
  const footer = document.getElementById('calendarModalFooter');

  if (confirmBox && state.isDirty) {
    const isCurrent = Boolean(state.currentGameId && state.currentGameId.startsWith(dateVal));
    if (isCurrent) {
      confirmTitle.textContent = `Discard Unsaved Changes & Reload ${dateVal}?`;
      confirmDesc.textContent = `You have unsaved edits in active match ${dateVal}. Proceeding will discard all unsaved edits and reload the last saved version from disk.`;
    } else {
      confirmTitle.textContent = `Discard Unsaved Changes & Open ${dateVal}?`;
      confirmDesc.textContent = `You have unsaved edits in ${state.currentGameId}. Opening ${dateVal} will discard them. Press Cancel and Save first to keep them.`;
    }
    confirmBox.style.display = 'block';
    if (footer) footer.style.display = 'none';
    return;
  }

  proceedCalendarPick();
}

async function proceedCalendarPick() {
  cancelCalendarConfirm();
  const dateVal = el.calendarDateInput.value.trim();
  el.calendarSubmitBtn.disabled = true;
  el.calendarModalFeedback.style.display = 'block';
  el.calendarModalFeedback.className = 'modal-feedback';
  el.calendarModalFeedback.textContent = `Checking recordings for ${dateVal}...`;

  try {
    const res = await fetch('/api/game/find-or-generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: dateVal }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.status === 'exists' || data.status === 'imported') {
      closeCalendarModal();
      await loadGamesList(data.game_id);
    } else if (data.status === 'unsupported' || data.status === 'not_found') {
      el.calendarModalFeedback.className = 'modal-feedback error';
      el.calendarModalFeedback.textContent = data.message || `Cannot open ${dateVal}: format not supported.`;
    } else if (data.status === 'started') {
      closeCalendarModal();
      openLogModal(`⚡ Generating Review CSV: ${dateVal}`);
      streamTaskLogs(data.task_id, async (exitCode, error) => {
        if (exitCode === 0) {
          await loadGamesList(data.game_id);
        } else {
          showToast(`Generation failed for ${dateVal}. Check logs for details.`, 'error');
        }
      });
    }
  } catch (err) {
    console.error('Calendar pick error:', err);
    el.calendarModalFeedback.className = 'modal-feedback error';
    el.calendarModalFeedback.textContent = `Error: ${err.message}`;
  } finally {
    el.calendarSubmitBtn.disabled = false;
  }
}

window.proceedCalendarPick = proceedCalendarPick;

// Game Setup & Info Wizard Functions
async function openGameInfoModal(isWizard = false) {
  if (!state.currentGameId) {
    showToast('Please select a game first', 'info');
    return;
  }

  const modal = document.getElementById('gameInfoModal');
  if (!modal) return;

  const titleEl = document.getElementById('gameInfoModalTitle');
  const subEl = document.getElementById('gameInfoModalSubtitle');
  if (titleEl) {
    titleEl.textContent = isWizard ? '✨ Quick Game Setup' : '⚙️ Game Setup & Info';
  }
  if (subEl) {
    subEl.textContent = isWizard
      ? 'Welcome! Configure opponent, crest, and league for this game to enable clean highlight reels and scoreboard sync.'
      : 'Set opponent, logos, and league for highlight reels and scoreboard sync.';
  }

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/info`);
    if (res.ok) {
      const data = await res.json();
      state.gameInfo = data.game_info || {};
      state.availableLogos = data.logos || [];
    }
  } catch (err) {
    console.warn('Failed to fetch game info:', err);
  }

  await loadGlobalDefaults();
  const gi = state.gameInfo || {};
  const logos = state.availableLogos || [];

  // Populate datalist for opponent autocomplete
  const datalist = document.getElementById('opponentTeamsList');
  if (datalist) {
    datalist.innerHTML = '';
    const teamNames = Array.from(new Set(logos.map(l => l.team).filter(Boolean))).sort();
    teamNames.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      datalist.appendChild(opt);
    });
  }

  // Populate selects for crests/logos (Home & Away)
  const selHome = document.getElementById('selHomeLogo');
  if (selHome) {
    selHome.innerHTML = '';
    logos.forEach(l => {
      const opt = document.createElement('option');
      opt.value = l.rel_path;
      opt.textContent = `${l.team} (${l.filename})`;
      selHome.appendChild(opt);
    });
    selHome.value = gi.home_logo || cfgDefaults().team_logo || '';
  }

  const selAway = document.getElementById('selAwayLogo');
  if (selAway) {
    selAway.innerHTML = '';
    const noneOpt = document.createElement('option');
    noneOpt.value = '';
    noneOpt.textContent = '(None / No Logo)';
    selAway.appendChild(noneOpt);

    logos.forEach(l => {
      const opt = document.createElement('option');
      opt.value = l.rel_path;
      opt.textContent = `${l.team} (${l.filename})`;
      selAway.appendChild(opt);
    });
    selAway.value = gi.away_logo || '';
    // New game: the opponent name is already known from the log but no crest is chosen yet: pre-select the matching one.
    if (!selAway.value && (gi.opponent || '').trim()) {
      const m = findLogoForOpponent(gi.opponent);
      if (m) selAway.value = m.rel_path;
    }
  }

  // Set league radio & custom row (leagues come from config; any other name is a custom league)
  let lChoice = defaultLeagueName();
  const knownLeague = leagueByName(gi.league);
  if (knownLeague) {
    lChoice = knownLeague.name;
  } else if (gi.league) {
    lChoice = 'Other';
    state.customLeagueLogo = gi.league_logo;
    const inpCust = document.getElementById('inpCustomLeague');
    if (inpCust) inpCust.value = gi.league;
  }
  renderLeaguePills('leaguePills', 'leagueChoice', onLeagueChoiceChange, lChoice);
  onLeagueChoiceChange(lChoice);

  // Set text fields
  const inpMatch = document.getElementById('inpMatchName');
  if (inpMatch) {
    inpMatch.value = gi.match_name || (state.currentGameId ? `${state.currentGameId} ${gi.home || cfgDefaults().team_name} v ${gi.opponent || ''}`.trim() : '');
  }

  const inpHome = document.getElementById('inpHomeName');
  if (inpHome) inpHome.value = gi.home || cfgDefaults().team_name;

  const inpOpponent = document.getElementById('inpOpponentName');
  if (inpOpponent) inpOpponent.value = gi.opponent || '';

  const inpScore = document.getElementById('inpFinalScore');
  if (inpScore) inpScore.value = gi.score || '';

  const inpHalf = document.getElementById('inpHalftimeScore');
  if (inpHalf) inpHalf.value = gi.halftime_score || '';

  const inpDate = document.getElementById('inpGameDate');
  if (inpDate) {
    if (gi.date) {
      inpDate.value = gi.date;
    } else if (state.currentGameId && /^\d{4}-\d{2}-\d{2}/.test(state.currentGameId)) {
      const parts = state.currentGameId.substring(0, 10).split('-');
      const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
      inpDate.value = d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
    } else {
      inpDate.value = '';
    }
  }

  onHomeLogoChange();
  onAwayLogoChange();
  modal.style.display = 'flex';
}

function closeGameInfoModal() {
  const modal = document.getElementById('gameInfoModal');
  if (modal) modal.style.display = 'none';
}

function onHomeLogoChange() {
  const selHome = document.getElementById('selHomeLogo');
  const img = document.getElementById('homeLogoImg');
  const placeholder = document.getElementById('homeLogoPlaceholder');
  if (!selHome || !img || !placeholder) return;

  const val = selHome.value;
  if (val) {
    img.src = '/' + val.replace(/^\/+/, '');
    img.style.display = 'block';
    placeholder.style.display = 'none';
  } else {
    img.style.display = 'none';
    placeholder.style.display = 'inline-block';
  }
}

function onLeagueChoiceChange(choice) {
  let val = choice;
  if (!val) {
    const checked = document.querySelector('input[name="leagueChoice"]:checked');
    val = checked ? checked.value : defaultLeagueName();
  }
  const customRow = document.getElementById('customLeagueRow');
  const img = document.getElementById('leagueLogoImg');
  const lg = leagueByName(val);
  if (lg) {
    if (customRow) customRow.style.display = 'none';
    setLeagueImg(img, lg.logo);
  } else {
    if (customRow) customRow.style.display = 'block';
    setLeagueImg(img, state.customLeagueLogo);
  }
}

function findLogoForOpponent(name) {
  const val = String(name || '').trim().toLowerCase();
  if (!val || !state.availableLogos) return null;
  return state.availableLogos.find(l => {
    const team = (l.team || '').toLowerCase();
    const fn = (l.filename || '').toLowerCase();
    return team === val || team.startsWith(val) || fn.includes(val);
  }) || null;
}

function onOpponentNameInput() {
  const inp = document.getElementById('inpOpponentName');
  const selAway = document.getElementById('selAwayLogo');
  if (!inp || !selAway) return;
  const match = findLogoForOpponent(inp.value);
  if (match) {
    selAway.value = match.rel_path;
    onAwayLogoChange();
  }
}

function onAwayLogoChange() {
  const selAway = document.getElementById('selAwayLogo');
  const img = document.getElementById('awayLogoImg');
  const placeholder = document.getElementById('awayLogoPlaceholder');
  if (!selAway || !img || !placeholder) return;

  const val = selAway.value;
  if (val) {
    img.src = '/' + val.replace(/^\/+/, '');
    img.style.display = 'block';
    placeholder.style.display = 'none';
  } else {
    img.style.display = 'none';
    placeholder.style.display = 'inline-block';
  }
}

function triggerLogoUpload(target) {
  state.logoUploadTarget = target;
  if (target === 'home') {
    document.getElementById('fileUploadHomeLogo')?.click();
  } else if (target === 'away') {
    document.getElementById('fileUploadAwayLogo')?.click();
  } else if (target === 'league') {
    document.getElementById('fileUploadLeagueLogo')?.click();
  }
}

async function onLogoFileSelected(event, target) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/upload-logo', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (res.status === 200 && data.exists) {
      const ok = await showConfirm(data.message, 'Overwrite Logo', 'Overwrite', 'btn-danger');
      if (ok) {
        const fd2 = new FormData();
        fd2.append('file', file);
        fd2.append('overwrite', 'true');
        const res2 = await fetch('/api/upload-logo', { method: 'POST', body: fd2 });
        const d2 = await res2.json();
        if (res2.ok && d2.success) {
          applyUploadedLogo(target, d2.path, d2.filename);
        }
      }
    } else if (res.ok && data.success) {
      applyUploadedLogo(target, data.path, data.filename);
      showToast(`Uploaded ${data.filename}`, 'success');
    } else {
      showToast(data.message || 'Upload failed', 'error');
    }
  } catch (err) {
    showToast(`Upload error: ${err.message}`, 'error');
  } finally {
    event.target.value = '';
  }
}

function applyUploadedLogo(target, relPath, filename) {
  if (target === 'home' || target === 'away') {
    const sel = document.getElementById(target === 'home' ? 'selHomeLogo' : 'selAwayLogo');
    if (sel) {
      let opt = Array.from(sel.options).find(o => o.value === relPath);
      if (!opt) {
        opt = document.createElement('option');
        opt.value = relPath;
        opt.textContent = `${filename}`;
        sel.appendChild(opt);
      }
      sel.value = relPath;
      if (target === 'home') onHomeLogoChange();
      else onAwayLogoChange();
    }
  } else if (target === 'league') {
    state.customLeagueLogo = relPath;
    const img = document.getElementById('leagueLogoImg');
    if (img) img.src = `/${relPath.replace(/^\/+/, '')}`;
  }
}

async function submitGameInfo(e) {
  if (e) e.preventDefault();
  if (!state.currentGameId) return;

  const wl = readWizardLeague();
  const leagueName = wl.name;
  const leagueLogo = wl.logo;

  const matchName = (document.getElementById('inpMatchName')?.value || '').trim();
  const home = (document.getElementById('inpHomeName')?.value || cfgDefaults().team_name).trim();
  const homeLogo = document.getElementById('selHomeLogo')?.value || cfgDefaults().team_logo || '';
  const opponent = (document.getElementById('inpOpponentName')?.value || '').trim();
  const awayLogo = document.getElementById('selAwayLogo')?.value || null;
  const score = (document.getElementById('inpFinalScore')?.value || '').trim();
  const halftimeScore = (document.getElementById('inpHalftimeScore')?.value || '').trim();
  const date = (document.getElementById('inpGameDate')?.value || '').trim();

  if (!home) {
    showToast('Home team name cannot be empty', 'warning');
    return;
  }
  if (!opponent) {
    showToast('Opponent team name cannot be empty', 'warning');
    return;
  }
  if (score && !/^\d+\s*-\s*\d+$/.test(score)) {
    showToast("Invalid final score format (use 'H-A', e.g. '3-1')", 'warning');
    return;
  }
  if (halftimeScore && !/^\d+\s*-\s*\d+$/.test(halftimeScore)) {
    showToast("Invalid halftime score format (use 'H-A', e.g. '1-0')", 'warning');
    return;
  }

  const payload = {
    league: leagueName,
    league_logo: leagueLogo,
    match_name: matchName,
    home: home,
    home_logo: homeLogo,
    date: date,
    opponent: opponent,
    away_logo: awayLogo,
    score: score,
    halftime_score: halftimeScore
  };

  const btnSave = document.getElementById('btnSaveGameInfo');
  if (btnSave) btnSave.disabled = true;

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/info`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.description || `HTTP ${res.status}`);
    }
    const data = await res.json();
    state.gameInfo = data.game_info || payload;
    applyInfoSaveResult(data);
    showToast('Game setup saved!', 'success');
    closeGameInfoModal();
  } catch (err) {
    console.error('Failed to save game setup:', err);
    showToast(`Error saving setup: ${err.message}`, 'error');
  } finally {
    if (btnSave) btnSave.disabled = false;
  }
}

// Expose functions to window
window.openGameInfoModal = openGameInfoModal;
window.closeGameInfoModal = closeGameInfoModal;
window.onHomeLogoChange = onHomeLogoChange;
window.onLeagueChoiceChange = onLeagueChoiceChange;
window.onOpponentNameInput = onOpponentNameInput;
window.onAwayLogoChange = onAwayLogoChange;
window.triggerLogoUpload = triggerLogoUpload;
window.onLogoFileSelected = onLogoFileSelected;
window.submitGameInfo = submitGameInfo;

async function generateCardsFromWizard() {
  if (!state.currentGameId) return;

  // First save current form data so make_reels has up-to-date game_info.json
  const wl = readWizardLeague();
  const leagueLogo = wl.logo;

  const matchName = (document.getElementById('inpMatchName')?.value || '').trim();
  const home = (document.getElementById('inpHomeName')?.value || cfgDefaults().team_name).trim();
  const homeLogo = document.getElementById('selHomeLogo')?.value || cfgDefaults().team_logo || '';
  const opponent = (document.getElementById('inpOpponentName')?.value || '').trim();
  const awayLogo = document.getElementById('selAwayLogo')?.value || null;
  const score = (document.getElementById('inpFinalScore')?.value || '').trim();
  const halftimeScore = (document.getElementById('inpHalftimeScore')?.value || '').trim();
  const date = (document.getElementById('inpGameDate')?.value || '').trim();

  if (!opponent) {
    showToast('Please enter an opponent team name first', 'warning');
    return;
  }

  const payload = {
    league: wl.name,
    league_logo: leagueLogo,
    match_name: matchName,
    home: home,
    home_logo: homeLogo,
    date: date,
    opponent: opponent,
    away_logo: awayLogo,
    score: score,
    halftime_score: halftimeScore
  };

  const btnCards = document.getElementById('btnWizardGenerateCards');
  if (btnCards) btnCards.disabled = true;

  try {
    // 1. Save game info
    const saveRes = await fetch(`/api/game/${state.currentGameId}/info`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!saveRes.ok) throw new Error(`Could not save game setup: HTTP ${saveRes.status}`);
    const saveData = await saveRes.json();
    state.gameInfo = saveData.game_info || payload;
    applyInfoSaveResult(saveData);

    // 2. Close wizard modal and open terminal log modal
    closeGameInfoModal();
    openLogModal(`🎦 Generating Title Cards: ${state.currentGameId}`);

    // 3. Trigger card generation
    const genRes = await fetch(`/api/game/${state.currentGameId}/cards`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    if (!genRes.ok) throw new Error(`Could not start card generation: HTTP ${genRes.status}`);
    const genData = await genRes.json();

    if (genData.task_id) {
      streamTaskLogs(genData.task_id, (exitCode, error) => {
        if (exitCode === 0) {
          showToast('Title cards (Intro, Half-time, Outro) generated successfully!', 'success');
        } else {
          showToast(`Title card generation failed (${error || 'exit ' + exitCode})`, 'error');
        }
      });
    }
  } catch (err) {
    console.error('Failed to generate cards:', err);
    showToast(`Error: ${err.message}`, 'error');
  } finally {
    if (btnCards) btnCards.disabled = false;
  }
}

window.generateCardsFromWizard = generateCardsFromWizard;

// Windows-style Application Menu Handlers
function toggleAppMenu(e) {
  if (e) e.stopPropagation();
  const dropdown = document.getElementById('appMenuDropdown');
  if (!dropdown) return;
  const isShown = dropdown.style.display !== 'none';
  dropdown.style.display = isShown ? 'none' : 'block';
}

function closeAppMenu() {
  const dropdown = document.getElementById('appMenuDropdown');
  if (dropdown) dropdown.style.display = 'none';
}

// Featured Player & Reels Handlers
async function openFeaturedPlayerModal() {
  if (!state.currentGameId) {
    showToast('Please select a game first', 'info');
    return;
  }

  const modal = document.getElementById('featuredPlayerModal');
  if (!modal) return;

  // Fetch roster if not already loaded
  if (!state.roster || state.roster.length === 0) {
    try {
      const res = await fetch('/api/roster');
      if (res.ok) {
        const data = await res.json();
        state.roster = data.roster || [];
      }
    } catch (err) {
      console.warn('Failed to fetch roster:', err);
    }
  }

  // Count clips per player in current game (skipped rows with assigned players are cut for player reels)
  const playerClipCounts = {};
  if (state.rows && state.rows.length > 0) {
    state.rows.forEach(r => {
      const pField = String(r.player || '').trim();
      if (!pField) return;
      if (isRowSkipped(r) && !pField) return;
      // Handle comma-separated player numbers e.g. "11, 7"
      const numbers = pField.split(/[,/ ]+/).map(s => s.trim()).filter(Boolean);
      numbers.forEach(no => {
        playerClipCounts[no] = (playerClipCounts[no] || 0) + 1;
      });
    });
  }

  const tbody = document.getElementById('rosterTableBody');
  if (tbody) {
    tbody.innerHTML = '';
    const rosterList = state.roster || [];

    // Sort numerically by jersey number (excluding any empty/unassigned rows)
    const validRoster = rosterList.filter(p => p && p.no && String(p.no).trim());
    const sorted = [...validRoster].sort((a, b) => (parseInt(a.no, 10) || 0) - (parseInt(b.no, 10) || 0));

    sorted.forEach(p => {
      const tr = document.createElement('tr');
      const clipCount = playerClipCounts[p.no] || 0;
      const isZero = (clipCount === 0);

      const selectedList = state.featuredPlayers || defaultFeatured();
      const isSelected = selectedList.includes(String(p.no));

      if (isSelected && !isZero) tr.className = 'roster-row-selected';
      if (isZero) tr.style.opacity = '0.55';

      const countBadge = isZero
        ? `<span class="badge-clips-zero">0 clips - skipped</span>`
        : `<span class="badge-clips">${clipCount} clip${clipCount === 1 ? '' : 's'}</span>`;

      tr.innerHTML = `
        <td style="text-align: center;">
          <input type="checkbox" name="featuredPlayerCheck" value="${escapeSafe(p.no)}" ${isSelected && !isZero ? 'checked' : ''} ${isZero ? 'disabled' : ''} onchange="onFeaturedPlayerCheckboxChange(this)" onclick="event.stopPropagation();">
        </td>
        <td style="text-align: center;"><span class="roster-no-badge">#${escapeSafe(p.no)}</span></td>
        <td><strong>${escapeSafe(p.name)}</strong></td>
        <td>${escapeSafe(p.short_name || '')}</td>
        <td style="text-align: right;">${countBadge}</td>
      `;

      if (!isZero) {
        tr.onclick = () => toggleFeaturedPlayerRow(p.no);
      }
      tbody.appendChild(tr);
    });
  }

  modal.style.display = 'flex';
}

function closeFeaturedPlayerModal() {
  const modal = document.getElementById('featuredPlayerModal');
  if (modal) modal.style.display = 'none';
}

function onFeaturedPlayerCheckboxChange(cb) {
  const tr = cb.closest('tr');
  if (tr && !cb.disabled) {
    if (cb.checked) {
      tr.classList.add('roster-row-selected');
    } else {
      tr.classList.remove('roster-row-selected');
    }
  }
  const checkedBoxes = Array.from(document.querySelectorAll('input[name="featuredPlayerCheck"]:checked'));
  state.featuredPlayers = checkedBoxes.map(b => b.value);
}

function toggleFeaturedPlayerRow(no) {
  const cb = document.querySelector(`input[name="featuredPlayerCheck"][value="${no}"]`);
  if (cb && !cb.disabled) {
    cb.checked = !cb.checked;
    onFeaturedPlayerCheckboxChange(cb);
  }
}

function toggleFeaturedPlayerCheck(no) {
  toggleFeaturedPlayerRow(no);
}

async function submitFeaturedPlayerReels() {
  if (!state.currentGameId) return;

  const checkedBoxes = Array.from(document.querySelectorAll('input[name="featuredPlayerCheck"]:checked'));
  let selectedPlayers = checkedBoxes.map(cb => cb.value);
  if (selectedPlayers.length === 0) {
    selectedPlayers = defaultFeatured();
  }
  state.featuredPlayers = selectedPlayers;
  const playersArg = selectedPlayers.join(',');

  const stageChoice = document.querySelector('input[name="reelStageChoice"]:checked')?.value || 'all';

  // Format description
  const playerNames = selectedPlayers.map(no => {
    const pObj = (state.roster || []).find(p => String(p.no) === String(no));
    return pObj ? `${pObj.name} (#${no})` : `#${no}`;
  }).join(', ');

  closeFeaturedPlayerModal();
  openLogModal(`🎬 Generating Highlight Reels: ${state.currentGameId} (Players: ${playerNames})`);

  const btnSubmit = document.getElementById('btnSubmitGenerateReels');
  if (btnSubmit) btnSubmit.disabled = true;

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/reels`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        player: playersArg,
        stage: stageChoice
      })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.task_id) {
      streamTaskLogs(data.task_id, (exitCode, error) => {
        if (exitCode === 0) {
          showToast(`Highlight reels for ${playerNames} generated successfully!`, 'success');
        } else {
          showToast(`Reel generation exited with code ${exitCode}${error ? ': ' + error : ''}`, 'error');
        }
      });
    }
  } catch (err) {
    console.error('Failed to launch reel generation:', err);
    showToast(`Error: ${err.message}`, 'error');
  } finally {
    if (btnSubmit) btnSubmit.disabled = false;
  }
}

// Expose menu & featured player functions
window.toggleAppMenu = toggleAppMenu;
window.closeAppMenu = closeAppMenu;
window.openFeaturedPlayerModal = openFeaturedPlayerModal;
window.closeFeaturedPlayerModal = closeFeaturedPlayerModal;
window.toggleFeaturedPlayerCheck = toggleFeaturedPlayerCheck;
window.submitFeaturedPlayerReels = submitFeaturedPlayerReels;

// Player Multi-Select Modal Functions
async function openPlayerSelectModal(rowIndex) {
  if (rowIndex === null || rowIndex === undefined || !state.rows[rowIndex]) return;
  state.playerSelectRowIndex = rowIndex;
  const row = state.rows[rowIndex];
  const modal = document.getElementById('playerSelectModal');
  if (!modal) return;

  const titleEl = document.getElementById('playerSelectTitle');
  if (titleEl) {
    const clipStr = row.clip ? `Clip ${row.clip}` : `Row ${rowIndex + 1}`;
    titleEl.textContent = `👤 Select Players (${clipStr})`;
  }

  const descEl = document.getElementById('playerSelectDesc');
  if (descEl) {
    descEl.textContent = `Assign players for row ${rowIndex + 1} (${escapeSafe(row.type || 'mark')} at ${escapeSafe(row.video_time || '--:--')}). Multiple players can be selected.`;
  }

  // Pre-parse existing players (e.g. "1,33" or "11, 1")
  const currentVal = (row.player || '').trim();
  const currentSelectedList = currentVal ? currentVal.split(/[,;\s]+/).map(s => s.trim()).filter(Boolean) : [];

  // Fetch roster if not already loaded
  if (!state.roster || state.roster.length === 0) {
    try {
      const res = await fetch('/api/roster');
      const data = await res.json();
      state.roster = data.roster || [];
    } catch (err) {
      console.warn('Failed to fetch roster:', err);
    }
  }

  renderPlayerSelectItems(currentSelectedList);
  updatePlayerSelectSummary();
  modal.style.display = 'flex';
}

function renderPlayerSelectItems(currentSelectedList) {
  const container = document.getElementById('playerSelectList');
  if (!container) return;

  const rosterList = [...(state.roster || [])].sort((a, b) => (parseInt(a.no, 10) || 0) - (parseInt(b.no, 10) || 0));

  if (rosterList.length === 0 && currentSelectedList.length === 0) {
    container.innerHTML = '<div style="padding: 18px; text-align: center; color: #475569; font-size: 13px;">No roster players found.<br><small style="color: #64748B;">You can manage the roster in Menu ▾ &gt; Team Roster</small></div>';
    return;
  }

  let html = rosterList.map(p => {
    const isChecked = currentSelectedList.includes(String(p.no));
    const shortName = p.short_name || (p.name ? p.name.split(' ')[0] : `Player ${p.no}`);
    const fullName = p.name && p.name !== shortName ? `(${p.name})` : '';
    return `
      <label class="player-select-row ${isChecked ? 'selected' : ''}">
        <input type="checkbox" class="player-select-cb" value="${escapeSafe(p.no)}" ${isChecked ? 'checked' : ''} onchange="onPlayerSelectCheckboxChange(this)">
        <span class="roster-no-badge">#${escapeSafe(p.no)}</span>
        <span class="player-select-name">${escapeSafe(shortName)}</span>
        ${fullName ? `<span class="player-select-fullname">${escapeSafe(fullName)}</span>` : ''}
      </label>
    `;
  }).join('');

  // Include any custom or unlisted tokens present in current selection (e.g. "op" or unlisted number)
  const knownNos = new Set(rosterList.map(p => String(p.no)));
  const customItems = currentSelectedList.filter(tok => !knownNos.has(tok));
  if (customItems.length > 0) {
    html += customItems.map(tok => `
      <label class="player-select-row selected">
        <input type="checkbox" class="player-select-cb" value="${escapeSafe(tok)}" checked onchange="onPlayerSelectCheckboxChange(this)">
        <span class="roster-no-badge" style="background: #334155; color: #FFFFFF;">#${escapeSafe(tok)}</span>
        <span class="player-select-name">${escapeSafe(tok)}</span>
        <span class="player-select-fullname">(custom)</span>
      </label>
    `).join('');
  }

  container.innerHTML = html;
}

function onPlayerSelectCheckboxChange(cb) {
  const row = cb.closest('.player-select-row');
  if (row) {
    if (cb.checked) {
      row.classList.add('selected');
    } else {
      row.classList.remove('selected');
    }
  }
  updatePlayerSelectSummary();
}

function updatePlayerSelectSummary() {
  const cbs = Array.from(document.querySelectorAll('.player-select-cb:checked'));
  const vals = cbs.map(c => c.value);
  const summaryEl = document.getElementById('playerSelectSummary');
  if (summaryEl) {
    summaryEl.textContent = vals.length ? `Selected (${vals.length}): ${vals.join(', ')}` : 'Selected: none';
  }
}

function clearPlayerSelectAll() {
  document.querySelectorAll('.player-select-cb').forEach(cb => {
    cb.checked = false;
    const row = cb.closest('.player-select-row');
    if (row) row.classList.remove('selected');
  });
  updatePlayerSelectSummary();
}

function savePlayerSelect() {
  if (state.playerSelectRowIndex === null || state.playerSelectRowIndex === undefined) return;
  const rowIndex = state.playerSelectRowIndex;
  const row = state.rows[rowIndex];
  if (!row) {
    closePlayerSelectModal();
    return;
  }

  const cbs = Array.from(document.querySelectorAll('.player-select-cb:checked'));
  const selectedNos = cbs.map(c => c.value);
  const newVal = selectedNos.join(',');

  if ((row.player || '') !== newVal) {
    recordHistory();
    row.player = newVal;
    setDirty(true);
    updateInspector();
    renderTable();
    showToast(`Player updated to "${newVal || '(none)'}"`, 'success');
  }

  closePlayerSelectModal();
}

function closePlayerSelectModal() {
  const modal = document.getElementById('playerSelectModal');
  if (modal) modal.style.display = 'none';
  state.playerSelectRowIndex = null;
}

window.openPlayerSelectModal = openPlayerSelectModal;
window.closePlayerSelectModal = closePlayerSelectModal;
window.savePlayerSelect = savePlayerSelect;
window.clearPlayerSelectAll = clearPlayerSelectAll;
window.onPlayerSelectCheckboxChange = onPlayerSelectCheckboxChange;

// Final 4K Production Handlers
let productionPollInterval = null;

async function openFinalProductionModal() {
  if (!state.currentGameId) {
    showToast('Please select a game first', 'info');
    return;
  }

  const modal = document.getElementById('finalProductionModal');
  if (!modal) return;
  modal.style.display = 'flex';

  // Clear any residual status from previously opened game
  const statusWrap = document.getElementById('productionStatusWrap');
  const liveStatus = document.getElementById('productionLiveStatus');
  const logTail = document.getElementById('productionLogTail');
  const lastNote = document.getElementById('productionLastRunNote');
  if (statusWrap) statusWrap.style.display = 'none';
  if (liveStatus) {
    liveStatus.textContent = 'Status: Idle';
    liveStatus.style.color = '#1D4ED8';
  }
  if (lastNote) lastNote.style.display = 'none';
  if (logTail) logTail.textContent = '';

  await refreshProductionPreflight();
}

function closeFinalProductionModal() {
  const modal = document.getElementById('finalProductionModal');
  if (modal) modal.style.display = 'none';
  if (productionPollInterval) {
    clearInterval(productionPollInterval);
    productionPollInterval = null;
  }
}

function openUntidyFromProduction() {
  closeFinalProductionModal();
  openOrganizeModal();
  toggleUntidyMode();
}
window.openUntidyFromProduction = openUntidyFromProduction;

async function refreshProductionPreflight() {
  const listEl = document.getElementById('preflightChecksList');
  const btnStart = document.getElementById('btnStartProduction');
  const batInfo = document.getElementById('batFileInfo');
  const batBox = document.getElementById('batCommandBox');
  const batCmd = document.getElementById('batCommandPre');
  const estBox = document.getElementById('productionEstimateBox');
  const inpConfirm = document.getElementById('inpProductionConfirm');

  // Show the placeholder only on the first load; later refreshes (after Generate .bat, run status) keep the
  // current list on screen until the new one arrives, so the modal does not collapse and re-expand.
  if (listEl && !listEl.children.length) {
    listEl.innerHTML = '<div class="preflight-loading" style="color: #475569; font-size: 13px;">Checking game readiness...</div>';
  }

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/production/preflight`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // Tidied (archived) game: there is nothing to produce, so hide the checks, batch script, START box, log and
    // Start button and show only the explanation with an Untidy button.
    const tidiedPanel = document.getElementById('productionTidiedPanel');
    const hideWhenTidied = [
      document.querySelector('#finalProductionModal .preflight-section'),
      document.getElementById('productionStaleAlert'),
      document.querySelector('#finalProductionModal .production-batch-card'),
      document.querySelector('#finalProductionModal .production-warning-box'),
      document.getElementById('productionConfirmBox'),
      document.getElementById('productionStatusWrap'),
      btnStart,
    ];
    if (data.tidied) {
      if (tidiedPanel) tidiedPanel.style.display = 'block';
      hideWhenTidied.forEach(el => { if (el) el.style.display = 'none'; });
      state.productionPreflightPassed = false;
      return;
    }
    if (tidiedPanel) tidiedPanel.style.display = 'none';
    [hideWhenTidied[0], hideWhenTidied[2], hideWhenTidied[3], hideWhenTidied[4], hideWhenTidied[6]].forEach(el => { if (el) el.style.display = ''; });

    if (listEl) {
      listEl.innerHTML = '';
      const checks = data.checks || {};
      const order = ['game_info', 'roster', 'cards', 'zoom', 'timings', 'disk_space'];
      order.forEach(k => {
        const c = checks[k];
        if (!c) return;
        const item = document.createElement('div');
        item.className = 'preflight-item';
        item.innerHTML = `
          <div class="preflight-item-left">
            <span class="preflight-icon">${c.ok ? '✅' : '⚠️'}</span>
            <div>
              <div class="preflight-label">${escapeSafe(c.label)}</div>
              <div class="preflight-details">${escapeSafe(c.details)}</div>
            </div>
          </div>
          <span class="preflight-status-badge ${c.ok ? 'status-badge-ok' : 'status-badge-fail'}">
            ${c.ok ? 'PASSED' : 'REQUIRED'}
          </span>
        `;
        listEl.appendChild(item);
      });
    }

    if (estBox && data.estimates) {
      estBox.innerHTML = `⏱️ <strong>Estimated Run Time:</strong> ${escapeSafe(data.estimates.est_label)} (${data.estimates.clip_count} clips, ${data.estimates.zoom_count} replays)`;
    }

    // Staleness alert
    const staleAlert = document.getElementById('productionStaleAlert');
    const staleDesc = document.getElementById('productionStaleDesc');
    const staleList = document.getElementById('productionStaleClipsList');
    if (staleAlert && data.staleness) {
      if (data.staleness.is_stale) {
        staleAlert.style.display = 'block';
        const stClips = data.staleness.stale_replays || [];
        if (staleDesc) {
          const estMin = data.staleness.est_rebuild_minutes || 5;
          staleDesc.textContent = `${stClips.length} 4K replay${stClips.length === 1 ? '' : 's'} and highlight reels are out of date because replay window or crop settings were modified after the last production run. Rebuild estimate: ~${estMin} min (${stClips.length} replays + highlight reels).`;
        }
        if (staleList) {
          const clipLabels = stClips.map(c => `Clip ${c.n} (${c.token}): ${c.reason}`).join(' • ');
          staleList.textContent = clipLabels;
        }
      } else {
        staleAlert.style.display = 'none';
      }
    }

    if (data.bat && data.bat.exists) {
      const shName = data.bat.filename.replace('.bat', '.sh');
      if (batInfo) {
        batInfo.style.display = 'block';
        batInfo.innerHTML = `📜 Run scripts ready: <code>${escapeSafe(data.bat.filename)}</code> & <code>${escapeSafe(shName)}</code>`;
      }
      if (batBox) batBox.style.display = 'block';
      if (batCmd) {
        batCmd.textContent = (navigator.platform && navigator.platform.toLowerCase().includes('win'))
          ? `cmd.exe /c "${data.bat.path}"`
          : `./${shName}`;
      }
    } else {
      if (batInfo) {
        batInfo.textContent = '';
        batInfo.style.display = 'none';
      }
      if (batBox) batBox.style.display = 'none';
    }

    state.productionPreflightPassed = Boolean(data.all_passed);
    const isStartTyped = Boolean(inpConfirm && !inpConfirm.readOnly && inpConfirm.value.trim().toUpperCase() === 'START');
    if (btnStart) {
      btnStart.disabled = !(state.productionPreflightPassed && isStartTyped);
    }

    // Check status of production task or log
    await checkProductionStatus();
  } catch (err) {
    console.error('Failed to run production preflight:', err);
    if (listEl) {
      listEl.innerHTML = `<div style="color: #F87171; font-size: 13px;">Failed to load preflight checks: ${escapeSafe(err.message)}</div>`;
    }
  }
}

function onProductionConfirmInput() {
  const inpConfirm = document.getElementById('inpProductionConfirm');
  const btnStart = document.getElementById('btnStartProduction');
  const hint = document.getElementById('productionConfirmHint');
  const isStartTyped = Boolean(inpConfirm && !inpConfirm.readOnly && inpConfirm.value.trim().toUpperCase() === 'START');
  if (btnStart) {
    btnStart.disabled = !(state.productionPreflightPassed && isStartTyped);
  }
  if (hint) {
    if (isStartTyped && state.productionPreflightPassed) {
      hint.textContent = '✅ Confirmed! Click Start 4K Production below (or press Enter)';
      hint.style.color = '#15803D';
      hint.style.fontWeight = '600';
    } else {
      hint.textContent = 'Required confirmation for multi-hour 4K run';
      hint.style.color = '#475569';
      hint.style.fontWeight = 'normal';
    }
  }
}
window.onProductionConfirmInput = onProductionConfirmInput;

function resetProductionConfirm() {
  // Typed START is single-use: clear it and re-lock the Start button.
  const inp = document.getElementById('inpProductionConfirm');
  if (inp) { inp.value = ''; inp.readOnly = false; }
  onProductionConfirmInput();
}

// While a run is going the typed START stays visible (read-only) so the dialog shows "this was started";
// it is cleared when the run has completed, failed or been cancelled.
function syncProductionConfirmLock(running) {
  const inp = document.getElementById('inpProductionConfirm');
  const btnStart = document.getElementById('btnStartProduction');
  if (!inp) return;
  if (running) {
    inp.value = 'START';
    inp.readOnly = true;
    if (btnStart) btnStart.disabled = true;
  } else if (inp.readOnly) {
    resetProductionConfirm();
  }
}
window.resetProductionConfirm = resetProductionConfirm;

async function generateProductionScripts() {
  if (!state.currentGameId) return;
  const btn = document.getElementById('btnGenerateScripts') || document.getElementById('btnGenerateBat');
  const origText = btn ? btn.textContent : '⚙️ Generate scripts for manual run';
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Generating scripts...';
  }

  try {
    const playersArg = (state.featuredPlayers || defaultFeatured()).join(',');
    const res = await fetch(`/api/game/${state.currentGameId}/production/generate-bat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player: playersArg })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || `HTTP ${res.status}`);
    }

    const data = await res.json();
    const batRel = data.bat_rel || data.bat_path || '';
    showToast(`Generated scripts: ${batRel} (.bat / .sh)`, 'success');
    if (btn) {
      btn.textContent = '✅ Generated!';
      setTimeout(() => { if (btn) btn.textContent = origText; }, 3500);
    }
    await refreshProductionPreflight();
  } catch (err) {
    console.error('Failed to generate production scripts:', err);
    showToast(`Error generating scripts: ${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}
window.generateProductionScripts = generateProductionScripts;
window.generateProductionBat = generateProductionScripts;

async function dryRunProductionBat() {
  if (!state.currentGameId) return;
  const statusWrap = document.getElementById('productionStatusWrap');
  const liveStatus = document.getElementById('productionLiveStatus');
  const logTail = document.getElementById('productionLogTail');

  try {
    const playersArg = (state.featuredPlayers || defaultFeatured()).join(',');
    const res = await fetch(`/api/game/${state.currentGameId}/production/dry-run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player: playersArg })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (statusWrap) statusWrap.style.display = 'block';
    if (liveStatus) {
      liveStatus.textContent = 'Status: DRY-RUN PLANNED COMMANDS';
      liveStatus.style.color = '#F59E0B';
    }
    if (logTail) {
      logTail.textContent = data.output || 'No output from dry run';
      logTail.scrollTop = 0;
    }
    showToast('Dry run generated: inspected planned steps below.', 'info');
  } catch (err) {
    showToast(`Dry run error: ${err.message}`, 'error');
  }
}
window.dryRunProductionBat = dryRunProductionBat;

async function checkProductionStatus() {
  if (!state.currentGameId) return;
  const statusWrap = document.getElementById('productionStatusWrap');
  const liveStatus = document.getElementById('productionLiveStatus');
  const logTail = document.getElementById('productionLogTail');
  const btnCancel = document.getElementById('btnCancelProduction');
  const lockBanner = document.getElementById('productionLockBanner');
  const lblLockPid = document.getElementById('lblLockPid');
  const recutBtn = document.getElementById('recutBtn');

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/production/status`);
    if (!res.ok) return;
    const data = await res.json();
    syncProductionConfirmLock(data.status === 'running');

    if (data.status === 'running') {
      if (btnCancel) btnCancel.style.display = 'inline-block';
      if (lockBanner) {
        lockBanner.style.display = 'block';
        if (lblLockPid) lblLockPid.textContent = data.pid || '--';
      }
      if (recutBtn) {
        recutBtn.disabled = true;
        recutBtn.title = 'Re-cutting locked while production is running';
      }
    } else {
      if (btnCancel) btnCancel.style.display = 'none';
      if (lockBanner) lockBanner.style.display = 'none';
      if (recutBtn) {
        recutBtn.disabled = false;
        recutBtn.title = 'Fast (720) re-cut of changed clips and preview reel without touching Google Sheet';
      }
    }

    if (data.status !== 'idle' || (data.lines && data.lines.length > 0)) {
      if (statusWrap) statusWrap.style.display = 'block';
      const fmtTs = (t) => t ? new Date(t * 1000).toLocaleString([], { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
      const lastNote = document.getElementById('productionLastRunNote');
      if (liveStatus) {
        if (data.status === 'running') {
          liveStatus.textContent = `Status: RUNNING now (PID: ${data.pid || '--'})${data.started_ts ? `, started ${fmtTs(data.started_ts)}` : ''}`;
        } else {
          // Not running: this is the record of the PREVIOUS run, not a live status.
          const when = fmtTs(data.log_ts || data.started_ts);
          liveStatus.textContent = `Status from last run${when ? ` on ${when}` : ''}: ${data.status.toUpperCase()}`;
        }
        if (lastNote) {
          lastNote.style.display = data.status === 'running' ? 'none' : 'inline';
          lastNote.textContent = '(previous run - nothing is running now; the log below is from that run)';
        }
        liveStatus.style.color = (data.status === 'completed') ? '#72E098' : (data.status === 'failed' ? '#F87171' : (data.status === 'cancelled' ? '#F59E0B' : '#60A5FA'));
      }
      if (logTail) {
        logTail.textContent = (data.lines || []).slice(-15).join('\n');
        logTail.scrollTop = logTail.scrollHeight;
      }
    } else {
      if (statusWrap) statusWrap.style.display = 'none';
      if (liveStatus) {
        liveStatus.textContent = 'Status: Idle';
        liveStatus.style.color = '#1D4ED8';
      }
      if (logTail) logTail.textContent = '';
    }
  } catch (_) {}
}

async function cancelFinalProduction() {
  if (!state.currentGameId) return;
  const ok = await showConfirm('Cancel running 4K Final Production batch process?', 'Cancel Production', 'Yes, Cancel', 'btn-danger');
  if (!ok) return;

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/production/cancel`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      showToast('Production cancelled.', 'info');
      resetProductionConfirm();
      await checkProductionStatus();
    } else {
      showToast(data.message || 'Failed to cancel production', 'error');
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
}
window.cancelFinalProduction = cancelFinalProduction;

async function startFinalProduction() {
  if (!state.currentGameId) return;

  const btnStart = document.getElementById('btnStartProduction');
  if (btnStart) btnStart.disabled = true;

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/production/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || `HTTP ${res.status}`);
    }

    const data = await res.json();
    showToast(`4K Final Production launched in console (PID: ${data.pid})!`, 'success');
    syncProductionConfirmLock(true);

    const statusWrap = document.getElementById('productionStatusWrap');
    if (statusWrap) statusWrap.style.display = 'block';

    if (productionPollInterval) clearInterval(productionPollInterval);
    productionPollInterval = setInterval(checkProductionStatus, 3000);
    await checkProductionStatus();
  } catch (err) {
    console.error('Failed to start production:', err);
    showToast(`Error: ${err.message}`, 'error');
    if (btnStart) btnStart.disabled = false;
  }
}

let productionLogModalPoll = null;

function viewProductionLog() {
  if (!state.currentGameId) return;
  openLogModal(`🚀 4K Final Production Log (${state.currentGameId})`);
  if (el.logModalCloseBtn) el.logModalCloseBtn.disabled = false;

  async function pollStatus() {
    if (!el.logModal || el.logModal.style.display === 'none') {
      if (productionLogModalPoll) {
        clearInterval(productionLogModalPoll);
        productionLogModalPoll = null;
      }
      return;
    }

    try {
      const res = await fetch(`/api/game/${state.currentGameId}/production/status`);
      if (!res.ok) return;
      const data = await res.json();
      const pre = document.getElementById('logModalPre');
      if (pre && data && data.lines) {
        const text = data.lines.join('\n');
        if (pre.textContent !== text) {
          const isAtBottom = pre.scrollHeight - pre.clientHeight <= pre.scrollTop + 60;
          pre.textContent = text;
          if (isAtBottom || !pre.dataset.userScrolled) {
            pre.scrollTop = pre.scrollHeight;
            pre.dataset.userScrolled = 'true';
          }
        }
      }
      if (el.logModalCloseBtn) el.logModalCloseBtn.disabled = false;
      if (el.logModalStatus && data) {
        const isRunning = data.status === 'running';
        const isSuccess = data.status === 'completed' || data.status === 'finished' || (data.lines && data.lines.some(l => l.trim() === 'ALL OK'));
        const isFailed = data.status === 'failed';
        const isCancelled = data.status === 'cancelled';
        if (isSuccess) {
          el.logModalStatus.className = 'log-status success';
          el.logModalStatus.textContent = '✔ Completed successfully (ALL OK)';
          if (productionLogModalPoll && !isRunning) {
            clearInterval(productionLogModalPoll);
            productionLogModalPoll = null;
          }
        } else if (isFailed) {
          el.logModalStatus.className = 'log-status error';
          el.logModalStatus.textContent = '✖ Failed';
          if (productionLogModalPoll && !isRunning) {
            clearInterval(productionLogModalPoll);
            productionLogModalPoll = null;
          }
        } else if (isCancelled) {
          el.logModalStatus.className = 'log-status error';
          el.logModalStatus.textContent = '⚠ Cancelled';
          if (productionLogModalPoll && !isRunning) {
            clearInterval(productionLogModalPoll);
            productionLogModalPoll = null;
          }
        } else if (isRunning) {
          el.logModalStatus.className = 'log-status';
          el.logModalStatus.textContent = `Running... (PID: ${data.pid || '--'})`;
        } else {
          el.logModalStatus.className = 'log-status';
          el.logModalStatus.textContent = data.status ? (data.status.charAt(0).toUpperCase() + data.status.slice(1)) : 'Idle';
        }
      }
    } catch (_) {
      if (el.logModalCloseBtn) el.logModalCloseBtn.disabled = false;
    }
  }

  // Poll immediately, then every 1.5s while the modal remains open
  pollStatus();
  if (productionLogModalPoll) clearInterval(productionLogModalPoll);
  productionLogModalPoll = setInterval(pollStatus, 1500);
}

async function rebuildStaleProduction() {
  if (!state.currentGameId) return;
  const btn = document.getElementById('btnRebuildStale');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Starting rebuild...';
  }

  try {
    const playersArg = (state.featuredPlayers || defaultFeatured()).join(',');
    const res = await fetch(`/api/game/${state.currentGameId}/production/rebuild-stale`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player: playersArg })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(`Rebuild failed: ${err.message || res.statusText}`, 'error');
      if (btn) {
        btn.disabled = false;
        btn.textContent = '⚡ Rebuild Changed 4K Replays & Reels';
      }
      return;
    }

    const data = await res.json();
    closeFinalProductionModal();
    showToast('Rebuilding changed 4K replays and highlight reels in background...', 'info', 5000);

    // Open docked streaming log modal
    openLogModal(data.task_id, `Rebuild Changed 4K Replays & Reels (${state.currentGameId})`);
  } catch (e) {
    console.error('Failed to trigger rebuild:', e);
    showToast(`Failed to trigger rebuild: ${e.message}`, 'error');
    if (btn) {
      btn.disabled = false;
      btn.textContent = '⚡ Rebuild Changed 4K Replays & Reels';
    }
  }
}

window.openFinalProductionModal = openFinalProductionModal;
window.closeFinalProductionModal = closeFinalProductionModal;
window.generateProductionBat = generateProductionBat;
window.startFinalProduction = startFinalProduction;
window.viewProductionLog = viewProductionLog;
window.rebuildStaleProduction = rebuildStaleProduction;

// Dismiss topmost active layer on Escape (flags menu -> confirm box -> modal -> menu dropdown)
function dismissTopmostLayer() {
  // 0. Flags dropdown menu (topmost ephemeral popup)
  if (closeFlagsDropdown()) {
    return true;
  }

  // 1. In-page confirmation dialogs (topmost priority)
  const confirmModal = document.getElementById('confirmModal');
  if (confirmModal && confirmModal.style.display !== 'none') {
    closeConfirmModal(false);
    return true;
  }

  const calendarConfirm = document.getElementById('calendarConfirmBox');
  if (calendarConfirm && calendarConfirm.style.display !== 'none') {
    cancelCalendarConfirm();
    return true;
  }

  // 2. Modals in priority order (child/nested dialogs first)
  const modals = [
    { id: 'playerSelectModal', close: closePlayerSelectModal },
    { id: 'mediaReviewModal', close: closeMediaReviewModal },
    { id: 'gameDefaultsModal', close: closeGameDefaultsModal },
    { id: 'rosterModal', close: closeRosterModal },
    { id: 'calendarModal', close: closeCalendarModal },
    { id: 'gameInfoModal', close: closeGameInfoModal },
    { id: 'finalProductionModal', close: closeFinalProductionModal },
    { id: 'featuredPlayerModal', close: closeFeaturedPlayerModal },
    { id: 'organizeModal', close: closeOrganizeModal },
    { id: 'logModal', close: closeLogModal }
  ];

  for (const m of modals) {
    const elModal = document.getElementById(m.id);
    if (elModal && (elModal.style.display === 'flex' || elModal.style.display === 'block')) {
      m.close();
      return true;
    }
  }

  // 3. Dropdowns
  const recutDrop = document.getElementById('recutDropdownMenu');
  if (recutDrop && recutDrop.style.display !== 'none') {
    closeRecutMenu();
    return true;
  }

  const menuDrop = document.getElementById('appMenuDropdown');
  if (menuDrop && menuDrop.style.display !== 'none') {
    closeAppMenu();
    return true;
  }

  return false;
}

window.dismissTopmostLayer = dismissTopmostLayer;

// Event Listeners and Keyboard Shortcuts
function setupEventListeners() {
  // Close menu dropdown or flags dropdown on outside click
  document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('appMenuDropdown');
    const btn = document.getElementById('btnAppMenu');
    if (dropdown && dropdown.style.display !== 'none') {
      if (!dropdown.contains(e.target) && !btn?.contains(e.target)) {
        closeAppMenu();
      }
    }
    const recutDrop = document.getElementById('recutDropdownMenu');
    const recutBtn = document.getElementById('recutBtn');
    if (recutDrop && recutDrop.style.display !== 'none') {
      if (!recutDrop.contains(e.target) && !recutBtn?.contains(e.target)) {
        closeRecutMenu();
      }
    }
    const flagsMenu = document.getElementById('flagsDropdownMenu');
    if (flagsMenu && flagsMenu.style.display !== 'none') {
      if (!flagsMenu.contains(e.target) && !e.target.closest('.flags-cell-wrapper')) {
        closeFlagsDropdown();
      }
    }
  });

  const mediaModal = document.getElementById('mediaReviewModal');
  if (mediaModal) {
    mediaModal.addEventListener('click', (e) => {
      if (e.target === mediaModal) closeMediaReviewModal();
    });
  }

  const rosterModal = document.getElementById('rosterModal');
  if (rosterModal) {
    rosterModal.addEventListener('click', (e) => {
      if (e.target === rosterModal) closeRosterModal();
    });
  }

  // Initialize draggable timeline
  setupDraggableTimeline();

  // Game Selector
  el.gameSelect.addEventListener('change', onGameSelectChange);

  // Video time update -> timeline playhead and clock
  el.mainVideo.addEventListener('timeupdate', () => {
    if (el.mainVideo.paused) {
      updatePlayheadPosition();
      if (el.videoCurrentTime) {
        el.videoCurrentTime.textContent = formatTimeFraction(el.mainVideo.currentTime);
      }
    }
  });

  el.mainVideo.addEventListener('seeked', () => {
    updatePlayheadPosition();
    if (el.videoCurrentTime) {
      el.videoCurrentTime.textContent = formatTimeFraction(el.mainVideo.currentTime);
    }
  });

  el.mainVideo.addEventListener('loadedmetadata', () => {
    updateTimelineZoomWindow();
    updatePlayheadPosition();
  });

  el.mainVideo.addEventListener('pause', () => {
    if (state.loopingAction) {
      stopActionLoop();
    }
    if (el.playPauseBtn) el.playPauseBtn.textContent = '▶ Play';
    stopPlayheadRaf();
  });

  el.mainVideo.addEventListener('play', () => {
    if (el.playPauseBtn) el.playPauseBtn.textContent = '❚❚ Pause';
    startPlayheadRaf();
  });

  // Strict Alt-modifier check: guards against latched/sticky Alt flags in Chromium after Alt-Tab
  function isStrictAltModifier(e) {
    if (!e.altKey) return false;
    if (e.ctrlKey || e.metaKey) return false;
    if (typeof e.getModifierState === 'function' && !e.getModifierState('Alt')) return false;
    return true;
  }

  // Global Keyboard Shortcuts
  window.addEventListener('keydown', (e) => {
    // Escape always closes topmost open layer (confirm box -> modal -> menu dropdown) even when typing in input
    if (e.key === 'Escape' || e.code === 'Escape') {
      const handled = dismissTopmostLayer();
      if (handled) {
        e.preventDefault();
        e.stopPropagation();
        if (document.activeElement && document.activeElement.blur) {
          document.activeElement.blur();
        }
        return;
      }
      if (typeof isVideoZoomed === 'function' && isVideoZoomed()) {
        e.preventDefault();
        resetVideoZoom();
        return;
      }
    }

    // If typing in an input field, do not hijack normal typing
    if (['input', 'textarea', 'select'].includes(e.target.tagName.toLowerCase())) {
      return;
    }

    // Media Review Modal keyboard navigation (P2)
    const mediaModalEl = document.getElementById('mediaReviewModal');
    if (mediaModalEl && (mediaModalEl.style.display === 'flex' || mediaModalEl.style.display === 'block')) {
      if (e.key === 'ArrowUp' || e.key === '[') {
        e.preventDefault();
        stepMediaFile(-1);
        return;
      }
      if (e.key === 'ArrowDown' || e.key === ']') {
        e.preventDefault();
        stepMediaFile(1);
        return;
      }
      if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        const vid = document.getElementById('mediaReviewVideo');
        if (vid) {
          if (vid.paused) vid.play();
          else vid.pause();
        }
        return;
      }
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        const vid = document.getElementById('mediaReviewVideo');
        if (vid) vid.currentTime = Math.max(0, vid.currentTime - (e.shiftKey ? 10 : 5));
        return;
      }
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        const vid = document.getElementById('mediaReviewVideo');
        if (vid) vid.currentTime = Math.min(vid.duration || 86400, vid.currentTime + (e.shiftKey ? 10 : 5));
        return;
      }
    }

    if (e.key === ' ' || e.code === 'Space') {
      e.preventDefault();
      togglePlayPause();
    } else if (e.altKey && (e.key === '1' || e.code === 'Digit1') && isStrictAltModifier(e)) {
      e.preventDefault();
      setTimeFromPlayhead('action_start');
    } else if (e.altKey && (e.key === '2' || e.code === 'Digit2') && isStrictAltModifier(e)) {
      e.preventDefault();
      setTimeFromPlayhead('event');
    } else if (e.altKey && (e.key === '3' || e.code === 'Digit3') && isStrictAltModifier(e)) {
      e.preventDefault();
      setTimeFromPlayhead('action_end');
    } else if (e.key.toLowerCase() === 'x') {
      e.preventDefault();
      toggleSkipCurrentRow();
    } else if (e.key.toLowerCase() === 'z' && !e.ctrlKey) {
      e.preventDefault();
      toggleZoomCurrentRow();
    } else if (e.key.toLowerCase() === 'f' && !e.ctrlKey) {
      e.preventDefault();
      toggleTimelineZoom();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const newIdx = Math.max(0, state.selectedRowIndex - 1);
      selectRow(newIdx);
      if (state.autoPlayOnSelect) startActionLoop(newIdx);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      const newIdx = Math.min(state.rows.length - 1, state.selectedRowIndex + 1);
      selectRow(newIdx);
      if (state.autoPlayOnSelect) startActionLoop(newIdx);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      stepTime(e.shiftKey ? -5 : -1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      stepTime(e.shiftKey ? 5 : 1);
    } else if (e.key === ',') {
      e.preventDefault();
      stepFrame(-1);
    } else if (e.key === '.') {
      e.preventDefault();
      stepFrame(1);
    } else if (e.ctrlKey && e.key.toLowerCase() === 's') {
      e.preventDefault();
      save();
    } else if (e.ctrlKey && e.key.toLowerCase() === 'z') {
      e.preventDefault();
      undo();
    } else if (e.ctrlKey && e.key === 'Enter') {
      e.preventDefault();
      toggleActionLoop();
    } else if (e.key === 'Insert') {
      e.preventDefault();
      insertRowAtPlayhead();
    } else if (e.key === '0' && typeof isVideoZoomed === 'function' && isVideoZoomed()) {
      e.preventDefault();
      resetVideoZoom();
    }
  });
}

// --- Tidy / Organize Output Folder Modal ---
let organizeAction = 'tidy';  // 'tidy' or 'untidy' (undo Tidy for this game)
function toggleUntidyMode() {
  organizeAction = organizeAction === 'untidy' ? 'tidy' : 'untidy';
  const b = document.getElementById('btnUntidyOrganize');
  if (b) b.textContent = organizeAction === 'untidy' ? '🧹 Back to Tidy' : '↩ Untidy...';
  const ap = document.getElementById('btnApplyOrganize');
  if (ap) ap.textContent = organizeAction === 'untidy' ? '↩ Apply Untidy' : '✅ Apply Moves';
  previewOrganizePlan();
}
window.toggleUntidyMode = toggleUntidyMode;

function openOrganizeModal() {
  organizeAction = 'tidy';
  const b0 = document.getElementById('btnUntidyOrganize'); if (b0) b0.textContent = '↩ Untidy...';
  const a0 = document.getElementById('btnApplyOrganize'); if (a0) a0.textContent = '✅ Apply Moves';
  if (!state.currentGameId) {
    showToast('No game loaded.', 'error');
    return;
  }
  const modal = document.getElementById('organizeModal');
  if (modal) modal.style.display = 'flex';
  previewOrganizePlan();
}
window.openOrganizeModal = openOrganizeModal;

function closeOrganizeModal() {
  const modal = document.getElementById('organizeModal');
  if (modal) modal.style.display = 'none';
}
window.closeOrganizeModal = closeOrganizeModal;

async function previewOrganizePlan() {
  if (!state.currentGameId) return;
  const pre = document.getElementById('organizePlanPre');
  const lbl = document.getElementById('organizeStatusLabel');
  const btnApply = document.getElementById('btnApplyOrganize');
  if (pre) pre.textContent = 'Scanning files and computing tidy plan...';
  if (lbl) {
    lbl.textContent = 'Plan Preview (Dry Run)';
    lbl.style.color = '#38BDF8';
  }
  if (btnApply) btnApply.disabled = true;

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/organize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ apply: false, action: organizeAction })
    });
    const data = await res.json();
    if (res.status === 409) {
      if (pre) pre.textContent = '⚠️ Output folder organization is locked while 4K production is actively running.';
      if (lbl) {
        lbl.textContent = 'Locked (Production Running)';
        lbl.style.color = '#F87171';
      }
      return;
    }
    if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
    if (pre) pre.textContent = data.output || 'No moves planned.';
    if (btnApply) btnApply.disabled = false;
  } catch (err) {
    console.error('Failed to preview organize plan:', err);
    if (pre) pre.textContent = `Error: ${err.message}`;
  }
}
window.previewOrganizePlan = previewOrganizePlan;

async function applyOrganizePlan() {
  if (!state.currentGameId) return;
  const pre = document.getElementById('organizePlanPre');
  const lbl = document.getElementById('organizeStatusLabel');
  const btnApply = document.getElementById('btnApplyOrganize');

  if (btnApply) {
    btnApply.disabled = true;
    btnApply.textContent = '⏳ Applying Moves...';
  }
  if (lbl) {
    lbl.textContent = 'Applying moves to final/, work/, _to_delete/...';
    lbl.style.color = '#F59E0B';
  }

  try {
    const res = await fetch(`/api/game/${state.currentGameId}/organize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ apply: true, action: organizeAction })
    });
    const data = await res.json();
    if (res.status === 409) {
      showToast('Action locked while production is running.', 'error');
      return;
    }
    if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);
    if (pre) pre.textContent = data.output || 'Moves applied successfully.';
    if (lbl) {
      lbl.textContent = '✅ Organization Complete';
      lbl.style.color = '#10B981';
    }
    showToast(organizeAction === 'untidy' ? 'Game folder restored (untidied). Final 4K can re-render it now.' : 'Output folder organized successfully!', 'success');
  } catch (err) {
    console.error('Failed to apply organize moves:', err);
    showToast(`Error: ${err.message}`, 'error');
  } finally {
    if (btnApply) {
      btnApply.disabled = false;
      btnApply.textContent = organizeAction === 'untidy' ? '↩ Apply Untidy' : '✅ Apply Moves';
    }
  }
}
window.applyOrganizePlan = applyOrganizePlan;

// --- Roster Editor Modal ---
let rosterEditorData = [];
let rosterOriginalData = [];

async function openRosterModal() {
  const modal = document.getElementById('rosterModal');
  if (!modal) return;
  modal.style.display = 'flex';
  const statusEl = document.getElementById('rosterSyncStatus');
  if (statusEl) {
    statusEl.textContent = 'Checking sync...';
    statusEl.style.background = 'rgba(56, 189, 248, 0.15)';
    statusEl.style.color = '#38BDF8';
    statusEl.style.borderColor = 'rgba(56, 189, 248, 0.3)';
  }
  await loadRosterEditorData(true);
}
window.openRosterModal = openRosterModal;

function closeRosterModal() {
  if (rosterOriginalData && Array.isArray(rosterOriginalData)) {
    rosterEditorData = JSON.parse(JSON.stringify(rosterOriginalData));
    state.roster = rosterEditorData;
  }
  const modal = document.getElementById('rosterModal');
  if (modal) modal.style.display = 'none';
}
window.closeRosterModal = closeRosterModal;

async function loadRosterEditorData(checkRemote = false) {
  const tbody = document.getElementById('rosterEditorTableBody');
  const countNote = document.getElementById('rosterPlayerCountNote');
  const dateEl = document.getElementById('rosterCacheDate');
  const statusEl = document.getElementById('rosterSyncStatus');

  if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 24px; color: #475569;">Loading roster...</td></tr>';

  try {
    const res = await fetch(`/api/roster?check_remote=${checkRemote ? '1' : '0'}`);
    const data = await res.json();
    rosterEditorData = (data.roster || []).map(r => ({
      no: String(r.no || ''),
      name: String(r.name || ''),
      short_name: String(r.short_name || ''),
      contact: String(r.contact || '')
    }));
    rosterOriginalData = JSON.parse(JSON.stringify(rosterEditorData));
    state.roster = rosterEditorData;

    if (dateEl) {
      dateEl.textContent = data.cached_at ? `Cached: ${data.cached_at}` : '';
    }

    if (statusEl) {
      if (data.is_in_sync === true) {
        statusEl.textContent = '✅ In sync with Google Sheet';
        statusEl.style.background = 'rgba(16, 185, 129, 0.15)';
        statusEl.style.color = '#10B981';
        statusEl.style.borderColor = 'rgba(16, 185, 129, 0.3)';
      } else if (data.is_in_sync === false) {
        statusEl.textContent = '⚠️ Google Sheet differs (pull available)';
        statusEl.style.background = 'rgba(245, 158, 11, 0.15)';
        statusEl.style.color = '#F59E0B';
        statusEl.style.borderColor = 'rgba(245, 158, 11, 0.3)';
      } else if (data.remote_available === false) {
        statusEl.textContent = '📁 Local cache loaded';
        statusEl.style.background = 'rgba(148, 163, 184, 0.15)';
        statusEl.style.color = '#94A3B8';
        statusEl.style.borderColor = 'rgba(148, 163, 184, 0.3)';
      }
    }

    renderRosterEditorRows();
  } catch (err) {
    console.error('Failed to load roster:', err);
    if (tbody) tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 20px; color: #F87171;">Failed to load roster: ${err.message}</td></tr>`;
  }
}
window.loadRosterEditorData = loadRosterEditorData;

function renderRosterEditorRows() {
  const tbody = document.getElementById('rosterEditorTableBody');
  const countNote = document.getElementById('rosterPlayerCountNote');
  if (!tbody) return;

  if (rosterEditorData.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; padding: 24px; color: #475569;">No players found. Click "➕ Add Player" or "⬇️ Pull from Google Sheet".</td></tr>';
    if (countNote) countNote.textContent = '0 players';
    return;
  }

  tbody.innerHTML = '';
  rosterEditorData.forEach((p, idx) => {
    const tr = document.createElement('tr');
    tr.dataset.idx = idx;
    tr.innerHTML = `
      <td style="text-align: center;">
        <input type="text" class="roster-cell-input roster-input-no" value="${escapeSafe(p.no)}" placeholder="#" style="text-align: center; font-weight: 700;" oninput="onRosterRowChanged(${idx}, 'no', this.value)">
      </td>
      <td>
        <input type="text" class="roster-cell-input roster-input-name" value="${escapeSafe(p.name)}" placeholder="Full Player Name" oninput="onRosterRowChanged(${idx}, 'name', this.value)">
      </td>
      <td>
        <input type="text" class="roster-cell-input roster-input-short" value="${escapeSafe(p.short_name)}" placeholder="Short Name" oninput="onRosterRowChanged(${idx}, 'short_name', this.value)">
      </td>
      <td>
        <input type="text" class="roster-cell-input roster-input-contact" value="${escapeSafe(p.contact)}" placeholder="parent@email.com" oninput="onRosterRowChanged(${idx}, 'contact', this.value)">
      </td>
      <td style="text-align: center;">
        <button type="button" class="roster-del-btn" onclick="deleteRosterRow(${idx})" title="Delete player">🗑️</button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  if (countNote) countNote.textContent = `${rosterEditorData.length} player${rosterEditorData.length === 1 ? '' : 's'}`;
}

function onRosterRowChanged(idx, field, value) {
  if (rosterEditorData[idx]) {
    rosterEditorData[idx][field] = value;
    if (field === 'name' && !rosterEditorData[idx].short_name && value.trim()) {
      rosterEditorData[idx].short_name = value.trim().split(/\s+/)[0];
      const tr = document.querySelector(`#rosterEditorTableBody tr[data-idx="${idx}"]`);
      if (tr) {
        const shortInput = tr.querySelector('.roster-input-short');
        if (shortInput && !shortInput.value) shortInput.value = rosterEditorData[idx].short_name;
      }
    }
  }
  const statusEl = document.getElementById('rosterSyncStatus');
  if (statusEl) {
    statusEl.textContent = '✏️ Unsaved edits';
    statusEl.style.background = 'rgba(245, 158, 11, 0.15)';
    statusEl.style.color = '#F59E0B';
    statusEl.style.borderColor = 'rgba(245, 158, 11, 0.3)';
  }
}
window.onRosterRowChanged = onRosterRowChanged;

function addRosterRow() {
  rosterEditorData.push({
    no: '',
    name: '',
    short_name: '',
    contact: ''
  });
  renderRosterEditorRows();
  setTimeout(() => {
    const tbody = document.getElementById('rosterEditorTableBody');
    if (tbody && tbody.lastElementChild) {
      const inputNo = tbody.lastElementChild.querySelector('.roster-input-no');
      if (inputNo) inputNo.focus();
    }
  }, 50);
  const statusEl = document.getElementById('rosterSyncStatus');
  if (statusEl) {
    statusEl.textContent = '✏️ Unsaved edits';
    statusEl.style.background = 'rgba(245, 158, 11, 0.15)';
    statusEl.style.color = '#F59E0B';
    statusEl.style.borderColor = 'rgba(245, 158, 11, 0.3)';
  }
}
window.addRosterRow = addRosterRow;

function deleteRosterRow(idx) {
  if (idx >= 0 && idx < rosterEditorData.length) {
    rosterEditorData.splice(idx, 1);
    renderRosterEditorRows();
    const statusEl = document.getElementById('rosterSyncStatus');
    if (statusEl) {
      statusEl.textContent = '✏️ Unsaved edits';
      statusEl.style.background = 'rgba(245, 158, 11, 0.15)';
      statusEl.style.color = '#F59E0B';
      statusEl.style.borderColor = 'rgba(245, 158, 11, 0.3)';
    }
  }
}
window.deleteRosterRow = deleteRosterRow;

async function pullRosterFromGoogle() {
  const btn = document.getElementById('btnPullRoster');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Pulling...';
  }
  try {
    const res = await fetch('/api/roster/pull', { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);

    rosterEditorData = (data.roster || []).map(r => ({
      no: String(r.no || ''),
      name: String(r.name || ''),
      short_name: String(r.short_name || ''),
      contact: String(r.contact || '')
    }));
    rosterOriginalData = JSON.parse(JSON.stringify(rosterEditorData));
    state.roster = rosterEditorData;

    renderRosterEditorRows();
    const statusEl = document.getElementById('rosterSyncStatus');
    if (statusEl) {
      statusEl.textContent = '✅ In sync with Google Sheet';
      statusEl.style.background = 'rgba(16, 185, 129, 0.15)';
      statusEl.style.color = '#10B981';
      statusEl.style.borderColor = 'rgba(16, 185, 129, 0.3)';
    }
    showToast(data.message || `Successfully pulled ${rosterEditorData.length} players from Google Sheet!`, 'success');
  } catch (err) {
    console.error('Failed to pull roster:', err);
    showToast(`Failed to pull roster from Google Sheet: ${err.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '⬇️ Pull from Google Sheet';
    }
  }
}
window.pullRosterFromGoogle = pullRosterFromGoogle;

async function saveRoster() {
  const btn = document.getElementById('btnSaveRoster');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Saving & Syncing...';
  }

  const cleanRows = rosterEditorData.filter(r => (r.no && r.no.trim()) || (r.name && r.name.trim()));

  for (const r of cleanRows) {
    if (!r.name || !r.name.trim()) {
      showToast(`Player #${r.no || '?'} is missing a name. Please enter a name or remove the row.`, 'warning');
      if (btn) {
        btn.disabled = false;
        btn.textContent = '💾 Save Roster';
      }
      return;
    }
  }

  try {
    const res = await fetch('/api/roster', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ roster: cleanRows })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.message || `HTTP ${res.status}`);

    rosterEditorData = (data.roster || []).map(r => ({
      no: String(r.no || ''),
      name: String(r.name || ''),
      short_name: String(r.short_name || ''),
      contact: String(r.contact || '')
    }));
    rosterOriginalData = JSON.parse(JSON.stringify(rosterEditorData));
    state.roster = rosterEditorData;

    showToast(data.message || 'Roster saved to disk and Google Sheet!', data.sheet_synced ? 'success' : 'warning');
    closeRosterModal();
  } catch (err) {
    console.error('Failed to save roster:', err);
    showToast(`Failed to save roster: ${err.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '💾 Save Roster';
    }
  }
}
window.saveRoster = saveRoster;

// Defaults Modal Handlers
let globalDefaults = null;

// Generic placeholders only; the server always sends the user's real config (config/game_defaults.json).
const GENERIC_DEFAULTS = {
  team_name: 'Home FC', is_home: true, team_logo: '',
  leagues: [{ name: 'League A', logo: '' }, { name: 'League B', logo: '' }],
  league: 'League A', league_logo: '', featured_players: ['7'], sheet_id: ''
};
function cfgDefaults() { return globalDefaults || GENERIC_DEFAULTS; }
function defaultFeatured() {
  const f = cfgDefaults().featured_players;
  return (Array.isArray(f) && f.length) ? f.map(String) : GENERIC_DEFAULTS.featured_players.slice();
}
function leagueList() {
  const l = cfgDefaults().leagues;
  return (Array.isArray(l) && l.length) ? l : GENERIC_DEFAULTS.leagues;
}
function leagueByName(name) {
  const n = String(name || '').trim().toLowerCase();
  return n ? (leagueList().find(l => String(l.name).toLowerCase() === n) || null) : null;
}
function defaultLeagueName() {
  const lg = leagueByName(cfgDefaults().league);
  return lg ? lg.name : leagueList()[0].name;
}
// Renders the league radio pills (configured leagues + "Other") into a container.
function renderLeaguePills(containerId, radioName, handler, selected) {
  const box = document.getElementById(containerId);
  if (!box) return;
  box.innerHTML = '';
  const items = leagueList().map(l => ({ value: l.name, label: l.label || l.name })).concat([{ value: 'Other', label: 'Other' }]);
  items.forEach(it => {
    const lab = document.createElement('label');
    lab.className = 'league-pill-opt';
    const inp = document.createElement('input');
    inp.type = 'radio'; inp.name = radioName; inp.value = it.value;
    inp.checked = (it.value === selected);
    inp.addEventListener('change', () => handler(it.value));
    const sp = document.createElement('span');
    sp.textContent = it.label;
    lab.appendChild(inp); lab.appendChild(sp);
    box.appendChild(lab);
  });
}
function setLeagueImg(img, path) {
  if (!img) return;
  if (path) { img.src = '/' + String(path).replace(/^\/+/, ''); img.style.display = ''; }
  else { img.removeAttribute('src'); img.style.display = 'none'; }
}
// Current league choice in the Game Setup wizard -> {name, logo}
function readWizardLeague() {
  const checked = document.querySelector('input[name="leagueChoice"]:checked');
  const val = checked ? checked.value : defaultLeagueName();
  const lg = leagueByName(val);
  if (lg) return { name: lg.name, logo: lg.logo || '' };
  return { name: (document.getElementById('inpCustomLeague')?.value || 'Other').trim(), logo: state.customLeagueLogo || '' };
}

async function loadGlobalDefaults() {
  try {
    const res = await fetch('/api/defaults');
    if (res.ok) {
      globalDefaults = await res.json();
      return globalDefaults;
    }
  } catch (err) {
    console.warn('Failed to fetch defaults:', err);
  }
  return null;
}

async function openGameDefaultsModal() {
  const modal = document.getElementById('gameDefaultsModal');
  if (!modal) return;

  const defs = await loadGlobalDefaults() || GENERIC_DEFAULTS;

  const inpTeam = document.getElementById('defTeamName');
  const chkHome = document.getElementById('defIsHome');
  const selTeamLogo = document.getElementById('defTeamLogo');
  const selLeagueLogo = document.getElementById('defLeagueLogo');
  const inpFps = document.getElementById('defFeaturedPlayers');
  const inpSid = document.getElementById('defSheetId');

  // Preload team name & home role
  if (inpTeam) inpTeam.value = defs.team_name || GENERIC_DEFAULTS.team_name;
  if (chkHome) chkHome.checked = (defs.is_home !== false);

  // Preload featured players
  if (inpFps) inpFps.value = Array.isArray(defs.featured_players) ? defs.featured_players.join(', ') : (defs.featured_players || defaultFeatured().join(', '));

  // Preload Google Sheet ID
  if (inpSid) inpSid.value = defs.sheet_id || '';

  // Preload default league radio pills (from config)
  const leagueVal = leagueByName(defs.league) ? leagueByName(defs.league).name : 'Other';
  renderLeaguePills('defLeaguePills', 'defLeagueChoice', onDefLeagueChange, leagueVal);

  // Populate logos dropdowns (Team Logo & League Logo) from /api/logos
  try {
    const res = await fetch('/api/logos');
    if (res.ok) {
      const data = await res.json();
      const logos = data.logos || [];

      // Team Logo Dropdown
      if (selTeamLogo) {
        selTeamLogo.innerHTML = '<option value="">(None / Text only)</option>';
        logos.forEach(item => {
          const opt = document.createElement('option');
          opt.value = item.rel_path;
          opt.textContent = `${item.team ? item.team + ' - ' : ''}${item.filename}`;
          selTeamLogo.appendChild(opt);
        });
        selTeamLogo.value = defs.team_logo || '';
      }

      // League Logo Dropdown
      if (selLeagueLogo) {
        selLeagueLogo.innerHTML = '<option value="">(None / Text only)</option>';
        logos.forEach(item => {
          const opt = document.createElement('option');
          opt.value = item.rel_path;
          opt.textContent = `${item.team ? item.team + ' - ' : ''}${item.filename}`;
          selLeagueLogo.appendChild(opt);
        });
        selLeagueLogo.value = defs.league_logo || '';
      }
    }
  } catch (err) {
    console.warn('Failed to load logos for defaults:', err);
  }

  updateDefLogoPreview();
  updateDefLeagueLogoPreview();
  modal.style.display = 'flex';
}

function closeGameDefaultsModal() {
  const modal = document.getElementById('gameDefaultsModal');
  if (modal) modal.style.display = 'none';
}

function updateDefLogoPreview() {
  const sel = document.getElementById('defTeamLogo');
  const preview = document.getElementById('defTeamLogoPreview');
  if (!sel || !preview) return;
  const val = sel.value;
  if (val) {
    preview.innerHTML = `<img src="/${val}" alt="Team Logo" style="max-width:100%; max-height:100%; object-fit:contain;">`;
  } else {
    preview.innerHTML = '<span style="font-size:10px; color:#475569;">None</span>';
  }
}

function updateDefLeagueLogoPreview() {
  const sel = document.getElementById('defLeagueLogo');
  const preview = document.getElementById('defLeagueLogoPreview');
  if (!sel || !preview) return;
  const val = sel.value;
  if (val) {
    preview.innerHTML = `<img src="/${val}" alt="League Logo" style="max-width:100%; max-height:100%; object-fit:contain;">`;
  } else {
    preview.innerHTML = '<span style="font-size:10px; color:#475569;">None</span>';
  }
}

function onDefLeagueChange(val) {
  const sel = document.getElementById('defLeagueLogo');
  if (!sel) return;
  const lg = leagueByName(val);
  if (lg && lg.logo) sel.value = lg.logo;
  updateDefLeagueLogoPreview();
}

async function submitGameDefaults(event) {
  if (event) event.preventDefault();

  const teamName = document.getElementById('defTeamName')?.value.trim() || GENERIC_DEFAULTS.team_name;
  const isHome = Boolean(document.getElementById('defIsHome')?.checked);
  const teamLogo = document.getElementById('defTeamLogo')?.value || '';
  const leagueChoice = document.querySelector('input[name="defLeagueChoice"]:checked')?.value || defaultLeagueName();
  const leagueLogo = document.getElementById('defLeagueLogo')?.value || '';
  const featuredInput = document.getElementById('defFeaturedPlayers')?.value || defaultFeatured().join(',');
  const sheetId = document.getElementById('defSheetId')?.value.trim() || '';

  const featuredList = featuredInput.split(/[,/ ]+/).map(s => s.trim()).filter(Boolean);

  const payload = {
    team_name: teamName,
    is_home: isHome,
    team_logo: teamLogo,
    league: leagueChoice,
    league_logo: leagueLogo,
    featured_players: featuredList.length ? featuredList : defaultFeatured(),
    sheet_id: sheetId
  };

  try {
    const res = await fetch('/api/defaults', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast(`Failed to save defaults: ${err.error || res.statusText}`, 'error');
      return;
    }

    const data = await res.json();
    globalDefaults = data.defaults || payload;
    showToast('Workflow defaults saved successfully!', 'success');
    closeGameDefaultsModal();

    // If game info modal is open, propagate new defaults
    const inpHome = document.getElementById('inpHomeName');
    if (inpHome && !inpHome.value) inpHome.value = teamName;
  } catch (err) {
    console.error('Error saving defaults:', err);
    showToast(`Error saving defaults: ${err.message}`, 'error');
  }
}

window.openGameDefaultsModal = openGameDefaultsModal;
window.closeGameDefaultsModal = closeGameDefaultsModal;
window.updateDefLogoPreview = updateDefLogoPreview;
window.updateDefLeagueLogoPreview = updateDefLeagueLogoPreview;
window.onDefLeagueChange = onDefLeagueChange;
window.submitGameDefaults = submitGameDefaults;

// Start
document.addEventListener('DOMContentLoaded', init);
