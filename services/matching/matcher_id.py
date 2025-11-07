import hashlib
#Before comparing invoice to po assign invoice line_no so we can reliably get the invoice line_items
def _assign_invoice_line_numbers(invoice_id: str, items: list[dict]) -> list[dict]:
    out = []
    for idx, it in enumerate(items, start=1):  # 1-based index
        key_src = f"{invoice_id}|{idx}|{it.get('SellerPartNumber','')}|{it.get('ItemDescription','')}"
        uid = hashlib.sha1(key_src.encode()).hexdigest()[:12]
        it = {**it} #make a copy of dict
        it.setdefault("invoice_line_no", idx)
        it["invoice_line_uid"] = f"inv_{uid}"
        out.append(it)
    return out