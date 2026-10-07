"""Request bodies. Every one forbids unknown fields (no mass assignment) and validates at the API boundary;
the database re-checks everything that matters (constraints and triggers), so this layer is for good messages."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

Name = Annotated[str, Field(min_length=1, max_length=200)]
Text = Annotated[str, Field(min_length=1, max_length=2000)]
Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Pct = Annotated[Decimal, Field(ge=0, le=100, max_digits=6, decimal_places=2)]
NonNeg = Annotated[Decimal, Field(ge=0, max_digits=8, decimal_places=2)]

Role = Literal["ADMIN", "ENGINEER", "SUPERVISOR", "WORKER", "CONTRACTOR", "AUDITOR"]
CrewRole = Literal["ENTRANT", "STANDBY", "SUPERVISOR"]
Depth = Literal["TOP", "MID", "BOTTOM"]
ResolutionCode = Literal["CLEARED", "NO_BLOCKAGE_FOUND", "DUPLICATE_COMPLAINT", "REFERRED_OUT", "WITHDRAWN"]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def partial(model: type[BaseModel], name: str) -> type[BaseModel]:
    """An all-optional copy of `model` for PATCH bodies (only fields actually sent are applied)."""
    fields = {k: (Optional[f.annotation], None) for k, f in model.model_fields.items()}
    return create_model(name, __base__=In, **fields)


def _not_future(value: datetime | None) -> datetime | None:
    if value is not None:
        if value.tzinfo is None:
            raise ValueError("Give the time with its UTC offset, for example 2026-10-07T10:30:00+05:30.")
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("This time is in the future.")
    return value


# --- auth / users ----------------------------------------------------------------------------------------------
class LoginIn(In):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=200)]


class ChangePasswordIn(In):
    current_password: Annotated[str, Field(min_length=1, max_length=200)]
    new_password: Annotated[str, Field(min_length=1, max_length=200)]


class UserCreateIn(In):
    email: Annotated[str, Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
    full_name: Name
    role: Role
    password: Annotated[str, Field(min_length=1, max_length=200)]
    ulb_id: int | None = None
    contractor_id: int | None = None
    worker_id: int | None = None

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserUpdateIn(In):
    full_name: Name | None = None
    role: Role | None = None
    is_active: bool | None = None
    ulb_id: int | None = None
    contractor_id: int | None = None
    worker_id: int | None = None
    unlock: bool = False
    new_password: Annotated[str, Field(min_length=1, max_length=200)] | None = None


# --- reference data ----------------------------------------------------------------------------------------------
class UlbIn(In):
    name: Name
    district: Name
    state: Name


class ManholeIn(In):
    ulb_id: int
    code: Annotated[str, Field(min_length=1, max_length=40)]
    kind: Literal["SEWER", "SEPTIC"]
    depth_m: Annotated[Decimal, Field(gt=0, le=60, max_digits=5, decimal_places=2)]
    lat: Annotated[Decimal, Field(ge=-90, le=90)]
    lng: Annotated[Decimal, Field(ge=-180, le=180)]
    address: str | None = Field(None, max_length=300)


class MachineIn(In):
    ulb_id: int
    code: Annotated[str, Field(min_length=1, max_length=40)]
    kind: Literal["JETTING", "SUCTION", "ROBOT"]
    status: Literal["AVAILABLE", "IN_USE", "MAINTENANCE"] = "AVAILABLE"


class GearItemIn(In):
    gear_code: Annotated[str, Field(pattern=r"^[A-Z0-9_]{2,40}$")]
    name: Name
    statutory: bool = False
    legal_ref: str | None = Field(None, max_length=300)


class DetectorIn(In):
    serial_no: Annotated[str, Field(min_length=1, max_length=60)]
    model: Name
    calibration_valid_until: date


class ContractorIn(In):
    name: Name
    licence_no: Annotated[str, Field(min_length=1, max_length=60)]
    licence_valid_until: date
    status: Literal["ACTIVE", "SUSPENDED", "BLACKLISTED"] = "ACTIVE"


class WorkerIn(In):
    contractor_id: int
    full_name: Name
    namaste_id: Annotated[str, Field(min_length=3, max_length=40)]
    medical_fit_until: date
    trained_until: date
    is_active: bool = True


# --- complaints, jobs, waivers ------------------------------------------------------------------------------------
class ComplaintIn(In):
    manhole_id: int
    description: Text


class ComplaintPatch(In):
    description: Text


class ResolveIn(In):
    resolution_code: ResolutionCode


class JobIn(In):
    complaint_id: int
    contractor_id: int


class JobPatch(In):
    status: Literal["PLANNED", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED"]


class DeploymentIn(In):
    machine_id: int
    started_at: datetime
    ended_at: datetime | None = None
    outcome: Literal["CLEARED", "FAILED"] | None = None

    _past = field_validator("started_at", "ended_at")(_not_future)


class DeploymentFinishIn(In):
    ended_at: datetime
    outcome: Literal["CLEARED", "FAILED"]

    _past = field_validator("ended_at")(_not_future)


class WaiverIn(In):
    reason_code: Literal["MACHINE_FAILED", "NO_MACHINE_ACCESS", "STRUCTURAL_CONSTRAINT", "NO_MACHINE_AVAILABLE", "OTHER"]
    justification: Annotated[str, Field(min_length=50, max_length=2000)]


# --- permits ------------------------------------------------------------------------------------------------------
class PermitIn(In):
    job_id: int


class CrewIn(In):
    worker_id: int
    crew_role: CrewRole


class GearIssueIn(In):
    worker_id: int
    gear_code: Annotated[str, Field(pattern=r"^[A-Z0-9_]{2,40}$")]
    serial_no: Annotated[str, Field(min_length=1, max_length=60)]


class ReadingIn(In):
    detector_id: int
    depth_level: Depth
    o2_pct: Annotated[Decimal, Field(ge=0, le=100, max_digits=4, decimal_places=1)]
    h2s_ppm: NonNeg
    lel_pct: Pct
    co_ppm: NonNeg
    taken_at: datetime | None = None      # default: now (server clock); may only be a little in the past

    @field_validator("taken_at")
    @classmethod
    def _recent(cls, v: datetime | None) -> datetime | None:
        v = _not_future(v)
        if v is not None and v < datetime.now(timezone.utc) - timedelta(hours=1):
            raise ValueError("A reading older than one hour cannot be entered; take a new one.")
        return v


class EntryIn(In):
    worker_id: int
    entered_at: datetime
    exited_at: datetime | None = None

    @field_validator("entered_at", "exited_at")
    @classmethod
    def _tz(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("Give the time with its UTC offset, for example 2026-10-07T10:30:00+05:30.")
        return v


class ExitIn(In):
    exited_at: datetime

    @field_validator("exited_at")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Give the time with its UTC offset, for example 2026-10-07T10:30:00+05:30.")
        return v


class ReasonIn(In):
    reason: Annotated[str, Field(min_length=5, max_length=500)]


# --- consequences -------------------------------------------------------------------------------------------------
class IncidentIn(In):
    incident_type: Literal["FATALITY", "DISABILITY", "NEAR_MISS"]
    occurred_at: datetime
    worker_id: int
    manhole_id: int
    description: Text
    permit_id: int | None = None
    job_id: int | None = None

    _past = field_validator("occurred_at")(_not_future)


class PaymentIn(In):
    amount: Money


class InvoiceIn(In):
    job_id: int
    invoice_no: Annotated[str, Field(min_length=1, max_length=40)]
    amount_inr: Money


class NoteIn(In):
    note: Annotated[str, Field(min_length=10, max_length=1000)]


class ReviewIn(In):
    decision: Literal["CONFIRMED", "DISMISSED"]
    note: Annotated[str, Field(min_length=10, max_length=1000)]


class RuleValueIn(In):
    value: Decimal
    reason: Annotated[str, Field(min_length=10, max_length=1000)]


class RuleToggleIn(In):
    enabled: bool
