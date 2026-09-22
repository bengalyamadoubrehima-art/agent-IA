from pathlib import Path

from dotenv import load_dotenv

from core.activity import ActivityLogger
from core.ai import AIEngine
from core.confirmation import ConfirmationService
from core.events import EventBus
from core.memory import Memory
from core.orchestrator import Orchestrator
from core.permissions import PermissionManager
from core.state import StateManager

from interfaces.desktop import run_desktop
from interfaces.voice import VoiceInterface

from services.communication import CommunicationAgent

from tools.registry import ToolRegistry

from mobile.server import MobileBridge


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

MODEL = "gpt-5.6-luna"


def create_jarvis():

    # =====================================================
    # MÉMOIRE
    # =====================================================

    memory = Memory(
        BASE_DIR / "data" / "memory.json"
    )

    # =====================================================
    # JOURNAL D'ACTIVITÉ
    # =====================================================

    activity = ActivityLogger(
        BASE_DIR / "data" / "activity.json"
    )

    # =====================================================
    # ÉVÉNEMENTS
    # =====================================================

    event_bus = EventBus()

    # =====================================================
    # ÉTAT DE JARVIS
    # =====================================================

    state_manager = StateManager(
        event_bus=event_bus
    )

    # =====================================================
    # JOURNALISATION DES ÉTATS
    # =====================================================

    event_bus.subscribe(
        "state.changed",
        lambda event: activity.log(
            event="state.changed",
            message="État de JARVIS modifié.",
            data=event.data,
        )
    )

    # =====================================================
    # JOURNALISATION DES OUTILS
    # =====================================================

    for event_name in [
        "tool.started",
        "tool.finished",
        "tool.failed",
        "tool.blocked",
        "tool.denied",
        "tool.confirmation_required",
        "voice.started",
        "voice.recorded",
        "voice.transcribed",
        "voice.speaking_started",
        "voice.speaking_finished",
        "voice.error",
    ]:

        event_bus.subscribe(
            event_name,
            lambda event, name=event_name: activity.log(
                event=name,
                message=f"Événement : {name}",
                data=event.data,
            )
        )

    # =====================================================
    # PERMISSIONS
    # =====================================================

    permissions = PermissionManager()

    # =====================================================
    # COMMUNICATION
    # =====================================================

    communication = CommunicationAgent()

    # =====================================================
    # OUTILS
    # =====================================================

    tools = ToolRegistry(
        permissions=permissions,
        memory=memory,
        communication=communication,
        event_bus=event_bus,
    )

    tools.setup()

    # =====================================================
    # CONFIRMATION
    # =====================================================

    confirmation = ConfirmationService()

    # =====================================================
    # CERVEAU IA
    # =====================================================

    ai = AIEngine(
        memory=memory,
        tools=tools,
        model=MODEL,
        confirmation_handler=confirmation.ask,
    )

    # =====================================================
    # ORCHESTRATEUR
    # =====================================================

    orchestrator = Orchestrator(
        ai=ai,
        state_manager=state_manager,
    )

    # =====================================================
    # VOIX
    # =====================================================

    voice = VoiceInterface(
        orchestrator=orchestrator,
        base_dir=BASE_DIR,
        state_manager=state_manager,
        event_bus=event_bus,
    )

    mobile = MobileBridge(
        orchestrator=orchestrator,
        state_manager=state_manager,
        event_bus=event_bus,
    )

    mobile.start()

    return orchestrator, voice


def main():

    orchestrator, voice = create_jarvis()

    print()
    print("╔══════════════════════════════════════╗")
    print("║              JARVIS                  ║")
    print("╠══════════════════════════════════════╣")
    print(f"║ Modèle : {MODEL:<26}║")
    print("║ Mémoire : active                     ║")
    print("║ Événements : actifs                  ║")
    print("║ Journal : actif                       ║")
    print("║ Permissions : actives                 ║")
    print("║ Outils PC : actifs                    ║")
    print("║ Communication : prête                 ║")
    print("║ Voix : active                         ║")
    print("╚══════════════════════════════════════╝")
    print()

    print("🚀 Lancement de JARVIS...")

    return run_desktop(
        orchestrator=orchestrator,
        voice=voice,
    )


if __name__ == "__main__":
    main()