import os
import re

from fastapi import APIRouter

router = APIRouter()
_EMAIL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")


@router.get("/health")
def health():
    c = os.environ.get("CONTACT_EMAIL", "").strip()
    return {"ok": True, "service": "mordecai", "contact": c if _EMAIL.match(c) else ""}
