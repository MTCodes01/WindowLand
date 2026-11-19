"""
Autostart Manager for Windows 10 & 11.
Manages automatic silent background startup on user login via the Windows Registry
(HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run).
Does not require administrator privileges.
"""

import sys
import os
import winreg

APP_REG_NAME = "DynamicIslandOverlay"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_executable_command() -> str:
    """
    Returns the command to execute for startup.
    If compiled as an .exe (PyInstaller), returns the full exe path.
    If running as Python script, returns pythonw (silent no console) + script path.
    """
    if getattr(sys, "frozen", False):
        # Running as compiled PyInstaller executable
        return f'"{sys.executable}"'
    else:
        # Running as Python script: prefer pythonw.exe to avoid flashing console window
        python_exe = sys.executable
        dirname = os.path.dirname(python_exe)
        pythonw_candidate = os.path.join(dirname, "pythonw.exe")
        runner = pythonw_candidate if os.path.exists(pythonw_candidate) else python_exe
        
        main_script = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py"))
        return f'"{runner}" "{main_script}"'


def is_autostart_enabled() -> bool:
    """Checks whether the application is configured to start on Windows login."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, APP_REG_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def set_autostart(enable: bool, custom_exe_path: str = None) -> bool:
    """
    Enables or disables automatic startup with Windows.
    Uses HKEY_CURRENT_USER (safe, no admin UAC prompt needed).
    """
    try:
        if enable:
            cmd = f'"{custom_exe_path}"' if custom_exe_path else get_executable_command()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, cmd)
            return True
        else:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, APP_REG_NAME)
                except FileNotFoundError:
                    pass
            return True
    except Exception as e:
        print(f"Error updating autostart registry: {e}")
        return False
