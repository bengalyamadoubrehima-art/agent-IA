import difflib
import re
import unicodedata


def normaliser(texte):
    """
    Minuscules, sans accents, ponctuation ni espaces superflus
    (« Jean-Pierre » → « jean pierre »).
    """

    texte = unicodedata.normalize(
        "NFKD",
        str(texte)
    )

    texte = "".join(
        caractere
        for caractere in texte
        if not unicodedata.combining(caractere)
    )

    texte = re.sub(r"[^\w+]+", " ", texte.lower())

    return " ".join(texte.split())


def meilleure_correspondance(recherche, candidats, seuil=0.72):
    """
    Retourne le candidat le plus proche de la recherche,
    ou None si rien ne correspond suffisamment.

    candidats : liste de chaînes.
    """

    recherche = normaliser(recherche)

    if not recherche:
        return None

    index = {}

    for candidat in candidats:
        index.setdefault(
            normaliser(candidat),
            candidat
        )

    if recherche in index:
        return index[recherche]

    # Mots entiers ("word" → "microsoft word"), puis début du nom
    # ("spot" → "spotify"), puis n'importe où dans le nom.
    regles = [
        lambda cle: f" {recherche} " in f" {cle} ",
        lambda cle: cle.startswith(recherche),
        lambda cle: len(recherche) >= 4 and recherche in cle,
    ]

    for regle in regles:

        trouves = [cle for cle in index if regle(cle)]

        if trouves:
            return index[min(trouves, key=len)]

    proches = difflib.get_close_matches(
        recherche,
        list(index),
        n=1,
        cutoff=seuil,
    )

    if proches:
        return index[proches[0]]

    return None
