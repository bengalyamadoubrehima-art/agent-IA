import os
import tempfile
from pathlib import Path

import sounddevice as sd
import soundfile as sf
from dotenv import load_dotenv
from openai import OpenAI

from core.state import JarvisState


class VoiceInterface:
    """
    Interface vocale de JARVIS.

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

        load_dotenv(
            self.base_dir / ".env"
        )

        api_key = os.getenv(
            "OPENAI_API_KEY"
        )

        self.client = (
            OpenAI(api_key=api_key)
            if api_key
            else None
        )

        self.transcription_model = (
            "gpt-4o-mini-transcribe"
        )

        self.tts_model = (
            "gpt-4o-mini-tts"
        )

        self.tts_voice = "coral"

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
    # CLIENT OPENAI
    # =========================================================

    def _check_client(self):

        if self.client is None:

            raise RuntimeError(
                "La clé API OpenAI est absente "
                "du fichier .env."
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

        self._check_client()

        print(
            "🧠 Transcription..."
        )

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

        self._check_client()

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

        output_path = (
            self.base_dir
            / "audio"
            / "jarvis_response.wav"
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

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