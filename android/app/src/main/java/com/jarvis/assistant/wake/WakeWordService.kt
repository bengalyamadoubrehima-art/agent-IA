package com.jarvis.assistant.wake

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.jarvis.assistant.JarvisCore
import com.jarvis.assistant.MainActivity
import com.jarvis.assistant.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.json.JSONObject
import org.vosk.Model
import org.vosk.Recognizer
import org.vosk.android.RecognitionListener
import org.vosk.android.SpeechService
import org.vosk.android.StorageService
import java.io.IOException

/**
 * Écoute le mot « Jarvis » en arrière-plan, même quand l'application
 * est fermée, avec Vosk (reconnaissance vocale libre, hors ligne,
 * sans compte). Quand il est entendu, JARVIS émet un bip, écoute la
 * demande, l'exécute et répond à voix haute, sans ouvrir l'application.
 *
 * Android impose une notification permanente tant que le micro est
 * utilisé en arrière-plan.
 */
class WakeWordService : Service() {

    private lateinit var core: JarvisCore
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private var model: Model? = null
    private var recognizer: Recognizer? = null
    private var speech: SpeechService? = null

    private var loading = false
    private var handling = false
    private var destroyed = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        core = JarvisCore.get(this)
        createChannel()

        // Libère le micro quand l'écran de JARVIS en a besoin.
        core.wakeMicControl = { pause ->
            if (pause) stopDetection() else if (!handling) startDetection()
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            core.settings.wakeEnabled = false
            stopSelf()
            return START_NOT_STICKY
        }

        try {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification(IDLE_TEXT),
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
                } else {
                    0
                },
            )
        } catch (e: Exception) {
            // Android refuse d'ouvrir le micro en arrière-plan sans que
            // l'application ait été ouverte : l'écoute reprendra à la
            // prochaine ouverture de JARVIS.
            core.wakeListening = false
            stopSelf()
            return START_NOT_STICKY
        }

        if (model == null) loadModel() else startDetection()

        return START_STICKY
    }

    // ========================================================
    // MODÈLE VOCAL
    // ========================================================

    /** Copie le modèle Vosk des ressources de l'application (une seule fois). */
    private fun loadModel() {
        if (loading) return
        loading = true
        updateNotification("Préparation de l'écoute…")

        StorageService.unpack(
            this,
            MODEL_ASSET,
            "model",
            StorageService.Callback<Model> { loaded ->
                loading = false

                if (destroyed) {
                    loaded.close()
                    return@Callback
                }

                model = loaded
                startDetection()
            },
            StorageService.Callback<IOException> { error ->
                loading = false
                fail("Modèle vocal introuvable : ${error.message}")
            },
        )
    }

    // ========================================================
    // DÉTECTION DU MOT « JARVIS »
    // ========================================================

    private fun startDetection() {
        val loaded = model ?: return
        if (speech != null || destroyed) return

        try {
            val newRecognizer = Recognizer(loaded, SAMPLE_RATE, GRAMMAR)
            val newSpeech = SpeechService(newRecognizer, SAMPLE_RATE)

            recognizer = newRecognizer
            speech = newSpeech

            newSpeech.startListening(listener)

            core.wakeListening = true
            updateNotification(IDLE_TEXT)
        } catch (e: Exception) {
            fail("Impossible d'écouter « Jarvis » : ${e.message}")
        }
    }

    private fun stopDetection() {
        speech?.stop()
        speech?.shutdown()
        speech = null

        recognizer?.close()
        recognizer = null
    }

    private val listener = object : RecognitionListener {

        override fun onPartialResult(hypothesis: String?) {
            detect(hypothesis, "partial")
        }

        override fun onResult(hypothesis: String?) {
            detect(hypothesis, "text")
        }

        override fun onFinalResult(hypothesis: String?) {}

        override fun onError(exception: Exception?) {
            fail("Écoute de « Jarvis » interrompue : ${exception?.message}")
        }

        override fun onTimeout() {}
    }

    private fun detect(hypothesis: String?, key: String) {
        val text = try {
            JSONObject(hypothesis ?: return).optString(key)
        } catch (e: Exception) {
            return
        }

        if ("jarvis" in text.split(" ")) {
            scope.launch { onWakeWord() }
        }
    }

    private suspend fun onWakeWord() {
        if (handling || core.busy) return
        handling = true

        try {
            // Le micro est libéré pour écouter la demande.
            stopDetection()
            updateNotification("Je t'écoute…")
            core.handsFree()
        } finally {
            handling = false
            if (!destroyed) startDetection()
        }
    }

    private fun fail(message: String) {
        core.note(message)
        core.wakeListening = false
        core.settings.wakeEnabled = false
        stopSelf()
    }

    override fun onDestroy() {
        destroyed = true
        core.wakeMicControl = null
        stopDetection()
        model?.close()
        model = null
        core.wakeListening = false
        scope.cancel()
        super.onDestroy()
    }

    // ========================================================
    // NOTIFICATION
    // ========================================================

    private fun createChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Écoute de « Jarvis »",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Affichée tant que JARVIS écoute le mot « Jarvis »."
            setShowBadge(false)
        }

        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun notification(text: String): Notification {
        val open = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        val stop = PendingIntent.getService(
            this,
            1,
            Intent(this, WakeWordService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("JARVIS")
            .setContentText(text)
            .setOngoing(true)
            .setSilent(true)
            .setContentIntent(open)
            .addAction(0, "Arrêter l'écoute", stop)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    private fun updateNotification(text: String) {
        if (destroyed) return
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
    }

    companion object {
        private const val CHANNEL_ID = "wake_word"
        private const val NOTIFICATION_ID = 1
        private const val ACTION_STOP = "com.jarvis.assistant.STOP_WAKE"
        private const val IDLE_TEXT = "Dis « Jarvis » pour me parler."

        // Modèle anglais léger de Vosk, ajouté aux ressources à la compilation.
        private const val MODEL_ASSET = "model-en-us"
        private const val SAMPLE_RATE = 16000f

        // Vocabulaire limité : « jarvis » ou « autre chose ».
        private const val GRAMMAR = "[\"jarvis\", \"[unk]\"]"

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, WakeWordService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, WakeWordService::class.java))
        }
    }
}
