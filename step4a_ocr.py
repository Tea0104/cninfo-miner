"""
Step 4a OCR: Extract text from scanned/image-based PDFs.

Input:
    data/pdfs/{secCode}_{announcementId}.pdf

Output:
    data/ocr_texts.csv
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz
from rapidocr_onnxruntime import RapidOCR


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdfs"
OUTPUT_CSV = DATA_DIR / "ocr_texts.csv"
ERROR_LOG = DATA_DIR / "errors.log"

FIELDS = [
    "announcementId",
    "secCode",
    "filename",
    "pageCount",
    "textLength",
    "fullText",
]

OCR_FILES = [
    "002442_1202306535.pdf",
    "002890_1204418401.pdf",
    "002890_1204418402.pdf",
    "002890_1204418403.pdf",
    "600665_1202306589.pdf",
    "600983_1204146559.pdf",
    "601636_1204324066.pdf",
    "601636_1204324068.pdf",
    "603035_1203042922.pdf",
    "603069_1203158173.pdf",
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


def clean_ocr_text(text: str) -> str:
    """
    Normalize OCR whitespace without deleting recognized text.

    OCR can emit stray spaces and uneven blank lines. Keep recognized characters,
    trim whitespace around lines, collapse repeated blank lines, and join ordinary
    line breaks into readable paragraphs for later LLM extraction.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    return text.strip()


def sort_ocr_lines(result: list[Any]) -> list[Any]:
    """Sort OCR boxes top-to-bottom and left-to-right with a small y tolerance."""
    def key(item: Any) -> tuple[int, float]:
        box = item[0]
        y_values = [point[1] for point in box]
        x_values = [point[0] for point in box]
        return (round(min(y_values) / 10), min(x_values))

    return sorted(result, key=key)


def render_page_to_pixmap(page: fitz.Page) -> fitz.Pixmap:
    """Render page at 2x scale, enough for readable OCR without huge images."""
    matrix = fitz.Matrix(2, 2)
    return page.get_pixmap(matrix=matrix, alpha=False)


def ocr_page(engine: RapidOCR, page: fitz.Page) -> str:
    pixmap = render_page_to_pixmap(page)
    image_bytes = pixmap.tobytes("png")
    result, _ = engine(image_bytes)

    if not result:
        return ""

    lines: list[str] = []
    for item in sort_ocr_lines(result):
        if len(item) >= 2:
            text = str(item[1]).strip()
            if text:
                lines.append(text)

    return "\n".join(lines)


def extract_ocr_text(engine: RapidOCR, pdf_path: Path) -> tuple[int, str]:
    page_texts: list[str] = []

    with fitz.open(pdf_path) as doc:
        page_count = doc.page_count
        for page_index in range(page_count):
            page = doc.load_page(page_index)
            try:
                page_texts.append(ocr_page(engine, page))
            except Exception as exc:
                log_error(f"OCR 单页失败: {pdf_path.name} 第 {page_index + 1} 页; {exc}")
                page_texts.append("")

    return page_count, clean_ocr_text("\n\n".join(page_texts))


def write_csv(rows: list[dict[str, str | int]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    if not PDF_DIR.exists():
        raise FileNotFoundError(f"找不到 PDF 目录: {PDF_DIR}")

    rows: list[dict[str, str | int]] = []
    success_count = 0
    fail_count = 0
    empty_text_count = 0
    total_text_length = 0

    engine = RapidOCR()
    total = len(OCR_FILES)

    for index, filename in enumerate(OCR_FILES, start=1):
        pdf_path = PDF_DIR / filename
        try:
            if not pdf_path.exists():
                raise FileNotFoundError(f"找不到 PDF 文件: {pdf_path}")

            sec_code, announcement_id = parse_pdf_filename(pdf_path)
            page_count, full_text = extract_ocr_text(engine, pdf_path)
            text_length = len(full_text)

            rows.append(
                {
                    "announcementId": announcement_id,
                    "secCode": sec_code,
                    "filename": filename,
                    "pageCount": page_count,
                    "textLength": text_length,
                    "fullText": full_text,
                }
            )

            success_count += 1
            total_text_length += text_length
            if text_length == 0:
                empty_text_count += 1
                log_error(f"OCR 提取为空文本: {filename}")
        except Exception as exc:
            fail_count += 1
            log_error(f"OCR 提取失败: {filename}; {exc}")

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
