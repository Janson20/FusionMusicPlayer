package com.fusionlab.fusionmusic.data.update

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import com.fusionlab.fusionmusic.FusionApplication

/**
 * PackageInstaller 的回调。系统会通过 PendingIntent 把安装结果发到这里；
 * 需要用户确认时会额外给一个 Intent，必须由界面线程启动。
 */
class UpdateInstallReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)
        val message = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE).orEmpty()
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            @Suppress("DEPRECATION")
            val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT)
            if (confirm != null) {
                try {
                    confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(confirm)
                } catch (_: Exception) {
                    // 安装确认界面打不开时，下面的状态回调仍会给出原因。
                }
            }
        }
        val application = context.applicationContext as? FusionApplication ?: return
        application.container.updateRepository.onInstallResult(status, message)
    }

    companion object {
        const val ACTION_STATUS = "com.fusionlab.fusionmusic.UPDATE_INSTALL_STATUS"
        const val EXTRA_SESSION_ID = "session_id"
    }
}
