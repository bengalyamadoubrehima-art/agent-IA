import asyncio
import io
import os
import queue
import re
import tempfile
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from core.state import JarvisState


class VoiceInterface:
    """
    Interface vocale de JARVIS.

    Avec OpenAI : transcription et voix d'OpenAI (payantes).
    Avec Gemini : voix gratuites, reconnaissance vocale de Google et
    voix naturelle de Microsoft Edge (edge-tts).

    Flux :

        microphone
            ↓
        transcription
            ↓
        orchestrateur
            ↓
        réponse IA
            ↓
        synthèse vocale
            ↓
        haut-parleur
    """

    def __init__(
        self,
        orchestrator,
        base_dir,
        brain=None,
        state_manager=None,
        event_bus=None,
        sample_rate=16000,
        channels=1,
        recording_seconds=15,
    ):

        self.orchestrator = orchestrator

        self.base_dir = Path(
            base_dir
        )

        self.state = state_manager
        self.event_bus = event_bus

        self.sample_rate = sample_rate
        self.channels = channels
        self.recording_seconds = (
            recording_seconds
        )

        # Voix OpenAI seulement si le cerveau est OpenAI ;
        # sinon voix gratuites.
        self.client = (
            brain.client
            if brain is not None and brain.provider == "openai"
            else None
        )

        self.transcription_model = (
            "gpt-4o-mini-transcribe"
        )

        self.tts_model = (
            "gpt-4o-mini-tts"
        )

        self.tts_voice = "coral"

        # Voix gratuite (edge-tts) : voix française naturelle.
        self.edge_voice = os.getenv(
            "JARVIS_VOICE",
            "fr-FR-HenriNeural"
        )

    @property
    def available(self):
        return True

    # =========================================================
    # ÉVÉNEMENTS
    # =========================================================

    def _emit(
        self,
        event_name,
        data=None
    ):

        if self.event_bus:

            self.event_bus.emit(
                event_name,
                data or {}
            )

    def _set_state(
        self,
        state
    ):

        if self.state:

            self.state.set_state(
                state
            )

    # =========================================================
    # ENREGISTREMENT
    # =========================================================

    def record(self):
        """
        Enregistre jusqu'à ce que l'utilisateur se taise (et non plus
        pendant une durée fixe) : dès qu'il a fini de parler, JARVIS
        passe à la suite.
        """

        self._set_state(
            JarvisState.LISTENING
        )

        self._emit(
            "voice.started",
            {
                "duration": self.recording_seconds
            }
        )

        print()
        print("🎙️ Écoute...")

        block = int(self.sample_rate * BLOCK_SECONDS)

        blocks = []
        levels = []
        speaking = False
        loud = 0
        quiet = 0
        threshold = MIN_THRESHOLD

        max_blocks = int(self.recording_seconds / BLOCK_SECONDS)
        wait_blocks = int(WAIT_FOR_SPEECH_SECONDS / BLOCK_SECONDS)
        end_blocks = int(END_OF_SPEECH_SECONDS / BLOCK_SECONDS)
        calibration = int(CALIBRATION_SECONDS / BLOCK_SECONDS)

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=block,
        ) as stream:

            while len(blocks) < max_blocks:

                data, _ = stream.read(block)
                blocks.append(data.copy())

                level = float(np.sqrt(np.mean(np.square(data))))
                levels.append(level)

                # Bruit ambiant mesuré au début (le minimum, au cas où
                # l'utilisateur parlerait déjà).
                if len(levels) == calibration:
                    threshold = max(MIN_THRESHOLD, min(levels) * 3)

                if not speaking:

                    loud = loud + 1 if level > threshold else 0

                    if loud >= 3:
                        speaking = True

                    elif len(blocks) >= wait_blocks:
                        break

                else:

                    quiet = quiet + 1 if level < threshold else 0

                    if quiet >= end_blocks:
                        break

        audio = np.concatenate(blocks)

        temp_file = (
            tempfile.NamedTemporaryFile(
                suffix=".wav",
                delete=False,
            )
        )

        temp_file.close()

        sf.write(
            temp_file.name,
            audio,
            self.sample_rate,
        )

        audio_path = Path(
            temp_file.name
        )

        print(
            "🎧 Enregistrement terminé."
        )

        self._emit(
            "voice.recorded",
            {
                "file": str(audio_path)
            }
        )

        return audio_path

    # =========================================================
    # TRANSCRIPTION
    # =========================================================

    def transcribe(
        self,
        audio_path
    ):

        print(
            "🧠 Transcription..."
        )

        if self.client is not None:

            with open(
                audio_path,
                "rb"
            ) as audio_file:

                result = (
                    self.client
                    .audio
                    .transcriptions
                    .create(
                        model=self.transcription_model,
                        file=audio_file,
                    )
                )

            text = result.text.strip()

        else:

            text = self._transcribe_free(
                audio_path
            )

        print(
            f"🗣️ Tu as dit : {text}"
        )

        self._emit(
            "voice.transcribed",
            {
                "text": text
            }
        )

        return text

    # =========================================================
    # SYNTHÈSE VOCALE
    # =========================================================

    def speak(
        self,
        text
    ):

        if not text:
            return

        self._emit(
            "voice.speaking_started",
            {
                "text": text
            }
        )

        speaker = SentenceSpeaker(self)
        speaker.feed(text)
        speaker.finish()

        self._emit(
            "voice.speaking_finished",
            {
                "text": text
            }
        )

    def synthesize(self, text, loop):
        """Transforme une phrase en son (tableau audio, fréquence)."""

        if self.client is not None:

            response = (
                self.client
                .audio
                .speech
                .create(
                    model=self.tts_model,
                    voice=self.tts_voice,
                    input=text,
                    response_format="wav",
                )
            )

            data = response.content

        else:

            data = loop.run_until_complete(
                self._synthesize_free(text)
            )

        return self._decode(data)

    # =========================================================
    # VOIX GRATUITES
    # =========================================================

    @staticmethod
    def _transcribe_free(audio_path):
        """Reconnaissance vocale gratuite de Google (français)."""

        try:
            import speech_recognition as sr
        except ImportError as error:
            raise RuntimeError(
                "module manquant, lance : pip install -r requirements.txt"
            ) from error

        recognizer = sr.Recognizer()

        with sr.AudioFile(str(audio_path)) as source:
            audio = recognizer.record(source)

        try:
            return recognizer.recognize_google(
                audio,
                language="fr-FR"
            ).strip()

        except sr.UnknownValueError:
            return ""

        except sr.RequestError as error:
            raise RuntimeError(
                f"Reconnaissance vocale indisponible : {error}"
            ) from error

    async def _synthesize_free(self, text):
        """Voix française naturelle de Microsoft Edge (edge-tts)."""

        try:
            import edge_tts
        except ImportError as error:
            raise RuntimeError(
                "module manquant, lance : pip install -r requirements.txt"
            ) from error

        audio = bytearray()

        async for chunk in edge_tts.Communicate(
            text,
            self.edge_voice
        ).stream():

            if chunk["type"] == "audio":
                audio.extend(chunk["data"])

        return bytes(audio)

    @staticmethod
    def _decode(data):

        try:
            return sf.read(
                io.BytesIO(data),
                dtype="float32",
            )

        except Exception:

            # Certaines versions de libsndfile ne lisent le MP3 que
            # depuis un fichier.
            temp_file = tempfile.NamedTemporaryFile(
                suffix=".mp3",
                delete=False,
            )

            try:
                temp_file.write(data)
                temp_file.close()

                return sf.read(
                    temp_file.name,
                    dtype="float32",
                )

            finally:
                Path(temp_file.name).unlink(missing_ok=True)

    # =========================================================
    # CYCLE VOCAL COMPLET
    # =========================================================

    def process_once(self):

        audio_path = None

        try:

            audio_path = self.record()

            text = self.transcribe(
                audio_path
            )

            if not text:

                print(
                    "⚠️ Aucun texte détecté."
                )

                return

            self._set_state(
                JarvisState.THINKING
            )

            print(
                "🧠 JARVIS réfléchit..."
            )

            # La réponse arrive au fil de l'eau : chaque phrase est
            # affichée et dite dès qu'elle est complète.
            speaker = SentenceSpeaker(self)
            streamed = []

            def on_text(chunk):
                streamed.append(chunk)
                speaker.feed(chunk)

                self._emit(
                    "voice.reply_delta",
                    {
                        "text": chunk
                    }
                )

            try:

                response = (
                    self.orchestrator.handle(
                        text,
                        on_text=on_text
                    )
                )

                print()
                print(
                    f"🤖 JARVIS : {response}"
                )

                self._emit(
                    "voice.reply",
                    {
                        "text": response
                    }
                )

                # Réponse non diffusée au fil de l'eau (erreur, clé absente…).
                already = "".join(streamed).strip()

                if response and response.strip() != already:
                    speaker.feed(
                        " " + response if already else response
                    )

                if speaker.pending:
                    self._set_state(
                        JarvisState.SPEAKING
                    )

            finally:

                speaker.finish()

            self._emit(
                "voice.speaking_finished",
                {
                    "text": response
                }
            )

        except Exception as error:

            self._set_state(
                JarvisState.ERROR
            )

            self._emit(
                "voice.error",
                {
                    "error": str(error)
                }
            )

            print()
            print(
                f"❌ Erreur vocale : {error}"
            )

        finally:

            if audio_path is not None:

                try:

                    audio_path.unlink(
                        missing_ok=True
                    )

                except Exception:
                    pass

            if self.state:

                self.state.reset()

    # =========================================================
    # MODE VOCAL CONTINU
    # =========================================================

    def run(self):

        print()
        print(
            "╔══════════════════════════════════════╗"
        )
        print(
            "║          JARVIS VOICE               ║"
        )
        print(
            "╠══════════════════════════════════════╣"
        )
        print(
            "║ Microphone : actif                   ║"
        )
        print(
            "║ Transcription : active               ║"
        )
        print(
            "║ Synthèse vocale : active             ║"
        )
        print(
            "╚══════════════════════════════════════╝"
        )
        print()

        print(
            "Appuie sur Entrée pour parler."
        )

        print(
            "Tape 'q' puis Entrée pour quitter."
        )

        print()

        while True:

            try:

                command = input(
                    "🎙️ > "
                ).strip().lower()

            except (
                KeyboardInterrupt,
                EOFError
            ):

                print()
                print(
                    "🛑 Mode vocal arrêté."
                )

                break

            if command == "q":

                print(
                    "🛑 Mode vocal arrêté."
                )

                break

            self.process_once()

            print()

# =============================================================
# DÉTECTION DE LA PAROLE
# =============================================================

BLOCK_SECONDS = 0.03
CALIBRATION_SECONDS = 0.3
WAIT_FOR_SPEECH_SECONDS = 7
END_OF_SPEECH_SECONDS = 0.9
MIN_THRESHOLD = 0.01


# =============================================================
# PAROLE PHRASE PAR PHRASE
# =============================================================

SENTENCE_END = re.compile(r"[.!?…]+[»\")]*\s+|\n+")


class SentenceSplitter:
    """Découpe un texte qui arrive par morceaux en phrases complètes."""

    def __init__(self, max_length=160):
        self.buffer = ""
        self.max_length = max_length

    def feed(self, text):
        self.buffer += text
        sentences = []

        while True:
            found = SENTENCE_END.search(self.buffer)

            if not found:
                break

            sentence = self.buffer[:found.end()].strip()
            self.buffer = self.buffer[found.end():]

            if sentence:
                sentences.append(sentence)

        # Phrase très longue : on coupe à la dernière virgule pour ne
        # pas attendre.
        if len(self.buffer) > self.max_length:
            cut = self.buffer.rfind(", ", 0, self.max_length)

            if cut > 20:
                sentences.append(self.buffer[:cut + 1].strip())
                self.buffer = self.buffer[cut + 2:]

        return sentences

    def flush(self):
        rest = self.buffer.strip()
        self.buffer = ""
        return rest


def speakable(text):
    """Texte adapté à la lecture à voix haute."""

    text = re.sub(r"https?://\S+", "le lien", text)
    text = re.sub(r"[*#_`>|]", "", text)

    return re.sub(r"\s+", " ", text).strip()


class SentenceSpeaker:
    """
    Dit les phrases au fur et à mesure : pendant qu'une phrase est
    lue, la suivante est déjà en préparation.
    """

    def __init__(self, voice):
        self.voice = voice
        self.splitter = SentenceSplitter()
        self.texts = queue.Queue()
        self.sounds = queue.Queue()
        self.pending = False
        self.finished = False

        self.maker = threading.Thread(target=self._make, daemon=True)
        self.player = threading.Thread(target=self._play, daemon=True)

        self.maker.start()
        self.player.start()

    def feed(self, text):
        for sentence in self.splitter.feed(text):
            self._say(sentence)

    def _say(self, sentence):
        sentence = speakable(sentence)

        if sentence:
            self.pending = True
            self.texts.put(sentence)

    def finish(self):
        """Dit la fin du texte et attend la fin de la lecture."""

        if self.finished:
            return

        self.finished = True

        self._say(self.splitter.flush())
        self.texts.put(None)
        self.player.join()

    def _make(self):
        loop = asyncio.new_event_loop()

        try:
            while (sentence := self.texts.get()) is not None:
                try:
                    self.sounds.put(self.voice.synthesize(sentence, loop))

                except Exception as error:
                    self.voice._emit("voice.error", {"error": str(error)})
                    print(f"❌ Erreur vocale : {error}")

        finally:
            loop.close()
            self.sounds.put(None)

    def _play(self):
        first = True

        while (sound := self.sounds.get()) is not None:
            audio, sample_rate = sound

            if first:
                first = False
                self.voice._set_state(JarvisState.SPEAKING)
                print("🔊 JARVIS parle...")

            sd.play(audio, sample_rate)
            sd.wait()
