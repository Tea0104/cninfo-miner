"""
Step 4b: LLM structured extraction with dynamic columns.

Input:
    data/pdf_texts.csv

Output:
    data/extracted_results.csv

The prompt defines the output schema. The first non-empty LLM result determines
the dynamic CSV columns after the fixed metadata columns.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from config import (
    API_KEY,
    API_URL,
    DATA_DIR,
    EXTRACTION_SYSTEM_PROMPT,
    MAX_RETRIES,
    MODEL,
    REQUEST_INTERVAL,
)


INPUT_CSV = DATA_DIR / "pdf_texts.csv"
OUTPUT_CSV = DATA_DIR / "extracted_results.csv"
ERROR_LOG = DATA_DIR / "errors.log"
FIXED_COLS = ["announcementId", "secCode", "announcementTitle", "announcementTime"]


def log_error(message: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, file=sys.stderr)
    with ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_llm_items(content: str) -> list[dict[str, Any]]:
    parsed = json.loads(content)
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        items = parsed.get("results") or parsed.get("directors") or parsed.get("data") or []
        if not items and len(parsed) == 1:
            items = list(parsed.values())[0]
    else:
        items = []

    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item]


def clean_item(item: dict[str, Any]) -> dict[str, str]:
    return {
        str(key).strip(): "" if value is None else str(value).strip()
        for key, value in item.items()
        if str(key).strip()
    }


def call_llm(title: str, date: str, full_text: str) -> list[dict[str, str]]:
    user_message = f"""公告标题：{title}
公告时间：{date}
---
{full_text}"""

    url = API_URL
    if not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
        "max_tokens": 1024,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=90)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return [clean_item(item) for item in parse_llm_items(content) if clean_item(item)]
        except (requests.RequestException, json.JSONDecodeError, KeyError, IndexError) as exc:
            last_error = exc
            log_error(f"LLM 请求失败 第{attempt}次: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(attempt * 2)

    raise RuntimeError(f"LLM 请求连续 {MAX_RETRIES} 次失败") from last_error


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_existing_state() -> tuple[set[str], list[str]]:
    if not OUTPUT_CSV.exists():
        return set(), []

    with OUTPUT_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        dynamic_cols = [col for col in fieldnames if col not in FIXED_COLS]
        done_ids = {row.get("announcementId", "").strip() for row in reader if row.get("announcementId")}
    return done_ids, dynamic_cols


def write_results(rows: list[dict[str, str]], dynamic_cols: list[str], append: bool) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = FIXED_COLS + dynamic_cols
    mode = "a" if append and OUTPUT_CSV.exists() else "w"
    with OUTPUT_CSV.open(mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if mode == "w" or OUTPUT_CSV.stat().st_size == 0:
            writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in fieldnames})


def main() -> int:
    if not API_KEY or API_KEY == "你的API密钥":
        print("错误：请在 config.py 或环境变量中设置 LLM_API_KEY")
        return 1

    if not INPUT_CSV.exists():
        print(f"错误：输入文件 {INPUT_CSV} 不存在，请先运行 step4a_extract_text.py")
        return 1

    ann_list = DATA_DIR / "announcement_list.csv"
    if not ann_list.exists():
        print(f"错误：元数据文件 {ann_list} 不存在，请先运行 step1_fetch_list.py")
        return 1

    metadata = {row["announcementId"]: row for row in load_csv(ann_list)}
    records = load_csv(INPUT_CSV)
    total = len(records)
    processed_ids, dynamic_cols = load_existing_state()
    append = OUTPUT_CSV.exists() and bool(dynamic_cols)
    print(f"已处理 {len(processed_ids)} 条，共 {total} 条")
    if dynamic_cols:
        print(f"沿用已存在动态列: {dynamic_cols}")

    result_rows: list[dict[str, str]] = []
    success = 0
    empty = 0
    failed = 0

    for i, rec in enumerate(records, start=1):
        aid = rec.get("announcementId", "").strip()
        if aid in processed_ids:
            continue

        full_text = rec.get("fullText", "")
        if not full_text or len(full_text) < 20:
            log_error(f"{aid}: 文本为空或过短，跳过")
            failed += 1
            continue

        try:
            meta = metadata.get(aid, {})
            items = call_llm(
                title=meta.get("announcementTitle", ""),
                date=meta.get("announcementTime", ""),
                full_text=full_text,
            )

            if not items:
                empty += 1
            else:
                if not dynamic_cols:
                    dynamic_cols = list(items[0].keys())
                    print(f"发现动态列: {dynamic_cols}")

                for item in items:
                    row = {
                        "announcementId": aid,
                        "secCode": rec.get("secCode", ""),
                        "announcementTitle": meta.get("announcementTitle", ""),
                        "announcementTime": meta.get("announcementTime", ""),
                    }
                    for col in dynamic_cols:
                        row[col] = item.get(col, "")
                    result_rows.append(row)
                success += len(items)

            if i % 20 == 0:
                print(f"进度: {i}/{total} | 已提取 {success} 条结果 | 空公告 {empty} | 失败 {failed}")
        except Exception as exc:
            log_error(f"{aid}: 处理失败 - {exc}")
            failed += 1

        time.sleep(REQUEST_INTERVAL)

    write_results(result_rows, dynamic_cols, append=append)

    print(f"\n完成: 共 {total} 条公告")
    print(f"  提取结果: {success} 条")
    print(f"  无结果公告: {empty} 条")
    print(f"  处理失败: {failed} 条")
    print(f"  输出: {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
