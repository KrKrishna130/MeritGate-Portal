"""API integration tests. Use only an isolated test database (tables are recreated)."""
import io
import os
import time
import uuid

os.environ['DATABASE_URL'] = os.getenv('TEST_DATABASE_URL', 'sqlite://')
os.environ['SECRET_KEY'] = 'test-key-that-is-at-least-thirty-two-characters-long'
os.environ['ENABLE_DEADLINE_SWEEPER'] = 'false'
os.environ['REQUIRE_ADMIN_RESULT_REVIEW'] = 'true'

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from app import main as m
from app.models import Base, User, Attempt, Exam, Question, Enrollment, Event, Report, Audit
from app.security import password_hash

PW = 'test-password-12345'


@pytest.fixture()
def portal(monkeypatch):
    if os.getenv('TEST_DATABASE_URL'):
        engine = create_engine(os.environ['TEST_DATABASE_URL'])
    else:
        engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = m.sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(m, 'SessionLocal', factory)
    monkeypatch.setattr(m, 'cache', fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(m.settings, 'require_review', True)
    monkeypatch.setattr(m.settings, 'gemma_enabled', False)
    with factory() as s:
        for username, role in [('admin', 'admin'), ('alice', 'candidate'), ('bob', 'candidate')]:
            s.add(User(username=username, name=username.title(), role=role, password_hash=password_hash(PW)))
        s.commit()
    clients = [TestClient(m.app) for _ in range(3)]
    for c, name in zip(clients, ['admin', 'alice', 'bob']):
        r = c.post('/v1/auth/login', json={'username': name, 'password': PW})
        assert r.status_code == 200, r.text
    admin, alice, bob = clients
    people = admin.get('/v1/admin/candidates').json()
    ids = {x['username']: x['id'] for x in people}
    data = {'title': 'Test assessment', 'duration_minutes': 10, 'pass_percent': 60, 'questions': [
        {'prompt': 'How much is two plus two?', 'options': ['one', 'two', 'three', 'four'], 'correct_index': 3},
        {'prompt': 'How much is one plus one?', 'options': ['one', 'two', 'three', 'four'], 'correct_index': 1}]}
    eid = admin.post('/v1/admin/exams', json=data).json()['id']
    assert admin.post(f'/v1/admin/exams/{eid}/publish', json={'reviewed': True}).status_code == 200
    assert admin.post(f'/v1/admin/exams/{eid}/assign', json={'user_id': ids['alice']}).status_code == 200
    yield {'admin': admin, 'alice': alice, 'bob': bob, 'factory': factory, 'exam': eid, 'ids': ids, 'exam_data': data}
    for c in clients:
        c.close()
    engine.dispose()


def begin(p):
    cid = str(uuid.uuid4())
    r = p['alice'].post(f"/v1/exams/{p['exam']}/start", json={'client_id': cid, 'consent': True})
    assert r.status_code == 200, r.text
    aid = r.json()['id']
    headers = {'X-Exam-Client': cid}
    d = p['alice'].get(f'/v1/attempts/{aid}', headers=headers).json()
    return aid, headers, d


def test_full_candidate_flow_and_human_review(portal):
    p = portal
    aid, h, d = begin(p)
    assert 'correct_index' not in str(d)
    with p['factory']() as s:
        correct = {q.id: q.correct_index for q in s.scalars(select(Question)).all()}
    for q in d['questions']:
        r = p['alice'].put(f'/v1/attempts/{aid}/answer', headers=h, json={'question_id': q['id'], 'selected_index': correct[q['id']]})
        assert r.status_code == 200
    result = p['alice'].post(f'/v1/attempts/{aid}/submit', headers=h).json()
    assert result['score_percent'] == 100
    assert result['outcome'] == 'pending_review'
    assert p['admin'].post(f'/v1/admin/attempts/{aid}/review', json={'decision': 'approve', 'note': 'Verified with the candidate and proctor.'}).json()['outcome'] == 'qualified'
    assert p['alice'].post(f'/v1/attempts/{aid}/submit', headers=h).json()['score_percent'] == 100
    assert p['alice'].put(f'/v1/attempts/{aid}/answer', headers=h, json={'question_id': d['questions'][0]['id'], 'selected_index': 0}).status_code == 409


def test_auth_and_rbac(portal):
    assert TestClient(m.app).get('/v1/exams').status_code == 401
    assert portal['alice'].get('/v1/admin/attempts').status_code == 403
    assert portal['alice'].post('/v1/admin/candidates', json={'username': 'evil', 'name': 'Test', 'password': PW}).status_code == 403
    assert portal['bob'].get('/v1/exams').json() == []
    assert portal['bob'].post(f"/v1/exams/{portal['exam']}/start", json={'client_id': str(uuid.uuid4()), 'consent': True}).status_code == 403


def test_cross_candidate_and_tab_binding(portal):
    aid, h, _ = begin(portal)
    assert portal['bob'].get(f'/v1/attempts/{aid}', headers=h).status_code == 404
    assert portal['alice'].get(f'/v1/attempts/{aid}', headers={'X-Exam-Client': str(uuid.uuid4())}).status_code == 409
    r = portal['alice'].post(f"/v1/exams/{portal['exam']}/start", json={'client_id': str(uuid.uuid4()), 'consent': True})
    assert r.status_code == 409
    other = TestClient(m.app)
    assert other.post('/v1/auth/login', json={'username': 'alice', 'password': PW}).status_code == 409


def test_deadline_server_side_and_sweeper(portal):
    aid, h, d = begin(portal)
    with portal['factory']() as s:
        s.get(Attempt, aid).deadline = time.time() - 1
        s.commit()
    r = portal['alice'].put(f'/v1/attempts/{aid}/answer', headers=h, json={'question_id': d['questions'][0]['id'], 'selected_index': 3})
    assert r.status_code == 409
    a = portal['alice'].get(f'/v1/attempts/{aid}', headers=h).json()
    assert a['status'] == 'timed_out'
    assert a['score_percent'] == 0
    assert a['questions'] == []
    m.sweep_once()  # Repeat is safe.


def test_sweeper_closes_without_client_request(portal):
    aid, _, _ = begin(portal)
    with portal['factory']() as s:
        s.get(Attempt, aid).deadline = time.time() - 5
        s.commit()
    m.sweep_once()
    with portal['factory']() as s:
        assert s.get(Attempt, aid).status == 'timed_out'


def test_event_idempotence_and_review_threshold(portal, monkeypatch):
    monkeypatch.setattr(m.settings, 'require_review', False)
    aid, h, _ = begin(portal)
    e = {'event_id': str(uuid.uuid4()), 'kind': 'tab_hidden'}
    for _ in range(2):
        assert portal['alice'].post(f'/v1/attempts/{aid}/events', json=e, headers=h).status_code == 200
    with portal['factory']() as s:
        assert len(s.scalars(select(Event)).all()) == 1
        assert s.get(Attempt, aid).event_count == 1
    for kind in ['focus_lost', 'fullscreen_exit']:
        portal['alice'].post(f'/v1/attempts/{aid}/events', json={'event_id': str(uuid.uuid4()), 'kind': kind}, headers=h)
    assert portal['alice'].post(f'/v1/attempts/{aid}/submit', headers=h).json()['outcome'] == 'pending_review'


def test_heartbeat_gap_flags_review(portal, monkeypatch):
    monkeypatch.setattr(m.settings, 'require_review', False)
    aid, h, _ = begin(portal)
    with portal['factory']() as s:
        s.get(Attempt, aid).last_heartbeat = time.time() - 120
        s.commit()
    r = portal['alice'].post(f'/v1/attempts/{aid}/heartbeat', headers=h)
    assert r.json()['needs_review'] is True
    assert r.json()['status'] == 'in_progress'


def test_recovery_preserves_answers_and_deadline(portal):
    aid, h, d = begin(portal)
    qid = d['questions'][0]['id']
    portal['alice'].put(f'/v1/attempts/{aid}/answer', headers=h, json={'question_id': qid, 'selected_index': 2})
    r = portal['admin'].post(f'/v1/admin/attempts/{aid}/recover', json={'note': 'Original browser crashed during the exam.'})
    assert r.status_code == 200
    assert portal['alice'].get('/v1/auth/me').status_code == 401
    assert portal['alice'].post('/v1/auth/login', json={'username': 'alice', 'password': PW}).status_code == 200
    new_cid = str(uuid.uuid4())
    resumed = portal['alice'].post(f"/v1/exams/{portal['exam']}/start", json={'client_id': new_cid, 'consent': True}).json()
    assert resumed['id'] == aid
    assert resumed['deadline'] == d['deadline']
    assert resumed['answers'][qid] == 2
    assert resumed['needs_review'] is True
    assert portal['alice'].get(f'/v1/attempts/{aid}', headers=h).status_code == 409


def test_immutable_published_exam_and_draft_edit(portal):
    p = portal
    assert p['admin'].put(f"/v1/admin/exams/{p['exam']}", json=p['exam_data']).status_code == 409
    draft = p['admin'].post('/v1/admin/exams', json=p['exam_data']).json()['id']
    changed = {**p['exam_data'], 'title': 'Updated draft exam'}
    assert p['admin'].put('/v1/admin/exams/' + draft, json=changed).status_code == 200
    assert p['admin'].get('/v1/admin/exams/' + draft).json()['title'] == changed['title']
    assert p['admin'].post('/v1/admin/exams/' + draft + '/publish', json={'reviewed': False}).status_code == 422


def test_invalid_answer_unknown_question_and_clear(portal):
    aid, h, d = begin(portal)
    path = f'/v1/attempts/{aid}/answer'
    assert portal['alice'].put(path, headers=h, json={'question_id': d['questions'][0]['id'], 'selected_index': 9}).status_code == 422
    assert portal['alice'].put(path, headers=h, json={'question_id': str(uuid.uuid4()), 'selected_index': 1}).status_code == 400
    for i in [2, None]:
        assert portal['alice'].put(path, headers=h, json={'question_id': d['questions'][0]['id'], 'selected_index': i}).status_code == 200
    assert portal['alice'].get(f'/v1/attempts/{aid}', headers=h).json()['answers'] == {}


def test_csrf_origin_rejected_and_headers(portal):
    r = portal['alice'].post('/v1/auth/logout', headers={'Origin': 'https://untrusted.example'})
    assert r.status_code == 403
    r = portal['alice'].get('/v1/exams')
    assert r.headers['cache-control'] == 'no-store'
    assert r.headers['permissions-policy'].startswith('display-capture=()')


def test_review_rejection_and_below_pass_approval(portal):
    aid, h, _ = begin(portal)
    assert portal['admin'].post(f'/v1/admin/attempts/{aid}/review', json={'decision': 'approve', 'note': 'Not yet a completed exam.'}).status_code == 409
    portal['alice'].post(f'/v1/attempts/{aid}/submit', headers=h)
    result = portal['admin'].post(f'/v1/admin/attempts/{aid}/review', json={'decision': 'approve', 'note': 'Attempt valid, no answers provided.'}).json()
    assert result['outcome'] == 'not_qualified'
    assert portal['admin'].post(f'/v1/admin/attempts/{aid}/review', json={'decision': 'reject', 'note': 'Documented rule violation after review.'}).json()['outcome'] == 'disqualified'


def test_login_throttle_and_invalid_password(portal):
    c = TestClient(m.app)
    for _ in range(9):
        assert c.post('/v1/auth/login', json={'username': 'alice', 'password': 'wrong'}).status_code == 401
    assert c.post('/v1/auth/login', json={'username': 'alice', 'password': 'wrong'}).status_code == 429


def test_minio_export_and_download_authorization(portal, monkeypatch):
    objects = {}
    class Stored:
        def __init__(self, data): self.data = data
        def stream(self, size): yield self.data
        def close(self): pass
        def release_conn(self): pass
    class FakeMinio:
        def bucket_exists(self, bucket): return True
        def put_object(self, bucket, key, data, length, content_type): objects[key] = data.read()
        def get_object(self, bucket, key): return Stored(objects[key])
    monkeypatch.setattr(m, 'storage', lambda: FakeMinio())
    aid, _, _ = begin(portal)
    with portal['factory']() as s:
        s.get(User, portal['ids']['alice']).name = '=HYPERLINK("bad")'
        s.commit()
    r = portal['admin'].post('/v1/admin/reports')
    assert r.status_code == 201
    url = r.json()['download_url']
    download = portal['admin'].get(url)
    assert download.status_code == 200
    assert "'=HYPERLINK" in download.text
    assert portal['alice'].get(url).status_code == 403
    assert portal['admin'].get('/v1/admin/reports/'+str(uuid.uuid4())).status_code == 404


def test_gemma_disabled_and_bad_draft(portal, monkeypatch):
    assert portal['admin'].post('/v1/admin/questions/draft', json={'topic': 'Arithmetic', 'count': 3}).status_code == 409
    assert portal['alice'].post('/v1/admin/questions/draft', json={'topic': 'Arithmetic', 'count': 3}).status_code == 403
    monkeypatch.setattr(m.settings, 'gemma_enabled', True)
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs):
            return m.httpx.Response(200, json={'choices': [{'message': {'content': 'not json'}}]}, request=m.httpx.Request('POST', 'http://example.test'))
    monkeypatch.setattr(m.httpx, 'AsyncClient', FakeClient)
    assert portal['admin'].post('/v1/admin/questions/draft', json={'topic': 'Arithmetic', 'count': 3}).status_code == 502


def test_password_reset_invalidates_session(portal):
    r = portal['admin'].post(f"/v1/admin/candidates/{portal['ids']['alice']}/password", json={'password': 'new-long-password-345'})
    assert r.status_code == 200
    assert portal['alice'].get('/v1/auth/me').status_code == 401
    assert portal['alice'].post('/v1/auth/login', json={'username': 'alice', 'password': 'new-long-password-345'}).status_code == 200


def test_redis_unavailable_fails_closed(portal, monkeypatch):
    def fail(*args): raise m.redis.RedisError('unavailable')
    monkeypatch.setattr(m.cache, 'eval', fail)
    assert TestClient(m.app).post('/v1/auth/login', json={'username': 'alice', 'password': PW}).status_code == 503
