"""Start the HTTP service on loopback: python -m backend [--port 8000]."""
from __future__ import annotations

import argparse


def main():
    parser = argparse.ArgumentParser(description="Novel Pipeline — máy chủ cục bộ")
    parser.add_argument("--port", type=int, default=8000, help="Cổng HTTP cục bộ (mặc định: 8000)")
    arguments = parser.parse_args()
    if not 1 <= arguments.port <= 65535:
        parser.error("Cổng phải nằm trong khoảng 1–65535.")
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=arguments.port, proxy_headers=False)


if __name__ == "__main__":
    main()
