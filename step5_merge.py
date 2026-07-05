"""
Step 5: Merge dynamic LLM extraction results into final Excel.

Input:
    data/extracted_results.csv
    data/announcement_list.csv

Output:
    data/巨潮公告提取结果.xlsx
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd  # requires: openpyxl


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXTRACTED_CSV = DATA_DIR / "extracted_results.csv"
ANNOUNCEMENT_CSV = DATA_DIR / "announcement_list.csv"
UNPROCESSED_CSV = DATA_DIR / "unprocessed_checklist.csv"
OUTPUT_XLSX = DATA_DIR / "巨潮公告提取结果.xlsx"

FIXED_COLS = ["announcementId", "secCode", "announcementTitle", "announcementTime"]
EXCLUDED_COLS = ["announcementId", "secCode", "secName", "announcementTitle", "announcementTime"]


def load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames or []


def sort_by_date(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["announcementTime", "公告日期"]:
        if col in df.columns:
            return df.sort_values(col, ascending=False).reset_index(drop=True)
    return df.reset_index(drop=True)


def adjust_column_widths(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame) -> None:
    from openpyxl.utils import get_column_letter

    ws = writer.sheets[sheet_name]
    for i, col_name in enumerate(df.columns, 1):
        if df.empty:
            max_len = len(str(col_name)) + 2
        else:
            max_len = max(df[col_name].astype(str).map(len).max(), len(str(col_name))) + 2
        ws.column_dimensions[get_column_letter(i)].width = min(max_len, 60)


def main() -> int:
    if not EXTRACTED_CSV.exists():
        print("错误: 请先运行 step4b_llm_extract.py")
        return 1
    if not ANNOUNCEMENT_CSV.exists():
        print("错误: 请先运行 step1_fetch_list.py")
        return 1

    extracted_rows, extracted_cols = load_csv(EXTRACTED_CSV)
    announcement_rows, _ = load_csv(ANNOUNCEMENT_CSV)
    announcements = {row["announcementId"]: row for row in announcement_rows}

    dynamic_cols = [col for col in extracted_cols if col not in FIXED_COLS]
    df_main = sort_by_date(pd.DataFrame(extracted_rows, columns=extracted_cols))

    if UNPROCESSED_CSV.exists():
        excluded_rows, _ = load_csv(UNPROCESSED_CSV)
    else:
        extracted_ids = {row.get("announcementId", "") for row in extracted_rows}
        excluded_rows = [
            {
                "announcementId": aid,
                "secCode": meta.get("secCode", ""),
                "secName": meta.get("secName", ""),
                "announcementTitle": meta.get("announcementTitle", ""),
                "announcementTime": meta.get("announcementTime", ""),
            }
            for aid, meta in announcements.items()
            if aid not in extracted_ids
        ]

    df_excluded = sort_by_date(pd.DataFrame(excluded_rows, columns=EXCLUDED_COLS))

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        df_main.to_excel(writer, sheet_name="AI提取结果", index=False)
        df_excluded.to_excel(writer, sheet_name="已筛选排除", index=False)
        adjust_column_widths(writer, "AI提取结果", df_main)
        adjust_column_widths(writer, "已筛选排除", df_excluded)

    print(f"完成: {OUTPUT_XLSX}")
    print(f"  Sheet 1「AI提取结果」: {len(df_main):,} 行")
    print(f"  Sheet 2「已筛选排除」: {len(df_excluded):,} 行")
    print(f"  动态列: {dynamic_cols}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
