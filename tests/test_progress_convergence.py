"""Teste de convergência Progress × LessonProgress (DEBITOS #4).

Garante que, quando um aluno conclui todas as aulas de um curso via
LessonProgress, o curso aparece em _completed_course_ids(). E que quando
Progress.passed é True para um curso, o resultado é consistente.

Se este teste falhar, os dois modelos divergiram — corrigir antes de
qualquer release ou unificar os modelos (Fase 3).
"""
import pytest


@pytest.fixture()
def completed_aluno(app, seeded, client):
    """Aluno que concluiu todas as aulas do curso via LessonProgress."""
    with app.app_context():
        from extensions import db
        from models import LessonProgress

        uid = seeded['users']['aluno']
        cid = seeded['course_id']

        for mid in (seeded['module1_id'], seeded['module2_id']):
            prog = LessonProgress.query.filter_by(user_id=uid, module_id=mid).first()
            if not prog:
                prog = LessonProgress(user_id=uid, course_id=cid, module_id=mid)
                db.session.add(prog)
            prog.passed = True
            prog.score = 2
            prog.total = 2
            prog.video_watched = True

        db.session.commit()
        return {'user_id': uid, 'course_id': cid}


def test_completed_course_ids_includes_course(app, seeded, completed_aluno):
    """_completed_course_ids deve reconhecer o curso como concluído."""
    with app.app_context():
        from routes.trails import _completed_course_ids
        done = _completed_course_ids(completed_aluno['user_id'])
        assert completed_aluno['course_id'] in done, (
            f"Curso {completed_aluno['course_id']} tem todos os módulos "
            f"com LessonProgress.passed=True mas _completed_course_ids "
            f"não o inclui. Divergência Progress/LessonProgress detectada."
        )


def test_progress_passed_consistent(app, seeded, completed_aluno):
    """Se Progress.passed=True, _completed_course_ids também deve incluir."""
    with app.app_context():
        from extensions import db
        from models import Progress
        from routes.trails import _completed_course_ids

        uid = completed_aluno['user_id']
        cid = completed_aluno['course_id']

        prog = Progress.query.filter_by(user_id=uid, course_id=cid).first()
        if not prog:
            prog = Progress(user_id=uid, course_id=cid)
            db.session.add(prog)
        prog.material_done = True
        prog.quiz_score = 10
        prog.quiz_total = 10
        db.session.commit()

        assert prog.passed, "Progress.passed deveria ser True"
        done = _completed_course_ids(uid)
        assert cid in done, (
            f"Progress.passed=True mas _completed_course_ids não inclui "
            f"o curso {cid}. Os dois modelos divergiram."
        )


def test_incomplete_course_not_in_completed(app, seeded):
    """Curso com apenas 1 de 2 módulos concluídos não deve constar."""
    with app.app_context():
        from extensions import db
        from models import LessonProgress
        from routes.trails import _completed_course_ids

        uid = seeded['users']['tutor']
        cid = seeded['course_id']
        mid = seeded['module1_id']

        prog = LessonProgress.query.filter_by(user_id=uid, module_id=mid).first()
        if not prog:
            prog = LessonProgress(user_id=uid, course_id=cid, module_id=mid)
            db.session.add(prog)
        prog.passed = True
        prog.score = 2
        prog.total = 2
        db.session.commit()

        done = _completed_course_ids(uid)
        assert cid not in done, (
            f"Curso {cid} aparece em _completed_course_ids com apenas "
            f"1 de 2 módulos concluídos — falso positivo."
        )
