import uuid
from sqlalchemy import String, Integer, Float, Boolean, JSON, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), default='candidate')
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class Exam(Base):
    __tablename__ = 'exams'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text, default='')
    duration_minutes: Mapped[int] = mapped_column(Integer)
    pass_percent: Mapped[int] = mapped_column(Integer)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float)


class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    exam_id: Mapped[str] = mapped_column(ForeignKey('exams.id'), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)
    correct_index: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)


class Enrollment(Base):
    __tablename__ = 'enrollments'
    __table_args__ = (UniqueConstraint('user_id', 'exam_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    exam_id: Mapped[str] = mapped_column(ForeignKey('exams.id'))


class Attempt(Base):
    __tablename__ = 'attempts'
    __table_args__ = (UniqueConstraint('user_id', 'exam_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    exam_id: Mapped[str] = mapped_column(ForeignKey('exams.id'))
    client_binding: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[float] = mapped_column(Float)
    deadline: Mapped[float] = mapped_column(Float, index=True)
    last_heartbeat: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default='in_progress', index=True)
    question_order: Mapped[list] = mapped_column(JSON)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    score_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str] = mapped_column(String(30), default='in_progress')
    submitted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Event(Base):
    __tablename__ = 'events'
    __table_args__ = (UniqueConstraint('attempt_id', 'event_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('attempts.id'), index=True)
    event_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[float] = mapped_column(Float)


class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[str] = mapped_column(String(36))
    detail: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[float] = mapped_column(Float)


class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    object_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[float] = mapped_column(Float)
