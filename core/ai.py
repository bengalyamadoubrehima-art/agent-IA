import json


class AIEngine:

    def __init__(
        self,
        memory,
        tools,
        brain,
        confirmation_handler=None
    ):

        self.memory = memory
        self.tools = tools
        self.brain = brain
        self.confirmation_handler = confirmation_handler

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

Appareils :
- Sans précision, « ouvre X » concerne le PC. Si l'utilisateur
  parle de son téléphone, utilise les outils *_telephone.
- « Ouvre YouTube » sur le PC : ouvrir_site (youtube.com) ;
  sur le téléphone : ouvrir_application_telephone.
- Messages : WhatsApp par défaut, SMS seulement si demandé.
  Passe le nom du contact tel quel, le téléphone le retrouve
  dans le répertoire. Écris exactement le message demandé.
- E-mails : pour lire un e-mail, liste d'abord (lire_emails ou
  rechercher_emails) puis ouvre-le avec son id. Résume les
  e-mails au lieu de tout recopier.
"""

    def _messages(self, message):

        messages = [
            {
                "role": "system",
                "content": self.system_prompt
            }
        ]

        messages.extend(
            self.memory.recent_messages(20)
        )

        messages.append({
            "role": "user",
            "content": message
        })

        return messages

    @staticmethod
    def _clean_schema(schema):
        """
        Gemini n'accepte qu'une partie de JSON Schema :
        on retire additionalProperties et les listes vides.
        """

        if isinstance(schema, dict):
            return {
                key: AIEngine._clean_schema(value)
                for key, value in schema.items()
                if key != "additionalProperties"
                and not (key == "required" and not value)
            }

        if isinstance(schema, list):
            return [AIEngine._clean_schema(item) for item in schema]

        return schema

    def _tool_definitions(self):

        return [
            {
                "type": "function",
                "function": {
                    "name": definition["name"],
                    "description": definition["description"],
                    "parameters": self._clean_schema(
                        definition["parameters"]
                    ),
                },
            }
            for definition in self.tools.api_definitions
        ]

    def respond(self, message):

        if self.brain.client is None:
            return (
                f"La clé {self.brain.name} est absente : ajoute "
                f"{self.brain.key_name} dans le fichier .env."
            )

        messages = self._messages(message)
        tools = self._tool_definitions()

        self.memory.add_message(
            "user",
            message
        )

        try:

            answer = None

            for _ in range(8):

                reply = self.brain.chat(
                    messages,
                    tools
                )

                calls = reply.tool_calls or []

                if not calls:
                    answer = reply.content or ""
                    break

                # L'appel d'outil est renvoyé tel quel avec son résultat.
                messages.append({
                    "role": "assistant",
                    "content": reply.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in calls
                    ],
                })

                for call in calls:

                    try:
                        arguments = json.loads(
                            call.function.arguments or "{}"
                        )
                    except json.JSONDecodeError:
                        arguments = {}

                    print(
                        f"\n🔧 Jarvis → {call.function.name}"
                    )

                    result = self.tools.execute(
                        call.function.name,
                        arguments,
                        confirmation_handler=(
                            self.confirmation_handler
                        )
                    )

                    print(
                        f"   ↳ {result}"
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": str(result),
                    })

            if answer is None:
                answer = "Je n'ai pas pu terminer cette demande."

            answer = answer.strip() or "Je n'ai pas de réponse."

            self.memory.add_message(
                "assistant",
                answer
            )

            return answer

        except Exception as error:

            return self.brain.describe_error(error)
