import QtQuick
import QtQuick.Controls
import FluentUI
import ".."

/*!
    音质下拉框。

    settings.qualityOptions 是「id + 名字」的列表，而 FluComboBox 只吃字符串
    数组、按**下标**工作 —— 于是「取名字 / 按 id 找下标 / 选中后按 id 写设置」这三段
    在设置页里写了两遍（播放音质、下载默认音质）。收在这里一份。
*/
FluComboBox {
    id: control

    //: 当前选中的档位 id（"auto" / "flac24bit" / "flac" / "320k" / "128k"）
    property string quality: "320k"
    //: 选项来源（允许注入，默认取设置里那一份）
    property var options: settings.qualityOptions

    //: 用户选了某一档（参数是档位 id，不是下标）
    signal picked(string id)

    model: {
        var names = []
        for (var i = 0; i < control.options.length; i++)
            names.push(control.options[i].name)
        return names
    }

    currentIndex: {
        for (var i = 0; i < control.options.length; i++)
            if (control.options[i].id === control.quality)
                return i
        return 0
    }

    onActivated: function (index) {
        if (index >= 0 && index < control.options.length)
            control.picked(control.options[index].id)
    }
}
