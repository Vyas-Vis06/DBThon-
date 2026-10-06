"""Deterministic demo data. Idempotent, development-only.

* Static rows come from database/seeds/*.sql (natural-key ON CONFLICT DO NOTHING, run in file order).
* Demo logins are created here because they need a bcrypt hash. The password is supplied by the caller
  (environment or a generated value); it is never stored in source control.
"""

from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

from .security import hash_password

SEED_DIR = Path(__file__).resolve().parents[2] / "database" / "seeds"
EMAIL_DOMAIN = "zeroentry.example"  # reserved example domain: never routable

# (login, role, display name, scope). Scope keys: ulb name, contractor licence, worker NAMASTE id.
DEMO_USERS: list[tuple[str, str, str, dict[str, str]]] = [
    ("admin", "ADMIN", "Asha Admin", {}),
    ("engineer", "ENGINEER", "Meera Engineer (RSA)", {"ulb": "GCC Zone 13 - Adyar"}),
    ("supervisor", "SUPERVISOR", "Karthik Supervisor", {"ulb": "GCC Zone 13 - Adyar"}),
    ("worker", "WORKER", "Murugan A. (worker login)", {"worker": "NAM-TN-100001"}),
    ("contractor", "CONTRACTOR", "Marina Sanitation (office)", {"contractor": "TN-SAN-2026-001"}),
    ("auditor", "AUDITOR", "Vikram Auditor", {}),
]


def to_psycopg_dsn(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def run_seed(owner_url: str, password: str, *, app_env: str = "development", bcrypt_rounds: int = 12) -> dict[str, int]:
    """Apply all seed files and demo users; returns row counts. Raises on production or a weak password."""
    if app_env == "production":
        raise RuntimeError("Refusing to seed demo data when APP_ENV=production.")
    if "CHANGE_ME" in password:
        raise ValueError("SEED_USER_PASSWORD still holds the CHANGE_ME placeholder; set a real value.")
    hash_password(password, rounds=4)  # fail fast (before touching the database) on a weak password

    files = sorted(SEED_DIR.glob("*.sql"))
    base, scenarios = [f for f in files if f.name < "02"], [f for f in files if f.name >= "02"]
    with psycopg.connect(to_psycopg_dsn(owner_url)) as conn:  # one transaction: all or nothing
        for path in base:
            conn.execute(path.read_text(encoding="utf-8"))
        for login, role, name, scope in DEMO_USERS:
            conn.execute(
                """
                INSERT INTO app_user (role_id, ulb_id, contractor_id, worker_id, email, full_name, password_hash)
                SELECT r.role_id,
                       (SELECT ulb_id        FROM ulb        WHERE name       = %(ulb)s),
                       (SELECT contractor_id FROM contractor WHERE licence_no = %(lic)s),
                       (SELECT worker_id     FROM worker     WHERE namaste_id = %(nam)s),
                       %(email)s, %(name)s, %(hash)s
                FROM role r WHERE r.name = %(role)s
                ON CONFLICT (email) DO NOTHING
                """,
                {"ulb": scope.get("ulb"), "lic": scope.get("contractor"), "nam": scope.get("worker"),
                 "email": f"{login}@{EMAIL_DOMAIN}", "name": name, "role": role,
                 "hash": hash_password(password, rounds=bcrypt_rounds)},
            )
        for path in scenarios:                       # scenarios need the demo users (engineer, supervisor) to exist
            conn.execute(path.read_text(encoding="utf-8"))
        counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608 - fixed table names
                  for t in ("ulb", "manhole", "contractor", "worker", "machine", "gas_detector", "app_user")}
    return counts
