"""
Step 2: Download announcement PDFs listed in data/announcement_list.csv.

Input:
    data/announcement_list.csv

Output:
    data/pdfs/{secCode}_{announcementId}.pdf
"""

from __future__ import annotations

import csv
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
INPUT_CSV = DATA_DIR / "announcement_list.csv"
PDF_DIR = DATA_DIR / "pdfs"
ERROR_LOG = DATA_DIR / "errors.log"

STATIC_BASE_URL = "http://static.cninfo.com.cn"
MAX_RETRIES = 3
RETRY_DELAYS = [1, 3, 5]
REQUEST_INTERVAL_RANGE = (0.3, 0.8)

HEADERS = {
    "Accept": "application/pdf,application/octet-stream,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": "http://www.cninfo.com.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
}


def log_error(message: str) -> None:
    """Write errors both to stderr and data/errors.log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, file=sys.stderr)
    with ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_announcements() -> list[dict[str, str]]:
    if not INPUT_CSV.exists():
        raise FileNotFoundError(f"找不到输入文件: {INPUT_CSV}")

    with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def safe_filename_part(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    return text.strip("._")


def build_pdf_url(adjunct_url: str) -> str:
    path = adjunct_url.strip().lstrip("/")
    return f"{STATIC_BASE_URL}/{quote(path, safe='/')}"


def build_pdf_path(row: dict[str, str]) -> Path:
    sec_code = safe_filename_part(row.get("secCode"))
    announcement_id = safe_filename_part(row.get("announcementId"))
    if not sec_code or not announcement_id:
        raise ValueError(f"secCode 或 announcementId 缺失: {row}")
    return PDF_DIR / f"{sec_code}_{announcement_id}.pdf"


def file_exists_with_content(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def looks_like_pdf(content: bytes) -> bool:
    return content[:5] == b"%PDF-"


def download_pdf(session: requests.Session, url: str, path: Path) -> bool:
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            content = response.content
            if not content:
                raise ValueError("响应内容为空")
            if not looks_like_pdf(content):
                raise ValueError(f"响应不是 PDF，前 40 字节: {content[:40]!r}")

            tmp_path = path.with_suffix(path.suffix + ".tmp")
            with tmp_path.open("wb") as f:
                f.write(content)
            tmp_path.replace(path)
            return True
        except (requests.RequestException, OSError, ValueError) as exc:
            last_error = exc
            log_error(f"下载失败，第 {attempt}/{MAX_RETRIES} 次: {url}; {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAYS[attempt - 1])

    log_error(f"下载最终失败: {url}; 保存路径: {path}; 错误: {last_error}")
    return False


def main() -> int:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_announcements()
    total = len(rows)

    success_count = 0
    skip_count = 0
    fail_count = 0

    with requests.Session() as session:
        for index, row in enumerate(rows, start=1):
            try:
                adjunct_url = (row.get("adjunctUrl") or "").strip()
                if not adjunct_url:
                    raise ValueError("adjunctUrl 为空")

                pdf_path = build_pdf_path(row)
                if file_exists_with_content(pdf_path):
                    skip_count += 1
                else:
                    pdf_url = build_pdf_url(adjunct_url)
                    if download_pdf(session, pdf_url, pdf_path):
                        success_count += 1
                    else:
                        fail_count += 1

                if index % 50 == 0 or index == total:
                    print(
                        f"进度 {index}/{total}，"
                        f"成功 {success_count}，跳过 {skip_count}，失败 {fail_count}"
                    )

                if index < total:
                    time.sleep(random.uniform(*REQUEST_INTERVAL_RANGE))
            except Exception as exc:
                fail_count += 1
                log_error(f"第 {index} 行处理失败: {row}; {exc}")

    print(
        "完成："
        f"成功下载 {success_count} 个，"
        f"跳过已存在 {skip_count} 个，"
        f"失败 {fail_count} 个，"
        f"PDF 目录: {PDF_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
