-- 0008_hardening.sql
-- Least privilege for the runtime role ze_app. Triggers already forbid these changes for everyone but a
-- superuser; REVOKE adds a second, independent wall (and column-level UPDATE shrinks what a bug could touch).
-- Everything not mentioned keeps the default SELECT/INSERT/UPDATE/DELETE granted in 0001.

-- Reference data changes through migrations only. The two admin-editable tables expose a single column set.
REVOKE INSERT, UPDATE, DELETE ON role, legal_clause, resolution_type FROM ze_app;
REVOKE INSERT, UPDATE, DELETE ON detection_rule, rule_parameter FROM ze_app;
GRANT UPDATE (enabled)                        ON detection_rule TO ze_app;
GRANT UPDATE (value, updated_by, updated_at)  ON rule_parameter TO ze_app;

-- Append-only evidence: no UPDATE, no DELETE.
REVOKE UPDATE, DELETE ON audit_log, gas_reading, mechanisation_waiver, incident, shadow_entry_alert_event FROM ze_app;

-- Evidence that is never deleted, and may only change in the one way the workflow needs.
REVOKE DELETE ON entry_log, compensation_case, shadow_entry_alert, invoice_hold FROM ze_app;
REVOKE UPDATE ON entry_log, compensation_case, shadow_entry_alert, invoice_hold FROM ze_app;
GRANT UPDATE (period)                                                                ON entry_log         TO ze_app;
GRANT UPDATE (amount_paid, status, paid_at)                                          ON compensation_case TO ze_app;
GRANT UPDATE (status, last_evaluated_at, reviewed_by, reviewed_at, review_note)      ON shadow_entry_alert TO ze_app;
GRANT UPDATE (released_at, released_by, release_note)                                ON invoice_hold      TO ze_app;
