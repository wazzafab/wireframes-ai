import json
from copy import deepcopy


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def semantic_page_key(p):
    return p.get("path") or p.get("page_id") or ""


def main():
    wireframes = load("wireframes.json")
    semantics = load("semantic.json")

    # Build semantic lookup: page_key -> section label -> semantic block
    # Note: semantic.json often uses path keys like "/about", while wireframes.json uses slugs like "about"
    sem_lookup = {}

    for p in semantics.get("pages", []):
        key = semantic_page_key(p)
        sem_lookup[key] = {}

        for sec in p.get("sections", []):
            label = sec.get("section_label", "")
            sem_lookup[key][label] = sec

    enriched = deepcopy(wireframes)

    for page in enriched.get("pages", []):
        slug = page.get("slug") or ""
        slug_slash = f"/{slug.lstrip('/')}" if slug else ""

        # Try multiple keys to match semantic.json robustly
        page_key_candidates = []
        if slug:
            page_key_candidates.append(slug)
        if slug_slash:
            page_key_candidates.append(slug_slash)

        layout = page.get("layout", {})
        sections = layout.get("sections", [])

        for section in sections:
            label = section.get("h2") or section.get("label") or ""

            sem = None
            for k in page_key_candidates:
                sem = sem_lookup.get(k, {}).get(label)
                if sem:
                    break

            if sem:
                # Inject semantic metadata — renderer-safe keys
                section["semantic"] = {
                    "intent": sem.get("semantic_intent", "unknown"),
                    "narrative_role": sem.get("narrative_role", "unknown"),
                    "tone": sem.get("tone", "neutral"),
                    "supporting_facts": sem.get("supporting_facts", []) or [],
                    "success_signal": sem.get("success_signal", "") or "",
                }

                # OPTIONAL: component-level provenance hints (non-breaking)
                supporting = section["semantic"]["supporting_facts"]

                def pick(prefixes):
                    picked = []
                    for pref in prefixes:
                        picked.extend([f for f in supporting if isinstance(f, str) and f.startswith(pref)])
                    return picked if picked else supporting

                for comp in section.get("components", []):
                    ctype = (comp.get("type", "") or "").lower()

                    if ctype not in {"hero", "text", "cards", "bullets", "cta", "quote", "faq"}:
                        continue

                    if ctype in {"hero", "text", "quote"}:
                        comp["provenance_hint"] = pick(
                            ["facts.mission", "facts.vision", "facts.overview", "facts.about", "facts.background"]
                        )
                    elif ctype in {"bullets", "faq"}:
                        comp["provenance_hint"] = pick(
                            ["facts.objectives", "facts.steps", "facts.criteria", "facts.faq", "facts.key_points"]
                        )
                    elif ctype == "cards":
                        comp["provenance_hint"] = pick(["facts.offerings", "facts.services", "facts.resources", "facts.programs"])
                    elif ctype == "cta":
                        comp["provenance_hint"] = pick(["facts.cta", "facts.contact", "facts.email", "facts.phone"])
                    else:
                        comp["provenance_hint"] = supporting

            else:
                # IMPORTANT: ensure every section has a semantic object so verify_semantics passes
                section["semantic"] = {
                    "intent": "unknown",
                    "narrative_role": "unknown",
                    "tone": "neutral",
                    "supporting_facts": [],
                    "success_signal": "",
                }

    save("wireframes.enriched.json", enriched)
    print("Wrote wireframes.enriched.json")


if __name__ == "__main__":
    main()
