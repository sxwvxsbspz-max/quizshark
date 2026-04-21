# --- FILE: ./songquiz/additunes.py ---
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import threading
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, request, jsonify, Response

# ----------------------------
# Config
# ----------------------------

BASE_DIR = os.path.dirname(__file__)
QUESTIONS_FILE = os.path.join(BASE_DIR, "new_questions.json")

PORT = 8000
HOST = "0.0.0.0"

ITUNES_SEARCH_ENDPOINT = "https://itunes.apple.com/search"
COUNTRY = "DE"
LIMIT = 10

_write_lock = threading.Lock()

app = Flask(__name__)


# ----------------------------
# Helpers: new_questions.json
# ----------------------------

def _load_questions() -> List[Dict[str, Any]]:
    if not os.path.exists(QUESTIONS_FILE):
        return []
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data if isinstance(data, list) else []


def _save_questions(questions: List[Dict[str, Any]]) -> None:
    tmp = QUESTIONS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)
    os.replace(tmp, QUESTIONS_FILE)


def _next_id(questions: List[Dict[str, Any]]) -> int:
    if not questions:
        return 1
    max_id = 0
    for q in questions:
        try:
            max_id = max(max_id, int(q.get("id", 0)))
        except Exception:
            continue
    return max_id + 1


def _year_from_release_date(release_date: Any) -> Optional[int]:
    if isinstance(release_date, str) and len(release_date) >= 4:
        try:
            return int(release_date[:4])
        except ValueError:
            return None
    return None


# ----------------------------
# iTunes Search
# ----------------------------

def itunes_search(*, artist: str, title: str) -> List[Dict[str, Any]]:
    artist = (artist or "").strip()
    title = (title or "").strip()
    if not artist or not title:
        return []

    term = f"{artist} {title}".strip()

    try:
        r = requests.get(
            ITUNES_SEARCH_ENDPOINT,
            params={
                "term": term,
                "media": "music",
                "entity": "song",
                "limit": LIMIT,
                "country": COUNTRY,
            },
            timeout=8,
        )
    except requests.RequestException:
        return []

    if r.status_code != 200:
        return []

    try:
        data = r.json()
    except ValueError:
        return []

    results = data.get("results") or []
    out: List[Dict[str, Any]] = []

    for item in results:
        if not isinstance(item, dict):
            continue

        preview = item.get("previewUrl")
        track_name = item.get("trackName")
        artist_name = item.get("artistName")
        track_id = item.get("trackId")
        release_date = item.get("releaseDate")

        if not (isinstance(preview, str) and preview.startswith(("http://", "https://"))):
            continue
        if not isinstance(track_name, str) or not isinstance(artist_name, str):
            continue

        out.append(
            {
                "trackId": track_id,
                "artist": artist_name,
                "title": track_name,
                "year": _year_from_release_date(release_date),
                "previewUrl": preview,
                "artworkUrl": item.get("artworkUrl100") if isinstance(item.get("artworkUrl100"), str) else "",
            }
        )

    # simple best-first ordering: exact-ish match first
    artist_l = artist.lower()
    title_l = title.lower()

    def score(hit: Dict[str, Any]) -> int:
        s = 0
        if str(hit.get("artist", "")).lower() == artist_l:
            s += 50
        if str(hit.get("title", "")).lower() == title_l:
            s += 50
        # penalize obvious variants a bit
        t = str(hit.get("title", "")).lower()
        for bad in ["karaoke", "instrumental", "live", "remaster", "remastered", "tribute"]:
            if bad in t:
                s -= 10
        return s

    out.sort(key=score, reverse=True)
    return out


# ----------------------------
# HTML (served at http://localhost:8000/)
# ----------------------------

INDEX_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Add iTunes Track</title>
  <style>
    body { font-family: system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; margin: 24px; }
    h1 { margin: 0 0 8px; }
    .muted { opacity: .75; }
    .box { border: 1px solid #ddd; border-radius: 12px; padding: 14px; margin-top: 14px; }
    .row { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; }
    label { display: grid; gap: 6px; min-width: 260px; }
    input { padding: 10px 12px; font-size: 16px; border: 1px solid #ccc; border-radius: 10px; }
    button { padding: 10px 14px; font-size: 16px; cursor: pointer; border-radius: 10px; border: 1px solid #bbb; background: #f7f7f7; }
    button.primary { background: #111; color: #fff; border-color: #111; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .status { margin-top: 10px; font-size: 14px; }
    .ok { color: #0a7a2f; }
    .err { color: #b00020; }
    .hits { display: grid; gap: 10px; margin-top: 12px; }
    .hit { border: 1px solid #eee; border-radius: 12px; padding: 12px; display: grid; gap: 10px; }
    .hitTop { display: flex; gap: 12px; align-items: center; justify-content: space-between; flex-wrap: wrap; }
    .hitTitle { font-weight: 700; }
    .hitMeta { opacity: .8; font-size: 14px; }
    .hitLeft { display: grid; gap: 2px; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
    audio { width: 320px; max-width: 100%; }
    img.art { width: 60px; height: 60px; border-radius: 10px; object-fit: cover; border: 1px solid #eee; background: #fafafa; }
    .small { font-size: 13px; opacity: .8; }
    code { background: #f3f3f3; padding: 2px 6px; border-radius: 6px; }
  </style>
</head>
<body>
  <h1>iTunes Song hinzufügen</h1>
  <div class="muted">Suche per <b>Artist</b> + <b>Title</b>, Preview anhören, dann in <code>songquiz/new_questions.json</code> schreiben (audio = <code>itunes_auto</code>).</div>

  <div class="box">
    <div class="row">
      <label>
        Artist
        <input id="artist" placeholder="z. B. John Williams" autocomplete="off" />
      </label>
      <label>
        Title
        <input id="title" placeholder="z. B. Hedwig's Theme" autocomplete="off" />
      </label>
      <button id="btnSearch" class="primary">Search</button>
    </div>
    <div id="status" class="status muted"></div>
    <div id="results" class="hits"></div>
  </div>

<script>
  const elArtist  = document.getElementById("artist");
  const elTitle   = document.getElementById("title");
  const elBtn     = document.getElementById("btnSearch");
  const elStatus  = document.getElementById("status");
  const elResults = document.getElementById("results");

  function setStatus(msg, kind="") {
    elStatus.className = "status " + (kind === "ok" ? "ok" : kind === "err" ? "err" : "muted");
    elStatus.textContent = msg || "";
  }

  function stopAllAudio() {
    document.querySelectorAll("audio").forEach(a => {
      try { a.pause(); a.currentTime = 0; } catch(e) {}
    });
  }

  async function postJson(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    });
    const txt = await res.text();
    let data = null;
    try { data = JSON.parse(txt); } catch(e) {}
    return { ok: res.ok, status: res.status, data, raw: txt };
  }

  function renderHits(hits) {
    elResults.innerHTML = "";
    if (!hits || !hits.length) {
      elResults.innerHTML = "";
      return;
    }

    hits.forEach((h, idx) => {
      const div = document.createElement("div");
      div.className = "hit";

      const artist = h.artist || "";
      const title = h.title || "";
      const year = (h.year !== null && h.year !== undefined && h.year !== "") ? h.year : "";
      const previewUrl = h.previewUrl || "";
      const art = h.artworkUrl || "";

      div.innerHTML = `
        <div class="hitTop">
          <div style="display:flex; gap:12px; align-items:center;">
            ${art ? `<img class="art" src="${art}" alt="">` : `<div class="art" style="display:grid; place-items:center;"> </div>`}
            <div class="hitLeft">
              <div class="hitTitle">${title}</div>
              <div class="hitMeta">${artist}${year ? " • " + year : ""}</div>
              <div class="small">Treffer #${idx+1}</div>
            </div>
          </div>
          <div class="actions">
            <audio controls preload="none" src="${previewUrl}"></audio>
            <button class="btnAdd">Add to questions</button>
          </div>
        </div>
      `;

      const btnAdd = div.querySelector(".btnAdd");
      const audio = div.querySelector("audio");

      audio.addEventListener("play", () => {
        document.querySelectorAll("audio").forEach(a => { if (a !== audio) { try { a.pause(); } catch(e) {} } });
      });

      btnAdd.addEventListener("click", async () => {
        stopAllAudio();
        btnAdd.disabled = true;
        setStatus("Adding…");

        const payload = {
          artist: artist,
          title: title,
          year: year === "" ? null : Number(year)
        };

        const r = await postJson("/add", payload);

        if (!r.ok) {
          setStatus("Add fehlgeschlagen: " + (r.data && r.data.error ? r.data.error : r.raw), "err");
          btnAdd.disabled = false;
          return;
        }

        const newId = r.data && r.data.entry ? r.data.entry.id : null;
        setStatus("Added ✓ (id: " + newId + ")", "ok");
        btnAdd.disabled = false;
      });

      elResults.appendChild(div);
    });
  }

  async function doSearch() {
    stopAllAudio();
    const artist = (elArtist.value || "").trim();
    const title = (elTitle.value || "").trim();

    if (!artist || !title) {
      setStatus("Bitte Artist und Title ausfüllen.", "err");
      return;
    }

    elBtn.disabled = true;
    setStatus("Searching…");

    const r = await postJson("/search", { artist, title });

    elBtn.disabled = false;

    if (!r.ok) {
      setStatus("Search fehlgeschlagen: " + (r.data && r.data.error ? r.data.error : r.raw), "err");
      elResults.innerHTML = "";
      return;
    }

    const hits = (r.data && r.data.hits) ? r.data.hits : [];
    if (!hits.length) {
      setStatus("Keine Treffer mit Preview gefunden.", "err");
      elResults.innerHTML = "";
      return;
    }

    setStatus("Treffer: " + hits.length + " (du kannst Preview abspielen und einen auswählen).", "ok");
    renderHits(hits);
  }

  elBtn.addEventListener("click", doSearch);
  elTitle.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
  elArtist.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
</script>
</body>
</html>
"""


# ----------------------------
# Routes
# ----------------------------

@app.get("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html; charset=utf-8")


@app.post("/search")
def api_search():
    data = request.get_json(silent=True) or {}
    artist = (data.get("artist") or "").strip()
    title = (data.get("title") or "").strip()

    if not artist or not title:
        return jsonify({"hits": [], "error": "artist and title are required"}), 400

    hits = itunes_search(artist=artist, title=title)
    return jsonify({"hits": hits})


@app.post("/add")
def api_add():
    data = request.get_json(silent=True) or {}
    artist = (data.get("artist") or "").strip()
    title = (data.get("title") or "").strip()
    year = data.get("year", None)

    if not artist or not title:
        return jsonify({"error": "artist and title are required"}), 400

    # accept year as int or null
    year_val: Optional[int] = None
    if year is not None and year != "":
        try:
            year_val = int(year)
        except Exception:
            year_val = None

    with _write_lock:
        questions = _load_questions()
        new_id = _next_id(questions)

        entry = {
            "id": new_id,
            "category": "Soundtracks",
            "question": "",
            "correct": "",
            "wrong": [],
            "image": "",
            "lastplayed": "",
            "audio": "itunes_auto",
            "artist": artist,
            "title": title,
            "year": year_val if year_val is not None else "",
        }

        questions.append(entry)
        _save_questions(questions)

    return jsonify({"ok": True, "entry": entry})


# ----------------------------
# Main
# ----------------------------

if __name__ == "__main__":
    print(f"[additunes] Serving on http://localhost:{PORT}/")
    app.run(host=HOST, port=PORT, debug=False)
