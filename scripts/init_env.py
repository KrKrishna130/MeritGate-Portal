#!/usr/bin/env python3
"""Create local secrets once. Never overwrite an existing configuration."""
import pathlib
import secrets

root = pathlib.Path(__file__).resolve().parents[1]
path = root / '.env'
if path.exists():
    raise SystemExit('.env already exists; edit it directly. Nothing was overwritten.')
values = {
    'SECRET_KEY': secrets.token_hex(32),
    'POSTGRES_PASSWORD': secrets.token_hex(24),
    'REDIS_PASSWORD': secrets.token_hex(24),
    'ADMIN_PASSWORD': secrets.token_urlsafe(18),
    'DEMO_CANDIDATE_PASSWORD': secrets.token_urlsafe(18),
    'MINIO_SECRET_KEY': secrets.token_urlsafe(24),
}
values['DATABASE_URL'] = f"postgresql+psycopg://exam:{values['POSTGRES_PASSWORD']}@postgres:5432/exam"
values['REDIS_URL'] = f"redis://:{values['REDIS_PASSWORD']}@redis:6379/0"
lines = []
for line in (root / '.env.example').read_text().splitlines():
    key = line.split('=', 1)[0]
    lines.append(f'{key}={values[key]}' if key in values else line)
with path.open('x') as f:
    f.write('\n'.join(lines) + '\n')
path.chmod(0o600)
print('Created .env with independent random secrets. Read ADMIN_PASSWORD and DEMO_CANDIDATE_PASSWORD there.')
