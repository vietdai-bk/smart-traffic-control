"""Chạy backend: python run.py  (mặc định 0.0.0.0:8010)."""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("STCS_HOST", "0.0.0.0"),
        port=int(os.environ.get("STCS_PORT", "8010")),
        reload=os.environ.get("STCS_RELOAD", "0") == "1",
        log_level="info",
        # IP client do app.core.deps.client_ip xử lý theo STCS_TRUSTED_PROXIES; tắt xử lý trùng của uvicorn
        proxy_headers=False,
    )
