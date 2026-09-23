package com.jarvis.assistant

import kotlinx.coroutines.CompletableDeferred
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.atomic.AtomicLong

enum class JarvisState(val status: String, val word: String) {
    IDLE("SYSTÈME OPÉRATIONNEL", "VEILLE"),
    LISTENING("ÉCOUTE EN COURS", "ÉCOUTE"),
    THINKING("ANALYSE EN COURS", "ANALYSE"),
    EXECUTING("EXÉCUTION EN COURS", "ACTION"),
    SPEAKING("RÉPONSE VOCALE", "PAROLE"),
    ERROR("ANOMALIE DÉTECTÉE", "ERREUR"),
}

enum class Role { USER, JARVIS, SYSTEM }

data class ChatMessage(
    val role: Role,
    val text: String,
    val time: String = SimpleDateFormat("HH:mm", Locale.FRANCE).format(Date()),
    val id: Long = ids.incrementAndGet(),
) {
    private companion object {
        val ids = AtomicLong()
    }
}

data class Modules(
    val brain: Boolean = false,
    val whatsapp: Boolean = false,
    val gmail: Boolean = false,
    val pc: Boolean = false,
)

class ConfirmationRequest(
    val label: String,
    val details: String,
) {
    val result = CompletableDeferred<Boolean>()
}
