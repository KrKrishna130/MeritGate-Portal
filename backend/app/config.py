import os


def flag(key, default='false'):
    return os.getenv(key, default).lower() == 'true'


class Settings:
    app_name = os.getenv('APP_NAME', 'MeritGate Examination Portal')
    secret = os.getenv('SECRET_KEY', '')
    database_url = os.getenv('DATABASE_URL', 'postgresql+psycopg://exam:exam@postgres:5432/exam')
    redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    origins = os.getenv('CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')
    secure_cookie = flag('COOKIE_SECURE')
    session_hours = 12
    heartbeat_gap = int(os.getenv('HEARTBEAT_GAP_SECONDS', '60'))
    require_review = flag('REQUIRE_ADMIN_RESULT_REVIEW', 'true')
    review_threshold = int(os.getenv('REVIEW_EVENT_THRESHOLD', '3'))
    minio_endpoint = os.getenv('MINIO_ENDPOINT', 'minio:9000')
    minio_access = os.getenv('MINIO_ACCESS_KEY', '')
    minio_secret = os.getenv('MINIO_SECRET_KEY', '')
    minio_secure = flag('MINIO_SECURE')
    bucket = os.getenv('MINIO_OUTPUT_BUCKET', 'exam-reports')
    gemma_enabled = flag('GEMMA_ENABLED')
    gemma_url = os.getenv('GEMMA_BASE_URL', 'http://host.docker.internal:11434/v1')
    gemma_model = os.getenv('GEMMA_MODEL', 'gemma3:4b')
    gemma_key = os.getenv('GEMMA_API_KEY', 'not-needed')
    llm_timeout = int(os.getenv('LLM_TIMEOUT_SECONDS', '120'))
    sweeper = flag('ENABLE_DEADLINE_SWEEPER', 'true')


settings = Settings()
