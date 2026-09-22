from core.state import (
    JarvisState,
    StateManager,
)
from core.planner import Planner


class Orchestrator:

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

        self.planner = Planner(
            ai=self.ai
        )

    def handle(self, message):

        message = message.strip()

        if not message:
            return ""

        self.state.set_state(
            JarvisState.THINKING
        )

        try:

            plan = self.planner.create_plan(
                message
            )

            if not plan:
                response = self.ai.respond(
                    message
                )

                self.state.set_state(
                    JarvisState.IDLE
                )

                return response

            results = []

            print()
            print("🧠 Plan JARVIS :")

            for index, step in enumerate(
                plan,
                start=1
            ):

                description = step.get(
                    "description",
                    ""
                ).strip()

                if not description:
                    continue

                print(
                    f"   {index}. {description}"
                )

                self.state.set_state(
                    JarvisState.EXECUTING
                )

                result = self.ai.respond(
                    description
                )

                results.append(result)

            self.state.set_state(
                JarvisState.IDLE
            )

            if len(results) == 1:
                return results[0]

            return "\n".join(results)

        except Exception:

            self.state.set_state(
                JarvisState.ERROR
            )

            raise