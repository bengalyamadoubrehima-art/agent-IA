"""
Vérifie le mot d'activation « Jarvis » avant de publier l'application,
avec le même modèle, la même grammaire (assets/wake_grammar.json) et le
même seuil de confiance que WakeWordService.

Les phrases sont prononcées par une voix de synthèse (espeak-ng,
convertie en 16 kHz avec sox). « Jarvis » doit être détecté dans
toutes les phrases qui le contiennent, et dans aucune autre.
"""

import json
import subprocess
import sys
import wave
from pathlib import Path

from vosk import KaldiRecognizer, Model, SetLogLevel

MIN_CONFIDENCE = 0.5

# (phrase, voix, doit déclencher)
PHRASES = [
    ("Jarvis", "fr", True),
    ("Jarvis", "fr+m3", True),
    ("Jarvis", "fr+f2", True),
    ("Jarvis", "en-us", True),
    ("Jarvis, ouvre YouTube", "fr", True),
    ("Jarvis appelle maman", "fr+m3", True),
    ("J'arrive dans cinq minutes", "fr", False),
    ("J'arrive", "fr+f2", False),
    ("Le service est fini", "fr", False),
    ("C'est un bon service", "fr+m3", False),
    ("Gervais arrive", "fr", False),
    ("Ouvre YouTube", "fr", False),
    ("Bonjour, comment ça va", "fr", False),
]


def synthesize(text, voice):
    subprocess.run(["espeak-ng", "-v", voice, "-s", "140", "-w", "raw.wav", text], check=True)
    subprocess.run(["sox", "raw.wav", "-r", "16000", "-c", "1", "-b", "16", "speech.wav"], check=True)


def wake_word_heard(model, grammar):
    recognizer = KaldiRecognizer(model, 16000, grammar)
    recognizer.SetWords(True)
    words = []

    with wave.open("speech.wav") as audio:
        while True:
            data = audio.readframes(4000)
            if not data:
                break
            if recognizer.AcceptWaveform(data):
                words += json.loads(recognizer.Result()).get("result", [])

    words += json.loads(recognizer.FinalResult()).get("result", [])

    heard = any(w["word"] == "jarvis" and w["conf"] >= MIN_CONFIDENCE for w in words)
    return heard, " ".join(w["word"] for w in words)


def main():
    SetLogLevel(0)
    assets = Path(sys.argv[1])
    model = Model(str(assets / "model-fr"))
    grammar = (assets / "wake_grammar.json").read_text(encoding="utf-8")

    failures = 0

    for text, voice, expected in PHRASES:
        synthesize(text, voice)
        heard, words = wake_word_heard(model, grammar)
        ok = heard == expected
        failures += not ok
        print(f"[{'ok' if ok else 'ÉCHEC'}] {voice} « {text} » -> « {words} »")
        if not ok:
            attendu = "détecté" if expected else "ignoré"
            print(f"::error::Mot d'activation : « {text} » ({voice}) devait être {attendu}, entendu « {words} »")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
