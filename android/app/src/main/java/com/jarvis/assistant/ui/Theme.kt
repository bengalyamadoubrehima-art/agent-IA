package com.jarvis.assistant.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import com.jarvis.assistant.R

// Palette de la maquette « Jarvis UI »
val Accent = Color(0xFF5EE7FF)
val Bright = Color(0xFFEAFCFF)
val TextColor = Color(0xFFCFEFF5)
val Muted = Color(0x8CCFEFF5)
val Background = Color(0xFF050B0F)
val Surface = Color(0xFF0A1820)
val Danger = Color(0xFFFF5E5E)

@OptIn(ExperimentalTextApi::class)
val Orbitron = FontFamily(
    Font(R.font.orbitron, FontWeight.Medium, variationSettings = FontVariation.Settings(FontVariation.weight(500))),
    Font(R.font.orbitron, FontWeight.Bold, variationSettings = FontVariation.Settings(FontVariation.weight(700))),
    Font(R.font.orbitron, FontWeight.Black, variationSettings = FontVariation.Settings(FontVariation.weight(900))),
)

val SpaceMono = FontFamily(
    Font(R.font.space_mono_regular, FontWeight.Normal),
    Font(R.font.space_mono_bold, FontWeight.Bold),
)

@Composable
fun JarvisTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Accent,
            onPrimary = Background,
            background = Background,
            onBackground = TextColor,
            surface = Surface,
            onSurface = TextColor,
        ),
    ) {
        CompositionLocalProvider(
            LocalTextStyle provides TextStyle(fontFamily = SpaceMono, color = TextColor),
            content = content,
        )
    }
}
