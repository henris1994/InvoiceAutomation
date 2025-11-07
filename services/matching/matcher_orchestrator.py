from utils.utilfunctions import _normalize_for_id,_norm
import hashlib
from services.matching.matcher_id import _assign_invoice_line_numbers

#Compare Invoice to PO if not perfect match in terms of items_id-s fallback to Ai description
def validate_and_match_invoice_items_against_po_strict(
    invoice_id: str,
    invoice_items: list[dict],
    po_items: list[dict],
    ai_match_fn=None,                 # callable(invoice_wo_ids, po_wo_ids) -> {"matches":[...], "unmatched_po_lines":[...]}
    accept_threshold: float = 0.80,
):
    used_ai_match = False 
    """
    Strict identity-only validator:
      - Fails if invoice has more lines than PO (no extras logic here).
      - Enforces one-to-one mapping across ID + DESC.
      - Uses DESC matching only for ID-unmatched lines vs unused PO lines.
    """
    # 0) Hard count rule
    if len(invoice_items) > len(po_items):
        return {
            "po_id": po_items[0].get("prchseordr_id") if po_items else None,
            "invoice_id": invoice_id,
            "pass": False,
            "fail_reasons": [{
                "reason": "invoice-has-more-lines-than-po",
                "invoice_line_count": len(invoice_items),
                "po_line_count": len(po_items),
            }],
            "id_matches": [],
            "desc_matches": [],
            "unmatched_invoice_lines": [
                {"invoice_line_no": i+1, "description": it.get("ItemDescription","")}
                for i, it in enumerate(invoice_items[len(po_items):])
            ],
            "unused_po_lines": [{"po_line_no": p.get("line_no"), "description": p.get("description","")} for p in po_items],
        }

    # 1)Assign line_number to invoice 
    invoice_items = _assign_invoice_line_numbers(invoice_id, invoice_items)

    # 2) Build PO maps (by vendor_part) and an index by line_no
    
    po_by_line_no = {}
    for po in po_items:
        po_by_line_no[po.get("line_no")] = po
        

    # Exact ID matches — strict consume-once
    id_matches = []
    used_po_line_nos = set()
    matched_invoice_uids = set()
    inv_unmatched_for_desc = []

    
    # Build dict key vendor_part --> value po object
    po_by_id = {}
    for po in po_items:
        vid = _norm(po.get("vendor_part"))
        if vid:
            po_by_id[vid] = po  

    for inv in invoice_items:
        sid = _norm(inv.get("SellerPartNumber"))
        if not sid:
            inv_unmatched_for_desc.append(inv)
            continue

        po_ref = po_by_id.get(sid)
        if not po_ref:
            inv_unmatched_for_desc.append(inv)
            continue

        pln = po_ref.get("line_no")
        if pln in used_po_line_nos:
            inv_unmatched_for_desc.append(inv)
            continue

        id_matches.append({
            "type": "id_match",
            "invoice_line_no": inv["invoice_line_no"],
            "invoice_line_uid": inv["invoice_line_uid"],
            "invoice_description": inv.get("ItemDescription",""),
            "po_line_no": pln,
            "po_description": po_ref.get("description",""),
            "confidence": 1.0,
        })
        used_po_line_nos.add(pln)
        matched_invoice_uids.add(inv["invoice_line_uid"])

   

    # Add invoice lines with missing/bad IDs to DESCRIPTION pool
    # for inv in invoice_items:
    #     if inv["invoice_line_uid"] in matched_invoice_uids:
    #         continue
    #     sid = _norm(inv.get("SellerPartNumber"))
    #     if not sid :
    #         inv_unmatched_for_desc.append(inv)

    #DESC fallback only against UNUSED PO lines (strict one-to-one across ID + DESC)
    desc_matches = []
    ai_resp=''
    if ai_match_fn and inv_unmatched_for_desc:
        po_unused = [po for po in po_items if po.get("line_no") not in used_po_line_nos]
        if po_unused:
            ai_invoice_payload = [
                {"invoice_line_no": inv["invoice_line_no"], "invoice_description": inv.get("ItemDescription","")}
                for inv in inv_unmatched_for_desc
            ]
            ai_po_payload = [
                {"po_line_no": po.get("line_no"), "po_description": po.get("description","")}
                for po in po_unused
            ]

            print(ai_po_payload)
            print("invoiceaipayloaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaad")
            print(ai_invoice_payload)
            print("invoiceaipayloaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaad")
            ai_resp = ai_match_fn(ai_invoice_payload, ai_po_payload)

            # One-to-one within DESC, and also against ID-consumed lines
            desc_used_po = set()
            desc_used_inv = set()
            for m in ai_resp.get("matches", []):
                if m.get("decision") != "match":
                    continue
                if m.get("matched_po_line_no") is None:
                    continue
                if float(m.get("confidence", 0.0)) < accept_threshold:
                    continue
                iln = int(m["invoice_line_no"])
                pln = int(m["matched_po_line_no"])
                if pln in used_po_line_nos or pln in desc_used_po:
                    continue
                if iln in desc_used_inv:
                    continue

                # accept
                inv = next((x for x in inv_unmatched_for_desc if x["invoice_line_no"] == iln), None)
                po  = po_by_line_no.get(pln)
                if not inv or not po:
                    continue
                desc_matches.append({
                    "type": "desc_match",
                    "invoice_line_no": iln,
                    "invoice_line_uid": inv["invoice_line_uid"],
                    "invoice_description": inv.get("ItemDescription",""),
                    "po_line_no": pln,
                    "po_description": po.get("description",""),
                    "confidence": float(m.get("confidence", 0.0)),
                    "evidence_tokens": m.get("evidence_tokens", []),
                })
                desc_used_po.add(pln)
                desc_used_inv.add(iln)

            # Merge used PO lines from DESC into the global used set
            used_po_line_nos |= desc_used_po
            used_ai_match = len(desc_matches) > 0
            print("description aiiiiiiiiiiiiiiiiiiiiiiiiia descp")
            print(used_ai_match)
    # Final strict decision: every invoice line must be matched (count already ≤ PO count)
    matched_invoice_nos = {m["invoice_line_no"] for m in id_matches} | {m["invoice_line_no"] for m in desc_matches}
    unmatched_invoice_lines = [
        {"invoice_line_no": inv["invoice_line_no"], "description": inv.get("ItemDescription","")}
        for inv in invoice_items
        if inv["invoice_line_no"] not in matched_invoice_nos
    ]
    unused_po_lines = [
        {"po_line_no": po.get("line_no"), "description": po.get("description","")}
        for po in po_items if po.get("line_no") not in used_po_line_nos
    ]

    all_matched = len(unmatched_invoice_lines) == 0

    invoice_items_resolved = [dict(x) for x in invoice_items]
    po_items_resolved      = [dict(x) for x in po_items]
    patch_log = []
    #ASSIGN ID-S TO THE MATCHED DESCRIPTION MATCHES
    if all_matched:
        # Fast index by line numbers
        inv_idx_by_line = {int(i.get("invoice_line_no", idx+1)): idx for idx, i in enumerate(invoice_items_resolved)}
        po_idx_by_line  = {int(p.get("line_no")): idx for idx, p in enumerate(po_items_resolved) if p.get("line_no") is not None}

        # Helper: stable synthetic ID if PO vendor_part missing
        def make_assigned_id(inv_desc: str, po_desc: str) -> str:
            key = _normalize_for_id(f"{inv_desc}|{po_desc}")
            return "ai_" + hashlib.sha1(key.encode()).hexdigest()[:12]

        # Only desc matches need id_enrichment (ID matches already agree by definition)
        for m in desc_matches:
            iln = int(m["invoice_line_no"])
            pln = int(m["po_line_no"])
            inv_i = inv_idx_by_line[iln]
            po_i  = po_idx_by_line[pln]

            inv_line = invoice_items_resolved[inv_i]
            po_line  = po_items_resolved[po_i]

           
            # generate deterministic ID and set on both sides
            assigned = make_assigned_id(inv_line.get("ItemDescription",""), po_line.get("description",""))
            inv_line["SellerPartNumber"] = assigned
            po_line["vendor_part"] = assigned
            inv_line["ai_resolution"] = "desc_match"
            po_line["ai_resolution"] = "desc_match"
            patch_log.append({
                    "invoice_line_no": iln,
                    "po_line_no": pln,
                    "action": "assign_synthetic_id_both_sides",
                    "value": assigned
                })

    return {
        "po_id": po_items[0].get("prchseordr_id") if po_items else None,
        "invoice_id": invoice_id,
        "pass": all_matched,
        "fail_reasons": ([] if all_matched else [{"reason": "unmatched-invoice-lines", "lines": [x["invoice_line_no"] for x in unmatched_invoice_lines]}]),
        "id_matches": id_matches,
        "desc_matches": desc_matches,
        "unmatched_invoice_lines": unmatched_invoice_lines,
        "unused_po_lines": unused_po_lines,
        "accept_threshold": accept_threshold,
        # NEW:
        "invoice_items_resolved": invoice_items_resolved,
        "po_items_resolved": po_items_resolved,
        "patch_log": patch_log,
        "ai_resp":ai_resp,
        "used_ai_match": used_ai_match 
        
        
        
    }