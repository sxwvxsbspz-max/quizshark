socket.emit('register_tv');
socket.on('connect', () => {
  socket.emit('register_tv');
});

const videoLayer  = document.getElementById('video-layer');
const gameLayer   = document.getElementById('game-layer');
const videoPlayer = document.getElementById('phase-video');

const answersWrap = document.getElementById('options-grid');
const timerWrap   = document.querySelector('.ps__timer');

/* ---------- Richtige-Antworten-Grid ---------- */
const answersSection = document.getElementById('answers-section');
const answersGrid    = document.getElementById('answers-grid');

/* ---------- KI Loading Overlay ---------- */
const kiLoadingOverlay = document.getElementById('ki-loading-overlay');

/* ---------- KI-Timeout Overlay ---------- */
const kiTimeoutOverlay = document.getElementById('ki-timeout-overlay');
const kiTimeoutMsg     = document.getElementById('ki-timeout-msg');

/* ---------- IMAGE / DUMMY ---------- */
const qImageWrap   = document.getElementById('question-image-wrap');
const qImageEl     = document.getElementById('question-image');
const dummyInWrap  = document.getElementById('dummy-inbox-wrap');
const dummyInImg   = document.getElementById('dummy-inbox-img');

/* ---------- Root ---------- */
const psRoot = document.querySelector('.ps');

let timerRAF = null;
let unveilTO = null;

/* ---------- Server-Clock Sync ---------- */
let clockOffsetMs = 0;
function nowSyncedMs() {
  return Date.now() + clockOffsetMs;
}

socket.on('server_time', (data) => {
  const serverNow = data && typeof data.server_now === "number" ? data.server_now : null;
  if (serverNow === null) return;
  clockOffsetMs = serverNow - Date.now();
});

/* ---------- Player order ---------- */
let currentPlayerOrder = [];

/* ---------- Dynamische MAX SPIELER IM TV ---------- */
let maxTvPlayers = 9;

function computeMaxTvPlayers() {
  const sidebar = document.getElementById('player-sidebar');
  if (!sidebar) return 9;

  const cs = window.getComputedStyle(sidebar);
  const gap = parseFloat(cs.gap || '0') || 0;

  const host = sidebar.closest('.ps__sidebar') || sidebar;
  const sidebarH = host.getBoundingClientRect().height;

  let sampleCard = sidebar.querySelector('.ps__playerCard');

  if (!sampleCard) {
    const tmp = document.createElement('div');
    tmp.className = 'ps__player';
    tmp.innerHTML = `
      <div class="ps__answerBox is-hidden" aria-hidden="true"></div>
      <div class="ps__playerCardWrap">
        <div class="ps__playerCard">
          <div class="ps__playerName">X</div>
          <div class="ps__playerScore">0</div>
        </div>
      </div>
    `;
    sidebar.appendChild(tmp);

    sampleCard = tmp.querySelector('.ps__playerCard');
    const tileH = sampleCard ? sampleCard.getBoundingClientRect().height : 0;
    tmp.remove();

    if (!tileH) return 9;
    return Math.max(1, Math.floor((sidebarH + gap) / (tileH + gap)));
  }

  const tileH = sampleCard.getBoundingClientRect().height;
  if (!tileH) return 9;
  return Math.max(1, Math.floor((sidebarH + gap) / (tileH + gap)));
}

function updateMaxTvPlayers() {
  requestAnimationFrame(() => {
    maxTvPlayers = computeMaxTvPlayers();
  });
}

window.addEventListener('resize', updateMaxTvPlayers);

/* ---------- Question Audio (disabled, kein Audio in diesem Modul) ---------- */
const questionAudio = new Audio();
questionAudio.preload = 'auto';
questionAudio.volume = 1.0;

/* ---------- Background Music ---------- */
const bgm = new Audio('/doyouknow/media/gamesounds/background.mp3');
bgm.preload = 'auto';
bgm.loop = true;
bgm.volume = 1.0;

function startBgm() {
  try { bgm.currentTime = 0; } catch (_) {}
  bgm.play().catch(() => {});
}

function stopBgm() {
  try {
    bgm.pause();
    bgm.currentTime = 0;
  } catch (_) {}
}

/* ---------- Game SFX ---------- */
const SFX_BASE = '/doyouknow/media/gamesounds';

function playSfxOverlap(file) {
  try {
    const a = new Audio(`${SFX_BASE}/${file}`);
    a.preload = 'auto';
    a.volume = 1.0;
    a.play().catch(() => {});
  } catch (_) {}
}

const sfxAnswerUnveiled      = new Audio(`${SFX_BASE}/answerunveiled.mp3`);
const sfxPointsUnveiled      = new Audio(`${SFX_BASE}/pointsunveiled.mp3`);
const sfxPointsUpdated       = new Audio(`${SFX_BASE}/pointsupdated.mp3`);
const sfxRevealPlayerAnswers = new Audio(`${SFX_BASE}/reveal_player_answers.mp3`);
const sfxShowResolution      = new Audio(`${SFX_BASE}/show_resolution.mp3`);
const sfxAi                  = new Audio(`${SFX_BASE}/ai.mp3`);

[sfxAnswerUnveiled, sfxPointsUnveiled, sfxPointsUpdated, sfxRevealPlayerAnswers, sfxShowResolution, sfxAi].forEach(a => {
  a.preload = 'auto';
  a.volume = 1.0;
});

function playSfxSingle(audioEl) {
  try {
    audioEl.pause();
    audioEl.currentTime = 0;
    audioEl.play().catch(() => {});
  } catch (_) {}
}

function playSfx(key) {
  switch (key) {
    case 'answerEntered':
      playSfxOverlap('answerentered.mp3');
      return;
    case 'answerUnveiled':
      playSfxSingle(sfxAnswerUnveiled);
      return;
    case 'revealPlayerAnswers':
      playSfxSingle(sfxRevealPlayerAnswers);
      return;
    case 'showResolution':
      playSfxSingle(sfxShowResolution);
      return;
    case 'ai':
      playSfxSingle(sfxAi);
      return;
    case 'pointsUnveiled':
      playSfxSingle(sfxPointsUnveiled);
      return;
    case 'pointsUpdated':
      playSfxSingle(sfxPointsUpdated);
      return;
    default:
      return;
  }
}

/* ---------- Layer Switching ---------- */
function showVideo(src) {
  gameLayer.style.display = 'none';
  videoLayer.style.display = 'block';

  try { questionAudio.pause(); questionAudio.currentTime = 0; } catch (_) {}
  stopBgm();

  try { sfxAnswerUnveiled.pause();      sfxAnswerUnveiled.currentTime      = 0; } catch (_) {}
  try { sfxPointsUnveiled.pause();      sfxPointsUnveiled.currentTime      = 0; } catch (_) {}
  try { sfxPointsUpdated.pause();       sfxPointsUpdated.currentTime       = 0; } catch (_) {}
  try { sfxRevealPlayerAnswers.pause(); sfxRevealPlayerAnswers.currentTime = 0; } catch (_) {}
  try { sfxShowResolution.pause();      sfxShowResolution.currentTime      = 0; } catch (_) {}

  if (src) {
    videoPlayer.src = src;
    videoPlayer.load();
  }

  videoPlayer.play().catch(() => {});
}

function showGame() {
  videoLayer.style.display = 'none';
  gameLayer.style.display = 'block';
}

/* ---------- Video finished ---------- */
videoPlayer.onended = function () {
  socket.emit('module_event', { action: 'video_finished' });
};

/* ---------- Helpers ---------- */
function clearTimer() {
  if (timerRAF) {
    cancelAnimationFrame(timerRAF);
    timerRAF = null;
  }
}

function clearUnveil() {
  if (unveilTO) {
    clearTimeout(unveilTO);
    unveilTO = null;
  }
}

function getPlayerRow(playerId) {
  return document.getElementById(`player-${playerId}`);
}

function getAnswerBox(playerId) {
  return document.getElementById(`answer-${playerId}`);
}

function getCardWrap(playerId) {
  return document.getElementById(`cardwrap-${playerId}`);
}

function hideMcGrid() {
  if (answersWrap) answersWrap.classList.add('is-hidden');
}

const MAX_TILES = 11;

function hideAnswersSection() {
  if (answersSection) {
    answersSection.classList.add('is-hidden');
    answersSection.setAttribute('aria-hidden', 'true');
  }
  if (answersGrid) answersGrid.innerHTML = '';
}

function renderAnswersGrid(correctPlayerAnswers, kiExamples) {
  if (!answersGrid || !answersSection) return;

  // Deduplizieren (case-insensitive), Spielerantworten zuerst, dann KI
  const seen = new Set();
  const all = [];
  [...correctPlayerAnswers, ...(kiExamples || [])].forEach(ans => {
    const norm = String(ans || '').trim().toLowerCase();
    if (!norm || seen.has(norm)) return;
    seen.add(norm);
    all.push(String(ans).trim());
  });

  // Alphabetisch sortieren
  all.sort((a, b) => a.localeCompare(b, 'de', { sensitivity: 'base' }));

  const hasTruncation = all.length > MAX_TILES;
  const visible = hasTruncation ? all.slice(0, MAX_TILES) : all;

  answersGrid.innerHTML = '';

  visible.forEach(ans => {
    const tile = document.createElement('div');
    tile.className = 'dyk__answerTile';
    tile.textContent = ans;
    answersGrid.appendChild(tile);
  });

  if (hasTruncation) {
    const more = document.createElement('div');
    more.className = 'dyk__answerTile dyk__answerTile--more';
    more.textContent = '…';
    answersGrid.appendChild(more);
  }

  answersSection.classList.remove('is-hidden');
  answersSection.setAttribute('aria-hidden', 'false');
}

function hideTimer() {
  if (timerWrap) timerWrap.classList.add('is-invisible');
}

function showTimer() {
  if (timerWrap) timerWrap.classList.remove('is-invisible');
}

function onQuestionIntro() {
  hideMcGrid();
  hideAnswersSection();
  hideTimer();
}

function onOpenAnswers() {
  hideMcGrid();
  hideAnswersSection();
  showTimer();
}

function clearAllScorePops() {
  document.querySelectorAll('.ps__scorePop').forEach(n => n.remove());
}

function resetPlayerClassesForNewQuestion() {
  const sidebar = document.getElementById('player-sidebar');
  if (!sidebar) return;

  sidebar.querySelectorAll('.ps__player').forEach(row => {
    row.classList.remove(
      'is-answered',
      'choice-0', 'choice-1', 'choice-2', 'choice-3',
      'is-correct', 'is-wrong'
    );
    row.querySelectorAll('.ps__scorePop').forEach(n => n.remove());
  });
}

function resetPlayerAnswerBoxes() {
  const sidebar = document.getElementById('player-sidebar');
  if (!sidebar) return;

  sidebar.querySelectorAll('.ps__answerBox').forEach(box => {
    box.classList.add('is-hidden');
    box.setAttribute('aria-hidden', 'true');
    box.textContent = '';
  });
}

/* ---------- IMAGE / DUMMY ---------- */
function setQuestionImage(imageFile) {
  const fallback = '/doyouknow/media/dummy.svg';
  const file = (imageFile || '').trim();

  if (psRoot) psRoot.classList.remove('has-image', 'no-image');

  if (qImageWrap) qImageWrap.classList.add('is-hidden');
  if (dummyInWrap) dummyInWrap.classList.add('is-hidden');

  if (!file) {
    if (psRoot) psRoot.classList.add('no-image');
    if (dummyInWrap) dummyInWrap.classList.remove('is-hidden');
    if (dummyInImg) dummyInImg.src = fallback;
    return;
  }

  if (psRoot) psRoot.classList.add('has-image');
  if (qImageWrap) qImageWrap.classList.remove('is-hidden');

  const isAbsolute =
    file.startsWith('http://') ||
    file.startsWith('https://') ||
    file.startsWith('/');

  if (qImageEl) {
    qImageEl.src = isAbsolute ? file : `/doyouknow/media/images/${file}`;
    qImageEl.onerror = () => {
      qImageEl.onerror = null;
      qImageEl.src = fallback;
    };
  }
}

/* ---------- Ranked Player Rendering ---------- */
function renderPlayersRanked(playersRanked) {
  const sidebar = document.getElementById('player-sidebar');
  if (!sidebar) return;

  sidebar.innerHTML = '';

  maxTvPlayers = computeMaxTvPlayers();
  const list = (playersRanked || []).slice(0, maxTvPlayers);

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

/* ---------- Scores updaten ---------- */
function updateScoresInPlace(playersRanked) {
  const list = (playersRanked || []).slice(0, maxTvPlayers);

  const scoreMap = {};
  list.forEach(p => { scoreMap[p.player_id] = p.score; });

  currentPlayerOrder.forEach(pid => {
    const row = getPlayerRow(pid);
    if (!row) return;
    const scoreEl = row.querySelector('.ps__playerScore');
    if (scoreEl && Object.prototype.hasOwnProperty.call(scoreMap, pid)) {
      scoreEl.textContent = scoreMap[pid];
    }
  });
}

/* ---------- Timer ---------- */
function parseStartedAtToMs(startedAt) {
  if (startedAt === undefined || startedAt === null) return null;

  if (typeof startedAt === "number") {
    if (startedAt > 1e12) return startedAt;
    if (startedAt > 1e9)  return startedAt * 1000;
    return startedAt;
  }

  if (typeof startedAt === "string") {
    const t = Date.parse(startedAt);
    return Number.isFinite(t) ? t : null;
  }

  return null;
}

function startTimerVisual(seconds, startedAt) {
  clearTimer();
  if (timerWrap) timerWrap.style.setProperty('--p', '0%');

  const durMs = Math.max(0.001, Number(seconds || 1)) * 1000;
  const startedAtMs = parseStartedAtToMs(startedAt);

  if (startedAtMs !== null) {
    const endAtMs = startedAtMs + durMs;

    const tick = () => {
      const nowMs = nowSyncedMs();
      const elapsed = nowMs - startedAtMs;
      const percent = Math.min(100, Math.max(0, (elapsed / durMs) * 100));
      if (timerWrap) timerWrap.style.setProperty('--p', `${percent}%`);

      if (nowMs < endAtMs) timerRAF = requestAnimationFrame(tick);
      else clearTimer();
    };

    timerRAF = requestAnimationFrame(tick);
    return;
  }

  const start = performance.now();
  const tick = now => {
    const elapsed = now - start;
    const percent = Math.min(100, (elapsed / durMs) * 100);
    if (timerWrap) timerWrap.style.setProperty('--p', `${percent}%`);
    if (percent < 100) timerRAF = requestAnimationFrame(tick);
    else clearTimer();
  };

  timerRAF = requestAnimationFrame(tick);
}

function stopTimerVisual() {
  clearTimer();
  if (timerWrap) timerWrap.style.setProperty('--p', '0%');
}

/* ---------- Socket Events ---------- */
socket.on('show_question', data => {
  showGame();
  clearTimer();
  clearUnveil();
  clearAllScorePops();
  hideAnswersSection();

  startBgm();
  setQuestionImage(data.image);

  document.getElementById('question-text').innerText = data.text || '';

  if (answersWrap) answersWrap.innerHTML = '';
  onQuestionIntro();

  const ranked = (data.players_ranked || []);
  maxTvPlayers = computeMaxTvPlayers();
  currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
  renderPlayersRanked(ranked);

  resetPlayerClassesForNewQuestion();
  resetPlayerAnswerBoxes();
});

socket.on('open_answers', data => {
  clearTimer();
  clearAllScorePops();
  onOpenAnswers();

  const dur = Number((data && (data.total_duration ?? data.totalDuration ?? data.duration)) || 30);
  const startedAt = data && (data.started_at ?? data.startedAt ?? data.opened_at ?? data.openedAt);

  startTimerVisual(dur, startedAt);
});

socket.on('close_answers', () => {
  stopTimerVisual();
  // KI-Thinking-Overlay einblenden
  if (kiLoadingOverlay) {
    kiLoadingOverlay.classList.remove('is-hidden');
    kiLoadingOverlay.setAttribute('aria-hidden', 'false');
  }
  playSfx('ai');
});

socket.on('player_logged_in', data => {
  const row = getPlayerRow(data.player_id);
  if (row) row.classList.add('is-answered');

  const box = getAnswerBox(data.player_id);
  if (box) {
    box.classList.remove('is-hidden');
    box.setAttribute('aria-hidden', 'false');
    box.textContent = '';
  }

  playSfx('answerEntered');
});

socket.on('reveal_player_answers', data => {
  stopTimerVisual();
  playSfx('revealPlayerAnswers');
  clearAllScorePops();
  hideMcGrid();

  const pa = data.player_answers || {};

  Object.entries(pa).forEach(([playerId, answerVal]) => {
    const row = getPlayerRow(playerId);
    if (row) row.classList.add('is-answered');

    const box = getAnswerBox(playerId);
    if (!box) return;

    box.classList.remove('is-hidden');
    box.setAttribute('aria-hidden', 'false');

    let text = '';
    if (answerVal !== null && answerVal !== undefined) {
      if (typeof answerVal === 'object') {
        text = String(answerVal.text ?? answerVal.raw ?? '');
      } else {
        text = String(answerVal);
      }
    }

    box.textContent = text;
  });
});

socket.on('show_resolution', data => {
  stopBgm();
  playSfx('showResolution');
  // KI-Thinking-Overlay ausblenden
  if (kiLoadingOverlay) {
    kiLoadingOverlay.classList.add('is-hidden');
    kiLoadingOverlay.setAttribute('aria-hidden', 'true');
  }

  stopTimerVisual();
  clearAllScorePops();
  hideMcGrid();

  const details = data && data.details ? data.details : null;
  const kiExamples = Array.isArray(data && data.examples) ? data.examples : [];

  // Spieler-Avatare markieren + richtige Antworten sammeln
  const correctPlayerAnswers = [];

  if (details && typeof details === 'object') {
    currentPlayerOrder.forEach(playerId => {
      const row = getPlayerRow(playerId);
      if (!row) return;

      const d = details[playerId];
      if (!d) return;

      if (d.accepted === true)  row.classList.add('is-correct');
      if (d.accepted === false) row.classList.add('is-wrong');

      const box = getAnswerBox(playerId);
      if (box) {
        box.classList.remove('is-hidden');
        box.setAttribute('aria-hidden', 'false');
        const raw = d.raw_answer ?? d.rawAnswer ?? '';
        box.textContent = String(raw ?? '');
      }

      if (d.accepted === true && (d.raw_answer || d.rawAnswer)) {
        correctPlayerAnswers.push(d.raw_answer ?? d.rawAnswer);
      }
    });
  }

  // Antworten-Grid rendern (richtige Spielerantworten + KI-Vorschläge)
  renderAnswersGrid(correctPlayerAnswers, kiExamples);
});

socket.on('ki_timeout', data => {
  stopBgm();
  stopTimerVisual();

  if (kiTimeoutMsg && data && data.message) {
    kiTimeoutMsg.textContent = data.message;
  }

  if (kiTimeoutOverlay) {
    kiTimeoutOverlay.classList.remove('is-hidden');
    kiTimeoutOverlay.setAttribute('aria-hidden', 'false');
  }
});

socket.on('show_scoring', data => {
  const gainedObj = data.gained || {};
  const anyPoints = Object.values(gainedObj).some(g => Number(g) > 0);

  clearAllScorePops();
  if (!anyPoints) return;

  playSfx('pointsUnveiled');

  Object.entries(gainedObj).forEach(([playerId, g]) => {
    if (Number(g) > 0) {
      const row = getPlayerRow(playerId);
      if (!row) return;

      const pop = document.createElement('div');
      pop.className = 'ps__scorePop';
      pop.textContent = `+${g}`;

      const wrap = getCardWrap(playerId);
      const target = wrap || row;
      if (target) target.appendChild(pop);
    }
  });
});

socket.on('apply_scoring_update', data => {
  clearAllScorePops();
  updateScoresInPlace(data.players_ranked || []);
  playSfx('pointsUpdated');
});

socket.on('play_round_video', data => {
  clearTimer();
  clearUnveil();
  clearAllScorePops();
  showVideo(`/doyouknow/media/frage${data.round}.mp4`);
});

/* ---------- Init ---------- */
updateMaxTvPlayers();
showVideo();
