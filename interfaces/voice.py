import asyncio
import os
import tempfile
from pathlib import Path

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
        recording_seconds=6,
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

        frames = int(
            self.recording_seconds
            * self.sample_rate
        )

        audio = sd.rec(
            frames,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
        )

        sd.wait()

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

        self._set_state(
            JarvisState.SPEAKING
        )

        self._emit(
            "voice.speaking_started",
            {
                "text": text
            }
        )

        print(
            "🔊 JARVIS parle..."
        )

        audio_dir = self.base_dir / "audio"

        audio_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        if self.client is not None:

            output_path = audio_dir / "jarvis_response.wav"

            with (
                self.client
                .audio
                .speech
                .with_streaming_response
                .create(
                    model=self.tts_model,
                    voice=self.tts_voice,
                    input=text,
                    response_format="wav",
                )
                as response
            ):

                response.stream_to_file(
                    output_path
                )

        else:

            output_path = audio_dir / "jarvis_response.mp3"

            self._synthesize_free(
                text,
                output_path
            )

        self.play_audio(
            output_path
        )

        self._emit(
            "voice.speaking_finished",
            {
                "text": text
            }
        )

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

    def _synthesize_free(self, text, output_path):
        """Voix française naturelle de Microsoft Edge (edge-tts)."""

        try:
            import edge_tts
        except ImportError as error:
            raise RuntimeError(
                "module manquant, lance : pip install -r requirements.txt"
            ) from error

        asyncio.run(
            edge_tts.Communicate(
                text,
                self.edge_voice
            ).save(str(output_path))
        )

    # =========================================================
    # LECTURE AUDIO
    # =========================================================

    def play_audio(
        self,
        audio_path
    ):

        audio, sample_rate = (
            sf.read(
                audio_path,
                dtype="float32",
            )
        )

        sd.play(
            audio,
            sample_rate,
        )

        sd.wait()

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

            response = (
                self.orchestrator.handle(
                    text
                )
            )

            print()
            print(
                f"🤖 JARVIS : {response}"
            )

            self.speak(
                response
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