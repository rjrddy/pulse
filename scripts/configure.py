"""Create local credentials without displaying them."""

import secrets
from pathlib import Path

p = Path(".env")
if p.exists():
    raise SystemExit("Existing .env retained.")
p.write_text(
    "PULSE_PASSWORD="
    + secrets.token_urlsafe(24)
    + "\nPULSE_TOKEN="
    + secrets.token_urlsafe(32)
    + "\nPULSE_ORIGIN=http://localhost:8081\nPULSE_BUDGET_MS=40000\n"
)
p.chmod(0o600)
print("Created .env; open it locally for your operator password.")
