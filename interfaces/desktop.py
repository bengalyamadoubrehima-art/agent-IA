import math
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import (
    QDate,
    QLocale,
    QObject,
    QPointF,
    QRectF,
    Qt,
    QThread,
    QTime,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QShortcut,
)
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
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    import psutil
except ImportError:
    psutil = None


# =============================================================
# THÈME
# =============================================================

FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"

ACCENT = QColor("#5ee7ff")
BRIGHT = "#eafcff"
TEXT = "#cfeff5"
MUTED = "rgba(207,239,245,0.55)"
BACKGROUND = "#050b0f"

DISPLAY_FONT = "Orbitron"
MONO_FONT = "Space Mono"

STATE_LABELS = {
    "idle": ("SYSTÈME OPÉRATIONNEL", "VEILLE"),
    "listening": ("ÉCOUTE EN COURS", "ÉCOUTE"),
    "thinking": ("ANALYSE EN COURS", "ANALYSE"),
    "executing": ("EXÉCUTION EN COURS", "ACTION"),
    "speaking": ("RÉPONSE VOCALE", "PAROLE"),
    "error": ("ANOMALIE DÉTECTÉE", "ERREUR"),
}

TOOL_LABELS = {
    "ouvrir_site": "Ouverture d'un site",
    "rechercher_youtube": "Recherche YouTube",
    "recherche_web": "Recherche web",
    "ouvrir_application": "Ouverture d'une application",
    "lister_applications": "Inventaire des applications",
    "ouvrir_dossier": "Ouverture d'un dossier",
    "ouvrir_dossier_special": "Ouverture d'un dossier",
    "ouvrir_fichier": "Ouverture d'un fichier",
    "rechercher_fichier": "Recherche de fichier",
    "envoyer_message": "Envoi d'un message",
    "appeler_contact": "Appel téléphonique",
    "raccrocher": "Fin d'appel",
    "envoyer_email": "Envoi d'un e-mail",
    "lire_emails": "Lecture de Gmail",
    "rechercher_emails": "Recherche dans Gmail",
    "lire_email": "Lecture d'un e-mail",
    "ouvrir_application_telephone": "Application téléphone",
    "ouvrir_lien_telephone": "Lien sur le téléphone",
    "rechercher_youtube_telephone": "YouTube sur le téléphone",
    "rechercher_contact": "Recherche de contact",
    "statut_telephone": "État du téléphone",
    "memoriser": "Mémorisation",
    "rechercher_memoire": "Recherche en mémoire",
}


def accent(alpha=1.0):
    color = QColor(ACCENT)
    color.setAlphaF(alpha)
    return color


def load_fonts():
    global DISPLAY_FONT, MONO_FONT

    families = {}

    for path in FONTS_DIR.glob("*.ttf"):
        font_id = QFontDatabase.addApplicationFont(str(path))

        for family in QFontDatabase.applicationFontFamilies(font_id):
            families[family.lower()] = family

    DISPLAY_FONT = families.get("orbitron", "Consolas")
    MONO_FONT = families.get("space mono", "Consolas")


def font(family, size, weight=QFont.Normal, spacing=0.0):
    f = QFont(family)
    f.setPixelSize(size)
    f.setWeight(weight)

    # Orbitron est une police variable : on règle aussi son axe
    # de graisse quand Qt le permet (Qt 6.7+).
    if family == DISPLAY_FONT and hasattr(QFont, "setVariableAxis"):
        f.setVariableAxis(QFont.Tag("wght"), float(getattr(weight, "value", weight)))

    if spacing:
        f.setLetterSpacing(QFont.AbsoluteSpacing, spacing)

    return f


# =============================================================
# PONTS ENTRE LES THREADS ET L'INTERFACE
# =============================================================

class UiBridge(QObject):
    """
    Relaie les événements de JARVIS (émis depuis n'importe
    quel thread) vers le thread de l'interface.
    """

    event = Signal(str, object)

    EVENTS = [
        "state.changed",
        "tool.started",
        "tool.finished",
        "tool.failed",
        "tool.blocked",
        "tool.denied",
        "voice.transcribed",
        "voice.speaking_started",
        "voice.error",
    ]

    def __init__(self, event_bus=None):
        super().__init__()

        if event_bus is None:
            return

        for name in self.EVENTS:
            event_bus.subscribe(
                name,
                lambda event, name=name: self.event.emit(name, event.data)
            )


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

        label = TOOL_LABELS.get(tool_name, tool_name)

        box = QMessageBox(self.parent)
        box.setWindowTitle("JARVIS — Confirmation")
        box.setIcon(QMessageBox.Question)
        box.setText(f"Autoriser : {label} ?\n\n{details}")

        allow = box.addButton("Autoriser", QMessageBox.AcceptRole)
        deny = box.addButton("Refuser", QMessageBox.RejectRole)
        box.setDefaultButton(deny)

        box.exec()

        self.result = box.clickedButton() is allow

    def ask(self, tool_name, arguments):
        if threading.current_thread() is threading.main_thread():
            self._ask(tool_name, arguments)
        else:
            self.requested.emit(tool_name, arguments)

        return self.result


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


class VoiceWorker(QThread):

    def __init__(self, voice):
        super().__init__()
        self.voice = voice

    def run(self):
        self.voice.process_once()


class StatusWorker(QThread):
    checked = Signal(dict)

    def __init__(self, phone=None, email=None, voice=None):
        super().__init__()
        self.phone = phone
        self.email = email
        self.voice = voice

    def run(self):
        self.checked.emit({
            "pc": True,
            "phone": bool(self.phone and self.phone.est_connecte()),
            "gmail": bool(self.email and self.email.is_configured()),
            "voice": bool(self.voice and self.voice.client),
        })


# =============================================================
# ÉLÉMENTS VISUELS
# =============================================================

class Backdrop(QWidget):
    """
    Fond radial, trame de balayage et bande lumineuse
    qui descend lentement sur l'écran.
    """

    SCAN_HEIGHT = 120
    SCAN_PERIOD = 6.0

    def __init__(self):
        super().__init__()
        self.setObjectName("backdrop")
        self.scan_y = 0
        self.cache = None

    def advance(self):
        height = self.height() + self.SCAN_HEIGHT
        phase = (time.monotonic() % self.SCAN_PERIOD) / self.SCAN_PERIOD
        old = self.scan_y
        self.scan_y = int(phase * height) - self.SCAN_HEIGHT

        top = min(old, self.scan_y)
        self.update(0, top - 2, self.width(), abs(self.scan_y - old) + self.SCAN_HEIGHT + 4)

    def resizeEvent(self, event):
        self.cache = None
        super().resizeEvent(event)

    def _render_cache(self):
        # Dégradé et trame ne changent qu'au redimensionnement :
        # on les dessine une fois dans une image.
        rect = self.rect()
        ratio = self.devicePixelRatioF()

        cache = QPixmap(rect.size() * ratio)
        cache.setDevicePixelRatio(ratio)

        painter = QPainter(cache)

        gradient = QRadialGradient(
            QPointF(rect.width() * 0.5, rect.height() * 0.38),
            max(rect.width(), rect.height()) * 0.75,
        )
        gradient.setColorAt(0.0, QColor("#0a1820"))
        gradient.setColorAt(0.62, QColor(BACKGROUND))
        gradient.setColorAt(1.0, QColor("#020507"))
        painter.fillRect(rect, gradient)

        painter.setPen(QPen(accent(0.025), 1))

        for y in range(0, rect.height(), 3):
            painter.drawLine(0, y, rect.width(), y)

        painter.end()

        return cache

    def paintEvent(self, event):
        if self.cache is None or self.cache.deviceIndependentSize().toSize() != self.size():
            self.cache = self._render_cache()

        painter = QPainter(self)
        clip = event.rect()

        painter.drawPixmap(clip, self.cache, QRectF(clip.topLeft() * self.cache.devicePixelRatio(), clip.size() * self.cache.devicePixelRatio()).toRect())

        band = QLinearGradient(0, self.scan_y, 0, self.scan_y + self.SCAN_HEIGHT)
        band.setColorAt(0.0, accent(0.0))
        band.setColorAt(0.5, accent(0.05))
        band.setColorAt(1.0, accent(0.0))
        painter.fillRect(0, self.scan_y, self.width(), self.SCAN_HEIGHT, band)


class PulseDot(QWidget):

    def __init__(self, size=10):
        super().__init__()
        self.setFixedSize(size + 16, size + 16)
        self.dot = size

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(time.monotonic() * math.tau / 2.4))
        center = QPointF(self.width() / 2, self.height() / 2)

        glow = QRadialGradient(center, self.width() / 2)
        glow.setColorAt(0.0, accent(0.6 * pulse))
        glow.setColorAt(1.0, accent(0.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, self.width() / 2, self.height() / 2)

        painter.setBrush(accent(pulse))
        painter.drawEllipse(center, self.dot / 2, self.dot / 2)


class HudCore(QWidget):
    """
    Noyau central : deux couronnes qui tournent en sens
    opposés, un halo pulsé et l'état de JARVIS au centre.
    """

    SPEED = {
        "idle": 1.0,
        "listening": 1.8,
        "thinking": 3.5,
        "executing": 3.5,
        "speaking": 2.0,
        "error": 0.4,
    }

    def __init__(self):
        super().__init__()
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.state = "idle"
        self.outer = 0.0
        self.inner = 0.0
        self.last = time.monotonic()

    def set_state(self, state):
        self.state = state
        self.update()

    def advance(self):
        now = time.monotonic()
        elapsed = now - self.last
        self.last = now

        speed = self.SPEED.get(self.state, 1.0)

        self.outer = (self.outer + elapsed * 360 / 18 * speed) % 360
        self.inner = (self.inner - elapsed * 360 / 9 * speed) % 360

        self.update()

    @staticmethod
    def _ring(painter, radius, width, color, dashes=None, cap=Qt.FlatCap):
        pen = QPen(color, width)
        pen.setCapStyle(cap)

        if dashes:
            pen.setDashPattern([length / width for length in dashes])

        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height())
        scale = side / 420

        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(scale, scale)

        error = self.state == "error"
        tint = QColor("#ff5e5e") if error else ACCENT

        def color(alpha):
            c = QColor(tint)
            c.setAlphaF(alpha)
            return c

        # Couronne extérieure (rotation lente)
        painter.save()
        painter.rotate(self.outer)
        self._ring(painter, 204, 1, color(0.18))
        self._ring(painter, 204, 2, color(1.0), [16, 620], Qt.RoundCap)
        self._ring(painter, 204, 2, color(0.5), [4, 40])
        painter.restore()

        # Couronnes intérieures (rotation inverse)
        painter.save()
        painter.rotate(self.inner)
        self._ring(painter, 160, 1, color(0.35), [2, 10])
        self._ring(painter, 128, 1.5, color(0.5), [40, 12])
        painter.restore()

        # Halo pulsé
        pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(time.monotonic() * math.tau / 2.4))
        halo = QRadialGradient(QPointF(0, 0), 75)
        halo.setColorAt(0.0, color(0.35 * pulse))
        halo.setColorAt(0.7, color(0.02 * pulse))
        halo.setColorAt(1.0, color(0.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QPointF(0, 0), 75, 75)

        # Lueur et disque central
        glow = QRadialGradient(QPointF(0, 0), 78)
        glow.setColorAt(0.55, color(0.35))
        glow.setColorAt(1.0, color(0.0))
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(0, 0), 78, 78)

        painter.setBrush(QColor(5, 11, 15, 220))
        painter.setPen(QPen(color(1.0), 1))
        painter.drawEllipse(QPointF(0, 0), 52, 52)

        # Texte
        _, word = STATE_LABELS.get(self.state, ("", self.state.upper()))

        painter.setPen(color(1.0))
        painter.setFont(font(DISPLAY_FONT, 11, QFont.Medium, 2))
        painter.drawText(QRectF(-52, -30, 104, 20), Qt.AlignCenter, "CORE")

        painter.setPen(QColor(BRIGHT))
        painter.setFont(font(DISPLAY_FONT, 14 if len(word) <= 6 else 12, QFont.Bold, 1))
        painter.drawText(QRectF(-52, -8, 104, 26), Qt.AlignCenter, word)


class Waveform(QWidget):
    """
    Barres du signal audio : calmes au repos, amples quand
    JARVIS écoute ou parle.
    """

    BARS = 18

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(90)
        self.active = False
        self.level = 0.25

    def advance(self):
        target = 1.0 if self.active else 0.25
        self.level += (target - self.level) * 0.08
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(accent(0.75))

        gap = 4
        width = (self.width() - gap * (self.BARS - 1)) / self.BARS
        now = time.monotonic()

        for i in range(self.BARS):
            base = (25 + (i * 37) % 70) / 100
            wave = 0.5 + 0.5 * math.sin((now / 1.1 - i * 0.07) * math.tau)
            ratio = 0.2 + 0.8 * wave
            height = max(3.0, self.height() * base * ratio * self.level)

            painter.drawRoundedRect(
                QRectF(i * (width + gap), self.height() - height, width, height),
                2, 2
            )


class BlinkCursor(QWidget):

    def __init__(self):
        super().__init__()
        self.setFixedSize(7, 14)

    def paintEvent(self, event):
        painter = QPainter(self)
        pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(time.monotonic() * math.tau / 2.4))
        painter.fillRect(self.rect(), accent(pulse))


class MicButton(QPushButton):

    def __init__(self):
        super().__init__()
        self.setFixedSize(36, 36)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Parler à JARVIS (Ctrl+Espace)")
        self.setAccessibleName("Parler à JARVIS")
        self.setObjectName("micButton")
        self.active = False

    def set_active(self, active):
        self.active = active
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        border = accent(1.0 if (self.active or self.underMouse()) else 0.45)
        painter.setPen(QPen(border, 1))
        painter.setBrush(accent(0.22 if self.active else 0.06))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)

        # Micro
        pen = QPen(accent(1.0), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        cx = self.width() / 2
        painter.drawRoundedRect(QRectF(cx - 4, 8, 8, 13), 4, 4)

        path = QPainterPath()
        path.moveTo(cx - 8, 16)
        path.cubicTo(cx - 8, 26, cx + 8, 26, cx + 8, 16)
        painter.drawPath(path)
        painter.drawLine(QPointF(cx, 24), QPointF(cx, 28))


# =============================================================
# PANNEAUX
# =============================================================

class Panel(QFrame):

    def __init__(self, title):
        super().__init__()
        self.setObjectName("panel")

        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 16, 16, 16)
        self.body.setSpacing(0)

        label = QLabel(title)
        label.setObjectName("panelTitle")
        label.setFont(font(MONO_FONT, 10, spacing=3))
        self.body.addWidget(label)
        self.body.addSpacing(14)


class MetricBar(QWidget):

    def __init__(self):
        super().__init__()
        self.setFixedHeight(4)
        self.ratio = 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        rect = QRectF(self.rect())
        painter.setBrush(accent(0.12))
        painter.drawRoundedRect(rect, 2, 2)

        painter.setBrush(accent(1.0))
        painter.drawRoundedRect(QRectF(0, 0, rect.width() * self.ratio, rect.height()), 2, 2)


class Metric(QWidget):

    def __init__(self, label):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(5)

        row = QHBoxLayout()

        name = QLabel(label)
        name.setObjectName("metricLabel")

        self.value = QLabel("—")
        self.value.setObjectName("metricValue")

        row.addWidget(name)
        row.addStretch()
        row.addWidget(self.value)

        self.bar = MetricBar()

        layout.addLayout(row)
        layout.addWidget(self.bar)

    def set_value(self, ratio, text):
        self.bar.ratio = max(0.0, min(1.0, ratio))
        self.value.setText(text)
        self.bar.update()


class ModuleRow(QPushButton):

    def __init__(self, label):
        super().__init__()
        self.setObjectName("module")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40)

        self.label = label
        self.on = False
        self.detail = ""
        self.setAccessibleName(label)

    def set_on(self, on, detail=""):
        self.on = on
        self.detail = detail
        self.setToolTip(detail)
        self.setProperty("on", on)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(QColor("#dff6fa"))
        painter.setFont(font(MONO_FONT, 12))
        painter.drawText(
            QRectF(12, 0, self.width() - 40, self.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.label
        )

        center = QPointF(self.width() - 18, self.height() / 2)
        dot = accent(1.0) if self.on else QColor(207, 239, 245, 64)

        if self.on:
            glow = QRadialGradient(center, 9)
            glow.setColorAt(0.0, accent(0.6))
            glow.setColorAt(1.0, accent(0.0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(center, 9, 9)

        painter.setPen(Qt.NoPen)
        painter.setBrush(dot)
        painter.drawEllipse(center, 4, 4)


# =============================================================
# FENÊTRE PRINCIPALE
# =============================================================

class JarvisWindow(QMainWindow):

    def __init__(
        self,
        orchestrator,
        voice=None,
        phone=None,
        email=None,
        event_bus=None,
        state_manager=None,
    ):
        super().__init__()

        self.orchestrator = orchestrator
        self.voice = voice
        self.phone = phone
        self.email = email
        self.state_manager = state_manager

        self.worker = None
        self.voice_worker = None
        self.status_worker = None

        self.net_last = None
        self.net_peak = 1024 * 1024

        self.setWindowTitle("J.A.R.V.I.S.")
        self.resize(1280, 800)
        self.setMinimumSize(1100, 700)

        self.build_ui()
        self.apply_style()

        self.bridge = UiBridge(event_bus)
        self.bridge.event.connect(self.on_event)

        self.log("Démarrage du système.")

        self.start_timers()

        state = (
            state_manager.state.value
            if state_manager
            else "idle"
        )
        self.set_state(state)

        self.input.setFocus()

    # ---------------------------------------------------------
    # CONSTRUCTION
    # ---------------------------------------------------------

    def build_ui(self):
        self.backdrop = Backdrop()
        self.setCentralWidget(self.backdrop)

        root = QVBoxLayout(self.backdrop)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self.build_top_bar())

        body = QHBoxLayout()
        body.setContentsMargins(32, 32, 32, 32)
        body.setSpacing(32)

        body.addWidget(self.build_left_column())
        body.addLayout(self.build_center(), 1)
        body.addWidget(self.build_right_column())

        root.addLayout(body, 1)

    def build_top_bar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setFixedHeight(64)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 32, 0)
        layout.setSpacing(6)

        self.top_dot = PulseDot()
        layout.addWidget(self.top_dot)

        title = QLabel("J.A.R.V.I.S.")
        title.setObjectName("brand")
        title.setFont(font(DISPLAY_FONT, 20, QFont.Black, 6))
        layout.addWidget(title)

        layout.addStretch()

        self.status_label = QLabel()
        self.date_label = QLabel()
        self.clock_label = QLabel()

        for label in (self.status_label, self.date_label, self.clock_label):
            label.setObjectName("topInfo")
            label.setFont(font(MONO_FONT, 11, spacing=2))
            layout.addWidget(label)
            layout.addSpacing(30)

        self.clock_label.setObjectName("topClock")

        return bar

    def build_left_column(self):
        column = QWidget()
        column.setFixedWidth(276)

        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        diagnostics = Panel("DIAGNOSTICS SYSTÈME")

        self.metrics = {
            key: Metric(label)
            for key, label in [
                ("cpu", "PROCESSEUR"),
                ("ram", "MÉMOIRE"),
                ("net", "RÉSEAU"),
                ("disk", "STOCKAGE"),
            ]
        }

        for metric in self.metrics.values():
            diagnostics.body.addWidget(metric)

        journal = Panel("JOURNAL D'ACTIVITÉ")

        self.log_layout = QVBoxLayout()
        self.log_layout.setSpacing(10)
        self.log_layout.setContentsMargins(0, 0, 0, 0)

        journal.body.addLayout(self.log_layout)
        journal.body.addStretch()

        layout.addWidget(diagnostics)
        layout.addWidget(journal, 1)

        return column

    def build_center(self):
        layout = QVBoxLayout()
        layout.setSpacing(16)

        self.core = HudCore()
        layout.addWidget(self.core, 5)

        self.feed_area = QScrollArea()
        self.feed_area.setObjectName("feed")
        self.feed_area.setWidgetResizable(True)
        self.feed_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        feed = QWidget()
        feed.setObjectName("feedContent")

        self.feed_layout = QVBoxLayout(feed)
        self.feed_layout.setContentsMargins(4, 0, 8, 0)
        self.feed_layout.setSpacing(12)
        self.feed_layout.addStretch()

        self.feed_area.setWidget(feed)
        layout.addWidget(self.feed_area, 4)

        layout.addWidget(self.build_command_bar())

        return layout

    def build_command_bar(self):
        bar = QFrame()
        bar.setObjectName("commandBar")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 8, 8)
        layout.setSpacing(10)

        prompt = QLabel(">")
        prompt.setObjectName("prompt")
        prompt.setFont(font(MONO_FONT, 14))
        layout.addWidget(prompt)

        self.input = QLineEdit()
        self.input.setObjectName("commandInput")
        self.input.setPlaceholderText("Entrer une commande...")
        self.input.setAccessibleName("Commande")
        self.input.setFont(font(MONO_FONT, 13, spacing=0.5))
        self.input.returnPressed.connect(self.send_message)
        layout.addWidget(self.input, 1)

        self.cursor_block = BlinkCursor()
        layout.addWidget(self.cursor_block)

        self.mic = MicButton()
        self.mic.clicked.connect(self.voice_command)
        layout.addWidget(self.mic)

        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self.voice_command)

        return bar

    def build_right_column(self):
        column = QWidget()
        column.setFixedWidth(276)

        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        modules = Panel("MODULES ACTIFS")

        self.modules = {
            key: ModuleRow(label)
            for key, label in [
                ("pc", "ORDINATEUR"),
                ("phone", "TÉLÉPHONE"),
                ("gmail", "GMAIL"),
                ("voice", "VOIX"),
            ]
        }

        for index, module in enumerate(self.modules.values()):
            if index:
                modules.body.addSpacing(10)
            module.clicked.connect(self.check_status)
            modules.body.addWidget(module)

        audio = Panel("SIGNAL AUDIO")

        self.waveform = Waveform()
        audio.body.addWidget(self.waveform)
        audio.body.addSpacing(14)

        self.listening_label = QLabel()
        self.listening_label.setObjectName("listening")
        self.listening_label.setWordWrap(True)
        audio.body.addWidget(self.listening_label)
        audio.body.addStretch()

        layout.addWidget(modules)
        layout.addWidget(audio, 1)

        return column

    # ---------------------------------------------------------
    # MINUTERIES
    # ---------------------------------------------------------

    def start_timers(self):
        self.animation = QTimer(self)
        self.animation.timeout.connect(self.animate)
        self.animation.start(33)

        self.clock = QTimer(self)
        self.clock.timeout.connect(self.update_clock)
        self.clock.start(1000)
        self.update_clock()

        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.update_metrics)
        self.metrics_timer.start(2000)
        self.update_metrics()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.check_status)
        self.status_timer.start(30000)
        self.check_status()

    def animate(self):
        self.backdrop.advance()
        self.core.advance()
        self.waveform.advance()
        self.top_dot.update()
        self.cursor_block.update()

    def update_clock(self):
        locale = QLocale("fr_FR")

        self.date_label.setText(
            locale.toString(QDate.currentDate(), "dd MMM yyyy").upper()
        )
        self.clock_label.setText(
            QTime.currentTime().toString("HH:mm")
        )

    def update_metrics(self):
        if psutil is None:
            return

        cpu = psutil.cpu_percent(None)
        self.metrics["cpu"].set_value(cpu / 100, f"{cpu:.0f}%")

        ram = psutil.virtual_memory().percent
        self.metrics["ram"].set_value(ram / 100, f"{ram:.0f}%")

        disk = psutil.disk_usage(Path.home().anchor or "/").percent
        self.metrics["disk"].set_value(disk / 100, f"{disk:.0f}%")

        counters = psutil.net_io_counters()
        now = time.monotonic()
        total = counters.bytes_sent + counters.bytes_recv

        if self.net_last:
            last_total, last_time = self.net_last
            rate = max(0.0, (total - last_total) / max(now - last_time, 0.001))
            self.net_peak = max(self.net_peak, rate)

            if rate >= 1024 * 1024:
                text = f"{rate / 1024 / 1024:.1f} Mo/s"
            else:
                text = f"{rate / 1024:.0f} Ko/s"

            self.metrics["net"].set_value(rate / self.net_peak, text)

        self.net_last = (total, now)

    def check_status(self):
        if self.status_worker is not None and self.status_worker.isRunning():
            return

        self.status_worker = StatusWorker(self.phone, self.email, self.voice)
        self.status_worker.checked.connect(self.on_status)
        self.status_worker.start()

    def on_status(self, status):
        details = {
            "pc": ("Contrôle du PC actif", ""),
            "phone": ("Téléphone Android connecté via ADB", "Téléphone non connecté (voir README)"),
            "gmail": ("Compte Gmail configuré", "Gmail non configuré (.env)"),
            "voice": ("Voix disponible", "Voix indisponible (clé OpenAI absente)"),
        }

        for key, module in self.modules.items():
            on = status.get(key, False)
            yes, no = details[key]
            module.set_on(on, yes if on else no)

    # ---------------------------------------------------------
    # ÉTAT ET JOURNAL
    # ---------------------------------------------------------

    def set_state(self, state):
        status, _ = STATE_LABELS.get(state, (state.upper(), ""))

        self.status_label.setText(status)
        self.core.set_state(state)

        self.waveform.active = state in {"listening", "speaking"}
        self.mic.set_active(state == "listening")

        if state == "listening":
            text = "En écoute — parle maintenant."
        elif state == "speaking":
            text = "JARVIS répond…"
        elif self.voice is None:
            text = "Interface vocale indisponible."
        else:
            text = "Clique sur le micro ou appuie sur Ctrl+Espace pour parler."

        self.listening_label.setText(text)

    def log(self, text):
        row = QWidget()

        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        stamp = QLabel(QTime.currentTime().toString("HH:mm"))
        stamp.setObjectName("logTime")
        stamp.setAlignment(Qt.AlignTop)

        message = QLabel(text)
        message.setObjectName("logText")
        message.setWordWrap(True)

        layout.addWidget(stamp)
        layout.addWidget(message, 1)

        self.log_layout.insertWidget(0, row)

        while self.log_layout.count() > 9:
            old = self.log_layout.takeAt(self.log_layout.count() - 1)
            old.widget().deleteLater()

    def on_event(self, name, data):
        data = data or {}
        tool = TOOL_LABELS.get(data.get("tool"), data.get("tool", ""))

        if name == "state.changed":
            self.set_state(data.get("new", "idle"))

        elif name == "tool.started":
            self.log(f"{tool}…")

        elif name == "tool.finished":
            result = " ".join(str(data.get("result", "")).split())
            self.log(result[:90] + ("…" if len(result) > 90 else "") or f"{tool} : terminé.")

        elif name == "tool.failed":
            self.log(f"Échec — {tool}.")

        elif name == "tool.denied":
            self.log(f"Refusé — {tool}.")

        elif name == "tool.blocked":
            self.log(f"Bloqué — {tool}.")

        elif name == "voice.transcribed":
            self.add_message(data.get("text", ""), user=True)

        elif name == "voice.speaking_started":
            self.add_message(data.get("text", ""), user=False)

        elif name == "voice.error":
            self.log(f"Erreur vocale : {data.get('error', '')}")

    # ---------------------------------------------------------
    # CONVERSATION
    # ---------------------------------------------------------

    def add_message(self, text, user):
        if not text:
            return

        block = QWidget()

        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        if user:
            label = QLabel(f"> {text}")
            label.setObjectName("userMessage")
        else:
            name = QLabel("JARVIS")
            name.setObjectName("jarvisName")
            name.setFont(font(DISPLAY_FONT, 10, QFont.Bold, 3))
            layout.addWidget(name)

            label = QLabel(text)
            label.setObjectName("jarvisMessage")

        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)

        self.feed_layout.addWidget(block)

        QTimer.singleShot(
            50,
            lambda: self.feed_area.verticalScrollBar().setValue(
                self.feed_area.verticalScrollBar().maximum()
            )
        )

    def busy(self):
        return (
            (self.worker is not None and self.worker.isRunning())
            or (self.voice_worker is not None and self.voice_worker.isRunning())
        )

    def send_message(self):
        message = self.input.text().strip()

        if not message or self.busy():
            return

        self.input.clear()
        self.add_message(message, user=True)
        self.input.setEnabled(False)

        self.worker = AIWorker(self.orchestrator, message)
        self.worker.finished.connect(self.on_ai_response)
        self.worker.failed.connect(self.on_ai_error)
        self.worker.start()

    def on_ai_response(self, response):
        self.add_message(response, user=False)
        self.release_input()

    def on_ai_error(self, error):
        self.add_message(f"Erreur : {error}", user=False)
        self.log("Erreur du cerveau IA.")
        self.release_input()

    def release_input(self):
        self.input.setEnabled(True)
        self.input.setFocus()

    def voice_command(self):
        if self.voice is None:
            self.add_message("Interface vocale indisponible.", user=False)
            return

        if self.busy():
            return

        self.input.setEnabled(False)

        self.voice_worker = VoiceWorker(self.voice)
        self.voice_worker.finished.connect(self.release_input)
        self.voice_worker.start()

    # ---------------------------------------------------------
    # STYLE
    # ---------------------------------------------------------

    def apply_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {BACKGROUND}; }}

            QWidget {{ color: {TEXT}; }}

            #topBar {{
                border-bottom: 1px solid rgba(94,231,255,0.2);
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(94,231,255,0.05), stop:1 transparent);
            }}
            #brand {{ color: {BRIGHT}; }}
            #topInfo {{ color: {MUTED}; }}
            #topClock {{ color: {ACCENT.name()}; }}

            #panel {{
                border: 1px solid rgba(94,231,255,0.25);
                background: rgba(94,231,255,0.04);
                border-radius: 4px;
            }}
            #panelTitle {{ color: rgba(207,239,245,0.5); }}

            #metricLabel {{ color: rgba(207,239,245,0.75); }}
            #metricValue {{ color: {ACCENT.name()}; }}

            #logTime {{ color: rgba(94,231,255,0.7); font-size: 10.5px; }}
            #logText {{ color: rgba(207,239,245,0.7); font-size: 10.5px; }}

            #module {{
                background: rgba(255,255,255,0.02);
                border: 1px solid rgba(207,239,245,0.15);
                border-radius: 3px;
            }}
            #module[on="true"] {{
                background: rgba(94,231,255,0.08);
                border: 1px solid {ACCENT.name()};
            }}

            #listening {{ color: {MUTED}; font-size: 10.5px; }}

            #feed, #feedContent {{ background: transparent; border: none; }}
            #userMessage {{ color: {BRIGHT}; font-size: 13px; }}
            #jarvisName {{ color: {ACCENT.name()}; }}
            #jarvisMessage {{ color: {TEXT}; font-size: 13px; }}

            #commandBar {{
                border: 1px solid rgba(94,231,255,0.3);
                background: rgba(94,231,255,0.05);
                border-radius: 4px;
            }}
            #prompt {{ color: {ACCENT.name()}; }}
            #commandInput {{
                background: transparent;
                border: none;
                color: {BRIGHT};
                selection-background-color: rgba(94,231,255,0.35);
            }}
            #micButton {{ background: transparent; border: none; }}

            QScrollBar:vertical {{ background: transparent; width: 6px; }}
            QScrollBar::handle:vertical {{
                background: rgba(94,231,255,0.25);
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

            QToolTip {{
                background: #0a1820;
                color: {TEXT};
                border: 1px solid rgba(94,231,255,0.4);
            }}

            QMessageBox {{ background: #0a1820; }}
            QMessageBox QLabel {{ color: {TEXT}; font-size: 12px; }}
            QMessageBox QPushButton {{
                background: rgba(94,231,255,0.08);
                border: 1px solid {ACCENT.name()};
                border-radius: 3px;
                color: {BRIGHT};
                padding: 6px 18px;
                min-width: 60px;
            }}
            QMessageBox QPushButton:hover {{ background: rgba(94,231,255,0.2); }}
        """)


def run_desktop(
    orchestrator,
    voice=None,
    confirmation=None,
    phone=None,
    email=None,
    event_bus=None,
    state_manager=None,
):

    app = QApplication.instance()

    if app is None:
        app = QApplication(sys.argv)

    load_fonts()
    app.setFont(font(MONO_FONT, 11))

    window = JarvisWindow(
        orchestrator=orchestrator,
        voice=voice,
        phone=phone,
        email=email,
        event_bus=event_bus,
        state_manager=state_manager,
    )

    if confirmation is not None:
        dialog = ConfirmationDialog(window)
        confirmation.set_handler(dialog.ask)
        window.confirmation_dialog = dialog

    window.show()

    return app.exec()
