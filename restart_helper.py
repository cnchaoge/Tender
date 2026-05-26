"""
Tender 重启辅助脚本
由主进程调用，延迟启动新服务实例，确保旧进程已释放端口
"""
import sys
import time
import subprocess

if __name__ == "__main__":
    delay = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    host = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
    port = sys.argv[3] if len(sys.argv) > 3 else "8000"

    time.sleep(delay)

    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app",
         "--host", host, "--port", port,
         "--log-level", "info"],
        cwd=__file__.rsplit("/", 1)[0] if "/" in __file__ else ".",
    )
