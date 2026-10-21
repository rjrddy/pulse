"""Generate an ignored collector credential file from the local environment."""

import os
from pathlib import Path

p = Path("deploy/.pulse-token")
p.write_text(os.environ["PULSE_TOKEN"])
p.chmod(0o600)
