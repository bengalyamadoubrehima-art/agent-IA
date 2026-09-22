class CommunicationAgent:
    """
    Couche centrale de communication de Jarvis.

    Les fournisseurs réels (Android, email, etc.) seront
    branchés derrière cette interface.
    """

    def __init__(self):
        self.providers = {}

    def register_provider(self, name, provider):
        self.providers[name] = provider

    def _provider(self, name):
        provider = self.providers.get(name)

        if provider is None:
            raise RuntimeError(
                f"Le fournisseur '{name}' n'est pas connecté."
            )

        return provider

    def envoyer_message(
        self,
        contact,
        message,
        service="mobile"
    ):
        provider = self._provider(service)

        return provider.send_message(
            contact,
            message
        )

    def appeler_contact(
        self,
        contact,
        service="mobile"
    ):
        provider = self._provider(service)

        return provider.call_contact(
            contact
        )

    def envoyer_email(
        self,
        destinataire,
        sujet,
        contenu,
        service="email"
    ):
        provider = self._provider(service)

        return provider.send_email(
            destinataire,
            sujet,
            contenu
        )
