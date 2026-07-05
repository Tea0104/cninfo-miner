"""
Step 1: Fetch cninfo announcement list for "独立董事+辞职" from 2016 to 2018.

Output:
    data/announcement_list.csv
"""

from __future__ import annotations

import csv
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from config import DATA_DIR, SEARCH_KEYWORD, START_DATE, END_DATE, MAX_RETRIES


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_CSV = DATA_DIR / "announcement_list.csv"
ERROR_LOG = DATA_DIR / "errors.log"

API_URL = "http://www.cninfo.com.cn/new/fulltextSearch/full"
SEARCH_KEY = SEARCH_KEYWORD
PAGE_SIZE = 30

FIELDS = [
    "secCode",
    "secName",
    "announcementTitle",
    "announcementTime",
    "adjunctUrl",
    "announcementId",
    "orgId",
]

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Referer": (
        "http://www.cninfo.com.cn/new/fulltextSearch?"
        "notautosubmit=&keyWord=%E7%8B%AC%E7%AB%8B%E8%91%A3%E4%BA%8B%2B%E8%BE%9E%E8%81%8C"
    ),
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


def log_error(message: str) -> None:
    """Write errors both to stderr and data/errors.log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, file=sys.stderr)
    with ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def clean_title(title: Any) -> str:
    if title is None:
        return ""
    return str(title).replace("<em>", "").replace("</em>", "").strip()


def format_announcement_time(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        timestamp = int(value) / 1000
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError) as exc:
        log_error(f"公告时间转换失败: {value!r}; {exc}")
        return str(value)


def build_params(page_num: int) -> dict[str, Any]:
    return {
        "searchkey": SEARCH_KEY,
        "sdate": START_DATE,
        "edate": END_DATE,
        "pageNum": page_num,
        "pageSize": PAGE_SIZE,
        "sortName": "pubdate",
        "sortType": "desc",
        "isfulltext": "false",
    }


def fetch_page(session: requests.Session, page_num: int) -> dict[str, Any]:
    params = build_params(page_num)
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(API_URL, params=params, headers=HEADERS, timeout=20)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            wait_seconds = attempt * 2
            log_error(f"第 {page_num} 页请求失败，第 {attempt}/{MAX_RETRIES} 次: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(wait_seconds)

    raise RuntimeError(f"第 {page_num} 页请求连续失败") from last_error


def normalize_record(item: dict[str, Any]) -> dict[str, str]:
    return {
        "secCode": str(item.get("secCode") or "").strip(),
        "secName": str(item.get("secName") or "").strip(),
        "announcementTitle": clean_title(item.get("announcementTitle")),
        "announcementTime": format_announcement_time(item.get("announcementTime")),
        "adjunctUrl": str(item.get("adjunctUrl") or "").strip(),
        "announcementId": str(item.get("announcementId") or "").strip(),
        "orgId": str(item.get("orgId") or "").strip(),
    }


def write_csv(records: list[dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str]] = []

    with requests.Session() as session:
        page_num = 1
        total_pages: int | None = None
        total_records: int | None = None

        while True:
            data = fetch_page(session, page_num)
            announcements = data.get("announcements") or []

            if total_pages is None:
                total_pages = int(data.get("totalpages") or 0)
                total_records = int(data.get("totalRecordNum") or 0)

            for item in announcements:
                records.append(normalize_record(item))

            total_page_text = str(total_pages) if total_pages else "未知"
            expected_text = str(total_records) if total_records is not None else "未知"
            print(
                f"第 {page_num}/{total_page_text} 页完成，"
                f"本页 {len(announcements)} 条，累计 {len(records)} 条，接口总数 {expected_text}"
            )

            has_more = bool(data.get("hasMore"))
            if not announcements:
                break
            if not has_more:
                break

            page_num += 1
            time.sleep(random.uniform(0.5, 1.0))

    write_csv(records)
    print(f"完成：共获取 {len(records)} 条公告，已输出到 {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
