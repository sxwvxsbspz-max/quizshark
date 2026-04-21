/* --- FILE: ./haveiever/static/tv.js --- */

socket.emit('register_tv');
socket.on('connect', () => {
  socket.emit('register_tv');
});

const videoLayer  = document.getElementById('video-layer');
const gameLayer   = document.getElementById('game-layer');
const videoPlayer = document.getElementById('phase-video');

const answersWrap = document.getElementById('options-grid');
const timerWrap   = document.querySelector('.ps__timer');

// IMAGE / DUMMY
const qImageWrap   = document.getElementById('question-image-wrap');
const qImageEl     = document.getElementById('question-image');
const dummyInWrap  = document.getElementById('dummy-inbox-wrap');
const dummyInImg   = document.getElementById('dummy-inbox-img');

// Root für Klassenumschaltung
const psRoot = document.querySelector('.ps');

// Poll-Meta (Votes Cast)
const pollMetaWrap = document.getElementById('poll-meta');
const votesCastEl  = document.getElementById('votes-cast');

let timerRAF = null;
let unveilTO = null;

/* ---------- Server-Clock Sync ---------- */
let clockOffsetMs = 0; // server_now_ms - local_now_ms
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
      <div class="ps__playerCard">
        <div class="ps__playerName">X</div>
        <div class="ps__playerScore">0</div>
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


/* ---------- Audio ---------- */
const questionAudio = new Audio();
questionAudio.preload = 'auto';
questionAudio.volume = 1.0;

/* ---------- Background Music (optional) ---------- */
const bgm = new Audio('/haveiever/media/gamesounds/background.mp3');
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
const SFX_BASE = '/haveiever/media/gamesounds';

function playSfxOverlap(file) {
  try {
    const a = new Audio(`${SFX_BASE}/${file}`);
    a.preload = 'auto';
    a.volume = 1.0;
    a.play().catch(() => {});
  } catch (_) {}
}

const sfxAnswerUnveiled = new Audio(`${SFX_BASE}/answerunveiled.mp3`);
const sfxPointsUnveiled = new Audio(`${SFX_BASE}/pointsunveiled.mp3`);
const sfxPointsUpdated  = new Audio(`${SFX_BASE}/pointsupdated.mp3`);

const sfxRevealPlayerAnswers = new Audio(`${SFX_BASE}/reveal_player_answers.mp3`);
const sfxUnveilCorrect       = new Audio(`${SFX_BASE}/unveil_correct.mp3`);
const sfxShowResolution      = new Audio(`${SFX_BASE}/show_resolution.mp3`);

[
  sfxAnswerUnveiled, sfxPointsUnveiled, sfxPointsUpdated,
  sfxRevealPlayerAnswers, sfxUnveilCorrect, sfxShowResolution
].forEach(a => {
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
    case 'unveilCorrect':
      playSfxSingle(sfxUnveilCorrect);
      return;
    case 'showResolution':
      playSfxSingle(sfxShowResolution);
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

  try {
    questionAudio.pause();
    questionAudio.currentTime = 0;
  } catch (_) {}

  stopBgm();

  try { sfxAnswerUnveiled.pause(); sfxAnswerUnveiled.currentTime = 0; } catch (_) {}
  try { sfxPointsUnveiled.pause(); sfxPointsUnveiled.currentTime = 0; } catch (_) {}
  try { sfxPointsUpdated.pause();  sfxPointsUpdated.currentTime  = 0; } catch (_) {}
  try { sfxRevealPlayerAnswers.pause(); sfxRevealPlayerAnswers.currentTime = 0; } catch (_) {}
  try { sfxUnveilCorrect.pause();       sfxUnveilCorrect.currentTime       = 0; } catch (_) {}
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

function ensureLayoutSlotsVisible() {
  if (answersWrap) answersWrap.classList.remove('is-hidden');
  if (timerWrap) timerWrap.classList.remove('is-hidden');
}

function hideAnswersAndTimer() {
  ensureLayoutSlotsVisible();
  if (answersWrap) answersWrap.classList.add('is-invisible');
  if (timerWrap) timerWrap.classList.add('is-invisible');
}

function unveilAnswersOnly() {
  ensureLayoutSlotsVisible();
  if (answersWrap) answersWrap.classList.remove('is-invisible');
  if (timerWrap) timerWrap.classList.add('is-invisible');
  playSfx('answerUnveiled');
}

function showAnswersAndTimer() {
  ensureLayoutSlotsVisible();
  if (answersWrap) answersWrap.classList.remove('is-invisible');
  if (timerWrap) timerWrap.classList.remove('is-invisible');
}

function resetAnswerClasses() {
  document.querySelectorAll('.ps__answer').forEach(el => {
    el.classList.remove('is-correct', 'is-faded');
  });
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

function setPollMeta(votesCast) {
  const vc = Number(votesCast || 0);
  if (pollMetaWrap) pollMetaWrap.classList.remove('is-hidden');
  if (votesCastEl) votesCastEl.innerHTML = `
  <span class="ps__votesNumber">${vc}</span>
  <span class="ps__votesLabel">Antworten</span>
`;
}

function hidePollMeta() {
  if (pollMetaWrap) pollMetaWrap.classList.add('is-hidden');
  if (votesCastEl) votesCastEl.textContent = '';
}


/* ---------- IMAGE / DUMMY ---------- */
function setQuestionImage(imageFile) {
  const fallback = '/haveiever/media/dummy.svg';
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
    qImageEl.src = isAbsolute ? file : `/haveiever/media/images/${file}`;
    qImageEl.onerror = () => {
      qImageEl.onerror = null;
      qImageEl.src = fallback;
    };
  }
}


/* ---------- Ranked Player Rendering (Dynamic) ---------- */
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
      <div class="ps__playerCard">
        <div class="ps__playerName">${p.name}</div>
        <div class="ps__playerScore">${p.score}</div>
      </div>
    `;

    sidebar.appendChild(row);
  });
}

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
    if (startedAt > 1e12) return startedAt;          // ms
    if (startedAt > 1e9)  return startedAt * 1000;   // sec -> ms
    return startedAt;
  }

  if (typeof startedAt === "string") {
    const t = Date.parse(startedAt);
    return Number.isFinite(t) ? t : null;
  }

  return null;
}

function startTimerVisual(seconds, startedAt /* optional */) {
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


/* ---------- Unveil by absolute timestamp ---------- */
function scheduleAnswersUnveilAt(isoTs) {
  clearUnveil();

  const tMs = parseStartedAtToMs(isoTs);
  if (tMs === null) return;

  const delay = tMs - nowSyncedMs();
  if (delay <= 0) {
    unveilAnswersOnly();
    return;
  }

  unveilTO = setTimeout(() => {
    unveilTO = null;
    unveilAnswersOnly();
  }, delay);
}


/* ---------- Audio helpers ---------- */
function playAudioPromise(audioEl, src) {
  return new Promise(resolve => {
    if (!src) return resolve();

    try { audioEl.pause(); audioEl.currentTime = 0; } catch (_) {}
    audioEl.src = src;
    audioEl.load();

    const done = () => {
      audioEl.onended = null;
      audioEl.onerror = null;
      resolve();
    };

    audioEl.onended = done;
    audioEl.onerror = done;

    audioEl.play().catch(done);
  });
}

function playQuestionAudio(audioFile) {
  if (!audioFile) return Promise.resolve();
  return playAudioPromise(questionAudio, `/haveiever/media/audio/${audioFile}`);
}


/* =========================================================
   SOCKET EVENTS
   ========================================================= */

/*
  POLL (Have I ever)
  - show_poll: zeigt Ja/Nein + Timer + votes_cast
  - poll_update: markiert "hat gevotet" (ohne Ja/Nein) + votes_cast
  - close_poll: stoppt Timer (MC kommt danach via show_question)
*/

socket.on('show_poll', data => {
  showGame();
  clearTimer();
  clearUnveil();
  clearAllScorePops();

  // Optional: BGM kann hier starten (wenn vorhanden)
  try {
    if (bgm && bgm.paused) startBgm();
  } catch (_) {}

  const txt = (data && data.text) ? String(data.text) : '';
  document.getElementById('question-text').innerText = txt;

  setQuestionImage(data && data.image);

  // Poll-Options (TV nur Anzeige)
  answersWrap.innerHTML = '';
  const yesNo = ['JA', 'NEIN']; // JA links, NEIN rechts
  yesNo.forEach((label, i) => {
    const div = document.createElement('div');
    div.className = `ps__answer ${i === 0 ? 'poll-yes' : 'poll-no'}`;
    div.id = `answer-${i}`;
    div.innerText = label;
    answersWrap.appendChild(div);
  });

  resetAnswerClasses();

  // Player rendern
  if (data && Array.isArray(data.players_ranked)) {
    const ranked = data.players_ranked || [];
    maxTvPlayers = computeMaxTvPlayers();
    currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
    renderPlayersRanked(ranked);
  }

  resetPlayerClassesForNewQuestion();

  // wer schon gevotet hat -> als answered markieren (anonym, ohne Ja/Nein)
  const voted = (data && Array.isArray(data.voted_players)) ? data.voted_players : [];
  voted.forEach(pid => {
    const row = getPlayerRow(pid);
    if (row) row.classList.add('is-answered');
  });

// Im Poll (JA/NEIN) KEINE Votes-Kachel anzeigen
hidePollMeta();


  // Timer + Answers sichtbar
  showAnswersAndTimer();

  const dur = Number((data && (data.total_duration ?? data.duration)) || 12);
  const startedAt = data && (data.started_at ?? data.startedAt);
  startTimerVisual(dur, startedAt);

  // Poll-Pre-Audio (wenn vorhanden)
  const pre = data && data.pre_audio ? String(data.pre_audio) : '';
  if (pre) playQuestionAudio(pre);

  // SFX: Options erscheinen
  playSfx('answerUnveiled');
});

socket.on('poll_update', data => {
  const pid = data && data.player_id ? String(data.player_id) : '';
  if (pid) {
    const row = getPlayerRow(pid);
    if (row) row.classList.add('is-answered');
  }

  // WICHTIG: Im Poll (JA/NEIN) die Votes-Box NIE anfassen.
  // Die Votes-Box wird NUR in show_question (MC-Phase) gesetzt/angezeigt.

  playSfx('answerEntered');
});


socket.on('close_poll', () => {
  stopTimerVisual();
  hidePollMeta();
  // Screen bleibt stehen bis show_question kommt
});



/*
  MC-Teil (mc_standard)
*/

socket.on('show_question', data => {
  showGame();
  clearTimer();
  clearUnveil();
  clearAllScorePops();

  // BGM nur weiterlaufen lassen (falls vorhanden)
  try {
    if (bgm && bgm.paused) bgm.play().catch(() => {});
  } catch (_) {}

  setQuestionImage(data && data.image);

  document.getElementById('question-text').innerText = data && data.text ? String(data.text) : '';

  // votes_cast aus Poll im MC anzeigen
  setPollMeta(data && data.votes_cast);

  answersWrap.innerHTML = '';
  (data.options || []).forEach((opt, i) => {
    const div = document.createElement('div');
    div.className = `ps__answer ps__answer--${i}`;
    div.id = `answer-${i}`;
    div.innerText = opt;
    answersWrap.appendChild(div);
  });

  resetAnswerClasses();

  const ranked = (data.players_ranked || []);
  maxTvPlayers = computeMaxTvPlayers();
  currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
  renderPlayersRanked(ranked);

  resetPlayerClassesForNewQuestion();
  hideAnswersAndTimer();

  // Question Audio (MC)
  const a = data && data.audio ? String(data.audio) : '';
  if (a) playQuestionAudio(a);

  // Answers schon vor open_answers planen (Intro-Delay)
  if (data && (data.answers_unveil_at || data.answersUnveilAt)) {
    scheduleAnswersUnveilAt(data.answers_unveil_at || data.answersUnveilAt);
  }
});

socket.on('open_answers', data => {
  clearTimer();
  clearAllScorePops();

  showAnswersAndTimer();

  const dur = Number(data.duration || 15);
  const startedAt = data && (data.started_at ?? data.startedAt ?? data.opened_at ?? data.openedAt);

  startTimerVisual(dur, startedAt);
});

socket.on('close_answers', () => {
  stopTimerVisual();
});

socket.on('player_logged_in', data => {
  const pid = data && data.player_id;
  const row = getPlayerRow(pid);
  if (row) row.classList.add('is-answered');
  playSfx('answerEntered');
});

socket.on('reveal_player_answers', data => {
  stopTimerVisual();
  playSfx('revealPlayerAnswers');
  clearAllScorePops();
  showAnswersAndTimer();

  Object.entries(data.player_answers || {}).forEach(([playerId, choice]) => {
    const row = getPlayerRow(playerId);
    if (!row) return;

    row.classList.remove(
      'is-answered',
      'choice-0', 'choice-1', 'choice-2', 'choice-3',
      'is-correct', 'is-wrong'
    );

    row.classList.add(`choice-${choice}`);
  });
});

socket.on('unveil_correct', data => {
  playSfx('unveilCorrect');
  const correctIdx = Number(data && data.correct_index);

  document.querySelectorAll('.ps__answer').forEach((el, i) => {
    el.classList.remove('is-correct', 'is-faded');
    if (i === correctIdx) el.classList.add('is-correct');
    else el.classList.add('is-faded');
  });
});

socket.on('show_resolution', data => {
  stopBgm();
  playSfx('showResolution');

  stopTimerVisual();
  clearAllScorePops();
  showAnswersAndTimer();

  const correctIdx = data.correct_index;
  const playerAnswers = data.player_answers || {};

  document.querySelectorAll('.ps__player').forEach(row => {
    row.classList.remove('is-correct', 'is-wrong');

    const playerId = row.id.replace('player-', '');
    const choice = Object.prototype.hasOwnProperty.call(playerAnswers, playerId)
      ? playerAnswers[playerId]
      : null;

    const isCorrect = (choice !== null && Number(choice) === Number(correctIdx));

    if (isCorrect) row.classList.add('is-correct');
    else row.classList.add('is-wrong');
  });

  document.querySelectorAll('.ps__answer').forEach((el, i) => {
    el.classList.remove('is-correct', 'is-faded');
    if (i === Number(correctIdx)) el.classList.add('is-correct');
    else el.classList.add('is-faded');
  });
});


/*
  SCORING
  - show_scoring: zeigt NUR "+Punkte" (Scores bleiben wie angezeigt)
  - apply_scoring_update: aktualisiert NUR die Scores (und entfernt "+Punkte")
*/

socket.on('show_scoring', data => {
  const gainedObj = data.gained || {};
  const anyDelta = Object.values(gainedObj).some(g => Number(g) !== 0);

  clearAllScorePops();

  if (data.players_ranked && Array.isArray(data.players_ranked)) {
    const ranked = (data.players_ranked || []);
    maxTvPlayers = computeMaxTvPlayers();
    currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
    renderPlayersRanked(ranked);
  }

  if (!anyDelta) {
    return;
  }

  playSfx('pointsUnveiled');

  Object.entries(gainedObj).forEach(([playerId, gRaw]) => {
    const g = Number(gRaw) || 0;
    if (g === 0) return;

    const row = getPlayerRow(playerId);
    if (!row) return;

    const pop = document.createElement('div');
    pop.className = 'ps__scorePop';

    if (g > 0) pop.classList.add('is-plus');
    else if (g < 0) pop.classList.add('is-minus');

    pop.textContent = (g > 0) ? `+${g}` : `${g}`;
    row.appendChild(pop);
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

  // Poll-Meta zurück (neue Runde beginnt beim Video)
  hidePollMeta();

  showVideo(`/haveiever/media/frage${data.round}.mp4`);
});


/* ---------- Init ---------- */
updateMaxTvPlayers();
showVideo();

