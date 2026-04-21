// --- FILE: ./lobby/static/tv.js ---

socket.emit('register_tv');
socket.on('connect', () => {
  socket.emit('register_tv');
});

// =====================================================
// CONFIG
// =====================================================

const JOIN_URL  = "http://192.168.8.203";
const WIFI_SSID = "QUIZSHARK";
const WIFI_PASS = "quizshark";

const MAX_COLS = 3;

// Info-Box
const INFO_VIEWS = [
  { text: `Willkommen bei QuizShark!`, swoosh: null,  glow: null },

  // SO LANGE dieser Text steht -> LINKER QR permanent (bis fertig angezeigt / bis Step wechselt)
  { text: `WICHTIG: Mitmachen geht nur\nim "QUIZSHARK" WLAN`, swoosh: 'wifi', glow: 'wifi' },

    // SO LANGE dieser Text steht -> LINKER QR permanent (bis fertig angezeigt / bis Step wechselt)
  { text: `Scanne für das WLAN den linken QR-Code`, swoosh: 'wifi', glow: 'wifi' },

      // SO LANGE dieser Text steht -> LINKER QR permanent (bis fertig angezeigt / bis Step wechselt)
  { text: `WLAN-Name: QUIZSHARK\nPasswort: quizshark`, swoosh: 'wifi', glow: 'wifi' },

      // Hier: KEIN Glow (weil du es nicht wolltest)
  { text: `Scanne dann den rechten QR-Code\nund öffne das Quiz auf dem Handy`, swoosh: 'url', glow: 'url' },

  // SO LANGE dieser Text steht -> RECHTER QR permanent
  { text: `Oder öffne diese Aresse im Browser:\nplay.quizshark.de`, swoosh: 'url', glow: 'url' },

    // SO LANGE dieser Text steht -> RECHTER QR permanent
  { text: `Melde dich dann mit deinem Namen an und klicke auf "Ich bin Bereit!"`, swoosh: 'null', glow: 'null' },


    // SO LANGE dieser Text steht -> RECHTER QR permanent
  { text: `Viel Spaß beim Quizzen!`, swoosh: 'null', glow: 'null' }
];




const INFO_HOLD_MS = 7000; // 5s Standzeit pro Segment
const INFO_ANIM_MS = 380;  // muss zur CSS transition passen

// =====================================================
// ELEMENTS
// =====================================================

const playersEl = document.getElementById('lobby-players');
const bgm       = document.getElementById('bgm');

const infoA = document.getElementById('lobby-infobox-a');
const infoB = document.getElementById('lobby-infobox-b');

// =====================================================
// BACKGROUND MUSIC
// =====================================================

if (bgm) {
  bgm.volume = 0.4;
}

socket.on('connect', () => {
  if (bgm) bgm.play().catch(() => {});
});

// =====================================================
// QR CODES (RESPONSIVE)
// =====================================================

function qrSizeFor(el){
  if (!el) return 320;

  const area = el.closest('.qr-codeArea');
  if (!area) return 320;

  // 88% vom quadratischen QR-Bereich
  const s = Math.floor(Math.min(area.clientWidth, area.clientHeight) * 0.88);
  return Math.max(140, s);
}


function ensureQR(){
  const wifiEl = document.getElementById("qr-wifi");
  const urlEl  = document.getElementById("qr-url");

  if (wifiEl) {
    const s = qrSizeFor(wifiEl);
    wifiEl.innerHTML = "";
    new QRCode(wifiEl, {
      text: `WIFI:T:WPA;S:${WIFI_SSID};P:${WIFI_PASS};;`,
      width: s,
      height: s,
      correctLevel: QRCode.CorrectLevel.M
    });
  }

  if (urlEl) {
    const s = qrSizeFor(urlEl);
    urlEl.innerHTML = "";
    new QRCode(urlEl, {
      text: JOIN_URL,
      width: s,
      height: s,
      correctLevel: QRCode.CorrectLevel.M
    });
  }
}

function fitQrSectionToViewport(){
  const left = document.querySelector('.lobby-left');
  const section = document.querySelector('.qr-section');
  if (!left || !section) return;

  // Reset für saubere Messung
  section.style.transform = 'none';

  const scale = Math.min(1, left.clientHeight / section.scrollHeight);
  section.style.transform = `scale(${scale})`;
}



document.addEventListener("DOMContentLoaded", () => {
  ensureQR();

  // ein Frame warten, damit QR/Fonts/layout wirklich stehen
  requestAnimationFrame(() => {
    fitQrSectionToViewport();
  });
});




// =====================================================
// INFO BOX ROTATOR (SLIDE UP/DOWN + FADE, 5s HOLD)
// =====================================================

let infoIndex = 0;
let infoTimer = null;
let activeEl = null;
let idleEl   = null;

function setLayerText(el, text){
  if (!el) return;
  el.textContent = text;
}

function fitInfoBoxToActive(){
  const box = document.getElementById('lobby-infobox');
  if (!box || !activeEl) return;

  // kurz auto, damit wir korrekt messen
  box.style.height = 'auto';

  // tatsächliche Höhe des aktiven Textes
  const textRect = activeEl.getBoundingClientRect();
  const boxRect  = box.getBoundingClientRect();

  // Padding vertikal = Boxhöhe - Textfläche
  const verticalPadding = boxRect.height - box.clientHeight;

  const newHeight = Math.ceil(textRect.height + verticalPadding);

  box.style.height = `${newHeight}px`;
}

// =====================================================
// QR HIGHLIGHTS (SWOOSH + GLOW)
// =====================================================


function playSwoosh(target){
  // reset
  document.querySelectorAll('.qr-captionBox').forEach(el => {
    el.classList.remove('is-swoosh');
  });

  if (!target) return;

  const steps = {
    wifi: document.querySelector('.qr-step[data-step="wifi"]'),
    url:  document.querySelector('.qr-step[data-step="url"]')
  };

  if (target === 'both') {
    steps.wifi?.classList.add('is-swoosh');
    setTimeout(() => steps.url?.classList.add('is-swoosh'), 450);
  } else {
    steps[target]?.classList.add('is-swoosh');
  }
}

// Persistenter Glow: bleibt an, bis der nächste Step etwas anderes setzt
function setGlow(target){
  const wifiTile = document.getElementById('qr-wifi')?.closest('.qr-tile, .qr-step');
  const urlTile  = document.getElementById('qr-url') ?.closest('.qr-tile, .qr-step');

  // reset immer zuerst
  wifiTile?.classList.remove('is-glow');
  urlTile?.classList.remove('is-glow');

  if (!target) return;

  if (target === 'both') {
    wifiTile?.classList.add('is-glow');
    urlTile?.classList.add('is-glow');
    return;
  }

  if (target === 'wifi') wifiTile?.classList.add('is-glow');
  if (target === 'url')  urlTile?.classList.add('is-glow');
}



function showFirstInfo(){
  if (!infoA || !infoB || INFO_VIEWS.length === 0) return;

  activeEl = infoA;
  idleEl   = infoB;

  setLayerText(activeEl, INFO_VIEWS[infoIndex].text);

  activeEl.className = 'lobby-infobox__layer is-active';
  idleEl.className   = 'lobby-infobox__layer';

  fitInfoBoxToActive();

  // initiale Highlights
  const swooshTarget = INFO_VIEWS[infoIndex].swoosh;
  const glowTarget   = INFO_VIEWS[infoIndex].glow;
  setTimeout(() => {
    playSwoosh(swooshTarget);
    setGlow(glowTarget);
  }, 200);
}


function stepInfo(){
  if (!activeEl || !idleEl) return;

  infoIndex = (infoIndex + 1) % INFO_VIEWS.length;

  // Idle vorbereiten (unsichtbar unten)
  setLayerText(idleEl, INFO_VIEWS[infoIndex].text);

  idleEl.className = 'lobby-infobox__layer';

  // Transition starten
  requestAnimationFrame(() => {
    // Aktiver Text raus (oben)
    activeEl.classList.remove('is-active');
    activeEl.classList.add('is-exit');

    // Neuer Text rein (von unten)
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
fitQrSectionToViewport();

const swooshTarget = INFO_VIEWS[infoIndex].swoosh;
const glowTarget   = INFO_VIEWS[infoIndex].glow;

setTimeout(() => {
  playSwoosh(swooshTarget);
  setGlow(glowTarget);
}, 0);




  }, INFO_ANIM_MS + 30);

}

function startInfoRotation(){
  if (!infoA || !infoB || INFO_VIEWS.length === 0) return;

  showFirstInfo();

  // wichtig: sobald der erste Text aktiv ist -> nochmal proportional fitten
  requestAnimationFrame(() => {
    fitQrSectionToViewport();
  });

  clearInterval(infoTimer);
  infoTimer = setInterval(stepInfo, INFO_HOLD_MS);
}


document.addEventListener("DOMContentLoaded", startInfoRotation);

// =====================================================
// Helpers: messen, wie viele Cards pro Spalte passen
// (robust: misst echte Row-Höhe + echtes Gap der .ps__col)
// =====================================================

function measureRowHeight(){
  if (!playersEl) return 0;

  const probe = document.createElement('div');
  probe.className = 'ps__player is-not-ready';
  probe.style.position = 'absolute';
  probe.style.left = '0';
  probe.style.top = '0';
  probe.style.visibility = 'hidden';
  probe.style.pointerEvents = 'none';
  probe.innerHTML = `
    <div class="ps__playerCard">
      <div class="ps__playerName">Probe</div>
    </div>
  `;
  playersEl.appendChild(probe);
  const h = probe.getBoundingClientRect().height;
  playersEl.removeChild(probe);
  return h;
}

function measureRowGapPx(rowH){
  if (!playersEl) return 0;

  const col = document.createElement('div');
  col.className = 'ps__col';
  col.style.position = 'absolute';
  col.style.left = '0';
  col.style.top = '0';
  col.style.visibility = 'hidden';
  col.style.pointerEvents = 'none';

  col.innerHTML = `
    <div class="ps__player is-not-ready">
      <div class="ps__playerCard"><div class="ps__playerName">A</div></div>
    </div>
    <div class="ps__player is-not-ready">
      <div class="ps__playerCard"><div class="ps__playerName">B</div></div>
    </div>
  `;
  playersEl.appendChild(col);

  const first = col.children[0].getBoundingClientRect();
  const second = col.children[1].getBoundingClientRect();

  playersEl.removeChild(col);

  const step = Math.max(0, (second.top - first.top));
  const gap = Math.max(0, step - (rowH || 0));
  return gap;
}

function computeRowsPerCol(){
  if (!playersEl) return 0;

  const availH = playersEl.getBoundingClientRect().height;
  if (!availH || availH < 10) return 0;

  const rowH = measureRowHeight();
  if (!rowH || rowH < 5) return 0;

  const gapPx = measureRowGapPx(rowH);
  const step = rowH + gapPx;

  const rows = Math.max(1, Math.floor((availH + gapPx) / step));
  return rows;
}

// -----------------------------------------------------
// Render
// Gewünschte Logik:
// - immer rechts befüllen (oben->unten)
// - wenn rechts voll: bestehende Spalten "rutschen" nach links,
//   rechts entsteht eine neue Spalte
// -----------------------------------------------------

let lastPlayers = [];

function renderPlayers(players){
  if (!playersEl) return;

  const list = Array.isArray(players) ? players : [];
  const rowsPerCol = computeRowsPerCol() || 8; // Fallback

  playersEl.innerHTML = '';
  if (list.length === 0) return;

  const capacity = rowsPerCol;
  const maxVisibleSlots = capacity * MAX_COLS;

  // Overflow: 1 Slot für "+X weitere" reservieren
  const needsMore = list.length > maxVisibleSlots;
  const visibleSlots = needsMore ? Math.max(0, maxVisibleSlots - 1) : maxVisibleSlots;

  // Sichtbar bleiben die letzten N Spieler (neueste bleiben im Bild, rechts)
  const shown = list.slice(Math.max(0, list.length - visibleSlots));
  const hiddenCount = list.length - shown.length;

  // In Spalten chunk-en: links->rechts alt->neu
  const allCols = [];
  for (let i = 0; i < shown.length; i += capacity) {
    allCols.push(shown.slice(i, i + capacity));
  }

  // Nur die letzten MAX_COLS Spalten zeigen (damit "Shift" entsteht)
  const visibleCols = allCols.slice(Math.max(0, allCols.length - MAX_COLS));

  // "+X weitere" kommt in die RECHTE sichtbare Spalte ganz UNTEN
  if (hiddenCount > 0) {
    if (visibleCols.length === 0) visibleCols.push([]);

    const lastColIdx = visibleCols.length - 1;
    const col = visibleCols[lastColIdx];

    // wenn voll: letzte echte Player-Card rauswerfen
    if (col.length >= capacity) {
      col.pop();
    }

    col.push({ __moreCard: true, hiddenCount });
  }

  // Render: links->rechts (rechts ist die "aktuelle" Spalte)
  for (const colPlayers of visibleCols) {
    const col = document.createElement('div');
    col.className = 'ps__col';

    for (const p of colPlayers) {
      if (p && p.__moreCard) col.appendChild(makeMoreCard(p.hiddenCount));
      else col.appendChild(makePlayerCard(p));
    }

    playersEl.appendChild(col);
  }
}

function makePlayerCard(player){
  const p = player || {};
  const isReady = !!p.ready;

  const row = document.createElement('div');
  row.className = 'ps__player ' + (isReady ? 'is-ready' : 'is-not-ready');
  row.id = `player-${p.player_id}`;

  row.innerHTML = `
    <div class="ps__playerCard">
      <div class="ps__playerName">${escapeHtml(p.name || '')}</div>
    </div>
  `;
  return row;
}

function makeMoreCard(hiddenCount){
  const row = document.createElement('div');
  row.className = 'ps__player ps__player--more';
  row.innerHTML = `
    <div class="ps__playerCard">
      <div class="ps__playerName">+ ${hiddenCount} weitere</div>
    </div>
  `;
  return row;
}

function escapeHtml(str){
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// -----------------------------------------------------
// Re-render bei Resize (TV-Auflösung / Zoom / Browser-UI)
// -----------------------------------------------------

let resizeTimer = null;

window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    ensureQR();
    fitQrSectionToViewport();
    renderPlayers(lastPlayers);
  }, 150);
});

// -----------------------------------------------------
// Socket Event
// -----------------------------------------------------

socket.on('update_lobby', function(players) {
  lastPlayers = Array.isArray(players) ? players : [];
  renderPlayers(lastPlayers);
});
