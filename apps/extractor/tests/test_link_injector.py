import pymupdf

from src.parsing.link_injector import inject_links_inline


def test_link_injection_with_hyperlink():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)

    # Insert text and add a link annotation
    rect = pymupdf.Rect(45, 45, 300, 80)
    page.insert_text(pymupdf.Point(50, 65), "Visit Whimsync for details")
    page.insert_link(
        {
            "kind": pymupdf.LINK_URI,
            "from": rect,
            "uri": "https://whimsync.io",
        }
    )

    # Save to bytes and reload so PyMuPDF builds internal annotation and word structures
    pdf_bytes = doc.tobytes()
    doc.close()
    reloaded_doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = reloaded_doc[0]

    markdown_input = "Visit Whimsync for details and documentation."
    injected_md = inject_links_inline(page, markdown_input)

    assert (
        "[Visit Whimsync](https://whimsync.io)" in injected_md
        or "[Whimsync](https://whimsync.io)" in injected_md
        or "https://whimsync.io" in injected_md
    )
    reloaded_doc.close()


def test_link_injection_no_links():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text(pymupdf.Point(50, 65), "Plain digital text without links.")

    markdown_input = "Plain digital text without links."
    result = inject_links_inline(page, markdown_input)

    assert result == markdown_input
    doc.close()


def _reload(doc: pymupdf.Document) -> pymupdf.Document:
    pdf_bytes = doc.tobytes()
    doc.close()
    return pymupdf.open(stream=pdf_bytes, filetype="pdf")


def _word_rect(page: pymupdf.Page, text: str) -> pymupdf.Rect:
    return next(pymupdf.Rect(w[:4]) for w in page.get_text("words") if w[4] == text)


def _add_uri(page: pymupdf.Page, rect: pymupdf.Rect, uri: str) -> None:
    page.insert_link({"kind": pymupdf.LINK_URI, "from": rect, "uri": uri})


def test_split_annotations_merge_into_one_anchor():
    """One hyperlink stored as per-word + per-space annotations (common in PDF exporters)."""
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text(pymupdf.Point(50, 65), "See the PostgreSQL documentation closely.")
    doc = _reload(doc)
    page = doc[0]

    uri = "https://www.postgresql.org/docs/"
    first, second = _word_rect(page, "PostgreSQL"), _word_rect(page, "documentation")
    _add_uri(page, first, uri)
    _add_uri(page, pymupdf.Rect(first.x1, first.y0, second.x0, first.y1), uri)  # the space
    _add_uri(page, second, uri)
    doc = _reload(doc)

    result = inject_links_inline(doc[0], "See the PostgreSQL documentation closely.")

    assert result == f"See the [PostgreSQL documentation]({uri}) closely."
    doc.close()


def test_link_wrapped_across_lines_is_one_anchor():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text(pymupdf.Point(50, 65), "Read the pgvector")
    page.insert_text(pymupdf.Point(50, 80), "extension guide today.")
    doc = _reload(doc)
    page = doc[0]

    uri = "https://github.com/pgvector/pgvector"
    _add_uri(page, _word_rect(page, "pgvector"), uri)
    _add_uri(page, _word_rect(page, "extension"), uri)
    doc = _reload(doc)

    result = inject_links_inline(doc[0], "Read the pgvector\nextension guide today.")

    assert result == f"Read the [pgvector\nextension]({uri}) guide today."
    doc.close()


def test_adjacent_links_with_different_targets_stay_separate():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=800)
    page.insert_text(pymupdf.Point(50, 65), "Use Redis BullMQ here.")
    doc = _reload(doc)
    page = doc[0]

    _add_uri(page, _word_rect(page, "Redis"), "https://redis.io")
    _add_uri(page, _word_rect(page, "BullMQ"), "https://docs.bullmq.io")
    doc = _reload(doc)

    result = inject_links_inline(doc[0], "Use Redis BullMQ here.")

    assert result == "Use [Redis](https://redis.io) [BullMQ](https://docs.bullmq.io) here."
    doc.close()
