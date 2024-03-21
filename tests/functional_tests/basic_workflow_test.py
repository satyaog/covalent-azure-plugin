import getpass
from pathlib import Path
import covalent as ct
import pytest

from covalent_azure_plugin.azure import AzureExecutor

pytestmark = pytest.mark.timeout(10*60)


@pytest.mark.timeout(20*60)
@pytest.mark.asyncio
@pytest.mark.functional_tests
@pytest.mark.parametrize(
    ("keep_alive"),
    [True, False]
)
async def test_keep_alive(executor:AzureExecutor, keep_alive, tmp_path: Path):
    _executor = executor
    executor:AzureExecutor = ct.executor.AzureExecutor()
    executor.from_dict(_executor.to_dict())
    executor.state_id = tmp_path.name

    dispatch_ids = set()
    try:
        hostnames = set()
        for i in range(2):
            dispatch_id = ct.dispatch(
                ct.lattice(executor.get_connection_attributes), disable_run=False
            )()
            dispatch_ids.add(dispatch_id)

            result = ct.get_result(dispatch_id=dispatch_id, wait=True)
            status = str(result.status)

            print(result)

            assert status == str(ct.status.COMPLETED)

            connection_attributes, _ = result.result
            hostnames.update(connection_attributes)
            assert len(hostnames) == (1 if keep_alive else i + 1)
            dispatch_ids.pop()

    finally:
        while dispatch_ids:
            ct.cancel(dispatch_ids.pop())

        result = executor.stop_cloud_instance()
        status = str(result.status)

        print(result)

        assert status == str(ct.status.COMPLETED)

        if keep_alive:
            assert len(result.result) == 1
            (prefix, id), stopped_connection_attributes = result.result[0]
            assert prefix == executor.state_prefix
            assert id == executor.state_id
            assert stopped_connection_attributes == connection_attributes
        else:
            assert len(result.result) == 0


@pytest.mark.functional_tests
def test_basic_workflow(executor):
    @ct.electron(executor=executor)
    def join_words(a, b):
        return "-".join([a, b])

    @ct.electron
    def excitement(a):
        return f"{a}!"

    @ct.lattice
    def simple_workflow(a, b):
        phrase = join_words(a, b)
        return excitement(phrase)

    dispatch_id = ct.dispatch(simple_workflow)("Hello", "Covalent")
    result = ct.get_result(dispatch_id=dispatch_id, wait=True)
    status = str(result.status)

    print(result)

    assert status == str(ct.status.COMPLETED)
