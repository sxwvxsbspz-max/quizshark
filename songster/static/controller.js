// Songster Controller – Hitster-Mechanik

const LS_RUN_ID_KEY    = "blitzquiz_run_id";
const LS_PLAYER_ID_KEY = "blitzquiz_player_id";

socket.emit('register_controller', {
  player_id: localStorage.getItem(LS_PLAYER_ID_KEY) || "",
  run_id:    localStorage.getItem(LS_RUN_ID_KEY) || ""
});
socket.on('connect', () => {
  socket.emit('register_controller', {
    player_id: localStorage.getItem(LS_PLAYER_ID_KEY) || "",
    run_id:    localStorage.getItem(LS_RUN_ID_KEY) || ""
  });
});

// ----------------------------------------------------------------
// DOM refs
// ----------------------------------------------------------------
const titleScreen   = document.getElementById("title-screen");
const roundScreen   = document.getElementById("round-screen");
const qaScreen      = document.getElementById("qa-screen");
const roundLabel    = document.getElementById("round-label");
const playerNameEl  = document.getElementById("player-name");
const playerScoreEl = document.getElementById("player-score");
const timebarFill   = document.getElementById("timebar-fill");
const ctrlTimeline  = document.getElementById("ctrl-timeline");
const confirmBtn    = document.getElementById("confirm-btn");

// ----------------------------------------------------------------
// State
// ----------------------------------------------------------------
let locked         = true;
let hasSubmitted   = false;
let currentSlot    = 0;
let playerTimeline = [];
let anchorYear     = null;
let myScorePop     = 0;
let lastYearRange  = null;
let yellowState    = 'playing';  // 'playing' | 'correct' | 'wrong'
let yellowReveal   = { year: null, title: null, artist: null };

// Timer
let timebarRAF  = null;
let clockOffset = 0;
function nowSyncedMs() { return Date.now() + clockOffset; }

socket.on('server_time', d => {
  if (d && typeof d.server_now === 'number') clockOffset = d.server_now - Date.now();
});

// ----------------------------------------------------------------
// Screens
// ----------------------------------------------------------------
function showTitle() {
  if (titleScreen) titleScreen.style.display = "flex";
  if (roundScreen) roundScreen.style.display = "none";
  if (qaScreen)    qaScreen.style.display    = "none";
}

function showRound(n) {
  if (roundLabel) roundLabel.textContent = `Track ${n}`;
  if (titleScreen) titleScreen.style.display = "none";
  if (roundScreen) roundScreen.style.display = "flex";
  if (qaScreen)    qaScreen.style.display    = "none";
}

function showQA() {
  if (titleScreen) titleScreen.style.display = "none";
  if (roundScreen) roundScreen.style.display = "none";
  if (qaScreen)    qaScreen.style.display    = "flex";
}

// ----------------------------------------------------------------
// Timer Bar
// ----------------------------------------------------------------
function parseMs(v) {
  if (v == null) return null;
  if (typeof v === 'number') return v > 1e12 ? v : v > 1e9 ? v * 1000 : v;
  if (typeof v === 'string') { const t = Date.parse(v); return isFinite(t) ? t : null; }
  return null;
}

function stopTimebar() {
  if (timebarRAF) { cancelAnimationFrame(timebarRAF); timebarRAF = null; }
  if (timebarFill) timebarFill.style.width = "0%";
}

function startTimebar(seconds, startedAt) {
  if (!timebarFill) return;
  stopTimebar();
  const durMs  = Math.max(1, Number(seconds || 1)) * 1000;
  const startMs = parseMs(startedAt);

  if (startMs !== null) {
    const endMs = startMs + durMs;
    const tick = () => {
      const now = nowSyncedMs();
      const pct = Math.min(100, Math.max(0, (now - startMs) / durMs * 100));
      timebarFill.style.width = `${pct}%`;
      if (now < endMs) timebarRAF = requestAnimationFrame(tick);
      else stopTimebar();
    };
    timebarRAF = requestAnimationFrame(tick);
    return;
  }

  const start = performance.now();
  const tick = now => {
    const pct = Math.min(100, (now - start) / durMs * 100);
    timebarFill.style.width = `${pct}%`;
    if (pct < 100) timebarRAF = requestAnimationFrame(tick);
    else stopTimebar();
  };
  timebarRAF = requestAnimationFrame(tick);
}

// ----------------------------------------------------------------
// Score header
// ----------------------------------------------------------------
function updateHeader(playersRanked, gainedMap, opts = {}) {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !playersRanked) return;
  const me = playersRanked.find(p => p.player_id === myId);
  if (!me) return;
  if (playerNameEl) playerNameEl.textContent = me.name || "—";
  const score = me.score ?? "—";
  const gained = gainedMap && Object.prototype.hasOwnProperty.call(gainedMap, myId)
    ? Number(gainedMap[myId] || 0) : 0;
  if (opts.forceClear) {
    myScorePop = 0;
    if (playerScoreEl) playerScoreEl.textContent = score;
    return;
  }
  if (gained > 0 || opts.forcePop) {
    if (gained > 0) myScorePop = gained;
    if (playerScoreEl) playerScoreEl.innerHTML =
      `<span class="psc__scorePopInline">+${myScorePop}</span><span>${score}</span>`;
  } else {
    myScorePop = 0;
    if (playerScoreEl) playerScoreEl.textContent = score;
  }
}

// ----------------------------------------------------------------
// Tile height auto-scaling
// ----------------------------------------------------------------
const BASE_TILE_H   = 33;       // matches --tileHOrig
const YELLOW_TILE_H = BASE_TILE_H * 1.5;
const MIN_TILE_H    = 18;
const TILE_GAP      = 4;        // matches --gap

function adjustTileHeight() {
  const area = document.querySelector('.sng-ctrl__area');
  if (!area) return;

  const nFixed  = playerTimeline.length;
  const nTotal  = nFixed + 1;   // +1 for yellow tile
  const gaps    = (nTotal - 1) * TILE_GAP;
  const availH  = area.clientHeight - 4; // 4 = padding-bottom

  let tileH = BASE_TILE_H;
  if (nFixed > 0) {
    const spaceForFixed = availH - YELLOW_TILE_H - gaps;
    const ideal = spaceForFixed / nFixed;
    tileH = Math.min(BASE_TILE_H, Math.max(MIN_TILE_H, ideal));
  }

  document.documentElement.style.setProperty('--tileH', `${tileH}px`);
}

// ----------------------------------------------------------------
// Timeline building
// ----------------------------------------------------------------

function buildEqSvg() {
  return `<svg class="sng-ctrl__eq" viewBox="0 0 130 26" aria-hidden="true">
    <rect class="bar" x="0"   y="0" width="18" height="26" rx="3"/>
    <rect class="bar" x="28"  y="0" width="18" height="26" rx="3"/>
    <rect class="bar" x="56"  y="0" width="18" height="26" rx="3"/>
    <rect class="bar" x="84"  y="0" width="18" height="26" rx="3"/>
    <rect class="bar" x="112" y="0" width="18" height="26" rx="3"/>
  </svg>`;
}

function buildYellowTileHTML() {
  const stateClassMap = {
    playing: 'sng-ctrl__currentTile--yellow',
    correct: 'sng-ctrl__currentTile--correct',
    wrong:   'sng-ctrl__currentTile--wrong'
  };

  const stateClass = stateClassMap[yellowState] || 'sng-ctrl__currentTile--yellow';
  const lockedCls = (locked && !hasSubmitted && yellowState === 'playing') ? ' sng-ctrl__currentTile--locked' : '';
  const submittedCls = (hasSubmitted && yellowState === 'playing')
    ? ' sng-ctrl__currentTile--submitted'
    : '';

  let contentHTML;

  if (yellowReveal.year != null) {
    const sep = (yellowReveal.artist && yellowReveal.title) ? ' — ' : '';
    contentHTML = `
      <div class="sng-ctrl__fixedYear">${yellowReveal.year}</div>
      <div class="sng-ctrl__fixedOneLine"><span class="sng-ctrl__tileArtist">${yellowReveal.artist || ''}</span>${sep}${yellowReveal.title || ''}</div>
    `;
  } else {
    contentHTML = `
      ${buildEqSvg()}
      <div class="sng-ctrl__fixedOneLine sng-ctrl__currentLabel">Aktueller Song</div>
    `;
  }

  const handle = (!locked && yellowReveal.year == null) ? `
    <div class="sng-ctrl__dragHandle" aria-hidden="true">
      <div class="sng-ctrl__handleDot"></div><div class="sng-ctrl__handleDot"></div>
      <div class="sng-ctrl__handleDot"></div><div class="sng-ctrl__handleDot"></div>
      <div class="sng-ctrl__handleDot"></div><div class="sng-ctrl__handleDot"></div>
    </div>
  ` : '';

  return `
    <div
      class="sng-ctrl__currentTile ${stateClass}${lockedCls}${submittedCls}"
      id="ctrl-yellow-tile"
    >
      ${contentHTML}
      ${handle}
    </div>
  `;
}

function buildFixedTileHTML(tile) {
  if (tile.is_anchor) {
    return `<div class="sng-ctrl__fixedTile sng-ctrl__fixedTile--anchor">
      <div class="sng-ctrl__fixedYear">${tile.year}</div>
      <div class="sng-ctrl__fixedLabel">Ausgangsjahr</div>
    </div>`;
  }
  const artistPart = tile.artist || '';
  const titlePart  = tile.title  || '';
  const sep        = (artistPart && titlePart) ? ' — ' : '';
  return `<div class="sng-ctrl__fixedTile">
    <div class="sng-ctrl__fixedYear">${tile.year}</div>
    <div class="sng-ctrl__fixedOneLine"><span class="sng-ctrl__tileArtist">${artistPart}</span>${sep}${titlePart}</div>
  </div>`;
}

function renderTimeline() {
  if (!ctrlTimeline) return;
  adjustTileHeight();

  const clampedSlot = Math.max(0, Math.min(playerTimeline.length, currentSlot));
  let html = '';

  playerTimeline.slice(0, clampedSlot).forEach(tile => {
    html += buildFixedTileHTML(tile);
  });

  html += buildYellowTileHTML();

  playerTimeline.slice(clampedSlot).forEach(tile => {
    html += buildFixedTileHTML(tile);
  });

  ctrlTimeline.innerHTML = html;

  const yellowEl = document.getElementById('ctrl-yellow-tile');
  if (yellowEl && !locked && !hasSubmitted) {
    yellowEl.addEventListener('touchstart', onDragStart, { passive: false });
    yellowEl.addEventListener('mousedown', onDragStart, { passive: false });
  }
}

// ----------------------------------------------------------------
// Drag – yellow tile moves physically to chosen slot
// ----------------------------------------------------------------

let isDragging    = false;
let dragStartY    = 0;
let dragStartSlot = 0;
let dragStep      = 70;

function onDragStart(e) {
  if (locked || hasSubmitted) return;
  e.preventDefault();
  isDragging    = true;
  dragStartSlot = currentSlot;

  const yellowEl = document.getElementById('ctrl-yellow-tile');
  const gapVal = parseInt(
    getComputedStyle(document.documentElement).getPropertyValue('--gap')
  ) || 8;
  dragStep = yellowEl ? yellowEl.getBoundingClientRect().height + gapVal : 70;

  const touch = e.touches ? e.touches[0] : e;
  dragStartY = touch.clientY;

  document.addEventListener('touchmove', onDragMove, { passive: false });
  document.addEventListener('touchend',  onDragEnd,  { once: true, passive: true });
  document.addEventListener('mousemove', onDragMove, { passive: false });
  document.addEventListener('mouseup',   onDragEnd,  { once: true, passive: true });
}

function onDragMove(e) {
  if (!isDragging) return;
  if (e.cancelable) e.preventDefault();

  const touch = e.touches ? e.touches[0] : e;
  const dy     = touch.clientY - dragStartY;
  const n      = playerTimeline.length;

  const rawY    = dragStartSlot * dragStep + dy;
  const clampY  = Math.max(0, Math.min(n * dragStep, rawY));
  const newSlot = Math.max(0, Math.min(n, Math.round(clampY / dragStep)));

  if (newSlot !== currentSlot) {
    currentSlot = newSlot;
    socket.emit('module_event', { action: 'update_draft', payload: { slot_index: currentSlot } });
    renderTimeline();
  }
}

function onDragEnd() {
  if (!isDragging) return;
  isDragging = false;
  document.removeEventListener('touchmove', onDragMove);
  document.removeEventListener('mousemove', onDragMove);

  socket.emit('module_event', { action: 'update_draft', payload: { slot_index: currentSlot } });
  renderTimeline();
}

// ----------------------------------------------------------------
// Submit
// ----------------------------------------------------------------

function submitPlacement() {
  if (locked || hasSubmitted) return;
  hasSubmitted = true;
  lockUI();

  const tl    = playerTimeline;
  const n     = tl.length;
  const years = tl.map(t => Number(t.year));
  let yr;
  if (n === 0)               yr = '?';
  else if (currentSlot <= 0) yr = `< ${years[0]}`;
  else if (currentSlot >= n) yr = `> ${years[n - 1]}`;
  else                       yr = `${years[currentSlot - 1]}–${years[currentSlot]}`;
  lastYearRange = yr;

  socket.emit('module_event', { action: 'submit_answer', payload: { slot_index: currentSlot } });
}

// ----------------------------------------------------------------
// Lock / Unlock
// ----------------------------------------------------------------

function lockUI() {
  locked = true;
  if (confirmBtn) confirmBtn.disabled = true;
  renderTimeline();
}

function unlockUI() {
  locked       = false;
  hasSubmitted = false;
  if (confirmBtn) confirmBtn.disabled = false;
  renderTimeline();
}

function resetRound() {
  currentSlot  = 0;
  lastYearRange = null;
  hasSubmitted  = false;
  yellowState   = 'playing';
  yellowReveal  = { year: null, title: null, artist: null };
  renderTimeline();
}

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  const playerId = localStorage.getItem(LS_PLAYER_ID_KEY);
  const runId    = localStorage.getItem(LS_RUN_ID_KEY);
  if (playerId) socket.emit('resume_player', { player_id: playerId, run_id: runId || '' });

  const area = document.querySelector('.sng-ctrl__area');
  if (area && typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(() => renderTimeline()).observe(area);
  }
});

showTitle();
lockUI();
stopTimebar();

if (confirmBtn) {
  confirmBtn.addEventListener('pointerup', e => {
    e.preventDefault();
    submitPlacement();
  });
}

// ----------------------------------------------------------------
// Socket Events
// ----------------------------------------------------------------

socket.on('play_round_video', data => {
  showRound(Number(data.round || 1));
  stopTimebar();
  lockUI();
  resetRound();
});

socket.on('show_question', data => {
  showQA();
  stopTimebar();

  anchorYear = data.anchor_year;
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  playerTimeline = (data.player_timelines || {})[myId] || [];

  updateHeader(data.players_ranked, null, { forceClear: true });
  resetRound();
  unlockUI();
});

socket.on('open_answers', data => {
  unlockUI();
  const startedAt = data && (data.started_at ?? data.startedAt);
  const dur = Number((data && (data.duration ?? data.total_duration)) || 28);
  startTimebar(dur, startedAt);
});

socket.on('close_answers', () => {
  lockUI();
  stopTimebar();
});

socket.on('reveal_player_answers', () => {
  stopTimebar();
});

socket.on('unveil_correct', data => {
  lockUI();
  stopTimebar();
  yellowReveal = {
    year:   data.correct_year,
    title:  data.title  || '',
    artist: data.artist || '',
  };
  renderTimeline();
});

socket.on('show_resolution', data => {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  const res  = (data.player_results || {})[myId];

  yellowState = res && res.correct ? 'correct' : 'wrong';

  renderTimeline();
});

socket.on('show_scoring', data => {
  updateHeader(data.players_ranked, data.gained || {}, { forcePop: true });
  stopTimebar();
});

socket.on('apply_scoring_update', data => {
  updateHeader(data.players_ranked, null, { forceClear: true });
  stopTimebar();
});