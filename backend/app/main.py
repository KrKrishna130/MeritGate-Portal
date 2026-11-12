import asyncio
import csv
import io
import json
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager, suppress
from typing import Literal

import httpx
import jwt
import redis
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from minio import Minio
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from .config import settings
from .models import Base, User, Exam, Question, Enrollment, Attempt, Event, Audit, Report
from .security import password_hash, password_ok, binding

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
cache = redis.Redis.from_url(settings.redis_url, decode_responses=True)
log = logging.getLogger('meritgate')


def db():
    with SessionLocal() as session:
        yield session


def audit(s, actor, action, target, detail=''):
    s.add(Audit(actor_id=actor, action=action, target_id=target, detail=detail, created_at=time.time()))


def questions(s, exam_id):
    return s.scalars(select(Question).where(Question.exam_id == exam_id).order_by(Question.position)).all()


def finalize(s, a, reason='submitted'):
    if a.status != 'in_progress':
        return
    qs = questions(s, a.exam_id)
    correct = sum(a.answers.get(q.id) == q.correct_index for q in qs)
    a.score_percent = round(100 * correct / len(qs), 2) if qs else 0
    a.status = reason
    a.submitted_at = time.time()
    exam = s.get(Exam, a.exam_id)
    a.outcome = 'pending_review' if (a.needs_review or settings.require_review) else ('qualified' if a.score_percent >= exam.pass_percent else 'not_qualified')
    audit(s, a.user_id, reason, a.id)


def check_gap(s, a):
    now = time.time()
    if a.status == 'in_progress' and now - a.last_heartbeat > settings.heartbeat_gap:
        a.needs_review = True
    if a.status == 'in_progress' and now >= a.deadline:
        finalize(s, a, 'timed_out')


def sweep_once():
    with SessionLocal() as s:
        rows = s.scalars(select(Attempt).where(Attempt.status == 'in_progress').with_for_update(skip_locked=True)).all()
        for a in rows:
            check_gap(s, a)
        s.commit()


async def sweep():
    while True:
        try:
            await asyncio.to_thread(sweep_once)
        except Exception:
            log.exception('Deadline sweep failed; request-time enforcement remains active')
        await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app):
    if len(settings.secret) < 32:
        raise RuntimeError('SECRET_KEY must contain at least 32 characters. Run scripts/init_env.py.')
    # Schema creation is explicit via python -m app.bootstrap before serving.
    task = asyncio.create_task(sweep()) if settings.sweeper else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title=settings.app_name, version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                   allow_methods=['GET', 'POST', 'PUT'], allow_headers=['Content-Type', 'X-Exam-Client'])


@app.middleware('http')
async def security_headers(request: Request, call_next):
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        origin = request.headers.get('origin')
        # Cross-site browser writes are rejected; non-browser clients can authenticate normally.
        if (origin and origin not in settings.origins) or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Cross-origin write rejected. Check CORS_ORIGINS for this exact site URL.'}, status_code=403)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'display-capture=(), camera=(), microphone=()'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def current(request: Request, s: Session = Depends(db)):
    token = request.cookies.get('exam_session')
    try:
        payload = jwt.decode(token or '', settings.secret, algorithms=['HS256'], options={'require': ['exp', 'sub', 'jti']})
        user = s.get(User, payload['sub'])
        if not user or user.session_id != payload['jti']:
            raise ValueError()
        return user
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(401, 'Please sign in')


def admin(u: User = Depends(current)):
    if u.role != 'admin':
        raise HTTPException(403, 'Administrator access required')
    return u


def candidate(u: User = Depends(current)):
    if u.role != 'candidate':
        raise HTTPException(403, 'Candidate account required')
    return u


def me_view(u):
    return {'id': u.id, 'username': u.username, 'name': u.name, 'role': u.role}


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


@app.post('/v1/auth/login')
def login(body: Login, request: Request, response: Response, s: Session = Depends(db)):
    username = body.username.strip().lower()
    # Atomic Redis counters with TTL; fail closed when rate-limit storage is unavailable.
    keys = ['login:ip:' + binding(request.client.host), 'login:user:' + binding(username)]
    try:
        for key, limit in zip(keys, [40, 10]):
            count = cache.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],300) end; return n", 1, key)
            if count > limit:
                raise HTTPException(429, 'Too many login requests. Wait five minutes.')
    except redis.RedisError:
        raise HTTPException(503, 'Sign-in temporarily unavailable')
    u = s.scalar(select(User).where(User.username == username).with_for_update())
    # Also run scrypt for unknown users to avoid a fast account-existence oracle.
    valid = password_ok(body.password, u.password_hash if u else password_hash('unused-password'))
    if not u or not valid:
        raise HTTPException(401, 'Invalid user ID or password')
    active = s.scalars(select(Attempt).where(Attempt.user_id == u.id, Attempt.status == 'in_progress').with_for_update()).all()
    for a in active:
        check_gap(s, a)
    if any(a.status == 'in_progress' for a in active) and u.session_id:
        s.commit()
        raise HTTPException(409, 'An exam is already active. Resume in the original browser or ask an administrator for recovery.')
    u.session_id = str(uuid.uuid4())
    token = jwt.encode({'sub': u.id, 'jti': u.session_id, 'exp': int(time.time()) + settings.session_hours * 3600}, settings.secret, algorithm='HS256')
    audit(s, u.id, 'login', u.id)
    s.commit()
    response.set_cookie('exam_session', token, httponly=True, secure=settings.secure_cookie, samesite='strict', max_age=settings.session_hours * 3600, path='/')
    return me_view(u)


@app.get('/v1/auth/me')
def me(u: User = Depends(current)):
    return me_view(u)


@app.post('/v1/auth/logout')
def logout(response: Response, u: User = Depends(current), s: Session = Depends(db)):
    # Ending a login does not reset an exam's deadline or answers.
    locked = s.scalar(select(User).where(User.id == u.id).with_for_update())
    locked.session_id = None
    s.commit()
    response.delete_cookie('exam_session', path='/')
    return {'ok': True}


class NewUser(BaseModel):
    username: str = Field(pattern=r'^[a-zA-Z0-9_.-]{3,80}$')
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=128)


@app.post('/v1/admin/candidates', status_code=201)
def create_candidate(body: NewUser, u: User = Depends(admin), s: Session = Depends(db)):
    new = User(username=body.username.lower(), name=body.name, password_hash=password_hash(body.password), role='candidate')
    s.add(new)
    try:
        s.flush()
        audit(s, u.id, 'create_candidate', new.id)
        s.commit()
    except IntegrityError:
        s.rollback()
        raise HTTPException(409, 'User ID already exists')
    return me_view(new)


@app.get('/v1/admin/candidates')
def candidates(u: User = Depends(admin), s: Session = Depends(db)):
    return [me_view(x) for x in s.scalars(select(User).where(User.role == 'candidate').order_by(User.name)).all()]


class QuestionInput(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)

    @model_validator(mode='after')
    def options_valid(self):
        if any(not x.strip() or len(x) > 500 for x in self.options) or len(set(self.options)) != 4:
            raise ValueError('Provide four distinct, nonempty options of at most 500 characters')
        return self


class ExamInput(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    description: str = Field(max_length=3000, default='')
    duration_minutes: int = Field(ge=1, le=180)
    pass_percent: int = Field(ge=1, le=100)
    questions: list[QuestionInput] = Field(min_length=1, max_length=100)


@app.post('/v1/admin/exams', status_code=201)
def create_exam(body: ExamInput, u: User = Depends(admin), s: Session = Depends(db)):
    e = Exam(title=body.title, description=body.description, duration_minutes=body.duration_minutes, pass_percent=body.pass_percent, created_at=time.time())
    s.add(e)
    s.flush()
    for i, q in enumerate(body.questions):
        s.add(Question(exam_id=e.id, position=i, **q.model_dump()))
    audit(s, u.id, 'create_exam', e.id)
    s.commit()
    return {'id': e.id}


class PublishApproval(BaseModel):
    reviewed: Literal[True]


@app.post('/v1/admin/exams/{exam_id}/publish')
def publish(exam_id: str, body: PublishApproval, u: User = Depends(admin), s: Session = Depends(db)):
    e = s.scalar(select(Exam).where(Exam.id == exam_id).with_for_update())
    if not e:
        raise HTTPException(404, 'Exam not found')
    if not questions(s, e.id):
        raise HTTPException(400, 'Add questions first')
    e.published = True
    audit(s, u.id, 'publish_exam', e.id, 'Administrator confirmed human verification of questions and answer keys')
    s.commit()
    return {'ok': True}


class Assignment(BaseModel):
    user_id: uuid.UUID


@app.post('/v1/admin/exams/{exam_id}/assign')
def assign(exam_id: str, body: Assignment, u: User = Depends(admin), s: Session = Depends(db)):
    person, exam = s.get(User, str(body.user_id)), s.get(Exam, exam_id)
    if not person or person.role != 'candidate' or not exam:
        raise HTTPException(404, 'Candidate or exam not found')
    existing = s.scalar(select(Enrollment).where(Enrollment.user_id == person.id, Enrollment.exam_id == exam_id))
    if not existing:
        s.add(Enrollment(user_id=person.id, exam_id=exam_id))
        audit(s, u.id, 'assign_exam', exam_id, person.id)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
    return {'ok': True}


def exam_view(s, e):
    return {'id': e.id, 'title': e.title, 'description': e.description, 'duration_minutes': e.duration_minutes,
            'pass_percent': e.pass_percent, 'published': e.published, 'question_count': len(questions(s, e.id))}


@app.get('/v1/exams')
def list_exams(u: User = Depends(current), s: Session = Depends(db)):
    query = select(Exam).order_by(Exam.created_at.desc())
    if u.role != 'admin':
        query = query.join(Enrollment, Enrollment.exam_id == Exam.id).where(Enrollment.user_id == u.id, Exam.published == True)
    result = []
    for e in s.scalars(query).all():
        row = exam_view(s, e)
        a = s.scalar(select(Attempt).where(Attempt.exam_id == e.id, Attempt.user_id == u.id).with_for_update())
        if a:
            check_gap(s, a)
            row['attempt'] = attempt_view(a)
        result.append(row)
    s.commit()
    return result


class Start(BaseModel):
    client_id: uuid.UUID
    consent: Literal[True]


def attempt_view(a):
    return {k: getattr(a, k) for k in ['id', 'exam_id', 'status', 'deadline', 'started_at', 'answers', 'event_count', 'needs_review', 'score_percent', 'outcome', 'review_note']}


@app.post('/v1/exams/{exam_id}/start')
def start(exam_id: str, body: Start, u: User = Depends(candidate), s: Session = Depends(db)):
    s.scalar(select(User).where(User.id == u.id).with_for_update())
    e = s.get(Exam, exam_id)
    enrolled = s.scalar(select(Enrollment).where(Enrollment.user_id == u.id, Enrollment.exam_id == exam_id))
    if not e or not e.published or not enrolled:
        raise HTTPException(403, 'Exam is not assigned and published')
    a = s.scalar(select(Attempt).where(Attempt.user_id == u.id, Attempt.exam_id == exam_id).with_for_update())
    if a:
        check_gap(s, a)
        if a.status == 'in_progress':
            if a.client_binding and a.client_binding != binding(body.client_id):
                s.commit()
                raise HTTPException(409, 'Attempt belongs to another browser tab. Ask an administrator for recovery.')
            a.client_binding = binding(body.client_id)
        s.commit()
        return attempt_view(a)
    other = s.scalar(select(Attempt).where(Attempt.user_id == u.id, Attempt.status == 'in_progress').with_for_update())
    if other:
        check_gap(s, other)
        if other.status == 'in_progress':
            s.commit()
            raise HTTPException(409, 'Finish the active exam first')
    order = [q.id for q in questions(s, e.id)]
    secrets.SystemRandom().shuffle(order)
    now = time.time()
    a = Attempt(user_id=u.id, exam_id=e.id, client_binding=binding(body.client_id), started_at=now,
                deadline=now + e.duration_minutes * 60, last_heartbeat=now, question_order=order, answers={})
    s.add(a)
    s.flush()
    audit(s, u.id, 'start_exam', a.id, 'Candidate acknowledged exam monitoring notice')
    s.commit()
    return attempt_view(a)


def owned_attempt(attempt_id, s, u, client=None, write=False):
    a = s.scalar(select(Attempt).where(Attempt.id == attempt_id).with_for_update())
    if not a or a.user_id != u.id:
        raise HTTPException(404, 'Attempt not found')
    if not client or not a.client_binding or not secrets.compare_digest(a.client_binding, binding(client)):
        raise HTTPException(409, 'Original exam tab or administrator recovery required')
    check_gap(s, a)
    if write and a.status != 'in_progress':
        s.commit()
        raise HTTPException(409, 'Exam is already closed')
    return a


@app.get('/v1/attempts/{attempt_id}')
def get_attempt(attempt_id: str, x_exam_client: str = Header(default=''), u: User = Depends(candidate), s: Session = Depends(db)):
    a = owned_attempt(attempt_id, s, u, x_exam_client)
    data = attempt_view(a)
    if a.status == 'in_progress':
        lookup = {q.id: q for q in questions(s, a.exam_id)}
        data['questions'] = [{'id': qid, 'prompt': lookup[qid].prompt, 'options': lookup[qid].options} for qid in a.question_order]
    else:
        data['questions'] = []
    data['server_time'] = time.time()
    s.commit()
    return data


class Answer(BaseModel):
    question_id: uuid.UUID
    selected_index: int | None = Field(default=None, ge=0, le=3)


@app.put('/v1/attempts/{attempt_id}/answer')
def answer(attempt_id: str, body: Answer, x_exam_client: str = Header(default=''), u: User = Depends(candidate), s: Session = Depends(db)):
    a = owned_attempt(attempt_id, s, u, x_exam_client, write=True)
    qid = str(body.question_id)
    if qid not in a.question_order:
        raise HTTPException(400, 'Question does not belong to this attempt')
    updated = dict(a.answers)
    if body.selected_index is None:
        updated.pop(qid, None)
    else:
        updated[qid] = body.selected_index
    a.answers = updated
    s.commit()
    return {'saved': True, 'server_time': time.time()}


@app.post('/v1/attempts/{attempt_id}/heartbeat')
def heartbeat(attempt_id: str, x_exam_client: str = Header(default=''), u: User = Depends(candidate), s: Session = Depends(db)):
    a = owned_attempt(attempt_id, s, u, x_exam_client)
    if a.status == 'in_progress':
        a.last_heartbeat = time.time()
    s.commit()
    return {**attempt_view(a), 'server_time': time.time()}


class EventInput(BaseModel):
    event_id: uuid.UUID
    kind: Literal['tab_hidden', 'focus_lost', 'fullscreen_exit', 'copy_attempt', 'paste_attempt', 'context_menu', 'print_shortcut', 'screenshot_shortcut', 'window_resize', 'offline']


@app.post('/v1/attempts/{attempt_id}/events')
def event(attempt_id: str, body: EventInput, x_exam_client: str = Header(default=''), u: User = Depends(candidate), s: Session = Depends(db)):
    a = owned_attempt(attempt_id, s, u, x_exam_client)
    if a.status == 'in_progress':
        existing = s.scalar(select(Event).where(Event.attempt_id == a.id, Event.event_id == str(body.event_id)))
        if not existing:
            if a.event_count >= 1000:
                raise HTTPException(429, 'Event limit reached')
            s.add(Event(attempt_id=a.id, event_id=str(body.event_id), kind=body.kind, received_at=time.time()))
            a.event_count += 1
            if a.event_count >= settings.review_threshold:
                a.needs_review = True
    s.commit()
    return {'event_count': a.event_count, 'needs_review': a.needs_review}


@app.post('/v1/attempts/{attempt_id}/submit')
def submit(attempt_id: str, x_exam_client: str = Header(default=''), u: User = Depends(candidate), s: Session = Depends(db)):
    a = owned_attempt(attempt_id, s, u, x_exam_client)
    finalize(s, a)
    s.commit()
    return attempt_view(a)


@app.get('/v1/admin/attempts')
def attempts(u: User = Depends(admin), s: Session = Depends(db)):
    result = []
    for a in s.scalars(select(Attempt).order_by(Attempt.started_at.desc()).with_for_update()).all():
        check_gap(s, a)
        person, e = s.get(User, a.user_id), s.get(Exam, a.exam_id)
        result.append({**attempt_view(a), 'candidate': person.name, 'username': person.username, 'exam_title': e.title,
                       'last_heartbeat': a.last_heartbeat})
    s.commit()
    return result


@app.get('/v1/admin/attempts/{attempt_id}/events')
def attempt_events(attempt_id: str, u: User = Depends(admin), s: Session = Depends(db)):
    return [{'kind': x.kind, 'received_at': x.received_at} for x in s.scalars(select(Event).where(Event.attempt_id == attempt_id).order_by(Event.received_at)).all()]


class Review(BaseModel):
    decision: Literal['approve', 'reject']
    note: str = Field(min_length=10, max_length=2000)


@app.post('/v1/admin/attempts/{attempt_id}/review')
def review(attempt_id: str, body: Review, u: User = Depends(admin), s: Session = Depends(db)):
    a = s.scalar(select(Attempt).where(Attempt.id == attempt_id).with_for_update())
    if not a:
        raise HTTPException(404, 'Attempt not found')
    check_gap(s, a)
    if a.status == 'in_progress':
        s.commit()
        raise HTTPException(409, 'Wait until the exam is closed')
    exam = s.get(Exam, a.exam_id)
    a.outcome = ('qualified' if a.score_percent >= exam.pass_percent else 'not_qualified') if body.decision == 'approve' else 'disqualified'
    a.review_note = body.note
    audit(s, u.id, 'review_' + body.decision, a.id, body.note)
    s.commit()
    return attempt_view(a)


class Recovery(BaseModel):
    note: str = Field(min_length=10, max_length=2000)


@app.post('/v1/admin/attempts/{attempt_id}/recover')
def recover(attempt_id: str, body: Recovery, u: User = Depends(admin), s: Session = Depends(db)):
    # Lock User before Attempt, matching login/start lock ordering.
    initial = s.get(Attempt, attempt_id)
    if not initial:
        raise HTTPException(404, 'Attempt not found')
    person = s.scalar(select(User).where(User.id == initial.user_id).with_for_update())
    a = s.scalar(select(Attempt).where(Attempt.id == attempt_id).with_for_update())
    check_gap(s, a)
    if a.status != 'in_progress':
        s.commit()
        raise HTTPException(409, 'Closed exams cannot be reopened')
    a.client_binding = None
    a.needs_review = True
    person.session_id = None
    audit(s, u.id, 'recover_session', a.id, body.note)
    s.commit()
    return {'ok': True, 'message': 'Candidate may log in again. Original deadline remains in force.'}


def storage():
    return Minio(settings.minio_endpoint, access_key=settings.minio_access, secret_key=settings.minio_secret, secure=settings.minio_secure)


@app.post('/v1/admin/reports', status_code=201)
def export_report(u: User = Depends(admin), s: Session = Depends(db)):
    rows = attempts(u, s)
    fields = ['id', 'username', 'candidate', 'exam_title', 'status', 'score_percent', 'outcome', 'event_count', 'needs_review']
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        # Defend spreadsheet applications against formula injection in exported names/titles.
        writer.writerow({k: ("'" + str(row[k]) if str(row[k]).lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else row[k]) for k in fields})
    data = output.getvalue().encode('utf-8-sig')
    key = f'reports/{uuid.uuid4()}.csv'
    try:
        client = storage()
        if not client.bucket_exists(settings.bucket):
            client.make_bucket(settings.bucket)
        client.put_object(settings.bucket, key, io.BytesIO(data), len(data), content_type='text/csv')
    except Exception:
        log.exception('Report storage unavailable')
        raise HTTPException(503, 'MinIO report storage unavailable; retry later')
    report = Report(owner_id=u.id, object_key=key, created_at=time.time())
    s.add(report)
    s.flush()
    audit(s, u.id, 'export_report', report.id)
    s.commit()
    return {'download_url': f'/v1/admin/reports/{report.id}', 'id': report.id}


@app.get('/v1/admin/reports/{report_id}')
def download(report_id: str, u: User = Depends(admin), s: Session = Depends(db)):
    r = s.get(Report, report_id)
    if not r or r.owner_id != u.id:
        raise HTTPException(404, 'Report not found')
    try:
        obj = storage().get_object(settings.bucket, r.object_key)
    except Exception:
        raise HTTPException(503, 'Report unavailable')
    def stream():
        try:
            yield from obj.stream(65536)
        finally:
            obj.close()
            obj.release_conn()
    return StreamingResponse(stream(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="meritgate-results.csv"'})


@app.get('/v1/admin/audit')
def audit_log(u: User = Depends(admin), s: Session = Depends(db)):
    return [{k: getattr(a, k) for k in ['actor_id', 'action', 'target_id', 'detail', 'created_at']} for a in s.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200)).all()]


class DraftRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    count: int = Field(default=3, ge=1, le=5)


@app.post('/v1/admin/questions/draft')
async def draft(body: DraftRequest, u: User = Depends(admin)):
    if not settings.gemma_enabled:
        raise HTTPException(409, 'Enable GEMMA_ENABLED in .env to draft questions')
    try:
        prompt = f'Create {body.count} neutral factual multiple-choice practice questions about {body.topic}. Return ONLY JSON: {{"questions":[{{"prompt":"...","options":["A","B","C","D"],"correct_index":0}}]}}. Index is zero-based. No political persuasion or personal profiling.'
        async with httpx.AsyncClient(timeout=settings.llm_timeout) as client:
            r = await client.post(settings.gemma_url.rstrip('/') + '/chat/completions', headers={'Authorization': 'Bearer ' + settings.gemma_key}, json={'model': settings.gemma_model, 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.2, 'max_tokens': 1800, 'response_format': {'type': 'json_object'}})
        r.raise_for_status()
        content = r.json()['choices'][0]['message']['content']
        parsed = json.loads(content)
        result = [QuestionInput.model_validate(q).model_dump() for q in parsed['questions']]
        if len(result) != body.count:
            raise ValueError('Incorrect question count')
        return {'questions': result, 'notice': 'Unverified AI drafts. A human must verify facts and answer keys before publishing.'}
    except Exception:
        log.exception('Question drafting failed')
        raise HTTPException(502, 'Gemma unavailable or returned invalid questions. Use the manual question editor.')


@app.get('/v1/health')
def health(s: Session = Depends(db)):
    try:
        s.execute(text('SELECT 1'))
        cache.ping()
    except Exception:
        raise HTTPException(503, 'Database or Redis unavailable')
    return {'status': 'ok', 'gemma_enabled': settings.gemma_enabled}

@app.get('/v1/admin/exams/{exam_id}')
def exam_detail(exam_id: str, u: User = Depends(admin), s: Session = Depends(db)):
    e = s.get(Exam, exam_id)
    if not e:
        raise HTTPException(404, 'Exam not found')
    return {**exam_view(s, e), 'questions': [{'prompt': q.prompt, 'options': q.options, 'correct_index': q.correct_index} for q in questions(s, e.id)]}


@app.put('/v1/admin/exams/{exam_id}')
def edit_exam(exam_id: str, body: ExamInput, u: User = Depends(admin), s: Session = Depends(db)):
    e = s.scalar(select(Exam).where(Exam.id == exam_id).with_for_update())
    if not e:
        raise HTTPException(404, 'Exam not found')
    if e.published:
        raise HTTPException(409, 'Published exams are immutable. Create a new exam for changes.')
    for key in ['title', 'description', 'duration_minutes', 'pass_percent']:
        setattr(e, key, getattr(body, key))
    for q in questions(s, e.id):
        s.delete(q)
    for i, q in enumerate(body.questions):
        s.add(Question(exam_id=e.id, position=i, **q.model_dump()))
    audit(s, u.id, 'edit_draft', e.id)
    s.commit()
    return {'ok': True}


class ResetPassword(BaseModel):
    password: str = Field(min_length=12, max_length=128)


@app.post('/v1/admin/candidates/{user_id}/password')
def reset_password(user_id: str, body: ResetPassword, u: User = Depends(admin), s: Session = Depends(db)):
    person = s.scalar(select(User).where(User.id == user_id, User.role == 'candidate').with_for_update())
    if not person:
        raise HTTPException(404, 'Candidate not found')
    person.password_hash = password_hash(body.password)
    person.session_id = None
    audit(s, u.id, 'reset_candidate_password', person.id)
    s.commit()
    return {'ok': True}
