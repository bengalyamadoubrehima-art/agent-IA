import html
import imaplib
import os
import re
import smtplib
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime


class GmailService:
    """
    Lecture et envoi d'e-mails Gmail via IMAP / SMTP.

    Configuration (.env) :
        GMAIL_ADDRESS       adresse Gmail
        GMAIL_APP_PASSWORD  mot de passe d'application Google
                            (https://myaccount.google.com/apppasswords)
    """

    IMAP_HOST = "imap.gmail.com"
    SMTP_HOST = "smtp.gmail.com"

    def __init__(self, address=None, app_password=None):
        self.address = (
            address
            or os.getenv("GMAIL_ADDRESS", "")
        ).strip()

        self.app_password = (
            app_password
            or os.getenv("GMAIL_APP_PASSWORD", "")
        ).replace(" ", "")

    def is_configured(self):
        return bool(self.address and self.app_password)

    def _verifier(self):
        if not self.is_configured():
            raise RuntimeError(
                "Gmail n'est pas configuré : ajoute GMAIL_ADDRESS et "
                "GMAIL_APP_PASSWORD dans le fichier .env."
            )

    # ========================================================
    # IMAP
    # ========================================================

    def _connexion(self):
        self._verifier()

        imap = imaplib.IMAP4_SSL(self.IMAP_HOST)
        imap.login(self.address, self.app_password)

        # « Tous les messages » : un seul dossier pour la boîte
        # de réception et la recherche, donc des UID cohérents.
        dossier = "INBOX"

        _, lignes = imap.list()

        for ligne in lignes or []:
            texte = ligne.decode("utf-8", errors="ignore")

            if "\\All" in texte:
                dossier = texte.rsplit(' "/" ', 1)[-1].strip()
                break

        imap.select(dossier, readonly=True)

        return imap

    @staticmethod
    def _rechercher_uids(imap, requete):
        # Syntaxe de recherche Gmail (from:, is:unread, …),
        # envoyée en littéral UTF-8 pour accepter les accents.
        imap.literal = requete.encode("utf-8")

        _, donnees = imap.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW")

        return (donnees[0] or b"").split()

    @staticmethod
    def _resumer(imap, uids):
        if not uids:
            return []

        _, donnees = imap.uid(
            "FETCH",
            b",".join(uids).decode(),
            "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])",
        )

        resumes = []

        for element in donnees:

            if not isinstance(element, tuple):
                continue

            uid = re.search(rb"UID (\d+)", element[0])

            entetes = message_from_bytes(
                element[1],
                policy=policy.default
            )

            try:
                date = parsedate_to_datetime(entetes["date"]).strftime("%d/%m/%Y %H:%M")
            except (TypeError, ValueError):
                date = entetes["date"] or ""

            resumes.append({
                "id": uid.group(1).decode() if uid else "?",
                "de": str(entetes["from"] or ""),
                "sujet": str(entetes["subject"] or "(sans objet)"),
                "date": date,
            })

        resumes.sort(key=lambda r: int(r["id"]) if r["id"].isdigit() else 0, reverse=True)

        return resumes

    @staticmethod
    def _formater(resumes):
        if not resumes:
            return "Aucun e-mail trouvé."

        return "\n".join(
            f"[id {r['id']}] {r['date']} — {r['de']} — {r['sujet']}"
            for r in resumes
        )

    def lire_emails(self, nombre=5, non_lus_seulement=False):
        nombre = max(1, min(int(nombre), 25))

        requete = "in:inbox"

        if non_lus_seulement:
            requete += " is:unread"

        imap = self._connexion()

        try:
            uids = self._rechercher_uids(imap, requete)[-nombre:]
            return self._formater(self._resumer(imap, uids))
        finally:
            imap.logout()

    def rechercher_emails(self, recherche, nombre=10):
        nombre = max(1, min(int(nombre), 25))

        imap = self._connexion()

        try:
            uids = self._rechercher_uids(imap, recherche)[-nombre:]
            return self._formater(self._resumer(imap, uids))
        finally:
            imap.logout()

    def lire_email(self, identifiant):
        imap = self._connexion()

        try:
            _, donnees = imap.uid("FETCH", str(identifiant), "(BODY.PEEK[])")
        finally:
            imap.logout()

        brut = next(
            (element[1] for element in donnees if isinstance(element, tuple)),
            None
        )

        if brut is None:
            return f"E-mail introuvable : {identifiant}"

        message = message_from_bytes(brut, policy=policy.default)

        partie = message.get_body(preferencelist=("plain", "html"))
        contenu = ""

        if partie is not None:
            contenu = partie.get_content()

            if partie.get_content_type() == "text/html":
                contenu = re.sub(r"(?is)<(script|style).*?</\1>", "", contenu)
                contenu = re.sub(r"(?s)<[^>]+>", " ", contenu)
                contenu = html.unescape(contenu)

        contenu = re.sub(r"[ \t]+", " ", contenu)
        contenu = re.sub(r"\n\s*\n+", "\n\n", contenu).strip()

        pieces_jointes = [
            piece.get_filename()
            for piece in message.iter_attachments()
            if piece.get_filename()
        ]

        texte = (
            f"De : {message['from']}\n"
            f"À : {message['to']}\n"
            f"Date : {message['date']}\n"
            f"Sujet : {message['subject']}\n"
        )

        if pieces_jointes:
            texte += f"Pièces jointes : {', '.join(pieces_jointes)}\n"

        return texte + "\n" + (contenu[:5000] or "(message vide)")

    # ========================================================
    # SMTP
    # ========================================================

    def send_email(self, destinataire, sujet, contenu):
        self._verifier()

        message = EmailMessage()
        message["From"] = self.address
        message["To"] = destinataire
        message["Subject"] = sujet
        message.set_content(contenu)

        with smtplib.SMTP_SSL(self.SMTP_HOST, 465, timeout=30) as smtp:
            smtp.login(self.address, self.app_password)
            smtp.send_message(message)

        return f"E-mail envoyé à {destinataire}."
