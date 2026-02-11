import json
import re
from typing import Any, Dict, List, Tuple


def load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s\-\/]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def best_match(target: str, candidates: List[str]) -> Tuple[str, float]:
    """
    Very lightweight matching:
    score = word overlap ratio
    """
    t_words = set(norm(target).split())
    best = ("", 0.0)
    for c in candidates:
        c_words = set(norm(c).split())
        if not t_words or not c_words:
            continue
        overlap = len(t_words & c_words)
        score = overlap / max(len(t_words), len(c_words))
        if score > best[1]:
            best = (c, score)
    return best


def semantic_page_key(p: Dict[str, Any]) -> str:
    # Prefer path if present, else page_id, else slug-like value
    return p.get("path") or p.get("page_id") or p.get("slug") or ""


def wireframe_page_key(p: Dict[str, Any]) -> str:
    # In your wireframes.json the canonical page reference is slug ("/about", "/")
    return p.get("slug") or ""


def main() -> None:
    wireframes = load("wireframes.json")
    semantics = load("semantic.json")

    # Build lookup: page_key (path/slug) -> semantic sections
    sem_by_page: Dict[str, List[Dict[str, Any]]] = {}
    for p in semantics.get("pages", []):
        key = semantic_page_key(p)
        sem_by_page[norm(key)] = p.get("sections", [])

    report: Dict[str, Any] = {"pages": []}

    for page in wireframes.get("pages", []):
        page_key = wireframe_page_key(page)
        if not page_key:
            continue

        # Wireframe sections are inside layout.sections
        layout = page.get("layout", {})
        wf_sections = layout.get("sections", [])

        # Use h2 first (most stable), else label
        wf_labels: List[str] = []
        for s in wf_sections:
            wf_labels.append(s.get("h2") or s.get("label") or "")

        sem_sections = sem_by_page.get(norm(page_key), [])
        sem_labels = [s.get("section_label", "") for s in sem_sections]

        matches = []
        for sem_label in sem_labels:
            m, score = best_match(sem_label, wf_labels)
            matches.append(
                {
                    "semantic_section_label": sem_label,
                    "best_wireframe_section_label": m,
                    "score": round(score, 3),
                }
            )

        report["pages"].append(
            {
                "page_slug": page_key,
                "wireframe_section_labels": wf_labels,
                "semantic_section_labels": sem_labels,
                "auto_matches": matches,
            }
        )

    with open("binding_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("Wrote binding_report.json")


if __name__ == "__main__":
    main()
