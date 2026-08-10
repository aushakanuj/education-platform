from fastapi.testclient import TestClient

from education_platform.core.config import get_settings

STUDENT_EMAIL = "student@example.com"
STUDENT_PASSWORD = "password123"


def test_provision_login_me_refresh_logout(client: TestClient) -> None:
    provision = client.post(
        "/api/v1/auth/provision-student",
        json={
            "email": STUDENT_EMAIL,
            "password": STUDENT_PASSWORD,
            "full_name": "Test Student",
            "student_identifier": "S-100",
        },
    )
    assert provision.status_code == 200
    body = provision.json()
    assert body["email"] == STUDENT_EMAIL
    assert "student" in body["roles"]
    assert body["student_profile_id"]

    bad = client.post(
        "/api/v1/auth/login",
        json={"email": STUDENT_EMAIL, "password": "wrong-password"},
    )
    assert bad.status_code == 401

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": STUDENT_EMAIL,
            "password": STUDENT_PASSWORD,
            "institution_name": "POC Demo School",
        },
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == STUDENT_EMAIL

    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refreshed.json()["refresh_token"]},
    )
    assert logout.status_code == 204


def test_unauthenticated_materials_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/materials").status_code == 401


def test_seeded_admin_login_and_learning_directory(client: TestClient) -> None:
    settings = get_settings()
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": settings.demo_admin_email,
            "password": settings.demo_admin_password,
            "institution_name": "POC Demo School",
        },
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == settings.demo_admin_email
    assert "administrator" in body["roles"]
    assert body["student_profile_id"] is None

    directory = client.get("/api/v1/me/learning-directory", headers=headers)
    assert directory.status_code == 200
    subjects = directory.json()["subjects"]
    assert len(subjects) == 1
    assert subjects[0]["code"] == "MATH"
