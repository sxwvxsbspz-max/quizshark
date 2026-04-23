// === YOURCATEGORY TV JS ===

socket.emit('register_tv');
socket.on('connect', () => socket.emit('register_tv'));

// ---------------------------------------------------------------------------
// Layers
// ---------------------------------------------------------------------------

const layerVideo      = document.getElementById('yc-video-layer');
const layerInput      = document.getElementById('yc-input-layer');
const layerGenerating = document.getElementById('yc-generating-layer');
const layerAnnounce   = document.getElementById('yc-announcement-layer');
const layerGame       = document.getElementById('game-layer');
const phaseVideo      = document.getElementById('yc-phase-video');

function showLayer(el) {
  [layerVideo, layerInput, layerGenerating, layerAnnounce, layerGame].forEach(l => {
    if (l) l.style.display = (l === el) ? '' : 'none';
  });
}

function showVideo(src) {
  if (phaseVideo && src) {
    phaseVideo.src = src;
    phaseVideo.load();
    phaseVideo.play().catch(() => {});
  }
  showLayer(layerVideo);
}

phaseVideo.onended = function() {
  socket.emit('module_event', { action: 'video_finished' });
};

// ---------------------------------------------------------------------------
// Server clock sync
// ---------------------------------------------------------------------------

let clockOffsetMs = 0;
function nowSyncedMs() { return Date.now() + clockOffsetMs; }

socket.on('server_time', data => {
  const sn = data && typeof data.server_now === 'number' ? data.server_now : null;
  if (sn !== null) clockOffsetMs = sn - Date.now();
});

// ---------------------------------------------------------------------------
// Audio helpers
// ---------------------------------------------------------------------------

const MEDIA_BASE      = '/yourcategory/media/audio/';
const SFX_BASE        = '/yourcategory/media/gamesounds/';
const PS_SFX_BASE     = '/punktesammler/media/gamesounds/';
const PLAYER_SND_BASE = '/playerdata/playersounds/';

function playOnce(src) {
  try {
    const a = new Audio(src);
    a.preload = 'auto';
    a.volume  = 1.0;
    a.play().catch(() => {});
    return a;
  } catch (_) { return null; }
}

function playOnceReturn(src) {
  return new Promise(res => {
    try {
      const a = new Audio(src);
      a.preload = 'auto';
      a.volume  = 1.0;
      a.play().catch(() => res());
      a.onended = () => res();
      a.onerror = () => res();
    } catch (_) { res(); }
  });
}

// Punktesammler shared SFX (reuse same files)
const SFX = {
  answerEntered:       () => playOnce(PS_SFX_BASE + 'answerentered.mp3'),
  answerUnveiled:      null,
  revealPlayerAnswers: null,
  unveilCorrect:       null,
  showResolution:      null,
  pointsUnveiled:      null,
  pointsUpdated:       null,
};

const _sfxCache = {};
function _sfxSingle(key, file) {
  if (!_sfxCache[key]) {
    _sfxCache[key] = new Audio(PS_SFX_BASE + file);
    _sfxCache[key].preload = 'auto';
    _sfxCache[key].volume  = 1.0;
  }
  const a = _sfxCache[key];
  try { a.pause(); a.currentTime = 0; a.play().catch(() => {}); } catch (_) {}
}

function playSfx(key) {
  switch (key) {
    case 'answerEntered':       SFX.answerEntered(); break;
    case 'answerUnveiled':      _sfxSingle(key, 'answerunveiled.mp3'); break;
    case 'revealPlayerAnswers': _sfxSingle(key, 'reveal_player_answers.mp3'); break;
    case 'unveilCorrect':       _sfxSingle(key, 'unveil_correct.mp3'); break;
    case 'showResolution':      _sfxSingle(key, 'show_resolution.mp3'); break;
    case 'pointsUnveiled':      _sfxSingle(key, 'pointsunveiled.mp3'); break;
    case 'pointsUpdated':       _sfxSingle(key, 'pointsupdated.mp3'); break;
  }
}

// ---------------------------------------------------------------------------
// Player sound map (for name TTS, same as leaderboard)
// ---------------------------------------------------------------------------

let playerSoundMap = {};
const playerSoundCache = new Map();

function normalizeName(name) {
  let s = String(name || '').trim().toLowerCase();
  if (s.includes(' ')) s = s.split(' ')[0];
  s = s.replace(/ä/g,'ae').replace(/ö/g,'oe').replace(/ü/g,'ue').replace(/ß/g,'ss');
  s = s.normalize('NFD').replace(/[̀-ͯ]/g, '');
  return s.replace(/[^a-z0-9]/g, '');
}

fetch(PLAYER_SND_BASE + 'map.json', { cache: 'no-cache' })
  .then(r => r.ok ? r.json() : {})
  .then(m => { playerSoundMap = m || {}; })
  .catch(() => {});

function getPlayerAudioSrc(name) {
  const key    = normalizeName(name);
  const mapped = key ? playerSoundMap[key] : null;
  if (!mapped) return null;
  return PLAYER_SND_BASE + mapped;
}

// ---------------------------------------------------------------------------
// Background music (category input)
// ---------------------------------------------------------------------------

let bgmInput = null;
let bgmInputStarted = false;

function startBgmInput() {
  if (bgmInputStarted) return;
  bgmInputStarted = true;
  bgmInput = new Audio(SFX_BASE + 'questionentry.mp3');
  bgmInput.preload = 'auto';
  bgmInput.loop    = true;
  bgmInput.volume  = 0.85;
  bgmInput.play().catch(() => {});
}

function stopBgmInput() {
  if (!bgmInput) return;
  try { bgmInput.pause(); bgmInput.currentTime = 0; } catch (_) {}
  bgmInputStarted = false;
}

const bgm = new Audio('/punktesammler/media/gamesounds/background.mp3');
bgm.preload = 'auto';
bgm.loop    = true;
bgm.volume  = 1.0;

function startBgm() {
  try { bgm.currentTime = 0; } catch (_) {}
  bgm.play().catch(() => {});
}

function stopBgm() {
  try { bgm.pause(); bgm.currentTime = 0; } catch (_) {}
}

// Question audio (MC phase)
const questionAudio = new Audio();
questionAudio.preload = 'auto';
questionAudio.volume  = 1.0;

function playQuestionAudio(file) {
  if (!file) return;
  try { questionAudio.pause(); questionAudio.currentTime = 0; } catch (_) {}
  questionAudio.src = file.startsWith('/') ? file : MEDIA_BASE + file;
  questionAudio.load();
  questionAudio.play().catch(() => {});
}

// ---------------------------------------------------------------------------
// LAYER 1: Category Input
// ---------------------------------------------------------------------------

// --- Inspiration Cycling (slide-in from left, slide-out to right) ---
let inspirationList = [];
let inspirationIndex = 0;
let inspirationInterval = null;
let _currentInspEl = null;

function _showInspirationItem(text) {
  const stage = document.getElementById('input-inspiration-stage');
  if (!stage) return;

  if (_currentInspEl) {
    const old = _currentInspEl;
    old.classList.remove('is-entering');
    old.classList.add('is-leaving');
    setTimeout(() => { if (old.parentNode) old.parentNode.removeChild(old); }, 500);
  }

  const el = document.createElement('div');
  el.className = 'yc-insp-item is-entering';
  el.textContent = text;
  stage.appendChild(el);
  _currentInspEl = el;
}

function startInspirationCycle(categories) {
  if (inspirationInterval) clearInterval(inspirationInterval);
  inspirationList = (categories || []);
  _currentInspEl = null;
  if (!inspirationList.length) return;
  inspirationIndex = 0;
  _showInspirationItem(inspirationList[inspirationIndex]);
  inspirationIndex = (inspirationIndex + 1) % inspirationList.length;
  inspirationInterval = setInterval(() => {
    _showInspirationItem(inspirationList[inspirationIndex]);
    inspirationIndex = (inspirationIndex + 1) % inspirationList.length;
  }, 3000);
}

function stopInspirationCycle() {
  if (inspirationInterval) { clearInterval(inspirationInterval); inspirationInterval = null; }
  _currentInspEl = null;
}

// --- Player Sidebar (input phase) ---
function renderInputSidebar(playersRanked, submitted) {
  const sidebar = document.getElementById('input-player-sidebar');
  if (!sidebar) return;

  const submittedSet = new Set(submitted || []);
  sidebar.innerHTML = '';

  (playersRanked || []).forEach(p => {
    const row = document.createElement('div');
    row.className = 'ps__player' + (submittedSet.has(p.player_id) ? ' is-answered' : '');
    row.id = `input-player-${p.player_id}`;
    row.innerHTML = `<div class="ps__playerCard"><div class="ps__playerName">${p.name}</div><div class="ps__playerScore">${p.score}</div></div>`;
    sidebar.appendChild(row);
  });
}

function markPlayerSubmitted(playerId) {
  const row = document.getElementById(`input-player-${playerId}`);
  if (row) row.classList.add('is-answered');
}

// --- Input Timer ---
let inputTimerRAF = null;
const inputTimerCircle = document.getElementById('input-timer-circle');

function startInputTimer(endsAt) {
  if (inputTimerRAF) { cancelAnimationFrame(inputTimerRAF); inputTimerRAF = null; }
  if (!inputTimerCircle) return;

  const endMs = Date.parse(endsAt);
  if (!Number.isFinite(endMs)) return;

  const tick = () => {
    const now     = nowSyncedMs();
    const startMs = endMs - (window._ycInputDuration || 30) * 1000;
    const elapsed = now - startMs;
    const durMs   = endMs - startMs;
    const pct     = Math.min(100, Math.max(0, (elapsed / durMs) * 100));
    inputTimerCircle.style.setProperty('--p', pct + '%');
    if (now < endMs) inputTimerRAF = requestAnimationFrame(tick);
  };
  inputTimerRAF = requestAnimationFrame(tick);
}

socket.on('yc_category_input', data => {
  window._ycInputDuration = data.duration || 30;
  showLayer(layerInput);
  startBgmInput();
  renderInputSidebar(data.players_ranked, data.submitted);
  startInspirationCycle(data.inspiration_categories);
  if (data.ends_at) startInputTimer(data.ends_at);
});

socket.on('yc_player_submitted', data => {
  markPlayerSubmitted(data.player_id);
  playSfx('answerEntered');
});

// ---------------------------------------------------------------------------
// LAYER 2: Generating
// ---------------------------------------------------------------------------

const genProgressText = document.getElementById('gen-progress-text');
const genBarFill      = document.getElementById('gen-bar-fill');
const genCurrentText  = document.getElementById('gen-current-text');
const genErrorText    = document.getElementById('gen-error-text');

let _genErrorTimeout = null;

function updateGenProgress(progress, total, current, player) {
  if (genProgressText) genProgressText.textContent = `${progress} von ${total} fertig`;
  if (genBarFill) {
    const pct = total > 0 ? Math.round((progress / total) * 100) : 0;
    genBarFill.style.width = pct + '%';
  }
  if (genCurrentText) {
    genCurrentText.textContent = current ? `"${current}"` : '';
  }
}

socket.on('yc_generating', data => {
  stopBgmInput();
  stopInspirationCycle();
  showLayer(layerGenerating);
  updateGenProgress(data.progress || 0, data.total || 0, data.current_category, data.current_player);
  if (data.players_ranked) {
    const sb = document.getElementById('gen-player-sidebar');
    if (sb && !sb.children.length) {
      (data.players_ranked).forEach(p => {
        const row = document.createElement('div');
        row.className = 'ps__player';
        row.innerHTML = `<div class="ps__playerCard"><div class="ps__playerName">${p.name}</div><div class="ps__playerScore">${p.score}</div></div>`;
        sb.appendChild(row);
      });
    }
  }
});

socket.on('yc_error', data => {
  const type = data.sound_type || 'technical';
  const num  = Math.floor(Math.random() * 5) + 1;

  let soundFile;
  if (type === 'content_policy') soundFile = `contentpolicy${num}.mp3`;
  else if (type === 'nonsense')  soundFile = `nonsensequestion${num}.mp3`;
  else                           soundFile = `technicalerror${num}.mp3`;

  playOnce(SFX_BASE + soundFile);

  if (genErrorText) {
    if (_genErrorTimeout) clearTimeout(_genErrorTimeout);
    genErrorText.style.display = '';
    genErrorText.style.animation = 'none';

    let msg;
    if (type === 'content_policy') msg = `${data.player_name}: Kategorie nicht erlaubt 🚫`;
    else if (type === 'nonsense')  msg = `${data.player_name}: Keine Frage möglich 🤔`;
    else                           msg = `${data.player_name}: Technischer Fehler ⚡`;

    genErrorText.textContent = msg;
    // Trigger reflow to restart animation
    void genErrorText.offsetWidth;
    genErrorText.style.animation = '';

    _genErrorTimeout = setTimeout(() => {
      if (genErrorText) genErrorText.style.display = 'none';
    }, 4200);
  }
});

// ---------------------------------------------------------------------------
// LAYER 3: Announcement
// ---------------------------------------------------------------------------

const annCounter  = document.getElementById('ann-counter');
const annPlayer   = document.getElementById('ann-player');
const annCategory = document.getElementById('ann-category');

socket.on('yc_announcement', async data => {
  // Show announcement inside the game layer (question area + player sidebar)
  document.getElementById('question-text').innerText =
    `Nächste Kategorie: ${data.category || '—'}`;

  answersWrap.innerHTML = `
    <div class="yc-ann__ingame">
      <div class="yc-ann__ingame-from">Ausgesucht von:</div>
      <div class="yc-ann__ingame-player">${data.player_name || '—'}</div>
    </div>`;

  answersWrap.classList.remove('is-invisible');
  if (timerWrap) timerWrap.classList.add('is-invisible');

  const ranked = data.players_ranked || [];
  maxTvPlayers = computeMaxTvPlayers();
  currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
  renderPlayersRanked(ranked);
  resetPlayerClassesForNewQuestion();

  showLayer(layerGame);

  // Play announcement audio, then player name audio
  if (data.announcement_audio) {
    await playOnceReturn(SFX_BASE + data.announcement_audio);
  }

  const nameSrc = getPlayerAudioSrc(data.player_name);
  if (nameSrc) {
    await playOnceReturn(nameSrc);
  }

  socket.emit('module_event', { action: 'announcement_finished' });
});

// ---------------------------------------------------------------------------
// LAYER 4: MC Game (reusing Punktesammler logic)
// ---------------------------------------------------------------------------

const answersWrap = document.getElementById('options-grid');
const timerWrap   = document.getElementById('game-timer');
const qImageWrap  = document.getElementById('question-image-wrap');
const qImageEl    = document.getElementById('question-image');
const dummyInWrap = document.getElementById('dummy-inbox-wrap');
const dummyInImg  = document.getElementById('dummy-inbox-img');
const psRoot      = document.querySelector('.yc-tv');  // for has-image class

let timerRAF     = null;
let unveilTO     = null;
let currentPlayerOrder = [];
let maxTvPlayers = 9;

// --- Timer helpers ---
function parseMs(val) {
  if (val === null || val === undefined) return null;
  if (typeof val === 'number') {
    if (val > 1e12) return val;
    if (val > 1e9)  return val * 1000;
    return val;
  }
  if (typeof val === 'string') {
    const t = Date.parse(val);
    return Number.isFinite(t) ? t : null;
  }
  return null;
}

function clearTimer() {
  if (timerRAF) { cancelAnimationFrame(timerRAF); timerRAF = null; }
}

function clearUnveil() {
  if (unveilTO) { clearTimeout(unveilTO); unveilTO = null; }
}

function startTimerVisual(seconds, startedAt) {
  clearTimer();
  if (timerWrap) timerWrap.style.setProperty('--p', '0%');

  const durMs       = Math.max(0.001, Number(seconds || 1)) * 1000;
  const startedAtMs = parseMs(startedAt);

  if (startedAtMs !== null) {
    const endAtMs = startedAtMs + durMs;
    const tick = () => {
      const now = nowSyncedMs();
      const pct = Math.min(100, Math.max(0, ((now - startedAtMs) / durMs) * 100));
      if (timerWrap) timerWrap.style.setProperty('--p', pct + '%');
      if (now < endAtMs) timerRAF = requestAnimationFrame(tick);
      else clearTimer();
    };
    timerRAF = requestAnimationFrame(tick);
    return;
  }

  const start = performance.now();
  const tick = now => {
    const pct = Math.min(100, ((now - start) / durMs) * 100);
    if (timerWrap) timerWrap.style.setProperty('--p', pct + '%');
    if (pct < 100) timerRAF = requestAnimationFrame(tick);
    else clearTimer();
  };
  timerRAF = requestAnimationFrame(tick);
}

function stopTimerVisual() {
  clearTimer();
  if (timerWrap) timerWrap.style.setProperty('--p', '0%');
}

function ensureVisible() {
  if (answersWrap) answersWrap.classList.remove('is-hidden');
  if (timerWrap)   timerWrap.classList.remove('is-hidden');
}

function hideAnswersAndTimer() {
  ensureVisible();
  if (answersWrap) answersWrap.classList.add('is-invisible');
  if (timerWrap)   timerWrap.classList.add('is-invisible');
}

function showAnswersAndTimer() {
  ensureVisible();
  if (answersWrap) answersWrap.classList.remove('is-invisible');
  if (timerWrap)   timerWrap.classList.remove('is-invisible');
}

function unveilAnswersOnly() {
  ensureVisible();
  if (answersWrap) answersWrap.classList.remove('is-invisible');
  if (timerWrap)   timerWrap.classList.add('is-invisible');
  playSfx('answerUnveiled');
}

function scheduleAnswersUnveilAt(isoTs) {
  clearUnveil();
  const tMs = parseMs(isoTs);
  if (tMs === null) return;
  const delay = tMs - nowSyncedMs();
  if (delay <= 0) { unveilAnswersOnly(); return; }
  unveilTO = setTimeout(() => { unveilTO = null; unveilAnswersOnly(); }, delay);
}

function resetAnswerClasses() {
  document.querySelectorAll('#options-grid .ps__answer').forEach(el =>
    el.classList.remove('is-correct', 'is-faded'));
}

function clearAllScorePops() {
  document.querySelectorAll('.ps__scorePop').forEach(n => n.remove());
}

function resetPlayerClassesForNewQuestion() {
  const sb = document.getElementById('player-sidebar');
  if (!sb) return;
  sb.querySelectorAll('.ps__player').forEach(row => {
    row.classList.remove('is-answered','choice-0','choice-1','choice-2','choice-3','is-correct','is-wrong');
    row.querySelectorAll('.ps__scorePop').forEach(n => n.remove());
  });
}

function getPlayerRow(pid) {
  return document.getElementById(`player-${pid}`);
}

function computeMaxTvPlayers() {
  const sb = document.getElementById('player-sidebar');
  if (!sb) return 9;
  const cs  = window.getComputedStyle(sb);
  const gap = parseFloat(cs.gap || '0') || 0;
  const h   = (sb.closest('.ps__sidebar') || sb).getBoundingClientRect().height;
  let card  = sb.querySelector('.ps__playerCard');
  if (!card) {
    const tmp = document.createElement('div');
    tmp.className = 'ps__player';
    tmp.innerHTML = '<div class="ps__playerCard"><div class="ps__playerName">X</div><div class="ps__playerScore">0</div></div>';
    sb.appendChild(tmp);
    card = tmp.querySelector('.ps__playerCard');
    const th = card ? card.getBoundingClientRect().height : 0;
    tmp.remove();
    if (!th) return 9;
    return Math.max(1, Math.floor((h + gap) / (th + gap)));
  }
  const th = card.getBoundingClientRect().height;
  if (!th) return 9;
  return Math.max(1, Math.floor((h + gap) / (th + gap)));
}

function renderPlayersRanked(ranked) {
  const sb = document.getElementById('player-sidebar');
  if (!sb) return;
  sb.innerHTML = '';
  maxTvPlayers = computeMaxTvPlayers();
  (ranked || []).slice(0, maxTvPlayers).forEach(p => {
    const row = document.createElement('div');
    row.className = 'ps__player';
    row.id = `player-${p.player_id}`;
    row.innerHTML = `<div class="ps__playerCard"><div class="ps__playerName">${p.name}</div><div class="ps__playerScore">${p.score}</div></div>`;
    sb.appendChild(row);
  });
}

function updateScoresInPlace(ranked) {
  const scoreMap = {};
  (ranked || []).slice(0, maxTvPlayers).forEach(p => { scoreMap[p.player_id] = p.score; });
  currentPlayerOrder.forEach(pid => {
    const row = getPlayerRow(pid);
    if (!row) return;
    const el = row.querySelector('.ps__playerScore');
    if (el && Object.prototype.hasOwnProperty.call(scoreMap, pid)) el.textContent = scoreMap[pid];
  });
}

function setQuestionImage(imageFile) {
  const fallback = '/punktesammler/media/dummy.svg';
  const file = (imageFile || '').trim();

  if (qImageWrap) qImageWrap.classList.add('is-hidden');
  if (dummyInWrap) dummyInWrap.classList.add('is-hidden');

  if (!file) {
    if (dummyInWrap) dummyInWrap.classList.remove('is-hidden');
    if (dummyInImg)  dummyInImg.src = fallback;
    return;
  }

  if (qImageWrap) qImageWrap.classList.remove('is-hidden');
  const src = (file.startsWith('http') || file.startsWith('/')) ? file : `/yourcategory/media/images/${file}`;
  if (qImageEl) {
    qImageEl.src = src;
    qImageEl.onerror = () => { qImageEl.onerror = null; qImageEl.src = fallback; };
  }
}

// --- MC Socket Events ---

socket.on('show_question', data => {
  clearTimer();
  clearUnveil();
  clearAllScorePops();

  startBgm();
  playQuestionAudio(data.audio);
  setQuestionImage(data.image);
  document.getElementById('question-text').innerText = data.text;

  answersWrap.innerHTML = '';
  (data.options || []).forEach((opt, i) => {
    const div = document.createElement('div');
    div.className = `ps__answer ps__answer--${i}`;
    div.id = `answer-${i}`;
    div.innerText = opt;
    answersWrap.appendChild(div);
  });

  resetAnswerClasses();
  const ranked = data.players_ranked || [];
  maxTvPlayers = computeMaxTvPlayers();
  currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
  renderPlayersRanked(ranked);
  resetPlayerClassesForNewQuestion();
  hideAnswersAndTimer();

  if (data.answers_unveil_at || data.answersUnveilAt) {
    scheduleAnswersUnveilAt(data.answers_unveil_at || data.answersUnveilAt);
  }

  showLayer(layerGame);
});

socket.on('open_answers', data => {
  clearTimer();
  clearAllScorePops();
  showAnswersAndTimer();
  const dur = Number(data.duration || 15);
  const startedAt = data && (data.started_at ?? data.startedAt ?? data.opened_at ?? data.openedAt);
  startTimerVisual(dur, startedAt);
});

socket.on('close_answers', () => stopTimerVisual());

socket.on('player_logged_in', data => {
  const row = getPlayerRow(data.player_id);
  if (row) row.classList.add('is-answered');
  playSfx('answerEntered');
});

socket.on('reveal_player_answers', data => {
  stopBgm();
  stopTimerVisual();
  playSfx('revealPlayerAnswers');
  clearAllScorePops();
  showAnswersAndTimer();

  Object.entries(data.player_answers || {}).forEach(([pid, choice]) => {
    const row = getPlayerRow(pid);
    if (!row) return;
    row.classList.remove('is-answered','choice-0','choice-1','choice-2','choice-3','is-correct','is-wrong');
    row.classList.add(`choice-${choice}`);
  });
});

socket.on('unveil_correct', data => {
  playSfx('unveilCorrect');
  const ci = Number(data && data.correct_index);
  document.querySelectorAll('#options-grid .ps__answer').forEach((el, i) => {
    el.classList.remove('is-correct', 'is-faded');
    if (i === ci) el.classList.add('is-correct');
    else el.classList.add('is-faded');
  });
});

socket.on('show_resolution', data => {
  stopTimerVisual();
  playSfx('showResolution');
  clearAllScorePops();
  showAnswersAndTimer();

  const ci = data.correct_index;
  const pa = data.player_answers || {};

  document.querySelectorAll('.ps__player').forEach(row => {
    row.classList.remove('is-correct', 'is-wrong');
    const pid   = row.id.replace('player-', '');
    const choice = Object.prototype.hasOwnProperty.call(pa, pid) ? pa[pid] : null;
    if (choice !== null && Number(choice) === Number(ci)) row.classList.add('is-correct');
    else row.classList.add('is-wrong');
  });

  document.querySelectorAll('#options-grid .ps__answer').forEach((el, i) => {
    el.classList.remove('is-correct', 'is-faded');
    if (i === ci) el.classList.add('is-correct');
    else el.classList.add('is-faded');
  });
});

socket.on('show_scoring', data => {
  const gained   = data.gained || {};
  const anyPts   = Object.values(gained).some(g => Number(g) > 0);

  clearAllScorePops();

  if (data.players_ranked && Array.isArray(data.players_ranked)) {
    maxTvPlayers = computeMaxTvPlayers();
    currentPlayerOrder = data.players_ranked.slice(0, maxTvPlayers).map(p => p.player_id);
    renderPlayersRanked(data.players_ranked);
  }

  if (!anyPts) return;
  playSfx('pointsUnveiled');

  Object.entries(gained).forEach(([pid, g]) => {
    if (Number(g) > 0) {
      const row = getPlayerRow(pid);
      if (!row) return;
      const pop = document.createElement('div');
      pop.className = 'ps__scorePop';
      pop.textContent = `+${g}`;
      row.appendChild(pop);
    }
  });
});

socket.on('apply_scoring_update', data => {
  clearAllScorePops();
  updateScoresInPlace(data.players_ranked || []);
  playSfx('pointsUpdated');
});

// --- game_finished: reload ---
socket.on('game_finished', () => {
  try { stopBgmInput(); } catch (_) {}
  window.location.href = '/tv';
});

// Init
window.addEventListener('resize', () => { maxTvPlayers = computeMaxTvPlayers(); });
