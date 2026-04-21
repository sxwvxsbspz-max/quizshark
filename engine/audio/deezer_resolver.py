# --- FILE: ./engine/audio/deezer_resolver.py ---
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
deezer_resolver.py

Zweck:
- Kapselt ausschließlich Deezer-Logik.
- Löst Deezer-Audio-Referenzen wie "deezer:<track_id>" in eine abspielbare Preview-MP3-URL auf.
- Enthält Cache + TTL, damit nicht bei jeder Frage Deezer abgefragt wird.

Wichtig:
- KEIN Routing / keine Policy hier (das macht ./engine/audio/resolve_audio.py).
- KEIN Schreiben in questions.json.
- Dieser Resolver kennt nur Deezer.

Hinweis:
- Deezer Preview ist i.d.R. 30 Sekunden MP3 ("preview" Feld).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import requests


DEEZE_TRACK_ENDPOINT = "https://api.deezer.com/track/{track_id}"

# "deezer:3135556" oder "deezer://3135556" tolerieren wir beide
_DEEZER_REF_RE = re.compile(r"^deezer(?:://|:)(\d+)\s*$", re.IGNORECASE)


@dataclass
class DeezerResolveResult:
    ok: bool
    url: Optional[str] = None
    track_id: Optional[int] = None
    reason: Optional[str] = None


class DeezerResolver:
    """
    Resolver mit Cache + TTL.

    Usage:
      resolver = DeezerResolver()
      res = resolver.resolve("deezer:3135556")   # -> DeezerResolveResult
      url = resolver.resolve_to_url("deezer:3135556")  # -> preview url or None
    """

    def __init__(
        self,
        timeout_seconds: float = 6.0,
        cache_ttl_seconds: int = 6 * 60 * 60,  # 6 Stunden
        user_agent: str = "BlitzQuiz/1.0 (DeezerResolver)",
    ):
        self.timeout_seconds = float(timeout_seconds)
        self.cache_ttl_seconds = int(cache_ttl_seconds)
        self.user_agent = user_agent

        # cache: track_id -> (expires_epoch, preview_url or None, reason_if_none)
        self._cache: Dict[int, Tuple[float, Optional[str], Optional[str]]] = {}

        # Session für Connection Reuse
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.user_agent})

    # -------------------------
    # Public API
    # -------------------------

    def resolve(self, audio_ref: Optional[str]) -> DeezerResolveResult:
        """
        Wenn audio_ref ein Deezer-Ref ist, löst es zu preview-URL auf.

        - audio_ref None/"" -> ok=False
        - audio_ref kein Deezer-Ref -> ok=False
        """
        if not audio_ref:
            return DeezerResolveResult(ok=False, reason="empty_ref")

        m = _DEEZER_REF_RE.match(audio_ref.strip())
        if not m:
            return DeezerResolveResult(ok=False, reason="not_deezer_ref")

        track_id = int(m.group(1))

        # Cache check
        cached = self._cache.get(track_id)
        now = time.time()
        if cached:
            expires_at, url, reason = cached
            if now < expires_at:
                if url:
                    return DeezerResolveResult(ok=True, url=url, track_id=track_id)
                return DeezerResolveResult(ok=False, url=None, track_id=track_id, reason=reason or "no_preview_cached")
            else:
                # expired -> drop
                self._cache.pop(track_id, None)

        # Fetch from Deezer
        res = self._fetch_track(track_id)

        # Cache result (auch negative Ergebnisse cachen)
        self._cache[track_id] = (
            now + self.cache_ttl_seconds,
            res.url,
            res.reason,
        )
        return res

    def resolve_to_url(
        self,
        audio_ref: Optional[str],
        *,
        local_audio_base_url: Optional[str] = None,
        allow_passthrough_urls: bool = True,
    ) -> Optional[str]:
        """
        Convenience: gibt direkt eine URL zurück, die du ans Frontend geben kannst.

        Regeln:
        - "deezer:<id>" -> Deezer preview URL (wenn vorhanden)
        - absolute URL (http/https) -> bleibt (wenn allow_passthrough_urls=True)
        - sonst:
            - wenn local_audio_base_url gesetzt: local_audio_base_url + "/" + filename
            - sonst: audio_ref unverändert zurückgeben
        - Wenn Deezer keine Preview hat: None

        Beispiel:
          resolve_to_url("question-8.mp3", local_audio_base_url="/soundtracks/media/audio")
            -> "/soundtracks/media/audio/question-8.mp3"
        """
        if not audio_ref:
            return None

        s = audio_ref.strip()

        # Deezer?
        r = self.resolve(s)
        if r.ok and r.url:
            return r.url
        if r.reason and r.reason.startswith("deezer_"):
            # expliziter Deezer-Fail -> None
            return None

        # Passthrough absolute URL?
        if allow_passthrough_urls and (s.startswith("http://") or s.startswith("https://")):
            return s

        # Lokale Datei -> base url prefixen
        if local_audio_base_url:
            base = local_audio_base_url.rstrip("/")
            # wenn s schon wie "/soundtracks/media/audio/x.mp3" aussieht, nicht doppelt prefixen
            if s.startswith("/"):
                return s
            return f"{base}/{s}"

        # Fallback: unverändert
        return s

    def clear_cache(self) -> None:
        self._cache.clear()

    # -------------------------
    # Internals
    # -------------------------

    def _fetch_track(self, track_id: int) -> DeezerResolveResult:
        url = DEEZE_TRACK_ENDPOINT.format(track_id=track_id)
        try:
            r = self._session.get(url, timeout=self.timeout_seconds)
        except requests.RequestException as e:
            return DeezerResolveResult(
                ok=False,
                track_id=track_id,
                reason=f"deezer_request_error:{type(e).__name__}",
            )

        if r.status_code != 200:
            return DeezerResolveResult(
                ok=False,
                track_id=track_id,
                reason=f"deezer_http_{r.status_code}",
            )

        try:
            data = r.json()
        except ValueError:
            return DeezerResolveResult(
                ok=False,
                track_id=track_id,
                reason="deezer_bad_json",
            )

        # Deezer liefert bei Fehlern manchmal {"error": {...}}
        if isinstance(data, dict) and "error" in data:
            code = None
            try:
                code = (data.get("error") or {}).get("code")
            except Exception:
                code = None
            return DeezerResolveResult(
                ok=False,
                track_id=track_id,
                reason=f"deezer_api_error:{code}" if code is not None else "deezer_api_error",
            )

        preview = data.get("preview") if isinstance(data, dict) else None
        if not preview or not isinstance(preview, str):
            return DeezerResolveResult(
                ok=False,
                track_id=track_id,
                reason="deezer_no_preview",
            )

        # preview sollte eine http(s) URL sein
        if not (preview.startswith("http://") or preview.startswith("https://")):
            return DeezerResolveResult(
                ok=False,
                track_id=track_id,
                reason="deezer_preview_not_url",
            )

        return DeezerResolveResult(ok=True, url=preview, track_id=track_id)


# Optional: simples Singleton, falls du überall denselben Cache nutzen willst.
_default_resolver: Optional[DeezerResolver] = None


def get_default_resolver() -> DeezerResolver:
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = DeezerResolver()
    return _default_resolver
