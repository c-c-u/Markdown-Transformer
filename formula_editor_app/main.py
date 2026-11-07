# -*- coding: utf-8 -*-
"""程序入口：DPI 感知、Tk 窗口和冒烟测试参数。"""
from __future__ import annotations

import argparse
import ctypes
import sys
import tkinter as tk
from tkinter import messagebox

from .app import FormulaEditorApp

def enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="公式编辑器：可视化编辑、实时输出 Markdown 公式")
    parser.add_argument("--smoke-test", action="store_true", help="构建窗口并执行一轮公式编辑/实时输出测试后退出")
    args = parser.parse_args(argv)

    enable_dpi_awareness()
    root = tk.Tk()
    app = FormulaEditorApp(root)

    def report_callback_exception(exc_type, exc_value, exc_tb) -> None:
        import traceback

        traceback.print_exception(exc_type, exc_value, exc_tb)
        messagebox.showerror("程序错误", str(exc_value), parent=root)

    root.report_callback_exception = report_callback_exception

    if args.smoke_test:
        try:
            app.run_smoke_test()
        finally:
            root.destroy()
        return 0

    root.mainloop()
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
