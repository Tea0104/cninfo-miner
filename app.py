"""
巨潮资讯网公告信息抽取工具
双击运行即可，无需命令行。
"""

from __future__ import annotations

import csv
import random
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import Tk, Frame, Label, Entry, Button, Checkbutton, Text, Scrollbar, END, VERTICAL, RIGHT, BOTH, LEFT, Y, X, W, E, messagebox, DISABLED, NORMAL, BooleanVar, StringVar
from tkinter.ttk import Progressbar, Separator, Combobox
from typing import Any

import requests

import re

from config import PRESET_SCENARIOS, PROMPT_PRESETS, build_prompt

BASE_DIR = Path(__file__).resolve().parent
DATA_ROOT = BASE_DIR / "data"
DATA_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_name(s: str) -> str:
    """Sanitize keyword for folder name."""
    return re.sub(r'[\\/:*?"<>|+\s]', '', s)

# ── API Logic (inline, no external step files needed) ──
API_URL = "http://www.cninfo.com.cn/new/fulltextSearch/full"
PDF_BASE = "http://static.cninfo.com.cn"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

class App:
    def __init__(self):
        self.root = Tk()
        self.root.title("巨潮资讯网公告信息抽取工具")
        self.root.geometry("780x750")
        self.root.resizable(True, True)

        self.running = False
        self.stop_event = threading.Event()
        self.build_ui()

    @property
    def task_dir(self) -> Path:
        kw = _safe_name(self.kw_var.get().strip())
        sd = self.sd_var.get().strip()
        ed = self.ed_var.get().strip()
        d = DATA_ROOT / f"{kw}_{sd}_{ed}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── UI ───────────────────────────────────────────────
    def build_ui(self):
        # -- Config frame --
        frm = Frame(self.root, padx=12, pady=8)
        frm.pack(fill=X)

        row = 0
        Label(frm, text="搜索关键词:").grid(row=row, column=0, sticky=W, pady=3)
        self.kw_var = StringVar(value="独立董事+辞职")
        Entry(frm, textvariable=self.kw_var, width=30).grid(row=row, column=1, sticky=W, padx=5)
        row += 1

        Label(frm, text="开始日期:").grid(row=row, column=0, sticky=W, pady=3)
        self.sd_var = StringVar(value="2016-01-01")
        Entry(frm, textvariable=self.sd_var, width=15).grid(row=row, column=1, sticky=W, padx=5)
        row += 1

        Label(frm, text="结束日期:").grid(row=row, column=0, sticky=W, pady=3)
        self.ed_var = StringVar(value="2018-12-31")
        Entry(frm, textvariable=self.ed_var, width=15).grid(row=row, column=1, sticky=W, padx=5)
        row += 1

        Label(frm, text="LLM API Key:").grid(row=row, column=0, sticky=W, pady=3)
        self.key_var = StringVar(value="")
        Entry(frm, textvariable=self.key_var, width=50, show="*").grid(row=row, column=1, sticky=W, padx=5)
        row += 1

        Label(frm, text="API 地址:").grid(row=row, column=0, sticky=W, pady=3)
        self.url_var = StringVar(value="https://api.deepseek.com")
        Entry(frm, textvariable=self.url_var, width=50).grid(row=row, column=1, sticky=W, padx=5)
        row += 1

        Label(frm, text="模型名:").grid(row=row, column=0, sticky=W, pady=3)
        self.model_var = StringVar(value="deepseek-chat")
        Entry(frm, textvariable=self.model_var, width=25).grid(row=row, column=1, sticky=W, padx=5)
        row += 1

        Label(frm, text="Prompt 模板:").grid(row=row, column=0, sticky=W, pady=3)
        self.prompt_preset_var = StringVar(value="高管离职")
        self.prompt_preset_combo = Combobox(
            frm,
            textvariable=self.prompt_preset_var,
            values=list(PRESET_SCENARIOS.keys()),
            width=18,
            state="readonly",
        )
        self.prompt_preset_combo.grid(row=row, column=1, sticky=W, padx=5)
        self.prompt_preset_combo.bind("<<ComboboxSelected>>", self.on_prompt_preset_changed)
        Button(frm, text="恢复默认", command=self.reset_prompt_to_preset, width=10).grid(row=row, column=2, sticky=W, padx=5)
        row += 1

        Label(frm, text="提取目标:").grid(row=row, column=0, sticky=W, pady=3)
        self.prompt_target_var = StringVar(value="")
        Entry(frm, textvariable=self.prompt_target_var, width=30).grid(row=row, column=1, sticky=W, padx=5)
        row += 1

        Label(frm, text="提取字段:").grid(row=row, column=0, sticky=W, pady=3)
        self.prompt_fields_var = StringVar(value="")
        Entry(frm, textvariable=self.prompt_fields_var, width=40).grid(row=row, column=1, sticky=W, padx=5)
        row += 1

        Label(frm, text="额外要求:").grid(row=row, column=0, sticky=W, pady=3)
        self.prompt_extra_var = StringVar(value="")
        Entry(frm, textvariable=self.prompt_extra_var, width=50).grid(row=row, column=1, sticky=W, padx=5)
        prompt_action_frm = Frame(frm)
        prompt_action_frm.grid(row=row, column=2, sticky=W, padx=5)
        Button(prompt_action_frm, text="生成 Prompt", command=self.generate_prompt_from_simple_mode, width=12).pack(side=LEFT)
        self.show_prompt_var = BooleanVar(value=False)
        Checkbutton(
            prompt_action_frm,
            text="显示完整 Prompt（高级）",
            variable=self.show_prompt_var,
            command=self.toggle_prompt_editor,
        ).pack(side=LEFT, padx=(8, 0))
        row += 1

        self.prompt_hint_var = StringVar(value="")
        Label(frm, textvariable=self.prompt_hint_var, fg="gray").grid(row=row, column=0, columnspan=3, sticky=W, pady=(2, 6))
        row += 1

        self.prompt_label = Label(frm, text="抽取规则 Prompt（可直接编辑）：")
        self.prompt_label.grid(row=row, column=0, columnspan=3, sticky=W, pady=(8, 3))
        row += 1

        self.prompt_text = Text(frm, height=10, width=88, wrap="word", font=("微软雅黑", 10))
        self.prompt_text.grid(row=row, column=0, columnspan=3, sticky=W+E, pady=3)
        self.reset_prompt_to_preset()
        self.toggle_prompt_editor()
        row += 1

        Separator(frm, orient="horizontal").grid(row=row, column=0, columnspan=3, sticky=W+E, pady=8)

        # -- Buttons --
        btn_row = row + 1
        btn_frm = Frame(frm)
        btn_frm.grid(row=btn_row, column=0, columnspan=3, sticky=W)

        Button(btn_frm, text="① 获取公告列表", command=lambda: self.run_thread(self.step1),
               width=16).pack(side=LEFT, padx=2)
        Button(btn_frm, text="② 下载 PDF", command=lambda: self.run_thread(self.step2),
               width=14).pack(side=LEFT, padx=2)
        Button(btn_frm, text="③ 提取文本", command=lambda: self.run_thread(self.step3_text),
               width=14).pack(side=LEFT, padx=2)
        Button(btn_frm, text="④ AI 抽取", command=lambda: self.run_thread(self.step4_llm),
               width=14).pack(side=LEFT, padx=2)
        Button(btn_frm, text="⑤ 生成 Excel", command=lambda: self.run_thread(self.step5_excel),
               width=14).pack(side=LEFT, padx=2)

        btn_frm2 = Frame(frm)
        btn_frm2.grid(row=btn_row + 1, column=0, columnspan=3, sticky=W, pady=4)
        Button(btn_frm2, text="▶ 一键运行全部", command=lambda: self.run_thread(self.run_all),
               width=20, bg="#4CAF50", fg="white", font=("", 10, "bold")).pack(side=LEFT, padx=2)
        self.stop_btn = Button(btn_frm2, text="■ 停止", command=self.do_stop,
                               width=10, bg="#F44336", fg="white", state=DISABLED)
        self.stop_btn.pack(side=LEFT, padx=2)
        Button(btn_frm2, text="打开 data 文件夹", command=self.open_data_folder,
               width=18).pack(side=LEFT, padx=2)

        # -- Progress --
        self.progress = Progressbar(frm, mode="determinate", length=400)
        self.progress.grid(row=btn_row + 2, column=0, columnspan=3, sticky=W+E, pady=6)
        self.status_var = StringVar(value="就绪")
        Label(frm, textvariable=self.status_var, fg="gray").grid(row=btn_row + 3, column=0, columnspan=3, sticky=W)

        # -- Log --
        log_frm = Frame(self.root, padx=12)
        log_frm.pack(fill=BOTH, expand=True, pady=(0, 8))
        self.log = Text(log_frm, wrap="word", font=("Consolas", 9))
        self.log.pack(side=LEFT, fill=BOTH, expand=True)
        scroll = Scrollbar(log_frm, orient=VERTICAL, command=self.log.yview)
        scroll.pack(side=RIGHT, fill=Y)
        self.log.configure(yscrollcommand=scroll.set)

    def set_prompt_text(self, prompt: str):
        self.prompt_text.delete("1.0", END)
        self.prompt_text.insert("1.0", prompt)

    def set_simple_prompt_fields(self, target: str, fields: str, extra: str):
        self.prompt_target_var.set(target)
        self.prompt_fields_var.set(fields)
        self.prompt_extra_var.set(extra)
        self.update_prompt_hint()

    def update_prompt_hint(self):
        fields = self.prompt_fields_var.get().strip()
        if fields:
            self.prompt_hint_var.set(f"将自动生成包含以下字段的抽取规则：{fields}")
        else:
            self.prompt_hint_var.set("将自动生成包含你填写字段的抽取规则")

    def toggle_prompt_editor(self):
        if self.show_prompt_var.get():
            self.prompt_label.grid()
            self.prompt_text.grid()
        else:
            self.prompt_label.grid_remove()
            self.prompt_text.grid_remove()

    def generate_prompt_from_simple_mode(self):
        target = self.prompt_target_var.get().strip()
        fields = self.prompt_fields_var.get().strip()
        extra = self.prompt_extra_var.get().strip()
        if not target or not fields:
            messagebox.showwarning("生成 Prompt", "请至少填写提取目标和提取字段")
            return
        self.set_prompt_text(build_prompt(target, fields, extra))
        self.update_prompt_hint()

    def reset_prompt_to_preset(self):
        preset_name = self.prompt_preset_var.get()
        scenario = PRESET_SCENARIOS.get(preset_name)
        if scenario is None:
            messagebox.showwarning("Prompt 模板", f"找不到预设模板：{preset_name}")
            return
        target = scenario.get("target", "")
        fields = scenario.get("fields", "")
        extra = scenario.get("extra", "")
        self.set_simple_prompt_fields(target, fields, extra)
        if target and fields:
            self.set_prompt_text(build_prompt(target, fields, extra))
        else:
            self.set_prompt_text(PROMPT_PRESETS.get(preset_name, {}).get("prompt", ""))

    def on_prompt_preset_changed(self, _event=None):
        self.reset_prompt_to_preset()

    # ── Thread runner ────────────────────────────────────
    def run_thread(self, target):
        if self.running:
            messagebox.showwarning("运行中", "请等待当前任务完成。")
            return
        self.running = True
        self.stop_event.clear()
        self.log.delete(1.0, END)
        self.stop_btn.config(state=NORMAL)
        threading.Thread(target=self._wrapper(target), daemon=True).start()

    def do_stop(self):
        self.stop_event.set()
        self.log_insert("\n[用户] 正在停止...")
        self.set_status("正在停止...")

    def _wrapper(self, target):
        def fn():
            try:
                target()
            except Exception as e:
                self.log_insert(f"\n[错误] {e}")
            finally:
                self.running = False
                self.stop_btn.config(state=DISABLED)
        return fn

    def should_stop(self) -> bool:
        return self.stop_event.is_set()

    # ── Logging ──────────────────────────────────────────
    def log_insert(self, text: str):
        self.log.insert(END, text + "\n")
        self.log.see(END)

    def set_status(self, text: str):
        self.status_var.set(text)

    def set_progress(self, val: float):
        self.progress["value"] = val

    # ── Step 1 ──────────────────────────────────────────
    def _split_dates(self, sdate: str, edate: str) -> list[tuple[str, str]]:
        """Split date range into ≤3-year chunks (cninfo limit)."""
        from datetime import timedelta
        sd = datetime.strptime(sdate, "%Y-%m-%d")
        ed = datetime.strptime(edate, "%Y-%m-%d")
        chunks = []
        chunk_start = sd
        while chunk_start <= ed:
            # chunk_end = chunk_start + 3 years - 1 day
            year = chunk_start.year + 3
            month = chunk_start.month
            day = chunk_start.day
            try:
                chunk_end = datetime(year, month, day)
            except ValueError:
                # Day not valid in month (e.g. Feb 29 in non-leap year)
                last_days = {1:31, 2:29 if (year%4==0 and year%100!=0) or year%400==0 else 28,
                            3:31, 4:30, 5:31, 6:30, 7:31, 8:31, 9:30, 10:31, 11:30, 12:31}
                chunk_end = datetime(year, month, last_days[month])
            chunk_end = chunk_end - timedelta(days=1)
            if chunk_end > ed:
                chunk_end = ed
            chunks.append((chunk_start.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")))
            chunk_start = chunk_end + timedelta(days=1)
        return chunks

    def step1(self):
        self.log_insert("=== ① 获取公告列表 ===\n")
        keyword = self.kw_var.get().strip()
        sdate = self.sd_var.get().strip()
        edate = self.ed_var.get().strip()

        if not keyword:
            self.log_insert("[错误] 请输入搜索关键词")
            return

        chunks = self._split_dates(sdate, edate)
        if len(chunks) > 1:
            self.log_insert(f"日期范围超过3年，自动拆分为 {len(chunks)} 段:")
            for cs, ce in chunks:
                self.log_insert(f"  {cs} ~ {ce}")

        self.set_status("搜索中...")
        self.set_progress(0)

        csv_path = self.task_dir / "announcement_list.csv"
        all_records: list[dict] = []
        seen_ids: set[str] = set()

        for ci, (cs, ce) in enumerate(chunks):
            if self.should_stop():
                self.log_insert("[用户] ① 已停止")
                return

            self.log_insert(f"\n--- 第{ci+1}/{len(chunks)}段: {cs} ~ {ce} ---")
            page = 1
            chunk_records = 0

            while True:
                params = {
                    "searchkey": keyword, "sdate": cs, "edate": ce,
                    "pageNum": page, "pageSize": 30,
                    "sortName": "pubdate", "sortType": "desc", "isfulltext": "false",
                }
                try:
                    resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    self.log_insert(f"[错误] 第{page}页请求失败: {e}")
                    break

                anns = data.get("announcements") or []
                for a in anns:
                    aid = str(a.get("announcementId", "")).strip()
                    if aid and aid in seen_ids:
                        continue
                    if aid:
                        seen_ids.add(aid)
                    all_records.append({
                        "secCode": str(a.get("secCode", "")).strip(),
                        "secName": str(a.get("secName", "")).strip(),
                        "announcementTitle": str(a.get("announcementTitle", "")).replace("<em>", "").replace("</em>", "").strip(),
                        "announcementTime": self._fmt_time(a.get("announcementTime")),
                        "adjunctUrl": str(a.get("adjunctUrl", "")).strip(),
                        "announcementId": aid,
                        "orgId": str(a.get("orgId", "")).strip(),
                    })
                    chunk_records += 1

                total = data.get("totalRecordNum", "?")
                pct = (ci / len(chunks)) * 100 + (page / max(int(data.get("totalpages", 1)), 1)) * (100 / len(chunks))
                self.set_progress(min(pct, 99))
                self.log_insert(f"  第{page}页: {len(anns)} 条，段累计 {chunk_records}，段总数 {total}")

                has_more = bool(data.get("hasMore"))
                if not anns or not has_more or self.should_stop():
                    break
                page += 1
                time.sleep(random.uniform(0.5, 1.0))

        # Write CSV
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(all_records[0].keys()) if all_records else [])
            w.writeheader()
            w.writerows(all_records)

        self.log_insert(f"\n完成: {len(all_records)} 条公告（已去重）→ {csv_path}")
        self.set_progress(100)
        self.set_status(f"公告列表: {len(all_records)} 条")

    @staticmethod
    def _fmt_time(val: Any) -> str:
        if val in (None, ""):
            return ""
        try:
            return datetime.fromtimestamp(int(val) / 1000).strftime("%Y-%m-%d")
        except Exception:
            return str(val)

    # ── Step 2 ──────────────────────────────────────────
    def step2(self):
        self.log_insert("=== ② 下载 PDF ===\n")
        csv_path = self.task_dir / "announcement_list.csv"
        if not csv_path.exists():
            self.log_insert("[错误] 请先执行步骤①")
            return

        (self.task_dir / "pdfs").mkdir(parents=True, exist_ok=True)
        with csv_path.open("r", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        total = len(rows)
        downloaded = skipped = failed = 0
        MAX_PDF_RETRIES = 3

        for i, row in enumerate(rows):
            url = f"{PDF_BASE}/{row['adjunctUrl']}"
            ext = row['adjunctUrl'].rsplit(".", 1)[-1] if "." in row['adjunctUrl'] else "pdf"
            fname = f"{row['secCode']}_{row['announcementId']}.{ext}"
            fpath = self.task_dir / "pdfs" / fname

            if fpath.exists() and fpath.stat().st_size > 0:
                # Verify it's a real PDF (not a partial download)
                if fpath.read_bytes()[:4] == b'%PDF':
                    skipped += 1
                    continue
            else:
                ok = False
                for attempt in range(1, MAX_PDF_RETRIES + 1):
                    try:
                        r = requests.get(url, headers=HEADERS, timeout=60)
                        r.raise_for_status()
                        fpath.write_bytes(r.content)
                        downloaded += 1
                        ok = True
                        break
                    except Exception as e:
                        if attempt < MAX_PDF_RETRIES:
                            time.sleep(attempt * 2)
                        else:
                            self.log_insert(f"  下载失败 {fname}: {e}")
                            failed += 1

            if (i + 1) % 100 == 0:
                pct = (i + 1) / total * 100
                self.set_progress(pct)
                self.log_insert(f"  进度: {i+1}/{total}  (下载 {downloaded} 跳过 {skipped} 失败 {failed})")

            if self.should_stop():
                self.log_insert("[用户] ② 已停止")
                self.set_status("② 已停止")
                return

            time.sleep(random.uniform(0.2, 0.5))

        self.log_insert(f"\n完成: 下载 {downloaded} | 跳过 {skipped} | 失败 {failed}")
        self.set_progress(100)
        self.set_status(f"PDF: {downloaded + skipped} 个")

    # ── Step 3 ──────────────────────────────────────────
    def step3_text(self):
        self.log_insert("=== ③ 提取 PDF 文本 ===\n")
        try:
            import pdfplumber
        except ImportError:
            self.log_insert("[错误] 请先安装 pdfplumber: pip install pdfplumber")
            return

        pdfs = sorted((self.task_dir / "pdfs").glob("*.pdf"))
        if not pdfs:
            self.log_insert("[错误] 无 PDF，请先执行步骤②")
            return

        csv_path = self.task_dir / "pdf_texts.csv"
        total = len(pdfs)
        success = empty = 0

        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["announcementId", "secCode", "filename", "pageCount", "textLength", "fullText"])
            w.writeheader()

            for i, fp in enumerate(pdfs):
                parts = fp.stem.split("_", 1)
                sec_code = parts[0]
                ann_id = parts[1] if len(parts) > 1 else ""

                try:
                    raw = fp.read_bytes()
                    if raw.startswith(b"var affiches="):
                        # Old cninfo JS format (GBK-encoded): var affiches=[{"Zw":"text..."}]
                        import json as _j
                        for enc in ["gbk", "gb2312", "gb18030", "utf-8"]:
                            try:
                                js_text = raw.decode(enc)
                                break
                            except Exception:
                                continue
                        json_str = js_text[len("var affiches="):].strip().rstrip(";")
                        data = _j.loads(json_str)
                        text = " ".join((item.get("Zw", "") for item in data))
                        text = text.replace("<br>", " ").replace("&nbsp;", " ")
                        text = " ".join(text.split())
                        page_count = 1
                    else:
                        with pdfplumber.open(fp) as pdf:
                            text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                        text = " ".join(text.split())
                        page_count = len(pdf.pages) if hasattr(pdf, 'pages') else 1
                except Exception:
                    text = ""
                    page_count = 0

                w.writerow({
                    "announcementId": ann_id, "secCode": sec_code,
                    "filename": fp.name, "pageCount": page_count,
                    "textLength": len(text), "fullText": text,
                })
                if not text.strip():
                    empty += 1
                else:
                    success += 1

                if (i + 1) % 200 == 0:
                    self.log_insert(f"  进度: {i+1}/{total}")
                    self.set_progress((i + 1) / total * 100)

                if self.should_stop():
                    self.log_insert("[用户] ③ 已停止")
                    self.set_status("③ 已停止")
                    return

        self.log_insert(f"\n完成: 成功 {success} | 空文本(可能扫描件) {empty}")
        self.log_insert(f"  输出: {csv_path}")
        if empty:
            self.log_insert(f"  提示: {empty} 个文件可能是扫描件，请手动检查或使用 OCR 工具")
        self.set_progress(100)
        self.set_status(f"文本提取: {success} 篇")

    # ── Step 4 ──────────────────────────────────────────
    def step4_llm(self):
        self.log_insert("=== ④ AI 抽取公告信息 ===\n")
        import json as _json

        csv_path = self.task_dir / "pdf_texts.csv"
        ann_csv = self.task_dir / "announcement_list.csv"
        out_csv = self.task_dir / "extracted_results.csv"

        if not csv_path.exists():
            self.log_insert("[错误] 请先执行步骤③")
            return

        api_key = self.key_var.get().strip()
        api_url = self.url_var.get().strip()
        model = self.model_var.get().strip()

        if not api_key:
            self.log_insert("[错误] 请输入 API Key")
            return
        if not api_url.endswith("/chat/completions"):
            api_url = api_url.rstrip("/") + "/chat/completions"
        system_prompt = self.prompt_text.get("1.0", END).strip()
        if not system_prompt:
            self.log_insert("[错误] 抽取规则 Prompt 不能为空")
            return

        # Load metadata
        metadata = {}
        with ann_csv.open("r", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                metadata[row["announcementId"]] = row

        # Load texts
        with csv_path.open("r", encoding="utf-8-sig") as f:
            records = list(csv.DictReader(f))

        # Resume: load already-processed IDs and persistent failures
        done_ids = set()
        fixed_cols = ["announcementId", "secCode", "announcementTitle", "announcementTime"]
        dynamic_cols: list[str] = []
        append_existing_output = False
        if out_csv.exists():
            with out_csv.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                dynamic_cols = [c for c in (reader.fieldnames or []) if c not in fixed_cols]
                done_ids = {r["announcementId"] for r in reader}
                append_existing_output = bool(dynamic_cols)

        fail_log = self.task_dir / "failed_ids.txt"
        fail_counts: dict[str, int] = {}
        if fail_log.exists():
            for line in fail_log.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    fail_counts[parts[0]] = int(parts[1])

        MAX_FAILS = 5  # Give up after 5 total attempts across all runs

        self.log_insert(f"已处理 {len(done_ids)} 条，失败待重试 {len(fail_counts)} 条，共 {len(records)} 条")

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        total = len(records)
        found = empty = failed = skipped = 0
        result_rows: list[dict[str, str]] = []

        for i, rec in enumerate(records):
            aid = rec["announcementId"]
            if aid in done_ids:
                continue
            if fail_counts.get(aid, 0) >= MAX_FAILS:
                skipped += 1
                continue

            full_text = rec.get("fullText", "")
            if not full_text or len(full_text) < 20:
                fail_counts[aid] = fail_counts.get(aid, 0) + 1
                with fail_log.open("w", encoding="utf-8") as ff:
                    for k, v in fail_counts.items():
                        ff.write(f"{k},{v}\n")
                failed += 1
                continue

            meta = metadata.get(aid, {})
            user_msg = f'公告标题：{meta.get("announcementTitle", "")}\n公告时间：{meta.get("announcementTime", "")}\n---\n{full_text}'

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.0,
                "max_tokens": 1024,
                "response_format": {"type": "json_object"},
            }

            try:
                r = requests.post(api_url, json=payload, headers=headers, timeout=90)
                r.raise_for_status()
                body = r.json()
                content = body["choices"][0]["message"]["content"]
                parsed = _json.loads(content)

                if isinstance(parsed, list):
                    items = parsed
                elif isinstance(parsed, dict):
                    items = parsed.get("results") or parsed.get("directors") or parsed.get("data") or []
                    if not items and len(parsed) == 1:
                        items = list(parsed.values())[0]
                else:
                    items = []

                if not items:
                    empty += 1
                else:
                    for item in items:
                        if isinstance(item, dict):
                            clean_item = {str(k).strip(): "" if v is None else str(v).strip()
                                          for k, v in item.items() if str(k).strip()}
                            if not clean_item:
                                continue
                            if not dynamic_cols:
                                dynamic_cols = list(clean_item.keys())
                            result_row = {
                                "announcementId": aid,
                                "secCode": rec["secCode"],
                                "announcementTitle": meta.get("announcementTitle", ""),
                                "announcementTime": meta.get("announcementTime", ""),
                            }
                            for col in dynamic_cols:
                                result_row[col] = clean_item.get(col, "")
                            result_rows.append(result_row)
                            found += 1

                # Success: clear from fail log
                if aid in fail_counts:
                    del fail_counts[aid]

            except Exception as e:
                self.log_insert(f"  失败 {aid}: {e}")
                fail_counts[aid] = fail_counts.get(aid, 0) + 1
                failed += 1

            # Persist fail counts
            with fail_log.open("w", encoding="utf-8") as ff:
                for k, v in fail_counts.items():
                    ff.write(f"{k},{v}\n")

            if (i + 1) % 50 == 0:
                pct = (i + 1) / total * 100
                self.set_progress(pct)
                self.log_insert(f"  进度: {i+1}/{total} | 已提取 {found} 条结果 | 空 {empty} | 失败 {failed} | 跳过 {skipped}")

            if self.should_stop():
                self.log_insert("[用户] ④ 已停止")
                self.set_status("④ 已停止")
                if result_rows or not out_csv.exists():
                    self._write_extraction_csv(out_csv, fixed_cols, dynamic_cols, result_rows, append=append_existing_output)
                return

            time.sleep(1.0)

        self._write_extraction_csv(out_csv, fixed_cols, dynamic_cols, result_rows, append=append_existing_output)
        self.log_insert(f"\n完成: 提取到 {found} 条结果 | 无结果公告 {empty} 条 | 失败 {failed} 条 | 超过{MAX_FAILS}次跳过 {skipped} 条")
        if fail_counts:
            self.log_insert(f"  仍有 {len(fail_counts)} 条失败待下次重试，详情: {fail_log}")
        self.log_insert(f"  输出: {out_csv}")
        self.set_progress(100)
        self.set_status(f"AI 抽取: {found} 条")

    def _write_extraction_csv(self, out_csv: Path, fixed_cols: list[str],
                              dynamic_cols: list[str], rows: list[dict[str, str]],
                              append: bool = False):
        fieldnames = fixed_cols + dynamic_cols
        file_exists = out_csv.exists()
        mode = "a" if append and file_exists else "w"
        with out_csv.open(mode, newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if mode == "w" or out_csv.stat().st_size == 0:
                writer.writeheader()
            for row in rows:
                writer.writerow({col: row.get(col, "") for col in fieldnames})

    # ── Step 5 ──────────────────────────────────────────
    def step5_excel(self):
        self.log_insert("=== ⑤ 生成 Excel ===\n")
        try:
            import pandas as pd
        except ImportError:
            self.log_insert("[错误] 请先安装 pandas openpyxl: pip install pandas openpyxl")
            return

        dir_csv = self.task_dir / "extracted_results.csv"
        ann_csv = self.task_dir / "announcement_list.csv"

        if not dir_csv.exists():
            self.log_insert("[错误] 请先执行步骤④")
            return

        # Load extraction results
        with dir_csv.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            extracted_rows = list(reader)
            extracted_cols = reader.fieldnames or []

        meta = {}
        with ann_csv.open("r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                meta[r["announcementId"]] = r

        all_ids = set(meta.keys())
        extracted_ids = {d["announcementId"] for d in extracted_rows}
        unprocessed_ids = all_ids - extracted_ids

        # Sheet 1: keep extracted CSV columns exactly as-is
        df1 = pd.DataFrame(extracted_rows, columns=extracted_cols)
        if "announcementTime" in df1.columns:
            df1 = df1.sort_values("announcementTime", ascending=False)

        # Sheet 2
        rows2 = []
        for aid in unprocessed_ids:
            m = meta.get(aid, {})
            rows2.append({
                "announcementId": aid,
                "secCode": m.get("secCode", ""),
                "secName": m.get("secName", ""),
                "announcementTitle": m.get("announcementTitle", ""),
                "announcementTime": m.get("announcementTime", ""),
            })
        excluded_cols = ["announcementId", "secCode", "secName", "announcementTitle", "announcementTime"]
        df2 = pd.DataFrame(rows2, columns=excluded_cols)
        if "announcementTime" in df2.columns:
            df2 = df2.sort_values("announcementTime", ascending=False)

        out = self.task_dir / "巨潮公告提取结果.xlsx"
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df1.to_excel(writer, sheet_name="AI提取结果", index=False)
            df2.to_excel(writer, sheet_name="已筛选排除", index=False)

            from openpyxl.utils import get_column_letter
            for sheet_name, df in [("AI提取结果", df1), ("已筛选排除", df2)]:
                ws = writer.sheets[sheet_name]
                for i, col in enumerate(df.columns, 1):
                    if df.empty:
                        max_len = len(str(col)) + 2
                    else:
                        max_len = max(df[col].astype(str).map(len).max(), len(str(col))) + 2
                    max_len = min(max_len, 60)
                    ws.column_dimensions[get_column_letter(i)].width = max_len

        self.log_insert(f"完成: {out}")
        self.log_insert(f"  Sheet「AI提取结果」: {len(df1)} 行")
        self.log_insert(f"  Sheet「已筛选排除」: {len(df2)} 行")
        self.set_status("Excel 已生成")

    # ── Run All ──────────────────────────────────────────
    def run_all(self):
        self.log_insert("▶ 一键运行全部步骤\n")
        for step_name, step_fn in [
            ("① 获取公告列表", self.step1),
            ("② 下载 PDF", self.step2),
            ("③ 提取文本", self.step3_text),
            ("④ AI 抽取", self.step4_llm),
            ("⑤ 生成 Excel", self.step5_excel),
        ]:
            if self.should_stop():
                break
            self.log_insert(f"\n{'='*50}")
            self.log_insert(f"  执行: {step_name}")
            self.log_insert(f"{'='*50}")
            step_fn()
            self.set_progress(0)

        self.log_insert("\n" + "=" * 50)
        self.log_insert("  全部完成！请查看 data/ 目录下的 Excel 文件。")
        self.log_insert("=" * 50)
        self.set_status("全部完成")
        messagebox.showinfo("完成", "全部步骤已完成！\n请查看 data/巨潮公告提取结果.xlsx")

    def open_data_folder(self):
        import os
        os.startfile(self.task_dir)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
