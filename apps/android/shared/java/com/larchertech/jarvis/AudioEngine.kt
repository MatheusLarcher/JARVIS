package com.larchertech.jarvis

import android.annotation.SuppressLint
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.media.SoundPool
import java.io.File
import java.net.URL
import kotlin.math.abs
import kotlin.math.min

// Captura contínua do microfone (16kHz mono PCM, frames de 80ms) + players.
class AudioEngine(private val cacheDir: File) {
    @Volatile private var recording = false
    private var thread: Thread? = null

    // acks locais: SoundPool = latência mínima
    private val pool = SoundPool.Builder().setMaxStreams(2)
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
        .build()
    private val ackIds = mutableListOf<Int>()
    private var player: MediaPlayer? = null

    @SuppressLint("MissingPermission")
    fun startMic(onFrame: (ByteArray, Int) -> Unit, onLevel: (Float) -> Unit) {
        if (recording) return
        recording = true
        thread = Thread {
            val minBuf = AudioRecord.getMinBufferSize(
                16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            val rec = AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION, 16000,
                AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                maxOf(minBuf, 1280 * 2 * 4))
            val buf = ByteArray(1280 * 2) // 80ms
            rec.startRecording()
            try {
                while (recording) {
                    var off = 0
                    while (off < buf.size && recording) {
                        val n = rec.read(buf, off, buf.size - off)
                        if (n <= 0) break
                        off += n
                    }
                    if (off == buf.size) {
                        var sum = 0L
                        var i = 0
                        while (i < buf.size) {
                            val s = (buf[i].toInt() and 0xFF) or (buf[i + 1].toInt() shl 8)
                            sum += abs(s.toShort().toInt()).toLong()
                            i += 8
                        }
                        onLevel(min(1f, (sum / (buf.size / 8f)) / 6000f))
                        onFrame(buf.copyOf(), buf.size)
                    }
                }
            } finally {
                rec.stop(); rec.release()
            }
        }.apply { priority = Thread.MAX_PRIORITY; start() }
    }

    fun stopMic() {
        recording = false
        thread?.join(500)
    }

    // baixa os acks uma vez e carrega no SoundPool (toque instantâneo, sem rede)
    fun preloadAcks(acks: List<Pair<String, String>>) {
        Thread {
            synchronized(ackIds) {
                ackIds.forEach { pool.unload(it) }
                ackIds.clear()
                for ((name, url) in acks) {
                    try {
                        val f = File(cacheDir, "ack_$name")
                        if (!f.exists()) f.writeBytes(URL(url).readBytes())
                        ackIds.add(pool.load(f.absolutePath, 1))
                    } catch (_: Exception) { }
                }
            }
        }.start()
    }

    fun playAck() {
        synchronized(ackIds) {
            if (ackIds.isNotEmpty()) pool.play(ackIds.random(), 1f, 1f, 1, 0, 1f)
        }
    }

    fun playUrl(url: String, onDone: () -> Unit) {
        player?.release()
        player = MediaPlayer().apply {
            setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ASSISTANT)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            setDataSource(url)
            setOnPreparedListener { start() }
            setOnCompletionListener { onDone() }
            setOnErrorListener { _, _, _ -> onDone(); true }
            prepareAsync()
        }
    }
}
