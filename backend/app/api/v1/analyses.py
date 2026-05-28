"""Analyses REST API."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    get_analysis_norms_service,
    get_analysis_service,
    get_current_user,
)
from app.models.user import User
from app.schemas.analysis import (
    AnalysisHistoryResponse,
    AnalysisParameterDetail,
    AnalysisParameterNorm,
    AnalysisParameterSummary,
    AnalysisRecordCreate,
    AnalysisRecordFull,
    AnalysisRecordSummary,
    AnalysisRecordUpdate,
    AnalysisValueResponse,
    AnalysisValueUpdate,
)
from app.services.analysis_norms_service import AnalysisNormsService
from app.services.analysis_service import (
    AnalysisRecordNotFoundError,
    AnalysisService,
    AnalysisValueNotFoundError,
)

router = APIRouter(prefix="/v1/analyses", tags=["analyses"])


# ---------- Records -------------------------------------------------------- #


@router.get("", response_model=list[AnalysisRecordSummary])
async def list_analyses(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    only_abnormal: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    svc: AnalysisService = Depends(get_analysis_service),
) -> list[AnalysisRecordSummary]:
    return await svc.list_records(
        current_user.id,
        date_from=date_from,
        date_to=date_to,
        only_abnormal=only_abnormal,
    )


@router.post(
    "", response_model=AnalysisRecordFull, status_code=status.HTTP_201_CREATED
)
async def create_analysis(
    data: AnalysisRecordCreate,
    current_user: User = Depends(get_current_user),
    svc: AnalysisService = Depends(get_analysis_service),
) -> AnalysisRecordFull:
    return await svc.create_record(current_user.id, data)


@router.get("/{record_id}", response_model=AnalysisRecordFull)
async def get_analysis(
    record_id: int,
    current_user: User = Depends(get_current_user),
    svc: AnalysisService = Depends(get_analysis_service),
) -> AnalysisRecordFull:
    try:
        return await svc.get_record(current_user.id, record_id)
    except AnalysisRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail="analysis_not_found") from exc


@router.patch("/{record_id}", response_model=AnalysisRecordFull)
async def update_analysis(
    record_id: int,
    data: AnalysisRecordUpdate,
    current_user: User = Depends(get_current_user),
    svc: AnalysisService = Depends(get_analysis_service),
) -> AnalysisRecordFull:
    try:
        return await svc.update_record(current_user.id, record_id, data)
    except AnalysisRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail="analysis_not_found") from exc


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    record_id: int,
    current_user: User = Depends(get_current_user),
    svc: AnalysisService = Depends(get_analysis_service),
) -> None:
    try:
        await svc.delete_record(current_user.id, record_id)
    except AnalysisRecordNotFoundError as exc:
        raise HTTPException(status_code=404, detail="analysis_not_found") from exc


# ---------- Values --------------------------------------------------------- #


@router.patch("/values/{value_id}", response_model=AnalysisValueResponse)
async def update_value(
    value_id: int,
    data: AnalysisValueUpdate,
    current_user: User = Depends(get_current_user),
    svc: AnalysisService = Depends(get_analysis_service),
) -> AnalysisValueResponse:
    try:
        return await svc.update_value(current_user.id, value_id, data)
    except AnalysisValueNotFoundError as exc:
        raise HTTPException(status_code=404, detail="value_not_found") from exc


# ---------- Parameter history --------------------------------------------- #


@router.get(
    "/parameters/{parameter_code}/history",
    response_model=AnalysisHistoryResponse,
)
async def parameter_history(
    parameter_code: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    svc: AnalysisService = Depends(get_analysis_service),
) -> AnalysisHistoryResponse:
    return await svc.get_parameter_history(
        current_user.id,
        parameter_code,
        date_from=date_from,
        date_to=date_to,
    )


# ---------- Dictionary --------------------------------------------------- #


dict_router = APIRouter(prefix="/v1/dictionaries", tags=["dictionaries"])


@dict_router.get(
    "/analysis-parameters",
    response_model=list[AnalysisParameterSummary],
)
async def search_parameters(
    search: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    _current_user: User = Depends(get_current_user),
    norms: AnalysisNormsService = Depends(get_analysis_norms_service),
) -> list[AnalysisParameterSummary]:
    summaries = await norms.search(search, limit=limit)
    return [
        AnalysisParameterSummary(
            code=s.code, name_ru=s.name_ru, unit=s.unit, category=s.category
        )
        for s in summaries
    ]


@dict_router.get(
    "/analysis-parameters/{code}",
    response_model=AnalysisParameterDetail,
)
async def get_parameter_detail(
    code: str,
    gender: str = Query(default="any"),
    age: int = Query(default=18, ge=0, le=150),
    _current_user: User = Depends(get_current_user),
    norms: AnalysisNormsService = Depends(get_analysis_norms_service),
) -> AnalysisParameterDetail:
    param = norms.get(code)
    if param is None:
        raise HTTPException(status_code=404, detail="parameter_not_found")
    norm = norms.get_norm(code, gender=gender, age=age)
    return AnalysisParameterDetail(
        code=param.code,
        name_ru=param.name_ru,
        name_en=param.name_en,
        unit=param.unit,
        alternative_units=param.alternative_units,
        category=param.category,
        description=param.description,
        synonyms=param.synonyms,
        applicable_norm=(
            AnalysisParameterNorm(
                min=norm.min,
                max=norm.max,
                gender=norm.gender,
                age_from=norm.age_from,
                age_to=norm.age_to,
            )
            if norm is not None
            else None
        ),
    )
