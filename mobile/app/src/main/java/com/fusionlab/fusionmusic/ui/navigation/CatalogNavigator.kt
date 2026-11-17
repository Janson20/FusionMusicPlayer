package com.fusionlab.fusionmusic.ui.navigation

import androidx.compose.runtime.staticCompositionLocalOf

data class CatalogNavigator(
    val openArtist: (id: String, name: String) -> Unit,
    val openAlbum: (id: String, name: String, artist: String) -> Unit
)

val LocalCatalogNavigator = staticCompositionLocalOf<CatalogNavigator?> { null }
