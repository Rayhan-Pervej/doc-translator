"""
doc-translator — translate a Japanese folder (names + contents) to English.

Usage:
    python main.py <input_path> [--pages N]

    <input_path>  File or folder to translate. Output is created next to it,
                  named  <name>_english.
    --pages N     Only translate first N pages of each PDF (useful for testing).

Examples:
    python -X utf8 main.py "D:/Projects/日本語文書"
    python -X utf8 main.py "D:/Projects/report.xlsx"

Note: On Windows always run with  python -X utf8  so Japanese paths work.
"""

import sys
import os
import ctypes
from pathlib import Path

# ── Unicode console setup (Windows) ──────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
if sys.platform == "win32":
    ctypes.windll.kernel32.SetConsoleCP(65001)
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)

from translator.estimator import estimate_cost
from translator.pipeline  import translate_folder, process_file
from translator.client    import translate_name, get_actual_usage


def _parse_args():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    src       = Path(os.fsdecode(sys.argv[1].strip('"').strip("'"))).resolve()
    max_pages = None
    if "--pages" in sys.argv:
        idx       = sys.argv.index("--pages")
        max_pages = int(sys.argv[idx + 1])
        print(f"PDF page limit: {max_pages}")
    return src, max_pages


def _print_actual_cost():
    actual = get_actual_usage()
    print(f"Actual tokens used  — input: {actual['input_tokens']:,}  output: {actual['output_tokens']:,}")
    print(f"Actual cost         : ${actual['cost_usd']:.4f}")


def main():
    src, max_pages = _parse_args()

    if not src.exists():
        print(f"Error: not found: {src}")
        sys.exit(1)

    # ── Single file ───────────────────────────────────────────────────────────
    if src.is_file():
        print(f"Source:  {src}")
        estimate_cost(src)

        answer = input("  Proceed with translation? (y/n): ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)
        print()

        stem           = src.stem
        ext            = src.suffix
        translated_stem = translate_name(stem, context=f"file in folder: {src.parent.name}")
        dst_dir        = src.parent.parent / (src.parent.name + "_english")
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst_file       = dst_dir / (translated_stem + ext)

        print(f"Output:  {dst_file}")
        if dst_file.exists():
            if input("Output file already exists. Overwrite? (y/n): ").strip().lower() != "y":
                print("Aborted.")
                sys.exit(0)

        context = f"Document '{translated_stem + ext}' in folder '{src.parent.name}'"
        process_file(src, dst_file, context, max_pages=max_pages)

        print("\n── Done ──")
        print(f"Output: {dst_file}")
        _print_actual_cost()
        sys.exit(0)

    # ── Folder ────────────────────────────────────────────────────────────────
    dst = src.parent / (src.name + "_english")
    print(f"Source:  {src}")
    print(f"Output:  {dst}")
    estimate_cost(src)

    answer = input("  Proceed with translation? (y/n): ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)
    print()

    if dst.exists():
        if input("Output folder already exists. Overwrite? (y/n): ").strip().lower() != "y":
            print("Aborted.")
            sys.exit(0)

    dst.mkdir(parents=True, exist_ok=True)
    translate_folder(src, dst, max_pages=max_pages)

    print("\n── Done ──")
    _print_actual_cost()


if __name__ == "__main__":
    main()
