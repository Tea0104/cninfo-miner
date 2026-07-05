"""
PyInstaller packaging script.
Generates dist/巨潮公告提取工具/ with exe + config + docs.
"""
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist" / "巨潮公告提取工具"

def main():
    # Clean old build
    for d in ["build", "dist"]:
        p = BASE_DIR / d
        if p.exists():
            shutil.rmtree(p)

    print("=== 1/3 编译 exe ===")
    import os
    env = os.environ.copy()
    # Point PyInstaller to conda's Tcl/Tk (avoids version conflict with system Tcl)
    tcl_path = r"C:\ProgramData\anaconda3\Library\lib\tcl8.6"
    tk_path = r"C:\ProgramData\anaconda3\Library\lib\tk8.6"
    env["TCL_LIBRARY"] = tcl_path
    env["TK_LIBRARY"] = tk_path

    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--windowed",
        "--name", "巨潮公告提取工具",
        "--add-data", f"config.py{';' if sys.platform == 'win32' else ':'}.",
        "--hidden-import", "pdfplumber",
        "--hidden-import", "pandas",
        "--hidden-import", "openpyxl",
        "--hidden-import", "requests",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PySide6",
        "--exclude-module", "PySide2",
        "--exclude-module", "PyQt6",
        "--collect-all", "tkinter",
        "--clean",
        "--noconfirm",
        str(BASE_DIR / "app.py"),
    ], check=True, cwd=str(BASE_DIR), env=env)

    # PyInstaller puts output in dist/巨潮公告提取工具/ (onedir mode)
    # Actually it puts in dist/ for --onedir, then a subfolder
    exe_dir = BASE_DIR / "dist" / "巨潮公告提取工具"
    if not exe_dir.exists():
        # PyInstaller may use different naming
        candidates = list((BASE_DIR / "dist").iterdir())
        print(f"dist contents: {candidates}")
        # Find the folder containing the exe
        for c in candidates:
            if c.is_dir() and (c / "巨潮公告提取工具.exe").exists():
                exe_dir = c
                break

    print(f"exe location: {exe_dir}")

    if not exe_dir.exists() or not (exe_dir / "巨潮公告提取工具.exe").exists():
        print("ERROR: exe not found")
        return 1

    # Fix Tcl version mismatch: replace bundled Tcl/Tk with conda's correct version
    print("=== 2/4 修复 Tcl 版本 ===")
    import glob as _g
    conda_lib = Path(r"C:\ProgramData\anaconda3\Library")
    tcl_script_src = conda_lib / "lib" / "tcl8.6"
    tk_script_src = conda_lib / "lib" / "tk8.6"
    tcl_dll_src = conda_lib / "bin" / "tcl86t.dll"
    tk_dll_src = conda_lib / "bin" / "tk86t.dll"
    tcl_data_dst = exe_dir / "_internal" / "_tcl_data"
    dll_dst = exe_dir / "_internal"

    if tcl_data_dst.exists() and tcl_script_src.exists():
        # Replace Tcl/Tk script files
        for d in [tcl_data_dst / "tcl8.6", tcl_data_dst / "tk8.6"]:
            if d.exists():
                for f in _g.glob(str(d) + "\\**\\*", recursive=True):
                    try: Path(f).unlink()
                    except Exception: pass
        shutil.copytree(tcl_script_src, tcl_data_dst / "tcl8.6", dirs_exist_ok=True)
        shutil.copytree(tk_script_src, tcl_data_dst / "tk8.6", dirs_exist_ok=True)
        # Replace Tcl/Tk DLLs
        shutil.copy2(tcl_dll_src, dll_dst / "tcl86t.dll")
        shutil.copy2(tk_dll_src, dll_dst / "tk86t.dll")
        print("  Tcl/Tk 脚本+DLL 已替换为 8.6.15")
    else:
        print("  WARNING: 无法找到正确的Tcl，exe可能无法启动")

    print("=== 3/4 复制文件 ===")
    for f in ["README.md", "LICENSE", "requirements.txt"]:
        src = BASE_DIR / f
        if src.exists():
            shutil.copy2(src, exe_dir / f)
            print(f"  {f}")

    # config.py is already added via --add-data

    # Create empty data dir
    (exe_dir / "data").mkdir(exist_ok=True)

    print("=== 4/4 验证 ===")
    contents = list(exe_dir.iterdir())
    for c in sorted(contents):
        print(f"  {c.name}")

    print(f"\n完成: {exe_dir}")
    print(f"大小: {sum(f.stat().st_size for f in exe_dir.rglob('*') if f.is_file()) / 1024 / 1024:.1f} MB")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
