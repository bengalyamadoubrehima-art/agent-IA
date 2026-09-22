class PermissionManager:
    """
    Gestion centrale des permissions de JARVIS.

    Trois niveaux :

    ALLOWED
        Action exécutée directement.

    CONFIRM
        JARVIS demande une confirmation avant
        d'exécuter l'action.

    BLOCKED
        Action interdite.
    """

    ALLOWED = "allowed"
    CONFIRM = "confirm"
    BLOCKED = "blocked"

    def __init__(self):

        self.rules = {

            # -----------------------------
            # Lecture / consultation
            # -----------------------------

            "informations_pc": self.ALLOWED,
            "repertoire_utilisateur": self.ALLOWED,
            "rechercher_fichier": self.ALLOWED,
            "rechercher_memoire": self.ALLOWED,

            # -----------------------------
            # Navigation
            # -----------------------------

            "ouvrir_site": self.ALLOWED,
            "ouvrir_dossier_special": self.ALLOWED,
            "ouvrir_dossier": self.ALLOWED,
            "ouvrir_fichier": self.ALLOWED,

            # -----------------------------
            # Applications
            # -----------------------------

            "ouvrir_application": self.ALLOWED,
            "lister_applications": self.ALLOWED,
            "rechercher_youtube": self.ALLOWED,
            "recherche_web": self.ALLOWED,

            # -----------------------------
            # Téléphone
            # -----------------------------

            "ouvrir_application_telephone": self.ALLOWED,
            "ouvrir_lien_telephone": self.ALLOWED,
            "rechercher_youtube_telephone": self.ALLOWED,
            "rechercher_contact": self.ALLOWED,
            "raccrocher": self.ALLOWED,
            "statut_telephone": self.ALLOWED,

            # -----------------------------
            # Gmail (lecture)
            # -----------------------------

            "lire_emails": self.ALLOWED,
            "rechercher_emails": self.ALLOWED,
            "lire_email": self.ALLOWED,

            # -----------------------------
            # Mémoire
            # -----------------------------

            "memoriser": self.ALLOWED,

            # -----------------------------
            # Communication
            # -----------------------------

            "envoyer_message": self.CONFIRM,
            "appeler_contact": self.CONFIRM,
            "envoyer_email": self.CONFIRM,
        }

    def get_permission(self, tool_name):

        return self.rules.get(
            tool_name,
            self.CONFIRM
        )

    def is_allowed(self, tool_name):

        return (
            self.get_permission(tool_name)
            == self.ALLOWED
        )

    def requires_confirmation(self, tool_name):

        return (
            self.get_permission(tool_name)
            == self.CONFIRM
        )

    def is_blocked(self, tool_name):

        return (
            self.get_permission(tool_name)
            == self.BLOCKED
        )

    def block(self, tool_name):

        self.rules[tool_name] = self.BLOCKED

    def allow(self, tool_name):

        self.rules[tool_name] = self.ALLOWED

    def require_confirmation(self, tool_name):

        self.rules[tool_name] = self.CONFIRM

    def set_permission(
        self,
        tool_name,
        permission
    ):

        if permission not in {
            self.ALLOWED,
            self.CONFIRM,
            self.BLOCKED,
        }:
            raise ValueError(
                f"Permission inconnue : {permission}"
            )

        self.rules[tool_name] = permission

    def describe(self):

        return dict(self.rules)