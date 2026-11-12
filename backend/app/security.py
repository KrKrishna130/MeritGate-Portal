import base64
import hashlib
import hmac
import secrets


def password_hash(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return base64.b64encode(salt + key).decode()


def password_ok(password, encoded):
    try:
        raw = base64.b64decode(encoded)
        key = hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1)
        return hmac.compare_digest(key, raw[16:])
    except (ValueError, TypeError):
        return False


def binding(client):
    return hashlib.sha256(str(client).encode()).hexdigest()
