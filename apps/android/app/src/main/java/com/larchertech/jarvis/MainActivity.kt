package com.larchertech.jarvis

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.random.Random

private val CYAN = Color(0xFF21D4F3)
private val BG = Color(0xFF000508)

class MainActivity : ComponentActivity(), JarvisClient.Listener {
    private lateinit var prefs: Prefs
    private lateinit var audio: AudioEngine
    private var client: JarvisClient? = null

    private val uiState = mutableStateOf("IDLE")
    private val uiOnline = mutableStateOf(false)
    private val uiHeard = mutableStateOf("")
    private val uiAnswer = mutableStateOf("")
    private val uiTemp = mutableStateOf<Double?>(null)
    private val uiLevel = mutableStateOf(0f)
    private val uiConfigured = mutableStateOf(false)

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) startPipeline()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        audio = AudioEngine(cacheDir)
        uiConfigured.value = prefs.configured

        // tela sempre ligada + imersivo + cutout
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val ctrl = WindowInsetsControllerCompat(window, window.decorView)
        ctrl.hide(WindowInsetsCompat.Type.systemBars())
        ctrl.systemBarsBehavior =
            WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            window.attributes.layoutInDisplayCutoutMode =
                WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_ALWAYS
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            window.attributes.layoutInDisplayCutoutMode =
                WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES
        }

        setContent { Root() }
        if (prefs.configured) ensureMicAndStart()
    }

    private fun ensureMicAndStart() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED) startPipeline()
        else micPermission.launch(Manifest.permission.RECORD_AUDIO)
    }

    private fun startPipeline() {
        if (client != null) return
        client = JarvisClient(prefs, this)
        client!!.connect()
        audio.startMic(
            onFrame = { buf, len -> client?.sendAudio(buf, len) },
            onLevel = { lvl -> runOnUiThread { uiLevel.value = lvl } })
    }

    override fun onDestroy() {
        super.onDestroy()
        audio.stopMic()
        client?.disconnect()
    }

    private fun setBrightness(active: Boolean) {
        val lp = window.attributes
        lp.screenBrightness = if (active) 1.0f else 0.08f
        window.attributes = lp
    }

    // ==== JarvisClient.Listener (threads do OkHttp → UI thread) ====
    override fun onConnected(ackSounds: List<Pair<String, String>>) {
        audio.preloadAcks(ackSounds)
        runOnUiThread { uiOnline.value = true }
    }

    override fun onDisconnected() = runOnUiThread {
        uiOnline.value = false; uiState.value = "IDLE"; setBrightness(false)
    }

    override fun onWake() = runOnUiThread {
        uiHeard.value = ""; uiAnswer.value = ""
        setBrightness(true)                   // reator acende na hora
    }

    // só toca quando a pessoa chamou e parou; se o comando veio na mesma
    // frase, o servidor não manda ack e o Jarvis já responde direto
    override fun onAck() = runOnUiThread { audio.playAck() }

    override fun onState(state: String) = runOnUiThread {
        uiState.value = state
        setBrightness(state != "IDLE")
    }

    override fun onTranscript(text: String, final: Boolean) = runOnUiThread {
        uiHeard.value = text
    }

    override fun onSpeak(text: String, audioUrl: String?) = runOnUiThread {
        uiAnswer.value = text
        if (audioUrl != null) audio.playUrl(audioUrl) {}
    }

    override fun onAmbient(temperatureC: Double?) = runOnUiThread {
        if (temperatureC != null) uiTemp.value = temperatureC
    }

    // ==== UI ====
    @Composable
    private fun Root() {
        val configured by uiConfigured
        Box(Modifier.fillMaxSize().background(BG)) {
            if (!configured) SetupScreen() else Stage()
        }
    }

    @Composable
    private fun SetupScreen() {
        var host by rememberSaveable { mutableStateOf(prefs.serverHost.ifEmpty { "192.168.0.100:8040" }) }
        var device by rememberSaveable { mutableStateOf(prefs.deviceId.ifEmpty { "tablet-sala" }) }
        var token by rememberSaveable { mutableStateOf(prefs.token) }
        var room by rememberSaveable { mutableStateOf(prefs.room) }
        Column(
            Modifier.fillMaxSize().padding(32.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
        ) {
            Text("J A R V I S", color = CYAN, fontSize = 28.sp,
                modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
            OutlinedTextField(host, { host = it }, label = { Text("Servidor (ip:porta)") },
                modifier = Modifier.fillMaxWidth())
            OutlinedTextField(device, { device = it }, label = { Text("Device ID") },
                modifier = Modifier.fillMaxWidth())
            OutlinedTextField(token, { token = it }, label = { Text("Token") },
                modifier = Modifier.fillMaxWidth())
            OutlinedTextField(room, { room = it }, label = { Text("Cômodo (opcional)") },
                modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                prefs.serverHost = host; prefs.deviceId = device
                prefs.token = token; prefs.room = room
                if (prefs.configured) { uiConfigured.value = true; ensureMicAndStart() }
            }, modifier = Modifier.fillMaxWidth()) { Text("Conectar") }
        }
    }

    @Composable
    private fun Stage() {
        val state by uiState
        val online by uiOnline
        val heard by uiHeard
        val answer by uiAnswer
        val temp by uiTemp
        val level by uiLevel

        var clock by remember { mutableStateOf("") }
        var date by remember { mutableStateOf("") }
        var driftX by remember { mutableStateOf(0) }
        var driftY by remember { mutableStateOf(0) }
        LaunchedEffect(Unit) {
            while (true) {
                clock = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
                date = SimpleDateFormat("EEEE, d 'de' MMMM", Locale("pt", "BR")).format(Date())
                delay(5000)
            }
        }
        LaunchedEffect(Unit) {   // anti burn-in
            while (true) {
                delay(60_000)
                driftX = Random.nextInt(-8, 9); driftY = Random.nextInt(-5, 6)
            }
        }

        val idle = state == "IDLE"
        Box(Modifier.fillMaxSize()) {
            Reactor(state, level,
                Modifier.fillMaxSize(0.72f).align(Alignment.Center)
                    .clickable(interactionSource = remember { MutableInteractionSource() },
                        indication = null) {
                        // toque no reator = falar sem wake word (push-to-talk)
                        if (state == "IDLE") { audio.playAck(); client?.sendMicOpen() }
                    })

            Column(
                Modifier.align(Alignment.TopCenter).padding(top = 48.dp).fillMaxWidth(0.85f),
                horizontalAlignment = Alignment.CenterHorizontally) {
                if (heard.isNotEmpty())
                    Text("“$heard”", color = Color(0xFFAEE6F2), fontSize = 18.sp,
                        textAlign = TextAlign.Center)
                if (answer.isNotEmpty())
                    Text(answer, color = CYAN, fontSize = 18.sp, textAlign = TextAlign.Center)
            }

            Column(
                Modifier.align(Alignment.BottomCenter)
                    .padding(bottom = 40.dp)
                    .offset(driftX.dp, driftY.dp)
                    .fillMaxWidth(),
                horizontalAlignment = Alignment.CenterHorizontally) {
                Text(clock, color = CYAN.copy(alpha = if (idle) 0.8f else 1f),
                    fontSize = 46.sp, fontFamily = FontFamily.Monospace)
                Text(date, color = Color(0xFF7FB6C4), fontSize = 15.sp)
                temp?.let {
                    Text(String.format(Locale("pt", "BR"), "%.1f °C", it),
                        color = Color(0xFF5C8996), fontSize = 14.sp)
                }
            }

            Text(if (online) "● ONLINE" else "● RECONECTANDO",
                color = if (online) CYAN.copy(alpha = 0.7f) else Color(0xFF48505C),
                fontSize = 10.sp, letterSpacing = 3.sp,
                modifier = Modifier.align(Alignment.TopEnd).padding(16.dp))
        }
    }
}
