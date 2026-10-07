"""Shared text handling for the PDF builders.

Both ``pdf_builder`` and ``sample_builder`` need this, and ``pdf_builder`` already
imports from ``sample_builder``, so the helper lives here rather than in either one
to keep the module graph acyclic.
"""

from __future__ import annotations

import re

# Ranges Arial cannot draw. CJK punctuation and full-width forms matter as much as
# the ideographs: a full-width comma in an Arial paragraph is also a box.
CJK_RUN = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]+")


def with_cjk_font(text: str) -> str:
    """Wrap CJK runs so a Latin-styled paragraph can actually draw them.

    reportlab does not fall back between fonts inside a Paragraph: a paragraph
    styled with Arial draws every character with Arial, so any Chinese inside it
    renders as a .notdef box. That shipped 548 boxes (the Chinese heading on every
    story page), 744 more (Chinese meanings quoted inside exercise prompts), and
    168 more in the sample volumes - none of which any text-extraction check could
    see.

    ``text`` must already be HTML-escaped and must contain only our own markup, so
    the substitution cannot corrupt an entity or a tag.
    """

    return CJK_RUN.sub(
        lambda match: f'<font name="CETChinese">{match.group(0)}</font>', text
    )
