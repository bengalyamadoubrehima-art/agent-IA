"""
Expérience : grammaire à « leurres » pour le modèle français, afin que
« j'arrive », « service »… ne déclenchent pas « jarvis ».
Une annotation ::notice:: par grammaire.
"""

import json
import subprocess
import sys
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel

SMALL = ["j'arrive", "arrive", "arriver", "service", "gervais", "avis", "servir", "jarre", "vis"]
LARGE = SMALL + [
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "le", "la", "les", "un", "une", "des",
    "et", "est", "à", "de", "du", "en", "dans", "pour", "pas", "que", "qui", "ça", "va", "fait",
    "bonjour", "salut", "merci", "oui", "non", "ouvre", "appelle", "envoie", "message", "minutes",
    "cinq", "comment", "bien", "fini", "garçon", "bravo", "chaise", "journal", "jardin", "jarvis",
]

GRAMMARS = {
    "simple": ["jarvis", "[unk]"],
    "leurres": ["jarvis"] + SMALL + ["[unk]"],
    "leurres+mots": LARGE + ["[unk]"],
}

PHRASES = [
    ("Jarvis", "fr"), ("Jarvis", "fr+m3"), ("Jarvis", "fr+f2"), ("Jarvis", "en-us"),
    ("Jarvis, ouvre YouTube", "fr"), ("Jarvis appelle maman", "fr+m3"),
    ("J'arrive dans cinq minutes", "fr"), ("Le service est fini", "fr"),
    ("Gervais arrive", "fr"), ("C'est un bon service", "fr+m3"), ("J'arrive", "fr+f2"),
    ("Ouvre YouTube", "fr"), ("Bonjour, comment ça va", "fr"),
]


def synthesize(text, voice):
    subprocess.run(["espeak-ng", "-v", voice, "-s", "140", "-w", "raw.wav", text], check=True)
    subprocess.run(["sox", "raw.wav", "-r", "16000", "-c", "1", "-b", "16", "speech.wav"], check=True)


def recognize(model, words):
    recognizer = KaldiRecognizer(model, 16000, json.dumps(words, ensure_ascii=False))
    recognizer.SetWords(True)
    found = []
    with wave.open("speech.wav") as audio:
        while True:
            data = audio.readframes(4000)
            if not data:
                break
            if recognizer.AcceptWaveform(data):
                found += json.loads(recognizer.Result()).get("result", [])
    found += json.loads(recognizer.FinalResult()).get("result", [])
    return " ".join(f"{w['word']}({w['conf']:.2f})" if w["word"] == "jarvis" else w["word"] for w in found)


def main():
    SetLogLevel(0)
    model = Model(sys.argv[1])

    for text, voice in PHRASES:
        synthesize(text, voice)
        results = [f"{name}: {recognize(model, words)}" for name, words in GRAMMARS.items()]
        print(f"::notice::{voice} « {text} » => " + " || ".join(results))


if __name__ == "__main__":
    main()
