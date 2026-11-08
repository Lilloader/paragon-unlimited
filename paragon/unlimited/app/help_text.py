"""Help pages written as plain text files.

Every page is one file in Data/<game>/Help/, named after the page id (for example
``map_maker.txt``). The file starts with a few settings, then a line with three dashes, then
the text of the page:

    Title: Map Maker
    Lesson: 2                       (only for tutorial lessons: their number)
    Order: 30                       (where reference pages go in the list, low numbers first)
    Opens for: MapMaker, TemplateGallery   (windows whose F1 key opens this page)
    ---
    Text of the page...

    ## Files it changes         (optional, at the end: hidden until the reader clicks
    - *data/GameData.bin.lz* ...  "See what files this changes")

The text uses a few simple marks (see Data/FE13/Help/_HOW_TO_WRITE.txt); everything else is
shown as it is written.
"""
import html
import os
import re
from typing import Dict, List, Optional

HEADER_KEYS = {"title": "title", "lesson": "tutorial", "order": "order", "opens for": "windows"}

_INLINE = [
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"<i>\1</i>"),
    (re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)"), r'<a href="\2">\1</a>'),
]


def inline_html(text: str) -> str:
    out = html.escape(text, quote=False)
    for pattern, repl in _INLINE:
        out = pattern.sub(repl, out)
    return out


PICTURE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")
PICTURE_WIDTH = 560  # pixels in the help window (the picture keeps its shape)


def picture_size(path: str) -> Optional[tuple]:
    """(width, height) of a PNG (from its header), None for other files."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except OSError:
        pass
    return None


def picture_html(caption: str, src: str, folder: Optional[str] = None) -> str:
    """A picture on its own line: ![caption](pictures/file.png), file in the Help folder. Shown
    PICTURE_WIDTH pixels wide, or smaller when the picture itself is smaller."""
    width = PICTURE_WIDTH
    size = picture_size(os.path.join(folder, src)) if folder else None
    if size:
        width = min(width, size[0])
    cap = f"<br><i>{inline_html(caption)}</i>" if caption.strip() else ""
    return f'<p align="center"><img src="{html.escape(src)}" width="{width}">{cap}</p>'


def text_to_html(text: str, folder: Optional[str] = None) -> str:
    """Turn the simple marks into the HTML the help window shows."""
    blocks: List[str] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    para: List[str] = []

    def flush_para():
        if para:
            joined = " ".join(s.strip() for s in para)
            if joined.startswith("{{") and joined.endswith("}}"):
                blocks.append(joined)  # {{emotions}}, {{dialogue_commands}}: filled in later
            else:
                blocks.append(f"<p>{inline_html(joined)}</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        pic = PICTURE.match(stripped)
        if pic:
            flush_para()
            blocks.append(picture_html(pic.group(1), pic.group(2), folder))
            i += 1
            continue
        if stripped.startswith("## "):
            flush_para()
            blocks.append(f"<h3>{inline_html(stripped[3:].strip())}</h3>")
            i += 1
            continue
        if stripped == "```":  # example text shown exactly as written
            flush_para()
            j = i + 1
            code = []
            while j < len(lines) and lines[j].strip() != "```":
                code.append(lines[j])
                j += 1
            blocks.append("<pre>" + html.escape("\n".join(code), quote=False) + "</pre>")
            i = j + 1
            continue
        bullet = re.match(r"^- (.*)", stripped)
        number = re.match(r"^\d+\. (.*)", stripped)
        if bullet or number:
            flush_para()
            tag = "ul" if bullet else "ol"
            items: List[str] = []
            while i < len(lines):
                s = lines[i].strip()
                m = re.match(r"^- (.*)", s) if tag == "ul" else re.match(r"^\d+\. (.*)", s)
                if m:
                    items.append(m.group(1))
                elif s and items and not s.startswith("## ") and not re.match(r"^(- |\d+\. )", s):
                    items[-1] += " " + s  # an item that goes on over several lines
                else:
                    break
                i += 1
            blocks.append(f"<{tag}>" + "".join(f"<li>{inline_html(t)}</li>" for t in items) + f"</{tag}>")
            continue
        para.append(line)
        i += 1
    flush_para()
    return "\n".join(blocks)


def parse_page(text: str, folder: Optional[str] = None) -> dict:
    """Settings + body of one help file."""
    text = text.lstrip("﻿")
    head, sep, body = text.partition("\n---")
    if not sep:
        head, body = "", text
    else:
        body = body.split("\n", 1)[1] if "\n" in body else ""
    page = {"title": "", "windows": [], "body_text": body.strip("\n")}
    for line in head.splitlines():
        key, colon, value = line.partition(":")
        key = key.strip().lower()
        if not colon or key not in HEADER_KEYS:
            continue
        value = value.strip()
        name = HEADER_KEYS[key]
        if name == "windows":
            page[name] = [w.strip() for w in value.split(",") if w.strip()]
        elif name in ("tutorial", "order"):
            page[name] = int(value) if value.isdigit() else None
        else:
            page[name] = value
    body_text, files_text = split_files(page["body_text"])
    page["body"] = text_to_html(body_text, folder)
    page["files"] = text_to_html(files_text, folder) if files_text.strip() else ""
    return page


FILES_HEADING = re.compile(r"^##\s*Files it changes\s*$", re.IGNORECASE | re.MULTILINE)


def split_files(body: str):
    """The page text and its '## Files it changes' section (shown when the reader asks for it)."""
    m = FILES_HEADING.search(body)
    if not m:
        return body, ""
    return body[: m.start()].rstrip("\n"), body[m.end():].strip("\n")


def load_folder(folder: str) -> Dict[str, dict]:
    """All pages of a Help folder: lessons by number, then reference pages by Order."""
    pages = {}
    if not os.path.isdir(folder):
        return pages
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".txt") or name.startswith("_"):
            continue
        with open(os.path.join(folder, name), "r", encoding="utf-8") as f:
            pages[name[:-4]] = parse_page(f.read(), folder)
    lessons = sorted((p for p in pages.items() if p[1].get("tutorial")), key=lambda p: p[1]["tutorial"])
    reference = sorted((p for p in pages.items() if not p[1].get("tutorial")),
                       key=lambda p: (p[1].get("order") is None, p[1].get("order") or 0, p[1]["title"]))
    return dict(lessons + reference)


def read_text(folder: str, name: str) -> Optional[str]:
    path = os.path.join(folder, name)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
