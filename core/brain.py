import json
import os
import re
import threading
import urllib.request

from openai import (
    APIStatusError,
    AuthenticationError,
    NotFoundError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)


# =============================================================
# FOURNISSEURS
# =============================================================

PROVIDERS = {
    "gemini": {
        "name": "Gemini",
        "key": "GEMINI_API_KEY",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
    "groq": {
        "name": "Groq",
        "key": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1/",
    },
    "openai": {
        "name": "OpenAI",
        "key": "OPENAI_API_KEY",
        "url": None,
    },
}

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
GEMINI_FALLBACK = "gemini-2.5-flash"
GEMINI_BACKUPS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

EXCLUDED = ["lite", "image", "tts", "audio", "live", "thinking", "exp", "embedding", "vision", "8b"]

# Modèles Groq, du préféré au moins bon : bons en français et avec les outils.
GROQ_PREFERRED = [
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "moonshotai/kimi-k2-instruct",
    "meta-llama/llama-4-maverick",
    "qwen/qwen3-32b",
    "openai/gpt-oss-20b",
    "meta-llama/llama-4-scout",
]
GROQ_FALLBACK = "llama-3.3-70b-versatile"
GROQ_EXCLUDED = ["guard", "whisper", "tts", "playai", "compound", "orpheus", "safeguard"]

# Erreurs passagères : serveur saturé ou quota du modèle atteint.
RETRYABLE = {429, 500, 502, 503, 504}


# =============================================================
# CHOIX DES MODÈLES
# =============================================================

def _gemini_version(name):
    found = re.match(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(found.group(1)) if found else 0.0


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
    candidates = stable or usable

    if not candidates:
        return None

    return sorted(candidates, key=lambda name: (-_gemini_version(name), len(name)))[0]


def backup_models(names):
    """Modèles Gemini de secours : Flash stables récents, puis « lite » (au plus 4)."""

    usable = [
        name for name in names
        if name.startswith("gemini-")
        and "flash" in name
        and not any(word in name for word in EXCLUDED if word != "lite")
        and "preview" not in name
        and "latest" not in name
    ]

    return sorted(
        usable,
        key=lambda name: ("lite" in name, -_gemini_version(name), len(name))
    )[:4]


def groq_models(names):
    """Modèles Groq disponibles, rangés par ordre de préférence."""

    usable = [
        name for name in names
        if not any(word in name for word in GROQ_EXCLUDED)
    ]

    ranked = []

    for prefix in GROQ_PREFERRED:
        # Version la plus récente d'abord (ex. kimi-k2-instruct-0905).
        for name in sorted(usable, reverse=True):
            if name.startswith(prefix) and name not in ranked:
                ranked.append(name)

    return ranked


def reasoning_effort(provider, model):
    """
    Beaucoup de modèles « réfléchissent » en silence avant de répondre,
    ce qui ajoute plusieurs secondes. Pour un assistant, on réduit cette
    réflexion au minimum. None = ne rien envoyer.
    """

    if provider == "gemini":
        return "none" if model.startswith("gemini-2") else "minimal"

    if provider == "groq":
        if "gpt-oss" in model:
            return "low"
        if "qwen3" in model:
            return "none"

    return None


# =============================================================
# CERVEAU
# =============================================================

class Brain:
    """
    Cerveau de JARVIS au format « Chat Completions » :

        gemini  Google Gemini, gratuit et sans carte bancaire (par défaut)
        groq    Groq, gratuit, sans carte bancaire et très rapide
        openai  OpenAI, payant

    Configuration (.env) :
        AI_PROVIDER     gemini, groq ou openai (facultatif)
        GEMINI_API_KEY  clé gratuite : aistudio.google.com → « Get API key »
        GROQ_API_KEY    clé gratuite : console.groq.com → « API Keys »
        OPENAI_API_KEY  clé OpenAI
        AI_MODEL        modèle imposé (facultatif, sinon choisi automatiquement)

    Les réponses arrivent en continu (streaming) : JARVIS peut afficher
    et dire la première phrase pendant que la suite s'écrit.
    """

    def __init__(self, provider, api_key, model=None, openai_model=None):
        self.provider = provider if provider in PROVIDERS else "gemini"
        self.api_key = api_key
        self.openai_model = openai_model
        self._model = model or None
        self._forced_model = bool(model)
        self._model_lock = threading.Lock()
        self._reasoning_supported = True

        self.backups = (
            list(GEMINI_BACKUPS) if self.provider == "gemini"
            else [GROQ_FALLBACK] if self.provider == "groq"
            else []
        )

        self.client = None

        if api_key:
            self.client = OpenAI(
                api_key=api_key,
                base_url=PROVIDERS[self.provider]["url"],
                # Les autres modèles prennent le relais en cas de saturation :
                # inutile d'attendre longtemps sur le même.
                max_retries=1,
            )

    @classmethod
    def from_env(cls, openai_model):
        provider = os.getenv("AI_PROVIDER", "").strip().lower()

        if provider not in PROVIDERS:
            # Sans choix explicite : le premier fournisseur gratuit qui a une clé.
            if os.getenv("GEMINI_API_KEY"):
                provider = "gemini"
            elif os.getenv("GROQ_API_KEY"):
                provider = "groq"
            elif os.getenv("OPENAI_API_KEY"):
                provider = "openai"
            else:
                provider = "gemini"

        return cls(
            provider=provider,
            api_key=os.getenv(PROVIDERS[provider]["key"], "").strip(),
            model=os.getenv("AI_MODEL", "").strip(),
            openai_model=openai_model,
        )

    @property
    def name(self):
        return PROVIDERS[self.provider]["name"]

    @property
    def key_name(self):
        return PROVIDERS[self.provider]["key"]

    # =========================================================
    # MODÈLE
    # =========================================================

    @property
    def model(self):
        with self._model_lock:
            if self._model:
                return self._model

            if self.provider == "openai":
                self._model = self.openai_model
            else:
                fallback = GEMINI_FALLBACK if self.provider == "gemini" else GROQ_FALLBACK

                try:
                    self._model = self._pick_model() or fallback
                except Exception:
                    self._model = fallback

            return self._model

    def _pick_model(self):
        if self.provider == "groq":
            names = [model.id for model in self.client.models.list()]
            ranked = groq_models(names)

            if ranked:
                self.backups = ranked[1:4]

            return ranked[0] if ranked else None

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

        self.backups = backup_models(names) or list(GEMINI_BACKUPS)

        return choose_gemini_model(names)

    def warm_up(self):
        """
        Choisit le modèle en arrière-plan dès le lancement, pour que la
        première question ne paie pas ce temps-là.
        """

        if self.client is None:
            return

        threading.Thread(target=lambda: self.model, daemon=True).start()

    # =========================================================
    # CONVERSATION
    # =========================================================

    def stream(self, messages, tools=None, on_text=None):
        """
        Envoie la conversation et lit la réponse au fil de l'eau.

        on_text(morceau) est appelé pour chaque morceau de texte reçu.
        Renvoie le message complet de l'assistant (dict), appels d'outils
        compris, prêt à être renvoyé tel quel au modèle.
        """

        primary = self.model
        candidates = [primary]

        # En cas de saturation, les autres modèles gratuits prennent le relais.
        if self.provider != "openai" and not self._forced_model:
            candidates += [name for name in self.backups if name != primary]

        for index, model in enumerate(candidates):
            last = index == len(candidates) - 1

            try:
                response = self._open_stream(model, messages, tools)

            except APIStatusError as error:
                if last or not self._switchable(error):
                    raise
                continue

            return self._read_stream(response, on_text)

    def _open_stream(self, model, messages, tools):
        arguments = {"model": model, "messages": messages, "stream": True}

        if tools:
            arguments["tools"] = tools

        effort = reasoning_effort(self.provider, model)

        if effort and self._reasoning_supported:
            arguments["reasoning_effort"] = effort

        try:
            return self.client.chat.completions.create(**arguments)

        except APIStatusError as error:
            # Réglage refusé par ce modèle : on réessaie sans.
            if error.status_code != 400 or "reasoning_effort" not in arguments:
                raise

            del arguments["reasoning_effort"]
            response = self.client.chat.completions.create(**arguments)
            self._reasoning_supported = False
            return response

    def _switchable(self, error):
        if error.status_code in RETRYABLE:
            return True

        # Groq : appel d'outil mal formé par le modèle, un autre peut réussir.
        return (
            self.provider == "groq"
            and error.status_code == 400
            and "tool_use_failed" in str(error)
        )

    @staticmethod
    def _read_stream(response, on_text):
        text = []
        calls = []

        for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if delta.content:
                text.append(delta.content)

                if on_text:
                    on_text(delta.content)

            for part in delta.tool_calls or []:
                data = part.model_dump(exclude_none=True)
                position = data.pop("index", None)
                function = data.pop("function", {}) or {}

                # Un nouvel appel commence : nouvel index ou nouvel identifiant.
                if position is not None:
                    current = next((c for c in calls if c["_index"] == position), None)
                else:
                    current = calls[-1] if calls else None

                if current is not None and data.get("id") and current["id"] and data["id"] != current["id"]:
                    current = None

                if current is None:
                    current = {
                        "_index": position,
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    }
                    calls.append(current)

                if function.get("name"):
                    current["function"]["name"] = function["name"]

                if function.get("arguments"):
                    current["function"]["arguments"] += function["arguments"]

                # id, type et champs propres au fournisseur (ex. la
                # « thought_signature » de Gemini dans extra_content).
                for key, value in data.items():
                    if value:
                        current[key] = value

        message = {"role": "assistant", "content": "".join(text) or None}

        if calls:
            for number, call in enumerate(calls):
                call.pop("_index", None)
                call["id"] = call["id"] or f"call_{number}"
                call["function"]["arguments"] = call["function"]["arguments"] or "{}"

            message["tool_calls"] = calls

        return message

    def describe_error(self, error):
        if isinstance(error, RateLimitError):
            return f"{self.name} : limite de demandes atteinte pour le moment, réessaie dans une minute."

        if isinstance(error, (AuthenticationError, PermissionDeniedError)):
            return f"{self.name} refuse la demande : vérifie {self.key_name} dans le fichier .env."

        if isinstance(error, NotFoundError):
            return f"{self.name} ne trouve pas le modèle « {self.model} » : retire AI_MODEL du fichier .env."

        if isinstance(error, APIStatusError) and error.status_code == 400:
            return f"{self.name} refuse la demande ({error.message}). Vérifie {self.key_name} dans le fichier .env."

        if isinstance(error, APIStatusError) and error.status_code >= 500:
            return f"{self.name} est surchargé en ce moment, réessaie dans quelques secondes."

        return f"Erreur du cerveau IA ({self.name}) : {error}"
