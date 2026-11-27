import re
from collections import defaultdict
from typing import Any

import pymupdf


def _link_target(link: dict[str, Any]) -> str | None:
    kind = link.get("kind")
    if kind == pymupdf.LINK_URI:
        return link.get("uri")
    if kind == pymupdf.LINK_GOTO:
        dest_page = link.get("page", -1)
        return f"#page-{dest_page + 1}" if dest_page >= 0 else None
    if kind == pymupdf.LINK_GOTOR:
        return link.get("file") or link.get("uri")
    return None


def _extract_page_links(page: pymupdf.Page) -> list[dict[str, Any]]:
    """
    Extracts {text, uri, rect} for actionable links on the page.

    PDF producers often split one hyperlink into several annotations (one per
    word, per inter-word space, or per wrapped line). Fragments with the same
    target whose words are adjacent in reading order are merged back into a
    single link, so "PostgreSQL documentation" stays one anchor.
    """
    # Words in reading order: (x0, y0, x1, y1, text, block, line, word).
    words = sorted(page.get_text("words"), key=lambda w: (w[5], w[6], w[7]))

    fragments = []
    for link in page.get_links():
        target = _link_target(link)
        if not target:
            continue

        rect = pymupdf.Rect(link["from"])
        hit_indices = []
        for idx, w in enumerate(words):
            wrect = pymupdf.Rect(w[:4])
            inter = wrect & rect
            if wrect.get_area() > 0 and inter.get_area() > 0.2 * wrect.get_area():
                hit_indices.append(idx)

        if hit_indices:
            fragments.append({"uri": target, "rect": rect, "indices": hit_indices})

    fragments.sort(key=lambda f: f["indices"][0])

    merged: list[dict[str, Any]] = []
    for frag in fragments:
        prev = merged[-1] if merged else None
        # Adjacent (or overlapping) words with the same target belong to one link.
        if prev and prev["uri"] == frag["uri"] and frag["indices"][0] <= prev["indices"][-1] + 1:
            prev["indices"] = sorted(set(prev["indices"]) | set(frag["indices"]))
            prev["rect"] = prev["rect"] | frag["rect"]
        else:
            merged.append({**frag, "indices": list(frag["indices"])})

    links = []
    for item in merged:
        text = re.sub(r"\s+", " ", " ".join(words[i][4] for i in item["indices"])).strip()
        if text:
            links.append({"text": text, "uri": item["uri"], "rect": item["rect"]})

    links.sort(key=lambda item: (round(item["rect"].y0, 1), item["rect"].x0))
    return links


def inject_links_inline(page: pymupdf.Page, md_text: str) -> str:
    """
    Injects markdown links [anchor text](uri) into generated Markdown text.
    Uses positional zipping to avoid over-linking duplicate anchor texts and
    avoids nesting within existing markdown links.
    """
    links = _extract_page_links(page)
    if not links or not md_text.strip():
        return md_text

    grouped_uris = defaultdict(list)
    for link in links:
        grouped_uris[link["text"]].append(link["uri"])

    candidates = []
    for text, uris in grouped_uris.items():
        words = [re.escape(w) for w in text.split(" ") if w]
        if not words:
            continue

        pattern = r"[\s*_`]+".join(words)
        try:
            regex = re.compile(pattern)
        except re.error:
            continue

        matches = []
        for m in regex.finditer(md_text):
            start, end = m.span()
            before = md_text[:start]
            # Avoid wrapping if already inside a markdown link [ ... ]
            if before.count("[") > before.count("]"):
                continue
            matches.append((start, end))

        for (start, end), uri in zip(matches, uris):
            candidates.append((start, end, uri))

    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))

    selected = []
    last_end = -1
    for start, end, uri in candidates:
        if start >= last_end:
            selected.append((start, end, uri))
            last_end = end

    if not selected:
        return md_text

    out = []
    cursor = 0
    for start, end, uri in selected:
        out.append(md_text[cursor:start])
        out.append(f"[{md_text[start:end]}]({uri})")
        cursor = end
    out.append(md_text[cursor:])

    return "".join(out)
