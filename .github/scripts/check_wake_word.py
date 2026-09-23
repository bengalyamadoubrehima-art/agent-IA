"""
Vérifie que le modèle Vosk embarqué dans l'application reconnaît
le mot « Jarvis », avec la même grammaire que WakeWordService.

Le mot est prononcé par une voix de synthèse (espeak-ng), en
anglais puis en français. L'échec en anglais bloque la compilation ;
les autres cas sont affichés pour information.
"""

import json
import subprocess
import sys
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel

GRAMMAR = '["jarvis", "[unk]"]'


def synthesize(text, voice):
    subprocess.run(["espeak-ng", "-v", voice, "-s", "140", "-w", "raw.wav", text], check=True)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", "raw.wav",
         "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", "speech.wav"],
        check=True,
    )


def recognize(model, text, voice):
    synthesize(text, voice)
    recognizer = KaldiRecognizer(model, 16000, GRAMMAR)
    heard = []

    with wave.open("speech.wav") as audio:
        while True:
            data = audio.readframes(4000)
            if not data:
                break
            if recognizer.AcceptWaveform(data):
                heard.append(json.loads(recognizer.Result())["text"])

    heard.append(json.loads(recognizer.FinalResult())["text"])
    return " ".join(part for part in heard if part)


def detected(text):
    return "jarvis" in text.split()


def main():
    SetLogLevel(0)
    model = Model(sys.argv[1])

    required = recognize(model, "Jarvis", "en-us")
    print(f"[anglais] « Jarvis » -> « {required} »")

    checks = [
        ("Jarvis", "fr", True),
        ("Jarvis, ouvre YouTube", "fr", True),
        ("Ouvre YouTube", "fr", False),
        ("Bonjour, comment ça va", "fr", False),
        ("J'arrive dans cinq minutes", "fr", False),
    ]

    for text, voice, expected in checks:
        result = recognize(model, text, voice)
        status = "ok" if detected(result) == expected else "À SURVEILLER"
        print(f"[{voice}] « {text} » -> « {result} » ({status})")
        if status != "ok":
            print(f"::warning::Mot d'activation : « {text} » ({voice}) -> « {result} »")

    if not detected(required):
        print("::error::Le modèle ne reconnaît pas « Jarvis ».")
        sys.exit(1)


if __name__ == "__main__":
    main()
