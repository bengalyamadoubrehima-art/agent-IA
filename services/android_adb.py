import os
import re
import shlex
import shutil
import subprocess
import time
import urllib.parse
import xml.etree.ElementTree as ElementTree

from tools.matching import meilleure_correspondance, normaliser


class AndroidPhone:
    """
    Contrôle d'un téléphone Android depuis le PC via ADB
    (débogage USB ou débogage sans fil).

    Aucune application à installer sur le téléphone :
    ADB permet d'ouvrir des applications, de lancer des
    appels, de lire les contacts et d'appuyer sur le bouton
    « Envoyer » de WhatsApp.
    """

    APPLICATIONS = {
        "youtube": "com.google.android.youtube",
        "youtube music": "com.google.android.apps.youtube.music",
        "whatsapp": "com.whatsapp",
        "whatsapp business": "com.whatsapp.w4b",
        "gmail": "com.google.android.gm",
        "chrome": "com.android.chrome",
        "google": "com.google.android.googlequicksearchbox",
        "maps": "com.google.android.apps.maps",
        "google maps": "com.google.android.apps.maps",
        "play store": "com.android.vending",
        "photos": "com.google.android.apps.photos",
        "google photos": "com.google.android.apps.photos",
        "instagram": "com.instagram.android",
        "facebook": "com.facebook.katana",
        "messenger": "com.facebook.orca",
        "tiktok": "com.zhiliaoapp.musically",
        "snapchat": "com.snapchat.android",
        "telegram": "org.telegram.messenger",
        "x": "com.twitter.android",
        "twitter": "com.twitter.android",
        "spotify": "com.spotify.music",
        "netflix": "com.netflix.mediaclient",
        "deezer": "deezer.android.app",
        "discord": "com.discord",
        "linkedin": "com.linkedin.android",
    }

    # Applications système dont le paquet varie selon le fabricant :
    # on passe par une action Android standard.
    INTENTS = {
        "appareil photo": ["-a", "android.media.action.STILL_IMAGE_CAMERA"],
        "camera": ["-a", "android.media.action.STILL_IMAGE_CAMERA"],
        "parametres": ["-a", "android.settings.SETTINGS"],
        "reglages": ["-a", "android.settings.SETTINGS"],
        "telephone": ["-a", "android.intent.action.DIAL"],
        "contacts": ["-a", "android.intent.action.VIEW", "-d", "content://contacts/people/"],
        "messages": ["-a", "android.intent.action.MAIN", "-c", "android.intent.category.APP_MESSAGING"],
        "sms": ["-a", "android.intent.action.MAIN", "-c", "android.intent.category.APP_MESSAGING"],
        "calendrier": ["-a", "android.intent.action.MAIN", "-c", "android.intent.category.APP_CALENDAR"],
        "galerie": ["-a", "android.intent.action.MAIN", "-c", "android.intent.category.APP_GALLERY"],
        "horloge": ["-a", "android.intent.action.SHOW_ALARMS"],
        "alarme": ["-a", "android.intent.action.SHOW_ALARMS"],
        "calculatrice": ["-a", "android.intent.action.MAIN", "-c", "android.intent.category.APP_CALCULATOR"],
    }

    def __init__(
        self,
        serial=None,
        country_code=None,
        whatsapp_package=None,
        adb_path=None,
    ):
        self.serial = serial or os.getenv("ANDROID_ADB_SERIAL", "").strip() or None

        self.country_code = (
            country_code
            or os.getenv("PHONE_COUNTRY_CODE", "")
        ).strip().lstrip("+")

        self.whatsapp_package = (
            whatsapp_package
            or os.getenv("WHATSAPP_PACKAGE", "com.whatsapp")
        )

        self.adb_path = (
            adb_path
            or os.getenv("ADB_PATH", "").strip()
            or shutil.which("adb")
        )

        self._contacts = None
        self._contacts_time = 0

    # ========================================================
    # ADB
    # ========================================================

    def _adb(self, *args, timeout=20, serial=True):

        if not self.adb_path:
            raise RuntimeError(
                "ADB est introuvable. Installe les « Android SDK "
                "Platform Tools » et ajoute adb au PATH (ou définis "
                "ADB_PATH dans .env)."
            )

        commande = [self.adb_path]

        if serial and self.serial:
            commande += ["-s", self.serial]

        commande += list(args)

        resultat = subprocess.run(
            commande,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

        if resultat.returncode != 0:
            raise RuntimeError(
                (resultat.stderr or resultat.stdout).strip()
                or f"Échec de la commande adb {' '.join(args)}"
            )

        return resultat.stdout

    def _shell(self, *args, timeout=20):
        # adb shell recolle les arguments : on les protège
        # pour que les « & » et apostrophes passent intacts.
        commande = " ".join(
            shlex.quote(str(arg))
            for arg in args
        )

        return self._adb("shell", commande, timeout=timeout)

    def connecter(self):
        """
        Vérifie que le téléphone est joignable et
        se connecte en Wi-Fi si nécessaire.
        """

        if self.serial and ":" in self.serial:

            appareils = self._adb("devices", serial=False)

            if f"{self.serial}\tdevice" not in appareils:
                sortie = self._adb("connect", self.serial, serial=False)

                if "connected" not in sortie:
                    raise RuntimeError(
                        f"Connexion ADB impossible à {self.serial} : "
                        f"{sortie.strip()}"
                    )

        etat = self._adb("get-state").strip()

        if etat != "device":
            raise RuntimeError(
                f"Téléphone non prêt (état : {etat}). Vérifie que le "
                "débogage est activé et autorisé sur le téléphone."
            )

    def statut(self):
        try:
            self.connecter()
            modele = self._shell("getprop", "ro.product.model").strip()
            return f"Téléphone connecté : {modele}"

        except Exception as error:
            return f"Téléphone non connecté : {error}"

    def est_connecte(self):
        try:
            self.connecter()
            return True
        except Exception:
            return False

    def _reveiller(self):
        self._shell("input", "keyevent", "KEYCODE_WAKEUP")

    # ========================================================
    # APPLICATIONS
    # ========================================================

    def _paquets_installes(self):
        sortie = self._shell("pm", "list", "packages")

        return [
            ligne.split(":", 1)[1].strip()
            for ligne in sortie.splitlines()
            if ligne.startswith("package:")
        ]

    def ouvrir_application(self, nom):
        self.connecter()
        self._reveiller()

        cle = normaliser(nom)

        if cle in self.INTENTS:
            self._shell("am", "start", *self.INTENTS[cle])
            return f"Application ouverte sur le téléphone : {nom}"

        paquets = self._paquets_installes()

        paquet = self.APPLICATIONS.get(cle)

        if paquet is None or paquet not in paquets:
            # Nom de paquet donné directement, ou recherche approchée
            # dans les paquets (« netflix » → com.netflix.mediaclient).
            if cle in paquets:
                paquet = cle
            else:
                compact = cle.replace(" ", "")
                candidats = [
                    p for p in paquets
                    if compact in p.lower().replace("_", "")
                ]
                paquet = min(candidats, key=len) if candidats else None

        if paquet is None:
            return (
                f"Application introuvable sur le téléphone : {nom}"
            )

        sortie = self._shell(
            "monkey",
            "-p", paquet,
            "-c", "android.intent.category.LAUNCHER",
            "1",
        )

        if "No activities found" in sortie:
            return f"Impossible de lancer {paquet} sur le téléphone."

        return f"Application ouverte sur le téléphone : {nom}"

    def ouvrir_lien(self, url):
        self.connecter()
        self._reveiller()

        if not re.match(r"^[a-z][a-z0-9+.-]*:", url):
            url = "https://" + url

        self._shell(
            "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", url,
        )

        return f"Lien ouvert sur le téléphone : {url}"

    def rechercher_youtube(self, recherche):
        return self.ouvrir_lien(
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote_plus(recherche)
        )

    # ========================================================
    # CONTACTS
    # ========================================================

    def contacts(self):
        """
        Retourne {nom: numéro}, mis en cache 5 minutes.
        """

        if self._contacts is not None and time.time() - self._contacts_time < 300:
            return self._contacts

        self.connecter()

        sortie = self._shell(
            "content", "query",
            "--uri", "content://com.android.contacts/data/phones",
            "--projection", "display_name:data1",
        )

        contacts = {}

        for ligne in sortie.splitlines():

            trouve = re.search(
                r"display_name=(.*?), data1=(.*)$",
                ligne
            )

            if trouve:
                nom = trouve.group(1).strip()
                numero = trouve.group(2).strip()

                if nom and numero and numero != "NULL":
                    contacts.setdefault(nom, numero)

        self._contacts = contacts
        self._contacts_time = time.time()

        return contacts

    @staticmethod
    def _est_numero(texte):
        return bool(re.fullmatch(r"[+\d][\d\s.\-()]{5,}", texte.strip()))

    def resoudre_contact(self, contact):
        """
        Retourne (nom, numéro) à partir d'un nom ou d'un numéro.
        """

        if self._est_numero(contact):
            return contact.strip(), contact.strip()

        contacts = self.contacts()

        nom = meilleure_correspondance(contact, list(contacts))

        if nom is None:
            raise RuntimeError(
                f"Contact introuvable dans le téléphone : {contact}"
            )

        return nom, contacts[nom]

    def rechercher_contact(self, nom):
        recherche = normaliser(nom)

        resultats = [
            f"{contact} : {numero}"
            for contact, numero in self.contacts().items()
            if recherche in normaliser(contact)
        ]

        if not resultats:
            try:
                contact, numero = self.resoudre_contact(nom)
                resultats = [f"{contact} : {numero}"]
            except RuntimeError:
                return f"Aucun contact ne correspond à « {nom} »."

        return "\n".join(resultats[:20])

    def numero_international(self, numero):
        """
        Format attendu par WhatsApp : indicatif + numéro,
        chiffres uniquement (ex. 33612345678).
        """

        brut = numero.strip()
        chiffres = re.sub(r"\D", "", brut)

        if brut.startswith("+"):
            return chiffres

        if chiffres.startswith("00"):
            return chiffres[2:]

        if self.country_code:

            if chiffres.startswith(self.country_code) and len(chiffres) > 10:
                return chiffres

            if chiffres.startswith("0"):
                return self.country_code + chiffres[1:]

            return self.country_code + chiffres

        return chiffres

    # ========================================================
    # INTERFACE DU TÉLÉPHONE
    # ========================================================

    def _noeuds_ecran(self):
        self._shell("uiautomator", "dump", "/sdcard/jarvis_ui.xml", timeout=30)
        xml = self._shell("cat", "/sdcard/jarvis_ui.xml")

        debut = xml.find("<?xml")

        if debut < 0:
            return []

        racine = ElementTree.fromstring(xml[debut:].strip())

        return list(racine.iter("node"))

    def _appuyer_sur(self, correspond, delai=12):
        """
        Attend qu'un élément correspondant apparaisse
        à l'écran puis appuie dessus.
        """

        limite = time.time() + delai

        while time.time() < limite:

            try:
                noeuds = self._noeuds_ecran()
            except Exception:
                noeuds = []

            for noeud in noeuds:

                if not correspond(noeud):
                    continue

                zone = re.findall(r"\d+", noeud.get("bounds", ""))

                if len(zone) != 4:
                    continue

                x1, y1, x2, y2 = map(int, zone)

                self._shell(
                    "input", "tap",
                    str((x1 + x2) // 2),
                    str((y1 + y2) // 2),
                )

                return True

            time.sleep(1)

        return False

    # ========================================================
    # MESSAGES
    # ========================================================

    def send_message(self, contact, message, application="whatsapp"):

        application = normaliser(application or "whatsapp")

        self.connecter()

        nom, numero = self.resoudre_contact(contact)

        self._reveiller()

        if application == "sms":
            return self._envoyer_sms(nom, numero, message)

        return self._envoyer_whatsapp(nom, numero, message)

    def _envoyer_whatsapp(self, nom, numero, message):

        numero = self.numero_international(numero)

        url = (
            "https://api.whatsapp.com/send?phone="
            + numero
            + "&text="
            + urllib.parse.quote(message, safe="")
        )

        self._shell(
            "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", url,
            "-p", self.whatsapp_package,
        )

        identifiant = f"{self.whatsapp_package}:id/send"

        envoye = self._appuyer_sur(
            lambda noeud: (
                noeud.get("resource-id") == identifiant
                or normaliser(noeud.get("content-desc", "")) in {"envoyer", "send"}
            )
        )

        if not envoye:
            return (
                f"WhatsApp est ouvert avec le message pour {nom}, "
                "mais le bouton Envoyer n'a pas été trouvé "
                "(téléphone verrouillé ou numéro absent de WhatsApp ?)."
            )

        return f"Message WhatsApp envoyé à {nom} ({numero})."

    def _envoyer_sms(self, nom, numero, message):

        self._shell(
            "am", "start",
            "-a", "android.intent.action.SENDTO",
            "-d", f"sms:{numero}",
            "--es", "sms_body", message,
            "--ez", "exit_on_sent", "true",
        )

        def bouton_envoyer(noeud):
            description = normaliser(noeud.get("content-desc", ""))
            identifiant = noeud.get("resource-id", "")

            return (
                description.startswith(("envoyer", "send"))
                or identifiant.endswith(("/send", "/send_button", "/send_message_button_icon"))
            )

        if not self._appuyer_sur(bouton_envoyer):
            return (
                f"Le SMS pour {nom} est prêt sur le téléphone, "
                "mais le bouton Envoyer n'a pas été trouvé."
            )

        return f"SMS envoyé à {nom} ({numero})."

    # ========================================================
    # APPELS
    # ========================================================

    def call_contact(self, contact):

        self.connecter()

        nom, numero = self.resoudre_contact(contact)

        self._reveiller()

        self._shell(
            "am", "start",
            "-a", "android.intent.action.CALL",
            "-d", "tel:" + re.sub(r"[^\d+]", "", numero),
        )

        return f"Appel en cours vers {nom} ({numero})."

    def raccrocher(self):
        self.connecter()
        self._shell("input", "keyevent", "KEYCODE_ENDCALL")
        return "Appel terminé."
