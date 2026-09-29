from tests.conftest import alembic


def test_upgrade_downgrade_roundtrip_and_no_model_drift(test_urls: tuple[str, str]) -> None:
    _, mig = test_urls
    assert alembic(mig, "upgrade", "head").returncode == 0
    check = alembic(mig, "check")
    assert check.returncode == 0, check.stdout + check.stderr
    assert alembic(mig, "downgrade", "base").returncode == 0
    assert alembic(mig, "upgrade", "head").returncode == 0
