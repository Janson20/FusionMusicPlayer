package com.fusionlab.fusionmusic

import android.app.Application

class FusionApplication : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
        container.updateRepository.maybeAutoCheck()
    }
}
