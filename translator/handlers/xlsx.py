import re
import zipfile
from pathlib import Path

from ..common import has_japanese, jp_char_count, xml_escape, xml_unescape, batch_translate
from ..client import translate_name


_SP_PAT = re.compile(r'(<\w+:sp\b[^>]*>)(.*?)(</\w+:sp>)', re.DOTALL)


def _translate_drawing_xml(xml_bytes: bytes, context: str) -> bytes:
    text  = xml_bytes.decode("utf-8")
    t_pat = re.compile(r'(<\w+:t(?:\s[^>]*)?>)([^<]*)(</\w+:t>)')

    unique = list(dict.fromkeys(
        xml_unescape(m[1]) for m in t_pat.findall(text)
        if m[1].strip() and has_japanese(xml_unescape(m[1]))
    ))
    tmap: dict[str, str] = {}
    if unique:
        tmap = batch_translate(unique, context)
        def replace_t(m):
            plain  = xml_unescape(m.group(2))
            xlated = tmap.get(plain, plain)
            return m.group(1) + xml_escape(xlated) + m.group(3)
        text = t_pat.sub(replace_t, text)

    if not tmap:
        return text.encode("utf-8")

    # Only fix fonts and autofit in shapes that had Japanese text translated.
    # Shapes with no Japanese keep their original fonts.
    def _fix_shape(m: re.Match) -> str:
        body = m.group(2)
        texts = [xml_unescape(t[1]) for t in t_pat.findall(body)]
        if not any(orig in tmap for orig in texts):
            return m.group(0)
        body = re.sub(r'(<\w+:latin\b[^>]*\btypeface=")[^"]*(")', r'\1Arial\2', body)
        body = re.sub(r'(<\w+:ea\b[^>]*\btypeface=")[^"]*(")',    r'\1Arial\2', body)
        body = re.sub(r'(<\w+:cs\b[^>]*\btypeface=")[^"]*(")',    r'\1Arial\2', body)
        body = re.sub(r'<(\w+:)noAutofit/>',                       r'<\1normAutofit/>', body)
        return m.group(1) + body + m.group(3)

    text = _SP_PAT.sub(_fix_shape, text)
    return text.encode("utf-8")


def _translate_shared_strings(xml_bytes: bytes, context: str) -> bytes:
    text       = xml_bytes.decode("utf-8")
    si_pat     = re.compile(r'<si>(.*?)</si>', re.DOTALL)
    plain_t    = re.compile(r'<t(?:\s[^>]*)?>([^<]*)</t>')
    run_pat    = re.compile(r'<r\b[^>]*>(.*?)</r>', re.DOTALL)
    matches    = list(si_pat.finditer(text))
    if not matches:
        return xml_bytes

    entries = []
    for m in matches:
        inner = m.group(1)
        if run_pat.findall(inner):
            # Rich text: multiple <r> runs, join all <t> values to form the full string
            all_t = plain_t.findall(inner)
            raw   = "".join(all_t)
            entries.append((m, True, raw, xml_unescape(raw)))
        else:
            # Plain text: single <t> element
            t_m = plain_t.search(inner)
            if t_m:
                entries.append((m, False, t_m.group(1), xml_unescape(t_m.group(1))))

    unique = list(dict.fromkeys(e[3] for e in entries if e[3].strip() and has_japanese(e[3])))
    if not unique:
        return xml_bytes
    tmap = batch_translate(unique, context)

    result = text
    for m, is_rich, _, plain in reversed(entries):
        xlated = tmap.get(plain, plain)
        if xlated == plain:
            continue
        translated = xml_escape(xlated)
        inner      = m.group(1)
        start, end = m.start(), m.end()

        if is_rich:
            runs = list(run_pat.finditer(inner))
            if not runs:
                continue
            # Keep only the last run with the full translation; drop all preceding runs.
            # Empty runs with <rPr> formatting left behind cause Excel's "String properties" repair error.
            last_run = runs[-1]
            last_run_inner = last_run.group(1)
            tp = plain_t.search(last_run_inner)
            if not tp:
                continue
            new_last_inner = last_run_inner[:tp.start(1)] + translated + last_run_inner[tp.end(1):]
            new_inner = inner[:runs[0].start()] + f"<r>{new_last_inner}</r>" + inner[last_run.end():]
        else:
            tp = plain_t.search(inner)
            if not tp:
                continue
            new_inner = inner[:tp.start(1)] + translated + inner[tp.end(1):]

        result = result[:start] + f"<si>{new_inner}</si>" + result[end:]

    # Strip phonetic ruby annotations from ALL entries — Japanese-specific, meaningless in English output.
    # Done after the translation loop so it covers both translated and untranslated entries.
    result = re.sub(r'<rPh\b[^>]*>.*?</rPh>', '', result, flags=re.DOTALL)
    result = re.sub(r'<phoneticPr\b[^>]*/>', '', result)

    return result.encode("utf-8")


def _translate_sheet_xml(xml_bytes: bytes, context: str) -> bytes:
    text   = xml_bytes.decode("utf-8")
    inline = re.findall(r'(<is><t>)(.*?)(</t></is>)', text, re.DOTALL)
    cached = re.findall(r'(<c [^>]*t="str"[^>]*>(?:<f[^>]*>[^<]*</f>)?<v>)([^<]+)(</v>)', text)

    all_unique = list(dict.fromkeys(
        [t[1] for t in inline if t[1].strip()] +
        [t[1] for t in cached if t[1].strip()]
    ))
    if not all_unique:
        return xml_bytes

    tmap = batch_translate(all_unique, context)

    def replace(m):
        orig   = m.group(2)
        xlated = tmap.get(xml_unescape(orig), xml_unescape(orig))
        return m.group(1) + xml_escape(xlated) + m.group(3)

    text = re.sub(r'(<is><t>)(.*?)(</t></is>)', replace, text, flags=re.DOTALL)
    text = re.sub(r'(<c [^>]*t="str"[^>]*>(?:<f[^>]*>[^<]*</f>)?<v>)([^<]+)(</v>)', replace, text)
    return text.encode("utf-8")


def _translate_workbook_xml(xml_bytes: bytes, context: str) -> tuple[bytes, dict[str, str]]:
    text  = xml_bytes.decode("utf-8")
    # Unescape &quot; etc. in tab names before processing.
    # A name like 4."Input" would be stored as 4.&quot;Input&quot; in the XML attribute
    names     = [(p, xml_unescape(n), s) for p, n, s in re.findall(r'(<sheet\b[^>]*\bname=")([^"]+)(")', text)]
    jp_names  = [n for _, n, _ in names if has_japanese(n)]
    if not jp_names:
        return xml_bytes, {}

    tmap      = batch_translate(jp_names, context)
    all_names = [n for _, n, _ in names]
    seen: set[str] = set(n.lower() for n in all_names if not has_japanese(n))

    sanitized: dict[str, str] = {}
    for n in all_names:
        if n not in tmap:
            continue
        en = tmap[n]
        for ch in r'\/?*[]':
            en = en.replace(ch, "-")
        en   = en.replace(":", "-").strip()[:31].rstrip()  # Excel tab names max 31 chars
        base, suffix = en, 2
        while en.lower() in seen:
            # Deduplicate: append _2, _3 ... if another tab already has this name
            tag = f"_{suffix}"
            en  = base[:31 - len(tag)] + tag
            suffix += 1
        seen.add(en.lower())
        sanitized[n] = en
        tmap[n]      = en

    for jp, en in sanitized.items():
        en_attr  = en.replace("&", "&amp;").replace('"', "&quot;")
        jp_attr  = jp.replace("&", "&amp;").replace('"', "&quot;")
        text     = text.replace(f'name="{jp_attr}"', f'name="{en_attr}"')

    return text.encode("utf-8"), tmap


def _patch_formula_sheet_refs(xml_bytes: bytes, sheet_name_map: dict[str, str]) -> bytes:
    if not sheet_name_map:
        return xml_bytes
    text = xml_bytes.decode("utf-8")
    for jp, en in sorted(sheet_name_map.items(), key=lambda x: -len(x[0])):
        text = text.replace(f"'{jp}'!", f"'{en}'!")
        text = text.replace(f"{jp}!",   f"'{en}'!")
    return text.encode("utf-8")


_JP_FONT_NAMES = re.compile(
    r'[　-鿿豈-﫿'   # CJK / fullwidth chars in the font name
    r'|Meiryo|MS\s*Gothic|MS\s*Mincho|Yu\s*Gothic|Yu\s*Mincho'
    r'|ＭＳ|メイリオ|游|宋体|SimSun|NSimSun|FangSong|KaiTi|MingLiU'
    r']',
    re.IGNORECASE,
)


def _set_fonts_arial_styles(xml_bytes: bytes) -> bytes:
    text = xml_bytes.decode("utf-8")

    def _fix_font_block(m: re.Match) -> str:
        block = m.group(0)
        name_m = re.search(r'<name\b[^>]*\bval="([^"]*)"', block)
        if name_m and _JP_FONT_NAMES.search(name_m.group(1)):
            block = re.sub(r'(<name\b[^>]*\bval=")[^"]*(")', r'\1Arial\2', block)
            block = re.sub(r'(<scheme\b[^>]*\bval=")[^"]*(")', r'\1none\2', block)
        return block

    text = re.sub(r'<font>.*?</font>', _fix_font_block, text, flags=re.DOTALL)
    return text.encode("utf-8")


def _set_fonts_arial_shared_strings(xml_bytes: bytes) -> bytes:
    text = xml_bytes.decode("utf-8")

    def _fix_rfont(m: re.Match) -> str:
        val = m.group(1)
        return f'<rFont val="Arial"/>' if _JP_FONT_NAMES.search(val) else m.group(0)

    text = re.sub(r'<rFont\b[^>]*\bval="([^"]*)"[^/]*/>', _fix_rfont, text)
    return text.encode("utf-8")


def _patch_docprops_app(xml_bytes: bytes, sheet_name_map: dict[str, str]) -> bytes:
    text = xml_bytes.decode("utf-8")
    for jp, en in sheet_name_map.items():
        text = text.replace(f">{jp}<", f">{en}<")
    return text.encode("utf-8")


def _find_drawing_paths(all_items: list[tuple]) -> set[str]:
    """
    Discover actual drawing XML paths by reading worksheet .rels files.
    This handles non-standard drawing locations used by third-party tools.
    Falls back to xl/drawings/*.xml if no rels found.
    """
    import posixpath
    drawing_paths: set[str] = set()
    rels_drawing_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"

    file_map = {item.filename: data for item, data in all_items}

    for fname in file_map:
        if not fname.startswith("xl/worksheets/_rels/") or not fname.endswith(".rels"):
            continue
        try:
            rels_xml = file_map[fname].decode("utf-8")
            for target in re.findall(
                rf'Type="{re.escape(rels_drawing_type)}"[^>]*Target="([^"]+)"', rels_xml
            ):
                # Target is relative to xl/worksheets/, resolve to full path
                base = "xl/worksheets/"
                full = posixpath.normpath(posixpath.join(base, target)).lstrip("/")
                drawing_paths.add(full)
        except Exception:
            pass

    # Fallback: if no rels found, use standard path pattern
    if not drawing_paths:
        for fname, _ in [(item.filename, d) for item, d in all_items]:
            if fname.startswith("xl/drawings/") and fname.endswith(".xml") and not fname.endswith(".rels"):
                drawing_paths.add(fname)

    return drawing_paths


def translate_xlsx(src: Path, dst: Path, context: str):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".tmp.xlsx")

    try:
        all_items: list[tuple] = []
        with zipfile.ZipFile(src, "r") as zin:
            for item in zin.infolist():
                all_items.append((item, zin.read(item.filename)))

        # Discover actual drawing paths from .rels files
        drawing_paths = _find_drawing_paths(all_items)

        # Translate workbook first to get sheet name map
        sheet_name_map: dict[str, str] = {}
        wb_translated: bytes = b""
        for item, data in all_items:
            if item.filename == "xl/workbook.xml":
                print("    Translating sheet tab names...")
                wb_translated, sheet_name_map = _translate_workbook_xml(data, context)
                break

        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for item, orig_data in all_items:
                fname = item.filename
                data  = orig_data

                if fname == "xl/calcChain.xml":
                    # Drop calcChain: it caches formula evaluation order by cell address,
                    # which becomes stale after we rewrite shared strings. Excel rebuilds it on open.
                    continue

                elif fname == "[Content_Types].xml":
                    text = data.decode("utf-8")
                    text = re.sub(
                        r'\s*<Override\b[^>]*PartName="/xl/calcChain\.xml"[^>]*/>\s*', '', text
                    )
                    data = text.encode("utf-8")

                elif fname == "xl/workbook.xml":
                    data = wb_translated

                elif fname == "xl/sharedStrings.xml":
                    print("    Translating shared strings...")
                    data = _translate_shared_strings(data, context)
                    data = _set_fonts_arial_shared_strings(data)

                elif fname == "xl/styles.xml":
                    print("    Setting fonts to Arial in styles...")
                    data = _set_fonts_arial_styles(data)

                elif fname.startswith("xl/worksheets/") and fname.endswith(".xml") and not fname.endswith(".rels"):
                    print(f"    Translating worksheet: {fname}")
                    data = _translate_sheet_xml(data, context)
                    data = _patch_formula_sheet_refs(data, sheet_name_map)

                elif fname in drawing_paths:
                    print(f"    Translating drawing: {fname}")
                    data = _translate_drawing_xml(data, context)

                elif fname == "docProps/app.xml":
                    data = _patch_docprops_app(data, sheet_name_map)

                if data is orig_data:
                    zout.writestr(item, data)
                else:
                    # Reuse original ZipInfo metadata except compression, to avoid timestamp drift
                    new_info              = zipfile.ZipInfo(fname)
                    new_info.compress_type = zipfile.ZIP_DEFLATED
                    zout.writestr(new_info, data)

        if dst.exists():
            dst.unlink()
        tmp.rename(dst)

    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
