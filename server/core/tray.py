"""
ClawOS X - 系统托盘
"""
import threading, webbrowser

def _create_icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(37, 99, 235, 255))
    draw.text((12, 14), "CX", fill=(255, 255, 255, 255))
    return img

_tray = None
_restart_callback = None

def _validate_dashscope_key(api_key: str) -> bool:
    """验证 DashScope API Key 是否有效"""
    import httpx
    try:
        resp = httpx.post(
            "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "text-embedding-v3", "input": {"texts": ["test"]}},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception:
        return False

def _show_settings():
    import tkinter as tk
    from server.config import get_settings, update_env

    settings = get_settings()
    win = tk.Toplevel()
    win.title("ClawOS X 设置")
    win.geometry("500x180")
    win.resizable(False, False)
    win.attributes("-topmost", True)

    v_dashscope = tk.StringVar(value=settings.DASHSCOPE_API_KEY)
    v_msg = tk.StringVar(value="")

    ai_frame = tk.LabelFrame(win, text=" AI 模型 ", padx=8, pady=4)
    ai_frame.grid(row=0, column=0, columnspan=2, sticky="we", padx=8, pady=(8, 4))
    tk.Label(ai_frame, text="DashScope API Key:", anchor="w").grid(row=0, column=0, sticky="w", pady=3)
    tk.Entry(ai_frame, textvariable=v_dashscope, width=50).grid(row=0, column=1, padx=8, pady=3)

    tk.Label(win, textvariable=v_msg, fg="gray").grid(row=1, column=0, columnspan=2, pady=4)

    btn_frame = tk.Frame(win)
    btn_frame.grid(row=2, column=0, columnspan=2, pady=8)

    def on_save():
        key = v_dashscope.get().strip()
        if not key:
            v_msg.set("API Key 不能为空")
            v_msg.config(fg="red")
            return
        v_msg.set("正在验证...")
        v_msg.config(fg="gray")
        win.update()
        if not _validate_dashscope_key(key):
            v_msg.set("验证失败：API Key 无效或网络超时")
            v_msg.config(fg="red")
            return
        update_env("DASHSCOPE_API_KEY", key)
        win.destroy()
        if _restart_callback:
            _restart_callback()

    tk.Button(btn_frame, text="保存并重启", command=on_save, width=14,
              bg="#2563eb", fg="white").grid(row=0, column=0, padx=8)
    tk.Button(btn_frame, text="取消", command=win.destroy, width=14).grid(row=0, column=1, padx=8)
    win.columnconfigure(1, weight=1)
    win.wait_window()

def _on_open(icon, item):
    webbrowser.open("http://localhost:8000")

def _on_settings(icon, item):
    _show_settings()

def _on_restart(icon, item):
    if _restart_callback:
        _restart_callback()

def _on_exit(icon, item):
    if _restart_callback:
        _restart_callback(stop=True)
    icon.stop()

def _run_tray():
    global _tray
    import pystray
    from pystray import MenuItem as MI

    img = _create_icon_image()
    menu = pystray.Menu(
        MI("打开前台", _on_open),
        MI("设置", _on_settings),
        MI("重启服务", _on_restart),
        MI("退出", _on_exit),
    )
    _tray = pystray.Icon("ClawOSX", icon=img, title="ClawOS X", menu=menu)
    _tray.run()

def setup_tray(restart_callback):
    global _restart_callback
    _restart_callback = restart_callback
    t = threading.Thread(target=_run_tray, daemon=True)
    t.start()
