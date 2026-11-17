package com.fusionlab.fusionmusic.data.config

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject

object ConfigDefaults {
    val DEFAULTS: JsonObject = Json.parseToJsonElement(RAW).jsonObject

    private const val RAW = """
{
  "appearance": {
    "theme": "auto",
    "accent": "#6C4DF6",
    "background": "solid",
    "background_image": "",
    "background_opacity": 85,
    "background_blur": 10,
    "background_scrim": 30,
    "surface_sidebar": 30,
    "surface_bottom": 40,
    "surface_overlay": 35,
    "surface_card": 20,
    "animations": true,
    "nav_expanded": true
  },
  "playback": {
    "volume": 65,
    "muted": false,
    "mode": "loop_list",
    "quality": "320k",
    "auto_play_next": true,
    "fade_in_ms": 0,
    "remember_progress": true,
    "seek_step_ms": 5000,
    "restore_session": true
  },
  "audio": {
    "equalize": true,
    "target_lufs": -14.0,
    "preamp_db": 0.0,
    "allow_boost": true,
    "max_gain_db": 12.0,
    "min_gain_db": -24.0,
    "analysis_seconds": 0,
    "decode_timeout": 180,
    "slice_seconds": 0.008,
    "prefetch_next": true,
    "prefer_tags": false,
    "source_offset": true
  },
  "update": {
    "auto_check": true,
    "interval_hours": 24,
    "include_prerelease": false,
    "last_check": 0,
    "skip_version": ""
  },
  "sources": {
    "enabled": ["wy", "tx", "kw", "kg", "mg"],
    "priority": ["wy", "tx", "kw", "kg", "mg"],
    "fallback": true,
    "prefer_original": true,
    "concurrency": 6
  },
  "account": {
    "provider": "netease",
    "auto_login": true,
    "save_credentials": true,
    "cookie_refresh_days": 7,
    "portable": false
  },
  "storage": {
    "cache_cover": true,
    "cache_lyric": true,
    "cache_media": false,
    "media_cache_limit_mb": 2048,
    "download_dir": "",
    "cover_dir": ""
  },
  "download": {
    "quality": "320k",
    "filename_template": "{singer} - {name}",
    "write_tags": true,
    "embed_cover": true,
    "save_lyric": true,
    "duplicate": "rename",
    "add_to_library": false,
    "concurrency": 2
  },
  "lyrics": {
    "show_translation": true,
    "show_romaji": false,
    "dynamic": true,
    "font_size": 17,
    "alignment": "center",
    "desktop_lyric": false,
    "desktop_lyric_locked": false
  },
  "local": {
    "folders": [],
    "extensions": [".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".wma"],
    "scan_on_start": false,
    "match_online": true
  },
  "window": {
    "width": 1180,
    "height": 760,
    "maximized": false,
    "player_expanded": false,
    "queue_visible": false,
    "tray_icon": true,
    "close_action": "ask"
  },
  "advanced": {
    "proxy": "",
    "timeout": 15,
    "log_level": "INFO"
  },
  "search_history": []
}
"""
}
