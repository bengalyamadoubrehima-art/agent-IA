package com.jarvis.assistant

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import com.jarvis.assistant.access.WhatsAppService
import com.jarvis.assistant.ai.Assistant
import com.jarvis.assistant.tools.GmailClient
import com.jarvis.assistant.tools.Matching
import com.jarvis.assistant.tools.PcLink
import com.jarvis.assistant.tools.PhoneTools
import com.jarvis.assistant.tools.ToolRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * Cœur de JARVIS, partagé entre l'écran et l'écoute en arrière-plan
 * (mot d'activation « Jarvis ») : conversation, voix, outils et état.
 */
class JarvisCore private constructor(private val context: Context) {

    val settings = JarvisSettings(context)

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private val gmail = GmailClient(settings)
    private val pc = PcLink(settings)

    private val tools = ToolRegistry(
        phone = PhoneTools(context, settings, appVisible = { uiVisible }),
        gmail = gmail,
        pc = pc,
        confirm = ::askConfirmation,
        log = ::log,
    )

    private val assistant = Assistant(settings, tools)

    private val voice = Voice(context).apply {
        onLevel = { audioLevel = it }
        onPartial = { partial = it }
    }

    // Une seule conversation à la fois
    private val conversation = Mutex()

    val messages = mutableStateListOf<ChatMessage>()

    var state by mutableStateOf(JarvisState.IDLE)
        private set

    var partial by mutableStateOf("")
        private set

    var audioLevel by mutableFloatStateOf(0f)
        private set

    var confirmation by mutableStateOf<ConfirmationRequest?>(null)
        private set

    var modules by mutableStateOf(Modules())
        private set

    /** Vrai quand le service du mot d'activation écoute « Jarvis ». */
    var wakeListening by mutableStateOf(false)

    /** Mis en pause (true) / relancé (false) par l'écran quand il a besoin du micro. */
    var wakeMicControl: ((Boolean) -> Unit)? = null

    /** Vrai quand l'écran de JARVIS est affiché. */
    @Volatile
    var uiVisible = false

    val busy: Boolean
        get() = conversation.isLocked

    // ========================================================
    // CONVERSATION
    // ========================================================

    /** Commande tapée au clavier. */
    fun send(text: String) {
        val message = text.trim()
        if (message.isEmpty() || busy) return

        scope.launch {
            conversation.withLock { process(message) }
        }
    }

    /** Bouton micro de l'écran. */
    fun startListening() {
        if (busy || !micAllowed()) return

        scope.launch {
            conversation.withLock {
                wakeMicControl?.invoke(true)
                try {
                    converse(beep = false)
                } finally {
                    wakeMicControl?.invoke(false)
                }
            }
        }
    }

    fun stopListening() {
        voice.stopListening()
    }

    /** Appelé quand « Jarvis » est entendu : écoute la demande et y répond. */
    suspend fun handsFree() {
        if (busy || !micAllowed()) return

        withContext(Dispatchers.Main) {
            conversation.withLock { converse(beep = true) }
        }
    }

    private suspend fun converse(beep: Boolean) {
        voice.stopSpeaking()
        if (beep) voice.beep()

        partial = ""
        state = JarvisState.LISTENING

        val heard = voice.listen()

        partial = ""
        audioLevel = 0f

        when (heard) {
            is Heard.Text -> process(heard.text)
            is Heard.Failure -> {
                state = JarvisState.IDLE
                note(heard.message)
            }
        }
    }

    private suspend fun process(message: String) {
        voice.stopSpeaking()
        messages += ChatMessage(Role.USER, message)
        state = JarvisState.THINKING

        var failed = false

        val answer = try {
            assistant.respond(message)
        } catch (e: Exception) {
            failed = true
            "Erreur : ${e.message}"
        }

        messages += ChatMessage(Role.JARVIS, answer)

        // Sans écran, la réponse est toujours dite à voix haute.
        if ((settings.speakReplies || !uiVisible) && voice.canSpeak) {
            state = JarvisState.SPEAKING
            voice.speak(answer)
        }

        state = if (failed) JarvisState.ERROR else JarvisState.IDLE
    }

    fun note(text: String) {
        scope.launch { messages += ChatMessage(Role.SYSTEM, text) }
    }

    private fun log(text: String) {
        scope.launch {
            messages += ChatMessage(Role.SYSTEM, text)
            if (state == JarvisState.THINKING) state = JarvisState.EXECUTING
        }
    }

    private fun micAllowed(): Boolean {
        val granted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED

        if (!granted) {
            note("Autorise le micro : réglages de JARVIS → « Autoriser les permissions ».")
            return false
        }

        if (!voice.canListen) {
            note("La reconnaissance vocale n'est pas disponible : installe ou mets à jour l'application Google.")
            return false
        }

        return true
    }

    // ========================================================
    // CONFIRMATION
    // ========================================================

    /**
     * Écran affiché : boîte de dialogue.
     * Sans écran : JARVIS pose la question à voix haute et écoute la réponse.
     */
    private suspend fun askConfirmation(label: String, details: String): Boolean =
        withContext(Dispatchers.Main) {
            if (uiVisible) {
                val request = ConfirmationRequest(label, details)
                confirmation = request
                val approved = request.result.await()
                confirmation = null
                return@withContext approved
            }

            val spokenDetails = details.lines().joinToString(". ")

            state = JarvisState.SPEAKING
            voice.speak("$label. $spokenDetails. Je confirme ?")

            state = JarvisState.LISTENING
            val heard = voice.listen()
            state = JarvisState.EXECUTING

            val approved = heard is Heard.Text && isYes(heard.text)
            note(if (approved) "Confirmé à la voix." else "Annulé à la voix.")
            approved
        }

    private fun isYes(answer: String): Boolean {
        val words = " ${Matching.normalize(answer)} "

        if (listOf(" non ", " pas ", " annule ", " stop ", " attends ").any { it in words }) return false

        return listOf(
            " oui ", " ouais ", " ok ", " okay ", " d accord ", " vas y ", " confirme ",
            " envoie ", " appelle ", " bien sur ", " exactement ", " go ", " yes ",
        ).any { it in words }
    }

    fun answerConfirmation(approved: Boolean) {
        confirmation?.result?.complete(approved)
    }

    // ========================================================
    // MODULES
    // ========================================================

    fun refreshModules() {
        scope.launch {
            val pcReachable = withContext(Dispatchers.IO) { pc.reachable() }

            modules = Modules(
                brain = settings.apiKey.isNotBlank(),
                whatsapp = WhatsAppService.isEnabled(context),
                gmail = gmail.isConfigured(),
                pc = pcReachable,
            )
        }
    }

    companion object {

        @Volatile
        private var instance: JarvisCore? = null

        fun get(context: Context): JarvisCore =
            instance ?: synchronized(this) {
                instance ?: JarvisCore(context.applicationContext).also { instance = it }
            }
    }
}
