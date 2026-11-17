package com.fusionlab.fusionmusic.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.blur
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import java.io.File

@Composable
fun AppBackground(
    imagePath: String,
    opacity: Int,
    blurRadius: Int,
    scrim: Int
) {
    if (imagePath.isNotBlank() && File(imagePath).exists()) {
        AsyncImage(
            model = File(imagePath),
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier
                .fillMaxSize()
                .blur(blurRadius.coerceIn(0, 40).dp)
                .alpha((opacity.coerceIn(0, 100) / 100f))
        )
    }
    if (scrim > 0) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(Color.Black.copy(alpha = (scrim.coerceIn(0, 100) / 100f) * 0.65f))
        )
    }
}
