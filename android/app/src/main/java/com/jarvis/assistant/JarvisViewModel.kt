package com.jarvis.assistant

import android.Manifest
import android.app.Application
import android.content.pm.PackageManager
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.jarvis.assistant.access.WhatsAppService
import com.jarvis.assistant.ai.Assistant
import com.jarvis.assistant.tools.GmailClient
import com.jarvis.assistant.tools.PcLink
import com.jarvis.assistant.tools.PhoneTools
import com.jarvis.assistant.tools.ToolRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class JarvisViewModel(application: Application) : AndroidViewModel(application), Voice.Listener {

    val settings = JarvisSettings(application)

    private val gmail = GmailClient(settings)
    private val pc = PcLink(settings)

    private val tools = ToolRegistry(
        phone = PhoneTools(application, settings),
        gmail = gmail,
        pc = pc,
        confirm = ::askConfirmation,
        log = ::log,
    )

    private val assistant = Assistant(settings, tools)
    private val voice = Voice(application, this)

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

    private var working = false

    // ========================================================
    // CONVERSATION
    // ========================================================

    fun send(text: String) {
        val message = text.trim()
        if (message.isEmpty() || working) return

        working = true
        voice.stopSpeaking()
        messages += ChatMessage(Role.USER, message)
        state = JarvisState.THINKING

        viewModelScope.launch {
            var failed = false

            val answer = try {
                assistant.respond(message)
            } catch (e: Exception) {
                failed = true
                "Erreur : ${e.message}"
            }

            messages += ChatMessage(Role.JARVIS, answer)
            working = false

            if (settings.speakReplies && voice.canSpeak) {
                state = JarvisState.SPEAKING
                voice.speak(answer)
            } else {
                state = if (failed) JarvisState.ERROR else JarvisState.IDLE
            }
        }
    }

    fun note(text: String) {
        messages += ChatMessage(Role.SYSTEM, text)
    }

    private fun log(text: String) {
        viewModelScope.launch {
            messages += ChatMessage(Role.SYSTEM, text)
            if (working) state = JarvisState.EXECUTING
        }
    }

    // ========================================================
    // CONFIRMATION
    // ========================================================

    private suspend fun askConfirmation(label: String, details: String): Boolean =
        withContext(Dispatchers.Main) {
            val request = ConfirmationRequest(label, details)
            confirmation = request
            val approved = request.result.await()
            confirmation = null
            approved
        }

    fun answerConfirmation(approved: Boolean) {
        confirmation?.result?.complete(approved)
    }

    // ========================================================
    // VOIX
    // ========================================================

    fun startListening() {
        if (working || state == JarvisState.LISTENING) return

        val granted = ContextCompat.checkSelfPermission(
            getApplication(), Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED

        if (!granted) {
            note("Autorise le micro : réglages de JARVIS → « Autoriser les permissions ».")
            return
        }

        if (!voice.canListen) {
            note("La reconnaissance vocale n'est pas disponible : installe ou mets à jour l'application Google.")
            return
        }

        voice.stopSpeaking()
        partial = ""
        state = JarvisState.LISTENING
        voice.listen()
    }

    fun stopListening() {
        voice.stopListening()
    }

    override fun onPartial(text: String) {
        partial = text
    }

    override fun onFinal(text: String) {
        partial = ""
        audioLevel = 0f
        state = JarvisState.IDLE
        send(text)
    }

    override fun onLevel(level: Float) {
        audioLevel = level
    }

    override fun onListenError(message: String) {
        partial = ""
        audioLevel = 0f
        state = JarvisState.IDLE
        note(message)
    }

    override fun onSpeakingDone() {
        if (state == JarvisState.SPEAKING) state = JarvisState.IDLE
    }

    // ========================================================
    // MODULES
    // ========================================================

    fun refreshModules() {
        viewModelScope.launch {
            val pcReachable = withContext(Dispatchers.IO) { pc.reachable() }

            modules = Modules(
                brain = settings.openAiKey.isNotBlank(),
                whatsapp = WhatsAppService.isEnabled(getApplication()),
                gmail = gmail.isConfigured(),
                pc = pcReachable,
            )
        }
    }

    override fun onCleared() {
        voice.release()
    }
}
