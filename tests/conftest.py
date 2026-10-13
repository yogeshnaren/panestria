"""Load test-only stack helpers before integration/e2e collection."""

from stack_support import COMPOSE, DATABASE_URL

# Importing from this directory also makes stack_support available when pytest
# collects only an e2e or integration node. Neither application imports this file.
assert "panestria-r0-tests-" in COMPOSE[-1] and ":55440/" in DATABASE_URL
