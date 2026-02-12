class PolicyOrchestrator:

    def __init__(self, redis_client, ipcat_client):
        self.redis = redis_client
        self.client = ipcat_client

    # ----------------------------------------

    async def resolve_project(self, project: str) -> str:
        chip = await self.client.get_chip_by_name(project)
        return chip["id"]

    # ----------------------------------------

    async def resolve_latest_version(self, chip_id: str) -> str:
        policies = await self.client.get_xpu_policies(chip_id)

        published = [p for p in policies if p["published"]]
        latest = max(published, key=lambda p: float(p["version"]))

        return latest["version"]

    # ----------------------------------------

    async def ensure_ingested(self, chip, version):

        done_key = f"ipcat:done:{chip}:{version}"

        if self.redis.exists(done_key):
            return

        await self._ingest_chip(chip, version)

        self.redis.set(done_key, 1, ex=3600)

    # ----------------------------------------

    async def _ingest_chip(self, chip, version):

        policy_id = await self.client.select_xpu_policy(chip, version)
        export_id, token = await self.client.start_policy_export(
            chip, policy_id
        )

        async for page in self.client.fetch_policy_xml(
            chip, version, export_id, token
        ):
            await self._ingest_page(chip, version, page)

    # ----------------------------------------

    async def _ingest_page(self, chip, version, xml_elements):

        for mpu_elem in xml_elements:
            ingest_single_mpu(self.redis, chip, version, mpu_elem)