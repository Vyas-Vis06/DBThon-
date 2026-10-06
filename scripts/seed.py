"""Load the deterministic demo data into the database named by MIGRATION_DATABASE_URL / DATABASE_URL.

    python scripts/seed.py            # needs SEED_USER_PASSWORD (12+ chars, mixed case, a digit)

Safe to run twice. Refuses when APP_ENV=production.
"""

import sys

from zeroentry.config import get_settings
from zeroentry.seed import run_seed


def main() -> int:
    settings = get_settings()
    if not settings.seed_user_password:
        print("Set SEED_USER_PASSWORD (12+ chars, mixed case, a digit) in .env or the environment.", file=sys.stderr)
        return 2
    counts = run_seed(settings.owner_database_url, settings.seed_user_password, app_env=settings.app_env)
    print("Seeded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
