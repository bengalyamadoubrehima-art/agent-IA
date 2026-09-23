class CommunicationTools:

    def __init__(self, communication):
        self.communication = communication

    def envoyer_message(
        self,
        contact,
        message,
        service="whatsapp"
    ):
        return self.communication.envoyer_message(
            contact=contact,
            message=message,
            service=service
        )

    def appeler_contact(
        self,
        contact,
        service="telephone"
    ):
        return self.communication.appeler_contact(
            contact=contact,
            service=service
        )

    def envoyer_email(
        self,
        destinataire,
        sujet,
        contenu,
        service="email"
    ):
        return self.communication.envoyer_email(
            destinataire=destinataire,
            sujet=sujet,
            contenu=contenu,
            service=service
        )
