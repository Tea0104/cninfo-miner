"""
Step 4a: Extract plain text from downloaded announcement PDFs.

Input:
    data/pdfs/{secCode}_{announcementId}.pdf

Output:
    data/pdf_texts.csv
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"
OUTPUT_CSV = DATA_DIR / "pdf_texts.csv"
ERROR_LOG = DATA_DIR / "errors.log"

FIELDS = [
    "announcementId",
    "secCode",
    "filename",
    "pageCount",
    "textLength",
    "fullText",
]


def log_error(message: str) -> None:
    """Write errors both to stderr and data/errors.log."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, file=sys.stderr)
    with ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def parse_pdf_filename(path: Path) -> tuple[str, str]:
    """Parse {secCode}_{announcementId}.pdf into secCode and announcementId."""
    stem = path.stem
    if "_" not in stem:
        raise ValueError(f"PDF 文件名不符合 {{secCode}}_{{announcementId}}.pdf 格式: {path.name}")

    sec_code, announcement_id = stem.split("_", 1)
    if not sec_code or not announcement_id:
        raise ValueError(f"PDF 文件名缺少 secCode 或 announcementId: {path.name}")

    return sec_code, announcement_id


def clean_full_text(text: str) -> str:
    """
    Merge excessive line breaks into readable paragraphs without rewriting content.

    pdfplumber often emits one visual line per text line. For LLM processing, keep all
    extracted characters but normalize whitespace layout:
    - convert Windows/Mac newlines to "\n"
    - trim spaces around line breaks
    - collapse 3+ blank lines to one paragraph break
    - join single line breaks into spaces
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return text.strip()


def extract_pdf_text(path: Path) -> tuple[int, str]:
    page_texts: list[str] = []

    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as exc:
                log_error(f"PDF 单页提取失败: {path.name} 第 {page_number} 页; {exc}")
                page_text = ""
            page_texts.append(page_text)

    return page_count, clean_full_text("\n\n".join(page_texts))


def write_csv(rows: list[dict[str, str | int]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    if not PDF_DIR.exists():
        raise FileNotFoundError(f"找不到 PDF 目录: {PDF_DIR}")

    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    total = len(pdf_files)

    rows: list[dict[str, str | int]] = []
    success_count = 0
    fail_count = 0
    empty_text_count = 0
    total_text_length = 0

    for index, pdf_path in enumerate(pdf_files, start=1):
        try:
            sec_code, announcement_id = parse_pdf_filename(pdf_path)
            page_count, full_text = extract_pdf_text(pdf_path)
            text_length = len(full_text)

            rows.append(
                {
                    "announcementId": announcement_id,
                    "secCode": sec_code,
                    "filename": pdf_path.name,
                    "pageCount": page_count,
                    "textLength": text_length,
                    "fullText": full_text,
                }
            )

            success_count += 1
            total_text_length += text_length
            if text_length == 0:
                empty_text_count += 1
                log_error(f"PDF 提取为空文本，可能是扫描件: {pdf_path.name}")
        except Exception as exc:
            fail_count += 1
            log_error(f"PDF 提取失败: {pdf_path.name}; {exc}")

        if index % 100 == 0 or index == total:
            print(
                f"进度 {index}/{total}，"
                f"成功 {success_count}，失败 {fail_count}，空文本 {empty_text_count}"
            )

    write_csv(rows)

    average_text_length = round(total_text_length / success_count, 2) if success_count else 0
    print(
        "完成："
        f"成功 {success_count} 个，"
        f"失败 {fail_count} 个，"
        f"平均文本长度 {average_text_length}，"
        f"空文本 {empty_text_count} 个，"
        f"输出文件: {OUTPUT_CSV}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
