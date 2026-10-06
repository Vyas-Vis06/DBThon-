"""Read-only SQLAlchemy Core handles for the database views, so routers query them with the same typed, parameterised
API as the ORM tables. Separate MetaData: these are never created or reflected as tables (see test_models_match_schema)."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, MetaData, Numeric, SmallInteger, Table, Text, Date, Integer

metadata = MetaData()
TS = DateTime(timezone=True)


def _view(name: str, *columns: Column) -> Table:
    return Table(name, metadata, *columns)


v_suspected_shadow_entry = _view(
    "v_suspected_shadow_entry",
    Column("complaint_id", BigInteger), Column("rule_code", Text), Column("rule_title", Text),
    Column("manhole_id", BigInteger), Column("ulb_id", BigInteger), Column("contractor_id", BigInteger),
    Column("job_id", BigInteger), Column("anchor_at", TS), Column("evidence_deadline", TS), Column("past_grace", Boolean),
    Column("late_evidence_exists", Boolean), Column("reason", Text), Column("alert_id", BigInteger), Column("alert_status", Text))

v_compensation_overdue = _view(
    "v_compensation_overdue",
    Column("case_id", BigInteger), Column("incident_id", BigInteger), Column("incident_type", Text), Column("occurred_at", TS),
    Column("worker_id", BigInteger), Column("contractor_id", BigInteger), Column("contractor_name", Text), Column("ulb_id", BigInteger),
    Column("amount_due", Numeric), Column("amount_paid", Numeric), Column("amount_outstanding", Numeric),
    Column("due_by", Date), Column("days_overdue", Integer))

v_invoice_status = _view(
    "v_invoice_status",
    Column("invoice_id", BigInteger), Column("job_id", BigInteger), Column("contractor_id", BigInteger), Column("invoice_no", Text),
    Column("amount_inr", Numeric), Column("status", Text), Column("submitted_at", TS), Column("on_hold", Boolean),
    Column("hold_reasons", Text))

v_contractor_risk = _view(
    "v_contractor_risk",
    Column("contractor_id", BigInteger), Column("name", Text), Column("status", Text), Column("fatalities", BigInteger),
    Column("disabilities", BigInteger), Column("confirmed_alerts", BigInteger), Column("open_alerts", BigInteger),
    Column("overdue_cases", BigInteger), Column("risk_score", BigInteger))

v_ulb_year_kpi = _view(
    "v_ulb_year_kpi",
    Column("ulb_id", BigInteger), Column("ulb_name", Text), Column("year", Integer), Column("jobs", BigInteger),
    Column("mechanised_jobs", BigInteger), Column("manual_exception_jobs", BigInteger), Column("zero_entry_rate_pct", Numeric))

v_ulb_year_incidents = _view(
    "v_ulb_year_incidents",
    Column("ulb_id", BigInteger), Column("ulb_name", Text), Column("year", Integer), Column("incidents", BigInteger),
    Column("deaths", BigInteger), Column("compensation_due", Numeric), Column("compensation_paid", Numeric),
    Column("mean_days_to_compensation", Numeric))

v_permit_compliance = _view(
    "v_permit_compliance",
    Column("permit_id", BigInteger), Column("job_id", BigInteger), Column("supervisor_id", BigInteger),
    Column("clauses_total", BigInteger), Column("clauses_failed", BigInteger), Column("ready_to_authorise", Boolean),
    Column("failing_clauses", Text))
