"""Post body rendering: Markdown (or legacy HTML / plain text) to sanitized HTML.

Writing conventions:
- An image on its own line becomes a full-width figure. The [alt text] doubles as the caption,
  or use ![alt](url "Caption") when they should differ. ![](url) has no caption.
- Several images on consecutive lines (no blank line between) become a photo gallery.
"""
import re
import xml.etree.ElementTree as etree

import markdown
import nh3
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

PROSE_CLASSES = (
    "post-body prose prose-lg prose-neutral max-w-none font-serif text-[1.15rem] md:text-[1.2rem] "
    "prose-headings:font-sans prose-headings:font-bold prose-headings:tracking-tight prose-headings:text-ink "
    "prose-h2:mt-14 prose-h2:text-[1.75rem] md:prose-h2:text-3xl prose-h3:text-2xl "
    "prose-p:leading-[1.8] prose-li:leading-[1.75] prose-strong:text-ink "
    "prose-a:text-forest prose-a:decoration-forest/40 prose-a:decoration-2 prose-a:underline-offset-4 "
    "hover:prose-a:decoration-forest prose-blockquote:border-l-4 prose-blockquote:border-l-forest "
    "prose-blockquote:font-normal prose-blockquote:not-italic prose-blockquote:text-ink "
    "prose-hr:my-14 prose-code:font-mono prose-code:text-[0.9em]"
)

ALLOWED_TAGS = {
    "p", "br", "hr", "h2", "h3", "h4", "h5", "h6", "strong", "b", "em", "i", "u", "s", "del", "mark",
    "small", "sub", "sup", "a", "ul", "ol", "li", "blockquote", "figure", "figcaption", "img", "div",
    "span", "code", "pre", "kbd", "table", "thead", "tbody", "tr", "th", "td", "dl", "dt", "dd", "abbr",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title", "class", "id"},
    "img": {"src", "alt", "title", "width", "height", "loading", "decoding"},
    "div": {"class"},
    "figure": {"class"},
    "code": {"class"},
    "ol": {"start"},
    "li": {"id"},
    "sup": {"id"},
    "th": {"align"},
    "td": {"align"},
    "abbr": {"title"},
}
ALLOWED_CLASSES = {"gallery", "cols-2", "cols-3", "footnote", "footnote-ref", "footnote-backref"}


def _filter_attribute(tag, attr, value):
    if attr != "class":
        return value
    if tag == "code":
        return value if re.fullmatch(r"language-[\w-]+", value) else None
    kept = " ".join(c for c in value.split() if c in ALLOWED_CLASSES)
    return kept or None


def _only_images(p):
    if (p.text or "").strip():
        return None
    images = []
    for child in p:
        if (child.tail or "").strip():
            return None
        if child.tag == "img":
            images.append(child)
        elif child.tag != "br":
            return None
    return images or None


def _figure(img):
    figure = etree.Element("figure")
    caption = img.attrib.pop("title", "") or img.get("alt", "")
    img.tail = None
    img.set("loading", "lazy")
    img.set("decoding", "async")
    figure.append(img)
    if caption.strip():
        figcaption = etree.SubElement(figure, "figcaption")
        figcaption.text = caption.strip()
    return figure


class FigureTreeprocessor(Treeprocessor):
    def run(self, root):
        for heading in root.iter("h1"):
            heading.tag = "h2"
        for p in list(root.iter("p")):
            images = _only_images(p)
            if not images:
                continue
            figures = [_figure(img) for img in images]
            p.clear()
            if len(figures) == 1:
                p.tag = "figure"
                p.extend(list(figures[0]))
            else:
                n = len(figures)
                p.tag = "div"
                p.set("class", f"gallery {'cols-3' if n == 3 or n >= 5 else 'cols-2'}")
                p.extend(figures)


class FigureExtension(Extension):
    def extendMarkdown(self, md):
        # After inline parsing (priority 20) so <img> elements exist.
        md.treeprocessors.register(FigureTreeprocessor(md), "lot_figures", 15)


def render_markdown(text):
    html = markdown.markdown(
        text or "", extensions=["extra", "sane_lists", "smarty", FigureExtension()], output_format="html"
    )
    clean = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        attribute_filter=_filter_attribute,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )
    return mark_safe(clean)


def plain_text(text):
    return re.sub(r"\s+", " ", strip_tags(render_markdown(text))).strip()
