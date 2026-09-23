package com.jarvis.assistant.ui

import android.os.BatteryManager
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.jarvis.assistant.ChatMessage
import com.jarvis.assistant.ConfirmationRequest
import com.jarvis.assistant.JarvisState
import com.jarvis.assistant.JarvisViewModel
import com.jarvis.assistant.Modules
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.PI
import kotlin.math.max
import kotlin.math.sin
import com.jarvis.assistant.Role as MessageRole

// =============================================================
// APPLICATION
// =============================================================

@Composable
fun JarvisApp(
    vm: JarvisViewModel,
    onRequestPermissions: () -> Unit,
    onOpenAccessibility: () -> Unit,
) {
    var showSettings by rememberSaveable { mutableStateOf(false) }

    Box(Modifier.fillMaxSize().hudBackground()) {
        ScanBand()

        if (showSettings) {
            SettingsScreen(
                settings = vm.settings,
                onClose = {
                    showSettings = false
                    vm.refreshModules()
                },
                onRequestPermissions = onRequestPermissions,
                onOpenAccessibility = onOpenAccessibility,
            )
        } else {
            HudScreen(
                vm = vm,
                onOpenSettings = { showSettings = true },
                onOpenAccessibility = onOpenAccessibility,
            )
        }
    }

    vm.confirmation?.let { ConfirmDialog(it, vm::answerConfirmation) }
}

// =============================================================
// FOND
// =============================================================

/** Dégradé radial et trame horizontale, dessinés une seule fois. */
fun Modifier.hudBackground(): Modifier = drawWithCache {
    val gradient = Brush.radialGradient(
        0f to Color(0xFF0A1820),
        0.62f to Background,
        1f to Color(0xFF020507),
        center = Offset(size.width / 2f, size.height * 0.3f),
        radius = max(size.width, size.height) * 0.8f,
    )
    val line = Accent.copy(alpha = 0.025f)

    onDrawBehind {
        drawRect(gradient)

        var y = 0f
        while (y < size.height) {
            drawLine(line, Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
            y += 3f
        }
    }
}

/** Bande lumineuse qui descend lentement sur l'écran. */
@Composable
private fun ScanBand() {
    BoxWithConstraints(Modifier.fillMaxSize()) {
        val screenHeight = constraints.maxHeight.toFloat()
        val bandHeight = with(LocalDensity.current) { 120.dp.toPx() }

        val progress by rememberInfiniteTransition(label = "scan").animateFloat(
            initialValue = 0f,
            targetValue = 1f,
            animationSpec = infiniteRepeatable(tween(6000, easing = LinearEasing)),
            label = "scan",
        )

        Box(
            Modifier
                .fillMaxWidth()
                .height(120.dp)
                .graphicsLayer { translationY = progress * (screenHeight + bandHeight) - bandHeight }
                .background(
                    Brush.verticalGradient(
                        listOf(Color.Transparent, Accent.copy(alpha = 0.05f), Color.Transparent)
                    )
                )
        )
    }
}

// =============================================================
// ÉCRAN PRINCIPAL
// =============================================================

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun HudScreen(
    vm: JarvisViewModel,
    onOpenSettings: () -> Unit,
    onOpenAccessibility: () -> Unit,
) {
    var input by rememberSaveable { mutableStateOf("") }

    val coreHeight by animateDpAsState(
        targetValue = if (WindowInsets.isImeVisible) 96.dp else 230.dp,
        label = "core",
    )

    LaunchedEffect(Unit) {
        while (true) {
            vm.refreshModules()
            delay(30_000)
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .padding(horizontal = 16.dp)
    ) {
        TopBar(onOpenSettings)
        StatusStrip(vm.state)

        HudCore(vm.state, Modifier.fillMaxWidth().height(coreHeight))

        ModulesRow(vm.modules, onOpenSettings, onOpenAccessibility)

        Conversation(vm.messages, Modifier.weight(1f).fillMaxWidth())

        if (vm.partial.isNotBlank()) {
            Text(
                vm.partial,
                color = Accent,
                fontSize = 13.sp,
                modifier = Modifier.padding(vertical = 6.dp),
            )
        }

        Waveform(vm.state, vm.audioLevel, Modifier.fillMaxWidth().height(28.dp))

        Spacer(Modifier.height(8.dp))

        val listening = vm.state == JarvisState.LISTENING

        CommandBar(
            value = input,
            onValueChange = { input = it },
            onSend = {
                vm.send(input)
                input = ""
            },
            listening = listening,
            onMic = { if (listening) vm.stopListening() else vm.startListening() },
        )

        Spacer(Modifier.height(12.dp))
    }
}

@Composable
private fun TopBar(onOpenSettings: () -> Unit) {
    var clock by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        val format = SimpleDateFormat("HH:mm", Locale.FRANCE)
        while (true) {
            clock = format.format(Date())
            delay(1000)
        }
    }

    Row(
        Modifier.fillMaxWidth().padding(top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        PulseDot()
        Spacer(Modifier.width(10.dp))
        Text(
            "J.A.R.V.I.S.",
            color = Bright,
            fontFamily = Orbitron,
            fontWeight = FontWeight.Black,
            fontSize = 18.sp,
            letterSpacing = 4.sp,
        )
        Spacer(Modifier.weight(1f))
        Text(clock, color = Accent, fontSize = 13.sp, letterSpacing = 2.sp)
        IconButton(onClick = onOpenSettings) {
            Icon(Icons.Filled.Settings, contentDescription = "Réglages", tint = Muted)
        }
    }

    HorizontalDivider(color = Accent.copy(alpha = 0.2f))
}

@Composable
private fun PulseDot() {
    val pulse by rememberInfiniteTransition(label = "pulse").animateFloat(
        initialValue = 0.35f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1200), RepeatMode.Reverse),
        label = "pulse",
    )

    Canvas(Modifier.size(18.dp)) {
        drawCircle(
            Brush.radialGradient(listOf(Accent.copy(alpha = 0.6f * pulse), Color.Transparent)),
            radius = size.minDimension / 2f,
        )
        drawCircle(Accent.copy(alpha = pulse), radius = 4.dp.toPx())
    }
}

@Composable
private fun StatusStrip(state: JarvisState) {
    val context = LocalContext.current
    var battery by remember { mutableIntStateOf(-1) }

    LaunchedEffect(Unit) {
        val manager = context.getSystemService(BatteryManager::class.java)
        while (true) {
            battery = manager?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1
            delay(60_000)
        }
    }

    val date = remember {
        SimpleDateFormat("dd MMM yyyy", Locale.FRANCE).format(Date()).uppercase(Locale.FRANCE)
    }

    Row(
        Modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            state.status,
            color = if (state == JarvisState.ERROR) Danger else Muted,
            fontSize = 10.sp,
            letterSpacing = 2.sp,
            maxLines = 1,
            modifier = Modifier.weight(1f),
        )
        Text(date, color = Muted, fontSize = 10.sp, letterSpacing = 1.sp, maxLines = 1)
        if (battery in 0..100) {
            Text("BAT $battery%", color = Muted, fontSize = 10.sp, letterSpacing = 1.sp, maxLines = 1)
        }
    }
}

// =============================================================
// NOYAU
// =============================================================

@Composable
private fun HudCore(state: JarvisState, modifier: Modifier) {
    val speed = when (state) {
        JarvisState.IDLE -> 1f
        JarvisState.LISTENING -> 1.8f
        JarvisState.THINKING, JarvisState.EXECUTING -> 3.5f
        JarvisState.SPEAKING -> 2f
        JarvisState.ERROR -> 0.4f
    }

    val currentSpeed by rememberUpdatedState(speed)
    var outer by remember { mutableFloatStateOf(0f) }
    var inner by remember { mutableFloatStateOf(0f) }

    LaunchedEffect(Unit) {
        var last = 0L
        while (true) {
            withFrameNanos { now ->
                if (last != 0L) {
                    val elapsed = (now - last) / 1_000_000_000f
                    outer = (outer + elapsed * 20f * currentSpeed) % 360f
                    inner = (inner - elapsed * 40f * currentSpeed) % 360f
                }
                last = now
            }
        }
    }

    val pulse by rememberInfiniteTransition(label = "halo").animateFloat(
        initialValue = 0.35f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1200), RepeatMode.Reverse),
        label = "halo",
    )

    val tint = if (state == JarvisState.ERROR) Danger else Accent

    BoxWithConstraints(modifier, contentAlignment = Alignment.Center) {
        val showLabel = maxHeight > 150.dp

        Canvas(Modifier.fillMaxSize()) {
            val scale = size.minDimension / 420f
            val c = center

            fun ring(
                radius: Float,
                width: Float,
                alpha: Float,
                dashes: FloatArray? = null,
                cap: StrokeCap = StrokeCap.Butt,
            ) {
                drawCircle(
                    color = tint.copy(alpha = alpha),
                    radius = radius * scale,
                    center = c,
                    style = Stroke(
                        width = width * scale * 1.4f,
                        cap = cap,
                        pathEffect = dashes?.let { d -> PathEffect.dashPathEffect(FloatArray(d.size) { d[it] * scale }) },
                    ),
                )
            }

            rotate(outer, c) {
                ring(204f, 1f, 0.18f)
                ring(204f, 2f, 1f, floatArrayOf(16f, 620f), StrokeCap.Round)
                ring(204f, 2f, 0.5f, floatArrayOf(4f, 40f))
            }

            rotate(inner, c) {
                ring(160f, 1f, 0.35f, floatArrayOf(2f, 10f))
                ring(128f, 1.5f, 0.5f, floatArrayOf(40f, 12f))
            }

            drawCircle(
                Brush.radialGradient(
                    listOf(tint.copy(alpha = 0.35f * pulse), tint.copy(alpha = 0.02f * pulse), Color.Transparent),
                    center = c,
                    radius = 100f * scale,
                ),
                radius = 100f * scale,
                center = c,
            )

            drawCircle(
                Brush.radialGradient(
                    0.6f to tint.copy(alpha = 0.3f),
                    1f to Color.Transparent,
                    center = c,
                    radius = 98f * scale,
                ),
                radius = 98f * scale,
                center = c,
            )

            drawCircle(Color(0xDC050B0F), radius = 72f * scale, center = c)
            drawCircle(tint, radius = 72f * scale, center = c, style = Stroke(1.dp.toPx()))
        }

        if (showLabel) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    "CORE",
                    color = tint,
                    fontFamily = Orbitron,
                    fontWeight = FontWeight.Medium,
                    fontSize = 9.sp,
                    letterSpacing = 2.sp,
                )
                Text(
                    state.word,
                    color = Bright,
                    fontFamily = Orbitron,
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp,
                    letterSpacing = 1.sp,
                )
            }
        }
    }
}

// =============================================================
// MODULES
// =============================================================

@Composable
private fun ModulesRow(
    modules: Modules,
    onOpenSettings: () -> Unit,
    onOpenAccessibility: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        ModuleChip("CERVEAU", modules.brain, Modifier.weight(1f), onOpenSettings)
        ModuleChip("WHATSAPP", modules.whatsapp, Modifier.weight(1f), onOpenAccessibility)
        ModuleChip("GMAIL", modules.gmail, Modifier.weight(1f), onOpenSettings)
        ModuleChip("PC", modules.pc, Modifier.weight(1f), onOpenSettings)
    }
}

@Composable
private fun ModuleChip(label: String, on: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(3.dp)

    Row(
        modifier
            .heightIn(min = 44.dp)
            .clip(shape)
            .background(if (on) Accent.copy(alpha = 0.08f) else Color.White.copy(alpha = 0.02f))
            .border(1.dp, if (on) Accent else TextColor.copy(alpha = 0.15f), shape)
            .clickable(role = Role.Button, onClick = onClick)
            .semantics { contentDescription = "$label : ${if (on) "actif" else "inactif"}" }
            .padding(horizontal = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            color = Color(0xFFDFF6FA),
            fontSize = 9.sp,
            letterSpacing = 1.sp,
            maxLines = 1,
            modifier = Modifier.weight(1f),
        )
        Box(
            Modifier
                .size(6.dp)
                .background(if (on) Accent else TextColor.copy(alpha = 0.25f), CircleShape)
        )
    }
}

// =============================================================
// CONVERSATION
// =============================================================

@Composable
private fun Conversation(messages: List<ChatMessage>, modifier: Modifier) {
    val listState = rememberLazyListState()

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }

    if (messages.isEmpty()) {
        Box(modifier, contentAlignment = Alignment.Center) {
            Text(
                "Dis « ouvre YouTube », « appelle Maman »\nou « lis mes derniers mails ».",
                color = Muted,
                fontSize = 12.sp,
                lineHeight = 18.sp,
                textAlign = TextAlign.Center,
            )
        }
        return
    }

    LazyColumn(
        modifier,
        state = listState,
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        items(messages, key = { it.id }) { MessageRow(it) }
    }
}

@Composable
private fun MessageRow(message: ChatMessage) {
    when (message.role) {
        MessageRole.USER -> Text(
            "> ${message.text}",
            color = Bright,
            fontSize = 14.sp,
            lineHeight = 20.sp,
        )

        MessageRole.JARVIS -> Column {
            Text(
                "JARVIS",
                color = Accent,
                fontFamily = Orbitron,
                fontWeight = FontWeight.Bold,
                fontSize = 10.sp,
                letterSpacing = 3.sp,
            )
            Spacer(Modifier.height(4.dp))
            SelectionContainer {
                Text(message.text, color = TextColor, fontSize = 14.sp, lineHeight = 20.sp)
            }
        }

        MessageRole.SYSTEM -> Row {
            Text(message.time, color = Accent.copy(alpha = 0.7f), fontSize = 11.sp)
            Spacer(Modifier.width(8.dp))
            Text(message.text, color = TextColor.copy(alpha = 0.7f), fontSize = 11.sp, lineHeight = 16.sp)
        }
    }
}

// =============================================================
// SIGNAL AUDIO
// =============================================================

@Composable
private fun Waveform(state: JarvisState, level: Float, modifier: Modifier) {
    val active = state == JarvisState.LISTENING || state == JarvisState.SPEAKING

    val amplitude by animateFloatAsState(if (active) 1f else 0.25f, tween(400), label = "amplitude")
    val micLevel by rememberUpdatedState(if (state == JarvisState.LISTENING) 0.35f + level * 0.65f else 1f)

    var time by remember { mutableFloatStateOf(0f) }

    LaunchedEffect(Unit) {
        while (true) withFrameNanos { time = it / 1_000_000_000f }
    }

    Canvas(modifier.semantics { contentDescription = "Signal audio" }) {
        val bars = 18
        val gap = 4.dp.toPx()
        val width = (size.width - gap * (bars - 1)) / bars

        for (i in 0 until bars) {
            val base = (25 + (i * 37) % 70) / 100f
            val wave = 0.5f + 0.5f * sin((time / 1.1f - i * 0.07f) * 2f * PI.toFloat())
            val height = max(3f, size.height * base * (0.2f + 0.8f * wave) * amplitude * micLevel)

            drawRoundRect(
                color = Accent.copy(alpha = 0.75f),
                topLeft = Offset(i * (width + gap), size.height - height),
                size = Size(width, height),
                cornerRadius = CornerRadius(2.dp.toPx()),
            )
        }
    }
}

// =============================================================
// BARRE DE COMMANDE
// =============================================================

@Composable
private fun CommandBar(
    value: String,
    onValueChange: (String) -> Unit,
    onSend: () -> Unit,
    listening: Boolean,
    onMic: () -> Unit,
) {
    val shape = RoundedCornerShape(4.dp)

    Row(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Accent.copy(alpha = 0.05f))
            .border(1.dp, Accent.copy(alpha = 0.3f), shape)
            .padding(start = 14.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(">", color = Accent, fontSize = 15.sp)
        Spacer(Modifier.width(10.dp))

        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier.weight(1f).semantics { contentDescription = "Commande" },
            textStyle = TextStyle(color = Bright, fontFamily = SpaceMono, fontSize = 14.sp),
            cursorBrush = SolidColor(Accent),
            maxLines = 4,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { onSend() }),
            decorationBox = { field ->
                Box {
                    if (value.isEmpty()) {
                        Text("Entrer une commande...", color = Muted, fontSize = 14.sp)
                    }
                    field()
                }
            },
        )

        Spacer(Modifier.width(8.dp))

        if (value.isNotBlank()) {
            HudIconButton("Envoyer", onSend) { sendGlyph(it) }
        } else {
            HudIconButton(
                if (listening) "Arrêter l'écoute" else "Parler à JARVIS",
                onMic,
                active = listening,
            ) { micGlyph(it) }
        }
    }
}

@Composable
private fun HudIconButton(
    label: String,
    onClick: () -> Unit,
    active: Boolean = false,
    glyph: DrawScope.(Color) -> Unit,
) {
    val shape = RoundedCornerShape(4.dp)

    Box(
        Modifier
            .size(48.dp)
            .clip(shape)
            .background(Accent.copy(alpha = if (active) 0.22f else 0.06f))
            .border(1.dp, Accent.copy(alpha = if (active) 1f else 0.45f), shape)
            .clickable(role = Role.Button, onClickLabel = label, onClick = onClick)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size(22.dp)) { glyph(Accent) }
    }
}

private fun DrawScope.micGlyph(color: Color) {
    val w = size.width
    val stroke = Stroke(width = w * 0.08f, cap = StrokeCap.Round)

    drawRoundRect(
        color,
        topLeft = Offset(w * 0.35f, w * 0.06f),
        size = Size(w * 0.3f, w * 0.52f),
        cornerRadius = CornerRadius(w * 0.15f),
        style = stroke,
    )
    drawArc(
        color,
        startAngle = 0f,
        sweepAngle = 180f,
        useCenter = false,
        topLeft = Offset(w * 0.2f, w * 0.2f),
        size = Size(w * 0.6f, w * 0.56f),
        style = stroke,
    )
    drawLine(color, Offset(w * 0.5f, w * 0.76f), Offset(w * 0.5f, w * 0.94f), strokeWidth = w * 0.08f, cap = StrokeCap.Round)
}

private fun DrawScope.sendGlyph(color: Color) {
    val w = size.width
    val path = Path().apply {
        moveTo(w * 0.12f, w * 0.18f)
        lineTo(w * 0.9f, w * 0.5f)
        lineTo(w * 0.12f, w * 0.82f)
        lineTo(w * 0.26f, w * 0.5f)
        close()
    }

    drawPath(path, color, style = Stroke(width = w * 0.08f, join = StrokeJoin.Round))
}

// =============================================================
// CONFIRMATION
// =============================================================

@Composable
private fun ConfirmDialog(request: ConfirmationRequest, onAnswer: (Boolean) -> Unit) {
    androidx.compose.material3.AlertDialog(
        onDismissRequest = { onAnswer(false) },
        containerColor = Surface,
        titleContentColor = Bright,
        textContentColor = TextColor,
        shape = RoundedCornerShape(6.dp),
        modifier = Modifier.border(1.dp, Accent.copy(alpha = 0.4f), RoundedCornerShape(6.dp)),
        title = { Text("Autoriser : ${request.label} ?", fontFamily = SpaceMono, fontSize = 15.sp) },
        text = { Text(request.details, fontFamily = SpaceMono, fontSize = 13.sp, lineHeight = 19.sp) },
        confirmButton = { HudButton("Autoriser", primary = true) { onAnswer(true) } },
        dismissButton = { HudButton("Refuser") { onAnswer(false) } },
    )
}

@Composable
fun HudButton(
    text: String,
    modifier: Modifier = Modifier,
    primary: Boolean = false,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(3.dp)

    Box(
        modifier
            .heightIn(min = 44.dp)
            .clip(shape)
            .background(Accent.copy(alpha = if (primary) 0.16f else 0.06f))
            .border(1.dp, if (primary) Accent else Accent.copy(alpha = 0.45f), shape)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(text, color = Bright, fontSize = 13.sp, textAlign = TextAlign.Center)
    }
}
