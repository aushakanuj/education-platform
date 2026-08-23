from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from education_platform.modules.academics.models import (
    AcademicPeriod,
    Grade,
    GradeSubjectOffering,
    PeriodGrade,
    Subject,
    Subtopic,
    TeachingAssignment,
    TeachingAssignmentStatus,
)
from education_platform.modules.assessments.models import (
    CommonMasteryQuiz,
    QuestionAnswerKey,
    QuizItem,
)
from education_platform.modules.auth.models import Institution, RoleName, User, UserRole, UserStatus
from education_platform.modules.auth.security import hash_password
from education_platform.modules.materials.seed import (
    POC_GRADE_NAME,
    POC_INSTITUTION_NAME,
    POC_PERIOD_NAME,
    POC_SUBJECT_CODE,
)

POC_TEACHER_EMAIL = "math.teacher@demo.school"
POC_TEACHER_PASSWORD = "demo1234"


def _login(client: TestClient, email: str, password: str, institution_name: str) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "institution_name": institution_name},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _assign_poc_teacher(db: Session) -> None:
    institution = db.scalar(select(Institution).where(Institution.name == POC_INSTITUTION_NAME))
    assert institution is not None
    user = User(
        institution_id=institution.id,
        email=POC_TEACHER_EMAIL,
        full_name="POC Math Teacher",
        password_hash=hash_password(POC_TEACHER_PASSWORD),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role=RoleName.TEACHER))
    period = db.scalar(
        select(AcademicPeriod).where(
            AcademicPeriod.institution_id == institution.id,
            AcademicPeriod.name == POC_PERIOD_NAME,
        )
    )
    grade = db.scalar(
        select(Grade).where(Grade.institution_id == institution.id, Grade.name == POC_GRADE_NAME)
    )
    subject = db.scalar(
        select(Subject).where(
            Subject.institution_id == institution.id, Subject.code == POC_SUBJECT_CODE
        )
    )
    assert period is not None and grade is not None and subject is not None
    period_grade = db.scalar(
        select(PeriodGrade).where(
            PeriodGrade.academic_period_id == period.id, PeriodGrade.grade_id == grade.id
        )
    )
    assert period_grade is not None
    offering = db.scalar(
        select(GradeSubjectOffering).where(
            GradeSubjectOffering.period_grade_id == period_grade.id,
            GradeSubjectOffering.subject_id == subject.id,
        )
    )
    assert offering is not None
    db.add(
        TeachingAssignment(
            teacher_user_id=user.id,
            academic_period_id=period.id,
            grade_subject_offering_id=offering.id,
            section_id=None,
            status=TeachingAssignmentStatus.ACTIVE,
        )
    )
    db.commit()


def test_enrollments_after_poc_math(
    client: TestClient, enrolled_student_headers: dict[str, str]
) -> None:
    response = client.get("/api/v1/me/enrollments", headers=enrolled_student_headers)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["grade_enrollments"]) == 1
    assert len(payload["subject_enrollments"]) == 1
    assert payload["subject_enrollments"][0]["subject_code"] == "MATH"


def test_quiz_attempt_scores_without_leaking_keys(
    client: TestClient,
    enrolled_student_headers: dict[str, str],
    seeded_db: Session,
) -> None:
    quiz = client.get(
        "/api/v1/materials/square_numbers_patterns/quiz", headers=enrolled_student_headers
    )
    assert quiz.status_code == 200
    questions = quiz.json()["questions"]
    quiz_id = quiz.json()["id"]

    directory = client.get("/api/v1/me/learning-directory", headers=enrolled_student_headers)
    assert directory.status_code == 200
    subtopic_id = next(
        subtopic["id"]
        for subject in directory.json()["subjects"]
        for topic in subject["topics"]
        for subtopic in topic["subtopics"]
        if subtopic["slug"] == "square_numbers_patterns"
    )
    progress = client.put(
        f"/api/v1/subtopics/{subtopic_id}/material-progress",
        headers=enrolled_student_headers,
        json={"status": "completed"},
    )
    assert progress.status_code == 200, progress.text

    start = client.post(
        f"/api/v1/quizzes/{quiz_id}/attempts",
        headers=enrolled_student_headers,
    )
    assert start.status_code == 200
    attempt_id = start.json()["id"]
    assert start.json()["status"] == "in_progress"
    attempt_version_id = start.json()["quiz_version_id"]

    items = seeded_db.scalars(
        select(QuizItem)
        .where(QuizItem.quiz_version_id == UUID(str(attempt_version_id)))
        .order_by(QuizItem.sequence)
    ).all()
    assert items
    answers = []
    for item in items:
        key = seeded_db.scalar(
            select(QuestionAnswerKey).where(
                QuestionAnswerKey.question_version_id == item.question_version_id
            )
        )
        assert key is not None and key.correct_option_label is not None
        answers.append(
            {
                "question_number": item.sequence,
                "selected_option_label": key.correct_option_label,
            }
        )

    submit = client.post(
        f"/api/v1/attempts/{attempt_id}/submit",
        headers=enrolled_student_headers,
        json={"answers": answers},
    )
    assert submit.status_code == 200, submit.text
    result = submit.json()
    assert result["status"] == "scored"
    assert float(result["score_percent"]) == 100.0
    assert result["passed"] is True
    assert len(result["answers"]) == len(questions)
    serialized = str(result)
    assert "correct_option_label" not in serialized
    assert "Answer Key" not in serialized

    fetched = client.get(f"/api/v1/attempts/{attempt_id}", headers=enrolled_student_headers)
    assert fetched.status_code == 200
    assert fetched.json()["score_percent"] == result["score_percent"]

    again = client.post(
        f"/api/v1/attempts/{attempt_id}/submit",
        headers=enrolled_student_headers,
        json={"answers": answers},
    )
    assert again.status_code == 409


def test_unenrolled_cannot_start_attempt(client: TestClient, seeded_db: Session) -> None:
    provision = client.post(
        "/api/v1/auth/provision-student",
        json={
            "email": "locked@example.com",
            "password": "password123",
            "full_name": "Locked",
            "student_identifier": "S-locked",
            "institution_name": POC_INSTITUTION_NAME,
        },
    )
    assert provision.status_code == 200
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "locked@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    subtopic = seeded_db.scalar(
        select(Subtopic).where(Subtopic.slug == "rectangles_squares_properties")
    )
    assert subtopic is not None
    quiz = seeded_db.scalar(
        select(CommonMasteryQuiz).where(CommonMasteryQuiz.subtopic_id == subtopic.id)
    )
    assert quiz is not None
    start = client.post(f"/api/v1/quizzes/{quiz.id}/attempts", headers=headers)
    assert start.status_code == 404


def test_teacher_cannot_start_attempt(client: TestClient, seeded_db: Session) -> None:
    _assign_poc_teacher(seeded_db)
    headers = _login(client, POC_TEACHER_EMAIL, POC_TEACHER_PASSWORD, POC_INSTITUTION_NAME)
    subtopic = seeded_db.scalar(
        select(Subtopic).where(Subtopic.slug == "rectangles_squares_properties")
    )
    assert subtopic is not None
    quiz = seeded_db.scalar(
        select(CommonMasteryQuiz).where(CommonMasteryQuiz.subtopic_id == subtopic.id)
    )
    assert quiz is not None
    start = client.post(f"/api/v1/quizzes/{quiz.id}/attempts", headers=headers)
    assert start.status_code == 403
    assert start.json()["detail"] == "Student enrollment required"
