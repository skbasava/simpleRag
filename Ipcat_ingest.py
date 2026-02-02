import asyncio
from ipcatalog_client import IPCatalogClient
from token_manager import TokenManager
from orchestrator import PolicyOrchestrator

BASE_URL = "https://ipcatalog-api.qualcomm.com/api/1"

token_mgr = TokenManager(
    BASE_URL,
    username="YOUR_USER",
    password="YOUR_PASS"
)

client = IPCatalogClient(BASE_URL, token_mgr)
orchestrator = PolicyOrchestrator(client)

async def handle_query():
    result, meta = await orchestrator.get_policy_by_mpu(
        chip_name="kaanapalli",
        version="v3",
        mpu_name="AOSS_MPU"
    )

    print("RESULT:\n", result)
    print("META:\n", meta)

if __name__ == "__main__":
    asyncio.run(handle_query())