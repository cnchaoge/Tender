# Runtime hook: add real Python site-packages to sys.path before any frozen imports
import sys
import os

if getattr(sys, 'frozen', False):
    import winreg

    # Find real Python installation via Windows registry
    python_home = None
    try:
        # Check Python 3.12 first (PythonInstallPath from python.exe registration)
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Python\PythonCore\3.12\InstallPath")
        python_home, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
    except Exception:
        try:
            # Try user-level install
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Python\PythonCore\3.12\InstallPath")
            python_home, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
        except Exception:
            pass

    if python_home and os.path.isdir(python_home):
        real_site_packages = os.path.join(python_home, 'Lib', 'site-packages')
        real_scripts = os.path.join(python_home, 'Scripts')
        if os.path.isdir(real_site_packages) and real_site_packages not in sys.path:
            sys.path.insert(0, real_site_packages)
            print(f"[runtime_hook] Added site-packages: {real_site_packages}")
        if os.path.isdir(real_scripts) and real_scripts not in sys.path:
            sys.path.insert(0, real_scripts)
            print(f"[runtime_hook] Added scripts: {real_scripts}")
    else:
        print("[runtime_hook] Could not find Python installation in registry")
