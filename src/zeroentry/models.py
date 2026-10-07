"""SQLAlchemy 2.0 models mapped onto the SQL-defined schema.

The migrations in database/migrations/sql/ own the schema (constraints, triggers, functions, policies);
these classes only *map* it, and `create_all()` is never called. `tests/db/test_models_match_schema.py` fails
when a table, column, nullability, primary key or foreign key here drifts from the migrated database.

`DB` marks values the database produces itself (identity keys' siblings: DEFAULT now(), status defaults), so
the ORM reads them back after INSERT instead of leaving them empty.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (BigInteger, Boolean, Date, DateTime, FetchedValue, ForeignKey, ForeignKeyConstraint,
                        Integer, LargeBinary, Numeric, SmallInteger, Text)
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, Range
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TS = DateTime(timezone=True)
DB = FetchedValue()


class Base(DeclarativeBase):
    pass


def _pk(type_=BigInteger):
    return mapped_column(type_, primary_key=True)


def _fk(target: str, nullable: bool = False, type_=BigInteger):
    return mapped_column(type_, ForeignKey(target), nullable=nullable)


# --- identity and access ----------------------------------------------------------------------------
class Role(Base):
    __tablename__ = "role"
    role_id: Mapped[int] = _pk(SmallInteger)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)


class Ulb(Base):
    __tablename__ = "ulb"
    ulb_id: Mapped[int] = _pk()
    name: Mapped[str] = mapped_column(Text)
    district: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)


class Contractor(Base):
    __tablename__ = "contractor"
    contractor_id: Mapped[int] = _pk()
    name: Mapped[str] = mapped_column(Text)
    licence_no: Mapped[str] = mapped_column(Text)
    licence_valid_until: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=DB)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


class Worker(Base):
    __tablename__ = "worker"
    worker_id: Mapped[int] = _pk()
    contractor_id: Mapped[int] = _fk("contractor.contractor_id")
    full_name: Mapped[str] = mapped_column(Text)
    namaste_id: Mapped[str] = mapped_column(Text)
    medical_fit_until: Mapped[date] = mapped_column(Date)
    trained_until: Mapped[date] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=DB)


class AppUser(Base):
    __tablename__ = "app_user"
    user_id: Mapped[int] = _pk()
    role_id: Mapped[int] = _fk("role.role_id", type_=SmallInteger)
    ulb_id: Mapped[int | None] = _fk("ulb.ulb_id", nullable=True)
    contractor_id: Mapped[int | None] = _fk("contractor.contractor_id", nullable=True)
    worker_id: Mapped[int | None] = _fk("worker.worker_id", nullable=True)
    email: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=DB)
    failed_logins: Mapped[int] = mapped_column(SmallInteger, server_default=DB)
    locked_until: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


class UserSession(Base):
    __tablename__ = "user_session"
    session_id: Mapped[int] = _pk()
    user_id: Mapped[int] = _fk("app_user.user_id")
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    csrf_token: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    expires_at: Mapped[datetime] = mapped_column(TS)
    revoked_at: Mapped[datetime | None] = mapped_column(TS)


# --- assets, complaints, jobs ----------------------------------------------------------------------
class Manhole(Base):
    __tablename__ = "manhole"
    manhole_id: Mapped[int] = _pk()
    ulb_id: Mapped[int] = _fk("ulb.ulb_id")
    code: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    depth_m: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    address: Mapped[str | None] = mapped_column(Text)


class ResolutionType(Base):
    __tablename__ = "resolution_type"
    code: Mapped[str] = _pk(Text)
    description: Mapped[str] = mapped_column(Text)
    requires_evidence: Mapped[bool] = mapped_column(Boolean)


class Complaint(Base):
    __tablename__ = "complaint"
    complaint_id: Mapped[int] = _pk()
    manhole_id: Mapped[int] = _fk("manhole.manhole_id")
    description: Mapped[str] = mapped_column(Text)
    raised_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    status: Mapped[str] = mapped_column(Text, server_default=DB)
    resolved_at: Mapped[datetime | None] = mapped_column(TS)
    resolution_code: Mapped[str | None] = mapped_column(Text, ForeignKey("resolution_type.code"))
    resolved_by: Mapped[int | None] = _fk("app_user.user_id", nullable=True)


class Machine(Base):
    __tablename__ = "machine"
    machine_id: Mapped[int] = _pk()
    ulb_id: Mapped[int] = _fk("ulb.ulb_id")
    code: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=DB)


class Job(Base):
    __tablename__ = "job"
    job_id: Mapped[int] = _pk()
    complaint_id: Mapped[int] = _fk("complaint.complaint_id")
    contractor_id: Mapped[int] = _fk("contractor.contractor_id")
    method: Mapped[str] = mapped_column(Text, server_default=DB)
    status: Mapped[str] = mapped_column(Text, server_default=DB)
    created_by: Mapped[int | None] = _fk("app_user.user_id", nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


class MachineDeployment(Base):
    __tablename__ = "machine_deployment"
    deploy_id: Mapped[int] = _pk()
    job_id: Mapped[int] = _fk("job.job_id")
    machine_id: Mapped[int] = _fk("machine.machine_id")
    started_at: Mapped[datetime] = mapped_column(TS)
    ended_at: Mapped[datetime | None] = mapped_column(TS)
    outcome: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[int | None] = _fk("app_user.user_id", nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    outcome_recorded_at: Mapped[datetime | None] = mapped_column(TS, server_default=DB, server_onupdate=DB)


class MechanisationWaiver(Base):
    __tablename__ = "mechanisation_waiver"
    waiver_id: Mapped[int] = _pk()
    job_id: Mapped[int] = _fk("job.job_id")
    reason_code: Mapped[str] = mapped_column(Text)
    justification: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[int] = _fk("app_user.user_id")
    approved_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


# --- entry permits ---------------------------------------------------------------------------------
class EntryPermit(Base):
    __tablename__ = "entry_permit"
    permit_id: Mapped[int] = _pk()
    job_id: Mapped[int] = _fk("job.job_id")
    supervisor_id: Mapped[int] = _fk("app_user.user_id")
    status: Mapped[str] = mapped_column(Text, server_default=DB)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    authorised_at: Mapped[datetime | None] = mapped_column(TS)
    authorised_by: Mapped[int | None] = _fk("app_user.user_id", nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(TS)
    ended_at: Mapped[datetime | None] = mapped_column(TS)
    end_reason: Mapped[str | None] = mapped_column(Text)


class PermitCrew(Base):
    __tablename__ = "permit_crew"
    permit_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("entry_permit.permit_id"), primary_key=True)
    worker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("worker.worker_id"), primary_key=True)
    crew_role: Mapped[str] = mapped_column(Text)


class GearItem(Base):
    __tablename__ = "gear_item"
    gear_code: Mapped[str] = _pk(Text)
    name: Mapped[str] = mapped_column(Text)
    statutory: Mapped[bool] = mapped_column(Boolean, server_default=DB)
    legal_ref: Mapped[str | None] = mapped_column(Text)


class GearIssue(Base):
    __tablename__ = "gear_issue"
    __table_args__ = (ForeignKeyConstraint(["permit_id", "worker_id"], ["permit_crew.permit_id", "permit_crew.worker_id"]),)
    issue_id: Mapped[int] = _pk()
    permit_id: Mapped[int] = mapped_column(BigInteger)
    worker_id: Mapped[int] = mapped_column(BigInteger)
    gear_code: Mapped[str] = mapped_column(Text, ForeignKey("gear_item.gear_code"))
    serial_no: Mapped[str] = mapped_column(Text)
    issued_by: Mapped[int | None] = _fk("app_user.user_id", nullable=True)
    issued_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


class GasDetector(Base):
    __tablename__ = "gas_detector"
    detector_id: Mapped[int] = _pk()
    serial_no: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    calibration_valid_until: Mapped[date] = mapped_column(Date)


class GasReading(Base):
    __tablename__ = "gas_reading"
    reading_id: Mapped[int] = _pk()
    permit_id: Mapped[int] = _fk("entry_permit.permit_id")
    detector_id: Mapped[int] = _fk("gas_detector.detector_id")
    depth_level: Mapped[str] = mapped_column(Text)
    o2_pct: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    h2s_ppm: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    lel_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    co_ppm: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    taken_at: Mapped[datetime] = mapped_column(TS)
    recorded_by: Mapped[int] = _fk("app_user.user_id")
    recorded_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


class EntryLog(Base):
    __tablename__ = "entry_log"
    __table_args__ = (ForeignKeyConstraint(["permit_id", "worker_id"], ["permit_crew.permit_id", "permit_crew.worker_id"]),)
    entry_id: Mapped[int] = _pk()
    permit_id: Mapped[int] = mapped_column(BigInteger)
    worker_id: Mapped[int] = mapped_column(BigInteger)
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE)
    recorded_by: Mapped[int] = _fk("app_user.user_id")
    recorded_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    exit_recorded_at: Mapped[datetime | None] = mapped_column(TS, server_default=DB, server_onupdate=DB)


# --- consequences ----------------------------------------------------------------------------------
class Incident(Base):
    __tablename__ = "incident"
    __table_args__ = (
        ForeignKeyConstraint(["permit_id", "job_id"], ["entry_permit.permit_id", "entry_permit.job_id"]),
        ForeignKeyConstraint(["permit_id", "worker_id"], ["permit_crew.permit_id", "permit_crew.worker_id"]),
    )
    incident_id: Mapped[int] = _pk()
    incident_type: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(TS)
    manhole_id: Mapped[int] = _fk("manhole.manhole_id")
    worker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("worker.worker_id"))
    contractor_id: Mapped[int] = _fk("contractor.contractor_id")
    job_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("job.job_id"))
    permit_id: Mapped[int | None] = mapped_column(BigInteger)
    description: Mapped[str] = mapped_column(Text)
    recorded_by: Mapped[int] = _fk("app_user.user_id")
    recorded_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


class CompensationCase(Base):
    __tablename__ = "compensation_case"
    case_id: Mapped[int] = _pk()
    incident_id: Mapped[int] = _fk("incident.incident_id")
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=DB)
    due_by: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default=DB)
    opened_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    paid_at: Mapped[datetime | None] = mapped_column(TS)


class Invoice(Base):
    __tablename__ = "invoice"
    invoice_id: Mapped[int] = _pk()
    job_id: Mapped[int] = _fk("job.job_id")
    invoice_no: Mapped[str] = mapped_column(Text)
    amount_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(Text, server_default=DB)
    submitted_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    decided_by: Mapped[int | None] = _fk("app_user.user_id", nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(TS)
    paid_at: Mapped[datetime | None] = mapped_column(TS)


class InvoiceHold(Base):
    __tablename__ = "invoice_hold"
    hold_id: Mapped[int] = _pk()
    invoice_id: Mapped[int] = _fk("invoice.invoice_id")
    reason: Mapped[str] = mapped_column(Text)
    alert_id: Mapped[int | None] = _fk("shadow_entry_alert.alert_id", nullable=True)
    incident_id: Mapped[int | None] = _fk("incident.incident_id", nullable=True)
    placed_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    released_at: Mapped[datetime | None] = mapped_column(TS)
    released_by: Mapped[int | None] = _fk("app_user.user_id", nullable=True)
    release_note: Mapped[str | None] = mapped_column(Text)


# --- detection by absence --------------------------------------------------------------------------
class DetectionRule(Base):
    __tablename__ = "detection_rule"
    rule_code: Mapped[str] = _pk(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=DB)


class ShadowEntryAlert(Base):
    __tablename__ = "shadow_entry_alert"
    alert_id: Mapped[int] = _pk()
    complaint_id: Mapped[int] = _fk("complaint.complaint_id")
    rule_code: Mapped[str] = mapped_column(Text, ForeignKey("detection_rule.rule_code"))
    contractor_id: Mapped[int | None] = _fk("contractor.contractor_id", nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default=DB)
    reason: Mapped[str] = mapped_column(Text)
    evidence_deadline: Mapped[datetime] = mapped_column(TS)
    detected_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    last_evaluated_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    reviewed_by: Mapped[int | None] = _fk("app_user.user_id", nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TS)
    review_note: Mapped[str | None] = mapped_column(Text)


class ShadowEntryAlertEvent(Base):
    __tablename__ = "shadow_entry_alert_event"
    event_id: Mapped[int] = _pk()
    alert_id: Mapped[int] = _fk("shadow_entry_alert.alert_id")
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[int | None] = _fk("app_user.user_id", nullable=True)
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


# --- law as data, audit ----------------------------------------------------------------------------
class RuleParameter(Base):
    __tablename__ = "rule_parameter"
    param_key: Mapped[str] = _pk(Text)
    value: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    legal_ref: Mapped[str] = mapped_column(Text)
    is_assumption: Mapped[bool] = mapped_column(Boolean, server_default=DB)
    updated_by: Mapped[int | None] = _fk("app_user.user_id", nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    revision: Mapped[int] = mapped_column(Integer, server_default=DB, server_onupdate=DB)
    source_code: Mapped[str] = _fk("policy_source.source_code", type_=Text)


class PolicySource(Base):
    __tablename__ = "policy_source"
    source_code: Mapped[str] = _pk(Text)
    source_type: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_version: Mapped[str] = mapped_column(Text)
    citation_clause: Mapped[str] = mapped_column(Text)
    applicability: Mapped[str] = mapped_column(Text)


class LegalClauseSource(Base):
    __tablename__ = "legal_clause_source"
    clause_code: Mapped[str] = mapped_column(Text, ForeignKey("legal_clause.clause_code"), primary_key=True)
    source_code: Mapped[str] = mapped_column(Text, ForeignKey("policy_source.source_code"), primary_key=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger)


class RuleParameterHistory(Base):
    __tablename__ = "rule_parameter_history"
    history_id: Mapped[int] = _pk()
    param_key: Mapped[str] = _fk("rule_parameter.param_key", type_=Text)
    revision: Mapped[int] = mapped_column(Integer)
    value: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    legal_ref: Mapped[str] = mapped_column(Text)
    is_assumption: Mapped[bool] = mapped_column(Boolean)
    source_code: Mapped[str] = _fk("policy_source.source_code", type_=Text)
    effective_at: Mapped[datetime] = mapped_column(TS)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    change_reason: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


class PermitAuthorizationDecision(Base):
    __tablename__ = "permit_authorization_decision"
    decision_id: Mapped[int] = _pk()
    permit_id: Mapped[int] = _fk("entry_permit.permit_id")
    decision_kind: Mapped[str] = mapped_column(Text)
    decision_at: Mapped[datetime] = mapped_column(TS)
    actor_user_id: Mapped[int] = mapped_column(BigInteger)
    snapshot_format: Mapped[int] = mapped_column(SmallInteger, server_default=DB)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    snapshot_sha256: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


class PermitSafetyEvent(Base):
    __tablename__ = "permit_safety_event"
    event_id: Mapped[int] = _pk()
    permit_id: Mapped[int] = _fk("entry_permit.permit_id")
    entry_id: Mapped[int | None] = _fk("entry_log.entry_id", nullable=True)
    event_key: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    reason_code: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(TS, server_default=DB)


class LegalClause(Base):
    __tablename__ = "legal_clause"
    clause_code: Mapped[str] = _pk(Text)
    title: Mapped[str] = mapped_column(Text)
    legal_ref: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(SmallInteger)


class AuditLog(Base):
    __tablename__ = "audit_log"
    log_id: Mapped[int] = _pk()
    occurred_at: Mapped[datetime] = mapped_column(TS, server_default=DB)
    actor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(Text)
    table_name: Mapped[str] = mapped_column(Text)
    row_pk: Mapped[str] = mapped_column(Text)
    old_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
