#!/usr/bin/env python
"""Create admin user for fraud-detector.

Usage:
    python scripts/create_admin.py

The admin password is read from the ADMIN_PASSWORD environment variable.
If not set, the script prompts securely via getpass.
"""

import getpass
import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import settings
from src.core.security import hash_password

# Refuse to run against non-dev environments without explicit password
if settings.environment == "production":
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        print("ERROR: ADMIN_PASSWORD environment variable is required in production.")
        sys.exit(1)
else:
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        admin_password = getpass.getpass("Enter admin password: ")
        confirm = getpass.getpass("Confirm admin password: ")
        if admin_password != confirm:
            print("ERROR: Passwords do not match.")
            sys.exit(1)

if len(admin_password) < 12:
    print("ERROR: Admin password must be at least 12 characters.")
    sys.exit(1)

user_id = str(uuid4())
hashed = hash_password(admin_password)

sql = f"""INSERT INTO users (id, username, email, hashed_password, role, is_active, created_at, updated_at)
VALUES ('{user_id}', 'admin', 'admin@frauddetector.dev', '{hashed}', 'admin', true, NOW(), NOW());"""

print(sql)
