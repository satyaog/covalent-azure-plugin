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

"""Azure executor plugin for the Covalent dispatcher."""

import asyncio
import copy
from dataclasses import dataclass
import functools
import glob
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
from typing import Any, Callable, Coroutine, Dict, List

import covalent as ct
from covalent._shared_files import logger
from covalent._shared_files.config import get_config
from covalent._shared_files.exceptions import TaskCancelledError
from covalent_ssh_plugin.ssh import _EXECUTOR_PLUGIN_DEFAULTS as _SSH_EXECUTOR_PLUGIN_DEFAULTS
from covalent_ssh_plugin.ssh import SSHExecutor

executor_plugin_name = "AzureExecutor"

app_log = logger.app_log
log_stack_info = logger.log_stack_info

_EXECUTOR_PLUGIN_DEFAULTS = copy.deepcopy(_SSH_EXECUTOR_PLUGIN_DEFAULTS)
_EXECUTOR_PLUGIN_DEFAULTS.update(
    {
        "username": "ubuntu",
        "hostname": "",
        "location": "eastus2",
        "size": "Standard_B2ats_v2",
        "disk_size": 64,
        "state_prefix": "",
        "state_id": "",
        "cluster_size": 1,
        "keep_alive": False,
        "conda_env": "covalent",
        "_skip_setup": None,
    }
)


@dataclass
class FakeTransportableObject:
    obj:Any

    def get_deserialized(self):
        return self.obj


class AzureExecutor(SSHExecutor):
    """
    Executor class that invokes the input function on an Azure Virtual Machine instance
    Args:
        location: The Azure Region where the Resource Group should exist
        size: The SKU which should be used for the Virtual Machine.
        state_prefix: Prefix to use in the Terrform state file name
        state_id: Id to use in the Terrform state file name
        cluster_size: The number of Virtual Machines in the cluster.
        keep_alive: Keep the cloud instance running
    """

    _TF_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "infra"))

    def __init__(
        self,
        username: str = "ubuntu",
        hostname: str = None,
        location: str = "eastus2",
        size: str = "Standard_B2ats_v2",
        disk_size: int = 64,
        state_prefix: str = "",
        state_id: str = "",
        keep_alive: bool = False,
        cluster_size: int = 1,
        conda_env: str = "covalent",
        ssh_key_file: str = None,
        cache_dir: str = None,
        python_path: str = "",
        remote_cache: str = "",
        run_local_on_ssh_fail: bool = False,
        poll_freq: int = 15,
        do_cleanup: bool = True,
        remote_workdir: str = "",
        create_unique_workdir: bool = None,
        _skip_setup: bool = False,
    ) -> None:
        username = username or get_config("executors.azure.username")
        hostname = hostname or get_config("executors.azure.hostname")

        SSHExecutor.__init__(
            self=self,
            username=username,
            hostname=hostname,
            conda_env=conda_env,
            ssh_key_file=ssh_key_file,
            cache_dir=cache_dir,
            python_path=python_path,
            remote_cache=remote_cache,
            run_local_on_ssh_fail=run_local_on_ssh_fail,
            poll_freq=poll_freq,
            do_cleanup=do_cleanup,
            remote_workdir=remote_workdir,
            create_unique_workdir=create_unique_workdir,
        )

        # as executor instance is reconstructed the below values are seemingly lost, added back here as a temp fix
        self.hostnames = []
        self.private_ips = []
        self.env = None
        self.location = location or get_config("executors.azure.location")
        self.size = size or get_config("executors.azure.size")
        self.disk_size = disk_size or get_config("executors.azure.disk_size")
        self.conda_env = conda_env or get_config("executors.azure.conda_env")

        self.python3_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        # TODO: Remove this once AWSExecutor has a `covalent_version` attribute
        # Setting covalent version to be used in the EC2 instance
        self.covalent_version = ct.__version__
        self.infra_vars = []
        self.state_prefix = state_prefix or get_config("executors.azure.state_prefix")
        self.state_id = state_id or get_config("executors.azure.state_id")
        self.cluster_size = cluster_size
        self.keep_alive = keep_alive if keep_alive is not None else get_config("executors.azure.keep_alive")
        self._skip_setup = _skip_setup

    @classmethod
    @functools.cache
    def _executor_args_placeholder(cls):
        return hashlib.sha256(
            bytes(
                str(cls).replace(f"{cls.__module__}.", ""),
                "utf8"
            )
        ).hexdigest()

    @property
    def executor_args_placeholder(self):
        return self._executor_args_placeholder()

    def get_connection_attributes(self):
        @ct.electron(executor=self)
        def _(executor:AzureExecutor):
            executor, task_metadata = executor
            return (
                executor._get_connection_attributes(),
                task_metadata
            )
        _.__name__ = self.get_connection_attributes.__name__
        return _(self.executor_args_placeholder)

    def _get_connection_attributes(self):
        return {
            hostname: {
                "hostname":hostname,
                "username":self.username,
                "ssh_key_file":self.ssh_key_file,
                "private_ip":private_ip,
                "env":self.env,
                "python_path":self.python_path,
            }
            for hostname, private_ip in zip(self.hostnames, self.private_ips or self.hostnames)
        }

    def list_running_instances(self):
        executor = AzureExecutor()
        executor.from_dict(self.to_dict())
        executor._skip_setup = True
        executor.keep_alive = True

        @ct.electron(executor=executor)
        def _(executor:AzureExecutor):
            executor, task_metadata = executor

            running_instances = {}

            dummy_executor = AzureExecutor()
            for state_file in glob.glob(
                executor._get_tf_statefile_path(task_metadata)
            ):
                dummy_executor._set_state_id(state_file)
                dummy_executor.update_connection_attributes(state_file)
                running_instances[
                    (dummy_executor.state_prefix, dummy_executor.state_id)
                ] = dummy_executor._get_connection_attributes()
            return running_instances
        _.__name__ = self.list_running_instances.__name__
        return _(executor.executor_args_placeholder)

    def cp_to_remote(self, src:str, dest:str):
        executor = AzureExecutor()
        executor.from_dict(self.to_dict())
        executor._skip_setup = True
        executor.keep_alive = True

        @ct.electron(executor=executor)
        def _(executor:AzureExecutor):
            executor, task_metadata = executor

            state_file = executor._get_tf_statefile_path(task_metadata)
            executor.update_connection_attributes(state_file)

            rsync = ct.fs_strategies.Rsync(
                user=executor.username,
                host=executor.hostname,
                private_key_path=executor.ssh_key_file
            )
            _, transfer = ct.fs.TransferToRemote(src, dest, strategy=rsync).cp()
            transfer()
        _.__name__ = self.cp_to_remote.__name__
        return _(executor.executor_args_placeholder)

    def stop_cloud_instance(self) -> tuple:
        executor = AzureExecutor()
        executor.from_dict(self.to_dict())
        executor._skip_setup = True

        @ct.electron(executor=executor)
        def _(executor:AzureExecutor, wait_for:Any=None):
            """
            Args:
                wait_for: Wait for the result of previous electron results
            """
            executor, _ = executor
            executor.keep_alive = False
            return wait_for
        _.__name__ = self.stop_cloud_instance.__name__

        dispatch_id = ct.dispatch(
            ct.lattice(
                lambda:_(executor.executor_args_placeholder, executor.list_running_instances())
            ),
            disable_run=False
        )()

        return ct.get_result(dispatch_id=dispatch_id, wait=True)

    async def _run_async_subprocess(self, cmd: List[str], cwd=None, log_output: bool = False):
        proc = await asyncio.create_subprocess_shell(
            " ".join(cmd), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
        )

        try:
            if log_output:
                stdout_chunks = []
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode("utf-8").strip()
                    stdout_chunks.append(line_str)
                    app_log.debug(line_str)

                _, stderr = await proc.communicate()
                stderr = stderr.decode("utf-8").strip()
                stdout = os.linesep.join(stdout_chunks)

            else:
                stdout, stderr = await proc.communicate()
                stdout = stdout.decode("utf-8").strip()
                stderr = stderr.decode("utf-8").strip()
        except asyncio.CancelledError:
            proc.terminate()
            raise

        if proc.returncode != 0:
            app_log.debug(stderr)
            raise subprocess.CalledProcessError(proc.returncode, cmd, stdout, stderr)

        return proc, stdout, stderr

    async def _run_or_retry(self, *args, ignore_cancel=False, timeout=20*60, **kwargs):
        err = None
        task = asyncio.create_task(self._run_async_subprocess(*args, **kwargs))
        t =- time.time()
        while True:
            elapsed = t + time.time()

            await asyncio.sleep(1 - (t + time.time())%1)

            try:
                task.result()
                break
            # Task is still running and result cannot be fetch
            except asyncio.exceptions.InvalidStateError:
                if not ignore_cancel and await self.get_cancel_requested():
                    task.cancel()
                    raise TaskCancelledError
            except subprocess.CalledProcessError as _:
                err = _
                if "Error acquiring the state lock" not in err.stderr:
                    raise

            if elapsed >= timeout:
                raise err or TimeoutError(
                    f"Could not complete command within {timeout} secs"
                    f"({elapsed:.2f}s elapsed)"
                )
            elif task.done():
                # Retry until lock is aquired
                task = asyncio.create_task(self._run_async_subprocess(*args, **kwargs))

    def _get_state_id(self, task_metadata: Dict=None) -> str:
        prefix = self.state_prefix or task_metadata["node_id"]
        id = self.state_id or task_metadata["dispatch_id"]
        return f"{prefix}-{id.replace('-', '')}"

    def _set_state_id(self, state_file: str) -> None:
        state_file_parts = pathlib.Path(state_file).stem.split("-")
        self.state_id = state_file_parts.pop()
        # pop "azure-"
        state_file_parts.pop(0)
        self.state_prefix = "-".join(state_file_parts)

    def _get_tf_statefile_path(self, task_metadata:dict) -> str:
        state_id = self._get_state_id(task_metadata)
        return f"{self._TF_DIR}/azure-{state_id}.tfstate"

    def _get_tf_output(self, var: str, state_file: str) -> str:
        try:
            result = subprocess.run(
                ["terraform", "output", "-raw", f"-state={state_file}", var],
                cwd=self._TF_DIR,
                stdout=subprocess.PIPE,
                encoding="utf8",
                check=True
            )
            value = result.stdout
        except subprocess.CalledProcessError:
            result = subprocess.run(
                ["terraform", "output", "-json", f"-state={state_file}", var],
                cwd=self._TF_DIR,
                stdout=subprocess.PIPE,
                encoding="utf8",
                check=True
            )
            value = json.loads(result.stdout)
        return value

    def _get_infra_vars(self, task_metadata):
        return {
            "name": f"covalent-azure-task-{self._get_state_id(task_metadata)}",
            "username": f"{self.username}",
            "location": f"{self.location}",
            "size": f"{self.size}",
            "disk_size_gb": f"{self.disk_size}",
            "cluster_size": (f"{self.cluster_size}" if self.cluster_size else "1"),
            "python3_version": f"{self.python3_version}",
            "covalent_version": f"{self.covalent_version}",
        }

    def update_connection_attributes(self, state_file: str):
        # Update attributes from Terraform Output
        self.hostnames = self._get_tf_output("hostnames", state_file)
        self.private_ips = self._get_tf_output("private_ips", state_file)
        if not self.hostname:
            # Use the master node if hostname is not defined
            self.hostname = self._get_tf_output("hostname", state_file)
        self.username = self._get_tf_output("username", state_file)
        self.ssh_key_file = self._get_tf_output("ssh_key", state_file)
        self.env = self._get_tf_output("env", state_file)
        self.python_path = self._get_tf_output("python_path", state_file)

        self.ssh_key_file = str(pathlib.Path(self.ssh_key_file).expanduser())

    async def setup(self, task_metadata: Dict) -> None:
        """
        Invokes Terraform to provision supporting resources for the instance
        """
        if self._skip_setup:
            return

        state_file = self._get_tf_statefile_path(task_metadata)

        if "*" in state_file:
            found_state_files = list(glob.glob(state_file))
            assert len(found_state_files) == 1, (
                f"Could not find a state file at {state_file} or too many files "
                f"found {found_state_files}"
            )
            state_file = found_state_files[0]
            self._set_state_id(state_file)

        # Init Terraform (doing this in a blocking manner to avoid race
        # conditions during init, better way would to be use asyncio locks or to
        # ensure that terraform init is run just once)
        subprocess.run(["terraform init"], cwd=self._TF_DIR, shell=True, check=True)

        # Apply Terraform Plan
        base_cmd = [
            "terraform",
            "apply",
            "-auto-approve",
            f"-state={state_file}",
            "-lock-timeout=60s",
        ]

        self.infra_vars = self._get_infra_vars(task_metadata)
        infra_vars = [f"-var={k}={v}" for k, v in self.infra_vars.items()]

        cmd = base_cmd + infra_vars
        app_log.debug(f"Running Terraform setup command: {cmd}")
        await self._run_or_retry(cmd, cwd=self._TF_DIR, log_output=True)

        self.update_connection_attributes(state_file)

    async def run(
        self, function: Callable, args: list, kwargs: dict, task_metadata: Dict
    ) -> Coroutine:
        args_placeholder_id = ct.TransportableObject(self.executor_args_placeholder)

        for i, arg in enumerate(args):
            if arg == args_placeholder_id:
                args[i] = FakeTransportableObject((self, task_metadata))
                return function(*args, **kwargs)

        for k, arg in kwargs.items():
            if arg == args_placeholder_id:
                kwargs[k] = FakeTransportableObject((self, task_metadata))
                return function(*args, **kwargs)

        return await super().run(function, args, kwargs, task_metadata)

    async def teardown(self, task_metadata: Dict) -> None:
        """
        Invokes Terraform to terminate the instance and teardown supporting resources
        """
        if self.keep_alive:
            app_log.debug(f"Keep alive after {task_metadata} ({vars(self)})")
            return
        app_log.debug(f"Teardown after {task_metadata} ({vars(self)})")

        state_file = self._get_tf_statefile_path(task_metadata)

        found_state_files = list(glob.glob(state_file))

        for state_file in found_state_files:
            if not os.path.exists(state_file):
                raise FileNotFoundError(
                    f"Could not find Terraform state file: {state_file}. Infrastructure may need to be manually deprovisioned."
                )

            base_cmd = ["terraform", "destroy", "-auto-approve", f"-state={state_file}", "-lock-timeout=60s"]
            self._set_state_id(state_file)
            infra_vars = self._get_infra_vars(task_metadata)
            infra_vars = [f"-var={k}={v}" for k, v in infra_vars.items()]
            cmd = base_cmd + infra_vars

            app_log.debug(f"Running teardown Terraform command: {cmd}")

            await self._run_or_retry(cmd, cwd=self._TF_DIR, log_output=True, ignore_cancel=True)

            # Delete the state file
            os.remove(state_file)
            os.remove(f"{state_file}.backup")
