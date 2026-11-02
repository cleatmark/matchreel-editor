"""Turn the in-app user guide (tools/editor/static/guide.html) into public docs.

Two outputs, both generated at export time so the guide stays a single source:
  * docs/USER_GUIDE.md        - renders directly on GitHub (images in docs/guide/images/)
  * docs/guide/index.html     - the same page the app serves, for GitHub Pages (images relative)
Standard library only.
"""
import os
import re
import shutil
from html.parser import HTMLParser

VOID = {"br", "img", "input", "meta", "link", "hr", "path"}
SKIP = {"head", "style", "script", "aside", "nav", "svg", "input", "title"}
INLINE = {"a", "strong", "b", "em", "i", "code", "kbd", "span", "br", "img", "mark", "small", "sub", "sup"}
SKIP_CLASSES = {"dots", "dot", "screenshot-header", "hero-badge", "sidebar-header", "search-box", "callout-icon"}
CALLOUT_LABEL = {"callout-info": "Info", "callout-warning": "Warning", "callout-tip": "Tip", "callout-danger": "Important"}


class Node:
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.kids = tag, dict(attrs), []

    @property
    def classes(self):
        return set((self.attrs.get("class") or "").split())


class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", [])
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].kids.append(n)
        if tag not in VOID:
            self.stack.append(n)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].kids.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].kids.append(data)


def _text(n):
    if isinstance(n, str):
        return n
    return "".join(_text(k) for k in n.kids)


def _squash(s):
    return re.sub(r"\s+", " ", s)


def _img(n, prefix):
    src = (n.attrs.get("src") or "").split("?")[0]
    name = src.rsplit("/", 1)[-1]
    return f"![{n.attrs.get('alt', '')}]({prefix}{name})"


def inline(n, prefix):
    if isinstance(n, str):
        return _squash(n)
    t = n.tag
    if t in SKIP or n.classes & SKIP_CLASSES:
        return ""
    inner = "".join(inline(k, prefix) for k in n.kids)
    if t == "br":
        return "<br>"
    if t == "img":
        return _img(n, prefix)
    if t in ("strong", "b"):
        s = inner.strip()
        return f"**{s}**" if s else ""
    if t in ("em", "i"):
        s = inner.strip()
        return f"*{s}*" if s else ""
    if t == "code":
        s = _text(n).strip().replace("`", "'")
        return f"`{s}`" if s else ""
    if t == "kbd":
        s = _text(n).strip()
        return f"<kbd>{s}</kbd>" if s else ""
    if t == "a":
        href = n.attrs.get("href") or ""
        s = inner.strip()
        return f"[{s}]({href})" if href.startswith("http") and s else inner
    if n.classes & {"chip"}:
        s = _text(n).strip()
        return f"`{s}`" if s else ""
    return inner


def _cell(n, prefix):
    return inline(n, prefix).strip().replace("|", "\\|") or " "


def table(n, prefix):
    rows = []

    def walk(x):
        for k in x.kids:
            if isinstance(k, str):
                continue
            if k.tag == "tr":
                rows.append([_cell(c, prefix) for c in k.kids if not isinstance(c, str) and c.tag in ("td", "th")])
            else:
                walk(k)
    walk(n)
    rows = [r for r in rows if r]
    if not rows:
        return []
    w = max(len(r) for r in rows)
    rows = [r + [" "] * (w - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return ["\n".join(out)]


def lst(n, prefix, depth=0):
    lines = []
    num = 0
    for li in n.kids:
        if isinstance(li, str) or li.tag != "li":
            continue
        num += 1
        mark = f"{num}." if n.tag == "ol" else "-"
        own, nested = [], []
        for k in li.kids:
            if not isinstance(k, str) and k.tag in ("ul", "ol"):
                nested.append(k)
            else:
                own.append(inline(k, prefix) if not (not isinstance(k, str) and k.tag in ("div", "p")) else inline(k, prefix) + " ")
        text = re.sub(r"\s+", " ", "".join(own)).strip()
        lines.append("  " * depth + f"{mark} {text}")
        for sub in nested:
            lines += lst(sub, prefix, depth + 1)
    return lines


def blocks(n, prefix):
    """Return a list of markdown blocks (strings) for node n."""
    if isinstance(n, str):
        s = _squash(n).strip()
        return [s] if s else []
    t = n.tag
    if t in SKIP or n.classes & SKIP_CLASSES:
        return []
    if t in ("h1", "h2", "h3", "h4"):
        return ["#" * int(t[1]) + " " + re.sub(r"\s+", " ", inline(n, prefix)).strip()]
    if t == "p":
        s = inline(n, prefix).strip()
        return [s] if s else []
    if t in ("ul", "ol"):
        return ["\n".join(lst(n, prefix))]
    if t == "table":
        return table(n, prefix)
    if t == "pre":
        return ["```\n" + _text(n).strip("\n") + "\n```"]
    if t == "img":
        return [_img(n, prefix)]
    cls = n.classes
    if "screenshot-frame" in cls:
        out = []
        for k in n.kids:
            if isinstance(k, str):
                continue
            if k.tag == "img":
                out.append(_img(k, prefix))
            elif "screenshot-caption" in k.classes:
                c = inline(k, prefix).strip()
                if c:
                    out.append(f"*{c}*")
        return ["\n\n".join(out)] if out else []
    if cls & {"step-grid", "workflow-checklist"}:
        items = []
        for k in n.kids:
            if not isinstance(k, str) and "step-card" in k.classes:
                items.append("- " + _step(k, prefix))
        return ["\n".join(items)]
    if "step-card" in cls:
        return ["- " + _step(n, prefix)]
    if any(c.startswith("callout") for c in cls):
        label = next((CALLOUT_LABEL[c] for c in cls if c in CALLOUT_LABEL), "Note")
        body = []
        for k in n.kids:
            if not isinstance(k, str) and "callout-body" in k.classes:
                body = blocks_of_children(k, prefix)
        if not body:
            body = blocks_of_children(n, prefix)
        text = "\n\n".join(body)
        lines = [f"**{label}.** " + text.split("\n", 1)[0]] + (text.split("\n", 1)[1].split("\n") if "\n" in text else [])
        return ["\n".join(("> " + l) if l.strip() else ">" for l in lines)]
    if t in ("div", "section", "main", "body", "html", "article", "li", "root", "header", "footer", "span", "a", "strong", "em", "code"):
        return blocks_of_children(n, prefix)
    return blocks_of_children(n, prefix)


def _step(n, prefix):
    num = title = desc = ""
    for k in n.kids:
        if isinstance(k, str):
            continue
        if "step-num" in k.classes:
            num = inline(k, prefix).strip()
        elif "step-title" in k.classes:
            title = inline(k, prefix).strip()
        elif "step-desc" in k.classes:
            desc = inline(k, prefix).strip()
    if not (title or desc):
        flat = inline(n, prefix).strip()
        flat = re.sub(r"\s*(<br>\s*)+", " - ", flat, count=1).replace("<br>", " ")
        return re.sub(r"\s+", " ", flat).strip()
    head = f"**{num}. {title}**" if num and title else (f"**{title}**" if title else "")
    return (head + (" - " if head and desc else "") + desc).strip()


def blocks_of_children(n, prefix):
    out, run = [], []

    def flush():
        s = re.sub(r"\s+", " ", "".join(run)).strip()
        if s:
            out.append(s)
        run.clear()
    for k in n.kids:
        if isinstance(k, str) or (k.tag in INLINE and not (k.classes & SKIP_CLASSES) and k.tag != "img"):
            run.append(inline(k, prefix))
        else:
            flush()
            out.extend(blocks(k, prefix))
    flush()
    return out


def html_to_markdown(html, image_prefix, header=""):
    b = Builder()
    b.feed(html)
    body = next((k for k in _walk(b.root) if k.tag == "main"), b.root)
    parts = blocks_of_children(body, image_prefix)
    md = "\n\n".join(parts)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return (header.rstrip() + "\n\n" if header else "") + md


def _walk(n):
    for k in n.kids:
        if not isinstance(k, str):
            yield k
            yield from _walk(k)


MD_HEADER = """> Unofficial community tool, not affiliated with or endorsed by XbotGo.
> This page is generated from the in-app guide. A styled version is available on GitHub Pages: see the README.
"""


def pages_html(html):
    h = html.replace("/guide/images/", "images/")
    h = re.sub(r'\?v=\d+', "", h)
    h = re.sub(r'<a href="/"[^>]*>[^<]*</a>', "", h)
    return h


REDIRECT = ('<!doctype html><meta charset="utf-8"><title>User guide</title>'
            '<meta http-equiv="refresh" content="0; url=guide/"><a href="guide/">User guide</a>\n')


def write_guide_docs(root, dst):
    """Create docs/USER_GUIDE.md, docs/guide/index.html (+ images), docs/index.html, docs/.nojekyll in dst."""
    src = os.path.join(root, "tools", "editor", "static", "guide.html")
    html = open(src, encoding="utf-8").read()
    docs = os.path.join(dst, "docs")
    gimg = os.path.join(docs, "guide", "images")
    os.makedirs(gimg, exist_ok=True)
    simg = os.path.join(root, "tools", "editor", "static", "guide", "images")
    if os.path.isdir(simg):
        for f in os.listdir(simg):
            shutil.copy2(os.path.join(simg, f), os.path.join(gimg, f))
    def w(rel, text):
        p = os.path.join(docs, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    w("USER_GUIDE.md", html_to_markdown(html, "guide/images/", MD_HEADER))
    w("guide/index.html", pages_html(html))
    w("index.html", REDIRECT)
    w(".nojekyll", "")


if __name__ == "__main__":
    import sys
    r = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    write_guide_docs(r, sys.argv[1] if len(sys.argv) > 1 else os.path.join(r, "tmp", "guide_try"))
