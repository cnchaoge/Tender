"""
Tender - 系统托盘
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
    """用 PowerShell 弹窗：选模型 → 填Key → 验证 → 保存"""
    print("[tray] _show_settings_ps called")
    from server.config import get_settings, update_env
    from server.api.admin import verify_model_config, ModelConfigReq

    settings = get_settings()

    # 先调用 verify 接口获取当前状态
    current_valid = False
    current_msg = ""
    try:
        req = ModelConfigReq(provider=settings.LLM_PROVIDER, api_key=settings.DASHSCOPE_API_KEY if settings.LLM_PROVIDER == "dashscope" else settings.DEEPSEEK_API_KEY)
        resp = verify_model_config(req)
        current_valid = resp.valid
        current_msg = resp.message
    except Exception as e:
        current_msg = f"验证异常: {e}"

    script = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Tender 设置"
$form.Size = New-Object System.Drawing.Size(480, 220)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.TopMost = $true
$form.StartPosition = "CenterScreen"

# --- 行1: 模型选择 ---
$lblModel = New-Object System.Windows.Forms.Label
$lblModel.Location = New-Object System.Drawing.Point(10, 15)
$lblModel.Size = New-Object System.Drawing.Size(70, 20)
$lblModel.Text = "模型:"
$form.Controls.Add($lblModel)

$cmbModel = New-Object System.Windows.Forms.ComboBox
$cmbModel.Location = New-Object System.Drawing.Point(85, 12)
$cmbModel.Size = New-Object System.Drawing.Size(160, 20)
$cmbModel.DropDownStyle = "DropDownList"
$cmbModel.Items.Add("dashscope") | Out-Null
$cmbModel.Items.Add("deepseek") | Out-Null
$cmbModel.SelectedItem = "{settings.LLM_PROVIDER}"
$form.Controls.Add($cmbModel)

# --- 行2: API Key ---
$lblKey = New-Object System.Windows.Forms.Label
$lblKey.Location = New-Object System.Drawing.Point(10, 48)
$lblKey.Size = New-Object System.Drawing.Size(70, 20)
$lblKey.Text = "API Key:"
$form.Controls.Add($lblKey)

$txtKey = New-Object System.Windows.Forms.TextBox
$txtKey.Location = New-Object System.Drawing.Point(85, 45)
$txtKey.Size = New-Object System.Drawing.Size(370, 20)
$txtKey.Text = ""
$txtKey.PasswordChar = '*'
$form.Controls.Add($txtKey)

# --- 行3: 验证消息 ---
$lblMsg = New-Object System.Windows.Forms.Label
$lblMsg.Location = New-Object System.Drawing.Point(85, 72)
$lblMsg.Size = New-Object System.Drawing.Size(370, 16)
$lblMsg.Text = "{current_msg}"
$lblMsg.ForeColor = If({str(current_valid).lower()}) {{[System.Drawing.Color]::FromArgb(34,197,94)}} Else {{[System.Drawing.Color]::FromArgb(239,68,68)}}
$form.Controls.Add($lblMsg)

# --- 行4: 按钮 ---
$btnVerify = New-Object System.Windows.Forms.Button
$btnVerify.Location = New-Object System.Drawing.Point(85, 98)
$btnVerify.Size = New-Object System.Drawing.Size(90, 28)
$btnVerify.Text = "验证"
$btnVerify.FlatStyle = "Flat"
$form.Controls.Add($btnVerify)

$btnSave = New-Object System.Windows.Forms.Button
$btnSave.Location = New-Object System.Drawing.Point(185, 98)
$btnSave.Size = New-Object System.Drawing.Size(90, 28)
$btnSave.Text = "保存并重启"
$btnSave.FlatStyle = "Flat"
$btnSave.BackColor = [System.Drawing.Color]::FromArgb(37,99,235)
$btnSave.ForeColor = [System.Drawing.Color]::White
$btnSave.Enabled = $false
$form.Controls.Add($btnSave)

$btnCancel = New-Object System.Windows.Forms.Button
$btnCancel.Location = New-Object System.Drawing.Point(285, 98)
$btnCancel.Size = New-Object System.Drawing.Size(90, 28)
$btnCancel.Text = "取消"
$btnCancel.FlatStyle = "Flat"
$form.Controls.Add($btnCancel)

$done = $false
$saved_key = ""

# Verify button
$btnVerify.Add_Click({{
    $provider = $cmbModel.SelectedItem
    $apiKey = $txtKey.Text.Trim()
    If (-not $apiKey) {{
        $lblMsg.Text = "API Key 不能为空"
        $lblMsg.ForeColor = [System.Drawing.Color]::FromArgb(239,68,68)
        Return
    }}
    $body = @{{provider=$provider;api_key=$apiKey;model=""}} | ConvertTo-Json
    Try {{
        $resp = Invoke-RestMethod -Uri "http://localhost:8000/api/admin/model/verify" -Method Post -ContentType "application/json" -Body $body -TimeoutSec 10
        If ($resp.valid) {{
            $lblMsg.Text = "验证成功: " + $resp.message
            $lblMsg.ForeColor = [System.Drawing.Color]::FromArgb(34,197,94)
            $btnSave.Enabled = $true
        }} Else {{
            $lblMsg.Text = "验证失败: " + $resp.message
            $lblMsg.ForeColor = [System.Drawing.Color]::FromArgb(239,68,68)
            $btnSave.Enabled = $false
        }}
    }} Catch {{
        $lblMsg.Text = "验证异常: " + $_.Exception.Message
        $lblMsg.ForeColor = [System.Drawing.Color]::FromArgb(239,68,68)
        $btnSave.Enabled = $false
    }}
}})

# Save button
$btnSave.Add_Click({{
    $script:saved_key = $txtKey.Text.Trim()
    $script:done = $true
    $form.Close()
}})

$btnCancel.Add_Click({{ $form.Close() }})
$form.AcceptButton = $btnSave
$form.CancelButton = $btnCancel

$txtKey.focus()
$form.ShowDialog() | Out-Null

If ($done -and $saved_key) {{
    $provider = $cmbModel.SelectedItem
    "$provider`t$saved_key" | Out-File -FilePath "$env:TEMP\\tender_settings.txt" -Encoding UTF8
}}
'''

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.ps1', delete=False, encoding='gbk')
    tmp.write(script)
    tmp.close()

    result = subprocess.run(['powershell', '-ExecutionPolicy', 'Bypass', '-File', tmp.name],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[tray] PowerShell error: {result.stderr}")
    try:
        os.unlink(tmp.name)
    except Exception:
        pass

    settings_file = os.path.join(os.environ.get('TEMP', ''), 'tender_settings.txt')
    if os.path.exists(settings_file):
        with open(settings_file, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        try:
            os.unlink(settings_file)
        except Exception:
            pass
        if '\t' in content:
            provider, api_key = content.split('\t', 1)
            provider = provider.strip()
            api_key = api_key.strip()
            if provider == "deepseek":
                update_env("LLM_PROVIDER", "deepseek")
                update_env("DEEPSEEK_API_KEY", api_key)
            else:
                update_env("LLM_PROVIDER", "dashscope")
                update_env("DASHSCOPE_API_KEY", api_key)
            if _restart_callback:
                _restart_callback()
            print(f"[tray] Settings saved, provider={provider}")

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
    _tray = pystray.Icon("Tender", icon=img, title="Tender", menu=menu)
    _tray.run()

def setup_tray(restart_callback):
    global _restart_callback
    _restart_callback = restart_callback
    t = threading.Thread(target=_run_tray, daemon=True)
    t.start()
