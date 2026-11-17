package com.fusionlab.fusionmusic

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.core.view.WindowCompat
import com.fusionlab.fusionmusic.ui.MainScreen
import com.fusionlab.fusionmusic.ui.theme.FusionTheme
import com.fusionlab.fusionmusic.ui.theme.parseAccent

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001)
        }
        if (Build.VERSION.SDK_INT <= Build.VERSION_CODES.P &&
            checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), 1002)
        }

        val container = (application as FusionApplication).container
        if (container.downloadRepository.hasQueued()) {
            container.downloadRepository.startService()
        }

        setContent {
            val revision by container.config.revisions.collectAsState()
            val accent = remember(revision) {
                parseAccent(container.config.getString("appearance.accent", "#6C4DF6"))
            }
            val themeMode = remember(revision) {
                container.config.getString("appearance.theme", "auto")
            }
            val systemDark = isSystemInDarkTheme()
            val dark = when (themeMode) {
                "dark" -> true
                "light" -> false
                else -> systemDark
            }
            SideEffect {
                WindowCompat.getInsetsController(window, window.decorView).apply {
                    isAppearanceLightStatusBars = !dark
                    isAppearanceLightNavigationBars = !dark
                }
            }
            FusionTheme(accent = accent, darkTheme = dark) {
                MainScreen(container)
            }
        }
    }
}
