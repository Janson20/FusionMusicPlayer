package com.fusionlab.fusionmusic.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private fun lightScheme(accent: Color) = lightColorScheme(
    primary = accent,
    onPrimary = Color.White,
    primaryContainer = accent.copy(alpha = 0.16f),
    onPrimaryContainer = accent,
    secondary = Color(0xFF5B5B66),
    background = FusionBackgroundLight,
    onBackground = Color(0xFF1B1B1F),
    surface = FusionSurfaceLight,
    onSurface = Color(0xFF1B1B1F),
    surfaceVariant = Color(0xFFEDEBF4),
    onSurfaceVariant = Color(0xFF5A5866),
    outline = Color(0xFFC9C6D6),
    error = Color(0xFFB3261E)
)

private fun darkScheme(accent: Color) = darkColorScheme(
    primary = accent,
    onPrimary = Color.White,
    primaryContainer = accent.copy(alpha = 0.24f),
    onPrimaryContainer = Color(0xFFD8D0FF),
    secondary = Color(0xFFC8C5D4),
    background = FusionBackgroundDark,
    onBackground = Color(0xFFE8E6EF),
    surface = FusionSurfaceDark,
    onSurface = Color(0xFFE8E6EF),
    surfaceVariant = Color(0xFF292631),
    onSurfaceVariant = Color(0xFFC8C5D4),
    outline = Color(0xFF474350),
    error = Color(0xFFF2B8B5)
)

@Composable
fun FusionTheme(
    accent: Color = FusionPurple,
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    val scheme = if (darkTheme) darkScheme(accent) else lightScheme(accent)
    MaterialTheme(
        colorScheme = scheme,
        typography = Typography(),
        content = content
    )
}
