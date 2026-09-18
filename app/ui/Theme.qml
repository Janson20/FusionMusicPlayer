pragma Singleton
import QtQuick
import FluentUI

/*!
    全局视觉令牌。

    颜色体系：以「星云紫」为品牌主色，配合中性灰阶构成克制、耐看的暗/亮两套表面，
    避免纯黑与纯白带来的廉价感。所有派生色都从 `accent` 计算，用户在设置里换主色时
    整套 UI 会同步变化。
*/
QtObject {
    id: theme

    // ── 品牌色 ──────────────────────────────────────────
    property color accent: "#6C4DF6"
    readonly property color accentGradientEnd: "#A855F7"
    readonly property color accentHover: Qt.lighter(accent, 1.15)
    readonly property color accentPressed: Qt.darker(accent, 1.15)
    readonly property color accentSoft: theme.dark
        ? Qt.rgba(accent.r, accent.g, accent.b, 0.20)
        : Qt.rgba(accent.r, accent.g, accent.b, 0.10)
    // 注意：不能命名为 onAccent —— QML 会把它当成 accent 信号的处理器
    readonly property color accentText: "#FFFFFF"

    // ── 表面 ────────────────────────────────────────────
    readonly property bool dark: FluTheme.dark
    readonly property color windowBg: dark ? "#131218" : "#F4F4FA"
    readonly property color navBg: dark ? "#191821" : "#EDEDF6"
    readonly property color cardBg: dark ? "#1E1D27" : "#FFFFFF"
    readonly property color cardHover: dark ? "#272633" : "#F4F3FB"
    readonly property color barBg: dark ? "#1A1923" : "#FFFFFF"
    readonly property color border: dark ? "#2C2B38" : "#E5E4EF"
    readonly property color divider: dark ? "#262531" : "#EEEDF5"
    readonly property color overlayBg: dark ? "#16151E" : "#FFFFFF"
    readonly property color scrim: Qt.rgba(0, 0, 0, dark ? 0.55 : 0.28)

    // ── 文本 ────────────────────────────────────────────
    readonly property color textPrimary: FluTheme.fontPrimaryColor
    readonly property color textSecondary: FluTheme.fontSecondaryColor
    readonly property color textTertiary: FluTheme.fontTertiaryColor

    // ── 状态色 ──────────────────────────────────────────
    readonly property color success: dark ? "#3DD68C" : "#16A34A"
    readonly property color warning: dark ? "#FBBF24" : "#D97706"
    readonly property color danger: dark ? "#F87171" : "#DC2626"

    // ── 尺寸 ────────────────────────────────────────────
    readonly property int radiusSmall: 6
    readonly property int radius: 10
    readonly property int radiusLarge: 16
    readonly property int titleBarHeight: 34
    readonly property int navWidth: 218
    readonly property int navCompactWidth: 66
    readonly property int playerBarHeight: 94

    // ── 动效 ────────────────────────────────────────────
    property bool animations: true
    readonly property int durationFast: animations ? 110 : 0
    readonly property int durationNormal: animations ? 190 : 0
    readonly property int durationSlow: animations ? 300 : 0

    function mix(a, b, t) {
        return Qt.rgba(a.r + (b.r - a.r) * t,
                       a.g + (b.g - a.g) * t,
                       a.b + (b.b - a.b) * t,
                       a.a + (b.a - a.a) * t)
    }
}
