"""
Vérifie que le modèle Vosk embarqué dans l'application reconnaît
le mot « Jarvis », avec la même grammaire que WakeWordService.

Le mot est prononcé par une voix de synthèse (espeak-ng, converti en
16 kHz avec sox), en
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
        ["sox", "raw.wav", "-r", "16000", "-c", "1", "-b", "16", "speech.wav"],
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

    # Exploration : ce que le modèle entend sans grammaire (pour trouver
    # les variantes de « Jarvis » prononcé à la française).
    free = KaldiRecognizer(model, 16000)
    for text, voice in [("Jarvis", "fr"), ("Jarvice", "fr"), ("Djarvisse", "fr"), ("Jarvis", "en-us")]:
        synthesize(text, voice)
        free = KaldiRecognizer(model, 16000)
        with wave.open("speech.wav") as audio:
            while True:
                data = audio.readframes(4000)
                if not data:
                    break
                free.AcceptWaveform(data)
        print(f"[libre {voice}] « {text} » -> « {json.loads(free.FinalResult())['text']} »")

    if not detected(required):
        print("::error::Le modèle ne reconnaît pas « Jarvis ».")
        sys.exit(1)


if __name__ == "__main__":
    main()
