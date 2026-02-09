import redis
from redis.commands.bf import BF
from typing import Iterable
from .models import Policy

TTL_CHIP = 36 * 3600
TTL_POLICY = 24 * 3600

r = redis.Redis(host="redis", port=6379, decode_responses=True)
bf = BF(r)

def ensure_bloom():
    try:
        bf.reserve("bf:chip_version", 0.01, 10000)
    except redis.ResponseError:
        pass

def cache_chip(chip_name: str, chip_id: int):
    r.setex(f"chip:name:{chip_name.lower()}", TTL_CHIP, chip_id)

def bloom_add(chip: str, version: str):
    bf.add("bf:chip_version", f"{chip}|{version}")

def bloom_exists(chip: str, version: str) -> bool:
    return bf.exists("bf:chip_version", f"{chip}|{version}")

def cache_policies(policies: Iterable[Policy]):
    pipe = r.pipeline()
    for p in policies:
        pipe.sadd(f"mpus:{p.chip}:{p.version}", p.mpu)
        pipe.setex(
            f"policy:{p.chip}:{p.version}:{p.mpu}:{p.region}",
            TTL_POLICY,
            p.raw_text,
        )
    pipe.execute()