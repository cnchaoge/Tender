"""
ClawOS X - 系统托盘
pystray 做托盘，settings 用 PowerShell 独立窗口
"""
import threading, webbrowser, subprocess, tempfile, os

_tray = None
_restart_callback = None

def _create_icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(37, 99, 235, 255))
    draw.text((12, 14), "CX", fill=(255, 255, 255, 255))
    return img

def _show_settings_ps():
    """用 PowerShell 弹窗输入 API Key，保存后触发重启"""
    from server.config import get_settings, update_env

    settings = get_settings()

    script = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "ClawOS X 设置"
$form.Size = New-Object System.Drawing.Size(520, 160)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.TopMost = $true
$form.StartPosition = "CenterScreen"

$lbl = New-Object System.Windows.Forms.Label
$lbl.Location = New-Object System.Drawing.Point(10, 20)
$lbl.Size = New-Object System.Drawing.Size(150, 20)
$lbl.Text = "DashScope API Key:"
$form.Controls.Add($lbl)

$txt = New-Object System.Windows.Forms.TextBox
$txt.Location = New-Object System.Drawing.Point(165, 17)
$txt.Size = New-Object System.Drawing.Size(320, 20)
$txt.Text = "{settings.DASHSCOPE_API_KEY}"
$form.Controls.Add($txt)

$msg = New-Object System.Windows.Forms.Label
$msg.Location = New-Object System.Drawing.Point(165, 45)
$msg.Size = New-Object System.Drawing.Size(320, 16)
$msg.Text = ""
$msg.ForeColor = [System.Drawing.Color]::Gray
$form.Controls.Add($msg)

$btnOK = New-Object System.Windows.Forms.Button
$btnOK.Location = New-Object System.Drawing.Point(230, 75)
$btnOK.Size = New-Object System.Drawing.Size(100, 25)
$btnOK.Text = "保存并重启"
$btnOK.FlatStyle = "Popup"
$btnOK.BackColor = [System.Drawing.Color]::FromArgb(37,99,235)
$btnOK.ForeColor = [System.Drawing.Color]::White

$btnCancel = New-Object System.Windows.Forms.Button
$btnCancel.Location = New-Object System.Drawing.Point(340, 75)
$btnCancel.Size = New-Object System.Drawing.Size(100, 25)
$btnCancel.Text = "取消"

$done = $false
$key = ""

$btnOK.Add_Click({{
    $script:key = $txt.Text.Trim()
    if (-not $script:key) {{
        $msg.Text = "API Key 不能为空"
        $msg.ForeColor = [System.Drawing.Color]::Red
        return
    }}
    $script:done = $true
    $form.Close()
}})
$btnCancel.Add_Click({{ $form.Close() }})
$form.AcceptButton = $btnOK
$form.CancelButton = $btnCancel

$form.Controls.Add($btnOK)
$form.Controls.Add($btnCancel)
$txt.focus()
$form.ShowDialog() | Out-Null

if ($done -and $key) {{
    $key | Out-File -FilePath "$env:TEMP\\clawosx_apikey.txt" -Encoding UTF8
}}
'''

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False, encoding='utf-8')
    tmp.write(script)
    tmp.close()

    subprocess.run(['powershell', '-ExecutionPolicy', 'Bypass', '-File', tmp.name],
                   capture_output=True)
    try:
        os.unlink(tmp.name)
    except Exception:
        pass

    key_file = os.path.join(os.environ.get('TEMP', ''), 'clawosx_apikey.txt')
    if os.path.exists(key_file):
        with open(key_file, 'r', encoding='utf-8') as f:
            key = f.read().strip()
        try:
            os.unlink(key_file)
        except Exception:
            pass
        if key:
            update_env("DASHSCOPE_API_KEY", key)
            if _restart_callback:
                _restart_callback()

def _on_open(icon, item):
    webbrowser.open("http://localhost:8000")

def _on_settings(icon, item):
    threading.Thread(target=_show_settings_ps, daemon=True).start()

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
