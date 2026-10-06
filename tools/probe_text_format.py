"""摸清 ``Text.textFormat`` 在 QML / PySide6 两侧怎么读。

冒烟测试要在 Python 里判断某个歌词行是不是富文本。``QQmlExpression`` 里写
``textFormat === Text.StyledText`` 实测拿不到结果（表达式报错），这里查清楚：
1. ``item.property("textFormat")`` 从 Python 读出来是什么；
2. ``Text.PlainText / StyledText`` 的数值各是多少；
3. QQmlExpression 出错时错误信息是什么。

用法::

    python tools/probe_text_format.py [输出文件]
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression  # noqa: E402

QML = r"""
import QtQuick

Item {
    id: root
    Text { id: plain; objectName: "plain"; text: "普通"; textFormat: Text.PlainText }
    Text { id: styled; objectName: "styled"; text: "<font color='#ff0000'>红</font>" }
    Text { id: styled2; objectName: "styled2"; text: "富"; textFormat: Text.StyledText }

    property int enumPlain: Text.PlainText
    property int enumStyled: Text.StyledText
    property int enumAuto: Text.AutoText
    property string formatOfAsText: String(plain.textFormat)
}
"""


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("probe_text_format.txt")
    app = QGuiApplication(sys.argv[:1])
    tmp = Path(tempfile.mkdtemp(prefix="fusion_tf_")) / "probe.qml"
    tmp.write_text(QML, encoding="utf-8")
    engine = QQmlApplicationEngine()
    warnings: list[str] = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    engine.load(QUrl.fromLocalFile(str(tmp)))
    roots = engine.rootObjects()
    out: list[str] = []
    if not roots:
        out.append("QML 加载失败")
        out.extend(warnings)
    else:
        root = roots[0]
        out.append(f"Text.PlainText={root.property('enumPlain')} "
                   f"Text.StyledText={root.property('enumStyled')} "
                   f"Text.AutoText={root.property('enumAuto')}")
        out.append(f"plain.textFormat 的 String()={root.property('formatOfAsText')!r}")
        for name in ("plain", "styled", "styled2"):
            item = root.findChild(object, name)
            try:
                value = repr(item.property("textFormat"))
            except Exception as e:
                value = f"<读不出来：{type(e).__name__}: {e}>"
            out.append(f"{name}: property('textFormat')={value}")
            for expr_text in ("textFormat === Text.StyledText", "textFormat === 2"):
                expr = QQmlExpression(engine.rootContext(), item, expr_text)
                result, undefined = expr.evaluate()
                out.append(f"    [{expr_text}] 结果={result!r} undefined={undefined} "
                           f"错误={expr.error().toString()!r}")
    target.write_text("\n".join(out), encoding="utf-8")
    print(f"已写入 {target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
