import os

import pytest

from helpers import FakeClock, RecordingSink, load_fixture


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """Blare reads the environment, so tests must not inherit a real config."""
    for key in list(os.environ):
        if key.startswith("BLARE_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def reset_global_client():
    """Keep the module-level singleton from leaking between tests."""
    import blare

    yield
    blare.close()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def sink():
    return RecordingSink()


@pytest.fixture
def fixture():
    return load_fixture
