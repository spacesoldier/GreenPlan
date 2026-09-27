import pytest
from fastapi.testclient import TestClient

from greenplan_api.fixtures import fixture_repository
from greenplan_api.main import create_app


@pytest.fixture
def repository():
    return fixture_repository()


@pytest.fixture
def client(repository) -> TestClient:
    return TestClient(create_app(repository=repository))
