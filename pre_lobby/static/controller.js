// --- FILE: ./pre_lobby/static/controller.js ---

// =====================================================
// CONTROLLER REGISTRIERUNG
// =====================================================

socket.emit('register_controller');
socket.on('connect', () => {
  socket.emit('register_controller');
});

// =====================================================
// INFO BOX ROTATOR (2 Layer + Höhe anpassen)
// Box ist jetzt DIE CARD selbst
// =====================================================

// Wenn du exakt die gleichen Texte wie auf der TV willst: hier identisch halten.
const INFO_VIEWS = [
  { text: "Willkommen bei QuizShark!" },
  { text: "Das Quiz startet in Kürze." }
];

const INFO_HOLD_MS = 7000; // Standzeit pro Zeile
const INFO_ANIM_MS = 380;  // muss zur CSS transition passen (controller.css)

const box   = document.getElementById('prelobby-controller-infobox');
const infoA = document.getElementById('prelobby-controller-infobox-a');
const infoB = document.getElementById('prelobby-controller-infobox-b');

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

  // Reset, damit die Messung nicht durch alte Höhe verfälscht wird
  box.style.height = 'auto';

  // Höhe des aktiven Layers (Text + Layer-Padding)
  const textRect = activeEl.getBoundingClientRect();

  // Box-Vertikal-Padding + Border (offsetHeight - clientHeight)
  // WICHTIG: Card-Padding ist in CSS auf 0 gesetzt, Padding sitzt in den Layern.
  const verticalPadding = box.offsetHeight - box.clientHeight;

  const newHeight = Math.ceil(textRect.height + verticalPadding);
  box.style.height = `${newHeight}px`;
}

function showFirstInfo(){
  if (!infoA || !infoB || INFO_VIEWS.length === 0) return;

  activeEl = infoA;
  idleEl   = infoB;

  setLayerText(activeEl, INFO_VIEWS[infoIndex].text);

  activeEl.className = 'prelobby-infobox__layer is-active';
  idleEl.className   = 'prelobby-infobox__layer';

  requestAnimationFrame(() => {
    fitInfoBoxToActive();
  });
}

function stepInfo(){
  if (!activeEl || !idleEl) return;

  infoIndex = (infoIndex + 1) % INFO_VIEWS.length;

  // Idle vorbereiten (unsichtbar)
  setLayerText(idleEl, INFO_VIEWS[infoIndex].text);
  idleEl.className = 'prelobby-infobox__layer';

  // Transition starten
  requestAnimationFrame(() => {
    activeEl.classList.remove('is-active');
    activeEl.classList.add('is-exit');

    idleEl.classList.add('is-enter');
  });

  // Nach Ende: Zustände finalisieren + Layer tauschen
  setTimeout(() => {
    activeEl.className = 'prelobby-infobox__layer';

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
  clearTimeout(window.__preLobbyControllerResizeTimer);
  window.__preLobbyControllerResizeTimer = setTimeout(() => {
    fitInfoBoxToActive();
  }, 120);
});
