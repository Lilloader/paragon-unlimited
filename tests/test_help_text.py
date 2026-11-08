"""Help pages as plain text files (Data/FE13/Help/*.txt, paragon/unlimited/help_text.py)."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

from paragon.unlimited.app import help_text

FOLDER = os.path.join("Data", "FE13", "Help")


def check(cond, what):
    if not cond:
        raise AssertionError(what)


def test_marks():
    page = help_text.parse_page(
        "Title: Test page\nLesson: 3\nOpens for: A, B\n---\n"
        "First line\njoined.\n\n## Heading\n\n- one **bold**\n  goes on\n- two *italic*\n\n"
        "1. step [link](topic:main)\n2. web [site](https://example.com)\n\n"
        "```\n$SetSpeaker(Chrom)\n<keep>\n```\n\n{{emotions}}\n\nA -> B & ★\n")
    check(page["title"] == "Test page" and page["tutorial"] == 3 and page["windows"] == ["A", "B"], page)
    h = page["body"]
    check("<p>First line joined.</p>" in h, h)
    check("<h3>Heading</h3>" in h, h)
    check("<ul><li>one <b>bold</b> goes on</li><li>two <i>italic</i></li></ul>" in h, h)
    check('<ol><li>step <a href="topic:main">link</a></li><li>web <a href="https://example.com">site</a></li></ol>' in h, h)
    check("<pre>$SetSpeaker(Chrom)\n&lt;keep&gt;</pre>" in h, h)
    check("\n{{emotions}}\n" in h + "\n", h)
    check("<p>A -&gt; B &amp; ★</p>" in h, h)
    check(help_text.parse_page("no settings\n")["body"] == "<p>no settings</p>", "file without a top part")
    pic = help_text.text_to_html("Before\n![The *first* page](pictures/home.png)\nAfter")
    check(pic == '<p>Before</p>\n<p align="center"><img src="pictures/home.png" width="560"><br><i>The <i>first</i> '
          'page</i></p>\n<p>After</p>', pic)
    check('<img src="pictures/a.png"' in help_text.text_to_html("![](pictures/a.png)")
          and "<br>" not in help_text.text_to_html("![](pictures/a.png)"), "picture without a caption")
    print("marks: ok")


def test_pages():
    pages = help_text.load_folder(FOLDER)
    check(len(pages) >= 35, len(pages))
    check(not any(k.startswith("_") for k in pages), "files starting with _ are not pages")
    lessons = [k for k, p in pages.items() if p.get("tutorial")]
    check([pages[k]["tutorial"] for k in lessons] == list(range(1, len(lessons) + 1)), "lessons in order")
    check(list(pages)[len(lessons)] == "main", "Getting started first after the lessons")
    for k, p in pages.items():
        check(p["title"], f"{k} has a title")
        for link in re.findall(r"topic:([a-z_0-9]+)", p["body"]):
            check(link in pages, f"{k} links to missing page {link}")
        check("**" not in p["body"], f"{k}: unmatched ** bold mark")
        for src in re.findall(r'<img src="([^"]+)"', p["body"] + p["files"]):
            check(os.path.isfile(os.path.join(FOLDER, src)), f"{k}: picture {src} is missing")
    for name in os.listdir(FOLDER):
        if not name.endswith(".txt"):
            continue
        with open(os.path.join(FOLDER, name), "rb") as f:
            check(b"colour" not in f.read().lower(), f"US spelling in {name}")
    check("thane98" in help_text.read_text(FOLDER, "_Acknowledgments.txt"), "license notice kept")
    for k in ("characters", "classes", "items", "skills", "map_maker", "sprite_workshop", "chapters", "facedata"):
        check(pages[k]["files"] and "Files it changes" not in pages[k]["body"], f"{k}: files section split off")
    check("static.bin.lz" in pages["characters"]["files"], "characters list their file")
    body, files = help_text.split_files("Text\n\n## Files it changes\n\n- *a.bin*\n")
    check(body == "Text" and files == "- *a.bin*", (body, files))
    check(help_text.split_files("No files")[1] == "", "pages without a section")
    small = help_text.picture_html("", "pictures/enemies_and_win.png", FOLDER)
    check('width="430"' in small, small)  # smaller pictures are not blown up
    check(sum('<img src="pictures/' in p["body"] for p in pages.values()) >= 6, "lessons have pictures")
    print("pages: ok", len(pages))


if __name__ == "__main__":
    test_marks()
    test_pages()
    print("help text test: all checks passed")
