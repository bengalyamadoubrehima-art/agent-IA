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
    SetLogLevel(-1)
    models = {"fr": Model(sys.argv[1]), "en": Model(sys.argv[2])}

    grammars = {
        "fr": [
            None,
            '["jarvis", "[unk]"]',
            '["jarre vis", "[unk]"]',
            '["jarvis", "jarre vis", "jar vis", "jarre visse", "[unk]"]',
        ],
        "en": [None, '["jarvis", "[unk]"]'],
    }

    phrases = [
        ("Jarvis", "fr"), ("Jarvis", "fr+m3"), ("Jarvis", "fr+f2"), ("Jarvis", "en-us"),
        ("Jarvis, ouvre YouTube", "fr"),
        ("Ouvre YouTube", "fr"), ("J'arrive dans cinq minutes", "fr"),
        ("Le service est fini", "fr"), ("Gervais", "fr"), ("Bonjour, comment ça va", "fr"),
    ]

    for text, voice in phrases:
        synthesize(text, voice)
        for lang, model in models.items():
            for grammar in grammars[lang]:
                result = recognize(model, grammar)
                print(f"::notice::[{lang}] {voice} « {text} » | grammaire={grammar or 'libre'} -> « {result} »")


if __name__ == "__main__":
    main()
