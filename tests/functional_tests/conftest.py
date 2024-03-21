import getpass
from pathlib import Path
import subprocess
from unittest import mock
import pytest

import covalent as ct
from covalent._shared_files.config import ConfigManager

from ..conftest import _COVALENT_ENV, env


@pytest.fixture(scope="module")
def executor():
    executor = ct.executor.AzureExecutor(
        size="Standard_B1s",
        keep_alive=True,
        state_prefix=f"test-{getpass.getuser()}",
        state_id = Path(__file__).parent.name
    )
    try:
        yield executor
    finally:
        # Remove all tests instances if any
        executor.state_id = "*"
        result = executor.stop_cloud_instance()
        assert len(result.result) == 0


@pytest.fixture(scope="function", autouse=True)
def covalent_config_manager(mocker: mock):
    with env(_COVALENT_ENV):
        _config_manager = ConfigManager()
    mocker.patch(
        "covalent._shared_files.config._config_manager",
        _config_manager
    )
    ct.set_config("sdk.log_level", "info")
    yield


@pytest.fixture(scope="module", autouse=True)
def server():
    with env(_COVALENT_ENV):
        subprocess.run([
            "covalent",
            "start",
            "--port", "49010",
            "--develop"
        ])
    yield
