package com.jarvis.assistant.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.assistant.JarvisSettings

@Composable
fun SettingsScreen(
    settings: JarvisSettings,
    onClose: () -> Unit,
    onRequestPermissions: () -> Unit,
    onOpenAccessibility: () -> Unit,
) {
    var openAiKey by remember { mutableStateOf(settings.openAiKey) }
    var model by remember { mutableStateOf(settings.model) }
    var gmailAddress by remember { mutableStateOf(settings.gmailAddress) }
    var gmailPassword by remember { mutableStateOf(settings.gmailPassword) }
    var countryCode by remember { mutableStateOf(settings.countryCode) }
    var whatsappPackage by remember { mutableStateOf(settings.whatsappPackage) }
    var pcAddress by remember { mutableStateOf(settings.pcAddress) }
    var pcToken by remember { mutableStateOf(settings.pcToken) }
    var speakReplies by remember { mutableStateOf(settings.speakReplies) }

    fun save() {
        settings.openAiKey = openAiKey
        settings.model = model
        settings.gmailAddress = gmailAddress
        settings.gmailPassword = gmailPassword
        settings.countryCode = countryCode
        settings.whatsappPackage = whatsappPackage
        settings.pcAddress = pcAddress
        settings.pcToken = pcToken
        settings.speakReplies = speakReplies
        onClose()
    }

    BackHandler { onClose() }

    Column(
        Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(
            "RÉGLAGES",
            color = Bright,
            fontFamily = Orbitron,
            fontWeight = FontWeight.Black,
            fontSize = 18.sp,
            letterSpacing = 4.sp,
        )

        Section("CERVEAU — OPENAI")
        HudField("Clé API OpenAI", openAiKey, { openAiKey = it }, secret = true)
        HudField("Modèle", model, { model = it })

        Section("GMAIL")
        HudField("Adresse Gmail", gmailAddress, { gmailAddress = it }, keyboardType = KeyboardType.Email)
        HudField("Mot de passe d'application", gmailPassword, { gmailPassword = it }, secret = true)

        Section("TÉLÉPHONE")
        HudField("Indicatif pays (ex. 223)", countryCode, { countryCode = it }, keyboardType = KeyboardType.Number)
        HudField("Application WhatsApp", whatsappPackage, { whatsappPackage = it })

        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Lire les réponses à voix haute", fontSize = 13.sp, modifier = Modifier.weight(1f))
            Switch(
                checked = speakReplies,
                onCheckedChange = { speakReplies = it },
                colors = SwitchDefaults.colors(
                    checkedThumbColor = Accent,
                    checkedTrackColor = Accent.copy(alpha = 0.35f),
                    uncheckedThumbColor = Muted,
                    uncheckedTrackColor = Surface,
                ),
            )
        }

        HudButton("Autoriser les permissions (micro, contacts, appels, SMS)", Modifier.fillMaxWidth()) {
            onRequestPermissions()
        }
        HudButton("Activer l'envoi WhatsApp automatique", Modifier.fillMaxWidth()) {
            onOpenAccessibility()
        }

        Section("LIEN AVEC LE PC")
        Text(
            "Pour donner des ordres au PC depuis le téléphone. JARVIS doit tourner sur le PC.",
            color = Muted,
            fontSize = 11.sp,
            lineHeight = 16.sp,
        )
        HudField("Adresse IP du PC (ex. 192.168.1.20)", pcAddress, { pcAddress = it }, keyboardType = KeyboardType.Uri)
        HudField("Jeton (ANDROID_BRIDGE_TOKEN du .env)", pcToken, { pcToken = it }, secret = true)

        Spacer(Modifier.height(4.dp))

        HudButton("Enregistrer", Modifier.fillMaxWidth(), primary = true) { save() }
        HudButton("Annuler", Modifier.fillMaxWidth()) { onClose() }
    }
}

@Composable
private fun Section(title: String) {
    Text(
        title,
        color = Muted,
        fontSize = 10.sp,
        letterSpacing = 3.sp,
        modifier = Modifier.padding(top = 8.dp),
    )
}

@Composable
private fun HudField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    secret: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    val shape = RoundedCornerShape(3.dp)

    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, color = TextColor.copy(alpha = 0.75f), fontSize = 11.sp)

        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            singleLine = true,
            textStyle = TextStyle(color = Bright, fontFamily = SpaceMono, fontSize = 14.sp),
            cursorBrush = SolidColor(Accent),
            visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = if (secret) KeyboardType.Password else keyboardType),
            modifier = Modifier
                .fillMaxWidth()
                .background(Accent.copy(alpha = 0.05f), shape)
                .border(1.dp, Accent.copy(alpha = 0.3f), shape)
                .padding(horizontal = 12.dp, vertical = 12.dp)
                .semantics { contentDescription = label },
        )
    }
}
