import json
import os
import re
from datetime import datetime

INPUT_JSON = "wireframes.enriched.json"
OUTPUT_DIR = "rendered_wireframes"
SHOW_SEMANTIC_OVERLAY = True

CANVAS_W = 1200
CANVAS_H = 1850

MARGIN = 36
GUTTER = 18

HEADER_H = 70
SECTION_GAP = 18
SECTION_PAD = 18

NEWSLETTER_BAND_H = 220
FOOTER_DARK_H = 140

COMP_H = 34
COMP_GAP = 10

# Header layout
LOGO_W = 120
LOGO_H = 44
HEADER_CTA_W = 130
HEADER_CTA_H = 34
NAV_GAP = 22
NAV_RIGHT_GAP = 18


# -------------------------
# Utilities
# -------------------------
def safe_filename(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "page"


def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


def approx_text_width(label: str, px_per_char: float = 7.0) -> int:
    return int(len(label or "") * px_per_char)


def canon(s: str) -> str:
    return (s or "").strip().lower().replace("_", "-").replace(" ", "-")


def find_components(sec: dict, *types_: str):
    wanted = {canon(t) for t in types_}
    out = []
    for c in (sec.get("components") or []):
        if canon(c.get("type")) in wanted:
            out.append(c)
    return out


def first_text_like(sec: dict):
    for c in (sec.get("components") or []):
        if canon(c.get("type")) == "text":
            return c
    return None


def first_button(sec: dict):
    for c in (sec.get("components") or []):
        if canon(c.get("type")) == "button":
            return c
    return None


def list_items_from_component(c: dict):
    # allow both `items` and `fields` lists
    items = c.get("items")
    if isinstance(items, list) and items:
        return [str(x) for x in items if str(x).strip()]
    fields = c.get("fields")
    if isinstance(fields, list) and fields:
        return [str(x) for x in fields if str(x).strip()]
    return []


def best_text_for_component(c: dict, fallback: str):
    # prefer placeholder, then label
    ph = (c.get("placeholder") or "").strip()
    if ph:
        return ph
    lab = (c.get("label") or "").strip()
    if lab:
        return lab
    return fallback


# -------------------------
# SVG helpers
# -------------------------
def css_block() -> str:
    return """
    <style>
      .page-bg { fill: #f6f6f6; }
      .page-frame { fill: #ffffff; stroke: #2b2b2b; stroke-width: 2.2; rx: 16; ry: 16; }

      .sketch {
        stroke: #2b2b2b;
        stroke-width: 2.2;
        stroke-linecap: round;
        stroke-linejoin: round;
        fill: #ffffff;
      }

      .sketch-dash {
        stroke: #2b2b2b;
        stroke-width: 2.2;
        stroke-linecap: round;
        stroke-linejoin: round;
        fill: #ffffff;
        stroke-dasharray: 7 6;
      }

      .panel-light {
        fill: #e9e9e9;
        stroke: #2b2b2b;
        stroke-width: 2.2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .panel-dark {
        fill: #6f6f6f;
        stroke: #2b2b2b;
        stroke-width: 2.2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .text {
        font-family: "Balsamiq Sans", "Comic Sans MS", "Segoe UI", Arial, sans-serif;
        fill: #222;
      }

      .meta { font-size: 15px; font-weight: 700; }
      .small { font-size: 12px; font-weight: 400; opacity: 0.9; }
      .overlay { font-size: 11px; font-weight: 600; opacity: 0.75; }


      /* Header/body links */
      .nav-link {
        font-size: 13px;
        fill: #1a73e8;
        text-decoration: underline;
        font-weight: 600;
      }

      /* Footer links (white for legibility) */
      .footer-link {
        font-size: 13px;
        fill: #ffffff;
        text-decoration: underline;
        font-weight: 600;
      }

      .h1 { font-size: 34px; font-weight: 800; }
      .h2 { font-size: 18px; font-weight: 800; }
      .h3 { font-size: 13px; font-weight: 800; }
      .muted { opacity: 0.8; }

      .button {
        fill: #efefef;
        stroke: #2b2b2b;
        stroke-width: 2.2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .button-dark {
        fill: #3e3e3e;
        stroke: #2b2b2b;
        stroke-width: 2.2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .button-text { font-size: 12px; font-weight: 700; fill: #222; }
      .button-text-inv { font-size: 12px; font-weight: 700; fill: #ffffff; }

      .imgph {
        fill: #e9e9e9;              /* light grey hero background */
        stroke: #2b2b2b;
        stroke-width: 2.2;
        stroke-linecap: round;
        stroke-linejoin: round;
      }

      .imgx {
        stroke: #2b2b2b;
        stroke-width: 1.6;          /* slightly lighter stroke */
        stroke-linecap: round;
        stroke-linejoin: round;
        opacity: 0.18;              /* faint X behind text */
      }

        .vdiv {
                stroke: #c9c9c9;
                stroke-width: 2.0;
                stroke-linecap: round;
                opacity: 0.9;
              }


    </style>
    """


def rect(x, y, w, h, cls="sketch", rx=12):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" class="{cls}" />'


def text(x, y, t, extra_cls="", anchor=None):
    tt = escape_xml(t)
    anchor_attr = f' text-anchor="{anchor}"' if anchor else ""
    classes = f"text {extra_cls}".strip()
    return f'<text x="{x}" y="{y}" class="{classes}"{anchor_attr}>{tt}</text>'


def line(x1, y1, x2, y2, cls="imgx"):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="{cls}" />'


def button(x, y, w, h, label, dark=False):
    cls = "button-dark" if dark else "button"
    tcls = "button-text-inv" if dark else "button-text"
    tx = x + (w / 2)
    ty = y + (h / 2) + 4
    return "\n".join([
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" ry="10" class="{cls}" />',
        f'<text x="{tx}" y="{ty}" text-anchor="middle" class="text {tcls}">{escape_xml(label)}</text>'
    ])


# -------------------------
# Nav for header
# -------------------------
_NAV_CACHE = None

def nav_from_page_labels(page_obj: dict):
    """
    Nav should reflect the current run's sitemap.json primary_nav.
    Fallbacks:
      1) INPUT_JSON pages list
      2) original hard-coded default
    """
    global _NAV_CACHE
    if _NAV_CACHE is not None:
        return _NAV_CACHE

    # 1) Best source: sitemap.json (created by main.py in the run folder)
    try:
        with open("sitemap.json", "r", encoding="utf-8") as f:
            sm = json.load(f)
        nav = sm.get("primary_nav")
        if isinstance(nav, list) and nav:
            _NAV_CACHE = [str(x) for x in nav if str(x).strip()]
            if _NAV_CACHE:
                return _NAV_CACHE
    except Exception:
        pass

    # 2) Fallback: derive from wireframes.json pages list
    try:
        with open(INPUT_JSON, "r", encoding="utf-8") as f:
            wf = json.load(f)
        pages = wf.get("pages", [])
        labels = [p.get("page") for p in pages if isinstance(p, dict) and p.get("page")]
        if labels:
            _NAV_CACHE = labels
            return _NAV_CACHE
    except Exception:
        pass

    # 3) Final fallback (your original default)
    _NAV_CACHE = ["Home", "About", "Objectives", "Resources", "Advocacy", "Contact"]
    return _NAV_CACHE



# -------------------------
# Dynamic section sizing based on JSON content
# -------------------------
def _inner_bottom_for_section(st: str, sec: dict, inner_y: int, inner_x: int, inner_w: int) -> int:
    st = canon(st)

    if st == "hero":
            img_h = 240
            b = inner_y + img_h
            # keep enough room for headline + subtitle + button + caption
            b = max(b, inner_y + 240)
            return b + 14

    if st == "features":
        # number of cards = 3 by default, or derived from cards/items/h3
        cards_count = 3
        cards = find_components(sec, "cards")
        if cards:
            items = list_items_from_component(cards[0])
            if items:
                cards_count = max(3, min(6, len(items)))
        else:
            h3 = sec.get("h3") or []
            if isinstance(h3, list) and h3:
                cards_count = max(3, min(6, len(h3)))
        # We still render 3 across, but height stays 140.
        return inner_y + 140 + 14

    if st == "content":
        divider_y = inner_y + 120
        heading_y = divider_y + 48

        bullet_rows = 4
        lists = find_components(sec, "list")
        if lists:
            items = list_items_from_component(lists[0])
            if items:
                bullet_rows = max(4, min(12, len(items)))

        bullets_start_y = heading_y + 32
        bullets_end_y = bullets_start_y + (bullet_rows * 22)

        # paragraph blocks: count how many text components
        text_count = len(find_components(sec, "text"))
        # allow extra vertical space if multiple paragraphs
        para_extra = max(0, (text_count - 1)) * 22

        bottom = max(bullets_end_y, inner_y + 96 + para_extra)
        return bottom + 18

    if st == "faq":
        # number of accordions derived from accordion/items
        faq_items = 4
        acc = find_components(sec, "accordion")
        if acc:
            items = list_items_from_component(acc[0])
            if items:
                faq_items = max(4, min(10, len(items)))
        return inner_y + (faq_items * 44) + 10

    if st == "proof":
        # quote or stats: allocate enough room
        if find_components(sec, "quote"):
            return inner_y + 90 + 14
        if find_components(sec, "stats"):
            return inner_y + 110 + 14
        return inner_y + 90 + 14

    if st == "steps":
        # steps count from list/items
        steps = 3
        lst = find_components(sec, "list")
        if lst:
            items = list_items_from_component(lst[0])
            if items:
                steps = max(3, min(8, len(items)))
        return inner_y + (steps * 36) + 18

    if st == "form":
        # show up to 4 fields + submit row
        fields_count = 3
        ff = find_components(sec, "form-field", "form_field", "field", "input", "textarea", "select", "checkbox", "radio")
        if ff:
            fields_count = max(3, min(6, len(ff)))
        return inner_y + 70 + (fields_count * 36) + 18

    if st in ("cta", "footer-cta", "footer_cta", "cta-section", "call-to-action"):
        return inner_y + 90 + 34 + 18

    # generic
    comps = sec.get("components", []) or []
    rows = min(6, len(comps)) if comps else 3
    return inner_y + rows * (COMP_H + COMP_GAP) + 18


def section_height_for(sec: dict) -> int:
    st = canon(sec.get("type"))
    header_block = 72
    inner_bottom = _inner_bottom_for_section(st, sec, 0, SECTION_PAD, 1000)

    min_total = {
        "hero": 360,
        "features": 260,
        "content": 280,
        "proof": 210,
        "steps": 240,
        "faq": 220,
        "cta": 160,
        "call-to-action": 160,
        "form": 240,
        "gallery": 240,
        "footer_cta": 160,
        "footer-cta": 160,
        "section": 220,
    }.get(st, 220)

    return int(max(min_total, header_block + inner_bottom + 8))


# -------------------------
# Section rendering (now uses JSON)
# -------------------------
def draw_section(svg, x, y, w, sec: dict, idx: int):
    st = canon(sec.get("type"))
    sec_id = sec.get("id", f"section-{idx+1}")
    label = truncate(sec.get("label", st or "Section"), 60)
    h2 = truncate(sec.get("h2", ""), 80) or label
    h3 = sec.get("h3") or []
    if not isinstance(h3, list):
        h3 = []

    h = section_height_for(sec)
    svg.append(rect(x, y, w, h, cls="sketch", rx=14))

    svg.append(text(x + 16, y + 28, h2, extra_cls="h2"))
    if SHOW_SEMANTIC_OVERLAY:
        sem = sec.get("semantic", {})
        intent = sem.get("intent", "")
        facts = sem.get("supporting_facts", [])
        intent_short = (intent or "")[:60] + ("…" if intent and len(intent) > 60 else "")
        overlay = f"intent: {intent_short} • facts: {len(facts)}"

        svg.append(text(
            x + 16,
            y + 44,
            overlay,
            extra_cls="overlay"
        ))

    svg.append(text(x + 16, y + 60, f"{st} • id: {sec_id}", extra_cls="small muted"))


    inner_x = x + SECTION_PAD
    inner_y = y + 72
    inner_w = w - (2 * SECTION_PAD)

    if st == "hero":
        # Slightly taller hero so text + CTA can breathe
        img_h = 280

        # Light grey background + faint X behind all text
        svg.append(rect(inner_x, inner_y, inner_w, img_h, cls="imgph", rx=10))
        svg.append(line(inner_x + 10, inner_y + 10, inner_x + inner_w - 10, inner_y + img_h - 10, cls="imgx"))
        svg.append(line(inner_x + inner_w - 10, inner_y + 10, inner_x + 10, inner_y + img_h - 10, cls="imgx"))

        # Title
        headline = truncate(h2, 44)
        title_y = inner_y + 118
        svg.append(text(x + w/2, title_y, headline, extra_cls="h1", anchor="middle"))

        # Subtitle: ONE short, powerful sentence (single line only)
        subtitle = ""
        if h3:
            if isinstance(h3, list) and h3:
                subtitle = str(h3[0])
            else:
                subtitle = str(h3)
        subtitle = " ".join((subtitle or "").split())
        subtitle = truncate(subtitle, 78)

        subtitle_y = title_y + 28
        if subtitle:
            svg.append(text(x + w/2, subtitle_y, subtitle, extra_cls="small muted", anchor="middle"))

        # Button: dynamic width based on label text (consistent left/right padding)
        btn = first_button(sec)
        btn_label = best_text_for_component(btn, "Learn More") if btn else "Learn More"
        btn_label = " ".join(str(btn_label or "").split())
        btn_label = truncate(btn_label, 28)

        # Approximate text width; keep within sane limits
        btn_w = max(120, min(300, 46 + (len(btn_label) * 9)))
        btn_h = 34
        btn_x = x + (w/2) - (btn_w/2)

        # Spacing rules: consistent breathing room from title/subtitle
        content_bottom_y = subtitle_y if subtitle else title_y
        btn_y = content_bottom_y + 26

        svg.append(button(btn_x, btn_y, btn_w, btn_h, btn_label, dark=False))

        # Caption sits below button, still inside hero area (consistent spacing)
        cap = first_text_like(sec)
        cap_text = best_text_for_component(cap, "Caption size text here with a link") if cap else "Caption size text here with a link"
        cap_text = " ".join(str(cap_text or "").split())
        cap_text = truncate(cap_text, 78)

        cap_y = btn_y + btn_h + 18
        svg.append(text(x + (w/2), cap_y, cap_text, extra_cls="small nav-link", anchor="middle"))

        return y + h + SECTION_GAP

    if st == "features":
        # 3 cards across (Balsamiq-ish), content from:
        # - cards.items OR h3 lines OR fallback labels
        card_gap = 16
        card_w = (inner_w - (2 * card_gap)) / 3
        card_h = 140

        card_titles = []
        cards = find_components(sec, "cards")
        if cards:
            items = list_items_from_component(cards[0])
            if items:
                card_titles = items[:3]

        if not card_titles and h3:
            card_titles = h3[:3]

        while len(card_titles) < 3:
            card_titles.append(f"{label} {len(card_titles)+1}")

        # Card body text sourced from first text placeholder if present
        t = first_text_like(sec)
        body = truncate(best_text_for_component(t, "Lorem ipsum dolor sit amet,") if t else "Lorem ipsum dolor sit amet,", 44)

        # Button label from first button if present
        b = first_button(sec)
        btn_label = truncate(best_text_for_component(b, "Learn More") if b else "Learn More", 18)

        for i in range(3):
            cx = inner_x + i * (card_w + card_gap)
            svg.append(rect(cx, inner_y, card_w, card_h, cls="sketch", rx=12))
            svg.append(text(cx + 12, inner_y + 28, truncate(card_titles[i], 20).upper(), extra_cls="small"))
            svg.append(text(cx + 12, inner_y + 54, body, extra_cls="small muted"))
            svg.append(button(cx + 12, inner_y + 92, 110, 30, btn_label, dark=False))
        return y + h + SECTION_GAP

    if st == "content":
        # Render:
        # Left: up to 3 list items (if list exists), else section label lines
        # Right: subtitle from first h3 OR label, then up to 3 text placeholders
        left_w = int(inner_w * 0.28)
        rx = inner_x + left_w + 18

        lists = find_components(sec, "list")
        left_lines = []
        if lists:
            items = list_items_from_component(lists[0])
            left_lines = items[:3]
        if not left_lines:
            left_lines = [f"{label} item {i}" for i in range(1, 4)]

        line0 = left_lines[0] if len(left_lines) > 0 else ""
        line1 = left_lines[1] if len(left_lines) > 1 else ""
        line2 = left_lines[2] if len(left_lines) > 2 else ""
        
        svg.append(text(inner_x + 6, inner_y + 22, truncate(line0, 22), extra_cls="small"))
        svg.append(text(inner_x + 6, inner_y + 40, truncate(line1, 22), extra_cls="small"))
        svg.append(text(inner_x + 6, inner_y + 58, truncate(line2, 22), extra_cls="small"))

        subtitle = truncate(h3[0], 60) if h3 else truncate(label, 60)
        svg.append(text(rx, inner_y + 24, subtitle.upper(), extra_cls="h2"))

        # right paragraph lines from text components
        texts = find_components(sec, "text")
        para_lines = []
        for c in texts[:3]:
            para_lines.append(truncate(best_text_for_component(c, "Lorem ipsum dolor sit amet."), 52))
        while len(para_lines) < 3:
            para_lines.append("Lorem ipsum dolor sit amet, consectetur")

        svg.append(text(rx, inner_y + 52, para_lines[0], extra_cls="small muted"))
        svg.append(text(rx, inner_y + 70, para_lines[1], extra_cls="small muted"))
        svg.append(text(rx, inner_y + 88, para_lines[2], extra_cls="small muted"))

        divider_y = inner_y + 120
        svg.append(line(inner_x + 10, divider_y, inner_x + inner_w - 10, divider_y, cls="imgx"))

        heading_y = divider_y + 48
        svg.append(text(inner_x + 6, heading_y, truncate((sec.get("label") or "CONTENT").upper(), 36), extra_cls="h2"))

        # bullet items
        # bullet items (layout logic)
        bullet_items_raw = []
        if lists:
            bullet_items_raw = list_items_from_component(lists[0]) or []

        # Threshold: need at least 8 bullets to justify a true 2-column list (4 + 4)
        use_two_cols = len(bullet_items_raw) >= 8

        col_y = heading_y + 32
        row_h = 22
        col_gap = 26

        if use_two_cols:
            # Two columns, split unique items across columns (no image placeholder)
            items = bullet_items_raw[:12]  # cap for wireframe density
            left_n = (len(items) + 1) // 2
            left_col = items[:left_n]
            right_col = items[left_n:]

            # ensure a minimum visual height
            rows = max(4, max(len(left_col), len(right_col)))

            while len(left_col) < rows:
                left_col.append("Additional point...")
            while len(right_col) < rows:
                right_col.append("Additional point...")

            col_w = (inner_w - col_gap) / 2

            # --- vertical divider (between the two bullet columns) ---
            split_x = inner_x + col_w + (col_gap / 2)
            divider_top = col_y - 6
            divider_bottom = col_y + (rows * row_h) + 6
            svg.append(line(split_x, divider_top, split_x, divider_bottom, cls="imgx"))

            for col, col_items in enumerate([left_col, right_col]):
                bx = inner_x + col * (col_w + col_gap)
                for i in range(rows):
                    svg.append(text(bx + 6, col_y + i * row_h, "• " + truncate(col_items[i], 34), extra_cls="small"))

        else:
            # One column list on the left + image placeholder on the right
            items = bullet_items_raw[:10]

            rows = max(4, len(items))
            while len(items) < rows:
                items.append("Additional point...")

            # Allocate space: list left, image right (balanced)
            list_w = int(inner_w * 0.55)
            img_x = inner_x + list_w + col_gap
            img_w = inner_w - list_w - col_gap

            # --- vertical divider (between list and image column) ---
            split_x = inner_x + list_w + (col_gap / 2)
            divider_top = col_y - 6
            # define the full content height we consider for vertical alignment
            content_h = (rows * row_h) + 18
            divider_bottom = col_y + content_h + 6
            svg.append(line(split_x, divider_top, split_x, divider_bottom, cls="imgx"))

            # Render single list
            for i in range(rows):
                svg.append(text(inner_x + 6, col_y + i * row_h, "• " + truncate(items[i], 52), extra_cls="small"))

            # Render sized image placeholder (CENTERED in its column: horizontally + vertically)
            img_h = min(240, content_h)

            # Center horizontally in right column
            ph_w = int(img_w * 0.86)
            ph_h = int(img_h * 0.82)

            ph_x = img_x + (img_w - ph_w) / 2
            ph_y = col_y + (content_h - ph_h) / 2

            svg.append(rect(ph_x, ph_y, ph_w, ph_h, cls="sketch-dash", rx=12))
            svg.append(line(ph_x + 10, ph_y + 10, ph_x + ph_w - 10, ph_y + ph_h - 10, cls="imgx"))
            svg.append(line(ph_x + ph_w - 10, ph_y + 10, ph_x + 10, ph_y + ph_h - 10, cls="imgx"))
            svg.append(text(ph_x + 14, ph_y + 24, "IMAGE", extra_cls="small muted"))

        return y + h + SECTION_GAP

    if st == "steps":
        # Render a vertical step list from list items
        lst = find_components(sec, "list")
        items = []
        if lst:
            items = list_items_from_component(lst[0])
        if not items:
            items = [f"Step {i}" for i in range(1, 4)]

        yy = inner_y
        for i, it in enumerate(items[:8], start=1):
            svg.append(rect(inner_x, yy, inner_w, 30, cls="sketch-dash", rx=10))
            svg.append(text(inner_x + 14, yy + 20, f"{i}. {truncate(it, 90)}", extra_cls="small"))
            yy += 36
        return y + h + SECTION_GAP

    if st == "proof":
        # Prefer stats, else quote, else generic dashed box
        if find_components(sec, "stats"):
            svg.append(rect(inner_x, inner_y, inner_w, 90, cls="sketch-dash", rx=12))
            svg.append(text(inner_x + 14, inner_y + 24, "Impact Statistics", extra_cls="small"))
            svg.append(text(inner_x + 14, inner_y + 48, truncate(best_text_for_component(find_components(sec, "stats")[0], "[CONFIRM impact statistics]"), 90), extra_cls="small muted"))
        elif find_components(sec, "quote"):
            svg.append(rect(inner_x, inner_y, inner_w, 70, cls="sketch-dash", rx=12))
            svg.append(text(inner_x + 14, inner_y + 28, truncate(best_text_for_component(find_components(sec, "quote")[0], "Expert quote or testimonial"), 90), extra_cls="small"))
        else:
            svg.append(rect(inner_x, inner_y, inner_w, 70, cls="sketch-dash", rx=12))
            svg.append(text(inner_x + 14, inner_y + 28, "Proof / Testimonial / Stats", extra_cls="small"))
        return y + h + SECTION_GAP

    if st == "faq":
        # Use accordion items if present
        items = []
        acc = find_components(sec, "accordion")
        if acc:
            items = list_items_from_component(acc[0])

        if not items:
            items = [f"FAQ item {i}" for i in range(1, 5)]

        yy = inner_y
        for it in items[:10]:
            svg.append(rect(inner_x, yy, inner_w, 34, cls="sketch-dash", rx=10))
            svg.append(text(inner_x + 14, yy + 22, truncate(it, 100), extra_cls="small"))
            yy += 44
        return y + h + SECTION_GAP

    if st == "form":
        # Render fields from explicit form-field components if present
        fields = []
        ff = find_components(sec, "form-field", "form_field", "field", "input", "textarea", "select", "checkbox", "radio")
        if ff:
            for c in ff[:6]:
                fields.append(truncate(best_text_for_component(c, c.get("label", "Field")), 40))

        if not fields:
            # fallback
            fields = ["Name", "Email", "Message"]

        # Title/subtitle from section headings
        svg.append(text(inner_x + inner_w/2, inner_y + 26, truncate(h2, 48), extra_cls="h2", anchor="middle"))
        sub = truncate(h3[0], 80) if h3 else "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
        svg.append(text(inner_x + inner_w/2, inner_y + 70, sub, extra_cls="small muted", anchor="middle"))

        yy = inner_y + 70
        for f in fields[:5]:
            svg.append(rect(inner_x, yy, inner_w, 30, cls="sketch", rx=8))
            svg.append(text(inner_x + 12, yy + 20, f, extra_cls="small muted"))
            yy += 36

        b = first_button(sec)
        btn_label = truncate(best_text_for_component(b, "Send Message") if b else "Send Message", 20)
        svg.append(button(inner_x + inner_w - 150, yy + 4, 150, 34, btn_label, dark=True))
        return y + h + SECTION_GAP

    if st in ("cta", "call-to-action", "cta-section", "footer-cta", "footer_cta", "footer-call-to-action", "footer_call_to_action"):
        title = truncate(h2, 50)
        sub = truncate(h3[0], 90) if h3 else "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
        svg.append(text(inner_x + inner_w/2, inner_y + 34, title, extra_cls="h2", anchor="middle"))
        svg.append(text(inner_x + inner_w/2, inner_y + 60, sub, extra_cls="small muted", anchor="middle"))

        b = first_button(sec)
        btn_label = truncate(best_text_for_component(b, "Take Action") if b else "Take Action", 20)
        svg.append(button(inner_x + (inner_w/2) - 70, inner_y + 90, 140, 34, btn_label, dark=False))
        return y + h + SECTION_GAP

    # fallback generic components: show component labels/placeholders as dashed rows
    comps = sec.get("components", []) or []
    cy = inner_y

    if not comps:
        comps = [{"type": "text", "label": "Placeholder content", "placeholder": ""}] * 3

    for comp in comps[:6]:
        svg.append(rect(inner_x, cy, inner_w, COMP_H, cls="sketch-dash", rx=10))
        lab = best_text_for_component(comp, "Component")
        svg.append(text(inner_x + 14, cy + 22, truncate(lab, 95), extra_cls="small"))
        cy += COMP_H + COMP_GAP

    return y + h + SECTION_GAP


# -------------------------
# Render one page
# -------------------------
def render_page_svg(page_obj: dict) -> str:
    page_name = page_obj.get("page", "Page")
    slug = page_obj.get("slug", "/")
    layout = page_obj.get("layout", {})
    h1 = layout.get("h1", "").strip() or page_name
    sections = layout.get("sections", []) or []

    svg = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">')
    svg.append(css_block())
    svg.append(f'<rect x="0" y="0" width="{CANVAS_W}" height="{CANVAS_H}" class="page-bg" />')

    frame_x = MARGIN
    frame_y = MARGIN
    frame_w = CANVAS_W - (2 * MARGIN)
    frame_h = CANVAS_H - (2 * MARGIN)

    svg.append(f'<rect x="{frame_x}" y="{frame_y}" width="{frame_w}" height="{frame_h}" class="page-frame" />')
    svg.append(text(frame_x, frame_y - 10, f"{page_name} ({slug})", extra_cls="meta"))

    hx = frame_x + GUTTER
    hy = frame_y + GUTTER
    hw = frame_w - (2 * GUTTER)

    # Header logo
    svg.append(rect(hx, hy, LOGO_W, LOGO_H, cls="sketch", rx=10))
    svg.append(line(hx + 8, hy + 8, hx + LOGO_W - 8, hy + LOGO_H - 8))
    svg.append(line(hx + LOGO_W - 8, hy + 8, hx + 8, hy + LOGO_H - 8))
    svg.append(text(hx + 18, hy + 28, "Logo Here", extra_cls="small"))

    # Header CTA
    cta_x = hx + hw - HEADER_CTA_W
    cta_y = hy + 6
    svg.append(button(cta_x, cta_y, HEADER_CTA_W, HEADER_CTA_H, "Take Action", dark=False))

    # Header nav (right-aligned cluster)
    nav_items = nav_from_page_labels(page_obj)
    nav_right_edge = cta_x - NAV_RIGHT_GAP
    nav_y = hy + 28
    cursor = nav_right_edge
    for item in reversed(nav_items):
        w_est = approx_text_width(item)
        x = cursor - w_est
        if x < (hx + LOGO_W + 22):
            break
        svg.append(text(x, nav_y, item, extra_cls="nav-link"))
        cursor = x - NAV_GAP

    # Layout area
    content_x = frame_x + GUTTER
    content_w = frame_w - (2 * GUTTER)
    cursor_y = hy + HEADER_H + 8

    # Footer stack positions first (prevents collisions)
    footer_y = frame_y + frame_h - FOOTER_DARK_H - GUTTER
    band_y = footer_y - NEWSLETTER_BAND_H - GUTTER
    content_bottom_limit = band_y - SECTION_GAP

    # Ensure a hero exists
    if sections and canon(sections[0].get("type")) == "hero":
        cursor_y = draw_section(svg, content_x, cursor_y, content_w, sections[0], 0)
        start_idx = 1
    else:
        hero_sec = {"id": "auto-hero", "type": "hero", "label": "Hero", "h2": h1, "components": []}
        cursor_y = draw_section(svg, content_x, cursor_y, content_w, hero_sec, 0)
        start_idx = 0

    idx = start_idx
    while idx < len(sections):
        next_h = section_height_for(sections[idx])
        if cursor_y + next_h > content_bottom_limit:
            break
        cursor_y = draw_section(svg, content_x, cursor_y, content_w, sections[idx], idx)
        idx += 1

    if idx < len(sections):
        svg.append(text(content_x, cursor_y + 18, "… (more sections not shown)", extra_cls="small"))

    # Newsletter band (still fixed element)
    svg.append(f'<rect x="{content_x}" y="{band_y}" width="{content_w}" height="{NEWSLETTER_BAND_H}" rx="14" ry="14" class="panel-light" />')
    svg.append(text(content_x + content_w/2, band_y + 70, "Newsletter Sign Up", extra_cls="h1", anchor="middle"))
    svg.append(text(content_x + content_w/2, band_y + 98, "Lorem ipsum dolor sit amet, consectetur adipiscing elit.", extra_cls="small muted", anchor="middle"))

    input_w = 340
    input_h = 38
    ix = content_x + (content_w/2) - (input_w/2) - 80
    iy = band_y + 130
    svg.append(rect(ix, iy, input_w, input_h, cls="sketch", rx=8))
    svg.append(button(ix + input_w + 18, iy, 150, input_h, "Action Button", dark=True))

    # Footer dark strip
    svg.append(f'<rect x="{content_x}" y="{footer_y}" width="{content_w}" height="{FOOTER_DARK_H}" rx="14" ry="14" class="panel-dark" />')

    # Footer logo
    flw = 140
    flh = 44
    fx = content_x + (content_w/2) - (flw/2)
    fy = footer_y + 18
    svg.append(rect(fx, fy, flw, flh, cls="sketch", rx=10))
    svg.append(line(fx + 8, fy + 8, fx + flw - 8, fy + flh - 8))
    svg.append(line(fx + flw - 8, fy + 8, fx + 8, fy + flh - 8))

    # Footer links (white)
    link_y = footer_y + 92
    links = ["Home", "About", "News", "Read Me"]
    total_w = sum(approx_text_width(l) for l in links) + (len(links)-1) * NAV_GAP
    start_x = content_x + (content_w/2) - (total_w/2)
    x = start_x
    for item in links:
        svg.append(text(x, link_y, item, extra_cls="footer-link"))
        x += approx_text_width(item) + NAV_GAP

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    svg.append(text(frame_x + frame_w - 260, frame_y + frame_h + 18, f"Rendered: {ts}", extra_cls="small"))

    svg.append("</svg>")
    return "\n".join(svg)


# -------------------------
# Main
# -------------------------
def main():
    if not os.path.exists(INPUT_JSON):
        raise FileNotFoundError(f"Missing {INPUT_JSON}. Run: python main.py")

    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        wf = json.load(f)

    pages = wf.get("pages", [])
    if not pages:
        raise ValueError("wireframes.json has no pages.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    written = []
    for p in pages:
        page_name = p.get("page", "page")
        slug = p.get("slug", "/")
        fname = safe_filename(page_name)
        if slug == "/":
            fname = "home"
        out_path = os.path.join(OUTPUT_DIR, f"{fname}.svg")

        svg = render_page_svg(p)
        with open(out_path, "w", encoding="utf-8") as out:
            out.write(svg)

        written.append(out_path)

    print("Render complete.")
    print(f"Output folder: {os.path.abspath(OUTPUT_DIR)}")
    print("Files:")
    for w in written:
        print(" -", w)


if __name__ == "__main__":
    main()
