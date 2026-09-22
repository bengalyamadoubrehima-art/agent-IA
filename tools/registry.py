class ToolRegistry:

    def __init__(
        self,
        permissions,
        memory,
        communication=None,
        event_bus=None
    ):

        self.permissions = permissions
        self.memory = memory
        self.communication = communication
        self.event_bus = event_bus

        self.functions = {}
        self.definitions = {}

    def register(
        self,
        name,
        description,
        parameters,
        function
    ):

        self.functions[name] = function

        self.definitions[name] = {
            "type": "function",
            "name": name,
            "description": description,
            "parameters": parameters,
        }

    @property
    def api_definitions(self):

        return list(
            self.definitions.values()
        )

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

    def execute(
        self,
        name,
        arguments,
        confirmation_handler=None
    ):

        self._emit(
            "tool.started",
            {
                "tool": name,
                "arguments": arguments,
            }
        )

        if self.permissions.is_blocked(name):

            result = (
                f"Action bloquée par les permissions : "
                f"{name}"
            )

            self._emit(
                "tool.blocked",
                {
                    "tool": name,
                    "arguments": arguments,
                    "result": result,
                }
            )

            return result

        function = self.functions.get(name)

        if function is None:

            result = (
                f"Outil inconnu : {name}"
            )

            self._emit(
                "tool.failed",
                {
                    "tool": name,
                    "arguments": arguments,
                    "error": result,
                }
            )

            return result

        if self.permissions.requires_confirmation(
            name
        ):

            if confirmation_handler is None:

                result = (
                    f"Confirmation nécessaire : "
                    f"{name}"
                )

                self._emit(
                    "tool.confirmation_required",
                    {
                        "tool": name,
                        "arguments": arguments,
                    }
                )

                return result

            approved = confirmation_handler(
                name,
                arguments
            )

            if not approved:

                result = (
                    f"Action refusée par "
                    f"l'utilisateur : {name}"
                )

                self._emit(
                    "tool.denied",
                    {
                        "tool": name,
                        "arguments": arguments,
                    }
                )

                return result

        try:

            result = function(
                **arguments
            )

            self._emit(
                "tool.finished",
                {
                    "tool": name,
                    "arguments": arguments,
                    "result": str(result),
                }
            )

            return result

        except Exception as error:

            result = (
                f"Erreur dans {name} : {error}"
            )

            self._emit(
                "tool.failed",
                {
                    "tool": name,
                    "arguments": arguments,
                    "error": str(error),
                }
            )

            return result

    def setup(self):

        from tools.browser import BrowserTools
        from tools.pc import PCAgent

        # ====================================================
        # WEB
        # ====================================================

        self.register(
            "ouvrir_site",
            "Ouvre un site web.",
            {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string"
                    }
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            BrowserTools.ouvrir_site
        )

        # ====================================================
        # PC
        # ====================================================

        self.register(
            "ouvrir_dossier",
            "Ouvre un dossier local.",
            {
                "type": "object",
                "properties": {
                    "chemin": {
                        "type": "string"
                    }
                },
                "required": ["chemin"],
                "additionalProperties": False,
            },
            PCAgent.ouvrir_dossier
        )

        self.register(
            "ouvrir_dossier_special",
            "Ouvre un dossier Windows courant.",
            {
                "type": "object",
                "properties": {
                    "nom": {
                        "type": "string",
                        "enum": [
                            "home",
                            "bureau",
                            "documents",
                            "telechargements",
                            "images",
                            "videos",
                            "musique",
                        ],
                    }
                },
                "required": ["nom"],
                "additionalProperties": False,
            },
            PCAgent.ouvrir_dossier_special
        )

        self.register(
            "ouvrir_fichier",
            "Ouvre un fichier local.",
            {
                "type": "object",
                "properties": {
                    "chemin": {
                        "type": "string"
                    }
                },
                "required": ["chemin"],
                "additionalProperties": False,
            },
            PCAgent.ouvrir_fichier
        )

        self.register(
            "rechercher_fichier",
            "Recherche un fichier sur le PC.",
            {
                "type": "object",
                "properties": {
                    "nom": {
                        "type": "string"
                    },
                    "dossier": {
                        "type": "string"
                    },
                },
                "required": ["nom"],
                "additionalProperties": False,
            },
            PCAgent.rechercher_fichier
        )

        self.register(
            "ouvrir_application",
            "Ouvre une application autorisée.",
            {
                "type": "object",
                "properties": {
                    "nom": {
                        "type": "string",
                        "enum": [
                            "vscode",
                            "visual studio code",
                            "chrome",
                            "google chrome",
                            "notepad",
                            "bloc-notes",
                            "explorateur",
                            "explorer",
                        ],
                    }
                },
                "required": ["nom"],
                "additionalProperties": False,
            },
            PCAgent.ouvrir_application
        )

        self.register(
            "repertoire_utilisateur",
            "Retourne le dossier utilisateur Windows.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            PCAgent.repertoire_utilisateur
        )

        self.register(
            "informations_pc",
            "Retourne les informations du PC.",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            PCAgent.informations
        )

        # ====================================================
        # MÉMOIRE
        # ====================================================

        self.register(
            "memoriser",
            "Mémorise une information.",
            {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string"
                    },
                    "value": {
                        "type": "string"
                    },
                },
                "required": [
                    "key",
                    "value"
                ],
                "additionalProperties": False,
            },
            self.memory.remember
        )

        self.register(
            "rechercher_memoire",
            "Recherche dans la mémoire.",
            {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string"
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            self.memory.search
        )

        # ====================================================
        # COMMUNICATION
        # ====================================================

        if self.communication:

            from tools.communication import (
                CommunicationTools
            )

            communication_tools = (
                CommunicationTools(
                    self.communication
                )
            )

            self.register(
                "envoyer_message",
                (
                    "Envoie un message à un contact "
                    "via un service de communication connecté."
                ),
                {
                    "type": "object",
                    "properties": {
                        "contact": {
                            "type": "string"
                        },
                        "message": {
                            "type": "string"
                        },
                        "service": {
                            "type": "string"
                        },
                    },
                    "required": [
                        "contact",
                        "message"
                    ],
                    "additionalProperties": False,
                },
                communication_tools.envoyer_message
            )

            self.register(
                "appeler_contact",
                (
                    "Lance un appel vers un contact "
                    "via un appareil connecté."
                ),
                {
                    "type": "object",
                    "properties": {
                        "contact": {
                            "type": "string"
                        },
                        "service": {
                            "type": "string"
                        },
                    },
                    "required": [
                        "contact"
                    ],
                    "additionalProperties": False,
                },
                communication_tools.appeler_contact
            )

            self.register(
                "envoyer_email",
                "Envoie un e-mail.",
                {
                    "type": "object",
                    "properties": {
                        "destinataire": {
                            "type": "string"
                        },
                        "sujet": {
                            "type": "string"
                        },
                        "contenu": {
                            "type": "string"
                        },
                        "service": {
                            "type": "string"
                        },
                    },
                    "required": [
                        "destinataire",
                        "sujet",
                        "contenu"
                    ],
                    "additionalProperties": False,
                },
                communication_tools.envoyer_email
            )