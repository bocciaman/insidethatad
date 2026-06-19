#!/usr/bin/env python3
"""
WordPress XML export → Hugo Markdown converter for insidethatad.net
Converts posts and pages to Hugo front matter + content files.
"""

import xml.etree.ElementTree as ET
import os
import re
import sys
from datetime import datetime
from pathlib import Path
import html

# Namespaces in WordPress WXR format
NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "wp": "http://wordpress.org/export/1.2/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
}


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text


def fix_image_urls(content):
    """Rewrite wp-content/uploads URLs to /img/ for Hugo static serving."""
    content = re.sub(
        r'https?://(?:www\.)?insidethatad\.(?:net|com)/wp-content/uploads/',
        '/img/',
        content
    )
    # Also handle bare /wp-content/uploads/ paths
    content = re.sub(r'/wp-content/uploads/', '/img/', content)
    return content


def wp_content_to_markdown(content):
    """Basic HTML → Markdown conversion for common WordPress patterns."""
    if not content:
        return ""

    # Fix image URLs first
    content = fix_image_urls(content)

    # Strip WordPress shortcodes: [caption]...[/caption] → keep inner content
    content = re.sub(r'\[caption[^\]]*\](.*?)\[/caption\]', r'\1', content, flags=re.DOTALL)
    # Strip remaining self-closing or unknown shortcodes like [gallery], [embed], etc.
    content = re.sub(r'\[/?[a-z_]+[^\]]*\]', '', content)

    # Gutenberg blocks: strip block comments
    content = re.sub(r"<!-- /?wp:[^\-].*?-->", "", content, flags=re.DOTALL)

    # Convert <h1>-<h6>
    for i in range(6, 0, -1):
        content = re.sub(rf"<h{i}[^>]*>(.*?)</h{i}>", r"#" * i + r" \1", content, flags=re.IGNORECASE | re.DOTALL)

    # Convert <strong> and <b>
    content = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", content, flags=re.IGNORECASE | re.DOTALL)

    # Convert <em> and <i>
    content = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", content, flags=re.IGNORECASE | re.DOTALL)

    # Convert <a href="...">text</a>
    content = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r"[\2](\1)", content, flags=re.IGNORECASE | re.DOTALL)

    # Convert <img> tags
    content = re.sub(r'<img[^>]*src=["\']([^"\']*)["\'][^>]*alt=["\']([^"\']*)["\'][^>]*/?>',
                     r"![\2](\1)", content, flags=re.IGNORECASE)
    content = re.sub(r'<img[^>]*src=["\']([^"\']*)["\'][^>]*/?>',
                     r"![](\1)", content, flags=re.IGNORECASE)

    # Convert <blockquote>
    content = re.sub(r"<blockquote[^>]*>(.*?)</blockquote>",
                     lambda m: "\n".join("> " + line for line in m.group(1).strip().splitlines()) + "\n",
                     content, flags=re.IGNORECASE | re.DOTALL)

    # Convert <ul>/<ol> lists
    content = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r"</?[uo]l[^>]*>", "\n", content, flags=re.IGNORECASE)

    # Protect iframes (YouTube, Vimeo, etc.) before stripping tags
    # Replace them with a placeholder, restore after tag stripping
    iframes = []
    def stash_iframe(m):
        iframes.append(m.group(0))
        return f"\n\nIFRAME_PLACEHOLDER_{len(iframes)-1}\n\n"
    content = re.sub(r"<iframe[^>]*>.*?</iframe>", stash_iframe, content, flags=re.IGNORECASE | re.DOTALL)

    # Convert <p> and <br>
    content = re.sub(r"</p>", "\n\n", content, flags=re.IGNORECASE)
    content = re.sub(r"<p[^>]*>", "", content, flags=re.IGNORECASE)
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.IGNORECASE)

    # Remove remaining HTML tags
    content = re.sub(r"<[^>]+>", "", content)

    # Restore iframes
    for i, iframe in enumerate(iframes):
        # Fix protocol-relative URLs (//youtube.com → https://youtube.com)
        iframe = re.sub(r'src="//([^"]+)"', r'src="https://\1"', iframe)
        # Wrap in a div for responsive styling
        responsive = (
            f'<div class="video-container">\n{iframe}\n</div>'
        )
        content = content.replace(f"IFRAME_PLACEHOLDER_{i}", responsive)

    # Decode HTML entities
    content = html.unescape(content)

    # Clean up excessive blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content.strip()


def parse_date(date_str):
    """Parse WordPress date formats."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%a, %d %b %Y %H:%M:%S +0000"):
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


def get_text(element, tag, ns_key=None):
    """Safely get text from an XML element."""
    if ns_key:
        el = element.find(f"{{{NS[ns_key]}}}{tag}")
    else:
        el = element.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return ""


def sanitize_filename(s):
    return re.sub(r"[^\w\-]", "-", s).strip("-")[:80]


def convert(xml_path, output_dir):
    print(f"Parsing {xml_path}...")
    # WordPress XML may contain undefined HTML entities — replace them before parsing
    with open(xml_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    # Inject common HTML entity definitions into the DOCTYPE
    entity_defs = """<!DOCTYPE rss [
  <!ENTITY nbsp "&#160;">
  <!ENTITY mdash "&#8212;">
  <!ENTITY ndash "&#8211;">
  <!ENTITY ldquo "&#8220;">
  <!ENTITY rdquo "&#8221;">
  <!ENTITY lsquo "&#8216;">
  <!ENTITY rsquo "&#8217;">
  <!ENTITY amp "&#38;">
  <!ENTITY lt "&#60;">
  <!ENTITY gt "&#62;">
  <!ENTITY apos "&#39;">
  <!ENTITY hellip "&#8230;">
  <!ENTITY trade "&#8482;">
  <!ENTITY reg "&#174;">
  <!ENTITY copy "&#169;">
  <!ENTITY bull "&#8226;">
  <!ENTITY eacute "&#233;">
  <!ENTITY egrave "&#232;">
  <!ENTITY agrave "&#224;">
  <!ENTITY aacute "&#225;">
  <!ENTITY auml "&#228;">
  <!ENTITY ouml "&#246;">
  <!ENTITY uuml "&#252;">
  <!ENTITY Agrave "&#192;">
  <!ENTITY Eacute "&#201;">
  <!ENTITY ccedil "&#231;">
  <!ENTITY ntilde "&#241;">
  <!ENTITY oacute "&#243;">
  <!ENTITY iacute "&#237;">
  <!ENTITY uacute "&#250;">
  <!ENTITY frac12 "&#189;">
  <!ENTITY frac14 "&#188;">
  <!ENTITY times "&#215;">
  <!ENTITY divide "&#247;">
  <!ENTITY laquo "&#171;">
  <!ENTITY raquo "&#187;">
  <!ENTITY euro "&#8364;">
  <!ENTITY pound "&#163;">
  <!ENTITY yen "&#165;">
]>"""
    # Insert DOCTYPE entity definitions after the XML declaration
    if "<!DOCTYPE" not in raw[:500]:
        # Find end of XML declaration
        xml_decl_end = raw.find("?>")
        if xml_decl_end != -1:
            raw = raw[:xml_decl_end+2] + "\n" + entity_defs + raw[xml_decl_end+2:]
        else:
            raw = entity_defs + "\n" + raw
    # Strip any remaining undefined entities as a safety net
    raw = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", raw)
    import io
    tree = ET.parse(io.StringIO(raw))
    root = tree.getroot()
    channel = root.find("channel")

    posts_dir = Path(output_dir) / "content" / "posts"
    pages_dir = Path(output_dir) / "content"
    posts_dir.mkdir(parents=True, exist_ok=True)

    items = channel.findall("item")
    post_count = 0
    page_count = 0
    skip_count = 0

    for item in items:
        post_type = get_text(item, "post_type", "wp")
        status = get_text(item, "status", "wp")

        # Only convert published posts and pages
        if status not in ("publish", "draft"):
            skip_count += 1
            continue
        if post_type not in ("post", "page"):
            skip_count += 1
            continue

        title = get_text(item, "title") or "untitled"
        slug = get_text(item, "post_name", "wp") or slugify(title)
        if not slug:
            slug = slugify(title)

        pub_date_str = get_text(item, "post_date", "wp")
        pub_date = parse_date(pub_date_str)
        date_str = pub_date.strftime("%Y-%m-%dT%H:%M:%S+00:00") if pub_date else ""

        # Get categories and tags
        categories = []
        tags = []
        for cat in item.findall("category"):
            domain = cat.get("domain", "")
            nicename = cat.get("nicename", "")
            text = cat.text or nicename
            if domain == "category":
                categories.append(text)
            elif domain == "post_tag":
                tags.append(text)

        # Get content
        content_el = item.find(f"{{{NS['content']}}}encoded")
        raw_content = content_el.text if content_el is not None and content_el.text else ""
        body = wp_content_to_markdown(raw_content)

        # Get excerpt
        excerpt_el = item.find(f"{{{NS['excerpt']}}}encoded")
        excerpt = (excerpt_el.text or "").strip() if excerpt_el is not None else ""
        excerpt = re.sub(r"<[^>]+>", "", excerpt).strip()

        # Extract first image for featured image; fall back to default
        DEFAULT_IMG = "/img/default-post.jpg"
        featured_img = DEFAULT_IMG
        img_match = re.search(r'<img[^>]*src=["\']([^"\']+)["\']', raw_content, re.IGNORECASE)
        if img_match:
            featured_img = fix_image_urls(img_match.group(1))

        # Extract agency and brand/client from raw content
        def extract_field(pattern, text):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                val = re.sub(r"<[^>]+>", "", m.group(1)).strip().strip("*").strip()
                val = html.unescape(val)
                return val[:100] if val else ""
            return ""

        # Match "Agency: Name" — stop at line end, em-dash, or asterisks
        agency = (
            extract_field(r'\*{0,2}(?:advertising )?[Aa]gency\*{0,2}\s*:\s*\*{0,2}([^—\n\r<\[*]{2,60}?)(?:\s*[—\n]|$)', raw_content)
            or "Unknown"
        )
        brand = extract_field(r'\*{0,2}(?:[Cc]lient|[Bb]rand)\*{0,2}\s*:\s*\*{0,2}([^—\n\r<\[*]{2,60}?)(?:\s*[—\n]|$)', raw_content)

        is_draft = status == "draft"

        # Build front matter (TOML)
        # TOML strings: use double quotes, escape backslashes and double quotes
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        fm_lines = [
            "+++",
            f'title = "{safe_title}"',
        ]
        if date_str:
            fm_lines.append(f'date = "{date_str}"')
        fm_lines.append(f'slug = "{slug}"')
        if is_draft:
            fm_lines.append('draft = true')
        if categories:
            cats_str = ", ".join(f'"{c}"' for c in categories)
            fm_lines.append(f"categories = [{cats_str}]")
        if tags:
            tags_str = ", ".join(f'"{t}"' for t in tags)
            fm_lines.append(f"tags = [{tags_str}]")
        if excerpt:
            safe_excerpt = excerpt.replace('"', '\\"')[:200]
            fm_lines.append(f'description = "{safe_excerpt}"')
        safe_agency = agency.replace("\\", "\\\\").replace('"', '\\"')
        safe_brand = brand.replace("\\", "\\\\").replace('"', '\\"') if brand else ""
        fm_lines.append(f'agency = "{safe_agency}"')
        if safe_brand:
            fm_lines.append(f'brand = "{safe_brand}"')
        fm_lines.append(f'[cover]')
        fm_lines.append(f'  image = "{featured_img}"')
        fm_lines.append("+++")

        front_matter = "\n".join(fm_lines)
        md_content = front_matter + "\n\n" + body

        # Write file
        safe_slug = sanitize_filename(slug) or sanitize_filename(title)
        if post_type == "post":
            out_path = posts_dir / f"{safe_slug}.md"
            post_count += 1
        else:
            # Pages go to content root
            out_path = pages_dir / f"{safe_slug}.md"
            page_count += 1

        out_path.write_text(md_content, encoding="utf-8")

    print(f"Done: {post_count} posts, {page_count} pages, {skip_count} skipped")


if __name__ == "__main__":
    xml_file = "/Users/aanwar1982/Downloads/ITA Redesign/insidethatad.WordPress.2026-06-18.xml"
    site_dir = "/Users/aanwar1982/Sites/insidethatad"
    convert(xml_file, site_dir)
