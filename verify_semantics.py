import json


def load(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    wf = load("wireframes.enriched.json")

    missing = []

    for page in wf.get("pages", []):
        slug = page.get("slug", "<missing-slug>")
        sections = (page.get("layout") or {}).get("sections", [])

        for idx, section in enumerate(sections):
            label = section.get("h2") or section.get("label") or f"<section-{idx}>"
            sem = section.get("semantic")

            if not isinstance(sem, dict):
                missing.append((slug, label, "missing semantic object"))
                continue

            # required semantic keys (lightweight, deterministic)
            required = ["intent", "narrative_role", "tone", "supporting_facts", "success_signal"]
            for k in required:
                if k not in sem:
                    missing.append((slug, label, f"missing semantic.{k}"))
                    
            # Component provenance coverage check
            supporting = sem.get("supporting_facts", [])
            if supporting:
                for comp in section.get("components", []):
                    ctype = comp.get("type", "").lower()

                    if ctype in {"hero", "text", "cards", "bullets", "cta", "quote", "faq"}:
                        if "provenance_hint" not in comp:
                            missing.append(
                                (slug, label, f"component missing provenance_hint ({ctype})")
                            )


    if missing:
        print("❌ Semantic verification failed. Missing semantic metadata:")
        for slug, label, reason in missing:
            print(f" - {slug} :: {label} -> {reason}")
        raise SystemExit(1)

    print("Semantic verification passed (all sections have semantic metadata).")


if __name__ == "__main__":
    main()
