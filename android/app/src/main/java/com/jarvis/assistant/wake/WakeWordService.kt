package com.jarvis.assistant.wake

import ai.picovoice.porcupine.Porcupine
import ai.picovoice.porcupine.PorcupineException
import ai.picovoice.porcupine.PorcupineManager
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

/**
 * Écoute le mot « Jarvis » en arrière-plan, même quand l'application
 * est fermée. Quand il est entendu, JARVIS émet un bip, écoute la
 * demande, l'exécute et répond à voix haute, sans ouvrir l'application.
 *
 * Android impose une notification permanente tant que le micro est
 * utilisé en arrière-plan.
 */
class WakeWordService : Service() {

    private lateinit var core: JarvisCore
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private var porcupine: PorcupineManager? = null
    private var handling = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        core = JarvisCore.get(this)
        createChannel()
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

        if (porcupine == null) startDetection()

        return START_STICKY
    }

    // ========================================================
    // DÉTECTION DU MOT « JARVIS »
    // ========================================================

    private fun startDetection() {
        val key = core.settings.picovoiceKey

        if (key.isBlank()) {
            fail("Ajoute ta clé Picovoice dans les réglages de JARVIS pour activer « Jarvis ».")
            return
        }

        try {
            porcupine = PorcupineManager.Builder()
                .setAccessKey(key)
                .setKeyword(Porcupine.BuiltInKeyword.JARVIS)
                .setSensitivity(0.6f)
                .setErrorCallback { error ->
                    scope.launch { fail("Écoute de « Jarvis » interrompue : ${error.message}") }
                }
                .build(applicationContext) {
                    scope.launch { onWakeWord() }
                }

            porcupine?.start()
            core.wakeListening = true
        } catch (e: PorcupineException) {
            fail("Impossible d'activer « Jarvis » : ${e.message}. Vérifie ta clé Picovoice.")
        }
    }

    private suspend fun onWakeWord() {
        if (handling || core.busy) return
        handling = true

        try {
            // Le micro est libéré pour écouter la demande.
            runCatching { porcupine?.stop() }
            updateNotification("Je t'écoute…")
            core.handsFree()
        } finally {
            updateNotification(IDLE_TEXT)
            runCatching { porcupine?.start() }
            handling = false
        }
    }

    private fun fail(message: String) {
        core.note(message)
        core.wakeListening = false
        core.settings.wakeEnabled = false
        stopSelf()
    }

    override fun onDestroy() {
        runCatching { porcupine?.stop() }
        porcupine?.delete()
        porcupine = null
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
        getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(text))
    }

    companion object {
        private const val CHANNEL_ID = "wake_word"
        private const val NOTIFICATION_ID = 1
        private const val ACTION_STOP = "com.jarvis.assistant.STOP_WAKE"
        private const val IDLE_TEXT = "Dis « Jarvis » pour me parler."

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, WakeWordService::class.java))
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, WakeWordService::class.java))
        }
    }
}
