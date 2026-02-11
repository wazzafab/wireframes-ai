import json

print("Running verification…")

with open("sitemap.json", "r", encoding="utf-8") as f:
    sitemap = json.load(f)

with open("wireframes.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

# Check pages match
sp = {(p["page"], p["slug"]) for p in sitemap["site_map"]}
wp = {(p["page"], p["slug"]) for p in wf["pages"]}

if sp != wp:
    raise Exception(f"Page mismatch:\nMissing: {sp - wp}\nExtra: {wp - sp}")


def canon(s: str) -> str:
    """Canonicalise enums to reduce false failures."""
    return (s or "").strip().lower().replace("_", "-").replace(" ", "-")


section_ok = {
    "section", "hero", "content", "features", "steps",
    "proof", "faq", "cta", "form", "gallery", "footer-cta"
}

# Note: main.py uses "footer_cta" – canonicalised to "footer-cta" here for consistency
# We'll accept both via canonicalisation.

component_ok = {
    "text", "image", "button", "nav", "cards",
    "list", "quote", "stats", "form", "accordion", "divider",
    # Form field variants (these are allowed by main.py schema)
    "form-field", "field", "input", "textarea", "select", "checkbox", "radio"
}

for page in wf["pages"]:
    for section in page["layout"]["sections"]:

        # h2 check
        if not section.get("h2") or not str(section["h2"]).strip():
            raise Exception(f"Missing h2 → {page['page']}::{section.get('id')}")

        # section enum check (canonicalised)
        st = canon(section.get("type"))
        if st == "footer-cta":
            st = "footer-cta"  # explicit, readable
        if st not in section_ok and st != "footer-cta":
            # accept footer_cta too (canonical form would be footer-cta already)
            raise Exception(f"Bad section type → {page['page']}::{section.get('id')}::{section.get('type')}")

        # component enum check (canonicalised)
        for comp in section.get("components", []):
            ct = canon(comp.get("type"))

            # Normalise common form-field variants to "form-field"
            if ct in {"formfield"}:
                ct = "form-field"

            if ct not in component_ok:
                raise Exception(
                    f"Bad component type → {page['page']}::{section.get('id')}::{comp.get('type')}"
                )

print("VERIFIED — wireframes are structurally correct.")
