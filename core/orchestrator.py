from core.state import (
    JarvisState,
    StateManager,
)


class Orchestrator:
    """
    Reçoit les demandes (texte, voix, téléphone) et les confie au
    cerveau IA, qui enchaîne lui-même les outils nécessaires.

    Une seule requête au cerveau par demande (plus d'étape de
    planification séparée) : c'est plus rapide et ça économise le
    quota gratuit de Gemini.
    """

    def __init__(
        self,
        ai,
        state_manager=None
    ):

        self.ai = ai

        self.state = (
            state_manager
            or StateManager()
        )

    def handle(self, message):

        message = message.strip()

        if not message:
            return ""

        self.state.set_state(
            JarvisState.THINKING
        )

        try:

            response = self.ai.respond(
                message
            )

            self.state.set_state(
                JarvisState.IDLE
            )

            return response

        except Exception:

            self.state.set_state(
                JarvisState.ERROR
            )

            raise
