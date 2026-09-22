import secrets
import urllib.error
import urllib.request
import json


class AndroidBridge:

    def __init__(
        self,
        base_url=None,
        token=None
    ):
        self.base_url = (
            base_url.rstrip("/")
            if base_url
            else None
        )

        self.token = token
        self.connected = False

    # ========================================================
    # CONFIGURATION
    # ========================================================

    def configure(self, base_url, token):
        self.base_url = base_url.rstrip("/")
        self.token = token

    # ========================================================
    # ÉTAT
    # ========================================================

    def is_configured(self):
        return bool(
            self.base_url
            and self.token
        )

    # ========================================================
    # REQUÊTE
    # ========================================================

    def _request(self, action, payload=None):

        if not self.is_configured():
            raise RuntimeError(
                "Android n'est pas configuré."
            )

        body = json.dumps({
            "action": action,
            "payload": payload or {}
        }).encode("utf-8")

        request = urllib.request.Request(
            f"{self.base_url}/api/action",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization":
                    f"Bearer {self.token}"
            }
        )

        try:

            with urllib.request.urlopen(
                request,
                timeout=10
            ) as response:

                data = json.loads(
                    response.read().decode("utf-8")
                )

            if not data.get("success"):
                raise RuntimeError(
                    data.get(
                        "error",
                        "Erreur Android inconnue."
                    )
                )

            self.connected = True

            return data.get("result")

        except urllib.error.URLError as error:

            self.connected = False

            raise RuntimeError(
                f"Android inaccessible : {error}"
            )

    # ========================================================
    # TEST DE CONNEXION
    # ========================================================

    def ping(self):

        result = self._request(
            "ping"
        )

        self.connected = True

        return result

    # ========================================================
    # MESSAGES
    # ========================================================

    def send_message(
        self,
        contact,
        message
    ):

        return self._request(
            "send_message",
            {
                "contact": contact,
                "message": message
            }
        )

    # ========================================================
    # APPELS
    # ========================================================

    def call_contact(self, contact):

        return self._request(
            "call_contact",
            {
                "contact": contact
            }
        )

    # ========================================================
    # CONTACTS
    # ========================================================

    def get_contacts(self):

        return self._request(
            "get_contacts"
        )
