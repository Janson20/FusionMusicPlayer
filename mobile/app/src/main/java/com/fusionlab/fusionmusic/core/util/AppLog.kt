package com.fusionlab.fusionmusic.core.util

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStreamWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class AppLog(context: Context) {
    private val logDir = File(context.filesDir, "data/logs").apply { mkdirs() }
    private val logFile = File(logDir, "fusion.log")
    private val lock = Any()
    private val stamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)

    fun d(tag: String, message: String) = write("D", tag, message)
    fun i(tag: String, message: String) = write("I", tag, message)
    fun w(tag: String, message: String) = write("W", tag, message)
    fun e(tag: String, message: String) = write("E", tag, message)
    fun e(tag: String, message: String, error: Throwable) = write("E", tag, message + "\n" + Log.getStackTraceString(error))

    private fun write(level: String, tag: String, message: String) {
        when (level) {
            "E" -> Log.e(tag, message)
            "W" -> Log.w(tag, message)
            "D" -> Log.d(tag, message)
            else -> Log.i(tag, message)
        }
        val line = stamp.format(Date()) + " " + level + " " + tag + " " + message + "\n"
        synchronized(lock) {
            try {
                if (logFile.length() > MAX_BYTES) rotate()
                FileOutputStream(logFile, true).use { stream ->
                    OutputStreamWriter(stream, Charsets.UTF_8).use { it.write(line) }
                }
            } catch (_: Exception) {
                // Logging must never take the app down.
            }
        }
    }

    private fun rotate() {
        val oldest = File(logDir, "fusion.3.log")
        if (oldest.exists()) oldest.delete()
        for (index in 2 downTo 0) {
            val from = File(logDir, if (index == 0) "fusion.log" else "fusion." + index + ".log")
            val to = File(logDir, "fusion." + (index + 1) + ".log")
            if (from.exists()) from.renameTo(to)
        }
    }

    fun shareFile(): File = logFile

    private companion object {
        const val MAX_BYTES = 2L * 1024L * 1024L
    }
}
