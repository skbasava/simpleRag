from typing import Optional, List
from intervaltree import IntervalTree
from .interval_loader import load_interval_tree


class UnifiedPolicyEngine:

    def __init__(self, redis_client, orchestrator):
        self.redis = redis_client
        self.orchestrator = orchestrator
        self._tree_cache = {}  # (chip, version, mpu) -> IntervalTree

    async def query(
        self,
        project: str,
        address: Optional[int] = None,
        region_number: Optional[int] = None,
        mpu: Optional[str] = None,
        profile: Optional[str] = None,
        stage: Optional[str] = None,
        version: Optional[str] = None,
    ) -> List[dict]:

        chip_id = await self.orchestrator.resolve_project(project)

        if not version:
            version = await self.orchestrator.resolve_latest_version(chip_id)

        await self.orchestrator.ensure_ingested(chip_id, version)

        if address is not None:
            return self._search_by_address(
                chip_id, version, mpu, address, profile, stage
            )

        if region_number is not None:
            return self._search_by_region(
                chip_id, version, mpu, region_number, profile
            )

        raise ValueError("Unsupported query type")

    # ---------------------------------------------------------

    def _get_tree(self, chip, version, mpu) -> IntervalTree:
        key = (chip, version, mpu)

        if key not in self._tree_cache:
            self._tree_cache[key] = load_interval_tree(
                self.redis, chip, version, mpu
            )

        return self._tree_cache[key]

    # ---------------------------------------------------------

    def _search_by_address(
        self,
        chip,
        version,
        mpu,
        address,
        profile,
        stage,
    ) -> List[dict]:

        tree = self._get_tree(chip, version, mpu)

        matches = tree[address]

        results = []

        for interval in matches:
            region = interval.data

            if profile and profile.upper() not in region["profiles"]:
                continue

            if stage and region.get("stage") != stage:
                continue

            results.append(region)

        return results

    # ---------------------------------------------------------

    def _search_by_region(
        self,
        chip,
        version,
        mpu,
        region_number,
        profile,
    ) -> List[dict]:

        pattern = f"ipcat:region:{chip}:{version}:{mpu}:{region_number}:*"
        keys = self.redis.keys(pattern)

        results = []

        for key in keys:
            region = json.loads(self.redis.get(key))

            if profile and profile.upper() not in region["profiles"]:
                continue

            results.append(region)

        return results