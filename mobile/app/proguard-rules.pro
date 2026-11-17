# Kotlin serialization keeps generated serializers.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class kotlinx.serialization.json.** {
    *** Companion;
}
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.fusionlab.fusionmusic.**$$serializer { *; }
-keepclassmembers class com.fusionlab.fusionmusic.** {
    *** Companion;
}
-keepclasseswithmembers class com.fusionlab.fusionmusic.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# jaudiotagger touches java.awt types in its generic image path. Android has no AWT.
-dontwarn java.awt.**
-dontwarn javax.imageio.**
-dontwarn org.jaudiotagger.**
-keep class org.jaudiotagger.** { *; }

# OkHttp / Coil / Media3 ship their own consumer rules.
-dontwarn okhttp3.**
-dontwarn okio.**
