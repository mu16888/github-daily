"""从 Windows 剪贴板读凭据，绕开「复制粘贴到聊天框」这一步。

为什么需要这个：
Cookie 是登录态凭据，让锋哥把它粘贴到对话里等于让登录态进入聊天记录、
日志和本对话的上下文。走剪贴板直读，值只在本机内存里落一次，
不进对话、不进 shell 历史、不进 git。

用法（锋哥操作）：
    1. 浏览器里复制好 Cookie（DevTools → Network → 请求 → Headers → Cookie）
    2. 回到终端跑：  python -m src.local --set-cookie juejin
    3. 程序读剪贴板 → 清洗 → 写 config/local_secrets.json → 立刻清空剪贴板
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes


def read_clipboard(retries: int = 12, delay: float = 0.15) -> str:
    """读 Windows 剪贴板文本。读不到返回空串。"""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except (AttributeError, OSError):
        return ""                      # 非 Windows 环境

    CF_UNICODETEXT = 13

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = wintypes.HANDLE
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    handle = None
    for _ in range(retries):
        if user32.OpenClipboard(None):
            handle = True
            break
        time.sleep(delay)
    if not handle:
        return ""

    try:
        data = user32.GetClipboardData(CF_UNICODETEXT)
        if not data:
            return ""
        ptr = kernel32.GlobalLock(data)
        if not ptr:
            return ""
        try:
            return ctypes.c_wchar_p(ptr).value or ""
        finally:
            kernel32.GlobalUnlock(data)
    except Exception:
        return ""
    finally:
        try:
            user32.CloseClipboard()
        except Exception:
            pass


def clear_clipboard() -> bool:
    """清空剪贴板：读完凭据就抹掉，不留在剪贴板里等人误粘贴。"""
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        for _ in range(12):
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                finally:
                    user32.CloseClipboard()
                return True
            time.sleep(0.15)
    except Exception:
        pass
    return False
