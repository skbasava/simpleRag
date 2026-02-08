import json
import redis
import logging
from typing import Iterable
from dataclasses import asdict

from ipcatalog.models import Chip  # your updated dataclass

logger = logging.getLogger("redis")

REDIS_SCHEMA_VERSION = 2

TTL_CHIPS = 36 * 3600

# ---------- Redis Keys ----------
SCHEMA_KEY = "ipcat:chip:schema_version"
CHIP_LIST_KEY = "ipcat:chips:list"
CHIP_ID_KEY = "ipcat:chip:id:{chip_id}"
CHIP_ALIAS_KEY = "ipcat:chip:alias:{alias}"

# ---------- Client ----------
redis_client = redis.Redis(
    host="rag-redis",
    port=6379,
    decode_responses=True,
)

# ---------- Schema Handling ----------
def schema_mismatch() -> bool:
    v = redis_client.get(SCHEMA_KEY)
    return v is None or int(v) != REDIS_SCHEMA_VERSION


def reset_schema():
    logger.warning("Redis schema mismatch → flushing chip keys")
    for key in redis_client.scan_iter("ipcat:chip:*"):
        redis_client.delete(key)
    redis_client.set(SCHEMA_KEY, REDIS_SCHEMA_VERSION)

# ---------- Write ----------
def cache_chips(chips: Iterable[Chip]) -> None:
    """
    Store chips + alias mappings atomically.
    """
    chips = list(chips)

    pipe = redis_client.pipeline(transaction=True)

    # master list
    pipe.setex(
        CHIP_LIST_KEY,
        TTL_CHIPS,
        json.dumps([asdict(c) for c in chips]),
    )

    for chip in chips:
        # id → chip
        pipe.setex(
            CHIP_ID_KEY.format(chip_id=chip.id),
            TTL_CHIPS,
            json.dumps(asdict(chip)),
        )

        # alias → id
        if chip.alias:
            pipe.setex(
                CHIP_ALIAS_KEY.format(alias=chip.alias.lower()),
                TTL_CHIPS,
                chip.id,
            )

    pipe.execute()

    logger.info(
        "Cached %d chips (%d aliases)",
        len(chips),
        sum(1 for c in chips if c.alias),
    )

# ---------- Read ----------
def get_chip_by_alias(alias: str) -> Chip | None:
    chip_id = redis_client.get(
        CHIP_ALIAS_KEY.format(alias=alias.lower())
    )
    if not chip_id:
        return None

    raw = redis_client.get(
        CHIP_ID_KEY.format(chip_id=chip_id)
    )
    if not raw:
        return None

    return Chip(**json.loads(raw))


def get_all_chips() -> list[Chip]:
    raw = redis_client.get(CHIP_LIST_KEY)
    if not raw:
        return []

    return [Chip(**c) for c in json.loads(raw)]