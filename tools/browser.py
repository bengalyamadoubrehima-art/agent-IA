import urllib.parse
import webbrowser


class BrowserTools:

    @staticmethod
    def ouvrir_site(url):

        url = url.strip()

        if not url:
            return "L'adresse du site est vide."

        if not (
            url.startswith("http://")
            or url.startswith("https://")
        ):
            url = "https://" + url

        opened = webbrowser.open(url)

        if not opened:
            return f"Impossible d'ouvrir le site : {url}"

        return f"Site ouvert : {url}"

    @staticmethod
    def rechercher_youtube(recherche):

        url = (
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote_plus(recherche)
        )

        return BrowserTools.ouvrir_site(url)

    @staticmethod
    def recherche_web(recherche):

        url = (
            "https://www.google.com/search?q="
            + urllib.parse.quote_plus(recherche)
        )

        return BrowserTools.ouvrir_site(url)
