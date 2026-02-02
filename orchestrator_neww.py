import asyncio
from concurrent.futures import ThreadPoolExecutor

from redis_client import redis_client, bloom, BLOOM_KEY
from cache_keys import *
from xml_parser import parse_mpu

TTL_CHIPS = 36 * 3600
TTL_POLICY = 24 * 3600
TTL_MPU = 24 * 3600

executor = ThreadPoolExecutor(max_workers=8)

class PolicyOrchestrator:
    """
    Core brain of the system.
    """

    def __init__(self, api_client):
        self.client = api_client

    def ensure_chips(self):
        if redis_client.exists(CHIP_LIST_KEY):
            return

        chips = self.client.list_chips()
        redis_client.setex(
            CHIP_LIST_KEY,
            TTL_CHIPS,
            ",".join(str(c["id"]) for c in chips)
        )

        for chip in chips:
            redis_client.setex(
                CHIP_ALIAS_KEY.format(chip_name=chip["name"].lower()),
                TTL_CHIPS,
                chip["id"]
            )

    async def get_policy_by_mpu(self, chip_name, version, mpu_name):
        self.ensure_chips()

        chip_id = redis_client.get(
            CHIP_ALIAS_KEY.format(chip_name=chip_name.lower())
        )
        if not chip_id:
            raise ValueError("Unknown chip")

        bloom_key = f"{chip_id}:{version}"
        if not bloom.bfExists(BLOOM_KEY, bloom_key):
            policies = self.client.list_xpu_policies(chip_id, version)
            bloom.bfAdd(BLOOM_KEY, bloom_key)

            redis_client.setex(
                POLICY_INDEX_KEY.format(chip_id=chip_id, version=version),
                TTL_POLICY,
                ",".join(str(p["id"]) for p in policies)
            )

        policy_ids = redis_client.get(
            POLICY_INDEX_KEY.format(chip_id=chip_id, version=version)
        ).split(",")

        for policy_id in policy_ids:
            mpu_key = MPU_KEY.format(
                chip_id=chip_id,
                policy_id=policy_id,
                mpu_name=mpu_name
            )

            cached = redis_client.get(mpu_key)
            if cached:
                return cached, {
                    "source": "redis",
                    "confidence": 0.95
                }

            xml_key = POLICY_XML_KEY.format(
                chip_id=chip_id,
                policy_id=policy_id
            )

            xml = redis_client.get(xml_key)
            if not xml:
                job = self.client.export_policy(policy_id)
                xml = job["xml"]
                redis_client.setex(xml_key, TTL_POLICY, xml)

            regions = await asyncio.get_event_loop().run_in_executor(
                executor,
                parse_mpu,
                xml,
                mpu_name
            )

            if regions:
                redis_client.setex(mpu_key, TTL_MPU, "\n".join(regions))
                return "\n".join(regions), {
                    "source": "api+parse",
                    "confidence": 0.85
                }

        return None, {"confidence": 0.0}