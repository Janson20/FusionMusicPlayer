package com.fusionlab.fusionmusic.data.config

import android.content.Context
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.io.FileOutputStream

class ConfigRepository(
    context: Context,
    private val scope: CoroutineScope
) {
    private val dataDir = File(context.filesDir, "data").apply { mkdirs() }
    private val file = File(dataDir, "config.json")
    private val temp = File(dataDir, "config.json.tmp")
    private val json = Json {
        prettyPrint = true
        prettyPrintIndent = "  "
        ignoreUnknownKeys = true
        explicitNulls = false
    }
    private val lock = Any()
    private val saveLock = Any()
    private var saveJob: Job? = null
    private var loadedRoot: JsonObject = ConfigDefaults.DEFAULTS
    private val revisionState = MutableStateFlow(0L)

    val revisions: StateFlow<Long> = revisionState

    init {
        load()
    }

    fun getJson(path: String, fallback: JsonElement = JsonNull): JsonElement = synchronized(lock) {
        nodeAt(loadedRoot, path) ?: fallback
    }

    fun has(path: String): Boolean = synchronized(lock) { nodeAt(loadedRoot, path) != null }

    fun getString(path: String, fallback: String = ""): String {
        val value = getJson(path)
        return if (value is JsonPrimitive && value.isString) value.content else fallback
    }

    fun getInt(path: String, fallback: Int = 0): Int {
        val value = getJson(path)
        return if (value is JsonPrimitive) value.intOrNull ?: fallback else fallback
    }

    fun getLong(path: String, fallback: Long = 0L): Long {
        val value = getJson(path)
        return if (value is JsonPrimitive) value.doubleOrNull?.toLong() ?: fallback else fallback
    }

    fun getDouble(path: String, fallback: Double = 0.0): Double {
        val value = getJson(path)
        return if (value is JsonPrimitive) value.doubleOrNull ?: fallback else fallback
    }

    fun getBoolean(path: String, fallback: Boolean = false): Boolean {
        val value = getJson(path)
        return if (value is JsonPrimitive) value.booleanOrNull ?: fallback else fallback
    }

    fun getStringList(path: String): List<String> {
        val value = getJson(path)
        if (value !is JsonArray) return emptyList()
        return value.mapNotNull { item ->
            if (item is JsonPrimitive && item.isString) item.content else null
        }
    }

    fun getObject(path: String): JsonObject? {
        val value = getJson(path)
        return value as? JsonObject
    }

    fun set(path: String, value: JsonElement) {
        synchronized(lock) {
            loadedRoot = putAt(loadedRoot, path.split('.').filter { it.isNotBlank() }, 0, value)
        }
        touch()
    }

    fun setString(path: String, value: String) = set(path, JsonPrimitive(value))

    fun setInt(path: String, value: Int) = set(path, JsonPrimitive(value))

    fun setLong(path: String, value: Long) = set(path, JsonPrimitive(value))

    fun setDouble(path: String, value: Double) = set(path, JsonPrimitive(value))

    fun setBoolean(path: String, value: Boolean) = set(path, JsonPrimitive(value))

    fun setStringList(path: String, values: List<String>) {
        set(path, JsonArray(values.map { JsonPrimitive(it) }))
    }

    fun remove(path: String) {
        synchronized(lock) {
            loadedRoot = removeAt(loadedRoot, path.split('.').filter { it.isNotBlank() }, 0)
        }
        touch()
    }

    fun snapshot(): JsonObject = synchronized(lock) { loadedRoot }

    fun resetAll() {
        synchronized(lock) { loadedRoot = ConfigDefaults.DEFAULTS }
        touch()
    }

    fun flushNow() {
        saveJob?.cancel()
        scope.launch(Dispatchers.IO) { saveToDisk() }
    }

    fun saveNowBlocking() {
        saveJob?.cancel()
        saveToDisk()
    }

    private fun touch() {
        val next = revisionState.value + 1
        revisionState.value = next
        saveJob?.cancel()
        saveJob = scope.launch {
            delay(300)
            saveToDisk()
        }
    }

    private fun load() {
        synchronized(lock) {
            if (!file.exists()) {
                loadedRoot = ConfigDefaults.DEFAULTS
                scheduleInitialWrite()
                return
            }
            try {
                val parsed = json.parseToJsonElement(file.readText(Charsets.UTF_8))
                val objectValue = parsed as? JsonObject
                    ?: throw IllegalArgumentException("config root is not an object")
                loadedRoot = mergeObjects(ConfigDefaults.DEFAULTS, objectValue)
            } catch (error: Exception) {
                backupCorrupt()
                loadedRoot = ConfigDefaults.DEFAULTS
                scheduleInitialWrite()
            }
        }
    }

    private fun scheduleInitialWrite() {
        saveJob?.cancel()
        saveJob = scope.launch {
            delay(100)
            saveToDisk()
        }
    }

    private fun backupCorrupt() {
        try {
            val target = File(dataDir, "config.json.corrupt")
            if (target.exists()) target.delete()
            file.renameTo(target)
        } catch (_: Exception) {
            // keep the original file if it cannot be moved
        }
    }

    private fun saveToDisk() {
        val text = synchronized(lock) { json.encodeToString(JsonObject.serializer(), loadedRoot) }
        synchronized(saveLock) {
            try {
                FileOutputStream(temp).use { stream ->
                    stream.write(text.toByteArray(Charsets.UTF_8))
                    stream.fd.sync()
                }
                if (file.exists() && !file.delete()) {
                    // renameTo can still succeed on some file systems; fall through
                }
                if (!temp.renameTo(file)) {
                    temp.copyTo(file, overwrite = true)
                    temp.delete()
                }
            } catch (_: Exception) {
                // Config writes must not crash the app; the next change retries.
            }
        }
    }

    private fun nodeAt(root: JsonObject, path: String): JsonElement? {
        var current: JsonElement = root
        for (part in path.split('.')) {
            if (part.isBlank()) continue
            val objectValue = current as? JsonObject ?: return null
            current = objectValue[part] ?: return null
        }
        return current
    }

    private fun putAt(root: JsonObject, parts: List<String>, index: Int, value: JsonElement): JsonObject {
        if (index >= parts.size) return value as? JsonObject ?: root
        val key = parts[index]
        val child = root[key]
        val next = if (index == parts.size - 1) {
            value
        } else {
            putAt(child as? JsonObject ?: JsonObject(emptyMap()), parts, index + 1, value)
        }
        val copy = LinkedHashMap<String, JsonElement>(root)
        copy[key] = next
        return JsonObject(copy)
    }

    private fun removeAt(root: JsonObject, parts: List<String>, index: Int): JsonObject {
        if (parts.isEmpty()) return root
        val key = parts[index]
        val copy = LinkedHashMap<String, JsonElement>(root)
        if (index == parts.size - 1) {
            copy.remove(key)
        } else {
            val child = root[key] as? JsonObject ?: return root
            copy[key] = removeAt(child, parts, index + 1)
        }
        return JsonObject(copy)
    }

    private fun mergeObjects(base: JsonObject, override: JsonObject): JsonObject {
        val merged = LinkedHashMap<String, JsonElement>(base)
        for ((key, value) in override) {
            val existing = merged[key]
            merged[key] = if (existing is JsonObject && value is JsonObject) {
                mergeObjects(existing, value)
            } else {
                value
            }
        }
        return JsonObject(merged)
    }
}
