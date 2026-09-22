import json


class Planner:

    def __init__(self, ai):
        self.ai = ai

    def create_plan(self, request):

        prompt = f"""
Transforme la demande suivante en un plan d'actions.

Demande :
{request}

Retourne UNIQUEMENT un JSON valide sous cette forme :

{{
    "steps": [
        {{
            "description": "description de l'action"
        }}
    ]
}}

Règles :
- Chaque étape doit être concrète.
- Les étapes doivent être dans l'ordre.
- Si la demande ne nécessite qu'une seule action, crée une seule étape.
- Ne crée pas d'action inutile.
"""

        try:
            response = self.ai.client.responses.create(
                model=self.ai.model,
                input=prompt,
            )

            data = json.loads(
                response.output_text
            )

            steps = data.get("steps", [])
            steps = steps[:5]

            if not isinstance(steps, list):
                return []

            return steps

        except Exception as error:

            print(
                f"⚠️ Erreur du planificateur : {error}"
            )

            return []