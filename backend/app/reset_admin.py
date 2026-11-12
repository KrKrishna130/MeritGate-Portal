"""Explicit local administrator recovery. Reads credentials from container env."""
import os
from sqlalchemy import select
from .main import SessionLocal
from .models import User
from .security import password_hash

name = os.getenv('ADMIN_USERNAME', 'admin').lower()
pw = os.getenv('ADMIN_PASSWORD', '')
if len(pw) < 12:
    raise SystemExit('Set ADMIN_PASSWORD to at least 12 characters first.')
with SessionLocal() as s:
    user = s.scalar(select(User).where(User.username == name, User.role == 'admin').with_for_update())
    if not user:
        raise SystemExit('Bootstrap administrator not found.')
    user.password_hash = password_hash(pw)
    user.session_id = None
    s.commit()
print('Bootstrap administrator password reset; existing admin sessions revoked.')
