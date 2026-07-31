package com.larchertech.jarvis

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit

// Cliente WebSocket do gateway: reconexão automática + envio de PCM binário.
class JarvisClient(
    private val prefs: Prefs,
    private val listener: Listener,
) {
    interface Listener {
        fun onConnected(ackSounds: List<Pair<String, String>>)
        fun onDisconnected()
        fun onWake()
        fun onState(state: String)
        fun onTranscript(text: String, final: Boolean)
        fun onSpeak(text: String, audioUrl: String?)
        fun onAmbient(temperatureC: Double?)
    }

    private val http = OkHttpClient.Builder()
        .pingInterval(15, TimeUnit.SECONDS)
        .build()
    private var ws: WebSocket? = null
    @Volatile private var wantConnected = false
    @Volatile var connected = false; private set

    fun baseUrl() = "http://${prefs.serverHost}"

    fun connect() {
        wantConnected = true
        open()
    }

    fun disconnect() {
        wantConnected = false
        ws?.close(1000, null)
    }

    private fun open() {
        if (!wantConnected || !prefs.configured) return
        val url = "ws://${prefs.serverHost}/ws/${prefs.deviceId}?token=${prefs.token}"
        val req = Request.Builder().url(url).build()
        ws = http.newWebSocket(req, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                connected = true
                val hello = JSONObject()
                    .put("type", "hello")
                    .put("device_type", if (prefs.deviceId.contains("tablet")) "tablet" else "phone")
                if (prefs.room.isNotEmpty()) hello.put("room", prefs.room)
                webSocket.send(hello.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handle(JSONObject(text))
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.w("JarvisClient", "ws falhou: ${t.message}")
                connected = false
                listener.onDisconnected()
                retry()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                connected = false
                listener.onDisconnected()
                retry()
            }
        })
    }

    private fun retry() {
        if (!wantConnected) return
        Thread {
            Thread.sleep(2000)
            if (wantConnected && !connected) open()
        }.start()
    }

    private fun handle(msg: JSONObject) {
        when (msg.optString("type")) {
            "hello_ok" -> {
                val acks = mutableListOf<Pair<String, String>>()
                val arr = msg.optJSONArray("ack_sounds")
                if (arr != null) for (i in 0 until arr.length()) {
                    val o = arr.getJSONObject(i)
                    acks.add(o.getString("name") to baseUrl() + o.getString("url"))
                }
                listener.onConnected(acks)
            }
            "wake" -> listener.onWake()
            "state" -> listener.onState(msg.optString("state", "IDLE"))
            "stt_partial" -> listener.onTranscript(msg.optString("text"), false)
            "stt_final" -> listener.onTranscript(msg.optString("text"), true)
            "speak" -> listener.onSpeak(
                msg.optString("text"),
                msg.optString("audio_url", "").ifEmpty { null }?.let { baseUrl() + it })
            "ambient" -> listener.onAmbient(
                if (msg.isNull("temperature_c")) null else msg.optDouble("temperature_c"))
        }
    }

    fun sendAudio(pcm: ByteArray, len: Int) {
        if (connected) ws?.send(pcm.toByteString(0, len))
    }

    fun sendMicOpen() {
        if (connected) ws?.send(JSONObject().put("type", "mic_open").toString())
    }

    fun sendContext(network: String?) {
        if (!connected) return
        val o = JSONObject().put("type", "context")
        if (network != null) o.put("network", network)
        ws?.send(o.toString())
    }
}
