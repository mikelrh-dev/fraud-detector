#!/usr/bin/env python
"""Create admin user for fraud-detector."""

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.security import hash_password

user_id = str(uuid4())
hashed = hash_password("admin123")

sql = f"""INSERT INTO users (id, username, email, hashed_password, role, is_active, created_at, updated_at)
VALUES ('{user_id}', 'admin', 'admin@frauddetector.dev', '{hashed}', 'admin', true, NOW(), NOW());"""

print(sql)
