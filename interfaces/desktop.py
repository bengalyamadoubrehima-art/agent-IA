import sys
import threading

from PySide6.QtCore import QObject, Qt, Signal, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tools.pc import PCAgent


class ConfirmationDialog(QObject):
    """
    Affiche les demandes de confirmation dans une boîte
    de dialogue, même quand elles viennent du thread IA.
    """

    requested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
        self.result = False

        self.requested.connect(
            self._ask,
            Qt.BlockingQueuedConnection
        )

    def _ask(self, tool_name, arguments):
        details = "\n".join(
            f"{key} : {value}"
            for key, value in (arguments or {}).items()
        )

        answer = QMessageBox.question(
            self.parent,
            "JARVIS — Confirmation",
            f"Autoriser l'action « {tool_name} » ?\n\n{details}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        self.result = answer == QMessageBox.Yes

    def ask(self, tool_name, arguments):
        if threading.current_thread() is threading.main_thread():
            self._ask(tool_name, arguments)
        else:
            self.requested.emit(tool_name, arguments)

        return self.result


class PhoneStatusWorker(QThread):
    checked = Signal(bool)

    def __init__(self, phone):
        super().__init__()
        self.phone = phone

    def run(self):
        self.checked.emit(self.phone.est_connecte())


class AIWorker(QThread):
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, orchestrator, message):
        super().__init__()
        self.orchestrator = orchestrator
        self.message = message

    def run(self):
        try:
            response = self.orchestrator.handle(self.message)
            self.finished.emit(response)
        except Exception as error:
            self.failed.emit(str(error))


class JarvisWindow(QMainWindow):

    def __init__(self, orchestrator, voice=None, phone=None):
        super().__init__()

        self.orchestrator = orchestrator
        self.voice = voice
        self.phone = phone
        self.phone_worker = None
        self.worker = None
        self.pulse_state = False

        self.setWindowTitle("JARVIS")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)

        self.build_ui()
        self.apply_style()
        self.start_effects()
        self.start_phone_status()

    # =========================================================
    # INTERFACE
    # =========================================================

    def build_ui(self):

        central = QWidget()
        central.setObjectName("background")

        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        root.addWidget(self.create_sidebar())
        root.addWidget(self.create_center(), 1)
        root.addWidget(self.create_right_panel())

    # =========================================================
    # SIDEBAR
    # =========================================================

    def create_sidebar(self):

        panel = QFrame()
        panel.setObjectName("sidebar")

        panel.setFixedWidth(235)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(8)

        logo = QLabel("JARVIS")
        logo.setObjectName("logo")

        subtitle = QLabel(
            "PERSONAL AI SYSTEM"
        )
        subtitle.setObjectName("subtitle")

        version = QLabel("CORE // 01.0")
        version.setObjectName("version")

        layout.addWidget(logo)
        layout.addWidget(subtitle)
        layout.addSpacing(4)
        layout.addWidget(version)

        line = QFrame()
        line.setObjectName("separator")
        line.setFixedHeight(1)

        layout.addSpacing(12)
        layout.addWidget(line)
        layout.addSpacing(12)

        self.nav_buttons = []

        items = [
            ("◉", "Conversation"),
            ("◈", "Mémoire"),
            ("▣", "PC"),
            ("▯", "Téléphone"),
            ("◎", "Internet"),
            ("⚒", "Outils"),
            ("⚙", "Paramètres"),
        ]

        for icon, text in items:

            button = QPushButton(
                f"   {icon}    {text}"
            )

            button.setObjectName(
                "navButton"
            )

            button.setCursor(
                Qt.PointingHandCursor
            )

            layout.addWidget(button)

            self.nav_buttons.append(button)

        layout.addStretch()

        online_panel = QFrame()
        online_panel.setObjectName(
            "onlinePanel"
        )

        online_layout = QVBoxLayout(
            online_panel
        )

        online_layout.setContentsMargins(
            12, 12, 12, 12
        )

        online = QLabel(
            "●  JARVIS ONLINE"
        )

        online.setObjectName(
            "onlineText"
        )

        online_detail = QLabel(
            "Tous les systèmes opérationnels"
        )

        online_detail.setObjectName(
            "onlineDetail"
        )

        online_layout.addWidget(online)
        online_layout.addWidget(
            online_detail
        )

        layout.addWidget(online_panel)

        return panel

    # =========================================================
    # CENTRE
    # =========================================================

    def create_center(self):

        center = QWidget()

        layout = QVBoxLayout(center)

        layout.setContentsMargins(
            0, 0, 0, 0
        )

        layout.setSpacing(12)

        layout.addWidget(
            self.create_top_bar()
        )

        layout.addWidget(
            self.create_hero()
        )

        layout.addWidget(
            self.create_conversation(),
            1
        )

        layout.addWidget(
            self.create_input()
        )

        return center

    # =========================================================
    # TOP BAR
    # =========================================================

    def create_top_bar(self):

        bar = QFrame()
        bar.setObjectName("topBar")

        layout = QHBoxLayout(bar)

        layout.setContentsMargins(
            18, 8, 18, 8
        )

        signal = QLabel(
            "▂▅▇▅▂  ÉCOUTER  ·  COMPRENDRE  ·  AGIR"
        )

        signal.setObjectName(
            "signal"
        )

        layout.addWidget(signal)

        layout.addStretch()

        notification = QLabel("◌")

        notification.setObjectName(
            "topIcon"
        )

        layout.addWidget(notification)

        connection = QLabel(
            "●  CONNECTÉ"
        )

        connection.setObjectName(
            "connection"
        )

        layout.addWidget(connection)

        return bar

    # =========================================================
    # HERO
    # =========================================================

    def create_hero(self):

        hero = QFrame()
        hero.setObjectName("hero")

        layout = QHBoxLayout(hero)

        layout.setContentsMargins(
            28, 24, 28, 24
        )

        text_layout = QVBoxLayout()

        label = QLabel(
            "JARVIS // NEURAL INTERFACE"
        )

        label.setObjectName(
            "heroLabel"
        )

        title = QLabel(
            "Bonjour."
        )

        title.setObjectName(
            "heroTitle"
        )

        description = QLabel(
            "Ton système personnel est prêt."
        )

        description.setObjectName(
            "heroDescription"
        )

        quote = QLabel(
            "« Écouter. Comprendre. Exécuter. »"
        )

        quote.setObjectName(
            "quote"
        )

        text_layout.addWidget(label)
        text_layout.addSpacing(8)
        text_layout.addWidget(title)
        text_layout.addWidget(
            description
        )
        text_layout.addSpacing(12)
        text_layout.addWidget(quote)

        layout.addLayout(
            text_layout
        )

        layout.addStretch()

        # Core visuel
        core = QFrame()
        core.setObjectName("coreVisual")

        core.setFixedSize(150, 150)

        core_layout = QVBoxLayout(core)

        core_layout.setAlignment(
            Qt.AlignCenter
        )

        core_icon = QLabel("◉")

        core_icon.setObjectName(
            "coreIcon"
        )

        core_status = QLabel(
            "NEURAL CORE"
        )

        core_status.setObjectName(
            "coreStatus"
        )

        self.core_icon = core_icon

        core_layout.addWidget(
            core_icon,
            alignment=Qt.AlignCenter
        )

        core_layout.addWidget(
            core_status,
            alignment=Qt.AlignCenter
        )

        layout.addWidget(core)

        return hero

    # =========================================================
    # CONVERSATION
    # =========================================================

    def create_conversation(self):

        frame = QFrame()
        frame.setObjectName(
            "conversationFrame"
        )

        outer = QVBoxLayout(frame)

        outer.setContentsMargins(
            12, 12, 12, 12
        )

        header = QHBoxLayout()

        title = QLabel(
            "CONVERSATION"
        )

        title.setObjectName(
            "sectionTitle"
        )

        state = QLabel(
            "● CANAL ACTIF"
        )

        state.setObjectName(
            "sectionState"
        )

        header.addWidget(title)
        header.addStretch()
        header.addWidget(state)

        outer.addLayout(header)

        self.scroll = QScrollArea()

        self.scroll.setWidgetResizable(
            True
        )

        self.scroll.setFrameShape(
            QFrame.NoFrame
        )

        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        self.messages_container = QWidget()

        self.messages_layout = QVBoxLayout(
            self.messages_container
        )

        self.messages_layout.setContentsMargins(
            8, 15, 8, 15
        )

        self.messages_layout.setSpacing(
            12
        )

        self.messages_layout.addStretch()

        self.scroll.setWidget(
            self.messages_container
        )

        outer.addWidget(
            self.scroll
        )

        return frame

    # =========================================================
    # RIGHT PANEL
    # =========================================================

    def create_right_panel(self):

        panel = QWidget()

        panel.setFixedWidth(255)

        layout = QVBoxLayout(panel)

        layout.setContentsMargins(
            0, 0, 0, 0
        )

        layout.setSpacing(12)

        layout.addWidget(
            self.create_system_panel()
        )

        layout.addWidget(
            self.create_connections_panel()
        )

        layout.addWidget(
            self.create_tools_panel()
        )

        layout.addStretch()

        return panel

    # =========================================================
    # SYSTEM PANEL
    # =========================================================

    def create_system_panel(self):

        panel = QFrame()

        panel.setObjectName(
            "sidePanel"
        )

        layout = QVBoxLayout(panel)

        layout.setContentsMargins(
            16, 16, 16, 16
        )

        title = QLabel(
            "◈  SYSTÈME"
        )

        title.setObjectName(
            "panelTitle"
        )

        layout.addWidget(title)

        layout.addSpacing(8)

        self.cpu_label = self.create_metric(
            layout,
            "CPU",
            "ACTIF"
        )

        self.ram_label = self.create_metric(
            layout,
            "RAM",
            "ACTIF"
        )

        self.disk_label = self.create_metric(
            layout,
            "DISQUE",
            "ACTIF"
        )

        return panel

    def create_metric(
        self,
        layout,
        name,
        value
    ):

        row = QHBoxLayout()

        label = QLabel(name)

        label.setObjectName(
            "metricName"
        )

        value_label = QLabel(
            value
        )

        value_label.setObjectName(
            "metricValue"
        )

        row.addWidget(label)
        row.addStretch()
        row.addWidget(
            value_label
        )

        layout.addLayout(row)

        bar = QFrame()

        bar.setObjectName(
            "metricBar"
        )

        bar.setFixedHeight(4)

        layout.addWidget(bar)

        layout.addSpacing(10)

        return value_label

    # =========================================================
    # CONNECTIONS
    # =========================================================

    def create_connections_panel(self):

        panel = QFrame()

        panel.setObjectName(
            "sidePanel"
        )

        layout = QVBoxLayout(panel)

        layout.setContentsMargins(
            16, 16, 16, 16
        )

        title = QLabel(
            "◉  CONNEXIONS"
        )

        title.setObjectName(
            "panelTitle"
        )

        layout.addWidget(title)

        layout.addSpacing(10)

        self.add_connection(
            layout,
            "▣",
            "PC",
            "Connecté"
        )

        self.phone_status = self.add_connection(
            layout,
            "▯",
            "Téléphone",
            "En attente"
        )

        self.add_connection(
            layout,
            "◎",
            "Internet",
            "En ligne"
        )

        return panel

    def add_connection(
        self,
        layout,
        icon,
        name,
        status
    ):

        row = QHBoxLayout()

        icon_label = QLabel(
            icon
        )

        icon_label.setObjectName(
            "connectionIcon"
        )

        name_label = QLabel(
            name
        )

        name_label.setObjectName(
            "connectionName"
        )

        status_label = QLabel(
            f"● {status}"
        )

        status_label.setObjectName(
            "connectionStatus"
        )

        row.addWidget(icon_label)
        row.addWidget(name_label)
        row.addStretch()
        row.addWidget(status_label)

        layout.addLayout(row)

        layout.addSpacing(8)

        return status_label

    def start_phone_status(self):

        if self.phone is None:
            return

        self.phone_timer = QTimer(self)
        self.phone_timer.timeout.connect(
            self.check_phone
        )
        self.phone_timer.start(30000)

        self.check_phone()

    def check_phone(self):

        if self.phone_worker is not None and self.phone_worker.isRunning():
            return

        self.phone_worker = PhoneStatusWorker(
            self.phone
        )
        self.phone_worker.checked.connect(
            self.on_phone_status
        )
        self.phone_worker.start()

    def on_phone_status(self, connected):

        self.phone_status.setText(
            "● Connecté" if connected else "● Déconnecté"
        )

    # =========================================================
    # TOOLS PANEL
    # =========================================================

    def create_tools_panel(self):

        panel = QFrame()

        panel.setObjectName(
            "sidePanel"
        )

        layout = QVBoxLayout(panel)

        layout.setContentsMargins(
            16, 16, 16, 16
        )

        title = QLabel(
            "⚒  ACCÈS RAPIDE"
        )

        title.setObjectName(
            "panelTitle"
        )

        layout.addWidget(title)

        layout.addSpacing(10)

        tools = [
            "VS Code",
            "Navigateur",
            "Explorateur",
            "Terminal",
        ]

        for name in tools:

            button = QPushButton(
                f"▣  {name}"
            )

            button.setObjectName(
                "quickButton"
            )

            button.setCursor(
                Qt.PointingHandCursor
            )

            button.clicked.connect(
                lambda _=False, app=name:
                    PCAgent.ouvrir_application(app)
            )

            layout.addWidget(
                button
            )

        return panel

    # =========================================================
    # INPUT
    # =========================================================

    def create_input(self):

        frame = QFrame()

        frame.setObjectName(
            "inputArea"
        )

        layout = QVBoxLayout(frame)

        layout.setContentsMargins(
            12, 12, 12, 10
        )

        input_row = QHBoxLayout()

        self.input = QLineEdit()

        self.input.setPlaceholderText(
            "Écris une commande à JARVIS..."
        )

        self.input.returnPressed.connect(
            self.send_message
        )

        input_row.addWidget(
            self.input
        )

        self.voice_button = QPushButton(
            "🎙"
        )

        self.voice_button.setObjectName(
            "voiceButton"
        )

        self.voice_button.setFixedSize(
            48, 44
        )

        self.voice_button.clicked.connect(
            self.voice_command
        )

        input_row.addWidget(
            self.voice_button
        )

        send = QPushButton(
            "➤"
        )

        send.setObjectName(
            "sendButton"
        )

        send.setFixedSize(
            48, 44
        )

        send.clicked.connect(
            self.send_message
        )

        input_row.addWidget(send)

        layout.addLayout(
            input_row
        )

        modes = QHBoxLayout()

        for text in [
            "▤  Texte",
            "♩  Voix",
            "◉  Vision",
            "↗  Fichiers",
            "•••  Plus",
        ]:

            button = QPushButton(text)

            button.setObjectName(
                "modeButton"
            )

            modes.addWidget(
                button
            )

        layout.addLayout(modes)

        return frame

    # =========================================================
    # MESSAGES
    # =========================================================

    def add_message(
        self,
        sender,
        text,
        user=False
    ):

        bubble = QFrame()

        bubble.setObjectName(
            "userBubble"
            if user
            else "jarvisBubble"
        )

        bubble.setMaximumWidth(
            850
        )

        layout = QVBoxLayout(
            bubble
        )

        layout.setContentsMargins(
            16, 12, 16, 12
        )

        sender_label = QLabel(
            sender
        )

        sender_label.setObjectName(
            "messageSender"
        )

        message = QLabel(
            text
        )

        message.setWordWrap(
            True
        )

        message.setObjectName(
            "messageText"
        )

        layout.addWidget(
            sender_label
        )

        layout.addWidget(
            message
        )

        row = QHBoxLayout()

        if user:
            row.addStretch()
            row.addWidget(
                bubble
            )
        else:
            row.addWidget(
                bubble
            )
            row.addStretch()

        self.messages_layout.insertLayout(
            self.messages_layout.count() - 1,
            row
        )

        self.scroll_to_bottom()

    def scroll_to_bottom(self):

        bar = (
            self.scroll
            .verticalScrollBar()
        )

        bar.setValue(
            bar.maximum()
        )

    # =========================================================
    # AI
    # =========================================================

    def send_message(self):

        message = (
            self.input
            .text()
            .strip()
        )

        if not message:
            return

        if self.worker is not None:
            return

        self.input.clear()

        self.add_message(
            "TOI",
            message,
            user=True
        )

        self.set_state(
            "● JARVIS RÉFLÉCHIT"
        )

        self.input.setEnabled(
            False
        )

        self.worker = AIWorker(
            self.orchestrator,
            message
        )

        self.worker.finished.connect(
            self.on_ai_response
        )

        self.worker.failed.connect(
            self.on_ai_error
        )

        self.worker.start()

    def on_ai_response(
        self,
        response
    ):

        self.add_message(
            "JARVIS",
            response,
            user=False
        )

        self.set_state(
            "● SYSTÈME PRÊT"
        )

        self.input.setEnabled(
            True
        )

        self.input.setFocus()

        self.worker = None

    def on_ai_error(
        self,
        error
    ):

        self.add_message(
            "JARVIS",
            f"Erreur : {error}",
            user=False
        )

        self.set_state(
            "● ERREUR"
        )

        self.input.setEnabled(
            True
        )

        self.input.setFocus()

        self.worker = None

    # =========================================================
    # VOICE
    # =========================================================

    def voice_command(self):

        if self.voice is None:

            self.add_message(
                "JARVIS",
                "Interface vocale indisponible.",
                user=False
            )

            return

        self.set_state(
            "● ÉCOUTE EN COURS"
        )

        self.voice.process_once()

        self.set_state(
            "● SYSTÈME PRÊT"
        )

    def set_state(self, text):

        self.state_label.setText(
            text
        )

    # =========================================================
    # EFFECTS
    # =========================================================

    def start_effects(self):

        self.effect_timer = QTimer(
            self
        )

        self.effect_timer.timeout.connect(
            self.animate_core
        )

        self.effect_timer.start(
            900
        )

    def animate_core(self):

        self.pulse_state = (
            not self.pulse_state
        )

        if self.pulse_state:

            self.core_icon.setText(
                "◉"
            )

        else:

            self.core_icon.setText(
                "◎"
            )

    # =========================================================
    # STYLE
    # =========================================================

    def apply_style(self):

        self.setStyleSheet(
            """
            * {
                font-family: "Segoe UI";
            }

            QMainWindow,
            #background {
                background: #050912;
                color: #eaf4ff;
            }

            /* SIDEBAR */

            #sidebar {
                background: #070d17;
                border: 1px solid #11233a;
                border-radius: 18px;
            }

            #logo {
                color: #f5fbff;
                font-size: 30px;
                font-weight: 800;
                letter-spacing: 3px;
            }

            #subtitle {
                color: #2baeff;
                font-size: 9px;
                letter-spacing: 2px;
            }

            #version {
                color: #43556e;
                font-size: 10px;
            }

            #separator {
                background: #13263d;
            }

            #navButton {
                background: transparent;
                color: #7f94ad;
                border: 1px solid transparent;
                border-radius: 10px;
                padding: 11px;
                text-align: left;
                font-size: 13px;
            }

            #navButton:hover {
                background: #0b1b2d;
                color: #49caff;
                border: 1px solid #123b5a;
            }

            #navButton:pressed {
                background: #0e2940;
            }

            #onlinePanel {
                background: #071b18;
                border: 1px solid #0d5948;
                border-radius: 12px;
            }

            #onlineText {
                color: #36e39b;
                font-size: 11px;
                font-weight: 700;
            }

            #onlineDetail {
                color: #527c72;
                font-size: 9px;
            }

            /* TOP BAR */

            #topBar {
                background: #070f1b;
                border: 1px solid #112a43;
                border-radius: 13px;
                min-height: 34px;
            }

            #signal {
                color: #279ddc;
                font-size: 10px;
                letter-spacing: 2px;
            }

            #topIcon {
                color: #5f7994;
                font-size: 18px;
            }

            #connection {
                color: #37e59d;
                font-size: 10px;
                font-weight: 700;
            }

            /* HERO */

            #hero {
                background:
                    qlineargradient(
                        x1: 0,
                        y1: 0,
                        x2: 1,
                        y2: 1,
                        stop: 0 #081321,
                        stop: 0.55 #07101e,
                        stop: 1 #0a1a2b
                    );

                border: 1px solid #15517a;
                border-radius: 18px;
            }

            #heroLabel {
                color: #27b7ff;
                font-size: 10px;
                letter-spacing: 2px;
                font-weight: 700;
            }

            #heroTitle {
                color: #f5fbff;
                font-size: 34px;
                font-weight: 700;
            }

            #heroDescription {
                color: #77a4c7;
                font-size: 14px;
            }

            #quote {
                color: #4f7695;
                font-size: 12px;
                font-style: italic;
            }

            #coreVisual {
                background:
                    qradialgradient(
                        cx: 0.5,
                        cy: 0.5,
                        radius: 0.5,
                        stop: 0 #103c5c,
                        stop: 0.45 #082138,
                        stop: 1 #050c16
                    );

                border: 1px solid #20baff;
                border-radius: 75px;
            }

            #coreIcon {
                color: #4bd5ff;
                font-size: 58px;
            }

            #coreStatus {
                color: #2e9dc8;
                font-size: 8px;
                letter-spacing: 2px;
            }

            /* CONVERSATION */

            #conversationFrame {
                background: #060d17;
                border: 1px solid #102943;
                border-radius: 16px;
            }

            #sectionTitle {
                color: #d7edff;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 2px;
            }

            #sectionState {
                color: #27c992;
                font-size: 9px;
            }

            #jarvisBubble {
                background: #091523;
                border: 1px solid #164362;
                border-radius: 13px;
            }

            #userBubble {
                background: #0b2034;
                border: 1px solid #17547c;
                border-radius: 13px;
            }

            #messageSender {
                color: #2bb7f4;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            #messageText {
                color: #dcecff;
                font-size: 13px;
            }

            /* RIGHT PANELS */

            #sidePanel {
                background: #070f19;
                border: 1px solid #112941;
                border-radius: 15px;
            }

            #panelTitle {
                color: #48c7ff;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
            }

            #metricName {
                color: #7b91a8;
                font-size: 10px;
            }

            #metricValue {
                color: #d9f5ff;
                font-size: 10px;
            }

            #metricBar {
                background:
                    qlineargradient(
                        x1: 0,
                        y1: 0,
                        x2: 1,
                        y2: 0,
                        stop: 0 #19b8ff,
                        stop: 0.55 #0d6795,
                        stop: 1 #102033
                    );

                border-radius: 2px;
            }

            #connectionIcon {
                color: #39c6ff;
                font-size: 13px;
            }

            #connectionName {
                color: #c9d9e8;
                font-size: 11px;
            }

            #connectionStatus {
                color: #3ce2a0;
                font-size: 9px;
            }

            #quickButton {
                background: #081625;
                border: 1px solid #163b58;
                border-radius: 9px;
                color: #8fcdf0;
                padding: 9px;
                text-align: left;
                font-size: 10px;
            }

            #quickButton:hover {
                background: #0d263d;
                border: 1px solid #21bfff;
                color: #ffffff;
            }

            /* INPUT */

            #inputArea {
                background: #070f1a;
                border: 1px solid #17486b;
                border-radius: 15px;
            }

            QLineEdit {
                background: transparent;
                border: none;
                color: #effaff;
                font-size: 14px;
                padding: 8px;
            }

            QLineEdit::placeholder {
                color: #40586e;
            }

            #voiceButton {
                background: #0b1d2e;
                border: 1px solid #185075;
                border-radius: 10px;
                color: #54cfff;
                font-size: 17px;
            }

            #voiceButton:hover {
                background: #10304a;
                border: 1px solid #29c6ff;
            }

            #sendButton {
                background: #0ca9ec;
                border: none;
                border-radius: 10px;
                color: #ffffff;
                font-size: 18px;
                font-weight: 700;
            }

            #sendButton:hover {
                background: #27c5ff;
            }

            #modeButton {
                background: transparent;
                border: 1px solid #122c44;
                border-radius: 8px;
                color: #58738c;
                padding: 7px 12px;
                font-size: 9px;
            }

            #modeButton:hover {
                background: #0a1c2d;
                color: #4bcaff;
                border: 1px solid #1b638c;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 7px;
            }

            QScrollBar::handle:vertical {
                background: #173b58;
                border-radius: 3px;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )


def run_desktop(
    orchestrator,
    voice=None,
    confirmation=None,
    phone=None
):

    app = QApplication.instance()

    if app is None:
        app = QApplication(
            sys.argv
        )

    window = JarvisWindow(
        orchestrator=orchestrator,
        voice=voice,
        phone=phone
    )

    if confirmation is not None:
        dialog = ConfirmationDialog(window)
        confirmation.set_handler(dialog.ask)
        window.confirmation_dialog = dialog

    window.show()

    return app.exec()