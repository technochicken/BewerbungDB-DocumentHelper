import pytest


@pytest.fixture(autouse=True)
def isolated_user_dirs(tmp_path_factory, monkeypatch):
    """Tests dürfen nie in den echten Benutzerordnern (~/Documents, %APPDATA%) schreiben."""
    fake_home = tmp_path_factory.mktemp("userhome")
    for var in ("USERPROFILE", "HOME"):
        monkeypatch.setenv(var, str(fake_home))
    monkeypatch.setenv("APPDATA", str(fake_home / "AppData"))
