import os


class SystemTools:

    @staticmethod
    def obtenir_repertoire_utilisateur():
        return os.path.expanduser("~")

    @staticmethod
    def nom_ordinateur():
        return os.environ.get(
            "COMPUTERNAME",
            "inconnu"
        )

    @staticmethod
    def utilisateur():
        return os.environ.get(
            "USERNAME",
            "inconnu"
        )