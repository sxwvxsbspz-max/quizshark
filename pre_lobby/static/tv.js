// --- FILE: ./pre_lobby/static/tv.js ---

// =====================================================
// SOCKET / TV REGISTRIERUNG
// =====================================================

socket.emit('register_tv');
socket.on('connect', () => {
  socket.emit('register_tv');
});

// =====================================================
// BACKGROUND MUSIC
// =====================================================

const bgm = document.getElementById('bgm');

if (bgm) {
  bgm.volume = 0.4;
}

socket.on('connect', () => {
  if (!bgm) return;
  bgm.play().catch(() => {});
});

// =====================================================
// INFO BOX ROTATOR (wie Lobby: 2 Layer + Höhe anpassen)
// =====================================================

const INFO_VIEWS = [
  { text: "Willkommen bei QuizShark!" },
  { text: "Das Quiz startet in Kürze." }
];

const INFO_HOLD_MS = 7000; // Standzeit pro Zeile
const INFO_ANIM_MS = 380;  // muss zur CSS transition passen (lobby/tv.css)

const box   = document.getElementById('pre-lobby-infobox');
const infoA = document.getElementById('pre-lobby-infobox-a');
const infoB = document.getElementById('pre-lobby-infobox-b');

let infoIndex = 0;
let infoTimer = null;
let activeEl  = null;
let idleEl    = null;

function setLayerText(el, text){
  if (!el) return;
  el.textContent = text;
}

function fitInfoBoxToActive(){
  if (!box || !activeEl) return;

  box.style.height = 'auto';

  const textRect = activeEl.getBoundingClientRect();
  const verticalPadding = box.offsetHeight - box.clientHeight;

  const newHeight = Math.ceil(textRect.height + verticalPadding);
  box.style.height = `${newHeight}px`;
}

function showFirstInfo(){
  if (!infoA || !infoB || INFO_VIEWS.length === 0) return;

  activeEl = infoA;
  idleEl   = infoB;

  setLayerText(activeEl, INFO_VIEWS[infoIndex].text);

  activeEl.className = 'lobby-infobox__layer is-active';
  idleEl.className   = 'lobby-infobox__layer';

  requestAnimationFrame(() => {
    fitInfoBoxToActive();
  });
}

function stepInfo(){
  if (!activeEl || !idleEl) return;

  infoIndex = (infoIndex + 1) % INFO_VIEWS.length;

  // Idle vorbereiten (unsichtbar)
  setLayerText(idleEl, INFO_VIEWS[infoIndex].text);
  idleEl.className = 'lobby-infobox__layer';

  // Transition starten
  requestAnimationFrame(() => {
    activeEl.classList.remove('is-active');
    activeEl.classList.add('is-exit');

    idleEl.classList.add('is-enter');
  });

  // Nach Ende: Zustände finalisieren + Layer tauschen
  setTimeout(() => {
    activeEl.className = 'lobby-infobox__layer';

    idleEl.classList.remove('is-enter');
    idleEl.classList.add('is-active');

    const tmp = activeEl;
    activeEl = idleEl;
    idleEl = tmp;

    fitInfoBoxToActive();
  }, INFO_ANIM_MS + 30);
}

function startInfoRotation(){
  if (!infoA || !infoB || INFO_VIEWS.length === 0) return;

  showFirstInfo();

  clearInterval(infoTimer);
  infoTimer = setInterval(stepInfo, INFO_HOLD_MS);
}

document.addEventListener('DOMContentLoaded', startInfoRotation);

window.addEventListener('resize', () => {
  clearTimeout(window.__preLobbyResizeTimer);
  window.__preLobbyResizeTimer = setTimeout(() => {
    fitInfoBoxToActive();
  }, 120);
});
