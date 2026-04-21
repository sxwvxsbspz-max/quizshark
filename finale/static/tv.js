// --- FILE: ./finale/static/tv.js ---

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

  // Falls noch nichts gerendert: temporär messen (WICHTIG: gleicher Aufbau wie echte Card!)
  if (!sampleCard) {
    const tmp = document.createElement('div');
    tmp.className = 'ps__player';
    tmp.innerHTML = `
      <div class="ps__playerCard">
        <div class="ps__playerName">X</div>

        <div class="ps__playerRight">
          <div class="ps__jokerSlots">
            <div class="ps__jokerSlot" data-slot="1" data-type="empty">
              <img src="/awardjokers/media/joker_gold.svg" class="ps__joker ps__joker--gold">
              <img src="/awardjokers/media/joker_white.svg" class="ps__joker ps__joker--white">
            </div>
            <div class="ps__jokerSlot" data-slot="2" data-type="white">
              <img src="/awardjokers/media/joker_gold.svg" class="ps__joker ps__joker--gold">
              <img src="/awardjokers/media/joker_white.svg" class="ps__joker ps__joker--white">
            </div>
          </div>

          <div class="ps__playerRankBox">
            <span class="ps__scoreText">0</span>
          </div>
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

// initial + bei Resize neu berechnen
window.addEventListener('resize', updateMaxTvPlayers);


/* ---------- Question Audio ---------- */
const questionAudio = new Audio();
questionAudio.preload = 'auto';
questionAudio.volume = 1.0;

/* ---------- Background Music ---------- */
const bgm = new Audio('/finale/media/gamesounds/background.mp3');
bgm.preload = 'auto';
bgm.loop = true;
bgm.volume = 1.0;

// State
let bgmStartedOnce = false;
let bgmFadeRAF = null;
let bgmFadeToken = 0;

function cancelBgmFade(){
  if (bgmFadeRAF) {
    cancelAnimationFrame(bgmFadeRAF);
    bgmFadeRAF = null;
  }
}

function fadeBgmTo(targetVol, ms = 250){
  targetVol = Math.max(0, Math.min(1, Number(targetVol)));
  ms = Math.max(0, Number(ms || 0));

  bgmFadeToken += 1;
  const token = bgmFadeToken;

  cancelBgmFade();

  const from = Number(bgm.volume || 0);
  const start = performance.now();

  if (ms <= 0) {
    bgm.volume = targetVol;
    return;
  }

  const tick = (now) => {
    if (token !== bgmFadeToken) return;
    const t = Math.min(1, (now - start) / ms);
    bgm.volume = from + (targetVol - from) * t;
    if (t < 1) bgmFadeRAF = requestAnimationFrame(tick);
    else bgmFadeRAF = null;
  };

  bgmFadeRAF = requestAnimationFrame(tick);
}

function ensureBgmPlaying(){
  if (!bgmStartedOnce) {
    bgmStartedOnce = true;
    try { bgm.currentTime = 0; } catch (_) {}
  }
  if (bgm.paused) {
    bgm.play().catch(() => {});
  }
}

function duckBgm(){
  fadeBgmTo(0.22, 220);
}

function unduckBgm(){
  fadeBgmTo(1.0, 220);
}


/* ---------- Game SFX ---------- */
const SFX_BASE = '/finale/media/gamesounds';

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
// NEU: Finale-Elimination SFX
const sfxEliminatedAnnouncement = new Audio(`${SFX_BASE}/eliminated_announcement.mp3`);


[sfxAnswerUnveiled, sfxPointsUnveiled, sfxPointsUpdated, sfxRevealPlayerAnswers, sfxUnveilCorrect, sfxShowResolution, sfxEliminatedAnnouncement].forEach(a => {
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
    case 'eliminationAnnouncement':
      playSfxSingle(sfxEliminatedAnnouncement);
      return;
    case 'eliminationFly':
      playSfxOverlap('eliminated.mp3');
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

/* ---------- Player Name Audio (Finale) ---------- */
const PLAYER_SOUND_BASE = '/playerdata/playersounds/';
const PLAYER_SOUND_MAP_URL = PLAYER_SOUND_BASE + 'map.json';

let playerSoundMap = {};
let playerSoundMapPromise = null;
const playerSoundCache = new Map(); // filename -> Audio

async function ensurePlayerSoundMapLoaded(){
  if (!playerSoundMapPromise) {
    playerSoundMapPromise = fetch(PLAYER_SOUND_MAP_URL, { cache: 'no-cache' })
      .then(r => (r && r.ok) ? r.json() : ({}))
      .then(json => {
        playerSoundMap = (json && typeof json === 'object') ? json : {};
        return playerSoundMap;
      })
      .catch(() => {
        playerSoundMap = playerSoundMap || {};
        return playerSoundMap;
      });
  }
  return playerSoundMapPromise;
}

function normalizeName(name){
  let s = String(name || '').trim().toLowerCase();

  // NUR erstes Wort (wie bei dir im Leaderboard)
  if (s.includes(' ')) s = s.split(' ')[0];

  s = s
    .replace(/ä/g, 'ae')
    .replace(/ö/g, 'oe')
    .replace(/ü/g, 'ue')
    .replace(/ß/g, 'ss');

  s = s.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  s = s.replace(/[^a-z0-9]/g, '');
  return s;
}

function getPlayerNameFromRow(pid){
  const row = getPlayerRow(pid);
  if (!row) return '';
  const el = row.querySelector('.ps__playerName');
  return (el ? el.textContent : '').trim();
}

function getCachedPlayerNameAudio(pid){
  const name = getPlayerNameFromRow(pid);
  const key = normalizeName(name);
  const mapped = (playerSoundMap && key) ? playerSoundMap[key] : null;
  if (!mapped) return null;

  const file = String(mapped).trim();
  if (!file) return null;

  if (playerSoundCache.has(file)) return playerSoundCache.get(file);

  const a = new Audio(PLAYER_SOUND_BASE + file);
  a.preload = 'auto';
  a.volume = 1.0;
  playerSoundCache.set(file, a);
  return a;
}

function playAudioWait(audioEl){
  return new Promise(res => {
    if (!audioEl) return res();

    const done = () => {
      audioEl.onended = null;
      audioEl.onerror = null;
      res();
    };

    try { audioEl.pause(); audioEl.currentTime = 0; } catch (_) {}
    audioEl.onended = done;
    audioEl.onerror = done;

    audioEl.play().catch(done);
  });
}

/* ---------- Finale elimination announcements (random pool) ---------- */

// >>> Konfiguration: wie viele Varianten gibt es?
const ELIM_SINGLE_VARIANTS   = 8;  // eliminated_announcement_single_01..08.mp3
const ELIM_MULTIPLE_VARIANTS = 14;  // eliminated_announcement_multiple_01..06.mp3

function pad2(n){ return String(n).padStart(2, '0'); }

function buildSfxPool(prefix, count){
  const pool = [];
  for (let i = 1; i <= count; i++) {
    const a = new Audio(`${SFX_BASE}/${prefix}_${pad2(i)}.mp3`);
    a.preload = 'auto';
    a.volume = 1.0;
    pool.push(a);
  }
  return pool;
}

const sfxElimAnnounceSinglePool   = buildSfxPool('eliminated_announcement_single', ELIM_SINGLE_VARIANTS);
const sfxElimAnnounceMultiplePool = buildSfxPool('eliminated_announcement_multiple', ELIM_MULTIPLE_VARIANTS);

function pickRandom(pool){
  if (!pool || !pool.length) return null;
  return pool[Math.floor(Math.random() * pool.length)];
}


// fire-and-forget: map.json früh laden
ensurePlayerSoundMapLoaded();


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

videoPlayer.onended = function () {
  socket.emit('module_event', {
    scope: 'system',
    action: 'video_finished',
    payload: { at: Date.now() }
  });
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

function clampJokers(n){
  const x = Number(n || 0) || 0;
  return Math.max(0, Math.min(2, x));
}

function computeJokerSlots(jokersWhite, jokersGold){
  const w = clampJokers(jokersWhite);
  const g = clampJokers(jokersGold);

  // Default: beide leer
  let slot1 = 'none';
  let slot2 = 'none';

  const total = Math.min(2, w + g);

  if (total === 0) {
    slot1 = 'none';
    slot2 = 'none';
  } else if (total === 1) {
    // 1 Joker immer rechts, links leer
    // Wichtig: links NICHT "none" setzen, sonst würde CSS Slot2 nach links schieben
    slot1 = 'empty';
    slot2 = (g === 1) ? 'gold' : 'white';
  } else {
    // total === 2
    if (g === 2) {
      slot1 = 'gold';
      slot2 = 'gold';
    } else if (w === 2) {
      slot1 = 'white';
      slot2 = 'white';
    } else {
      // 1 gold + 1 white: white links, gold rechts
      slot1 = 'white';
      slot2 = 'gold';
    }
  }

  return { slot1, slot2 };
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
      'choice-0', 'choice-1', 'choice-2', 'choice-3', 'choice-4',
      'is-correct', 'is-wrong'
    );
    row.querySelectorAll('.ps__scorePop').forEach(n => n.remove());
  });
}

/* ---------- IMAGE / DUMMY ---------- */
function setQuestionImage(imageFile) {
  const fallback = '/finale/media/dummy.svg';
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
    qImageEl.src = isAbsolute ? file : `/finale/media/images/${file}`;
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

    const { slot1, slot2 } = computeJokerSlots(p.jokers_white, p.jokers_gold);

    row.innerHTML = `
      <div class="ps__playerCard">
        <div class="ps__playerName">${(p.name || '')}</div>

        <div class="ps__playerRight">
          <div class="ps__jokerSlots">
            <div class="ps__jokerSlot" data-slot="1" data-type="${slot1}">
              <img src="/awardjokers/media/joker_gold.svg" class="ps__joker ps__joker--gold">
              <img src="/awardjokers/media/joker_white.svg" class="ps__joker ps__joker--white">
            </div>
            <div class="ps__jokerSlot" data-slot="2" data-type="${slot2}">
              <img src="/awardjokers/media/joker_gold.svg" class="ps__joker ps__joker--gold">
              <img src="/awardjokers/media/joker_white.svg" class="ps__joker ps__joker--white">
            </div>
          </div>

          <div class="ps__playerRankBox">
            <span class="ps__scoreText">${p.score}</span>
          </div>
        </div>
      </div>
    `;

    sidebar.appendChild(row);
  });
}

/* ---------- Scores updaten (Dynamic) ---------- */
function updateScoresInPlace(playersRanked) {
  const list = (playersRanked || []).slice(0, maxTvPlayers);

  const map = {};
  list.forEach(p => { map[p.player_id] = p; });

  currentPlayerOrder.forEach(pid => {
    const row = getPlayerRow(pid);
    if (!row) return;

    const p = Object.prototype.hasOwnProperty.call(map, pid) ? map[pid] : null;
    if (!p) return;

    // Score aktualisieren
    const scoreEl = row.querySelector('.ps__scoreText');
    if (scoreEl) scoreEl.textContent = p.score;

    // Joker-Slots aktualisieren
    const { slot1, slot2 } = computeJokerSlots(p.jokers_white, p.jokers_gold);
    const s1 = row.querySelector('.ps__jokerSlot[data-slot="1"]');
    const s2 = row.querySelector('.ps__jokerSlot[data-slot="2"]');
    if (s1) s1.setAttribute('data-type', slot1);
    if (s2) s2.setAttribute('data-type', slot2);
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
function playQuestionAudio(audioFile) {
  if (!audioFile) return;
  try { questionAudio.pause(); questionAudio.currentTime = 0; } catch (_) {}
  questionAudio.src = `/finale/media/audio/${audioFile}`;
  questionAudio.load();
  questionAudio.play().catch(() => {});
}

/* ---------- Pause Overlay (Finale) ---------- */
let pauseOverlay = null;

function ensurePauseOverlay(){
  if (pauseOverlay) return pauseOverlay;

  pauseOverlay = document.createElement('div');
  pauseOverlay.id = 'pause-overlay';
  pauseOverlay.style.position = 'fixed';
  pauseOverlay.style.inset = '0';
  pauseOverlay.style.display = 'none';
  pauseOverlay.style.alignItems = 'center';
  pauseOverlay.style.justifyContent = 'center';
  pauseOverlay.style.background = 'rgba(0,0,0,0.85)';
  pauseOverlay.style.zIndex = '99999';
  pauseOverlay.innerHTML = `
    <div style="font-size:72px;font-weight:900;letter-spacing:3px;">
      PAUSE
    </div>
  `;
  document.body.appendChild(pauseOverlay);
  return pauseOverlay;
}

function showPauseOverlay(){
  const el = ensurePauseOverlay();
  el.style.display = 'flex';

  // visuell + audio "ruhig"
  try { questionAudio.pause(); } catch (_) {}
  stopTimerVisual();
  clearUnveil();
  duckBgm();
}

function hidePauseOverlay(){
  if (pauseOverlay) pauseOverlay.style.display = 'none';
  // NICHT automatisch was starten – Backend schickt gleich show_question/open_answers
}


/* ---------- Socket Events ---------- */

socket.on('show_pause', () => {
  showPauseOverlay();
});

socket.on('hide_pause', () => {
  hidePauseOverlay();
});

socket.on('show_question', data => {
  hidePauseOverlay();
  showGame();
  clearTimer();
  clearUnveil();
  clearAllScorePops();

  ensureBgmPlaying();
  unduckBgm();

  playQuestionAudio(data.audio);
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
  const row = getPlayerRow(data.player_id);
  if (row) row.classList.add('is-answered');
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
      'choice-0', 'choice-1', 'choice-2', 'choice-3', 'choice-3', 
      'is-correct', 'is-wrong'
    );

    row.classList.add(`choice-${choice}`);
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
  duckBgm();
  playSfx('showResolution');


  stopTimerVisual();
  clearAllScorePops();
  showAnswersAndTimer();

  const correctIdx = Number(data && data.correct_index);
  const playerAnswers = (data && data.player_answers) || {};

  const meta = (data && data.finale_meta) || {};
  const whiteUsed = new Set((meta.white_used || []).map(String));
  const goldUsed  = new Set((meta.gold_used  || []).map(String));

  document.querySelectorAll('.ps__player').forEach(row => {
    row.classList.remove('is-correct', 'is-wrong', 'has-white-protection', 'has-gold-protection');

    const playerId = String(row.id.replace('player-', ''));

    // Priorität: Gold > White > korrekt > falsch
    if (goldUsed.has(playerId)) {
      row.classList.add('has-gold-protection');
      return;
    }

    if (whiteUsed.has(playerId)) {
      row.classList.add('has-white-protection');
      return;
    }

    const choice = Object.prototype.hasOwnProperty.call(playerAnswers, playerId)
      ? playerAnswers[playerId]
      : null;

    if (choice !== null && Number(choice) === correctIdx) {
      row.classList.add('is-correct');
    } else {
      row.classList.add('is-wrong');
    }
  });

  document.querySelectorAll('.ps__answer').forEach((el, i) => {
    el.classList.remove('is-correct', 'is-faded');
    if (i === correctIdx) el.classList.add('is-correct');
    else el.classList.add('is-faded');
  });
   
    // --- NEU: Eliminierte Kacheln fliegen raus (Frontend: N=0 nix, N=1 Single+Name, N>=2 Multiple) ---
    // --- NEU: Eliminierte Kacheln fliegen raus (Frontend: N=0 nix, N=1 Single+Name, N>=2 Multiple) ---
  (function runEliminationFlyout() {
    const meta2 = (data && data.finale_meta) || {};

    const orderedFromBackend = Array.isArray(meta2.ordered_eliminated)
      ? meta2.ordered_eliminated.map(String)
      : [];

    const eliminatedRaw = Array.isArray(meta2.eliminated)
      ? meta2.eliminated.map(String)
      : [];

    const eliminatedOrdered = (orderedFromBackend.length ? orderedFromBackend : currentPlayerOrder.map(String))
      .filter(pid => eliminatedRaw.includes(pid))
      .filter(pid => !!getPlayerRow(pid));

    const seq = meta2.elimination_sequence || {};
    const PAUSE_MS   = Number(seq.pause_ms ?? 1000);
    const STAGGER_MS = Number(seq.stagger_ms ?? 250);

    const FLY_MS = 650;

    const ack = () => {
      socket.emit('module_event', {
        scope: 'system',
        action: 'resolution_finished',
        payload: { round: (data && data.round) }
      });
    };

    const N = eliminatedOrdered.length;

    if (N === 0) {
      setTimeout(ack, PAUSE_MS);
      return;
    }

    setTimeout(() => {
      (async () => {

        if (N === 1) {
          await playAudioWait(pickRandom(sfxElimAnnounceSinglePool));


          await ensurePlayerSoundMapLoaded();
          const pid = eliminatedOrdered[0];

          const nameAudio = getCachedPlayerNameAudio(pid);
          if (nameAudio) {
            await playAudioWait(nameAudio);
          }

          const row = getPlayerRow(pid);
          if (row) {
            playSfx('eliminationFly');

            row.style.willChange = 'transform, opacity';
            row.style.transition = `transform ${FLY_MS}ms ease, opacity ${FLY_MS}ms ease`;
            row.style.transform = 'translateX(120vw)';
            row.style.opacity = '0';
            row.style.pointerEvents = 'none';
          }

          setTimeout(ack, FLY_MS + 50);
          return;
        }

        await playAudioWait(pickRandom(sfxElimAnnounceMultiplePool));


        eliminatedOrdered.forEach((pid, i) => {
          setTimeout(() => {
            const row = getPlayerRow(pid);
            if (!row) return;

            playSfx('eliminationFly');

            row.style.willChange = 'transform, opacity';
            row.style.transition = `transform ${FLY_MS}ms ease, opacity ${FLY_MS}ms ease`;
            row.style.transform = 'translateX(120vw)';
            row.style.opacity = '0';
            row.style.pointerEvents = 'none';
          }, i * STAGGER_MS);
        });

        const totalMs = ((N - 1) * STAGGER_MS) + FLY_MS + 50;
        setTimeout(ack, totalMs);

      })();
    }, PAUSE_MS);
  })();
});

/*
  SCORING (Timing NUR Backend)
  - show_scoring: zeigt NUR "+Punkte" (Scores bleiben wie angezeigt)
  - apply_scoring_update: aktualisiert NUR die Scores (und entfernt "+Punkte")
*/

socket.on('show_scoring', data => {
  const gainedObj = data.gained || {};
  const anyPoints = Object.values(gainedObj).some(g => Number(g) > 0);

  clearAllScorePops();

  // Optional: Wenn Backend "before" mitsendet, können wir es als Anker setzen
  // (damit die Sidebar-Reihenfolge stabil bleibt)
  if (!anyPoints) {
    return;
  }
  // Optional: Wenn Backend "before" mitsendet, können wir es als Anker setzen
  // (damit die Sidebar-Reihenfolge stabil bleibt)
  if (data.players_ranked && Array.isArray(data.players_ranked)) {
    const ranked = (data.players_ranked || []);
    maxTvPlayers = computeMaxTvPlayers();
    currentPlayerOrder = ranked.slice(0, maxTvPlayers).map(p => p.player_id);
    renderPlayersRanked(ranked);
  }

  // NUR "+Punkte" anzeigen (keine Score-Änderung hier!)
  playSfx('pointsUnveiled');

  Object.entries(gainedObj).forEach(([playerId, g]) => {
    if (Number(g) > 0) {
      const row = getPlayerRow(playerId);
      if (!row) return;

      const pop = document.createElement('div');
      pop.className = 'ps__scorePop';
      pop.textContent = `+${g}`;
      row.appendChild(pop);
    }
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
  showVideo(`/finale/media/frage${data.round}.mp4`);
});

/* ---------- Init ---------- */
updateMaxTvPlayers();
showVideo();
