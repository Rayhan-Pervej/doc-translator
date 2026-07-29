"""
Translation pipeline — walks folders, routes files, reports errors.
"""

import os
import shutil
import sys
from pathlib import Path

from .client import translate_name, get_actual_usage
from .handlers import HANDLERS


def process_file(src: Path, dst: Path, context: str, max_pages: int = None):
    ext     = src.suffix.lower()
    handler = HANDLERS.get(ext)
    if handler:
        print(f"  Translating content: {src.name}")
        if ext == ".pdf":
            handler(src, dst, context, max_pages=max_pages)
        else:
            handler(src, dst, context)
    else:
        print(f"  Copying (unsupported format): {src.name}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def translate_folder(src_root: Path, dst_root: Path, max_pages: int = None):
    # ── Phase 1: translate all folder names ───────────────────────────────────
    print("\n── Phase 1: Translating folder names ──")
    folder_name_map: dict[Path, str] = {}

    for dirpath, dirnames, _ in os.walk(src_root):
        for dirname in dirnames:
            original = Path(dirpath) / dirname
            print(f"  Folder: {dirname}")
            translated = translate_name(dirname, context=f"subfolder of {Path(dirpath).name}")
            folder_name_map[original] = translated
            print(f"    → {translated}")

    # ── Phase 2: translate files ──────────────────────────────────────────────
    print("\n── Phase 2: Translating files ──")
    errors: list[tuple[str, str]] = []

    for dirpath, _, filenames in os.walk(src_root):
        src_dir   = Path(dirpath)
        rel_parts = src_dir.relative_to(src_root).parts

        # Build translated output path
        translated_parts = []
        current = src_root
        for part in rel_parts:
            original_sub     = current / part
            translated_parts.append(folder_name_map.get(original_sub, part))
            current          = original_sub

        dst_dir        = dst_root / Path(*translated_parts) if translated_parts else dst_root
        folder_context = " > ".join(translated_parts) if translated_parts else src_root.name
        dst_dir.mkdir(parents=True, exist_ok=True)

        for filename in filenames:
            src_file = src_dir / filename
            stem     = Path(filename).stem
            ext      = Path(filename).suffix

            print(f"\nFile: {src_dir.relative_to(src_root) / filename}")
            translated_stem     = translate_name(stem, context=f"file in folder: {folder_context}")
            translated_filename = translated_stem + ext
            print(f"  Name → {translated_filename}")

            dst_file = dst_dir / translated_filename
            context  = f"Document '{translated_filename}' in folder '{folder_context}'"

            try:
                process_file(src_file, dst_file, context, max_pages=max_pages)
            except Exception as e:
                print(f"  ERROR: {e}")
                errors.append((str(src_file), str(e)))
                try:
                    shutil.copy2(src_file, dst_dir / filename)
                    print(f"  Fallback: copied original as {filename}")
                except Exception:
                    pass

    if errors:
        print(f"\n{len(errors)} file(s) had errors:")
        for path, err in errors:
            print(f"  {path}: {err}")
    else:
        print("\nAll files translated successfully.")
