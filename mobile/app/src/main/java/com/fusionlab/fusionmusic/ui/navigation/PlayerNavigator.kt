package com.fusionlab.fusionmusic.ui.navigation

import androidx.compose.runtime.staticCompositionLocalOf

/** Opens the now-playing screen from any song row. */
data class PlayerNavigator(
    val open: () -> Unit
)

val LocalPlayerNavigator = staticCompositionLocalOf<PlayerNavigator?> { null }
