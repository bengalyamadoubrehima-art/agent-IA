import os
import shutil
import subprocess
from pathlib import Path


class PCAgent:
    """
    Interface contrôlée entre JARVIS et Windows.
    """

    APPLICATIONS = {
        "vscode": ["code"],
        "visual studio code": ["code"],
        "chrome": ["chrome"],
        "google chrome": ["chrome"],
        "notepad": ["notepad"],
        "bloc-notes": ["notepad"],
        "explorateur": ["explorer"],
        "explorer": ["explorer"],
    }

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

        os.startfile(str(path))

        return f"Dossier ouvert : {path}"

    @staticmethod
    def ouvrir_dossier_special(nom):
        nom = nom.lower().strip()

        chemins = PCAgent.chemins_systeme()

        if nom not in chemins:
            return f"Dossier Windows inconnu : {nom}"

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

        os.startfile(str(path))

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

    @staticmethod
    def ouvrir_application(nom):
        nom = nom.lower().strip()

        candidates = PCAgent.APPLICATIONS.get(nom)

        if not candidates:
            return f"Application non autorisée : {nom}"

        for executable in candidates:

            executable_path = shutil.which(
                executable
            )

            if executable_path:
                subprocess.Popen(
                    [executable_path]
                )

                return f"Application ouverte : {nom}"

        return f"Application introuvable : {nom}"

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
                "inconnu"
            )

        return {
            "utilisateur": utilisateur,
            "ordinateur": os.environ.get(
                "COMPUTERNAME",
                "inconnu"
            ),
            "systeme": os.name,
            "repertoire_utilisateur": str(
                Path.home()
            ),
        }