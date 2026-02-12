import os
import re
import json
import argparse
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from docx import Document
from jsonschema import validate


# =========================
# CONFIG
# =========================
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()

# Locked default filename per SOP
DOC_PATH_DEFAULT = os.getenv("DOC_PATH", r"input.docx").strip()

SITEMAP_OUT = "sitemap.json"
FACTS_OUT = "facts.json"
WIREFRAMES_OUT = "wireframes.json"

TIMEOUT_SECS = 120


# =========================
# BASICS
# =========================
def die(msg: str) -> None:
    raise SystemExit(msg)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def read_txt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_docx(path: str) -> str:
    doc = Document(path)
    parts: List[str] = []
    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            parts.append(t)
    return "\n".join(parts).strip()


def load_doc_text(path: str) -> str:
    if not os.path.exists(path):
        die(f"File not found: {path}")

    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return read_docx(path)
    if ext == ".txt":
        return read_txt(path)

    die("Only .docx and .txt are supported for input.")


def slugify(label: str) -> str:
    s = (label or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s\-]+", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s or "page"


def is_filler_text(s: str) -> bool:
    if not s:
        return True
    t = s.strip().lower()
    if "lorem ipsum" in t:
        return True
    if t.startswith("[confirm"):
        return True
    if t.startswith("confirm "):
        return True
    return False


# =========================
# OPENAI HTTP
# =========================
def openai_post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        die("OPENAI_API_KEY is missing. Add it to your .env file.")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    r = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECS)
    if r.status_code >= 400:
        try:
            j = r.json()
        except Exception:
            die(f"OpenAI API error {r.status_code}: {r.text[:1500]}")
        die(f"OpenAI API error {r.status_code}: {json.dumps(j, indent=2)[:3000]}")

    return r.json()


def _extract_text_from_responses(resp: Dict[str, Any]) -> str:
    """
    Robust extraction of output text from Responses API payload.
    """
    if isinstance(resp, dict) and isinstance(resp.get("output_text"), str):
        return resp["output_text"].strip()

    out = resp.get("output")
    if isinstance(out, list):
        chunks: List[str] = []
        for item in out:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content", [])
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict):
                    continue
                if c.get("type") in ("output_text", "text") and isinstance(c.get("text"), str):
                    chunks.append(c["text"])
        if chunks:
            return "\n".join(chunks).strip()

    return ""


def call_llm_json(system: str, user: str, schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Responses API first (Structured Outputs). Chat Completions fallback.
    Always validates JSON against schema.
    """
    # 1) Responses API
    try:
        resp = openai_post_json(
            "https://api.openai.com/v1/responses",
            {
                "model": OPENAI_MODEL,
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # ✅ Correct shape for Responses structured outputs
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "output",
                        "schema": schema,
                    }
                },
            },
        )

        text_out = _extract_text_from_responses(resp)
        if not text_out:
            raise RuntimeError("Responses API returned no usable output text.")

        data = json.loads(text_out)
        validate(instance=data, schema=schema)
        return data

    except Exception:
        # 2) Chat Completions fallback
        resp = openai_post_json(
            "https://api.openai.com/v1/chat/completions",
            {
                "model": OPENAI_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "output",
                        "schema": schema,
                    },
                },
                "temperature": 0.2,
            },
        )

        content = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("Chat Completions fallback returned empty content.")

        data = json.loads(content)
        validate(instance=data, schema=schema)
        return data


# =========================
# SCHEMAS
# =========================
PHASE1_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["site_map", "primary_nav", "footer_nav"],
    "properties": {
        "site_map": {
            "type": "array",
            "minItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["page", "slug", "purpose"],
                "properties": {
                    "page": {"type": "string", "minLength": 1},
                    "slug": {"type": "string", "minLength": 1},
                    "purpose": {"type": "string", "minLength": 1},
                },
            },
        },
        "primary_nav": {"type": "array", "items": {"type": "string"}, "minItems": 3},
        "footer_nav": {"type": "array", "items": {"type": "string"}, "minItems": 2},
    },
}

FACTS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "org_name",
        "tagline",
        "mission",
        "vision",
        "audiences",
        "offerings",
        "programs",
        "objectives",
        "proof_points",
        "primary_ctas",
        "contact",
        "resources",
        "tone_keywords",
    ],
    "properties": {
        "org_name": {"type": ["string", "null"]},
        "tagline": {"type": ["string", "null"]},
        "mission": {"type": ["string", "null"]},
        "vision": {"type": ["string", "null"]},
        "audiences": {"type": "array", "items": {"type": "string"}},
        "offerings": {"type": "array", "items": {"type": "string"}},
        "programs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "summary"],
                "properties": {
                    "name": {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
        },
        "objectives": {"type": "array", "items": {"type": "string"}},
        "proof_points": {"type": "array", "items": {"type": "string"}},
        "primary_ctas": {"type": "array", "items": {"type": "string"}},
        "contact": {
            "type": "object",
            "additionalProperties": False,
            "required": ["email", "phone", "address", "social"],
            "properties": {
                "email": {"type": ["string", "null"]},
                "phone": {"type": ["string", "null"]},
                "address": {"type": ["string", "null"]},
                "social": {"type": "array", "items": {"type": "string"}},
            },
        },
        "resources": {"type": "array", "items": {"type": "string"}},
        "tone_keywords": {"type": "array", "items": {"type": "string"}},
    },
}

SECTION_TYPES_ALLOWED = [
    "section",
    "hero",
    "content",
    "features",
    "steps",
    "proof",
    "faq",
    "cta",
    "form",
    "gallery",
    "footer_cta",
]

COMPONENT_TYPES_ALLOWED = [
    "text",
    "image",
    "button",
    "nav",
    "cards",
    "list",
    "quote",
    "stats",
    "form",
    "accordion",
    "divider",
    "form-field",
    "form_field",
    "field",
    "input",
    "textarea",
    "select",
    "checkbox",
    "radio",
]

# IMPORTANT:
# OpenAI structured outputs requires: required must include every key in properties.
# So: section requires h3; component requires placeholder/fields/items (but we allow null/empty).
PHASE2_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["pages"],
    "properties": {
        "pages": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["page", "slug", "layout"],
                "properties": {
                    "page": {"type": "string", "minLength": 1},
                    "slug": {"type": "string", "minLength": 1},
                    "layout": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["h1", "sections"],
                        "properties": {
                            "h1": {"type": "string", "minLength": 1},
                            "sections": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["id", "type", "label", "h2", "h3", "components"],
                                    "properties": {
                                        "id": {"type": "string", "minLength": 1},
                                        "type": {"type": "string", "enum": SECTION_TYPES_ALLOWED},
                                        "label": {"type": "string", "minLength": 1},
                                        "h2": {"type": "string", "minLength": 1},
                                        "h3": {"type": ["array", "null"], "items": {"type": "string"}},
                                        "components": {
                                            "type": "array",
                                            "minItems": 1,
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "required": ["type", "label", "placeholder", "fields", "items"],
                                                "properties": {
                                                    "type": {"type": "string", "enum": COMPONENT_TYPES_ALLOWED},
                                                    "label": {"type": "string", "minLength": 1},
                                                    "placeholder": {"type": ["string", "null"]},
                                                    "fields": {"type": ["array", "null"], "items": {"type": "string"}},
                                                    "items": {"type": ["array", "null"], "items": {"type": "string"}},
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
    },
}


# =========================
# CANONICALISATION / SCRUB
# =========================
def canonical_section_type(t: str) -> str:
    x = (t or "").strip().lower().replace("_", "-").replace(" ", "-")
    if x in ("call-to-action", "calltoaction", "call-toaction", "cta-section", "cta-block"):
        return "cta"
    if x in ("footer-cta", "footercta", "footer-call-to-action", "footer-calltoaction"):
        return "footer_cta"
    if x in SECTION_TYPES_ALLOWED:
        return x
    return "content"


def canonical_component_type(t: str) -> str:
    x = (t or "").strip().lower().replace("_", "-").replace(" ", "-")
    if x in ("formfield", "form-field", "field"):
        return "form-field"
    if x in COMPONENT_TYPES_ALLOWED:
        return x
    return "text"


def scrub_wireframes(wf: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensures:
    - canonical enums
    - required keys always present (h3, placeholder, fields, items)
    - no lorem / [CONFIRM] where avoidable
    """
    for p in wf.get("pages", []):
        layout = p.get("layout", {})
        sections = layout.get("sections", [])
        for s in sections:
            s["type"] = canonical_section_type(s.get("type", ""))

            # h2 required and non-empty
            h2 = (s.get("h2") or "").strip()
            if not h2 or is_filler_text(h2):
                s["h2"] = (s.get("label") or "Section").strip()

            # h3 is REQUIRED by schema now: ensure present (empty list if none)
            if s.get("h3") is None:
                s["h3"] = []
            elif isinstance(s.get("h3"), list):
                s["h3"] = [x for x in s["h3"] if isinstance(x, str) and x.strip() and not is_filler_text(x)][:3]
            else:
                s["h3"] = []

            # Components
            for c in s.get("components", []):
                c["type"] = canonical_component_type(c.get("type", ""))
                c["label"] = (c.get("label") or "Component").strip()

                # Required keys: placeholder/fields/items
                if "placeholder" not in c or c["placeholder"] is None:
                    c["placeholder"] = ""
                if "fields" not in c or c["fields"] is None:
                    c["fields"] = []
                if "items" not in c or c["items"] is None:
                    c["items"] = []

                # Clean placeholder
                if isinstance(c["placeholder"], str) and is_filler_text(c["placeholder"]):
                    c["placeholder"] = c["label"]

                # Clean fields/items arrays
                for k in ("fields", "items"):
                    arr = c.get(k)
                    if not isinstance(arr, list):
                        c[k] = []
                        continue
                    cleaned = [x for x in arr if isinstance(x, str) and x.strip() and not is_filler_text(x)]
                    c[k] = cleaned[:10]

    validate(instance=wf, schema=PHASE2_SCHEMA)
    return wf


# =========================
# PHASE 1
# =========================
def run_phase1(doc_text: str) -> Dict[str, Any]:
    system = (
        "You are a website IA (information architecture) assistant.\n"
        "Return ONLY valid JSON matching the provided schema. No markdown, no commentary."
    )

    user = f"""
You will be given a business scoping document.
Your job: propose a practical, standard website sitemap for an effective public-facing website.

Hard requirements:
- Must include Home (slug "/")
- Must include About (slug "/about")
- Must include Contact (slug "/contact")
- Add any other pages that are clearly warranted by the document (but keep it practical).
- Provide primary_nav and footer_nav labels matching the pages.
- Slugs must be lowercase and hyphenated. Home must be "/".

Document:
\"\"\"{doc_text}\"\"\"
""".strip()

    data = call_llm_json(system, user, PHASE1_SCHEMA)

    pages = data["site_map"]
    by_name = {p["page"].strip().lower(): p for p in pages}

    if "home" not in by_name:
        pages.insert(0, {"page": "Home", "slug": "/", "purpose": "Primary landing page"})
    else:
        by_name["home"]["slug"] = "/"

    if "about" not in by_name:
        pages.append({"page": "About", "slug": "/about", "purpose": "About the business/organization"})

    if "contact" not in by_name:
        pages.append({"page": "Contact", "slug": "/contact", "purpose": "Contact and enquiry"})

    for p in pages:
        if p["slug"] == "/":
            continue
        p["slug"] = "/" + slugify(p["slug"].lstrip("/"))

    page_labels = [p["page"] for p in pages]
    data["primary_nav"] = [x for x in data["primary_nav"] if x in page_labels]
    data["footer_nav"] = [x for x in data["footer_nav"] if x in page_labels]

    if len(data["primary_nav"]) < 3:
        data["primary_nav"] = page_labels[: min(6, len(page_labels))]

    if len(data["footer_nav"]) < 2:
        data["footer_nav"] = page_labels[: min(4, len(page_labels))]

    data["site_map"] = pages
    validate(instance=data, schema=PHASE1_SCHEMA)
    return data


# =========================
# PHASE 1.5
# =========================
def run_phase1_5(doc_text: str) -> Dict[str, Any]:
    system = (
        "You are an information extraction assistant.\n"
        "Extract facts from the document into a compact facts bank for website wireframing.\n"
        "Return ONLY valid JSON matching schema.\n"
        "If unknown, use null or empty arrays.\n"
        "Do NOT invent facts. Do NOT output lorem. Do NOT output [CONFIRM]."
    )

    user = f"""
Extract a facts bank from this document for use in generating website wireframes.

Rules:
- Do NOT invent facts.
- If something is not explicitly stated, set it to null (or [] where applicable).
- Keep strings concise (1-2 sentences max for mission/vision).
- Objectives should be short bullet-style strings if present.
- Programs should be name + one-line summary if present.

Document:
\"\"\"{doc_text}\"\"\"
""".strip()

    data = call_llm_json(system, user, FACTS_SCHEMA)

    def scrub_str(x: Optional[str]) -> Optional[str]:
        if x is None:
            return None
        t = x.strip()
        if not t or is_filler_text(t):
            return None
        return t

    data["org_name"] = scrub_str(data.get("org_name"))
    data["tagline"] = scrub_str(data.get("tagline"))
    data["mission"] = scrub_str(data.get("mission"))
    data["vision"] = scrub_str(data.get("vision"))

    for k in ["audiences", "offerings", "objectives", "proof_points", "primary_ctas", "resources", "tone_keywords"]:
        data[k] = [
            x.strip()
            for x in (data.get(k) or [])
            if isinstance(x, str) and x.strip() and not is_filler_text(x)
        ]

    cleaned_programs = []
    for pr in (data.get("programs") or []):
        if not isinstance(pr, dict):
            continue
        name = (pr.get("name") or "").strip()
        summary = (pr.get("summary") or "").strip()
        if name and not is_filler_text(name):
            if is_filler_text(summary):
                summary = ""
            cleaned_programs.append({"name": name, "summary": summary})
    data["programs"] = cleaned_programs

    c = data.get("contact") or {}
    c["email"] = scrub_str(c.get("email"))
    c["phone"] = scrub_str(c.get("phone"))
    c["address"] = scrub_str(c.get("address"))
    c["social"] = [
        x.strip()
        for x in (c.get("social") or [])
        if isinstance(x, str) and x.strip() and not is_filler_text(x)
    ]
    data["contact"] = c

    validate(instance=data, schema=FACTS_SCHEMA)
    return data


# =========================
# PHASE 2
# =========================
def run_phase2(sitemap: Dict[str, Any], facts: Dict[str, Any]) -> Dict[str, Any]:
    system = (
        "You are a website wireframe planner.\n"
        "You produce JSON that will be rendered into Balsamiq-like wireframes.\n\n"
        "Absolute rules:\n"
        "- Output MUST be valid JSON and MUST conform to the given schema.\n"
        "- Use ONLY the provided sitemap + facts bank. Do not invent details.\n"
        "- DO NOT output Lorem ipsum. DO NOT output [CONFIRM].\n"
        "- If a detail is missing, use neutral scaffolding text derived from labels.\n"
        "- Every section MUST include h2.\n"
        "- Always include h3 as an array (can be empty).\n"
        "- Section type MUST be one of the allowed enums (use 'cta', not 'call-to-action').\n"
        "- Every component MUST include placeholder (string), fields (array), items (array) even if empty.\n"
        "- Generate ONLY ONE page per request.\n"
    )

    pages_out: List[Dict[str, Any]] = []

    for page in sitemap["site_map"]:
        expected_page = page["page"]
        expected_slug = page["slug"]

        user = f"""
Sitemap (full, for navigation context only):
{json.dumps(sitemap["site_map"], indent=2)}

Primary nav labels:
{json.dumps(sitemap["primary_nav"], indent=2)}

Footer nav labels:
{json.dumps(sitemap["footer_nav"], indent=2)}

Facts bank (ground truth):
{json.dumps(facts, indent=2)}

Task:
Generate wireframes JSON for EXACTLY this one page:
{json.dumps(page, indent=2)}

Rules:
- Return a JSON object with a single key: "pages"
- "pages" must be an array with EXACTLY 1 item (the page above)
- That item MUST have:
  - page = "{expected_page}"
  - slug = "{expected_slug}"
  - layout.h1
  - layout.sections (3 to 7 sections), each with:
    - id (unique)
    - type (enum only: {SECTION_TYPES_ALLOWED})
    - label
    - h2 (always present)
    - h3 (always present as array; can be empty)
    - components array

Component rules:
- Every component object MUST include keys:
  - type, label, placeholder, fields, items
- placeholder should be "" if not needed
- fields/items should be [] if not needed

Component types allowed:
{COMPONENT_TYPES_ALLOWED}

Populate headings/bullets using the facts bank wherever possible.
If facts are missing, keep it generic but still meaningful (no lorem).

Return JSON only.
""".strip()

        page_data = call_llm_json(system, user, PHASE2_SCHEMA)
        page_data = scrub_wireframes(page_data)

        # Strict: must be exactly one page returned
        if "pages" not in page_data or not isinstance(page_data["pages"], list) or len(page_data["pages"]) != 1:
            die(f"Phase 2 expected exactly 1 page, got: {type(page_data.get('pages'))} len={len(page_data.get('pages', [])) if isinstance(page_data.get('pages'), list) else 'n/a'}")

        one = page_data["pages"][0]

        # Strict: enforce expected identity
        if one.get("page") != expected_page or one.get("slug") != expected_slug:
            die(
                "Phase 2 page identity mismatch.\n"
                f"Expected: ({expected_page}, {expected_slug})\n"
                f"Got: ({one.get('page')}, {one.get('slug')})"
            )

        pages_out.append(one)

    data = {"pages": pages_out}

    # Final sanity check: must match sitemap pages exactly
    sm_pages = {(p["page"], p["slug"]) for p in sitemap["site_map"]}
    wf_pages = {(p["page"], p["slug"]) for p in data["pages"]}
    if sm_pages != wf_pages:
        missing = sm_pages - wf_pages
        extra = wf_pages - sm_pages
        die(f"Phase 2 page mismatch.\nMissing: {missing}\nExtra: {extra}")

    return data

# =========================
# MAIN / CLI
# =========================
def main() -> None:
    parser = argparse.ArgumentParser(description="Wireframe Builder (Phase 1 / 1.5 / 2)")
    parser.add_argument("--doc", default=DOC_PATH_DEFAULT, help="Path to input.docx or .txt (default: input.docx)")
    parser.add_argument("--phase", default="all", choices=["1", "1.5", "2", "all"], help="Run a specific phase")
    args = parser.parse_args()

    doc_path = args.doc
    if not os.path.isabs(doc_path):
        doc_path = os.path.join(os.getcwd(), doc_path)

    doc_text = load_doc_text(doc_path)
    if not doc_text:
        die("Document text is empty after parsing. Check input.docx contents.")

    sitemap = None
    facts = None

    if args.phase in ("1", "all"):
        sitemap = run_phase1(doc_text)
        save_json(SITEMAP_OUT, sitemap)
        print(f"Phase 1 complete. Saved {SITEMAP_OUT}")
        print(f"Primary nav: {sitemap['primary_nav']}")

    if args.phase in ("1.5", "all"):
        facts = run_phase1_5(doc_text)
        save_json(FACTS_OUT, facts)
        print(f"Phase 1.5 complete. Saved {FACTS_OUT}")

    if args.phase in ("2", "all"):
        if sitemap is None:
            if not os.path.exists(SITEMAP_OUT):
                die("Missing sitemap.json. Run Phase 1 first.")
            sitemap = load_json(SITEMAP_OUT)

        if facts is None:
            if not os.path.exists(FACTS_OUT):
                die("Missing facts.json. Run Phase 1.5 first.")
            facts = load_json(FACTS_OUT)

        wireframes = run_phase2(sitemap, facts)
        save_json(WIREFRAMES_OUT, wireframes)
        print(f"Phase 2 complete. Saved {WIREFRAMES_OUT}")
        print("Next: python verify.py")

    if args.phase not in ("1", "1.5", "2", "all"):
        die("Unknown phase selected.")


if __name__ == "__main__":
    main()
