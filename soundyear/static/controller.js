// --- FILE: ./soundyear/static/controller.js ---

const LS_RUN_ID_KEY = "blitzquiz_run_id";
const LS_PLAYER_ID_KEY = "blitzquiz_player_id";

/* ---------- Socket register / reconnect ---------- */
socket.emit('register_controller', {
  player_id: localStorage.getItem(LS_PLAYER_ID_KEY) || "",
  run_id: localStorage.getItem(LS_RUN_ID_KEY) || ""
});

socket.on('connect', () => {
  socket.emit('register_controller', {
    player_id: localStorage.getItem(LS_PLAYER_ID_KEY) || "",
    run_id: localStorage.getItem(LS_RUN_ID_KEY) || ""
  });
});

/* ---------- Screens ---------- */
const titleScreen = document.getElementById("title-screen");
const roundScreen = document.getElementById("round-screen");
const qaScreen    = document.getElementById("qa-screen");

/* ---------- Player header ---------- */
const playerNameEl  = document.getElementById("player-name");
const playerScoreEl = document.getElementById("player-score");

/* ---------- Round ---------- */
const roundLabel  = document.getElementById("round-label");

/* ---------- QA ---------- */
const qText = document.getElementById("question-text");

/* ---------- Year Wheel ---------- */
const yearForm   = document.getElementById("year-form");
const yearWheel  = document.getElementById("year-wheel");               // bleibt: Rahmen/Overlay
const yearWheelScroll = document.getElementById("year-wheel-scroll");   // NEU: echter Scroll-Container
const yearWheelList = document.getElementById("year-wheel-list");

const yearSubmit = document.getElementById("year-submit");
const yearHint   = document.getElementById("year-hint");

let selectedYear = null;

// NEU: merken, was der Spieler tatsächlich abgeschickt hat (für Δ)
let lastSubmittedYear = null;

// NEU: Box für Δ unter dem Wheel
let deltaBoxEl = null;

let locked = true;
let hasSubmitted = false;


/* ---------- Image ---------- */
const qImageWrap  = document.getElementById("question-image-wrap");
const qImageEl    = document.getElementById("question-image");

/* ---------- Timer-Bar ---------- */
const timebarFill = document.getElementById("timebar-fill");

/* ---------- Timer-Bar RAF ---------- */
let timebarRAF = null;

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

/* ---------- Score-Pop (Backend steuert Timing) ---------- */
let myScorePop = 0;

/* =========================================================
   Question Rot/Grün wie TV (für den jeweiligen Spieler)
   - setzt .is-correct / .is-wrong auf #question-text
   ========================================================= */

function clearQuestionResult(){
  if (!qText) return;
  qText.classList.remove("is-d0","is-d1","is-d2","is-d3","is-d4","is-d5");
}

function applyDistanceClass(diff){
  clearQuestionResult();
  if (!qText) return;

  if (diff === null || diff === undefined || !Number.isFinite(diff)) return;

  const d = Math.abs(Number(diff));
  if (d === 0) return qText.classList.add("is-d0");
  if (d === 1) return qText.classList.add("is-d1");
  if (d === 2) return qText.classList.add("is-d2");
  if (d === 3) return qText.classList.add("is-d3");
  if (d === 4) return qText.classList.add("is-d4");
  return qText.classList.add("is-d5"); // >4
}

/* =========================================================
   Reveal UI: Wheel -> correct year + Δ-Box
   ========================================================= */

function clearCorrectMark(){
  if (!yearWheelList) return;
  const prev = yearWheelList.querySelector(".syc__wheelItem.is-correct");
  if (prev) prev.classList.remove("is-correct");
}

function markCorrectYear(yearStr){
  if (!yearWheelList) return;
  clearCorrectMark();
  const el = yearWheelList.querySelector(`.syc__wheelItem[data-year="${yearStr}"]`);
  if (el) el.classList.add("is-correct");
}

function hideDeltaBox(){
  if (!deltaBoxEl) return;
  deltaBoxEl.classList.add("is-hidden");
  deltaBoxEl.setAttribute("aria-hidden", "true");
  deltaBoxEl.textContent = "";
}

function showDeltaBox(diff){
  if (!deltaBoxEl) return;
  if (diff === null || diff === undefined || !Number.isFinite(diff)) return;

  const d = Math.abs(Number(diff));
  deltaBoxEl.textContent = `Δ${d} Jahre`;
  deltaBoxEl.classList.remove("is-hidden");
  deltaBoxEl.setAttribute("aria-hidden", "false");
}

function revealCorrectWheel(correctYearStr, myYearStr /* optional */){
  if (!correctYearStr || !/^\d{4}$/.test(String(correctYearStr))) return;

  // Wheel zur Lösung scrollen
  scrollWheelToYear(String(correctYearStr));

  // korrektes Jahr grün markieren
  markCorrectYear(String(correctYearStr));

  // Δ anzeigen (wenn Tipp bekannt)
  const myY = myYearStr && /^\d{4}$/.test(String(myYearStr)) ? Number(myYearStr) : null;
  const corY = Number(correctYearStr);

  if (Number.isFinite(myY) && Number.isFinite(corY)) {
    showDeltaBox(Math.abs(myY - corY));
  } else {
    // Wenn kein Tipp bekannt: Box ausblenden
    hideDeltaBox();
  }
}


/* ---------- Screen Switching ---------- */
function showTitle() {
  if (titleScreen) titleScreen.style.display = "flex";
  if (roundScreen) roundScreen.style.display = "none";
  if (qaScreen)    qaScreen.style.display    = "none";
}

function showRound(round) {
  if (roundLabel) roundLabel.textContent = `Track ${round}`;
  if (titleScreen) titleScreen.style.display = "none";
  if (roundScreen) roundScreen.style.display = "flex";
  if (qaScreen)    qaScreen.style.display    = "none";
}

function showQA() {
  if (titleScreen) titleScreen.style.display = "none";
  if (roundScreen) roundScreen.style.display = "none";
  if (qaScreen)    qaScreen.style.display    = "flex";
}

/* ---------- Helpers (Lock/Unlock) ---------- */
function lockAll() {
  locked = true;
  hasSubmitted = true;

  if (yearWheel) {
    yearWheel.classList.add("is-locked");
    yearWheel.setAttribute("aria-disabled", "true");
  }
  if (yearSubmit) yearSubmit.disabled = true;

  if (yearSubmit) yearSubmit.classList.add("is-locked");
}

function unlockAll() {
  locked = false;
  hasSubmitted = false;

  if (yearWheel) {
    yearWheel.classList.remove("is-locked");
    yearWheel.setAttribute("aria-disabled", "false");
  }
  if (yearSubmit) yearSubmit.disabled = false;

  if (yearSubmit) yearSubmit.classList.remove("is-locked");
}

function clearYearInput() {
  if (yearHint) {
    yearHint.classList.add("is-hidden");
    yearHint.setAttribute("aria-hidden", "true");
  }

  // Default: 2010 (falls außerhalb Range, clampen)
  const startY = 1950;
  const endY = new Date().getFullYear();
  const defY = 2010;

  const clamped = Math.max(startY, Math.min(endY, defY));
  selectedYear = String(clamped);


  // Scroll Wheel auf Default (wenn bereits gebaut)
  if (yearWheelScroll && yearWheelList && yearWheelList.children.length) {
    scrollWheelToYear(selectedYear, { instant: true });
  }

  // NEU: Reveal UI reset
  clearCorrectMark();
  hideDeltaBox();
}



function showYearHint() {
  if (!yearHint) return;
  yearHint.classList.remove("is-hidden");
  yearHint.setAttribute("aria-hidden", "false");
}

function submitYearAnswer() {
  if (locked || hasSubmitted) return;

  const year = String(selectedYear ?? "").trim();
  if (!/^\d{4}$/.test(year)) {
    showYearHint();
    return;
  }

  lockAll();

  // NEU: Tipp merken (für Δ beim Reveal)
  lastSubmittedYear = year;

  socket.emit("module_event", {
    action: "submit_answer",
    payload: { text: year }
  });
}



/* ---------- Image ---------- */
function setQuestionImage(imageFile) {
  const fallback = '/soundyear/media/dummy.png';
  const file = (imageFile || '').trim();

  if (qImageWrap) qImageWrap.classList.add('is-hidden');
  if (!file) return;

  if (qImageWrap) qImageWrap.classList.remove('is-hidden');

  const isAbsolute =
    file.startsWith('http://') ||
    file.startsWith('https://') ||
    file.startsWith('/');

  if (qImageEl) {
    qImageEl.src = isAbsolute ? file : `/soundyear/media/images/${file}`;
    qImageEl.onerror = () => {
      qImageEl.onerror = null;
      qImageEl.src = fallback;
    };
  }
}

/* ---------- Score Rendering ---------- */
function clearScorePopInline() {
  myScorePop = 0;
  if (playerScoreEl) {
    const current = (playerScoreEl.textContent || "").trim();
    if (current) playerScoreEl.textContent = current;
  }
}

function renderScoreWithPop(scoreValue, popValue) {
  if (!playerScoreEl) return;

  const score = (scoreValue ?? "—");
  const pop = Number(popValue || 0);

  if (pop > 0) {
    playerScoreEl.innerHTML =
      `<span class="psc__scorePopInline">+${pop}</span>` +
      `<span class="psc__scoreValue">${score}</span>`;
  } else {
    playerScoreEl.textContent = `${score}`;
  }
}

function updatePlayerHeader(playersRanked, gainedMap, opts = {}) {
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  if (!myId || !playersRanked) return;

  const me = playersRanked.find(p => p.player_id === myId);
  if (!me) return;

  if (playerNameEl) playerNameEl.textContent = me.name || "—";

  const score = (me.score ?? "—");

  if (opts.forceClear) {
    myScorePop = 0;
    renderScoreWithPop(score, 0);
    return;
  }

  const gained = gainedMap && Object.prototype.hasOwnProperty.call(gainedMap, myId)
    ? Number(gainedMap[myId] || 0)
    : 0;

  if (opts.forcePop) {
    myScorePop = gained > 0 ? gained : myScorePop;
    renderScoreWithPop(score, myScorePop);
    return;
  }

  if (gained > 0) {
    myScorePop = gained;
    renderScoreWithPop(score, myScorePop);
  } else {
    myScorePop = 0;
    renderScoreWithPop(score, 0);
  }
}

/* ---------- Timer-Bar ---------- */
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

function stopTimebar() {
  if (timebarRAF) {
    cancelAnimationFrame(timebarRAF);
    timebarRAF = null;
  }
  if (timebarFill) timebarFill.style.width = "0%";
}

function startTimebar(seconds, startedAt /* optional */) {
  if (!timebarFill) return;

  stopTimebar();

  const durMs = Math.max(0.001, Number(seconds || 1)) * 1000;
  const startedAtMs = parseStartedAtToMs(startedAt);

  if (startedAtMs !== null) {
    const endAtMs = startedAtMs + durMs;

    const tick = () => {
      const nowMs = nowSyncedMs();
      const elapsed = nowMs - startedAtMs;
      const pct = Math.min(100, Math.max(0, (elapsed / durMs) * 100));
      timebarFill.style.width = `${pct}%`;

      if (nowMs < endAtMs) timebarRAF = requestAnimationFrame(tick);
      else stopTimebar();
    };

    timebarRAF = requestAnimationFrame(tick);
    return;
  }

  const start = performance.now();
  const tick = (now) => {
    const elapsed = now - start;
    const pct = Math.min(100, (elapsed / durMs) * 100);
    timebarFill.style.width = `${pct}%`;
    if (pct < 100) timebarRAF = requestAnimationFrame(tick);
    else stopTimebar();
  };

  timebarRAF = requestAnimationFrame(tick);
}

/* ---------- Reconnect ---------- */
document.addEventListener("DOMContentLoaded", () => {
  const playerId = localStorage.getItem(LS_PLAYER_ID_KEY);
  const runId = localStorage.getItem(LS_RUN_ID_KEY);
  if (playerId) {
    socket.emit('resume_player', { player_id: playerId, run_id: runId || "" });
  }

  const v = document.getElementById('ps-controller-video');
  if (v) v.play().catch(()=>{});
});

/* ---------- Init ---------- */
showTitle();
lockAll();
stopTimebar();
clearScorePopInline();
clearQuestionResult();
clearYearInput();

/* ---------- Socket Events ---------- */

socket.on("play_round_video", (data) => {
  showRound(Number(data.round || 1));
  lockAll();
  stopTimebar();
  clearScorePopInline();
  clearQuestionResult();
  clearYearInput();
});

socket.on("show_question", (data) => {
  showQA();

  if (qText) qText.textContent = data.text || "";
  setQuestionImage(data.image);

  // Header setzen (ohne Pop)
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });

  lockAll();
  stopTimebar();
  clearScorePopInline();
  clearQuestionResult();
  clearYearInput();
});

socket.on("open_answers", (data) => {
  // Start für Interaktion
  unlockAll();
  clearQuestionResult();

  // Fokus aufs Wheel
  if (yearWheelScroll) yearWheelScroll.focus();



  const startedAt = data && (data.started_at ?? data.startedAt ?? data.opened_at ?? data.openedAt);
  const dur = Number((data && (data.total_duration ?? data.totalDuration ?? data.duration)) || 15);

  startTimebar(dur, startedAt);
});

socket.on("close_answers", () => {
  lockAll();
  stopTimebar();
});

socket.on("reveal_player_answers", () => {
  stopTimebar();
});

socket.on("unveil_correct", (data) => {
  lockAll();
  stopTimebar();

  // Wenn Backend correct mitschickt, direkt auch hier reveal'en
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);

  function extractYear(v) {
    if (v === null || v === undefined) return null;
    if (typeof v === "number") return Number.isFinite(v) ? v : null;
    if (typeof v === "string") {
      const digits = v.match(/\d/g);
      if (!digits || digits.length < 4) return null;
      const n = parseInt(digits.slice(0, 4).join(""), 10);
      return Number.isFinite(n) ? n : null;
    }
    if (typeof v === "object") {
      const t = v.text ?? v.raw ?? v.value ?? v.year ?? null;
      return extractYear(typeof t === "number" ? String(t) : (t ?? ""));
    }
    return null;
  }

  const corYear = extractYear(data && data.correct);
  const myYear =
    myId && data && data.player_answers ? extractYear(data.player_answers[myId]) : null;

  const myYearFallback = Number.isFinite(Number(myYear)) ? String(myYear) : (lastSubmittedYear || null);

  if (Number.isFinite(Number(corYear))) {
    revealCorrectWheel(String(corYear), myYearFallback);
  }
});


socket.on("show_resolution", (data) => {
  lockAll();
  stopTimebar();

  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);

  function extractYear(v) {
    if (v === null || v === undefined) return null;

    if (typeof v === "number") return Number.isFinite(v) ? v : null;

    if (typeof v === "string") {
      const digits = v.match(/\d/g);
      if (!digits || digits.length < 4) return null;
      const n = parseInt(digits.slice(0, 4).join(""), 10);
      return Number.isFinite(n) ? n : null;
    }

    if (typeof v === "object") {
      // passt zu deinem Scoring: answer kann dict sein mit text/raw
      const t = v.text ?? v.raw ?? v.value ?? v.year ?? null;
      return extractYear(typeof t === "number" ? String(t) : (t ?? ""));
    }

    return null;
  }

  let diff = null;

  // In show_resolution kommen details i.d.R. NICHT mit -> wir rechnen selber
  if (myId && data && data.player_answers) {
    const myAns = data.player_answers[myId];
    const myYear = extractYear(myAns);
    const corYear = extractYear(data.correct);

    if (Number.isFinite(myYear) && Number.isFinite(corYear)) {
      diff = Math.abs(myYear - corYear);
    }
  }

  applyDistanceClass(diff);

  // NEU: Wheel zur korrekten Antwort + Δ-Box
  const corYear = extractYear(data && data.correct);
  const myYear =
    myId && data && data.player_answers ? extractYear(data.player_answers[myId]) : null;

  // Fallback, falls player_answers nicht mitkommt: nutze lastSubmittedYear
  const myYearFallback = Number.isFinite(Number(myYear)) ? String(myYear) : (lastSubmittedYear || null);

  if (Number.isFinite(Number(corYear))) {
    revealCorrectWheel(String(corYear), myYearFallback);
  }
});




function isPopPayload(data) {
  const phase = (data && (data.phase || data.mode || data.step) || "").toString().toLowerCase();
  if (phase === "pop" || phase === "points_pop" || phase === "reveal_points") return true;
  if (phase === "show_points") return true;
  if (data && data.show_pop === true) return true;
  return false;
}

socket.on("show_scoring", (data) => {
  if (isPopPayload(data)) {
    updatePlayerHeader(data.players_ranked, data.gained || {}, { forcePop: true });
  } else {
    updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  }

  // echte diff aus deinem Scoring-Details: details[player_id].diff
  const myId = localStorage.getItem(LS_PLAYER_ID_KEY);
  const d = data && data.details && myId && data.details[myId] ? data.details[myId].diff : null;
  applyDistanceClass(Number.isFinite(Number(d)) ? Number(d) : null);

  stopTimebar();
});


socket.on("apply_scoring_update", (data) => {
  updatePlayerHeader(data.players_ranked, null, { forceClear: true });
  stopTimebar();
});

/* ---------- Input (Year Wheel) ---------- */
if (yearForm) {
  yearForm.addEventListener("submit", (e) => {
    e.preventDefault();
    submitYearAnswer();
  });
}

function buildYearWheel() {
  if (!yearWheelList) return;

  const start = 1950;
  const end = new Date().getFullYear();

  // Liste leeren (falls reconnect / hot reload)
  yearWheelList.innerHTML = "";

  // Für “cooler Flow”: neu -> alt (oben neuere Jahre)
  for (let y = end; y >= start; y--) {
    const el = document.createElement("div");
    el.className = "syc__wheelItem";
    el.setAttribute("role", "option");
    el.dataset.year = String(y);
    el.textContent = String(y);
    yearWheelList.appendChild(el);
  }

  // Ghost-Items oben/unten: zeigen "-" statt “leere Box”
  function makeGhost() {
    const g = document.createElement("div");
    g.className = "syc__wheelItem is-ghost";
    g.setAttribute("role", "option");
    g.dataset.year = "";     // nicht auswählbar
    g.textContent = "-";
    return g;
  }

  // Für 7 sichtbare Items: 3 Ghost oben + 3 Ghost unten
  yearWheelList.prepend(makeGhost(), makeGhost(), makeGhost());
  yearWheelList.append(makeGhost(), makeGhost(), makeGhost());
}


function nearestYearToCenter() {

if (!yearWheelScroll || !yearWheelList) return null;

const wheelRect = yearWheelScroll.getBoundingClientRect();
const centerY = wheelRect.top + wheelRect.height / 2;


  let best = null;
  let bestDist = Infinity;

  const items = yearWheelList.querySelectorAll(".syc__wheelItem:not(.is-ghost)");

  items.forEach((it) => {
    const r = it.getBoundingClientRect();
    const mid = r.top + r.height / 2;
    const d = Math.abs(mid - centerY);
    if (d < bestDist) {
      bestDist = d;
      best = it;
    }
  });

  return best;
}

function applyWheelVisuals() {
if (!yearWheelScroll || !yearWheelList) return;

const wheelRect = yearWheelScroll.getBoundingClientRect();
const centerY = wheelRect.top + wheelRect.height / 2;


  const nearest = nearestYearToCenter();

  const items = yearWheelList.querySelectorAll(".syc__wheelItem");
  items.forEach((it) => {
    const r = it.getBoundingClientRect();
    const mid = r.top + r.height / 2;
    const dist = Math.min(1, Math.abs(mid - centerY) / (wheelRect.height / 2));

    it.classList.toggle("is-selected", nearest === it);

    const scale = 1 - dist * 0.16;
    const opacity = 1 - dist * 0.60;

    it.style.transform = `scale(${scale})`;
    it.style.opacity = `${opacity}`;
  });
}


function clampWheelScroll() {
  if (!yearWheelScroll || !yearWheelList) return;

  const real = yearWheelList.querySelectorAll(".syc__wheelItem:not(.is-ghost)");
  if (!real.length) return;

  const firstReal = real[0];
  const lastReal  = real[real.length - 1];

  const wheelH = yearWheelScroll.clientHeight;
  const centerOffset = wheelH / 2;

  const minScroll =
    (firstReal.offsetTop + firstReal.offsetHeight / 2) - centerOffset;

  const maxScroll =
    (lastReal.offsetTop + lastReal.offsetHeight / 2) - centerOffset;

  const st = yearWheelScroll.scrollTop;
  const clamped = Math.max(minScroll, Math.min(maxScroll, st));

  if (Math.abs(clamped - st) > 0.5) {
    yearWheelScroll.scrollTop = clamped;
  }
}


function snapToNearestYear() {
  const it = nearestYearToCenter();
  if (!it || !yearWheelScroll) return;

  const wheelRect = yearWheelScroll.getBoundingClientRect();
  const centerY = wheelRect.top + wheelRect.height / 2;

  const r = it.getBoundingClientRect();
  const mid = r.top + r.height / 2;
  const delta = mid - centerY;

  // Scroll so, dass das Item exakt in die Mitte kommt
  yearWheelScroll.scrollBy({ top: delta, left: 0, behavior: "smooth" });

  // Auswahl setzen
  const y = it.dataset.year;
  if (y) {
    selectedYear = y;
    if (yearHint) {
      yearHint.classList.add("is-hidden");
      yearHint.setAttribute("aria-hidden", "true");
    }
  }
}


function scrollWheelToYear(yearStr, opts = {}) {
  if (!yearWheelList || !yearWheelScroll) return;
  const target = yearWheelList.querySelector(`.syc__wheelItem[data-year="${yearStr}"]`);
  if (!target) return;

  const wheelRect = yearWheelScroll.getBoundingClientRect();
  const centerY = wheelRect.top + wheelRect.height / 2;

  const r = target.getBoundingClientRect();
  const mid = r.top + r.height / 2;
  const delta = mid - centerY;

  yearWheelScroll.scrollBy({ top: delta, left: 0, behavior: opts.instant ? "auto" : "smooth" });
  selectedYear = yearStr;
}


let wheelScrollT = null;

function onWheelScroll() {
  if (locked || hasSubmitted) return;

  clampWheelScroll();
  applyWheelVisuals();

  if (wheelScrollT) clearTimeout(wheelScrollT);
  wheelScrollT = setTimeout(() => {
    clampWheelScroll();
    snapToNearestYear();
    setTimeout(() => {
      clampWheelScroll();
      applyWheelVisuals();
    }, 60);
  }, 90);
}

document.addEventListener("DOMContentLoaded", () => {
  // NEU: Δ-Box direkt unter dem Wheel (unter year-form)
  if (!deltaBoxEl) {
    deltaBoxEl = document.createElement("div");
    deltaBoxEl.id = "delta-box";
    deltaBoxEl.className = "syc__deltaBox is-hidden";
    deltaBoxEl.setAttribute("aria-hidden", "true");

    // Unterhalb des year-form einfügen (wenn vorhanden)
    if (yearForm && yearForm.parentNode) {
      yearForm.parentNode.insertBefore(deltaBoxEl, yearForm.nextSibling);
    }
  }

  buildYearWheel();
  clearYearInput();
  clampWheelScroll();
  applyWheelVisuals();



  if (yearWheelScroll) {
    yearWheelScroll.addEventListener("scroll", onWheelScroll, { passive: true });

    // Tap auf Item: direkt dahin snappen
    yearWheelScroll.addEventListener("pointerup", (e) => {
      if (locked || hasSubmitted) return;
      const t = e.target && e.target.closest ? e.target.closest(".syc__wheelItem") : null;
      if (!t) return;
      const y = t.dataset.year;
      if (y) scrollWheelToYear(y);
      setTimeout(() => {
        snapToNearestYear();
        applyWheelVisuals();
      }, 80);
    });
  }

});

if (yearSubmit) {
  yearSubmit.addEventListener("pointerup", (e) => {
    e.preventDefault();
    submitYearAnswer();
  });
}
