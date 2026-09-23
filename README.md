# JARVIS

Assistant personnel qui pilote ton **PC**, ton **téléphone Android** et ta
boîte **Gmail**, à la voix ou au clavier.

| Tu dis… | JARVIS… |
| --- | --- |
| « Ouvre le gestionnaire de fichiers » | ouvre l'explorateur de fichiers du PC |
| « Ouvre VS Code », « ouvre Spotify », « ouvre Word » | lance l'application installée sur le PC |
| « Ouvre YouTube », « cherche lofi sur YouTube » | ouvre YouTube dans le navigateur |
| « Ouvre YouTube sur mon téléphone » | lance l'application YouTube du téléphone |
| « Envoie “j'arrive” à Maman sur WhatsApp » | envoie le message WhatsApp (après confirmation) |
| « Envoie un SMS à Paul » | envoie un SMS |
| « Appelle Jean-Pierre », « raccroche » | lance / termine l'appel sur le téléphone |
| « Lis mes derniers e-mails », « ai-je des mails de ma banque ? » | lit et résume Gmail |
| « Réponds à Paul par e-mail que… » | envoie l'e-mail (après confirmation) |

Les actions sensibles (messages, appels, envoi d'e-mails) demandent toujours
une confirmation (boîte de dialogue dans la fenêtre JARVIS).

## L'interface

Interface HUD sombre inspirée de la maquette « Jarvis UI » :

- **Barre du haut** : état de JARVIS, date et heure.
- **Diagnostics système** : processeur, mémoire, débit réseau et stockage, en temps réel.
- **Journal d'activité** : chaque action réellement exécutée par JARVIS.
- **Noyau central** : ses anneaux accélèrent quand JARVIS réfléchit ou agit, et
  virent au rouge en cas d'erreur.
- **Conversation** et **barre de commande** : tape ta demande puis Entrée, ou
  clique sur le micro (raccourci **Ctrl+Espace**) pour parler.
- **Modules actifs** : Ordinateur, Téléphone, Gmail et Voix s'allument quand ils
  sont prêts. Clique sur un module pour revérifier les connexions.
- **Signal audio** : s'anime pendant l'écoute et pendant que JARVIS parle.

---

## 1. Installation sur le PC

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS : source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # Linux/macOS : cp .env.example .env
```

Renseigne au minimum `OPENAI_API_KEY` dans `.env`, puis :

```bash
python main.py
```

Sur le PC, l'ouverture d'applications fonctionne immédiatement : JARVIS
cherche dans le menu Démarrer (y compris les applications du Microsoft Store)
sous Windows, dans les fichiers `.desktop` sous Linux, et dans `/Applications`
sous macOS.

## 2. Connecter le téléphone Android

JARVIS contrôle le téléphone avec **ADB** (l'outil officiel Android), depuis le
PC. Il n'y a aucune application à installer sur le téléphone.

1. **Installe ADB sur le PC** : télécharge les
   [SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools),
   décompresse-les et ajoute le dossier au `PATH` (ou mets le chemin complet de
   `adb.exe` dans `ADB_PATH` du `.env`).
2. **Active les options développeur** sur le téléphone : *Paramètres → À propos
   du téléphone → appuie 7 fois sur « Numéro de build »*.
3. **Connexion sans fil (Android 11 et plus)**, téléphone et PC sur le même Wi-Fi :
   - *Options pour les développeurs → Débogage sans fil* → active-le ;
   - touche *Associer l'appareil avec un code d'association* ; puis sur le PC :
     ```bash
     adb pair 192.168.1.42:37123      # IP:port et code affichés sur le téléphone
     ```
   - note l'adresse affichée en haut de l'écran *Débogage sans fil*
     (ex. `192.168.1.42:41234`) et mets-la dans `.env` :
     ```
     ANDROID_ADB_SERIAL=192.168.1.42:41234
     ```
   Ce port change au redémarrage du téléphone : il faudra alors mettre à jour
   `ANDROID_ADB_SERIAL`, sans refaire l'association.

   **Ou en USB** : active *Débogage USB*, branche le câble, accepte l'autorisation
   sur le téléphone et laisse `ANDROID_ADB_SERIAL` vide.
4. Vérifie avec `adb devices`. Le téléphone doit apparaître avec l'état `device`.
5. Mets l'indicatif de ton pays dans `PHONE_COUNTRY_CODE` (ex. `33` France,
   `223` Mali). WhatsApp en a besoin pour les numéros enregistrés sans `+`.

Le module **TÉLÉPHONE** s'allume dans la fenêtre JARVIS.

> **Bon à savoir**
> - Pour WhatsApp et les SMS, JARVIS ouvre la conversation puis appuie sur
>   « Envoyer » à ta place. Le téléphone doit donc être **déverrouillé** (JARVIS
>   allume l'écran mais ne peut pas saisir ton code).
> - Les contacts sont lus dans le répertoire du téléphone : dis simplement le
>   nom (« Maman », « Jean-Pierre »). JARVIS tolère les fautes légères.
> - WhatsApp Business : `WHATSAPP_PACKAGE=com.whatsapp.w4b`.
> - Ça ne marche pas avec un iPhone : iOS ne permet pas ce contrôle.

## 3. Connecter Gmail

JARVIS utilise IMAP/SMTP avec un **mot de passe d'application** Google (plus
simple qu'une application OAuth).

1. Active la **validation en deux étapes** sur ton compte Google.
2. Crée un mot de passe d'application : <https://myaccount.google.com/apppasswords>
   (nom : « JARVIS »). Google affiche 16 lettres.
3. Dans `.env` :
   ```
   GMAIL_ADDRESS=ton.adresse@gmail.com
   GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
   ```

La lecture n'altère rien : les e-mails lus par JARVIS restent « non lus ».

---

## Architecture

```
main.py                   assemble tous les modules et lance l'interface
core/                     IA (outils OpenAI), planificateur, mémoire, permissions, confirmation
interfaces/desktop.py     interface HUD PySide6 (conversation, voix, confirmations, diagnostics)
interfaces/assets/fonts/  polices Orbitron et Space Mono (licence SIL OFL)
interfaces/voice.py       enregistrement, transcription et synthèse vocale
tools/pc.py               fichiers, dossiers et applications du PC
tools/browser.py          sites, recherches Google / YouTube
tools/registry.py         déclaration de tous les outils disponibles pour l'IA
services/android_adb.py   téléphone : applications, contacts, WhatsApp, SMS, appels
services/gmail.py         Gmail : lecture, recherche, envoi
mobile/server.py          serveur WebSocket (port 8765) pour discuter avec JARVIS depuis un client mobile
```

Les droits de chaque outil (autorisé, confirmation, bloqué) se règlent dans
`core/permissions.py`.
