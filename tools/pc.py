import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

from tools.matching import meilleure_correspondance, normaliser


SYSTEME = platform.system()


def _ouvrir_chemin(path):
    """
    Ouvre un fichier, un dossier ou une URL avec
    l'application par défaut du système.
    """

    if SYSTEME == "Windows":
        os.startfile(str(path))

    elif SYSTEME == "Darwin":
        subprocess.Popen(["open", str(path)])

    else:
        subprocess.Popen(["xdg-open", str(path)])


class PCAgent:
    """
    Interface contrôlée entre JARVIS et l'ordinateur
    (Windows en priorité, Linux et macOS pris en charge).
    """

    # Noms parlés → nom canonique
    ALIAS = {
        "gestionnaire de fichiers": "fichiers",
        "explorateur de fichiers": "fichiers",
        "explorateur": "fichiers",
        "explorer": "fichiers",
        "finder": "fichiers",
        "mes fichiers": "fichiers",
        "vscode": "visual studio code",
        "vs code": "visual studio code",
        "code": "visual studio code",
        "chrome": "google chrome",
        "bloc notes": "bloc-notes",
        "notepad": "bloc-notes",
        "calculette": "calculatrice",
        "calculator": "calculatrice",
        "invite de commandes": "terminal",
        "cmd": "terminal",
        "powershell": "terminal",
        "console": "terminal",
        "gestionnaire de taches": "gestionnaire des taches",
        "task manager": "gestionnaire des taches",
        "parametres": "parametres",
        "reglages": "parametres",
        "settings": "parametres",
        "navigateur": "navigateur",
        "browser": "navigateur",
    }

    # Nom canonique → commandes à essayer (dans le PATH)
    COMMANDES = {
        "visual studio code": ["code"],
        "google chrome": ["chrome", "google-chrome", "google-chrome-stable", "chromium"],
        "firefox": ["firefox"],
        "bloc-notes": ["notepad", "gnome-text-editor", "gedit", "kate", "mousepad"],
        "calculatrice": ["calc", "gnome-calculator", "kcalc"],
        "terminal": ["wt", "powershell", "gnome-terminal", "konsole", "x-terminal-emulator"],
        "gestionnaire des taches": ["taskmgr", "gnome-system-monitor"],
        "spotify": ["spotify"],
        "discord": ["discord"],
        "vlc": ["vlc"],
    }

    _applications_installees = None

    @staticmethod
    def chemins_systeme():
        home = Path.home()

        return {
            "home": home,
            "bureau": home / "Desktop",
            "documents": home / "Documents",
            "telechargements": home / "Downloads",
            "images": home / "Pictures",
            "videos": home / "Videos",
            "musique": home / "Music",
        }

    @staticmethod
    def ouvrir_dossier(chemin):
        path = Path(
            os.path.expanduser(chemin)
        ).resolve()

        if not path.exists():
            return f"Dossier inexistant : {path}"

        if not path.is_dir():
            return f"Ce chemin n'est pas un dossier : {path}"

        _ouvrir_chemin(path)

        return f"Dossier ouvert : {path}"

    @staticmethod
    def ouvrir_dossier_special(nom):
        nom = nom.lower().strip()

        chemins = PCAgent.chemins_systeme()

        if nom not in chemins:
            return f"Dossier inconnu : {nom}"

        return PCAgent.ouvrir_dossier(
            chemins[nom]
        )

    @staticmethod
    def ouvrir_fichier(chemin):
        path = Path(
            os.path.expanduser(chemin)
        ).resolve()

        if not path.exists():
            return f"Fichier inexistant : {path}"

        if not path.is_file():
            return f"Ce chemin n'est pas un fichier : {path}"

        _ouvrir_chemin(path)

        return f"Fichier ouvert : {path}"

    @staticmethod
    def rechercher_fichier(nom, dossier=None):
        base = Path(
            os.path.expanduser(dossier)
            if dossier
            else Path.home()
        ).resolve()

        if not base.exists():
            return f"Dossier inexistant : {base}"

        if not base.is_dir():
            return f"Ce chemin n'est pas un dossier : {base}"

        recherche = nom.lower().strip()

        if not recherche:
            return "Le nom du fichier est vide."

        results = []

        try:
            for path in base.rglob("*"):

                if not path.is_file():
                    continue

                if recherche in path.name.lower():
                    results.append(str(path))

                if len(results) >= 20:
                    break

        except (PermissionError, OSError):
            pass

        if not results:
            return "Aucun fichier correspondant trouvé."

        return "\n".join(results)

    # =========================================================
    # APPLICATIONS
    # =========================================================

    @staticmethod
    def applications_installees():
        """
        Retourne {nom affiché: lanceur} pour les applications
        installées. Le résultat est mis en cache.
        """

        if PCAgent._applications_installees is not None:
            return PCAgent._applications_installees

        applications = {}

        try:
            if SYSTEME == "Windows":
                applications = PCAgent._applications_windows()

            elif SYSTEME == "Darwin":
                applications = PCAgent._applications_macos()

            else:
                applications = PCAgent._applications_linux()

        except Exception as error:
            print(f"⚠️ Liste des applications indisponible : {error}")

        PCAgent._applications_installees = applications

        return applications

    @staticmethod
    def _applications_windows():
        # Get-StartApps couvre le menu Démarrer et les
        # applications du Microsoft Store (WhatsApp, Spotify…).
        sortie = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                "Get-StartApps | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        ).stdout

        donnees = json.loads(sortie or "[]")

        if isinstance(donnees, dict):
            donnees = [donnees]

        return {
            item["Name"]: ("windows_app", item["AppID"])
            for item in donnees
            if item.get("Name") and item.get("AppID")
        }

    @staticmethod
    def _applications_macos():
        applications = {}

        for dossier in [
            Path("/Applications"),
            Path("/System/Applications"),
            Path.home() / "Applications",
        ]:
            if dossier.is_dir():
                for app in dossier.glob("*.app"):
                    applications[app.stem] = ("chemin", str(app))

        return applications

    @staticmethod
    def _applications_linux():
        applications = {}

        dossiers = [
            Path("/usr/share/applications"),
            Path("/usr/local/share/applications"),
            Path("/var/lib/flatpak/exports/share/applications"),
            Path.home() / ".local/share/applications",
        ]

        for dossier in dossiers:

            if not dossier.is_dir():
                continue

            for fichier in dossier.glob("*.desktop"):

                try:
                    lignes = fichier.read_text(
                        encoding="utf-8",
                        errors="ignore"
                    ).splitlines()
                except OSError:
                    continue

                nom = None
                cache = False

                for ligne in lignes:
                    if ligne.startswith("Name=") and nom is None:
                        nom = ligne[5:].strip()
                    elif ligne.strip() in {"NoDisplay=true", "Hidden=true"}:
                        cache = True

                if nom and not cache:
                    applications[nom] = ("desktop", fichier.stem)

        return applications

    @staticmethod
    def _lancer(type_lanceur, cible):

        if type_lanceur == "windows_app":
            subprocess.Popen(
                ["explorer.exe", f"shell:AppsFolder\\{cible}"]
            )

        elif type_lanceur == "desktop":
            subprocess.Popen(
                ["gtk-launch", cible],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        elif type_lanceur == "commande":
            if SYSTEME == "Windows":
                # Donne leur propre fenêtre aux applications console
                os.startfile(cible)
            else:
                subprocess.Popen(
                    [cible],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

        else:
            _ouvrir_chemin(cible)

    @staticmethod
    def ouvrir_application(nom):
        demande = nom.strip()
        cle = normaliser(demande)

        if not cle:
            return "Le nom de l'application est vide."

        canonique = PCAgent.ALIAS.get(cle, cle)

        if canonique == "fichiers":
            PCAgent.ouvrir_dossier(Path.home())
            return "Gestionnaire de fichiers ouvert."

        if canonique == "navigateur":
            _ouvrir_chemin("https://www.google.com")
            return "Navigateur ouvert."

        if canonique == "parametres":
            if SYSTEME == "Windows":
                _ouvrir_chemin("ms-settings:")
                return "Paramètres ouverts."
            canonique = "settings"

        # 1. Commande connue présente dans le PATH
        for commande in PCAgent.COMMANDES.get(canonique, []):

            executable = shutil.which(commande)

            if executable:
                PCAgent._lancer("commande", executable)
                return f"Application ouverte : {demande}"

        # 2. Application installée (menu Démarrer, .desktop, /Applications)
        applications = PCAgent.applications_installees()

        trouve = meilleure_correspondance(
            canonique,
            list(applications)
        )

        if trouve is None and canonique != cle:
            trouve = meilleure_correspondance(
                cle,
                list(applications)
            )

        if trouve:
            PCAgent._lancer(*applications[trouve])
            return f"Application ouverte : {trouve}"

        # 3. Exécutable du même nom dans le PATH
        executable = shutil.which(cle.replace(" ", ""))

        if executable:
            PCAgent._lancer("commande", executable)
            return f"Application ouverte : {demande}"

        return (
            f"Application introuvable sur ce PC : {demande}. "
            "Utilise lister_applications pour voir les noms exacts."
        )

    @staticmethod
    def lister_applications(filtre=""):
        applications = sorted(
            PCAgent.applications_installees()
        )

        if filtre:
            f = normaliser(filtre)
            applications = [
                nom for nom in applications
                if f in normaliser(nom)
            ]

        if not applications:
            return "Aucune application trouvée."

        return "\n".join(applications[:150])

    @staticmethod
    def repertoire_utilisateur():
        return str(Path.home())

    @staticmethod
    def informations():
        try:
            utilisateur = os.getlogin()
        except OSError:
            utilisateur = os.environ.get(
                "USERNAME",
                os.environ.get("USER", "inconnu")
            )

        return {
            "utilisateur": utilisateur,
            "ordinateur": platform.node() or "inconnu",
            "systeme": f"{SYSTEME} {platform.release()}",
            "repertoire_utilisateur": str(
                Path.home()
            ),
        }
