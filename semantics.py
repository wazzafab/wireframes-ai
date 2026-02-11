import json
from typing import Any, Dict, List

from jsonschema import validate

# Reuse your existing OpenAI call + helpers from main.py (keeps auth/model consistent)
from main import call_llm_json, load_json, save_json


SEMANTICS_OUT = "semantic.json"


SEMANTICS_SCHEMA: Dict[str, Any] = {
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
                "required": [
                    "page_id",
                    "label",
                    "path",
                    "purpose",
                    "primary_goal",
                    "audiences",
                    "sections",
                ],
                "properties": {
                    "page_id": {"type": "string", "minLength": 1},
                    "label": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "purpose": {"type": "string", "minLength": 1},
                    "primary_goal": {"type": "string", "minLength": 1},
                    "audiences": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "sections": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": [
                                "section_label",
                                "semantic_intent",
                                "narrative_role",
                                "tone",
                                "supporting_facts",
                                "success_signal",
                            ],
                            "properties": {
                                # Keep this label-driven for now; we’ll bind to wireframe section_ids in Step 1.3+
                                "section_label": {"type": "string", "minLength": 1},

                                # Examples: "credibility", "explain-framework", "how-it-works", "advocacy-proof", "contact"
                                "semantic_intent": {"type": "string", "minLength": 1},

                                # Examples: "authority framing", "reassurance", "education", "conversion"
                                "narrative_role": {"type": "string", "minLength": 1},

                                # Examples: ["trustworthy","clear"], ["bold","hopeful"]
                                "tone": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },

                                # Fact pointers: keep as strings for now e.g. "facts.mission", "facts.objectives[0]"
                                "supporting_facts": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },

                                # A measurable “what does good look like”
                                "success_signal": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                },
            },
        }
    },
}


def build_semantics_prompt(sitemap: Dict[str, Any], facts: Dict[str, Any], wireframes: Dict[str, Any]) -> str:
    return (
        "You are a semantic website planner.\n"
        "Your job: create a semantic layer (meaning + intent) for each EXISTING wireframe section.\n\n"
        "Hard rules:\n"
        "1) You MUST use the wireframes.json structure as the section anchor list.\n"
        "   For each page, output EXACTLY the same number of semantic sections as wireframes.json layout.sections.\n"
        "2) Each semantic section must include section_label that EXACTLY matches the wireframe section h2 (or label).\n"
        "   Do not invent new section labels.\n"
        "3) Do NOT invent facts. supporting_facts may only reference facts.json.\n"
        "4) supporting_facts must be simple string pointers like: facts.mission, facts.objectives[0], facts.offerings[2]\n"
        "5) If info is missing in facts.json, leave supporting_facts empty and set success_signal to reflect the gap.\n"
        "6) Output must strictly follow the provided JSON schema.\n\n"
        "Inputs:\n"
        f"SITEMAP_JSON:\n{json.dumps(sitemap, ensure_ascii=False, indent=2)}\n\n"
        f"FACTS_JSON:\n{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
        f"WIREFRAMES_JSON:\n{json.dumps(wireframes, ensure_ascii=False, indent=2)}\n"
    )



def main() -> None:
    sitemap = load_json("sitemap.json")
    facts = load_json("facts.json")
    wireframes = load_json("wireframes.json")


    system = (
        "Return ONLY JSON that matches the provided schema. "
        "No commentary, no markdown, no extra keys."
    )
    user = build_semantics_prompt(sitemap, facts, wireframes)

    semantics = call_llm_json(system=system, user=user, schema=SEMANTICS_SCHEMA)

    # Belt-and-suspenders local validation
    validate(instance=semantics, schema=SEMANTICS_SCHEMA)

    save_json(SEMANTICS_OUT, semantics)
    print(f"Wrote {SEMANTICS_OUT}")


if __name__ == "__main__":
    main()
