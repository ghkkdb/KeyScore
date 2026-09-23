"""Windows 进程完整性级别检测与管理员重启支持。"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes
from enum import Enum
from pathlib import Path


class IntegrityComparison(Enum):
    """表示 KeyScore 与目标窗口进程的完整性级别关系。"""

    COMPATIBLE = "compatible"
    TARGET_HIGHER = "target_higher"
    UNKNOWN = "unknown"


if sys.platform == "win32":
    class _SID_AND_ATTRIBUTES(ctypes.Structure):
        """对应 Win32 SID_AND_ATTRIBUTES 结构。"""

        _fields_ = (
            ("Sid", wintypes.LPVOID),
            ("Attributes", wintypes.DWORD),
        )


    class _TOKEN_MANDATORY_LABEL(ctypes.Structure):
        """对应 Win32 TOKEN_MANDATORY_LABEL 结构。"""

        _fields_ = (("Label", _SID_AND_ATTRIBUTES),)


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TOKEN_QUERY = 0x0008
_TOKEN_INTEGRITY_LEVEL = 25


def _token_integrity_level(token: int) -> int | None:
    """
    读取访问令牌的强制完整性级别 RID。

    Args:
        token (int): 已使用 TOKEN_QUERY 权限打开的访问令牌句柄。

    Returns:
        int | None: 完整性级别 RID；读取失败时返回 ``None``。
    """

    if sys.platform != "win32" or not token:
        return None
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.GetTokenInformation.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.GetSidSubAuthorityCount.argtypes = (wintypes.LPVOID,)
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthority.argtypes = (wintypes.LPVOID, wintypes.DWORD)
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)

    required = wintypes.DWORD()
    advapi32.GetTokenInformation(
        wintypes.HANDLE(token),
        _TOKEN_INTEGRITY_LEVEL,
        None,
        0,
        ctypes.byref(required),
    )
    if required.value == 0:
        return None
    buffer = ctypes.create_string_buffer(required.value)
    if not advapi32.GetTokenInformation(
        wintypes.HANDLE(token),
        _TOKEN_INTEGRITY_LEVEL,
        buffer,
        required.value,
        ctypes.byref(required),
    ):
        return None
    label = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_MANDATORY_LABEL)).contents
    count_pointer = advapi32.GetSidSubAuthorityCount(label.Label.Sid)
    if not count_pointer or count_pointer.contents.value == 0:
        return None
    rid_pointer = advapi32.GetSidSubAuthority(
        label.Label.Sid,
        count_pointer.contents.value - 1,
    )
    return int(rid_pointer.contents.value) if rid_pointer else None


def _process_integrity_level(process: int) -> int | None:
    """
    读取已打开进程的完整性级别。

    Args:
        process (int): Windows 进程句柄。

    Returns:
        int | None: 完整性级别 RID；无法打开令牌时返回 ``None``。
    """

    if sys.platform != "win32" or not process:
        return None
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.OpenProcessToken.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    )
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        wintypes.HANDLE(process),
        _TOKEN_QUERY,
        ctypes.byref(token),
    ):
        return None
    try:
        return _token_integrity_level(int(token.value))
    finally:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(token)


def current_process_integrity_level() -> int | None:
    """
    获取 KeyScore 当前进程的完整性级别。

    Returns:
        int | None: 完整性级别 RID；非 Windows 或读取失败时返回 ``None``。
    """

    if sys.platform != "win32":
        return None
    return _process_integrity_level(int(ctypes.windll.kernel32.GetCurrentProcess()))


def window_process_id(hwnd: int) -> int | None:
    """
    获取窗口所属进程 ID。

    Args:
        hwnd (int): Windows 窗口句柄。

    Returns:
        int | None: 进程 ID；窗口无效或非 Windows 时返回 ``None``。
    """

    if sys.platform != "win32" or not hwnd:
        return None
    process_id = wintypes.DWORD()
    ctypes.windll.user32.GetWindowThreadProcessId(
        wintypes.HWND(hwnd),
        ctypes.byref(process_id),
    )
    return int(process_id.value) if process_id.value else None


def window_process_integrity_level(hwnd: int) -> int | None:
    """
    获取指定窗口所属进程的完整性级别。

    Args:
        hwnd (int): Windows 窗口句柄。

    Returns:
        int | None: 完整性级别 RID；目标不可查询时返回 ``None``。
    """

    process_id = window_process_id(hwnd)
    if process_id is None:
        return None
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    )
    kernel32.OpenProcess.restype = wintypes.HANDLE
    process = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION,
        False,
        process_id,
    )
    if not process:
        return None
    try:
        return _process_integrity_level(int(process))
    finally:
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(process)


def compare_window_integrity(hwnd: int) -> IntegrityComparison:
    """
    比较 KeyScore 与目标窗口的完整性级别。

    Args:
        hwnd (int): 目标窗口句柄。

    Returns:
        IntegrityComparison: 权限兼容、目标更高或无法判断。
    """

    current_level = current_process_integrity_level()
    target_level = window_process_integrity_level(hwnd)
    if current_level is None or target_level is None:
        return IntegrityComparison.UNKNOWN
    if target_level > current_level:
        return IntegrityComparison.TARGET_HIGHER
    return IntegrityComparison.COMPATIBLE


def restart_as_administrator(resume_score_path: Path | None = None) -> bool:
    """
    通过 Windows UAC 启动一个管理员权限的 KeyScore 实例。

    Args:
        resume_score_path (Path | None): 新实例启动后需要恢复选中的曲谱。

    Returns:
        bool: Windows 已接受启动请求时返回 ``True``。
    """

    if sys.platform != "win32":
        return False
    arguments = [
        argument
        for argument in sys.argv[1:]
        if argument != "--restarted-elevated"
    ]
    cleaned_arguments: list[str] = []
    skip_next = False
    for argument in arguments:
        if skip_next:
            skip_next = False
            continue
        if argument == "--resume-score":
            skip_next = True
            continue
        if argument.startswith("--resume-score="):
            continue
        cleaned_arguments.append(argument)
    cleaned_arguments.append("--restarted-elevated")
    if resume_score_path is not None:
        cleaned_arguments.extend(("--resume-score", str(resume_score_path.resolve())))

    if getattr(sys, "frozen", False):
        executable = sys.executable
        launch_arguments = cleaned_arguments
    else:
        executable = sys.executable
        launch_arguments = ["-m", "keyscore", *cleaned_arguments]
    parameters = subprocess.list2cmdline(launch_arguments)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteW.argtypes = (
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_int,
    )
    shell32.ShellExecuteW.restype = ctypes.c_void_p
    result = shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        parameters,
        str(Path.cwd()),
        1,
    )
    return int(result or 0) > 32
