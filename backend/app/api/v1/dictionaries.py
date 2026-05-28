"""Reference dictionaries — ICD-10 lookup for autocomplete."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user, get_dictionaries_service
from app.models.user import User
from app.schemas.profile import ICD10Entry
from app.services.dictionaries_service import DictionariesService

router = APIRouter(prefix="/v1/dictionaries", tags=["dictionaries"])


@router.get("/icd10", response_model=list[ICD10Entry])
async def search_icd10(
    search: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    _current_user: User = Depends(get_current_user),
    svc: DictionariesService = Depends(get_dictionaries_service),
) -> list[ICD10Entry]:
    return await svc.search_icd10(search, limit=limit)
