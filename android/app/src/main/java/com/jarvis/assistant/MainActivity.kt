package com.jarvis.assistant

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import com.jarvis.assistant.access.WhatsAppService
import com.jarvis.assistant.ui.JarvisApp
import com.jarvis.assistant.ui.JarvisTheme
import com.jarvis.assistant.wake.WakeWordService

class MainActivity : ComponentActivity() {

    private val core by lazy { JarvisCore.get(this) }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { core.refreshModules() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            JarvisTheme {
                JarvisApp(
                    vm = core,
                    onRequestPermissions = { askPermissions() },
                    onOpenAccessibility = ::openAccessibilitySettings,
                    onToggleWake = ::toggleWakeWord,
                    onOpenOverlay = ::openOverlaySettings,
                    onOpenBattery = ::openBatterySettings,
                )
            }
        }

        if (savedInstanceState == null) {
            askPermissions(quiet = true)
            handleIntent(intent)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    override fun onStart() {
        super.onStart()
        core.uiVisible = true

        // Relance l'écoute de « Jarvis » si elle était activée
        // (par exemple après un redémarrage du téléphone).
        if (core.settings.wakeEnabled && !core.wakeListening && micGranted()) {
            WakeWordService.start(this)
        }
    }

    override fun onResume() {
        super.onResume()
        core.refreshModules()
    }

    override fun onStop() {
        core.uiVisible = false
        super.onStop()
    }

    /** Raccourci « Parler à JARVIS » : ouvre directement le micro. */
    private fun handleIntent(intent: Intent?) {
        if (intent?.action == ACTION_LISTEN) core.startListening()
    }

    // ========================================================
    // MOT D'ACTIVATION
    // ========================================================

    private fun toggleWakeWord() {
        if (core.wakeListening) {
            core.settings.wakeEnabled = false
            WakeWordService.stop(this)
            core.note("Écoute de « Jarvis » désactivée.")
            return
        }

        if (!micGranted()) {
            askPermissions()
            return
        }

        core.settings.wakeEnabled = true
        WakeWordService.start(this)
        core.note("Écoute de « Jarvis » activée : tu peux fermer l'application.")

        val canOpenApps = android.provider.Settings.canDrawOverlays(this) || WhatsAppService.isEnabled(this)
        if (!canOpenApps) {
            core.note(
                "Pour que JARVIS ouvre des applis quand tu n'es pas dans l'application, touche " +
                    "« Autoriser l'ouverture d'applis en arrière-plan » dans les réglages."
            )
        }
    }

    // ========================================================
    // PERMISSIONS ET RÉGLAGES ANDROID
    // ========================================================

    private fun micGranted(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED

    private fun askPermissions(quiet: Boolean = false) {
        val wanted = buildList {
            addAll(PERMISSIONS)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) add(Manifest.permission.POST_NOTIFICATIONS)
        }

        val missing = wanted.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missing.isEmpty()) {
            if (!quiet) Toast.makeText(this, "Toutes les permissions sont déjà accordées.", Toast.LENGTH_SHORT).show()
        } else {
            permissionLauncher.launch(missing.toTypedArray())
        }
    }

    private fun openAccessibilitySettings() {
        startActivity(Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS))
        Toast.makeText(this, "Active « JARVIS — envoi WhatsApp » dans la liste.", Toast.LENGTH_LONG).show()
    }

    /** « Afficher par-dessus les autres applis » : permet d'ouvrir des applis depuis l'arrière-plan. */
    private fun openOverlaySettings() {
        if (android.provider.Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "C'est déjà autorisé.", Toast.LENGTH_SHORT).show()
            return
        }

        startActivity(
            Intent(
                android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                Uri.parse("package:$packageName"),
            )
        )
        Toast.makeText(this, "Active l'autorisation pour JARVIS.", Toast.LENGTH_LONG).show()
    }

    @SuppressLint("BatteryLife")
    private fun openBatterySettings() {
        val power = getSystemService(PowerManager::class.java)

        if (power.isIgnoringBatteryOptimizations(packageName)) {
            Toast.makeText(this, "C'est déjà réglé.", Toast.LENGTH_SHORT).show()
            return
        }

        startActivity(
            Intent(
                android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                Uri.parse("package:$packageName"),
            )
        )
    }

    companion object {
        const val ACTION_LISTEN = "com.jarvis.assistant.LISTEN"

        private val PERMISSIONS = listOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.READ_CONTACTS,
            Manifest.permission.CALL_PHONE,
            Manifest.permission.SEND_SMS,
            Manifest.permission.ANSWER_PHONE_CALLS,
        )
    }
}
