import re
from decimal import Decimal
from datetime import datetime
from typing import Optional
import os
def _normalize_for_id(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[\W_]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s
def to_decimal(val):
    if val in (None, '', ' '):
        return Decimal('0.00')
    try:
        return Decimal(str(val).strip())
    except:
        return Decimal('0.00')

def int_or_zero(val):
    try:
        if val is None:
            return 0
        if isinstance(val, float):      # float -> int
            return int(val)
        if isinstance(val, str):        # string "2" or "2.0" -> int
            return int(float(val.strip()))
        return int(val)                 # int, Decimal, etc.
    except (ValueError, TypeError):
        return 0


def format_date(val):
    if isinstance(val, datetime):
        return val.strftime('%m%d%Y')
    if isinstance(val, str):
        try:
            parsed = datetime.strptime(val.strip(), '%Y-%m-%d')
            return parsed.strftime('%m%d%Y')
        except:
            return val.strip()
    return ''
def norm(v):
        return str(v).strip() if v is not None else None
def _norm(s): 
    return (s or "").strip().lower()
def _get_env(name: str, required: bool = True, default: Optional[str] = None) -> str:
    val = os.getenv(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val