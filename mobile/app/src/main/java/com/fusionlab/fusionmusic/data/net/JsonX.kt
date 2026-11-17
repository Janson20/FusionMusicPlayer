package com.fusionlab.fusionmusic.data.net

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
import kotlinx.serialization.json.longOrNull
import java.net.URLDecoder

private val jsonParser = Json { ignoreUnknownKeys = true; isLenient = true }

fun parseJson(text: String?): JsonElement? {
    if (text.isNullOrBlank()) return null
    return try {
        jsonParser.parseToJsonElement(text)
    } catch (_: Exception) {
        null
    }
}

fun parseJsonObject(text: String?): JsonObject? = parseJson(text) as? JsonObject

fun parseJsonArray(text: String?): JsonArray? = parseJson(text) as? JsonArray

fun jsonObject(vararg pairs: Pair<String, JsonElement>): JsonObject =
    JsonObject(linkedMapOf(*pairs))

fun jsonArray(items: List<JsonElement>): JsonArray = JsonArray(items)

fun jString(value: String): JsonPrimitive = JsonPrimitive(value)

fun jInt(value: Int): JsonPrimitive = JsonPrimitive(value)

fun jLong(value: Long): JsonPrimitive = JsonPrimitive(value)

fun jBool(value: Boolean): JsonPrimitive = JsonPrimitive(value)

fun JsonObject.string(key: String, fallback: String = ""): String {
    val value = this[key]
    return if (value is JsonPrimitive) value.content else fallback
}

fun JsonObject.int(key: String, fallback: Int = 0): Int {
    val value = this[key]
    return if (value is JsonPrimitive) value.intOrNull ?: fallback else fallback
}

fun JsonObject.long(key: String, fallback: Long = 0L): Long {
    val value = this[key]
    return if (value is JsonPrimitive) value.longOrNull ?: value.doubleOrNull?.toLong() ?: fallback else fallback
}

fun JsonObject.double(key: String, fallback: Double = 0.0): Double {
    val value = this[key]
    return if (value is JsonPrimitive) value.doubleOrNull ?: fallback else fallback
}

fun JsonObject.bool(key: String, fallback: Boolean = false): Boolean {
    val value = this[key]
    return if (value is JsonPrimitive) value.booleanOrNull ?: fallback else fallback
}

fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject

fun JsonObject.array(key: String): JsonArray? = this[key] as? JsonArray

fun JsonObject.stringList(key: String): List<String> {
    val value = this[key] as? JsonArray ?: return emptyList()
    return value.mapNotNull { item ->
        if (item is JsonPrimitive && item.isString) item.content else null
    }
}

fun JsonElement?.asObjectOrNull(): JsonObject? = this as? JsonObject

fun JsonElement?.asArrayOrNull(): JsonArray? = this as? JsonArray

fun JsonElement?.asStringOrNull(): String? {
    val value = this
    if (value is JsonPrimitive) return value.content
    return null
}

fun JsonElement?.asIntOrNull(): Int? {
    val value = this
    return if (value is JsonPrimitive) value.intOrNull else null
}

fun JsonElement?.asLongOrNull(): Long? {
    val value = this
    return if (value is JsonPrimitive) value.longOrNull ?: value.doubleOrNull?.toLong() else null
}

fun JsonElement?.asDoubleOrNull(): Double? {
    val value = this
    return if (value is JsonPrimitive) value.doubleOrNull else null
}

fun JsonElement?.asBooleanOrNull(): Boolean? {
    val value = this
    return if (value is JsonPrimitive) value.booleanOrNull else null
}

fun JsonObject.listObjects(key: String): List<JsonObject> {
    val array = this[key] as? JsonArray ?: return emptyList()
    return array.mapNotNull { it as? JsonObject }
}

fun decodeFormValue(raw: String): String {
    return try {
        URLDecoder.decode(raw, "UTF-8")
    } catch (_: Exception) {
        raw
    }
}

fun JsonObject.toStringCompact(): String = this.toString()

fun JsonElement.toJsonOrNull(): JsonElement? = this
