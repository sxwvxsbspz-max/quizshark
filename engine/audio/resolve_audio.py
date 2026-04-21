# --- FILE: ./engine/audio/resolve_audio.py ---
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
resolve_audio.py

Zweck:
- Zentraler Dispatcher ("Switchboard") für Audio-Refs in questions.json.
- Kapselt Routing/Policy:
    - absolute URLs -> passthrough
    - deezer:<track_id> -> Deezer preview URL
    - itunes:<track_id> -> iTunes/Apple preview URL (Lookup)
    - itunes_auto -> iTunes/Apple preview URL (Search per title+artist)
    - sonst -> lokale Datei (base url prefixen)

Wichtig:
- Diese Datei ist der EINZIGE Einstiegspunkt für Module (z.B. soundtracks/logic.py).
- Deezer/iTunes-spezifische Implementierung liegt in separaten Resolvern.

Erwartete Resolver-APIs (duck-typed):
- Deezer: engine/audio/deezer_resolver.py
    - class DeezerResolver
        - resolve_to_url(audio_ref, local_audio_base_url=None, allow_passthrough_urls=True) -> Optional[str]
- iTunes: engine/audio/itunes_resolver.py (neu)
    - class ITunesResolver
        - resolve_track_id(track_id: int) -> ITunesResolveResult (oder kompatibles Dict)
        - search_preview(title: str, artist: str) -> ITunesResolveResult (oder kompatibles Dict)
      wobei das Result idealerweise enthält:
        - url (previewUrl)
        - year (int) optional (abgeleitet aus releaseDate)
        - reason (str) optional

Diese Datei schreibt NICHT automatisch in questions.json zurück. Sie liefert nur "resolved_year"
zurück, damit die aufrufende Logic entscheiden kann: "nur wenn year leer ist -> setzen".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Literal


# -------------------------
# Ref-Parser
# -------------------------

_DEEZER_REF_RE = re.compile(r"^deezer(?:://|:)(\d+)\s*$", re.IGNORECASE)
_ITUNES_REF_RE = re.compile(r"^itunes(?:://|:)(\d+)\s*$", re.IGNORECASE)

_ITUNES_AUTO_TOKEN = "itunes_auto"


# -------------------------
# Public result
# -------------------------

Provider = Literal["deezer", "itunes", "passthrough", "local", "none"]


@dataclass
class AudioResolveResult:
    ok: bool
    url: Optional[str] = None
    provider: Provider = "none"
    resolved_year: Optional[int] = None  # nur gesetzt, wenn aus Apple abgeleitet & year vorher leer sein darf
    reason: Optional[str] = None         # Debug/Logging


# -------------------------
# Lazy singletons (shared cache)
# -------------------------

_deezer_singleton = None
_itunes_singleton = None


def _get_deezer_resolver():
    global _deezer_singleton
    if _deezer_singleton is None:
        # Import nur hier, damit keine Import-Zyklen entstehen
        from engine.audio.deezer_resolver import DeezerResolver  # type: ignore
        _deezer_singleton = DeezerResolver()
    return _deezer_singleton


def _get_itunes_resolver():
    global _itunes_singleton
    if _itunes_singleton is None:
        # Neu: muss von dir erstellt werden: engine/audio/itunes_resolver.py
        from engine.audio.itunes_resolver import ITunesResolver  # type: ignore
        _itunes_singleton = ITunesResolver()
    return _itunes_singleton


# -------------------------
# Small helpers
# -------------------------

def _is_abs_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _localize_filename(s: str, local_audio_base_url: Optional[str]) -> str:
    if not local_audio_base_url:
        return s
    base = local_audio_base_url.rstrip("/")
    if s.startswith("/"):
        return s  # schon absoluter Pfad
    return f"{base}/{s}"


# -------------------------
# Public API
# -------------------------

def resolve_audio_ref(
    audio_ref: Optional[str],
    *,
    # Kontext für itunes_auto + year-enrichment
    title: Optional[str] = None,
    artist: Optional[str] = None,
    year: Optional[int] = None,
    # Local / passthrough policy
    local_audio_base_url: Optional[str] = None,
    allow_passthrough_urls: bool = True,
) -> AudioResolveResult:
    """
    Zentraler Dispatcher.

    Inputs:
      - audio_ref:
          - "deezer:<id>"      -> Deezer preview URL
          - "itunes:<id>"      -> iTunes preview URL (Lookup)
          - "itunes_auto"      -> iTunes preview URL (Search via title+artist)
          - "https://..."      -> passthrough (wenn allow_passthrough_urls=True)
          - "file.mp3"         -> local_audio_base_url + "/file.mp3" (wenn gesetzt)

      - title/artist/year:
          - nur relevant für audio_ref == "itunes_auto"
          - Wenn year fehlt/leer, kann resolved_year gesetzt werden (aus releaseDate).

    Output:
      - AudioResolveResult:
          - url: was du ans Frontend geben kannst
          - resolved_year: optional (nur bei Apple)
    """
    if not audio_ref or not str(audio_ref).strip():
        return AudioResolveResult(ok=False, url=None, provider="none", reason="empty_ref")

    s = str(audio_ref).strip()

    # 1) Absolute URL passthrough
    if allow_passthrough_urls and _is_abs_url(s):
        return AudioResolveResult(ok=True, url=s, provider="passthrough")

    # 2) Deezer ref?
    m = _DEEZER_REF_RE.match(s)
    if m:
        try:
            deezer = _get_deezer_resolver()
            # DeezerResolver.resolve_to_url akzeptiert die Ref direkt
            url = deezer.resolve_to_url(
                s,
                local_audio_base_url=local_audio_base_url,
                allow_passthrough_urls=allow_passthrough_urls,
            )
            if url:
                return AudioResolveResult(ok=True, url=url, provider="deezer")
            return AudioResolveResult(ok=False, url=None, provider="deezer", reason="deezer_no_preview")
        except Exception as e:
            return AudioResolveResult(ok=False, url=None, provider="deezer", reason=f"deezer_exception:{type(e).__name__}")

    # 3) iTunes track id ref?
    m = _ITUNES_REF_RE.match(s)
    if m:
        track_id = int(m.group(1))
        try:
            itunes = _get_itunes_resolver()
            r = itunes.resolve_track_id(track_id)

            # duck-typing: r kann dataclass oder dict sein
            url = getattr(r, "url", None) if not isinstance(r, dict) else r.get("url")
            ry  = getattr(r, "year", None) if not isinstance(r, dict) else r.get("year")
            rsn = getattr(r, "reason", None) if not isinstance(r, dict) else r.get("reason")

            if url:
                # year nicht überschreiben: nur "vorschlagen"
                resolved_year = int(ry) if (ry is not None and (year is None)) else None
                return AudioResolveResult(ok=True, url=url, provider="itunes", resolved_year=resolved_year)
            return AudioResolveResult(ok=False, url=None, provider="itunes", reason=rsn or "itunes_no_preview")
        except Exception as e:
            return AudioResolveResult(ok=False, url=None, provider="itunes", reason=f"itunes_exception:{type(e).__name__}")

    # 4) iTunes auto token?
    if s.lower() == _ITUNES_AUTO_TOKEN:
        # title+artist müssen existieren
        t = (title or "").strip()
        a = (artist or "").strip()
        if not t or not a:
            return AudioResolveResult(ok=False, url=None, provider="itunes", reason="itunes_auto_missing_title_or_artist")

        try:
            itunes = _get_itunes_resolver()
            r = itunes.search_preview(title=t, artist=a)

            url = getattr(r, "url", None) if not isinstance(r, dict) else r.get("url")
            ry  = getattr(r, "year", None) if not isinstance(r, dict) else r.get("year")
            rsn = getattr(r, "reason", None) if not isinstance(r, dict) else r.get("reason")

            if url:
                resolved_year = int(ry) if (ry is not None and (year is None)) else None
                return AudioResolveResult(ok=True, url=url, provider="itunes", resolved_year=resolved_year)
            return AudioResolveResult(ok=False, url=None, provider="itunes", reason=rsn or "itunes_auto_no_match_or_no_preview")
        except Exception as e:
            return AudioResolveResult(ok=False, url=None, provider="itunes", reason=f"itunes_exception:{type(e).__name__}")

    # 5) Fallback: lokale Datei / roher String
    # (Wenn local_audio_base_url gesetzt -> prefixen, sonst unverändert lassen)
    url = _localize_filename(s, local_audio_base_url)
    return AudioResolveResult(ok=True, url=url, provider="local")


def resolve_audio_url(
    audio_ref: Optional[str],
    *,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    year: Optional[int] = None,
    local_audio_base_url: Optional[str] = None,
    allow_passthrough_urls: bool = True,
) -> Optional[str]:
    """
    Convenience: nur URL zurückgeben (kompatibel zu "alt").
    """
    r = resolve_audio_ref(
        audio_ref,
        title=title,
        artist=artist,
        year=year,
        local_audio_base_url=local_audio_base_url,
        allow_passthrough_urls=allow_passthrough_urls,
    )
    return r.url
