import pytest

from riksarkivet_mcp import server


@pytest.fixture(autouse=True)
async def fresh_client():
    # each test gets its own event loop, so don't reuse the module-level httpx client
    server._client = None
    yield
    if server._client is not None:
        await server._client.aclose()
        server._client = None
