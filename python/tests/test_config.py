import pytest

from blare.config import Config, derive_service_name
from blare.errors import ConfigError


def test_defaults_match_the_spec():
    config = Config.from_env()
    assert config.level == "ERROR"
    assert config.dedupe_window == 300
    assert config.max_per_hour == 20
    assert config.state == "file"
    assert config.resolve_after == 0
    assert config.stack_frames == 12
    assert config.timeout == 5
    assert config.environment == "unknown"
    assert config.enabled is True
    assert config.dry_run is False


def test_sinks_are_split_and_trimmed(monkeypatch):
    monkeypatch.setenv("BLARE_SINKS", " https://a.example/x , https://b.example/y ,")
    assert Config.from_env().sinks == ["https://a.example/x", "https://b.example/y"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
    ],
)
def test_boolean_forms(monkeypatch, raw, expected):
    monkeypatch.setenv("BLARE_ENABLED", raw)
    assert Config.from_env().enabled is expected


def test_a_bad_boolean_is_fatal(monkeypatch):
    """A misread setting must not look like a working install."""
    monkeypatch.setenv("BLARE_ENABLED", "maybe")
    with pytest.raises(ConfigError, match="not a boolean"):
        Config.from_env()


def test_a_bad_integer_is_fatal(monkeypatch):
    monkeypatch.setenv("BLARE_DEDUPE_WINDOW", "five minutes")
    with pytest.raises(ConfigError, match="not an integer"):
        Config.from_env()


def test_a_negative_window_is_fatal(monkeypatch):
    monkeypatch.setenv("BLARE_DEDUPE_WINDOW", "-1")
    with pytest.raises(ConfigError, match="must be >="):
        Config.from_env()


def test_a_bad_level_is_fatal(monkeypatch):
    monkeypatch.setenv("BLARE_LEVEL", "LOUD")
    with pytest.raises(ConfigError, match="not a level"):
        Config.from_env()


def test_lowercase_level_is_accepted(monkeypatch):
    monkeypatch.setenv("BLARE_LEVEL", "warning")
    assert Config.from_env().level == "WARNING"


def test_overrides_beat_the_environment(monkeypatch):
    monkeypatch.setenv("BLARE_SERVICE", "from-env")
    assert Config.from_env(service="from-code").service == "from-code"


def test_an_unknown_override_is_fatal():
    with pytest.raises(ConfigError, match="unknown setting"):
        Config.from_env(not_a_setting=1)


def test_platform_service_name_wins(monkeypatch):
    monkeypatch.setenv("FLY_APP_NAME", "checkout-api")
    assert derive_service_name() == "checkout-api"


def test_platform_order_is_respected(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "cloud-run-name")
    monkeypatch.setenv("FLY_APP_NAME", "fly-name")
    assert derive_service_name() == "cloud-run-name"


def test_inactive_without_sinks():
    assert Config.from_env().active is False


def test_active_with_a_sink(monkeypatch):
    monkeypatch.setenv("BLARE_SINKS", "console")
    assert Config.from_env().active is True


def test_disabled_overrides_sinks(monkeypatch):
    monkeypatch.setenv("BLARE_SINKS", "console")
    monkeypatch.setenv("BLARE_ENABLED", "0")
    assert Config.from_env().active is False
