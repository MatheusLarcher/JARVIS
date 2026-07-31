package com.larchertech.jarvis

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

private val CYAN = Color(0xFF21D4F3)
private val GREEN = Color(0xFF48E29B)
private val RED = Color(0xFFFF5252)

// Reator central: mesma linguagem visual da web, portada pra Compose Canvas.
@Composable
fun Reactor(state: String, level: Float, modifier: Modifier = Modifier) {
    var t by remember { mutableFloatStateOf(0f) }
    var stateT by remember { mutableFloatStateOf(0f) }
    var lastState by remember { mutableFloatStateOf(0f) } // hash simples do estado
    var colorMix by remember { mutableFloatStateOf(0f) }

    LaunchedEffect(Unit) {
        var last = System.nanoTime()
        while (true) {
            androidx.compose.runtime.withFrameNanos { now ->
                val dt = min(0.05f, (now - last) / 1e9f)
                last = now
                t += dt
                stateT += dt
                val target = if (state == "DONE" || state == "ERROR")
                    max(0f, 1f - stateT / 1.6f) else 0f
                colorMix += (target - colorMix) * min(1f, dt * 6f)
            }
        }
    }
    LaunchedEffect(state) { stateT = 0f }

    val special = when (state) { "DONE" -> GREEN; "ERROR" -> RED; else -> CYAN }
    fun mixc(a: Color, b: Color, f: Float) = Color(
        a.red + (b.red - a.red) * f, a.green + (b.green - a.green) * f,
        a.blue + (b.blue - a.blue) * f)
    val c = mixc(CYAN, special, colorMix)

    val glow = when (state) {
        "LISTENING" -> 0.75f + level * 0.5f
        "THINKING" -> 0.7f + 0.12f * sin(t * 3f)
        "EXECUTING" -> 0.85f + 0.15f * sin(t * 6f)
        "DONE", "ERROR" -> 0.9f
        else -> 0.35f + 0.08f * sin(t * 0.9f)
    }

    Canvas(modifier) {
        val s = min(size.width, size.height)
        val cx = size.width / 2f
        val cy = size.height / 2f
        val r = s * 0.32f

        // halo + núcleo
        drawCircle(
            Brush.radialGradient(
                0f to c.copy(alpha = 0.16f * glow), 0.55f to c.copy(alpha = 0.05f * glow),
                1f to Color.Transparent, center = Offset(cx, cy), radius = r * 2.1f),
            radius = r * 2.1f, center = Offset(cx, cy))
        drawCircle(
            Brush.radialGradient(
                0f to Color(0xFFDCFAFF).copy(alpha = 0.9f * glow),
                0.35f to c.copy(alpha = 0.55f * glow), 1f to Color.Transparent,
                center = Offset(cx, cy), radius = r * 0.55f),
            radius = r * 0.55f, center = Offset(cx, cy))

        // anel principal
        val breathe = if (state == "LISTENING") level * s * 0.012f else sin(t * 0.9f) * s * 0.004f
        drawCircle(c.copy(alpha = 0.85f * glow), radius = r + breathe,
            center = Offset(cx, cy), style = Stroke(max(2f, s * 0.008f)))

        // segmentos internos
        val segSpin = when (state) {
            "THINKING" -> t * 2.2f; "EXECUTING" -> t * 4f; else -> t * 0.15f
        } * (180f / PI.toFloat())
        rotate(segSpin, Offset(cx, cy)) {
            for (i in 0 until 10) {
                drawArc(
                    c.copy(alpha = (0.25f + 0.55f * ((i % 3) / 2f)) * glow),
                    startAngle = i * 36f, sweepAngle = 23f, useCenter = false,
                    topLeft = Offset(cx - r * 0.78f, cy - r * 0.78f),
                    size = androidx.compose.ui.geometry.Size(r * 1.56f, r * 1.56f),
                    style = Stroke(max(2f, s * 0.014f)))
            }
        }

        // anéis externos girando ao contrário
        val spin2 = (if (state == "THINKING") -t * 1.4f else -t * 0.1f) * (180f / PI.toFloat())
        rotate(spin2, Offset(cx, cy)) {
            for (i in 0 until 3) {
                drawArc(
                    c.copy(alpha = 0.5f * glow),
                    startAngle = i * 120f, sweepAngle = 90f, useCenter = false,
                    topLeft = Offset(cx - r * 1.22f, cy - r * 1.22f),
                    size = androidx.compose.ui.geometry.Size(r * 2.44f, r * 2.44f),
                    style = Stroke(max(1f, s * 0.004f)))
            }
        }

        // EXECUTING: partículas fluindo
        if (state == "EXECUTING") {
            for (i in 0 until 14) {
                val p = (t * 0.6f + i / 14f) % 1f
                val ang = (i / 14f) * 2f * PI.toFloat() + t * 0.5f
                val rr = r * (0.6f + p * 0.9f)
                drawCircle(c.copy(alpha = (1f - p) * 0.7f), radius = s * 0.004f,
                    center = Offset(cx + cos(ang) * rr, cy + sin(ang) * rr))
            }
        }
    }
}
