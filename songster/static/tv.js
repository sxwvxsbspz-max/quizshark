// Songster TV – Hitster-Mechanik

socket.emit('register_tv');
socket.on('connect', () => socket.emit('register_tv'));

// ----------------------------------------------------------------
// DOM
// ----------------------------------------------------------------
const videoLayer  = document.getElementById('video-layer');
const gameLayer   = document.getElementById('game-layer');
const videoPlayer = document.getElementById('phase-video');
const tvTimeline  = document.getElementById('tv-timeline');
const roundLabel  = document.getElementById('round-label');
const timerWrap   = document.getElementById('tv-timer');

// ----------------------------------------------------------------
// Server-Clock Sync
// ----------------------------------------------------------------
let clockOffsetMs = 0;
function nowSyncedMs() { return Date.now() + clockOffsetMs; }

// ----------------------------------------------------------------
// Timer
// ----------------------------------------------------------------
let timerRAF = null;

function clearTimer() {
  if (timerRAF) { cancelAnimationFrame(timerRAF); timerRAF = null; }
}

function startTimerVisual(seconds, startedAt) {
  clearTimer();
  if (timerWrap) timerWrap.style.setProperty('--p', '0%');
  const durMs = Math.max(0.001, Number(seconds || 1)) * 1000;
  const startMs = (typeof startedAt === 'number' && startedAt > 1e9) ? startedAt : null;
  if (startMs) {
    const endMs = startMs + durMs;
    const tick = () => {
      const now = nowSyncedMs();
      const pct = Math.min(100, Math.max(0, (now - startMs) / durMs * 100));
      if (timerWrap) timerWrap.style.setProperty('--p', `${pct}%`);
      if (now < endMs) timerRAF = requestAnimationFrame(tick);
      else clearTimer();
    };
    timerRAF = requestAnimationFrame(tick);
    return;
  }
  const t0 = performance.now();
  const tick = now => {
    const pct = Math.min(100, (now - t0) / durMs * 100);
    if (timerWrap) timerWrap.style.setProperty('--p', `${pct}%`);
    if (pct < 100) timerRAF = requestAnimationFrame(tick);
    else clearTimer();
  };
  timerRAF = requestAnimationFrame(tick);
}

function stopTimerVisual() {
  clearTimer();
  if (timerWrap) { timerWrap.style.setProperty('--p', '0%'); timerWrap.classList.add('is-invisible'); }
}

socket.on('server_time', d => {
  if (d && typeof d.server_now === 'number') clockOffsetMs = d.server_now - Date.now();
});

// ----------------------------------------------------------------
// Audio
// ----------------------------------------------------------------
const questionAudio = new Audio();
questionAudio.preload = 'auto';
questionAudio.volume = 1.0;
questionAudio.loop = true;

const SFX_BASE = '/songster/media/gamesounds';
const bgm = new Audio(`${SFX_BASE}/background.mp3`);
bgm.preload = 'auto'; bgm.loop = true; bgm.volume = 1.0;

function startBgm()  { try { bgm.currentTime = 0; } catch(_){} bgm.play().catch(()=>{}); }
function stopBgm()   { try { bgm.pause(); bgm.currentTime = 0; } catch(_){} }

function playSfxOnce(file) {
  try { const a = new Audio(`${SFX_BASE}/${file}`); a.volume = 1.0; a.play().catch(()=>{}); } catch(_){}
}

function playQuestionAudio(url) {
  if (!url) return;
  try { questionAudio.pause(); questionAudio.currentTime = 0; } catch(_){}
  questionAudio.src = url;
  questionAudio.load();
  questionAudio.play().catch(()=>{});
}

function stopQuestionAudio() {
  try { questionAudio.pause(); questionAudio.currentTime = 0; } catch(_){}
}

// ----------------------------------------------------------------
// Layer
// ----------------------------------------------------------------
function showVideo(src) {
  gameLayer.style.display = 'none';
  videoLayer.style.display = 'block';
  stopQuestionAudio(); stopBgm();
  if (src) { videoPlayer.src = src; videoPlayer.load(); }
  videoPlayer.play().catch(()=>{});
}

function showGame() {
  videoLayer.style.display = 'none';
  gameLayer.style.display = 'block';
}

videoPlayer.onended = () => socket.emit('module_event', { action: 'video_finished' });

// ----------------------------------------------------------------
// State
// ----------------------------------------------------------------
let currentRound            = 0;
let anchorYear              = null;
let currentYellowYear       = null;   // Jahr des aktuellen Songs (enthüllt)
let currentYellowTitle      = null;
let currentYellowArtist     = null;
let currentYellowPlacedYear = null;   // Jahr das nach der Runde gelb bleibt
let currentPlayerOrder      = [];
let maxTvPlayers            = 12;
let yearAnnounceAudio       = null;   // läuft noch während show_resolution kommt
let pendingScoreGained      = false;  // wurde in show_scoring gesetzt

// ----------------------------------------------------------------
// Player sidebar
// ----------------------------------------------------------------
function computeMaxTvPlayers() {
  const sidebar = document.getElementById('player-sidebar');
  if (!sidebar) return 12;
  const sidebarH = (sidebar.closest('.ps__sidebar') || sidebar).getBoundingClientRect().height;
  let sampleCard = sidebar.querySelector('.ps__playerCard');
  if (!sampleCard) {
    const tmp = document.createElement('div');
    tmp.className = 'ps__player';
    tmp.innerHTML = '<div class="ps__playerCard"><div class="ps__playerName">X</div><div class="ps__playerScore">0</div></div>';
    sidebar.appendChild(tmp);
    sampleCard = tmp.querySelector('.ps__playerCard');
    const h = sampleCard ? sampleCard.getBoundingClientRect().height : 0;
    tmp.remove();
    if (!h) return 12;
    return Math.max(1, Math.floor((sidebarH + 5) / (h + 5)));
  }
  const h = sampleCard.getBoundingClientRect().height;
  return h ? Math.max(1, Math.floor((sidebarH + 5) / (h + 5))) : 12;
}

function renderPlayers(playersRanked) {
  const sidebar = document.getElementById('player-sidebar');
  if (!sidebar) return;
  maxTvPlayers = computeMaxTvPlayers();
  const list = (playersRanked || []).slice(0, maxTvPlayers);
  currentPlayerOrder = list.map(p => p.player_id);

  sidebar.innerHTML = '';
  list.forEach(p => {
    const row = document.createElement('div');
    row.className = 'ps__player';
    row.id = `player-${p.player_id}`;
    row.innerHTML = `
      <div id="answer-${p.player_id}" class="ps__answerBox is-hidden" aria-hidden="true"></div>
      <div id="cardwrap-${p.player_id}" class="ps__playerCardWrap">
        <div class="ps__playerCard">
          <div class="ps__playerName">${p.name}</div>
          <div class="ps__playerScore">${p.score}</div>
        </div>
      </div>
    `;
    sidebar.appendChild(row);
  });
}

function updateScores(playersRanked) {
  (playersRanked || []).forEach(p => {
    const row = document.getElementById(`player-${p.player_id}`);
    if (!row) return;
    const scoreEl = row.querySelector('.ps__playerScore');
    if (scoreEl) scoreEl.textContent = p.score;
  });
}

function clearScorePops() {
  document.querySelectorAll('.ps__scorePop').forEach(n => n.remove());
}

function setYearRange(playerId, text) {
  const el = document.getElementById(`answer-${playerId}`);
  if (!el) return;
  if (text) {
    el.textContent = text;
    el.classList.remove('is-hidden');
    el.setAttribute('aria-hidden', 'false');
  } else {
    el.classList.add('is-hidden');
    el.setAttribute('aria-hidden', 'true');
    el.textContent = '';
  }
}

function clearYearRanges() {
  document.querySelectorAll('.ps__answerBox').forEach(el => {
    el.classList.add('is-hidden');
    el.setAttribute('aria-hidden', 'true');
    el.textContent = '';
  });
}

function clearPlayerClasses() {
  document.querySelectorAll('.ps__player').forEach(row => {
    row.classList.remove('is-answered', 'is-correct', 'is-wrong');
    clearScorePops();
  });
  clearYearRanges();
}

// ----------------------------------------------------------------
// Timeline rendering
// ----------------------------------------------------------------

function buildAudioSvg() {
  return `<svg class="sng__eq" viewBox="0 0 180 50" aria-hidden="true">
    <rect class="bar" x="5"   y="5" width="20" height="40" rx="4"/>
    <rect class="bar" x="35"  y="5" width="20" height="40" rx="4"/>
    <rect class="bar" x="65"  y="5" width="20" height="40" rx="4"/>
    <rect class="bar" x="95"  y="5" width="20" height="40" rx="4"/>
    <rect class="bar" x="125" y="5" width="20" height="40" rx="4"/>
    <rect class="bar" x="155" y="5" width="20" height="40" rx="4"/>
  </svg>`;
}

function buildTile(tile, variant) {
  const yearStr = tile.year != null ? String(tile.year) : '?';

  if (variant === 'yellow') {
    return `<div class="sng__tile sng__tile--yellow" id="tile-current" data-year="${tile.year}">
      <div class="sng__tileYearSlot">
        <svg class="sng__eq" id="tile-current-eq" viewBox="0 0 180 50" aria-hidden="true">
          <rect class="bar" x="5"   y="5" width="20" height="40" rx="4"/>
          <rect class="bar" x="35"  y="5" width="20" height="40" rx="4"/>
          <rect class="bar" x="65"  y="5" width="20" height="40" rx="4"/>
          <rect class="bar" x="95"  y="5" width="20" height="40" rx="4"/>
          <rect class="bar" x="125" y="5" width="20" height="40" rx="4"/>
          <rect class="bar" x="155" y="5" width="20" height="40" rx="4"/>
        </svg>
        <div class="sng__tileYear" id="tile-current-year" style="display:none">—</div>
      </div>
      <div class="sng__tileOneLine" id="tile-current-info">
        <span id="tile-current-loading">Song läuft…</span><span id="tile-current-artist" style="display:none"></span><span id="tile-current-sep" style="display:none"> — </span><span id="tile-current-title" style="display:none"></span>
      </div>
    </div>`;
  }

  if (tile.is_anchor) {
    return `<div class="sng__tile sng__tile--white" id="tile-anchor" data-year="${tile.year}">
      <div class="sng__tileYear">${yearStr}</div>
      <div class="sng__tileAnchorLabel">Ausgangsjahr</div>
    </div>`;
  }

  // Bereits gespielter Song – gelb wenn es der zuletzt platzierte ist, sonst weiß
  const isPlaced = (tile.year === currentYellowPlacedYear);
  const cls = isPlaced ? 'sng__tile--yellow' : 'sng__tile--white';
  const artistPart = tile.artist || '';
  const titlePart  = tile.title  || '';
  const sep        = (artistPart && titlePart) ? ' — ' : '';
  return `<div class="sng__tile ${cls}" id="tile-y${tile.year}" data-year="${tile.year}">
    <div class="sng__tileYear">${yearStr}</div>
    <div class="sng__tileOneLine">${artistPart}${sep}${titlePart}</div>
  </div>`;
}


function redrawTimeline(tvTimelineData, hasCurrentSong, currentSongYear) {
  const container = document.getElementById('tv-timeline');
  if (!container) return;
  let html = '';
  if (hasCurrentSong) {
    html += buildTile({year: currentSongYear}, 'yellow');
  }
  (tvTimelineData || []).forEach(tile => {
    html += buildTile(tile, tile.is_anchor ? 'anchor' : 'played');
  });
  container.innerHTML = html;
}

// ----------------------------------------------------------------
// Socket Events
// ----------------------------------------------------------------

socket.on('play_round_video', data => {
  clearScorePops();
  currentRound = Number(data.round || 1);
  showVideo(`/songster/media/frage${currentRound}.mp4`);
});

socket.on('show_question', data => {
  showGame();
  clearPlayerClasses();
  clearScorePops();
  stopBgm();
  stopTimerVisual();

  anchorYear              = data.anchor_year;
  currentYellowYear       = null;
  currentYellowTitle      = null;
  currentYellowArtist     = null;
  currentYellowPlacedYear = null;

  if (roundLabel) roundLabel.textContent = `Track ${data.round || currentRound}`;

  renderPlayers(data.players_ranked);
  redrawTimeline(data.tv_timeline, true, null);

  setTimeout(() => playQuestionAudio(data.audio), 500);
});

socket.on('open_answers', data => {
  if (timerWrap) timerWrap.classList.remove('is-invisible');
  startTimerVisual(data.duration || 28, data.started_at);
});

socket.on('close_answers', () => {
  stopTimerVisual();
});

socket.on('player_logged_in', data => {
  const row = document.getElementById(`player-${data.player_id}`);
  if (row) row.classList.add('is-answered');
  playSfxOnce('answerentered.mp3');
});

socket.on('reveal_player_answers', data => {
  playSfxOnce('reveal_player_answers.mp3');
  const pa = data.player_answers || {};
  Object.entries(pa).forEach(([pid, ans]) => {
    const row = document.getElementById(`player-${pid}`);
    if (row) row.classList.add('is-answered');
    setYearRange(pid, ans.year_range || '');
  });
});

socket.on('unveil_correct', data => {
  yearAnnounceAudio = new Audio(`${SFX_BASE}/year-${data.correct_year}.mp3`);
  yearAnnounceAudio.volume = 1.0;
  yearAnnounceAudio.play().catch(() => {});
  stopQuestionAudio();

  currentYellowYear   = data.correct_year;
  currentYellowTitle  = data.title || '';
  currentYellowArtist = data.artist || '';

  const eqEl      = document.getElementById('tile-current-eq');
  const yearEl    = document.getElementById('tile-current-year');
  const loadingEl = document.getElementById('tile-current-loading');
  const artistEl  = document.getElementById('tile-current-artist');
  const titleEl   = document.getElementById('tile-current-title');
  const sepEl     = document.getElementById('tile-current-sep');

  if (eqEl)      eqEl.style.display = 'none';
  if (yearEl)    { yearEl.textContent = String(currentYellowYear); yearEl.style.display = ''; }
  if (loadingEl) loadingEl.style.display = 'none';
  if (artistEl)  { artistEl.textContent = currentYellowArtist; artistEl.style.display = 'inline'; }
  if (titleEl)   { titleEl.textContent  = currentYellowTitle;  titleEl.style.display  = 'inline'; }
  if (sepEl)     sepEl.style.display = (currentYellowArtist && currentYellowTitle) ? 'inline' : 'none';
});

socket.on('show_resolution', data => {
  const correctYear   = data.correct_year;
  const playerResults = data.player_results || {};
  const newTvTimeline = data.tv_timeline || [];

  const doReveal = () => {
    playSfxOnce('show_resolution.mp3');
    Object.entries(playerResults).forEach(([pid, res]) => {
      const row = document.getElementById(`player-${pid}`);
      if (!row) return;
      row.classList.remove('is-answered');
      if (res.correct) row.classList.add('is-correct');
      else             row.classList.add('is-wrong');
    });
  };

  const doFly = () => {
    playSfxOnce('swoosh.mp3');
    _flyYellowTile(newTvTimeline, correctYear, () => setTimeout(doReveal, 2000));
  };

  if (yearAnnounceAudio && !yearAnnounceAudio.ended) {
    yearAnnounceAudio.addEventListener('ended', doFly, { once: true });
  } else {
    doFly();
  }
});

function _flyYellowTile(newTvTimeline, correctYear, onLanded) {
  const currentTile = document.getElementById('tile-current');
  if (!currentTile) {
    redrawTimeline(newTvTimeline, false, null);
    if (onLanded) onLanded();
    return;
  }

  // 1) Startposition sichern
  const fromRect = currentTile.getBoundingClientRect();

  // 2) Neue Timeline rendern (ohne gelbes Tile)
  redrawTimeline(newTvTimeline, false, null);

  // 3) Zielposition ermitteln (das Tile für correctYear in der neuen Timeline)
  const targetTile = document.getElementById(`tile-y${correctYear}`);
  if (!targetTile) return;
  const toRect = targetTile.getBoundingClientRect();

  // 4) Fliegendes Tile erstellen
  const flyEl = document.createElement('div');
  flyEl.className = 'sng__tile sng__tile--yellow sng__tile--flying';
  flyEl.style.width  = `${fromRect.width}px`;
  flyEl.style.height = `${fromRect.height}px`;
  flyEl.style.left   = `${fromRect.left}px`;
  flyEl.style.top    = `${fromRect.top}px`;
  flyEl.style.borderRadius = getComputedStyle(currentTile).borderRadius;
  flyEl.style.overflow = 'hidden';
  const sep = (currentYellowArtist && currentYellowTitle) ? ' — ' : '';
  flyEl.innerHTML = `
    <div class="sng__tileYearSlot"><div class="sng__tileYear">${correctYear}</div></div>
    <div class="sng__tileOneLine">${currentYellowArtist}${sep}${currentYellowTitle}</div>
  `;
  document.getElementById('game-layer').appendChild(flyEl);

  // 5) Ziel-Tile temporär ausblenden
  targetTile.style.visibility = 'hidden';

  // 6) Animieren (nächstem Frame warten für Transition)
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const dx = toRect.left - fromRect.left;
      const dy = toRect.top  - fromRect.top;
      flyEl.style.transform = `translate(${dx}px, ${dy}px)`;

      flyEl.addEventListener('transitionend', () => {
        flyEl.remove();
        currentYellowPlacedYear = correctYear;
        if (targetTile) {
          targetTile.classList.remove('sng__tile--white');
          targetTile.classList.add('sng__tile--yellow');
          targetTile.style.visibility = 'visible';
        }
        if (onLanded) onLanded();
      }, { once: true });
    });
  });
}

socket.on('show_scoring', data => {
  const gained = data.gained || {};
  clearScorePops();

  pendingScoreGained = Object.values(gained).some(g => Number(g) > 0);
  if (pendingScoreGained) {
    playSfxOnce('pointsunveiled.mp3');
    Object.entries(gained).forEach(([pid, g]) => {
      if (Number(g) > 0) {
        const target = document.getElementById(`cardwrap-${pid}`) || document.getElementById(`player-${pid}`);
        if (!target) return;
        const pop = document.createElement('div');
        pop.className = 'ps__scorePop';
        pop.textContent = `+${g}`;
        target.appendChild(pop);
      }
    });
  }
});

socket.on('apply_scoring_update', data => {
  clearScorePops();
  updateScores(data.players_ranked || []);
  if (pendingScoreGained) {
    playSfxOnce('pointsupdated.mp3');
    pendingScoreGained = false;
  }
});

// ----------------------------------------------------------------
// Init
// ----------------------------------------------------------------
window.addEventListener('resize', () => { maxTvPlayers = computeMaxTvPlayers(); });
showVideo();
