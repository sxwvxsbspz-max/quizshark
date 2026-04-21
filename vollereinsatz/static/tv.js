/* --- FILE: ./vollereinsatz/static/tv.js --- */


socket.emit('register_tv');
socket.on('connect', () => {
  socket.emit('register_tv');
});

const videoLayer  = document.getElementById('video-layer');
const gameLayer   = document.getElementById('game-layer');
const videoPlayer = document.getElementById('phase-video');

const answersWrap = document.getElementById('options-grid');
const timerWrap   = document.querySelector('.ps__timer');

// IMAGE / DUMMY (BESTEHEND)
const qImageWrap   = document.getElementById('question-image-wrap');
const qImageEl     = document.getElementById('question-image');
const dummyInWrap  = document.getElementById('dummy-inbox-wrap');
const dummyInImg   = document.getElementById('dummy-inbox-img');

// NEU: Root für Klassenumschaltung
const psRoot = document.querySelector('.ps');

let timerRAF = null;

// NEU: Answer unveil scheduling
let unveilTO = null;

/* ---------- NEU: Server-Clock Sync ---------- */
let clockOffsetMs = 0; // server_now_ms - local_now_ms
function nowSyncedMs() {
  return Date.now() + clockOffsetMs;
}

socket.on('server_time', (data) => {
  const serverNow = data && typeof data.server_now === "number" ? data.server_now : null;
  if (serverNow === null) return;

  // Offset so setzen, dass nowSyncedMs() ~= serverNow
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


  // Wenn schon ein Card-Element existiert: daran messen
  let sampleCard = sidebar.querySelector('.ps__playerCard');

  // Falls noch nichts gerendert: temporär messen
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

// initial + bei Resize neu berechnen
window.addEventListener('resize', updateMaxTvPlayers);


/* ---------- Question Audio ---------- */
const questionAudio = new Audio();
questionAudio.preload = 'auto';
questionAudio.volume = 1.0;

/* ---------- NEU: Category Audio ---------- */
const categoryAudio = new Audio();
categoryAudio.preload = 'auto';
categoryAudio.volume = 1.0;

/* ---------- Background Music ---------- */
const bgm = new Audio('/vollereinsatz/media/gamesounds/background.mp3');
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
const SFX_BASE = '/vollereinsatz/media/gamesounds';

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

// NEU: weitere "single" SFX, damit keine MP3-Namen hardcoded in Events stehen
const sfxRevealPlayerAnswers = new Audio(`${SFX_BASE}/reveal_player_answers.mp3`);
const sfxUnveilCorrect       = new Audio(`${SFX_BASE}/unveil_correct.mp3`);
const sfxShowResolution      = new Audio(`${SFX_BASE}/show_resolution.mp3`);

[sfxAnswerUnveiled, sfxPointsUnveiled, sfxPointsUpdated, sfxRevealPlayerAnswers, sfxUnveilCorrect, sfxShowResolution].forEach(a => {
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

// NEU: zentraler SFX-Wrapper (alles single, außer answerEntered = overlap)
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

  // NEU: Moderations-Queue hart stoppen
  resetVoiceQueue();

  try {
    questionAudio.pause();
    questionAudio.currentTime = 0;
  } catch (_) {}

  try {
    categoryAudio.pause();
    categoryAudio.currentTime = 0;
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

// NEU: Nur Antworten enthüllen (Timer bleibt hidden bis open_answers)
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

/* =========================================================
   NEU: Wager-Column (links im Panel)
   ========================================================= */

const wagerCol = document.getElementById('wager-column');

/* =========================================================
   NEU: Wager-UI Persistenz-State (bleibt bis Scoring)
   ========================================================= */
let wagerUIActive = false;                 // sobald show_wager gestartet wurde
let wagerSetByPlayer = {};                 // { playerId: true }
let wagerValueByPlayer = {};               // { playerId: number }
let wagerUnveiled = false;                 // nachdem unveil_wager kam

// NEU: Zustände nach Answer/Resolution
let wagerAnsweredByPlayer = {};            // { playerId: true } -> weißes Leuchten
let wagerResultByPlayer = {};              // { playerId: "correct"|"wrong" }
let wagerChoiceByPlayer = {};              // { playerId: 0|1|2|3 }


function resetWagerUIState() {
  wagerUIActive = false;
  wagerSetByPlayer = {};
  wagerValueByPlayer = {};
  wagerUnveiled = false;

  // NEU
  wagerAnsweredByPlayer = {};
  wagerResultByPlayer = {};
}


function applyWagerUIStateToVisibleBoxes() {
  const visible = (currentPlayerOrder || []).slice(0, maxTvPlayers);

  visible.forEach(pid => {
    if (wagerSetByPlayer[pid]) setWagerSet(pid);

    if (wagerUnveiled && Object.prototype.hasOwnProperty.call(wagerValueByPlayer, pid)) {
      setWagerUnveiled(pid, wagerValueByPlayer[pid]);
    }

    // NEU: answered (weiß)
    if (wagerAnsweredByPlayer[pid]) {
      setWagerAnswered(pid);
    }

    // Choice-Glow (Antwortfarbe) – gilt ab reveal_player_answers
    if (Object.prototype.hasOwnProperty.call(wagerChoiceByPlayer, pid)) {
      setWagerChoice(pid, wagerChoiceByPlayer[pid]);
    }

    // Result überschreibt Choice (grün/rot)
    if (wagerResultByPlayer[pid] === "correct") {
      clearWagerChoice(pid);
      clearWagerResult(pid);
      setWagerCorrect(pid);
    } else if (wagerResultByPlayer[pid] === "wrong") {
      clearWagerChoice(pid);
      clearWagerResult(pid);
      setWagerWrong(pid);
    }

  });
}



function hideWagerColumn() {
  if (!wagerCol) return;
  wagerCol.classList.remove('is-visible');
  wagerCol.innerHTML = '';
}

function showWagerColumn() {
  if (!wagerCol) return;
  wagerCol.classList.add('is-visible');
}

function renderWagerBoxesForCurrentOrder() {
  if (!wagerCol) return;

  wagerCol.innerHTML = '';

  // gleiche sichtbare Spieleranzahl wie Sidebar
  const list = (currentPlayerOrder || []).slice(0, maxTvPlayers);

  list.forEach(pid => {
    const div = document.createElement('div');
    div.className = 'ps__wagerBox';
    div.id = `wagerbox-${pid}`;
    div.textContent = ''; // bewusst leer (Zahl erst bei unveil)
    wagerCol.appendChild(div);
  });
}

function setWagerSet(pid) {
  const el = document.getElementById(`wagerbox-${pid}`);
  if (!el) return;
  el.classList.add('wager-set');
}


function setWagerUnveiled(pid, value) {
  const el = document.getElementById(`wagerbox-${pid}`);
  if (!el) return;
  el.classList.add('wager-set', 'wager-unveiled');
  el.textContent = `${value}`;
}

function clearWagerResult(pid) {
  const el = document.getElementById(`wagerbox-${pid}`);
  if (!el) return;
  el.classList.remove('is-correct', 'is-wrong');
}

function setWagerAnswered(pid) {
  const el = document.getElementById(`wagerbox-${pid}`);
  if (!el) return;
  el.classList.add('is-answered');
}

function setWagerCorrect(pid) {
  const el = document.getElementById(`wagerbox-${pid}`);
  if (!el) return;
  el.classList.add('is-correct');
}

function setWagerWrong(pid) {
  const el = document.getElementById(`wagerbox-${pid}`);
  if (!el) return;
  el.classList.add('is-wrong');
}

function clearWagerChoice(pid) {
  const el = document.getElementById(`wagerbox-${pid}`);
  if (!el) return;
  el.classList.remove('choice-0','choice-1','choice-2','choice-3');
}

function setWagerChoice(pid, choice) {
  const el = document.getElementById(`wagerbox-${pid}`);
  if (!el) return;

  // WICHTIG: Weiß-States entfernen, sonst bleibt der Rahmen weiß
  el.classList.remove('is-answered'); // weißer Glow
  el.classList.remove('wager-set');   // weißer Rahmen
  el.classList.remove('is-correct','is-wrong'); // safety

  clearWagerChoice(pid);
  el.classList.add(`choice-${choice}`);
}





/* ---------- IMAGE / DUMMY ---------- */
function setQuestionImage(imageFile) {
  const fallback = '/vollereinsatz/media/dummy.svg';
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
    qImageEl.src = isAbsolute ? file : `/vollereinsatz/media/images/${file}`;
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

/* ---------- Scores updaten (Dynamic) ---------- */
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
/*
  Timer-Umbau (nur hier):
  - Wenn Backend "started_at" mitliefert (ISO oder ms), nutzen wir echte Uhrzeit (Date.now),
    damit Reconnect/Delay korrekt bleibt.
  - Fallback bleibt: "duration" allein -> performance.now (wie vorher).
*/

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


  // Fallback (wie vorher)
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

/* ---------- NEU: Unveil by absolute timestamp ---------- */
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


/* ---------- Audio ---------- */

// NEU: Voiceover Ordner (Intros + PleaseBet)
const VO_BASE = '/vollereinsatz/media/audio';

// NEU: konfigurierbare Pausen
const PAUSE_AFTER_CATEGORY_INTRO_MS = 500;
const PAUSE_AFTER_CATEGORY_AUDIO_MS = 500;
const PAUSE_AFTER_QUESTION_INTRO_MS = 500;

// NEU: Pools (1–5)
const CATEGORY_INTRO_POOL = [
  'categoryintro1.mp3','categoryintro2.mp3','categoryintro3.mp3','categoryintro4.mp3','categoryintro5.mp3'
];
const PLEASE_BET_POOL = [
  'pleasebet1.mp3','pleasebet2.mp3','pleasebet3.mp3','pleasebet4.mp3','pleasebet5.mp3'
];
const QUESTION_INTRO_POOL = [
  'questionintro1.mp3','questionintro2.mp3','questionintro3.mp3','questionintro4.mp3','questionintro5.mp3'
];

// NEU: 1 Voiceover-Player + Queue (damit nichts überlappt)
const voiceOver = new Audio();
voiceOver.preload = 'auto';
voiceOver.volume = 1.0;

let voiceQueue = Promise.resolve();
let voiceToken = 0;

let lastCategoryIntro = null;
let lastPleaseBet = null;
let lastQuestionIntro = null;

function stopAudioEl(a) {
  try { a.pause(); a.currentTime = 0; } catch (_) {}
}

function resetVoiceQueue() {
  voiceToken++;
  voiceQueue = Promise.resolve();
  stopAudioEl(voiceOver);
}

function sleepMs(ms) {
  return new Promise(res => setTimeout(res, Math.max(0, Number(ms) || 0)));
}

function pickRandomNoRepeat(pool, last) {
  const list = (pool || []).filter(Boolean);
  if (list.length === 0) return null;
  if (list.length === 1) return list[0];

  let choice = list[Math.floor(Math.random() * list.length)];
  if (choice === last) {
    // 1x neu ziehen reicht bei kleinen Pools
    choice = list[Math.floor(Math.random() * list.length)];
  }
  return choice;
}

// spielt ein Audio-Element und resolved bei Ende/Fehler
function playAudioPromise(audioEl, src) {
  return new Promise(resolve => {
    if (!src) return resolve();

    stopAudioEl(audioEl);
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

// queue helper: serialisiert Sequenzen + kann bei Phasenwechsel abgebrochen werden
function enqueueVoice(fnAsync) {
  const tokenAtEnqueue = voiceToken;
  voiceQueue = voiceQueue
    .then(async () => {
      if (tokenAtEnqueue !== voiceToken) return;
      await fnAsync();
    })
    .catch(() => {});
}

// bleibt wie gehabt, aber jetzt als Promise nutzbar
function playQuestionAudio(audioFile) {
  if (!audioFile) return Promise.resolve();
  return playAudioPromise(questionAudio, `/vollereinsatz/media/audio/${audioFile}`);
}


function playCategoryAudio(audioFile) {
  if (!audioFile) return Promise.resolve();
  return playAudioPromise(categoryAudio, `/vollereinsatz/media/audio/${audioFile}`);
}


function playVoiceOverFile(filename) {
  if (!filename) return Promise.resolve();
  return playAudioPromise(voiceOver, `${VO_BASE}/${filename}`);
}


/* ---------- Socket Events ---------- */

/*
  NEU: CATEGORY_INTRO
  - nutzt die EXISTIERENDEN UI-Slots:
    - question-text => category
    - options-grid  => leer (noch keine Wager-Kacheln)
  - SFX: keins extra (du wolltest analog zu Fragen; die "Action" startet bei show_wager)
*/
socket.on('show_category', data => {
  showGame();
  clearTimer();
  clearUnveil();
  clearAllScorePops();

  // NEU: Voice-Queue reset, damit nichts aus der letzten Runde reinläuft
  resetVoiceQueue();

  // BGM STARTET HIER und läuft durch bis du sie bewusst stoppst
  startBgm();

  // NEU: Moderation früh starten (0.5s nach show_category)
  setTimeout(() => {
    enqueueVoice(async () => {
      const ci = pickRandomNoRepeat(CATEGORY_INTRO_POOL, lastCategoryIntro);
      lastCategoryIntro = ci;
      await playVoiceOverFile(ci);
      await sleepMs(PAUSE_AFTER_CATEGORY_INTRO_MS);

      const catA = data && data.categoryaudio ? String(data.categoryaudio) : '';
      if (catA) {
        await playCategoryAudio(catA);
        await sleepMs(PAUSE_AFTER_CATEGORY_AUDIO_MS);
      }

      const pb = pickRandomNoRepeat(PLEASE_BET_POOL, lastPleaseBet);
      lastPleaseBet = pb;
      await playVoiceOverFile(pb);
    });
  }, 500);

    document.getElementById('question-text').innerText = (data && data.category) ? `Kategorie: ${data.category}` : '';


  answersWrap.innerHTML = '';
  resetAnswerClasses();

  setQuestionImage(null);

    /* >>> NEU: Playerliste SOFORT korrekt rendern <<< */
  if (data && Array.isArray(data.players_ranked)) {
    const ranked = data.players_ranked;
    maxTvPlayers = computeMaxTvPlayers();
    currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
    renderPlayersRanked(ranked);
  }

  resetPlayerClassesForNewQuestion();
  hideAnswersAndTimer();

  // Wager-State reset (neue Runde / neue Category)
  resetWagerUIState();
  hideWagerColumn();
});




/*
  NEU: WAGER_OPEN
  - nutzt die EXISTIERENDEN UI-Slots:
    - question-text => category
    - options-grid  => 4 Einsatz-Kacheln
    - timer         => läuft wie open_answers (started_at + total_duration)
  - SFX: analog zum Frage-Unveil => answerUnveiled beim Anzeigen der Kacheln
*/
socket.on('show_wager', data => {
  showGame();
  clearTimer();
  clearUnveil();
  clearAllScorePops();

  // WICHTIG: KEIN startBgm() hier -> läuft aus show_category weiter

   document.getElementById('question-text').innerText = (data && data.category) ? `Kategorie: ${data.category}` : '';


  const values = (data && data.wager_values) ? data.wager_values : [25, 50, 100, 200];

  answersWrap.innerHTML = '';
  values.forEach((v, i) => {
    const div = document.createElement('div');
    div.className = `ps__answer ps__answer--${i}`;
    div.id = `answer-${i}`;
    div.innerText = `${v}`;
    answersWrap.appendChild(div);
  });

  resetAnswerClasses();

  // NEU: Sidebar-Player in Wager-Phase initial rendern (wichtig für die allererste Wager-Phase)
  if (data && Array.isArray(data.players_ranked)) {
    const ranked = data.players_ranked || [];
    maxTvPlayers = computeMaxTvPlayers();
    currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
    renderPlayersRanked(ranked);
  }


  // Snapshot: wer schon gesetzt hat -> Box sofort "aktiv" (ohne Zahl)
  wagerUIActive = true;

  // WICHTIG: Wager-Spalte + Boxen JETZT rendern (nicht erst bei show_question)
  showWagerColumn();
  renderWagerBoxesForCurrentOrder();

  const wagers = (data && data.wagers) ? data.wagers : {};
  Object.keys(wagers || {}).forEach(pid => {

    // merken + UI
    wagerSetByPlayer[pid] = true;
    setWagerSet(pid);
  });

  showAnswersAndTimer();


  const dur = Number((data && (data.total_duration ?? data.duration)) || 15);
  const startedAt = data && (data.started_at ?? data.startedAt);
  startTimerVisual(dur, startedAt);

  playSfx('answerUnveiled');
});



/*
  NEU: WAGER_UPDATE (entspricht player_logged_in vom Frage-Flow)
  - markiert im Sidebar den Spieler als "hat gesetzt"
  - SFX: answerEntered (gleiches File)
*/
socket.on('wager_update', data => {

  wagerUIActive = true;
  wagerSetByPlayer[data.player_id] = true;

  // Wager-Box aktivieren (ohne Zahl)
  setWagerSet(data.player_id);

  playSfx('answerEntered');
});



/*
  NEU: WAGER_UNVEIL (entspricht reveal_player_answers vom Frage-Flow)
  - stoppt Timer
  - zeigt pro Spieler den Einsatz als Pop (nutzt bestehende .ps__scorePop)
  - SFX: revealPlayerAnswers (gleiches File)
*/
socket.on('unveil_wager', data => {
  stopTimerVisual();
  playSfx('revealPlayerAnswers');
  clearAllScorePops();
  showAnswersAndTimer();

  // Wager-Spalte bleibt sichtbar, jetzt kommen die Zahlen rein
  wagerUIActive = true;
  wagerUnveiled = true;

  const wagers = (data && data.wagers) ? data.wagers : {};

  Object.entries(wagers || {}).forEach(([playerId, w]) => {

    wagerSetByPlayer[playerId] = true;
    wagerValueByPlayer[playerId] = Number(w);

    setWagerUnveiled(playerId, w);
  });
});



socket.on('show_question', data => {
  showGame();
  clearTimer();
  clearUnveil();
  clearAllScorePops();

  // BGM NICHT neu starten – es läuft seit show_category weiter.
  // Falls es aus irgendeinem Grund pausiert ist (z.B. Reconnect), nur weiterlaufen lassen:
  try {
    if (bgm && bgm.paused) bgm.play().catch(() => {});
  } catch (_) {}

  // NEU: Moderation für Question-Start:
  // random questionintro -> Pause -> dann Frage-Audio (data.audio)
  enqueueVoice(async () => {
    const qi = pickRandomNoRepeat(QUESTION_INTRO_POOL, lastQuestionIntro);
    lastQuestionIntro = qi;
    await playVoiceOverFile(qi);
    await sleepMs(PAUSE_AFTER_QUESTION_INTRO_MS);
    await playQuestionAudio(data.audio);
  });

  setQuestionImage(data.image);


  document.getElementById('question-text').innerText = data.text;

  answersWrap.innerHTML = '';
  data.options.forEach((opt, i) => {
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

  // WAGER bleibt sichtbar, falls es in dieser Runde aktiv ist (persistiert bis Scoring)
  // ABER: Question-spezifische States resetten (kein weißer Rahmen direkt bei Fragenstart)
  wagerAnsweredByPlayer = {};
  wagerResultByPlayer = {};
  wagerChoiceByPlayer = {};


  if (wagerUIActive) {
    showWagerColumn();
    renderWagerBoxesForCurrentOrder();
    applyWagerUIStateToVisibleBoxes();

    // FRAGE STARTET: "Wager gesetzt"-Weiß entfernen,
    // aber "Antwort abgegeben"-Weiß NICHT anfassen (kommt später über player_logged_in).
    document.querySelectorAll('.ps__wagerBox').forEach(el => {
      el.classList.remove('wager-set');
      // NICHT: el.classList.remove('is-answered');
    });
  } else {
    hideWagerColumn();
  }




  // NEU: Wenn Backend absolute Zeit liefert, Answers schon vor open_answers "geplant" enthüllen
  if (data && (data.answers_unveil_at || data.answersUnveilAt)) {
    scheduleAnswersUnveilAt(data.answers_unveil_at || data.answersUnveilAt);
  }
});



socket.on('open_answers', data => {
  clearTimer();
  clearAllScorePops();

  // open_answers ist weiterhin der definitive Start für Timer + Interaktion
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

  // NEU: auch Wager-Box weiß leuchten lassen, sobald Antwort abgegeben wurde
  if (pid) {
    wagerAnsweredByPlayer[pid] = true;
    setWagerAnswered(pid);
  }

  playSfx('answerEntered');
});


socket.on('reveal_player_answers', data => {
  stopTimerVisual();
  playSfx('revealPlayerAnswers');
  clearAllScorePops();
  showAnswersAndTimer();

  // WICHTIG: NICHT resetAnswerClasses() hier,
  // sonst werden is-correct/is-faded aus unveil_correct sofort wieder gelöscht.

  Object.entries(data.player_answers || {}).forEach(([playerId, choice]) => {
    const row = getPlayerRow(playerId);
    if (!row) return;

    row.classList.remove(
      'is-answered',
      'choice-0', 'choice-1', 'choice-2', 'choice-3',
      'is-correct', 'is-wrong'
    );

        row.classList.add(`choice-${choice}`);

    // NEU: Wager-Box in Answer-Farbe leuchten lassen (und Weiß entfernen)
    wagerAnsweredByPlayer[playerId] = false;
    delete wagerAnsweredByPlayer[playerId];

    wagerChoiceByPlayer[playerId] = Number(choice);
    setWagerChoice(playerId, Number(choice));


  });
});


socket.on('unveil_correct', data => {
  playSfx('unveilCorrect');
  const correctIdx = Number(data && data.correct_index);

  // Nur Antworten highlighten (keine Spieler richtig/falsch!)
  document.querySelectorAll('.ps__answer').forEach((el, i) => {
    el.classList.remove('is-correct', 'is-faded');
    if (i === correctIdx) el.classList.add('is-correct');
    else el.classList.add('is-faded');
  });
});


socket.on('show_resolution', data => {
  // NEU: Moderations-Queue hart stoppen
  resetVoiceQueue();

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

    if (isCorrect) {
      row.classList.add('is-correct');
    } else {
      row.classList.add('is-wrong');
    }

    // NEU: Wager-Box ebenfalls grün/rot
    if (playerId) {
      wagerResultByPlayer[playerId] = isCorrect ? "correct" : "wrong";
      clearWagerChoice(playerId);
      clearWagerResult(playerId);
      if (isCorrect) setWagerCorrect(playerId);
      else setWagerWrong(playerId);
    }

  });


  document.querySelectorAll('.ps__answer').forEach((el, i) => {
    el.classList.remove('is-correct', 'is-faded');
    if (i === correctIdx) el.classList.add('is-correct');
    else el.classList.add('is-faded');
  });
});


/*
  SCORING (Timing NUR Backend)
  - show_scoring: zeigt NUR "+Punkte" (Scores bleiben wie angezeigt)
  - apply_scoring_update: aktualisiert NUR die Scores (und entfernt "+Punkte")
*/

socket.on('show_scoring', data => {
  const gainedObj = data.gained || {};

  // Bei Wager gibt es auch negative Werte – wir zeigen alles außer 0 an
  const anyDelta = Object.values(gainedObj).some(g => Number(g) !== 0);

  clearAllScorePops();

  // Scoring-Phase: Wager-Boxen komplett neutral (kein weiß, kein grün/rot)
  wagerResultByPlayer = {};
  document.querySelectorAll('.ps__wagerBox').forEach(el => {
    el.classList.remove('is-correct', 'is-wrong');  // grün/rot weg
    el.classList.remove('is-answered');            // weiß weg (Antwort abgegeben)
    el.classList.remove('wager-set');              // weiß weg (Wager gesetzt)
    el.classList.remove('choice-0','choice-1','choice-2','choice-3'); // Answer-Farbe weg
  });
  wagerChoiceByPlayer = {};



  // Optional: Reihenfolge/Anzeige stabilisieren
  if (data.players_ranked && Array.isArray(data.players_ranked)) {
    const ranked = (data.players_ranked || []);
    maxTvPlayers = computeMaxTvPlayers();
    currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
    renderPlayersRanked(ranked);
  }

  if (!anyDelta) {
    return;
  }

  // Punkte/Verluste anzeigen (keine Score-Änderung hier!)
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

    pop.textContent = (g > 0) ? `+${g}` : `${g}`; // negatives hat schon "-"
    row.appendChild(pop);

  });
});


socket.on('apply_scoring_update', data => {
  // Backend sagt: jetzt Scores übernehmen + Popups entfernen
  clearAllScorePops();

  // Optional: wenn Backend Reihenfolge ändert, kann man hier auch neu rendern.
  // Wir lassen die Reihenfolge bewusst stabil (currentPlayerOrder),
  // und aktualisieren nur die sichtbaren Scores.
  updateScoresInPlace(data.players_ranked || []);

  playSfx('pointsUpdated');
});

socket.on('play_round_video', data => {
  clearTimer();
  clearUnveil();
  clearAllScorePops();

  // neue Runde -> Wager-UI komplett zurücksetzen
  resetWagerUIState();
  hideWagerColumn();

  showVideo(`/vollereinsatz/media/frage${data.round}.mp4`);
});


/* ---------- Init ---------- */
updateMaxTvPlayers();
showVideo();
