"""
下载 M3E-base 模型到本地缓存
盒子首次部署时运行一次即可
"""
from huggingface_hub import snapshot_download

print("开始下载 m3e-base 模型（约 400MB）...")
print("下载目录：~/.cache/huggingface/hub/models--moka-ai--m3e-base")
snapshot_download("moka-ai/m3e-base")
print("下载完成！")
