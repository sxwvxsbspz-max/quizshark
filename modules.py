# --- FILE: ./modules.py ---

def get_phase_sequence():
    """
    EINZIGE Quelle für die Reihenfolge der Spielphasen.
    Darf Duplikate enthalten (z. B. leaderboard mehrfach).
    'lobby' bleibt bewusst außen vor (Special-Case in app.py).
    """
    return [
       #"intro",

        #"punktesammler",
        #"songquiz",
        #"speedround",
         #  "leaderboard",

        #"soundtracks",
        #"freeknowledge",
        #"imagememory",   
         #  "leaderboard",
           
        #"pause",
        #   "leaderboard",

        #"soundyear",
        #"imagequiz",
        #"soundmemory",      
         #  "leaderboard",

        #"customquiz",
        #"haveiever",
        #"oddoneout",
        #"wellguessed",
        #"doyouknow",
        "yourcategory",
        #"vollereinsatz",
        #   "leaderboard",

        #"jokerrules",
        #"awardjokers",
        #"finale",
        #"siegerehrung",
    ]


def get_modules():
    # Lazy imports, damit beim App-Start keine Import-Zyklen
    # oder Side-Effects aus den Logic-Files zuschlagen

    # Zentrale Modul-Registry:
    # -> Neue Module nur hier eintragen (phase_name -> Logic-Importpfad)
    # "intro" bleibt bewusst KEIN konfigurierbares Modul.
    module_defs = {
        "punktesammler": {
            "logic": "punktesammler.logic:PunktesammlerLogic",
        },
        "leaderboard": {
            "logic": "leaderboard.logic:LeaderboardLogic",
        },
        "siegerehrung": {
            "logic": "siegerehrung.logic:SiegerehrungLogic",
        },
        "awardjokers": {
            "logic": "awardjokers.logic:AwardJokersLogic",
        },
        "speedround": {
            "logic": "speedround.logic:SpeedroundLogic",
        },
        "imagememory": {
            "logic": "imagememory.logic:ImagememoryLogic",
        },
        "soundmemory": {
            "logic": "soundmemory.logic:SoundmemoryLogic",
        },
        "imagequiz": {
            "logic": "imagequiz.logic:ImagequizLogic",
        },
        "soundtracks": {
            "logic": "soundtracks.logic:SoundtracksLogic",
        },
        "soundyear": {
            "logic": "soundyear.logic:SoundyearLogic",
        },
        "vollereinsatz": {
            "logic": "vollereinsatz.logic:VollereinsatzLogic",
        },
        "customquiz": {
            "logic": "customquiz.logic:CustomquizLogic",
        },
        "haveiever": {
            "logic": "haveiever.logic:HaveieverLogic",
        },
        "jackpot": {
            "logic": "jackpot.logic:JackpotLogic",
        },
        "songquiz": {
            "logic": "songquiz.logic:SongquizLogic",
        },
        "freeknowledge": {
            "logic": "freeknowledge.logic:FreeKnowledgeLogic",
        },
        "doyouknow": {
            "logic": "doyouknow.logic:DoYouKnowLogic",
        },
        "wellguessed": {
            "logic": "wellguessed.logic:WellGuessedLogic",
        },
        "oddoneout": {
            "logic": "oddoneout.logic:OddOneOutLogic",
        },
        "pause": {
            "logic": "pause.logic:PauseLogic",
        },
        "yourcategory": {
            "logic": "yourcategory.logic:YourCategoryLogic",
        },
        "finale": {
            "logic": "finale.logic:FinaleLogic",
        },
    }

    # ---------------------------------------------
    # Lazy Loader: "pkg.mod:Class" -> Class
    # ---------------------------------------------
    from importlib import import_module

    def _import_cls(path):
        if not isinstance(path, str) or ":" not in path:
            return path  # falls doch mal direkt eine Klasse übergeben wird
        mod_path, cls_name = path.split(":", 1)
        mod = import_module(mod_path)
        return getattr(mod, cls_name)

    # Rückgabeformat bleibt identisch zu vorher (logic: Class)
    return {
        name: {
            **cfg,
            "logic": _import_cls(cfg.get("logic")),
        }
        for name, cfg in module_defs.items()
    }
