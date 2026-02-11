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

    # Build semantic lookup: page -> section label -> semantic block
    sem_lookup = {}

    for p in semantics["pages"]:
        key = semantic_page_key(p)
        sem_lookup[key] = {}

        for sec in p["sections"]:
            label = sec["section_label"]
            sem_lookup[key][label] = sec

    enriched = deepcopy(wireframes)

    for page in enriched["pages"]:
        page_key = page.get("slug") or ""

        layout = page.get("layout", {})
        sections = layout.get("sections", [])

        for section in sections:
            label = section.get("h2") or section.get("label") or ""

            sem = sem_lookup.get(page_key, {}).get(label)

            if not sem:
                continue

            # Inject semantic metadata — renderer-safe keys
            section["semantic"] = {
                "intent": sem["semantic_intent"],
                "narrative_role": sem["narrative_role"],
                "tone": sem["tone"],
                "supporting_facts": sem["supporting_facts"],
                "success_signal": sem["success_signal"],
            }
            # OPTIONAL: component-level provenance hints (non-breaking)
            # We do NOT attempt perfect attribution yet; we provide a constrained hint list.
            # This is used later for refinement/export, not rendering.
            supporting = sem["supporting_facts"] or []

            def pick(prefixes):
                # Return supporting facts that start with any prefix
                picked = []
                for p in prefixes:
                    picked.extend([f for f in supporting if f.startswith(p)])
                # Fallback: if nothing matched, return the full supporting list
                return picked if picked else supporting

            for comp in section.get("components", []):
                ctype = comp.get("type", "").lower()

                if ctype not in {"hero", "text", "cards", "bullets", "cta", "quote", "faq"}:
                    continue

                if ctype in {"hero", "text", "quote"}:
                    comp["provenance_hint"] = pick(["facts.mission", "facts.vision", "facts.overview", "facts.about", "facts.background"])

                elif ctype in {"bullets", "faq"}:
                    comp["provenance_hint"] = pick(["facts.objectives", "facts.steps", "facts.criteria", "facts.faq", "facts.key_points"])

                elif ctype == "cards":
                    comp["provenance_hint"] = pick(["facts.offerings", "facts.services", "facts.resources", "facts.programs"])

                elif ctype == "cta":
                    comp["provenance_hint"] = pick(["facts.cta", "facts.contact", "facts.email", "facts.phone"])
                else:
                    comp["provenance_hint"] = supporting

    save("wireframes.enriched.json", enriched)

    print("Wrote wireframes.enriched.json")


if __name__ == "__main__":
    main()
