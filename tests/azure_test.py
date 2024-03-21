# Copyright 2021 Agnostiq Inc.
#
# This file is part of Covalent.
#
# Licensed under the Apache License 2.0 (the "License"). A copy of the
# License may be obtained with this software package or at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Use of this file is prohibited except in compliance with the License.
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Ignore results folders

import os
from pathlib import Path
from subprocess import CalledProcessError
import time
from unittest import mock

import covalent as ct
from covalent._shared_files.exceptions import TaskCancelledError
import pytest

from covalent_azure_plugin import azure


@pytest.fixture
def executor():
    azure_exec = azure.AzureExecutor(**{})
    return azure_exec


@pytest.mark.asyncio
async def test_cancel():
    executor = azure.AzureExecutor(**{})
    with pytest.raises(NotImplementedError):
        await executor.cancel()


def test_get_connection_attributes(mocker):
    executor = azure.AzureExecutor(**{})
    mock_task_metadata = {"dispatch_id": "123", "node_id": 1}

    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._executor_args_placeholder",
        lambda self:(self, mock_task_metadata)
    )

    executor.hostname = "hostname1"
    executor.hostnames = ["hostname1", "hostname2"]
    executor.username = "username"
    executor.ssh_key_file = "ssh_key_file"
    executor.env = "env"
    executor.python_path = "python_path"

    connection_attributes, task_metadata = executor.get_connection_attributes()

    assert set(connection_attributes) == set(executor.hostnames)
    for hostname, _connection_attributes in connection_attributes.items():
        _connection_attributes["hostname"] == hostname
        _connection_attributes["username"] == executor.username
        _connection_attributes["ssh_key_file"] == executor.ssh_key_file
        _connection_attributes["env"] == executor.env
        _connection_attributes["python_path"] == executor.python_path

    assert task_metadata == mock_task_metadata


def test_list_running_instances(mocker: mock, tmp_path: Path):
    executor = azure.AzureExecutor(**{})

    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._TF_DIR",
        str(tmp_path)
    )
    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._executor_args_placeholder",
        lambda self:(self, {"dispatch_id": "123", "node_id": 0})
    )
    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._get_tf_output",
        lambda *args:args[1]
    )

    state_files = [
        executor._get_tf_statefile_path({"dispatch_id": "321", "node_id": 1}),
        executor._get_tf_statefile_path({"dispatch_id": "321", "node_id": 2})
    ]

    for state_file in state_files:
        Path(state_file).touch()

    running_instances = executor.list_running_instances()

    for (prefix, id), _ in running_instances.items():
        executor.state_prefix = prefix
        executor.state_id = id
        assert executor._get_tf_statefile_path({}) in state_files


@pytest.mark.parametrize(
    "config,task_metadata,expected",
    [
        ({"state_prefix":"prefix", "state_id":"id"}, {"dispatch_id": "123", "node_id": 1}, "prefix-id"),
        ({"state_prefix":"prefix"}, {"dispatch_id": "123", "node_id": 1}, "prefix-123"),
        ({"state_id":"long-long-id"}, {"dispatch_id": "123", "node_id": 1}, "1-longlongid"),
        ({}, {"dispatch_id": "123", "node_id": 1}, "1-123"),
    ]
)
def test__get_state_id(config:dict, task_metadata:dict, expected):
    executor = azure.AzureExecutor(**config)
    assert executor._get_state_id(task_metadata) == expected


@pytest.mark.parametrize(
    "config,state_file,expected_prefix,expected_id",
    [
        ({"state_prefix":"config-prefix", "state_id":"config-id"}, "dir/dir/azure-prefix-id", "prefix", "id"),
        ({"state_prefix":"config-prefix", "state_id":"config-id"}, "dir/dir/azure-long-long-prefix-longlongid", "long-long-prefix", "longlongid"),
    ]
)
def test__set_state_id(config:dict, state_file:str, expected_prefix:str, expected_id:str):
    executor = azure.AzureExecutor(**config)
    executor._set_state_id(state_file)
    assert executor.state_prefix == expected_prefix
    assert executor.state_id == expected_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state_filenames",
    [
        ["state-prefix-id.tfstate", "state-prefix-id.tfstate"],
        ["state-*-id.tfstate", "state-prefix-id.tfstate"],
        ["state-*-id.tfstate", "state-prefix-id.tfstate", "state-prefix2-id.tfstate"],
    ]
)
async def test_setup(state_filenames: list, executor:azure.AzureExecutor, mocker: mock, tmp_path: Path):
    """Test validation of key file and setup."""

    INFRA_VARS = {"mock_var":"123"}
    MOCK_TF_VAR_OUTPUT = "mocked_tf_output"

    mock_task_metadata = {"dispatch_id": "123", "node_id": 1}

    state_file:Path = tmp_path / state_filenames.pop(0)
    for _state_file in state_filenames:
        (tmp_path / _state_file).touch()

    subprocess_mock: mock.MagicMock = mocker.patch("covalent_azure_plugin.azure.subprocess")

    run_async_process_mock = mock.AsyncMock()
    get_tf_output_mock = mock.Mock()
    get_tf_output_mock.return_value = MOCK_TF_VAR_OUTPUT
    get_infra_vars = mock.Mock()
    get_infra_vars.return_value = INFRA_VARS

    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._run_async_subprocess",
        side_effect=run_async_process_mock,
    )
    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._get_tf_output",
        side_effect=get_tf_output_mock,
    )
    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._get_infra_vars",
        side_effect=get_infra_vars,
    )

    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._get_tf_statefile_path", return_value=str(state_file)
    )

    if len(state_filenames) > 1:
        with pytest.raises(AssertionError):
            await executor.setup(mock_task_metadata)
        return
    else:
        await executor.setup(mock_task_metadata)

    get_infra_vars.assert_called_once()

    assert executor.infra_vars == INFRA_VARS
    assert executor.hostname == MOCK_TF_VAR_OUTPUT
    assert executor.hostnames == MOCK_TF_VAR_OUTPUT
    assert executor.username == MOCK_TF_VAR_OUTPUT
    assert executor.ssh_key_file == MOCK_TF_VAR_OUTPUT
    assert executor.env == MOCK_TF_VAR_OUTPUT
    assert executor.python_path == MOCK_TF_VAR_OUTPUT

    if "*" in state_file.name:
        assert executor.state_prefix == "prefix"
        assert executor.state_id == "id"

    run_async_process_mock.assert_called_once()

    subprocess_mock.run.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args,kwargs",
    [
        (["a1", "a2"],{"k3":3,"k4":4}),
        (["a1", ct.TransportableObject(azure.AzureExecutor._executor_args_placeholder()), "a2"],{"k3":3,"k4":4}),
        (["a1", None, "a2"],{"k3":3,"k_executor":ct.TransportableObject(azure.AzureExecutor._executor_args_placeholder()),"k4":4}),
    ]
)
async def test_run(args: list, kwargs:dict, mocker: mock):
    executor = azure.AzureExecutor(**{})
    mock_task_metadata = {"dispatch_id": "123", "node_id": 1}
    run_mock: mock.Mock = mocker.patch(
        "covalent_ssh_plugin.ssh.SSHExecutor.run",
    )
    test_is_called = "test() is called"
    def test(a1=None, _executor:azure.FakeTransportableObject=None, a2=None, **kwargs):
        _executor, _mock_task_metadata = (_executor or kwargs["k_executor"]).obj
        assert _executor is executor
        assert _mock_task_metadata is mock_task_metadata
        return test_is_called
    if await executor.run(test, args, kwargs, mock_task_metadata) == test_is_called:
        run_mock.assert_not_called()
    else:
        run_mock.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("keep_alive","state_files"),
    [
        (keep_alive, state_files)
        for keep_alive in (True, False)
        for state_files in (["state-prefix-id.tfstate"], [f"state-{i}-id.tfstate" for i in range(5)])
    ]
)
async def test_teardown(keep_alive: bool, state_files: list, mocker: mock, tmp_path: Path):
    MOCK_TF_VAR_OUTPUT = "mocked_tf_output"

    mock_task_metadata = {"dispatch_id": "123", "node_id": 1}

    executor = azure.AzureExecutor(keep_alive=keep_alive)

    state_files = [tmp_path / _ for _ in state_files]
    for _f in state_files:
        _f.touch()
        _f.with_name(f"{_f.name}.backup").touch()

    state_file = str(state_files.pop())
    not_existing_state_file = str(tmp_path / "dne.tfstate")

    executor.infra_vars = {"mock_var":"123"}

    get_tf_output_mock = mock.AsyncMock()
    get_tf_output_mock.return_value = MOCK_TF_VAR_OUTPUT
    run_async_process_mock = mock.AsyncMock()
    run_async_process_mock.return_value = (None, None, None)

    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._run_async_subprocess",
        side_effect=run_async_process_mock,
    )
    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._get_tf_output",
        side_effect=get_tf_output_mock,
    )
    mock_os_remove:mock.Mock = mocker.patch(
        "covalent_azure_plugin.azure.os.remove",
        side_effect=os.remove
    )

    if executor.keep_alive:
        get_tf_statefile_path_mock:mock.Mock = mocker.patch(
            "covalent_azure_plugin.azure.AzureExecutor._get_tf_statefile_path",
        )
        await executor.teardown(mock_task_metadata)
        get_tf_statefile_path_mock.assert_not_called()
        run_async_process_mock.assert_not_called()
        return

    # tfstate does not exist
    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._get_tf_statefile_path",
        return_value=not_existing_state_file,
    )
    await executor.teardown(mock_task_metadata)
    run_async_process_mock.assert_not_called()

    # tfstate exist
    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._get_tf_statefile_path",
        return_value=state_file,
    )
    await executor.teardown(mock_task_metadata)
    run_async_process_mock.assert_called_once()
    mock_os_remove.assert_any_call(state_file)
    mock_os_remove.assert_any_call(f"{state_file}.backup")
    run_async_process_mock.reset_mock()
    mock_os_remove.reset_mock()

    # glob tfstate
    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor._get_tf_statefile_path",
        return_value=str(tmp_path / "state-*.tfstate"),
    )

    await executor.teardown(mock_task_metadata)
    assert run_async_process_mock.call_count == len(state_files)
    assert mock_os_remove.call_count == len(state_files) * 2


def test_upload_task():
    pass


def test_submit_task():
    pass


def test_get_status():
    pass


def test_poll_task():
    pass


def test_query_result():
    pass


@pytest.mark.timeout(10)
@pytest.mark.asyncio
async def test__run_or_retry(executor:azure.AzureExecutor, mocker: mock):
    mocker.patch(
        "covalent_azure_plugin.azure.AzureExecutor.get_cancel_requested",
        return_value=False
    )

    # Do not catch CalledProcessError
    with pytest.raises(CalledProcessError):
        # Set a timeout bigger than the timeout of this test's timeout to make
        # sure we didn't wait
        await executor._run_or_retry(["exit", "1"], timeout=10)

    # Raise TimeoutError on timeout
    with pytest.raises(TimeoutError):
        await executor._run_or_retry(["sleep", "10"], timeout=1)

    with mock.patch(
        "covalent_azure_plugin.azure.AzureExecutor.get_cancel_requested",
        return_value=True
    ):
        # Raise TaskCancelledError on task cancel
        with pytest.raises(TaskCancelledError):
            await executor._run_or_retry(["sleep", "10"], timeout=10)

        # Ignore task cancel signal
        await executor._run_or_retry(["sleep", "1"], ignore_cancel=True, timeout=10)

    async def raise_state_lock_error(_, cmd, *_args, **_kwargs):
        raise CalledProcessError(
            1,
            cmd,
            None,
            '\x1b[31m╷\x1b[0m\x1b[0m\n\x1b[31m│\x1b[0m \x1b[0m\x1b[1m\x1b[31mError: \x1b[0m\x1b[0m\x1b[1mError acquiring the st'
            'ate lock\x1b[0m\n\x1b[31m│\x1b[0m \x1b[0m\n\x1b[31m│\x1b[0m \x1b[0m\x1b[0mError message: resource temporar'
            'ily unavailable\n\x1b[31m│\x1b[0m \x1b[0mLock Info:\n\x1b[31m│\x1b[0m \x1b[0m  ID:        6797897b-8'
            'd87-5743-d5ad-02eba7006d1c\n\x1b[31m│\x1b[0m \x1b[0m  Path:      /Users/satyaortiz-gagne/t'
            'ravail/mila/CODE/covalent-azure-plugin/covalent_azure_plugin/infra/azure-test-sa'
            'tyaortiz-gagne-test_keep_alive_True_0.tfstate\n\x1b[31m│\x1b[0m \x1b[0m  Operation: Operat'
            'ionTypeApply\n\x1b[31m│\x1b[0m \x1b[0m  Who:       satyaortiz-gagne@MacBook-Pro-de-Mila.lo'
            'cal\n\x1b[31m│\x1b[0m \x1b[0m  Version:   1.7.3\n\x1b[31m│\x1b[0m \x1b[0m  Created:   2024-05-15 21:'
            '04:42.437818 +0000 UTC\n\x1b[31m│\x1b[0m \x1b[0m  Info:      \n\x1b[31m│\x1b[0m \x1b[0m\n\x1b[31m│\x1b[0m \x1b'
            '[0m\n\x1b[31m│\x1b[0m \x1b[0mTerraform acquires a state lock to protect the state from bei'
            'ng written\n\x1b[31m│\x1b[0m \x1b[0mby multiple users at the same time. Please resolve the'
            ' issue above and try\n\x1b[31m│\x1b[0m \x1b[0magain. For most commands, you can disable lo'
            'cking with the "-lock=false"\n\x1b[31m│\x1b[0m \x1b[0mflag, but this is not recommended.\n\x1b'
            '[31m╵\x1b[0m\x1b[0m'
        )

    timeout = 2
    with mock.patch(
        "covalent_azure_plugin.azure.AzureExecutor._run_async_subprocess",
        raise_state_lock_error
    ), pytest.raises(CalledProcessError):
        t =- time.time()
        # Wait if getting "Error acquiring the state lock"
        await executor._run_or_retry([], timeout=timeout)
    t += time.time()
    assert t >= timeout
    # There's a grace period of 1s before timeout
    assert t < timeout + 1.1
