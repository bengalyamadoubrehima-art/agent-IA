import json
import os
import re
import urllib.request

from openai import (
    APIStatusError,
    AuthenticationError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
GEMINI_FALLBACK = "gemini-2.5-flash"

EXCLUDED = ["lite", "image", "tts", "audio", "live", "thinking", "exp", "embedding", "vision", "8b"]


def choose_gemini_model(names):
    """
    Choisit le meilleur modèle Gemini « Flash » : stable d'abord,
    puis la version la plus récente (même logique que l'application).
    """

    usable = [
        name for name in names
        if name.startswith("gemini-")
        and "flash" in name
        and not any(word in name for word in EXCLUDED)
    ]

    stable = [name for name in usable if "preview" not in name and "latest" not in name]

    def version(name):
        found = re.match(r"gemini-(\d+(?:\.\d+)?)", name)
        return float(found.group(1)) if found else 0.0

    candidates = stable or usable

    if not candidates:
        return None

    return sorted(candidates, key=lambda name: (-version(name), len(name)))[0]


class Brain:
    """
    Cerveau de JARVIS au format « Chat Completions » :

        gemini  Google Gemini, gratuit et sans carte bancaire (par défaut)
        openai  OpenAI, payant

    Configuration (.env) :
        AI_PROVIDER     gemini ou openai (facultatif)
        GEMINI_API_KEY  clé gratuite : aistudio.google.com → « Get API key »
        OPENAI_API_KEY  clé OpenAI
        AI_MODEL        modèle imposé (facultatif, sinon choisi automatiquement)
    """

    def __init__(self, provider, api_key, model=None, openai_model=None):
        self.provider = provider
        self.api_key = api_key
        self.openai_model = openai_model
        self._model = model or None

        self.client = None

        if api_key:
            self.client = OpenAI(
                api_key=api_key,
                base_url=GEMINI_URL if provider == "gemini" else None,
            )

    @classmethod
    def from_env(cls, openai_model):
        provider = os.getenv("AI_PROVIDER", "").strip().lower()

        if provider not in {"gemini", "openai"}:
            # Sans choix explicite : Gemini dès qu'une clé Gemini est présente.
            if os.getenv("GEMINI_API_KEY") or not os.getenv("OPENAI_API_KEY"):
                provider = "gemini"
            else:
                provider = "openai"

        key_name = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"

        return cls(
            provider=provider,
            api_key=os.getenv(key_name, "").strip(),
            model=os.getenv("AI_MODEL", "").strip(),
            openai_model=openai_model,
        )

    @property
    def name(self):
        return "Gemini" if self.provider == "gemini" else "OpenAI"

    @property
    def key_name(self):
        return "GEMINI_API_KEY" if self.provider == "gemini" else "OPENAI_API_KEY"

    # =========================================================
    # MODÈLE
    # =========================================================

    @property
    def model(self):
        if self._model:
            return self._model

        if self.provider == "openai":
            self._model = self.openai_model
        else:
            try:
                self._model = self._pick_gemini_model() or GEMINI_FALLBACK
            except Exception:
                self._model = GEMINI_FALLBACK

        return self._model

    def _pick_gemini_model(self):
        request = urllib.request.Request(
            GEMINI_MODELS_URL,
            headers={"x-goog-api-key": self.api_key},
        )

        with urllib.request.urlopen(request, timeout=15) as response:
            models = json.loads(response.read().decode("utf-8")).get("models", [])

        names = [
            model.get("name", "").removeprefix("models/")
            for model in models
            if "generateContent" in model.get("supportedGenerationMethods", [])
        ]

        return choose_gemini_model(names)

    # =========================================================
    # CONVERSATION
    # =========================================================

    def chat(self, messages, tools=None):
        """Envoie la conversation et renvoie le message de réponse."""

        arguments = {"model": self.model, "messages": messages}

        if tools:
            arguments["tools"] = tools

        response = self.client.chat.completions.create(**arguments)

        return response.choices[0].message

    def describe_error(self, error):
        if isinstance(error, RateLimitError):
            return f"{self.name} : limite de demandes atteinte pour le moment, réessaie dans une minute."

        if isinstance(error, (AuthenticationError, PermissionDeniedError)):
            return f"{self.name} refuse la demande : vérifie {self.key_name} dans le fichier .env."

        if isinstance(error, NotFoundError):
            return f"{self.name} ne trouve pas le modèle « {self.model} » : retire AI_MODEL du fichier .env."

        if isinstance(error, APIStatusError) and error.status_code == 400:
            return f"{self.name} refuse la demande ({error.message}). Vérifie {self.key_name} dans le fichier .env."

        return f"Erreur du cerveau IA ({self.name}) : {error}"
