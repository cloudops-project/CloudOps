from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.gettempdir()) / 'cloudops_stage1_tests.db'}"
os.environ["JWT_SECRET_KEY"] = "testing-only-secret-key-with-at-least-32-characters"
os.environ["COOKIE_SECURE"] = "false"
os.environ["REMEDIATION_EXECUTION_ENABLED"] = "true"
os.environ["AWS_TRUSTED_PRINCIPAL_ARN"] = "arn:aws:iam::111122223333:role/CloudOpsServiceRole"

import pytest
from fastapi.testclient import TestClient
from pytest import FixtureRequest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app

engine = create_engine(os.environ["DATABASE_URL"], connect_args={"check_same_thread": False})
TestingSession = sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def database(request: FixtureRequest) -> Generator[None, None, None]:
    if request.node.get_closest_marker("postgres_only"):
        yield
        return
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    with TestingSession() as session:
        yield session


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    def override() -> Generator[Session, None, None]:
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_db_session] = override
    app.dependency_overrides[get_settings] = get_settings
    test_client = TestClient(app, base_url="http://testserver")
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def user_payload() -> dict[str, str]:
    return {
        "email": "owner@example.com",
        "password": "Strong-Password-123!",
        "full_name": "Owner User",
    }


def register_and_login(client: TestClient, email: str = "owner@example.com") -> dict[str, str]:
    password = "Strong-Password-123!"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201, response.text
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
