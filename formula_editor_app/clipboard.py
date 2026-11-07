# -*- coding: utf-8 -*-
"""Windows 剪贴板读写；其他平台由 Tk 回退处理。"""
from __future__ import annotations

import ctypes
import sys

_WIN_CLIPBOARD_READY = False
_WIN_USER32 = None
_WIN_KERNEL32 = None
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002


def _win_clipboard_api():
    global _WIN_CLIPBOARD_READY, _WIN_USER32, _WIN_KERNEL32
    if _WIN_CLIPBOARD_READY:
        return _WIN_USER32, _WIN_KERNEL32
    if sys.platform != "win32":
        return None, None
    try:
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.restype = wintypes.HGLOBAL

        _WIN_USER32, _WIN_KERNEL32 = user32, kernel32
        _WIN_CLIPBOARD_READY = True
    except Exception:
        _WIN_USER32 = None
        _WIN_KERNEL32 = None
    return _WIN_USER32, _WIN_KERNEL32


def copy_text_to_clipboard(text: str) -> bool:
    """Windows 下写入系统剪贴板，关闭程序后仍可粘贴；其他平台返回 False。"""
    user32, kernel32 = _win_clipboard_api()
    if user32 is None or kernel32 is None:
        return False
    handle = None
    try:
        if not user32.OpenClipboard(None):
            return False
        try:
            if not user32.EmptyClipboard():
                return False
            data = text.encode("utf-16-le") + b"\x00\x00"
            handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(data))
            if not handle:
                return False
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                kernel32.GlobalFree(handle)
                handle = None
                return False
            try:
                ctypes.memmove(pointer, data, len(data))
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
                return False
            handle = None
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return False
    finally:
        if handle:
            kernel32.GlobalFree(handle)

