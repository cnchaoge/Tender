# Runtime hook: add real Python site-packages to sys.path before any frozen imports
import sys
import os

if getattr(sys, 'frozen', False):
    # Get the real Python executable path
    real_python = sys.executable
    real_python_dir = os.path.dirname(real_python)  # e.g. C:\Users\EWAY\AppData\Local\Programs\Python\Python312
    real_lib_dir = os.path.join(real_python_dir, 'Lib', 'site-packages')

    if os.path.isdir(real_lib_dir) and real_lib_dir not in sys.path:
        sys.path.insert(0, real_lib_dir)

    # Also add Scripts dir for any .exe tools
    real_scripts_dir = os.path.join(real_python_dir, 'Scripts')
    if os.path.isdir(real_scripts_dir) and real_scripts_dir not in sys.path:
        sys.path.insert(0, real_scripts_dir)
