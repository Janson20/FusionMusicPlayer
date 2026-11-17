package com.fusionlab.fusionmusic.ui.theme

import androidx.compose.ui.graphics.Color

val FusionPurple = Color(0xFF6C4DF6)
val FusionBackgroundLight = Color(0xFFF6F5FA)
val FusionSurfaceLight = Color(0xFFFFFFFF)
val FusionBackgroundDark = Color(0xFF111014)
val FusionSurfaceDark = Color(0xFF1A1820)

fun parseAccent(hex: String): Color {
    return try {
        val clean = hex.trim().removePrefix("#")
        val value = when (clean.length) {
            6 -> 0xFF000000L or clean.toLong(16)
            8 -> clean.toLong(16)
            else -> 0xFF6C4DF6L
        }
        Color(value)
    } catch (_: Exception) {
        FusionPurple
    }
}
