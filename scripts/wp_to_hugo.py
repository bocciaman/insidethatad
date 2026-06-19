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


def build_attachment_map(items):
    """Pass 1: build {attachment_id: url} from wp:post_type=attachment items."""
    att_map = {}
    for item in items:
        post_type = get_text(item, "post_type", "wp")
        if post_type != "attachment":
            continue
        att_id = get_text(item, "post_id", "wp")
        att_url_el = item.find(f"{{{NS['wp']}}}attachment_url")
        if att_id and att_url_el is not None and att_url_el.text:
            att_map[att_id] = att_url_el.text.strip()
    return att_map


def get_thumbnail_id(item):
    """Return the _thumbnail_id postmeta value for a post item, or None."""
    for pm in item.findall(f"{{{NS['wp']}}}postmeta"):
        key_el = pm.find(f"{{{NS['wp']}}}meta_key")
        val_el = pm.find(f"{{{NS['wp']}}}meta_value")
        if key_el is not None and key_el.text == "_thumbnail_id":
            return val_el.text.strip() if val_el is not None and val_el.text else None
    return None


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

    # Pass 1: build attachment ID → URL map
    attachment_map = build_attachment_map(items)
    print(f"Found {len(attachment_map)} attachments")

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

        # Extract featured image: prefer WordPress _thumbnail_id → attachment URL
        DEFAULT_IMG = "/img/default-post.jpg"
        featured_img = DEFAULT_IMG
        thumb_id = get_thumbnail_id(item)
        if thumb_id and thumb_id in attachment_map:
            featured_img = fix_image_urls(attachment_map[thumb_id])
        else:
            # Fall back to first inline image in post content
            img_match = re.search(r'<img[^>]*src=["\']([^"\']+)["\']', raw_content, re.IGNORECASE)
            if img_match:
                featured_img = fix_image_urls(img_match.group(1))

        # Strip HTML once for text-based extraction (so linked names like
        # <a href="...">Giuliano Garonzi</a> are readable by the patterns)
        plain_content = re.sub(r"<[^>]+>", " ", raw_content)
        plain_content = html.unescape(plain_content)
        plain_content = re.sub(r"\s{2,}", " ", plain_content)

        def extract_field(pattern, text):
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip().strip("*").strip()
                return val[:100] if val else ""
            return ""

        # Extract agency — run against plain text so hyperlinked names are visible
        # STOP: stop before line breaks, em-dash, or a new "Word:" credit label
        STOP = r'[^—\n\r\[*]{2,80}?'
        CREDIT_STOP = r'(?=\s*(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s*:|—|$|\n))'
        agency_patterns = [
            # "Advertising Agency: Name" or "Agency: Name" explicit label
            rf'(?:advertising\s+)?[Aa]gency\s*:\s*({STOP}){CREDIT_STOP}',
            # "Ad Agency:" prefix
            rf'[Aa]d\s+[Aa]gency\s*:\s*({STOP}){CREDIT_STOP}',
            # "comes to us courtesy of Agency" / "spot courtesy of Agency"
            rf'(?:comes?\s+to\s+us|spot|ad|commercial|campaign)\s+(?:is\s+)?courtesy\s+of\s+([A-Z][A-Za-z0-9&/\+\s\,\.\-]{3,55}?)(?:\.|,\s+[a-z]|\s+and\s+|\s*$)',
            # "created by / produced by / made by Agency for Brand"
            rf'(?:created|produced|made)\s+by\s+([A-Z][A-Za-z0-9&/\+\s\,\.\-]{3,50}?)\s+for\s+[A-Z]',
            # "from Agency, the creative team" / "from Agency."
            rf'from\s+([A-Z][A-Za-z0-9&/\+\s\-]{3,50}?)\s*[,\.]',
            # "appointed X as [its/new] agency/AOR"
            rf"appointed\s+([A-Z][A-Za-z0-9&\+\s\-]{{3,50}}?)\s+as\s+(?:its\s+)?(?:new\s+)?(?:advertising\s+)?(?:agency|AOR)",
            # Well-known agency names anywhere in the article
            r'(Wieden\s*\+\s*Kennedy|Commonwealth/McCann|TBWA|DDB\b|BBDO\b|McCann\s+\w+|Ogilvy(?:\s+\w+)?|Saatchi\s*&\s*Saatchi|Leo\s+Burnett|JWT\b|Grey\s+Global|FCB\b|R/GA|72andSunny|Droga5|CP\+B|Crispin\s+Porter|Arnold\s+Worldwide|Deutsch\b|Goodby\s+Silverstein|Young\s*&\s*Rubicam|Havas\s+\w+|Publicis\s+\w+|Anomaly\b|Innocean\b)',
        ]
        agency = "Unknown"
        for pat in agency_patterns:
            val = extract_field(pat, plain_content)
            if val and len(val) > 2:
                val = val.split('\n')[0].split('\r')[0]
                # Cut off at navigation words that signal prose ran on
                val = re.split(r'\s+(?:Read\s+more|Best,\s+-|Speak\s+on|E-Trade)', val, flags=re.IGNORECASE)[0]
                # Strip trailing article words: "The", "A", "An", "This" etc.
                val = re.sub(r'\s+(?:The|A|An|This|That|In|On|At|By|Is|Was|For|And)\s*$', '', val, flags=re.IGNORECASE)
                val = re.sub(r'[\.,\s]+$', '', val).strip()
                # Skip clear false positives
                if re.search(r'\b(came|said|told|which|that|this|with|from|their|have|been|also|were|when|Here\s+it|obviously|Unknown)\b', val, re.IGNORECASE):
                    continue
                if len(val) > 60:  # still too long — likely noise
                    continue
                agency = val
                break

        # Extract brand from the post title — three patterns in priority order:
        # 1. "Title | Brand"  e.g. "A Holiday to Remember | Chevrolet"
        # 2. "Brand: Title"   e.g. "Nike: XI Men"
        # 3. "Brand's ..."    e.g. "Nissan's Groundbreaking Ad"
        # 4. Explicit "Client: X" / "Brand: X" label in body text
        brand = ""
        pipe_match = re.search(r'\|\s*(.+?)\s*$', title)
        colon_match = re.match(r'^([^:]{2,40}):\s+\S', title)
        possessive_match = re.match(r'^([A-Z][A-Za-z0-9\s]{1,30}?)\'s\s', title)
        if pipe_match:
            brand = pipe_match.group(1).strip()
        elif colon_match:
            brand = colon_match.group(1).strip()
        elif possessive_match:
            brand = possessive_match.group(1).strip()
        else:
            brand = extract_field(r'(?:[Cc]lient|[Bb]rand)\s*:\s*([^—\n\r\[*]{2,60}?)(?=\s*(?:[A-Z][a-z]+\s*:|$|\n))', plain_content)
        # Pattern 4: "BrandName Ad/Commercial/Campaign/Spot ..."
        # e.g. "Google Pixel Ad On NBA Court" → "Google Pixel"
        if not brand:
            ad_words = r'(?:Ad|Ads|Commercial|Campaign|Spot|Spots|Video|Film|Print)\b'
            m = re.match(rf'^([A-Z][A-Za-z0-9](?:[A-Za-z0-9\s&\+]{{0,30}}?))\s+{ad_words}', title)
            if m:
                brand = m.group(1).strip()
        # Sanity check — skip if too long or looks like a sentence fragment
        if brand and (len(brand) > 50 or re.search(r'\b(the|a|an|and|or|but|to|of|in|on)\b', brand, re.IGNORECASE)):
            brand = ""

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
