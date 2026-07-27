from __future__ import annotations

import os
import subprocess
from typing import Any


WINDOWS_CREATE_NO_WINDOW = 0x08000000


def hidden_subprocess_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    kwargs: dict[str, Any] = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", WINDOWS_CREATE_NO_WINDOW),
    }
    startup_info_type = getattr(subprocess, "STARTUPINFO", None)
    if startup_info_type is None:
        return kwargs
    startup_info = startup_info_type()
    startup_info.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
    startup_info.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    kwargs["startupinfo"] = startup_info
    return kwargs
