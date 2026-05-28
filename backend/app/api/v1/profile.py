"""Patient profile + sub-collections REST API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import (
    get_allergies_service,
    get_chronic_conditions_service,
    get_current_user,
    get_family_history_service,
    get_patient_profile_service,
)
from app.models.user import User
from app.schemas.profile import (
    AllergyCreate,
    AllergyResponse,
    AllergyUpdate,
    ChronicConditionCreate,
    ChronicConditionResponse,
    ChronicConditionUpdate,
    FamilyHistoryCreate,
    FamilyHistoryResponse,
    FamilyHistoryUpdate,
    PatientProfileCreate,
    PatientProfileResponse,
    PatientProfileUpdate,
    WeightRecordCreate,
    WeightRecordResponse,
)
from app.services.allergies_service import AllergiesService, AllergyNotFoundError
from app.services.chronic_conditions_service import (
    ChronicConditionNotFoundError,
    ChronicConditionsService,
)
from app.services.family_history_service import (
    FamilyHistoryNotFoundError,
    FamilyHistoryService,
)
from app.services.patient_profile_service import (
    PatientProfileService,
    ProfileAlreadyExistsError,
    ProfileNotFoundError,
)

router = APIRouter(prefix="/v1/profile", tags=["profile"])


# ---------- Profile -------------------------------------------------------- #


@router.get("", response_model=PatientProfileResponse)
async def read_profile(
    current_user: User = Depends(get_current_user),
    svc: PatientProfileService = Depends(get_patient_profile_service),
) -> PatientProfileResponse:
    try:
        return await svc.get_profile(current_user.id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="profile_not_found") from exc


@router.post("", response_model=PatientProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    data: PatientProfileCreate,
    current_user: User = Depends(get_current_user),
    svc: PatientProfileService = Depends(get_patient_profile_service),
) -> PatientProfileResponse:
    try:
        return await svc.create_profile(current_user.id, data)
    except ProfileAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="profile_already_exists") from exc


@router.patch("", response_model=PatientProfileResponse)
async def update_profile(
    data: PatientProfileUpdate,
    current_user: User = Depends(get_current_user),
    svc: PatientProfileService = Depends(get_patient_profile_service),
) -> PatientProfileResponse:
    try:
        return await svc.update_profile(current_user.id, data)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="profile_not_found") from exc


# ---------- Weight history ------------------------------------------------ #


@router.get("/weight-history", response_model=list[WeightRecordResponse])
async def list_weight_history(
    current_user: User = Depends(get_current_user),
    svc: PatientProfileService = Depends(get_patient_profile_service),
) -> list[WeightRecordResponse]:
    return await svc.list_weight_history(current_user.id)


@router.post(
    "/weight-history",
    response_model=WeightRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_weight_record(
    data: WeightRecordCreate,
    current_user: User = Depends(get_current_user),
    svc: PatientProfileService = Depends(get_patient_profile_service),
) -> WeightRecordResponse:
    return await svc.add_weight_record(current_user.id, data)


# ---------- Chronic conditions -------------------------------------------- #


@router.get("/chronic-conditions", response_model=list[ChronicConditionResponse])
async def list_chronic_conditions(
    current_user: User = Depends(get_current_user),
    svc: ChronicConditionsService = Depends(get_chronic_conditions_service),
) -> list[ChronicConditionResponse]:
    return await svc.list_for_user(current_user.id)


@router.post(
    "/chronic-conditions",
    response_model=ChronicConditionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chronic_condition(
    data: ChronicConditionCreate,
    current_user: User = Depends(get_current_user),
    svc: ChronicConditionsService = Depends(get_chronic_conditions_service),
) -> ChronicConditionResponse:
    return await svc.create(current_user.id, data)


@router.patch(
    "/chronic-conditions/{condition_id}", response_model=ChronicConditionResponse
)
async def update_chronic_condition(
    condition_id: int,
    data: ChronicConditionUpdate,
    current_user: User = Depends(get_current_user),
    svc: ChronicConditionsService = Depends(get_chronic_conditions_service),
) -> ChronicConditionResponse:
    try:
        return await svc.update(current_user.id, condition_id, data)
    except ChronicConditionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="chronic_condition_not_found") from exc


@router.delete(
    "/chronic-conditions/{condition_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_chronic_condition(
    condition_id: int,
    current_user: User = Depends(get_current_user),
    svc: ChronicConditionsService = Depends(get_chronic_conditions_service),
) -> None:
    try:
        await svc.delete(current_user.id, condition_id)
    except ChronicConditionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="chronic_condition_not_found") from exc


# ---------- Allergies ----------------------------------------------------- #


@router.get("/allergies", response_model=list[AllergyResponse])
async def list_allergies(
    current_user: User = Depends(get_current_user),
    svc: AllergiesService = Depends(get_allergies_service),
) -> list[AllergyResponse]:
    return await svc.list_for_user(current_user.id)


@router.post(
    "/allergies", response_model=AllergyResponse, status_code=status.HTTP_201_CREATED
)
async def create_allergy(
    data: AllergyCreate,
    current_user: User = Depends(get_current_user),
    svc: AllergiesService = Depends(get_allergies_service),
) -> AllergyResponse:
    return await svc.create(current_user.id, data)


@router.patch("/allergies/{allergy_id}", response_model=AllergyResponse)
async def update_allergy(
    allergy_id: int,
    data: AllergyUpdate,
    current_user: User = Depends(get_current_user),
    svc: AllergiesService = Depends(get_allergies_service),
) -> AllergyResponse:
    try:
        return await svc.update(current_user.id, allergy_id, data)
    except AllergyNotFoundError as exc:
        raise HTTPException(status_code=404, detail="allergy_not_found") from exc


@router.delete("/allergies/{allergy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_allergy(
    allergy_id: int,
    current_user: User = Depends(get_current_user),
    svc: AllergiesService = Depends(get_allergies_service),
) -> None:
    try:
        await svc.delete(current_user.id, allergy_id)
    except AllergyNotFoundError as exc:
        raise HTTPException(status_code=404, detail="allergy_not_found") from exc


# ---------- Family history ------------------------------------------------ #


@router.get("/family-history", response_model=list[FamilyHistoryResponse])
async def list_family_history(
    current_user: User = Depends(get_current_user),
    svc: FamilyHistoryService = Depends(get_family_history_service),
) -> list[FamilyHistoryResponse]:
    return await svc.list_for_user(current_user.id)


@router.post(
    "/family-history",
    response_model=FamilyHistoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_family_history(
    data: FamilyHistoryCreate,
    current_user: User = Depends(get_current_user),
    svc: FamilyHistoryService = Depends(get_family_history_service),
) -> FamilyHistoryResponse:
    return await svc.create(current_user.id, data)


@router.patch("/family-history/{record_id}", response_model=FamilyHistoryResponse)
async def update_family_history(
    record_id: int,
    data: FamilyHistoryUpdate,
    current_user: User = Depends(get_current_user),
    svc: FamilyHistoryService = Depends(get_family_history_service),
) -> FamilyHistoryResponse:
    try:
        return await svc.update(current_user.id, record_id, data)
    except FamilyHistoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="family_history_not_found") from exc


@router.delete("/family-history/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_family_history(
    record_id: int,
    current_user: User = Depends(get_current_user),
    svc: FamilyHistoryService = Depends(get_family_history_service),
) -> None:
    try:
        await svc.delete(current_user.id, record_id)
    except FamilyHistoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="family_history_not_found") from exc
