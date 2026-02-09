class PolicyOrchestrator:
    def __init__(self, redis_client, ipcat_client):
        self.redis = redis_client
        self.client = ipcat_client

    async def get_policy_by_mpu(
        self,
        chip: str,
        version: str,
        mpu_name: str,
    ):
        """
        Entry point for API / backend.
        """

        # 1. Ensure chip+version is ingested
        await self._ensure_ingested(chip, version)

        # 2. Fetch MPU data from Redis
        return self._get_mpu_from_cache(chip, version, mpu_name)
        
    
    async def _ensure_ingested(self, chip: str, version: str) -> None:
    """
    Ensure Redis has data for (chip, version).
    """

    # Fast path: already ingested
    if self.redis.exists(f"ipcat:ingest:done:{chip}:{version}"):
        return

    # Trigger ingestion
    await ingest_chip(
        chip=chip,
        version=version,
        client=self.client,
        redis_client=self.redis,
    )
    
    def get_chip_list(self):
    raw = self.redis.get("ipcat:chips:list")
    if raw:
        return json.loads(raw)

    # TTL expired → re-ingest ALL chips (or selective)
    asyncio.create_task(self._refresh_chips())
    return []
    
    async def _refresh_chips(self):
    chips = await self.client.list_chips()
    cache_chips(chips)
    
    
    def _get_mpu_from_cache(self, chip, version, mpu_name):
    key = f"ipcat:mpu:{chip}:{version}:{mpu_name}"
    raw = self.redis.get(key)

    if not raw:
        raise KeyError(f"MPU {mpu_name} not found")

    return json.loads(raw)
        