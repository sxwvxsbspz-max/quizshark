socket.emit('register_tv');
socket.on('connect', () => { socket.emit('register_tv'); });

const videoLayer  = document.getElementById('video-layer');
const gameLayer   = document.getElementById('game-layer');
const videoPlayer = document.getElementById('phase-video');

const answersWrap        = document.getElementById('options-grid');
const timerWrap          = document.querySelector('.ps__timer');
const correctAnswerBox   = document.getElementById('correct-answer-box');
const correctAnswerValue = document.getElementById('correct-answer-value');

const qImageWrap  = document.getElementById('question-image-wrap');
const qImageEl    = document.getElementById('question-image');
const dummyInWrap = document.getElementById('dummy-inbox-wrap');
const dummyInImg  = document.getElementById('dummy-inbox-img');

const psRoot = document.querySelector('.ps');

let timerRAF = null;
let unveilTO = null;
let clockOffsetMs = 0;
let currentPlayerOrder = [];
let maxTvPlayers = 9;

function nowSyncedMs() { return Date.now() + clockOffsetMs; }

socket.on('server_time', (data) => {
  const serverNow = data && typeof data.server_now === "number" ? data.server_now : null;
  if (serverNow === null) return;
  clockOffsetMs = serverNow - Date.now();
});

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
    tmp.innerHTML = `<div class="ps__answerBox is-hidden" aria-hidden="true"></div><div class="ps__playerCardWrap"><div class="ps__playerCard"><div class="ps__playerName">X</div><div class="ps__playerScore">0</div></div></div>`;
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

function updateMaxTvPlayers() { requestAnimationFrame(() => { maxTvPlayers = computeMaxTvPlayers(); }); }
window.addEventListener('resize', updateMaxTvPlayers);

const questionAudio = new Audio();
questionAudio.preload = 'auto';
questionAudio.volume = 1.0;

const bgm = new Audio('/freeknowledge/media/gamesounds/background.mp3');
bgm.preload = 'auto';
bgm.loop = true;
bgm.volume = 1.0;

function startBgm() { try { bgm.currentTime = 0; } catch (_) {} bgm.play().catch(() => {}); }
function stopBgm()  { try { bgm.pause(); bgm.currentTime = 0; } catch (_) {} }

const SFX_BASE = '/freeknowledge/media/gamesounds';

function playSfxOverlap(file) {
  try { const a = new Audio(`${SFX_BASE}/${file}`); a.preload = 'auto'; a.volume = 1.0; a.play().catch(() => {}); } catch (_) {}
}

const sfxAnswerUnveiled      = new Audio(`${SFX_BASE}/answerunveiled.mp3`);
const sfxPointsUnveiled      = new Audio(`${SFX_BASE}/pointsunveiled.mp3`);
const sfxPointsUpdated       = new Audio(`${SFX_BASE}/pointsupdated.mp3`);
const sfxRevealPlayerAnswers = new Audio(`${SFX_BASE}/reveal_player_answers.mp3`);
const sfxUnveilCorrect       = new Audio(`${SFX_BASE}/unveil_correct.mp3`);
const sfxShowResolution      = new Audio(`${SFX_BASE}/show_resolution.mp3`);

[sfxAnswerUnveiled, sfxPointsUnveiled, sfxPointsUpdated, sfxRevealPlayerAnswers, sfxUnveilCorrect, sfxShowResolution].forEach(a => {
  a.preload = 'auto'; a.volume = 1.0;
});

function playSfxSingle(audioEl) {
  try { audioEl.pause(); audioEl.currentTime = 0; audioEl.play().catch(() => {}); } catch (_) {}
}

function playSfx(key) {
  switch (key) {
    case 'answerEntered':       playSfxOverlap('answerentered.mp3'); return;
    case 'answerUnveiled':      playSfxSingle(sfxAnswerUnveiled); return;
    case 'revealPlayerAnswers': playSfxSingle(sfxRevealPlayerAnswers); return;
    case 'unveilCorrect':       playSfxSingle(sfxUnveilCorrect); return;
    case 'showResolution':      playSfxSingle(sfxShowResolution); return;
    case 'pointsUnveiled':      playSfxSingle(sfxPointsUnveiled); return;
    case 'pointsUpdated':       playSfxSingle(sfxPointsUpdated); return;
  }
}

function showVideo(src) {
  gameLayer.style.display = 'none';
  videoLayer.style.display = 'block';
  try { questionAudio.pause(); questionAudio.currentTime = 0; } catch (_) {}
  stopBgm();
  [sfxAnswerUnveiled, sfxPointsUnveiled, sfxPointsUpdated, sfxRevealPlayerAnswers, sfxUnveilCorrect, sfxShowResolution].forEach(a => {
    try { a.pause(); a.currentTime = 0; } catch (_) {}
  });
  if (src) { videoPlayer.src = src; videoPlayer.load(); }
  videoPlayer.play().catch(() => {});
}

function showGame() { videoLayer.style.display = 'none'; gameLayer.style.display = 'block'; }

videoPlayer.onended = function () { socket.emit('module_event', { action: 'video_finished' }); };

function clearTimer() { if (timerRAF) { cancelAnimationFrame(timerRAF); timerRAF = null; } }
function clearUnveil() { if (unveilTO) { clearTimeout(unveilTO); unveilTO = null; } }
function getPlayerRow(pid)  { return document.getElementById(`player-${pid}`); }
function getAnswerBox(pid)  { return document.getElementById(`answer-${pid}`); }
function getCardWrap(pid)   { return document.getElementById(`cardwrap-${pid}`); }
function hideMcGrid() { if (answersWrap) answersWrap.classList.add('is-hidden'); }
function hideCorrectAnswerBox() { if (correctAnswerBox) correctAnswerBox.classList.add('is-hidden'); if (correctAnswerValue) correctAnswerValue.textContent = '—'; }
function showCorrectAnswerBox(text) { if (correctAnswerBox) correctAnswerBox.classList.remove('is-hidden'); if (correctAnswerValue) correctAnswerValue.textContent = (text ?? '—'); }
function hideTimer() { if (timerWrap) timerWrap.classList.add('is-invisible'); }
function showTimer() { if (timerWrap) timerWrap.classList.remove('is-invisible'); }

function onQuestionIntro() { hideMcGrid(); hideCorrectAnswerBox(); hideTimer(); }
function onOpenAnswers()   { hideMcGrid(); hideCorrectAnswerBox(); showTimer(); }

function clearAllScorePops() { document.querySelectorAll('.ps__scorePop').forEach(n => n.remove()); }

function resetPlayerClassesForNewQuestion() {
  const sidebar = document.getElementById('player-sidebar');
  if (!sidebar) return;
  sidebar.querySelectorAll('.ps__player').forEach(row => {
    row.classList.remove('is-answered', 'choice-0', 'choice-1', 'choice-2', 'choice-3', 'is-correct', 'is-wrong');
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

function setQuestionImage(imageFile) {
  const file = (imageFile || '').trim();
  if (psRoot) psRoot.classList.remove('has-image', 'no-image');
  if (qImageWrap) qImageWrap.classList.add('is-hidden');
  if (dummyInWrap) dummyInWrap.classList.add('is-hidden');
  if (!file) {
    if (psRoot) psRoot.classList.add('no-image');
    if (dummyInWrap) dummyInWrap.classList.remove('is-hidden');
    if (dummyInImg) dummyInImg.src = '/freeknowledge/media/dummy.svg';
    return;
  }
  if (psRoot) psRoot.classList.add('has-image');
  if (qImageWrap) qImageWrap.classList.remove('is-hidden');
  if (qImageEl) {
    const isAbsolute = file.startsWith('http://') || file.startsWith('https://') || file.startsWith('/');
    qImageEl.src = isAbsolute ? file : `/wellguessed/media/images/${file}`;
  }
}

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

function stopTimerVisual() { clearTimer(); if (timerWrap) timerWrap.style.setProperty('--p', '0%'); }

function playQuestionAudio(audioFile) {
  if (!audioFile) return;
  try { questionAudio.pause(); questionAudio.currentTime = 0; } catch (_) {}
  const file = String(audioFile).trim();
  if (!file) return;
  const isAbsolute = file.startsWith('http://') || file.startsWith('https://') || file.startsWith('/');
  questionAudio.src = isAbsolute ? file : `/wellguessed/media/audio/${file}`;
  questionAudio.load();
  questionAudio.play().catch(() => {});
}

function formatDistance(distance) {
  if (distance === null || distance === undefined) return null;
  const n = Number(distance);
  if (!Number.isFinite(n)) return null;
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

socket.on('show_question', data => {
  showGame(); clearTimer(); clearUnveil(); clearAllScorePops(); startBgm();
  setTimeout(() => { playQuestionAudio(data.audio); }, 500);
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
  clearTimer(); clearAllScorePops(); onOpenAnswers();
  const dur = Number((data && (data.total_duration ?? data.totalDuration ?? data.duration)) || 15);
  const startedAt = data && (data.started_at ?? data.startedAt ?? data.opened_at ?? data.openedAt);
  startTimerVisual(dur, startedAt);
});

socket.on('close_answers', () => { stopTimerVisual(); });

socket.on('player_logged_in', data => {
  const row = getPlayerRow(data.player_id);
  if (row) row.classList.add('is-answered');
  const box = getAnswerBox(data.player_id);
  if (box) { box.classList.remove('is-hidden'); box.setAttribute('aria-hidden', 'false'); box.textContent = ''; }
  playSfx('answerEntered');
});

socket.on('reveal_player_answers', data => {
  stopTimerVisual(); playSfx('revealPlayerAnswers'); clearAllScorePops(); hideMcGrid();
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
      text = typeof answerVal === 'object' ? String(answerVal.text ?? answerVal.raw ?? '') : String(answerVal);
    }
    box.textContent = text;
  });
});

socket.on('unveil_correct', data => {
  playSfx('unveilCorrect');
  const correct = (data && (data.correct ?? data.correct_answer ?? data.correctAnswer)) ?? null;
  showCorrectAnswerBox(correct !== null ? String(correct) : '—');
});

socket.on('show_resolution', data => {
  stopBgm(); playSfx('showResolution'); stopTimerVisual(); clearAllScorePops(); hideMcGrid();
  const details = data && data.details ? data.details : null;
  if (!details || typeof details !== 'object') return;

  currentPlayerOrder.forEach(playerId => {
    const row = getPlayerRow(playerId);
    if (!row) return;
    const d = details[playerId];
    if (!d) return;

    // Farbe: Gewinner grün, 0 Punkte rot, dazwischen neutral
    if (d.accepted === true)  row.classList.add('is-correct');
    if (d.accepted === false) row.classList.add('is-wrong');

    const box = getAnswerBox(playerId);
    if (!box) return;
    box.classList.remove('is-hidden');
    box.setAttribute('aria-hidden', 'false');

    const raw = d.raw_answer ?? '';
    const distStr = formatDistance(d.distance);
    // Schätzung + Abstand zur richtigen Antwort anzeigen
    box.textContent = distStr !== null ? `${raw} (±${distStr})` : String(raw);
  });
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
  clearTimer(); clearUnveil(); clearAllScorePops();
  showVideo(`/freeknowledge/media/frage${data.round}.mp4`);
});

updateMaxTvPlayers();
showVideo();
