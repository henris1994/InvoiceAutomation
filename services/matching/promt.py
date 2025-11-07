import json
from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def chatgpt_match_by_description(invoice_items_wo_ids: list[dict],
                                 po_items_wo_ids: list[dict]) -> dict:
    system_msg = {
        "role": "system",
        "content": (
            "You are an expert at matching invoice line items to purchase order (PO) line items.\n"
            "Data fields:\n"
            "- Invoice line: `invoice_line_no`, `invoice_description`.\n"
            "- PO line: `po_line_no`, `po_description`.\n\n"

            "MATCHING RULES:\n"
            "1) Compare by natural-language semantics of `invoice_description` ↔ `po_description` only.\n"
            "2) One-to-one: each PO line may be used at most once (consume-once across all matches).\n"
            "3) For each invoice line, pick the single best PO line. If no clearly appropriate match exists, "
            "   return decision='no_match' and matched_po_line_no=null.\n"
            "4) Confidence ∈ [0,1]: strong alignment → 0.80–0.95; partial → 0.50–0.79; weak/none → 0.00–0.49.\n"
            "5) `evidence_tokens` must be 1–3 short quoted substrings taken from the descriptions that show key overlapping phrases.\n"
            "6) `unmatched_po_lines` must contain the PO line numbers that remain unused after all assignments; "
            "   make them unique and sorted ascending.\n\n"

            "OUTPUT REQUIREMENTS:\n"
            "- Return VALID JSON ONLY (no prose) that conforms EXACTLY to the provided JSON schema (no extra keys).\n"
            "- Output one result object per invoice line in the input."
        )
    }

    user_payload = {
        "invoice_items": invoice_items_wo_ids,
        "po_items": po_items_wo_ids
    }

    user_msg = {
        "role": "user",
        "content": (
            "Match the following invoice items to purchase order items using textual descriptions only.\n\n"
            f"{json.dumps(user_payload, indent=2)}\n\n"
            "Return JSON with keys: matches, unmatched_po_lines."
        )
    }

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[system_msg, user_msg],
        temperature=0,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "InvoicePOMatches",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "matches": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "invoice_line_no": {"type": "integer"},
                                    "invoice_description": {"type": "string"},
                                    "decision": {"type": "string", "enum": ["match", "no_match"]},
                                    "matched_po_line_no": {"type": ["integer", "null"]},
                                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                                    "evidence_tokens": {
                                        "type": "array",
                                        "minItems": 1,
                                        "maxItems": 3,
                                        "items": {"type": "string"}
                                    }
                                },
                                "required": [
                                    "invoice_line_no",
                                    "invoice_description",
                                    "decision",
                                    "matched_po_line_no",
                                    "confidence",
                                    "evidence_tokens"
                                ]
                            }
                        },
                        "unmatched_po_lines": {
                            "type": "array",
                            "items": {"type": "integer"}
                        }
                    },
                    "required": ["matches", "unmatched_po_lines"]
                }
            }
        }
    )

    content = resp.choices[0].message.content
    data = json.loads(content)

    # Enforce uniqueness & sorting for safety (since the schema can’t do it here)
    if "unmatched_po_lines" in data:
        data["unmatched_po_lines"] = sorted({int(x) for x in data["unmatched_po_lines"]})

    print("Trying to match descriptions for missing IDs (gpt-4o-mini)")
    print(data)
    return data