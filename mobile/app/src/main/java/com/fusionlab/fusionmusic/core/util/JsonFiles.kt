package com.fusionlab.fusionmusic.core.util

import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import java.io.File
import java.io.FileOutputStream

object JsonFiles {
    val pretty: Json = Json {
        prettyPrint = true
        prettyPrintIndent = " "
        ignoreUnknownKeys = true
        encodeDefaults = true
        explicitNulls = false
    }

    val compact: Json = Json {
        prettyPrint = false
        ignoreUnknownKeys = true
        encodeDefaults = true
        explicitNulls = false
    }

    inline fun <reified T> read(file: File, default: T, json: Json = pretty): T {
        if (!file.exists()) return default
        return try {
            json.decodeFromString<T>(file.readText(Charsets.UTF_8))
        } catch (_: Exception) {
            backupCorrupt(file)
            default
        }
    }

    inline fun <reified T> writeAtomic(file: File, value: T, json: Json = pretty) {
        writeTextAtomic(file, json.encodeToString(value))
    }

    fun readElement(file: File, default: JsonElement): JsonElement {
        if (!file.exists()) return default
        return try {
            pretty.parseToJsonElement(file.readText(Charsets.UTF_8))
        } catch (_: Exception) {
            backupCorrupt(file)
            default
        }
    }

    fun writeElementAtomic(file: File, value: JsonElement) {
        writeTextAtomic(file, pretty.encodeToString(JsonElement.serializer(), value))
    }

    fun writeTextAtomic(file: File, text: String) {
        val parent = file.parentFile
        parent?.mkdirs()
        val temp = File(parent, file.name + ".tmp")
        try {
            FileOutputStream(temp).use { stream ->
                stream.write(text.toByteArray(Charsets.UTF_8))
                stream.fd.sync()
            }
            if (file.exists() && !file.delete()) {
                // Fall through to copyTo when delete fails (e.g. Windows file lock).
            }
            if (!temp.renameTo(file)) {
                temp.copyTo(file, overwrite = true)
                temp.delete()
            }
        } catch (error: Exception) {
            temp.delete()
            throw error
        }
    }

    fun backupCorrupt(file: File) {
        try {
            if (!file.exists()) return
            val target = File(file.parentFile, file.name + ".corrupt")
            if (target.exists()) target.delete()
            file.renameTo(target)
        } catch (_: Exception) {
            // Preserve the original if it cannot be moved.
        }
    }
}
