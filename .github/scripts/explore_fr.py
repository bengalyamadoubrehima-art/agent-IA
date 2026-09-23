"""
Expérience : quel modèle / quelle grammaire reconnaît « Jarvis »
prononcé à la française ? Résultats affichés en annotations ::notice::.
"""

import json
import subprocess
import sys
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel


def synthesize(text, voice):
    subprocess.run(["espeak-ng", "-v", voice, "-s", "140", "-w", "raw.wav", text], check=True)
    subprocess.run(["sox", "raw.wav", "-r", "16000", "-c", "1", "-b", "16", "speech.wav"], check=True)


def recognize(model, grammar):
    recognizer = KaldiRecognizer(model, 16000, grammar) if grammar else KaldiRecognizer(model, 16000)
    heard = []
    with wave.open("speech.wav") as audio:
        while True:
            data = audio.readframes(4000)
            if not data:
                break
            if recognizer.AcceptWaveform(data):
                heard.append(json.loads(recognizer.Result())["text"])
    heard.append(json.loads(recognizer.FinalResult())["text"])
    return " ".join(h for h in heard if h)


def main():
    SetLogLevel(0)
    models = {"fr": Model(sys.argv[1]), "en": Model(sys.argv[2])}

    grammar = '["jarvis", "[unk]"]'

    phrases = [
        ("Jarvis", "fr"), ("Jarvis", "fr+m3"), ("Jarvis", "fr+f2"), ("Jarvis", "en-us"),
        ("Jarvis, ouvre YouTube", "fr"),
        ("Ouvre YouTube", "fr"), ("J'arrive dans cinq minutes", "fr"),
        ("Le service est fini", "fr"), ("Gervais arrive", "fr"), ("Bonjour, comment ça va", "fr"),
    ]

    for text, voice in phrases:
        synthesize(text, voice)
        fr = recognize(models["fr"], grammar)
        en = recognize(models["en"], grammar)
        print(f"::notice::{voice} « {text} » -> FR « {fr} » | EN « {en} »")


if __name__ == "__main__":
    main()
