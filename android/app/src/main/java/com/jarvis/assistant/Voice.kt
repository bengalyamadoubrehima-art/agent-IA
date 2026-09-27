package com.jarvis.assistant

import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.Locale
import kotlin.coroutines.resume

/** Résultat d'une écoute. */
sealed interface Heard {
    data class Text(val text: String) : Heard
    data class Failure(val message: String) : Heard
}

/**
 * Voix de JARVIS avec les services Android (gratuits) :
 * reconnaissance vocale et synthèse vocale en français.
 * À utiliser depuis le thread principal.
 */
class Voice(private val context: Context) {

    var onLevel: (Float) -> Unit = {}
    var onPartial: (String) -> Unit = {}

    private val main = Handler(Looper.getMainLooper())
    private var recognizer: SpeechRecognizer? = null
    private var tts: TextToSpeech? = null
    private var ttsReady = false

    private var pendingListen: CancellableContinuation<Heard>? = null
    private val pendingSpeech = HashMap<String, CancellableContinuation<Unit>>()

    // Phrases en file d'attente (dites les unes après les autres).
    private val queued = HashSet<String>()
    private var lastQueued: String? = null

    val canListen: Boolean
        get() = SpeechRecognizer.isRecognitionAvailable(context)

    val canSpeak: Boolean
        get() = ttsReady

    init {
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                val result = tts?.setLanguage(Locale.FRANCE) ?: TextToSpeech.LANG_NOT_SUPPORTED
                ttsReady = result >= TextToSpeech.LANG_AVAILABLE
            }
        }

        tts?.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(utteranceId: String?) {}

            override fun onDone(utteranceId: String?) {
                main.post { finishSpeech(utteranceId) }
            }

            override fun onStop(utteranceId: String?, interrupted: Boolean) {
                main.post { finishSpeech(utteranceId) }
            }

            @Deprecated("Deprecated in Java")
            override fun onError(utteranceId: String?) {
                main.post { finishSpeech(utteranceId) }
            }
        })
    }

    // ========================================================
    // ÉCOUTE
    // ========================================================

    private val recognitionListener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onEvent(eventType: Int, params: Bundle?) {}

        override fun onRmsChanged(rmsdB: Float) {
            onLevel(((rmsdB + 2f) / 12f).coerceIn(0f, 1f))
        }

        override fun onPartialResults(partialResults: Bundle?) {
            firstResult(partialResults)?.let { onPartial(it) }
        }

        override fun onResults(results: Bundle?) {
            val text = firstResult(results)
            finishListen(
                if (text.isNullOrBlank()) Heard.Failure("Je n'ai rien entendu.") else Heard.Text(text)
            )
        }

        override fun onError(error: Int) {
            finishListen(
                Heard.Failure(
                    when (error) {
                        SpeechRecognizer.ERROR_NO_MATCH,
                        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Je n'ai rien entendu."
                        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Autorise le micro dans les réglages de JARVIS."
                        SpeechRecognizer.ERROR_NETWORK,
                        SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Reconnaissance vocale : pas de connexion."
                        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Le micro est déjà utilisé, réessaie."
                        SpeechRecognizer.ERROR_CLIENT -> "Écoute arrêtée."
                        else -> "Erreur du micro (code $error)."
                    }
                )
            )
        }
    }

    private fun firstResult(bundle: Bundle?): String? =
        bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()

    private fun finishListen(result: Heard) {
        val continuation = pendingListen ?: return
        pendingListen = null
        onLevel(0f)
        if (continuation.isActive) continuation.resume(result)
    }

    /** Écoute une phrase et la renvoie une fois terminée. */
    suspend fun listen(): Heard = suspendCancellableCoroutine { continuation ->
        finishListen(Heard.Failure("Écoute interrompue."))
        pendingListen = continuation

        val current = recognizer ?: SpeechRecognizer.createSpeechRecognizer(context).also {
            it.setRecognitionListener(recognitionListener)
            recognizer = it
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "fr-FR")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
        }

        continuation.invokeOnCancellation { main.post { recognizer?.cancel() } }

        current.startListening(intent)
    }

    fun stopListening() {
        recognizer?.stopListening()
    }

    /** Petit signal sonore : « je t'écoute ». */
    suspend fun beep() {
        val tone = try {
            ToneGenerator(AudioManager.STREAM_MUSIC, 70)
        } catch (e: RuntimeException) {
            return
        }

        tone.startTone(ToneGenerator.TONE_PROP_ACK, 150)
        delay(220)
        tone.release()
    }

    // ========================================================
    // PAROLE
    // ========================================================

    /**
     * Ajoute une phrase à la file de lecture et rend la main tout de suite :
     * JARVIS commence à parler pendant que la suite de la réponse arrive.
     */
    fun enqueue(text: String) {
        val engine = tts
        val sentence = clean(text)
        if (engine == null || !ttsReady || sentence.isEmpty()) return

        val id = "jarvis-${System.nanoTime()}"
        queued += id
        lastQueued = id

        if (engine.speak(sentence, TextToSpeech.QUEUE_ADD, null, id) != TextToSpeech.SUCCESS) {
            queued -= id
        }
    }

    /** Attend que toutes les phrases en file aient été dites. */
    suspend fun awaitSpeech() {
        val engine = tts ?: return
        val id = lastQueued ?: return
        if (id !in queued) return

        suspendCancellableCoroutine<Unit> { continuation ->
            pendingSpeech[id] = continuation

            continuation.invokeOnCancellation {
                main.post {
                    pendingSpeech.remove(id)
                    engine.stop()
                }
            }
        }
    }

    /** Lit le texte à voix haute (après ce qui est déjà en file) et attend la fin. */
    suspend fun speak(text: String) {
        enqueue(text)
        awaitSpeech()
    }

    private fun finishSpeech(id: String?) {
        if (id == null) return
        queued -= id
        val continuation = pendingSpeech.remove(id) ?: return
        if (continuation.isActive) continuation.resume(Unit)
    }

    fun stopSpeaking() {
        tts?.stop()
        (queued + pendingSpeech.keys).toList().forEach { finishSpeech(it) }
    }

    private fun clean(text: String): String =
        text.replace(Regex("https?://\\S+"), "le lien")
            .replace(Regex("[*#_`>]"), "")
            .replace(Regex("\\s+"), " ")
            .trim()
}
