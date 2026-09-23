class ToolRegistry:

    def __init__(
        self,
        permissions,
        memory,
        communication=None,
        event_bus=None,
        phone=None,
        email=None
    ):

        self.permissions = permissions
        self.memory = memory
        self.communication = communication
        self.event_bus = event_bus
        self.phone = phone
        self.email = email

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

        self.register(
            "rechercher_youtube",
            "Lance une recherche YouTube sur le PC.",
            {
                "type": "object",
                "properties": {
                    "recherche": {
                        "type": "string"
                    }
                },
                "required": ["recherche"],
                "additionalProperties": False,
            },
            BrowserTools.rechercher_youtube
        )

        self.register(
            "recherche_web",
            "Lance une recherche Google sur le PC.",
            {
                "type": "object",
                "properties": {
                    "recherche": {
                        "type": "string"
                    }
                },
                "required": ["recherche"],
                "additionalProperties": False,
            },
            BrowserTools.recherche_web
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
            "Ouvre un dossier utilisateur courant.",
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
            (
                "Ouvre une application installée sur le PC "
                "(ex. : gestionnaire de fichiers, vs code, chrome, "
                "spotify, discord, calculatrice, terminal, paramètres, "
                "word, whatsapp…)."
            ),
            {
                "type": "object",
                "properties": {
                    "nom": {
                        "type": "string",
                        "description": "Nom de l'application, tel que dit par l'utilisateur.",
                    }
                },
                "required": ["nom"],
                "additionalProperties": False,
            },
            PCAgent.ouvrir_application
        )

        self.register(
            "lister_applications",
            "Liste les applications installées sur le PC.",
            {
                "type": "object",
                "properties": {
                    "filtre": {
                        "type": "string",
                        "description": "Texte à rechercher dans le nom (facultatif).",
                    }
                },
                "additionalProperties": False,
            },
            PCAgent.lister_applications
        )

        self.register(
            "repertoire_utilisateur",
            "Retourne le dossier utilisateur.",
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
                    "Envoie un message depuis le téléphone à un "
                    "contact (nom du répertoire ou numéro)."
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
                            "type": "string",
                            "enum": ["whatsapp", "sms"],
                            "description": "whatsapp par défaut.",
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
                    "Appelle un contact depuis le téléphone "
                    "(nom du répertoire ou numéro)."
                ),
                {
                    "type": "object",
                    "properties": {
                        "contact": {
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
                "Envoie un e-mail depuis le compte Gmail.",
                {
                    "type": "object",
                    "properties": {
                        "destinataire": {
                            "type": "string",
                            "description": "Adresse e-mail.",
                        },
                        "sujet": {
                            "type": "string"
                        },
                        "contenu": {
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

        # ====================================================
        # TÉLÉPHONE
        # ====================================================

        if self.phone:

            self.register(
                "ouvrir_application_telephone",
                (
                    "Ouvre une application sur le téléphone Android "
                    "(youtube, whatsapp, instagram, appareil photo, "
                    "parametres…)."
                ),
                {
                    "type": "object",
                    "properties": {
                        "nom": {
                            "type": "string"
                        }
                    },
                    "required": ["nom"],
                    "additionalProperties": False,
                },
                self.phone.ouvrir_application
            )

            self.register(
                "ouvrir_lien_telephone",
                "Ouvre un lien (site, vidéo…) sur le téléphone.",
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
                self.phone.ouvrir_lien
            )

            self.register(
                "rechercher_youtube_telephone",
                "Lance une recherche dans YouTube sur le téléphone.",
                {
                    "type": "object",
                    "properties": {
                        "recherche": {
                            "type": "string"
                        }
                    },
                    "required": ["recherche"],
                    "additionalProperties": False,
                },
                self.phone.rechercher_youtube
            )

            self.register(
                "rechercher_contact",
                "Cherche un contact et son numéro dans le téléphone.",
                {
                    "type": "object",
                    "properties": {
                        "nom": {
                            "type": "string"
                        }
                    },
                    "required": ["nom"],
                    "additionalProperties": False,
                },
                self.phone.rechercher_contact
            )

            self.register(
                "raccrocher",
                "Termine l'appel en cours sur le téléphone.",
                {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                self.phone.raccrocher
            )

            self.register(
                "statut_telephone",
                "Indique si le téléphone est connecté à JARVIS.",
                {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                self.phone.statut
            )

        # ====================================================
        # GMAIL
        # ====================================================

        if self.email:

            self.register(
                "lire_emails",
                (
                    "Liste les derniers e-mails de la boîte de "
                    "réception Gmail (expéditeur, sujet, id)."
                ),
                {
                    "type": "object",
                    "properties": {
                        "nombre": {
                            "type": "integer",
                            "description": "5 par défaut, 25 maximum.",
                        },
                        "non_lus_seulement": {
                            "type": "boolean"
                        },
                    },
                    "additionalProperties": False,
                },
                self.email.lire_emails
            )

            self.register(
                "rechercher_emails",
                (
                    "Recherche des e-mails Gmail avec la syntaxe "
                    "Gmail (ex. : from:banque, subject:facture, "
                    "is:unread, newer_than:7d)."
                ),
                {
                    "type": "object",
                    "properties": {
                        "recherche": {
                            "type": "string"
                        },
                        "nombre": {
                            "type": "integer"
                        },
                    },
                    "required": ["recherche"],
                    "additionalProperties": False,
                },
                self.email.rechercher_emails
            )

            self.register(
                "lire_email",
                "Lit le contenu complet d'un e-mail à partir de son id.",
                {
                    "type": "object",
                    "properties": {
                        "identifiant": {
                            "type": "string"
                        }
                    },
                    "required": ["identifiant"],
                    "additionalProperties": False,
                },
                self.email.lire_email
            )
