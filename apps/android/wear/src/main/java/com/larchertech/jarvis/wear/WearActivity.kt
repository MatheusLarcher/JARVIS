package com.larchertech.jarvis.wear

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
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
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.larchertech.jarvis.AudioEngine
import com.larchertech.jarvis.JarvisClient
import com.larchertech.jarvis.Prefs
import com.larchertech.jarvis.Reactor
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val CYAN = Color(0xFF21D4F3)
private val BG = Color(0xFF000508)

// Relógio: mic SÓ sob demanda — toca no reator pra falar; para quando volta a IDLE.
class WearActivity : ComponentActivity(), JarvisClient.Listener {
    private lateinit var prefs: Prefs
    private lateinit var audio: AudioEngine
    private var client: JarvisClient? = null

    private val uiState = mutableStateOf("IDLE")
    private val uiOnline = mutableStateOf(false)
    private val uiAnswer = mutableStateOf("")
    private val uiLevel = mutableStateOf(0f)
    private val uiConfigured = mutableStateOf(false)
    @Volatile private var micActive = false

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        audio = AudioEngine(cacheDir)
        uiConfigured.value = prefs.configured
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (prefs.configured) start()
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) !=
            PackageManager.PERMISSION_GRANTED)
            micPermission.launch(Manifest.permission.RECORD_AUDIO)
        setContent { Root() }
    }

    private fun start() {
        if (client == null) {
            client = JarvisClient(prefs, this)
            client!!.connect()
        }
    }

    private fun startTalking() {
        if (!micActive && client?.connected == true &&
            checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
            PackageManager.PERMISSION_GRANTED) {
            micActive = true
            audio.playAck()
            client?.sendMicOpen()
            audio.startMic(
                onFrame = { buf, len -> client?.sendAudio(buf, len) },
                onLevel = { lvl -> runOnUiThread { uiLevel.value = lvl } })
        }
    }

    private fun stopTalking() {
        if (micActive) {
            micActive = false
            audio.stopMic()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        stopTalking()
        client?.disconnect()
    }

    // ==== listener ====
    override fun onConnected(ackSounds: List<Pair<String, String>>) {
        audio.preloadAcks(ackSounds)
        runOnUiThread { uiOnline.value = true }
    }

    override fun onDisconnected() = runOnUiThread {
        uiOnline.value = false; uiState.value = "IDLE"; stopTalking()
    }

    override fun onWake() { /* wake word não roda no relógio */ }

    override fun onState(state: String) = runOnUiThread {
        uiState.value = state
        if (state == "IDLE") stopTalking()
    }

    override fun onTranscript(text: String, final: Boolean) {}

    override fun onSpeak(text: String, audioUrl: String?) = runOnUiThread {
        uiAnswer.value = text
        if (audioUrl != null) audio.playUrl(audioUrl) {}
    }

    override fun onAmbient(temperatureC: Double?) {}

    // ==== UI ====
    @Composable
    private fun Root() {
        val configured by uiConfigured
        Box(Modifier.fillMaxSize().background(BG)) {
            if (!configured) Setup() else Stage()
        }
    }

    @Composable
    private fun Setup() {
        var host by rememberSaveable { mutableStateOf("192.168.0.100:8040") }
        var token by rememberSaveable { mutableStateOf("") }
        Column(Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            OutlinedTextField(host, { host = it }, label = { Text("Servidor") })
            OutlinedTextField(token, { token = it }, label = { Text("Token") })
            Button(onClick = {
                prefs.serverHost = host; prefs.deviceId = "galaxy-watch"; prefs.token = token
                if (prefs.configured) { uiConfigured.value = true; start() }
            }) { Text("OK") }
        }
    }

    @Composable
    private fun Stage() {
        val state by uiState
        val online by uiOnline
        val answer by uiAnswer
        val level by uiLevel
        var clock by remember { mutableStateOf("") }
        LaunchedEffect(Unit) {
            while (true) {
                clock = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())
                delay(5000)
            }
        }
        Box(Modifier.fillMaxSize().clickable(
            interactionSource = remember { MutableInteractionSource() }, indication = null) {
            if (state == "IDLE") startTalking()
        }) {
            Reactor(state, level, Modifier.fillMaxSize(0.9f).align(Alignment.Center))
            Text(clock, color = CYAN.copy(alpha = 0.85f), fontSize = 22.sp,
                fontFamily = FontFamily.Monospace,
                modifier = Modifier.align(Alignment.TopCenter).padding(top = 14.dp))
            if (answer.isNotEmpty())
                Text(answer, color = CYAN, fontSize = 11.sp,
                    modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 14.dp))
            if (!online)
                Text("●", color = Color(0xFF48505C), fontSize = 9.sp,
                    modifier = Modifier.align(Alignment.TopEnd).padding(10.dp))
        }
    }
}
