"""Explicit schema initialization and local demo setup; run before API startup."""
import os
import time
from sqlalchemy import select
from .main import engine, SessionLocal
from .models import Base, User, Exam, Question, Enrollment
from .security import password_hash


def bootstrap():
    Base.metadata.create_all(engine)
    username = os.getenv('ADMIN_USERNAME', 'admin').lower()
    password = os.getenv('ADMIN_PASSWORD', '')
    if len(password) < 12:
        raise RuntimeError('Set ADMIN_PASSWORD to at least 12 characters')
    with SessionLocal() as s:
        admin = s.scalar(select(User).where(User.username == username))
        if not admin:
            s.add(User(username=username, name='Examination Administrator', role='admin', password_hash=password_hash(password)))
        if os.getenv('SEED_DEMO', 'false').lower() == 'true':
            demo = s.scalar(select(User).where(User.username == 'candidate01'))
            if not demo:
                pw = os.getenv('DEMO_CANDIDATE_PASSWORD', '')
                if len(pw) < 12:
                    raise RuntimeError('Set DEMO_CANDIDATE_PASSWORD to at least 12 characters')
                demo = User(username='candidate01', name='Demo Candidate', role='candidate', password_hash=password_hash(pw))
                s.add(demo)
                s.flush()
                e = Exam(title='Candidate Aptitude Assessment', description='A sample assessment covering reasoning, numeracy, and digital literacy. Replace these demonstration questions before real examinations.', duration_minutes=15, pass_percent=60, published=True, created_at=time.time())
                s.add(e)
                s.flush()
                bank = [
                    ('What is 15 percent of 200?', ['15', '20', '30', '40'], 2),
                    ('Which number comes next: 2, 4, 8, 16, ...?', ['18', '24', '30', '32'], 3),
                    ('Which practice best protects an online account?', ['Sharing passwords', 'Using a unique password and MFA', 'Reusing one short password', 'Disabling security updates'], 1),
                    ('A task takes 3 hours each day for 5 days. What is the total time?', ['8 hours', '10 hours', '15 hours', '20 hours'], 2),
                    ('Which file extension typically identifies a spreadsheet workbook?', ['.mp3', '.png', '.xlsx', '.mp4'], 2),
                    ('If all roses are flowers, which statement must be true?', ['All flowers are roses', 'No roses are flowers', 'Every rose is a flower', 'Every flower is red'], 2),
                    ('A team completes 12 of 20 tasks. What percentage is complete?', ['40%', '50%', '60%', '80%'], 2),
                    ('What should you do with an unexpected email asking for your password?', ['Reply with the password', 'Verify through a trusted channel', 'Forward your password to everyone', 'Disable your antivirus'], 1),
                ]
                for i, (prompt, options, correct) in enumerate(bank):
                    s.add(Question(exam_id=e.id, prompt=prompt, options=options, correct_index=correct, position=i))
                s.add(Enrollment(user_id=demo.id, exam_id=e.id))
        s.commit()
    print('Schema and initial accounts ready. Existing passwords were preserved.')


if __name__ == '__main__':
    bootstrap()
