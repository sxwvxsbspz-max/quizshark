# --- FILE: ./engine/text/normalize_answer.py ---

import re
import unicodedata


def normalize_answer(value) -> str:
    """
    Normalisiert Freitext-Antworten für FreeKnowledge.

    Regeln:
    - None -> ""
    - in String umwandeln
    - trimmen
    - lowercase
    - deutsche Umlaute / ß:
        ä -> ae
        ö -> oe
        ü -> ue
        Ä -> ae
        Ö -> oe
        Ü -> ue
        ß -> ss
    - Akzente/Diakritika entfernen
    - Leerzeichen entfernen
    - Punkte / Satzzeichen / Sonderzeichen entfernen
    - nur a-z und 0-9 behalten

    Beispiele:
    - " Michael Jackson "   -> "michaeljackson"
    - "Mönchengladbach"     -> "moenchengladbach"
    - "Straße"              -> "strasse"
    - "AC/DC"               -> "acdc"
    - "Björk"               -> "bjork"
    """
    if value is None:
        return ""

    s = str(value).strip().lower()

    # Deutsche Sonderfälle zuerst
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
    for src, dst in replacements.items():
        s = s.replace(src, dst)

    # Unicode normalisieren und Akzente entfernen
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))

    # Alles außer a-z und 0-9 entfernen
    s = re.sub(r"[^a-z0-9]+", "", s)

    return s