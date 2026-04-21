# --- FILE: ./engine/audio/itunes_resolver.py ---
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
itunes_resolver.py

Zweck:
- Kapselt ausschließlich Apple / iTunes Logik.
- Unterstützt:
    - Lookup per Track-ID:   itunes:<track_id>
    - Auto-Search:           itunes_auto  (Search via title + artist)
- Liefert:
    - preview URL (30s)
    - optional: year (int), abgeleitet aus releaseDate

Wichtig:
- KEIN Routing / keine Policy hier (das macht resolve_audio.py).
- KEIN Schreiben in questions.json.
- Resolver gibt nur Daten zurück (duck-typed: Dataclass ODER dict).
"""

from __future__ import annotations

import time
import re
from dataclasses import dataclass
from typing import Optional, Dict, Tuple

import requests


# -------------------------
# Endpoints
# -------------------------

ITUNES_SEARCH_ENDPOINT = "https://itunes.apple.com/search"
ITUNES_LOOKUP_ENDPOINT = "https://itunes.apple.com/lookup"


# -------------------------
# Result-Objekt
# -------------------------

@dataclass
class ITunesResolveResult:
    ok: bool
    url: Optional[str] = None
    year: Optional[int] = None
    reason: Optional[str] = None


# -------------------------
# Resolver
# -------------------------

class ITunesResolver:
    """
    Apple iTunes Resolver mit Cache + TTL.

    - Kein Auth nötig (iTunes Search API)
    - Preview kommt aus Feld: previewUrl
    """

    def __init__(
        self,
        timeout_seconds: float = 6.0,
        cache_ttl_seconds: int = 6 * 60 * 60,  # 6h
        user_agent: str = "BlitzQuiz/1.0 (ITunesResolver)",
        country: str = "DE",
    ):
        self.timeout_seconds = float(timeout_seconds)
        self.cache_ttl_seconds = int(cache_ttl_seconds)
        self.user_agent = user_agent
        self.country = country

        # cache key -> (expires_epoch, ITunesResolveResult)
        self._cache: Dict[str, Tuple[float, ITunesResolveResult]] = {}

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self.user_agent})

    # -------------------------------------------------
    # Public API
    # -------------------------------------------------

    def resolve_track_id(self, track_id: int) -> ITunesResolveResult:
        """
        Lookup per iTunes Track-ID.
        """
        cache_key = f"id:{track_id}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            r = self._session.get(
                ITUNES_LOOKUP_ENDPOINT,
                params={
                    "id": track_id,
                    "entity": "song",
                    "country": self.country,
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as e:
            return self._cache_and_return(
                cache_key,
                ITunesResolveResult(ok=False, reason=f"itunes_request_error:{type(e).__name__}"),
            )

        if r.status_code != 200:
            return self._cache_and_return(
                cache_key,
                ITunesResolveResult(ok=False, reason=f"itunes_http_{r.status_code}"),
            )

        try:
            data = r.json()
        except ValueError:
            return self._cache_and_return(
                cache_key,
                ITunesResolveResult(ok=False, reason="itunes_bad_json"),
            )

        results = data.get("results") or []
        if not results:
            return self._cache_and_return(
                cache_key,
                ITunesResolveResult(ok=False, reason="itunes_no_results"),
            )

        return self._cache_and_return(
            cache_key,
            self._extract_preview_and_year(results[0]),
        )

    def search_preview(self, *, title: str, artist: str) -> ITunesResolveResult:
        """
        Auto-Search via title + artist.
        """
        norm_key = self._normalize_key(title, artist)
        cache_key = f"search:{norm_key}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        query = f"{artist} {title}".strip()

        try:
            r = self._session.get(
                ITUNES_SEARCH_ENDPOINT,
                params={
                    "term": query,
                    "media": "music",
                    "entity": "song",
                    "limit": 10,
                    "country": self.country,
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as e:
            return self._cache_and_return(
                cache_key,
                ITunesResolveResult(ok=False, reason=f"itunes_request_error:{type(e).__name__}"),
            )

        if r.status_code != 200:
            return self._cache_and_return(
                cache_key,
                ITunesResolveResult(ok=False, reason=f"itunes_http_{r.status_code}"),
            )

        try:
            data = r.json()
        except ValueError:
            return self._cache_and_return(
                cache_key,
                ITunesResolveResult(ok=False, reason="itunes_bad_json"),
            )

        results = data.get("results") or []
        if not results:
            return self._cache_and_return(
                cache_key,
                ITunesResolveResult(ok=False, reason="itunes_no_results"),
            )

        # Best-Match Heuristik (einfach & robust):
        # - exakter Artist-Name bevorzugt
        # - danach erster Treffer
        best = self._pick_best_match(results, title, artist)

        return self._cache_and_return(
            cache_key,
            self._extract_preview_and_year(best),
        )

    # -------------------------------------------------
    # Internals
    # -------------------------------------------------

    def _extract_preview_and_year(self, item: dict) -> ITunesResolveResult:
        preview = item.get("previewUrl")
        if not preview or not isinstance(preview, str):
            return ITunesResolveResult(ok=False, reason="itunes_no_preview")

        year = None
        release_date = item.get("releaseDate")
        if isinstance(release_date, str) and len(release_date) >= 4:
            try:
                year = int(release_date[:4])
            except ValueError:
                year = None

        return ITunesResolveResult(ok=True, url=preview, year=year)

    def _pick_best_match(self, results: list, title: str, artist: str) -> dict:
        title_l = title.lower()
        artist_l = artist.lower()

        for r in results:
            if (
                isinstance(r.get("trackName"), str)
                and isinstance(r.get("artistName"), str)
                and r["trackName"].lower() == title_l
                and r["artistName"].lower() == artist_l
            ):
                return r

        return results[0]

    def _normalize_key(self, title: str, artist: str) -> str:
        s = f"{artist}|{title}".lower()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[^\w\s|]", "", s)
        return s.strip()

    def _get_cached(self, key: str) -> Optional[ITunesResolveResult]:
        now = time.time()
        entry = self._cache.get(key)
        if not entry:
            return None
        expires_at, result = entry
        if now < expires_at:
            return result
        self._cache.pop(key, None)
        return None

    def _cache_and_return(self, key: str, result: ITunesResolveResult) -> ITunesResolveResult:
        self._cache[key] = (time.time() + self.cache_ttl_seconds, result)
        return result

    def clear_cache(self) -> None:
        self._cache.clear()
