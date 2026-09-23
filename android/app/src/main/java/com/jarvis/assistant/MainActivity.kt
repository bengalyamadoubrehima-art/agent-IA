package com.jarvis.assistant

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.core.content.ContextCompat
import com.jarvis.assistant.ui.JarvisApp
import com.jarvis.assistant.ui.JarvisTheme

class MainActivity : ComponentActivity() {

    private val viewModel: JarvisViewModel by viewModels()

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { viewModel.refreshModules() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            JarvisTheme {
                JarvisApp(
                    vm = viewModel,
                    onRequestPermissions = { askPermissions() },
                    onOpenAccessibility = ::openAccessibilitySettings,
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

    override fun onResume() {
        super.onResume()
        viewModel.refreshModules()
    }

    /** Raccourci « Parler à JARVIS » : ouvre directement le micro. */
    private fun handleIntent(intent: Intent?) {
        if (intent?.action == ACTION_LISTEN) viewModel.startListening()
    }

    private fun askPermissions(quiet: Boolean = false) {
        val missing = PERMISSIONS.filter {
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
        Toast.makeText(
            this,
            "Active « JARVIS — envoi WhatsApp » dans la liste.",
            Toast.LENGTH_LONG,
        ).show()
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
