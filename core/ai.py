import json
import os

from openai import OpenAI


class AIEngine:

    def __init__(
        self,
        memory,
        tools,
        model,
        confirmation_handler=None
    ):

        self.memory = memory
        self.tools = tools
        self.model = model
        self.confirmation_handler = confirmation_handler

        api_key = os.getenv("OPENAI_API_KEY")

        self.client = (
            OpenAI(api_key=api_key)
            if api_key
            else None
        )

        self.system_prompt = """
Tu es JARVIS, un assistant personnel intelligent.

Tu réponds en français par défaut.

Tu peux utiliser les outils disponibles pour agir
réellement sur les appareils et services autorisés.

Règles :
- Ne prétends jamais avoir effectué une action si elle
  n'a pas réellement été exécutée.
- Utilise les outils lorsqu'une action réelle est demandée.
- Utilise la mémoire lorsque cela est pertinent.
- Ne contourne jamais le système de permissions.
- Pour une action nécessitant une confirmation,
  laisse le système de confirmation gérer la demande.
- Sois naturel, précis et concis.
"""

    def _input(self, message):

        history = self.memory.recent_messages(20)

        items = [
            {
                "role": "developer",
                "content": self.system_prompt
            }
        ]

        items.extend(history)

        items.append({
            "role": "user",
            "content": message
        })

        return items

    def respond(self, message):

        if not self.client:
            return "La clé API OpenAI est absente."

        self.memory.add_message(
            "user",
            message
        )

        try:

            response = self.client.responses.create(
                model=self.model,
                input=self._input(message),
                tools=self.tools.api_definitions
            )

            while True:

                calls = [
                    item
                    for item in response.output
                    if item.type == "function_call"
                ]

                if not calls:
                    break

                outputs = []

                for call in calls:

                    try:
                        arguments = json.loads(
                            call.arguments
                        )
                    except json.JSONDecodeError:
                        arguments = {}

                    print(
                        f"\n🔧 Jarvis → {call.name}"
                    )

                    result = self.tools.execute(
                        call.name,
                        arguments,
                        confirmation_handler=(
                            self.confirmation_handler
                        )
                    )

                    print(
                        f"   ↳ {result}"
                    )

                    outputs.append({
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": str(result)
                    })

                response = self.client.responses.create(
                    model=self.model,
                    previous_response_id=response.id,
                    input=outputs,
                    tools=self.tools.api_definitions
                )

            answer = response.output_text

            self.memory.add_message(
                "assistant",
                answer
            )

            return answer

        except Exception as error:

            return (
                f"Erreur du cerveau IA : {error}"
            )
