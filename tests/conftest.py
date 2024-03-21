from contextlib import contextmanager
import os
from pathlib import Path

_covalent_home = Path(__file__).resolve().parent / "covalent"
_COVALENT_ENV = {
    "COVALENT_CONFIG_DIR":str(_covalent_home / ".config/covalent"),
    # "COVALENT_LOGDIR":str(_covalent_home / ".cache/covalent"),
    # "COVALENT_EXECUTOR_DIR":str(_covalent_home / ".config/covalent/executor_plugins"),
    # "COVALENT_DISPATCH_CACHE_DIR":str(_covalent_home / ".cache/covalent/dispatches"),
    # "COVALENT_RESULTS_DIR":str(_covalent_home / ".cache/covalent/results"),
    # "COVALENT_CACHE_DIR":str(_covalent_home / ".cache/covalent"),
    # "COVALENT_DATABASE":str(_covalent_home / ".local/share/covalent/dispatcher_db.sqlite"),
    # # for some reason covalent is using COVALENT_DATABASE for both sqlite and
    # # qelectron databases so we use XDG_DATA_HOME as well
    # "XDG_DATA_HOME":str(_covalent_home / ".local/share/covalent/qelectron_db"),
    # "COVALENT_HEARTBEAT_FILE":str(_covalent_home / ".cache/covalent"),
}


@contextmanager
def env(env:dict):
    _env = os.environ.copy()
    try:
        for k,v in env.items():
            os.environ[k] = v
        yield
    finally:
        for k in os.environ:
            if k not in _env:
                del os.environ[k]
            else:
                os.environ[k] = _env[k]


# init and write covalent config with test env context
with env({
    **_COVALENT_ENV,
    "HOME":str(_covalent_home),
}):
    from covalent._shared_files.config import ConfigManager
    ConfigManager()
