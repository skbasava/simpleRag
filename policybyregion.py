def policy_by_region(db, facts: dict) -> dict:
    """
    Fetch MPU access policy by region.
    Works for TAG routing.
    Safe for missing data.
    """

    project = facts.get("project")
    mpu_name = facts.get("mpu_name")
    region = facts.get("region")

    # ---- Validation ----
    if not project or not mpu_name or region is None:
        return {
            "count": 0,
            "records": [],
            "confidence": None,
            "explainability": "Insufficient data to resolve policy by region."
        }

    # ---- Query ----
    rows = db.fetch_all(
        """
        SELECT
            project,
            mpu_name,
            region,
            policy_name,
            access_type,
            addr_start,
            addr_end
        FROM mpu_policies
        WHERE project = :project
          AND mpu_name = :mpu_name
          AND region = :region
        """,
        {
            "project": project,
            "mpu_name": mpu_name,
            "region": region,
        }
    )

    # ---- No result ----
    if not rows:
        return {
            "count": 0,
            "records": [],
            "confidence": 0.0,
            "explainability": f"No MPU policy found for region {region}."
        }

    # ---- Normalize rows ----
    records = []
    for r in rows:
        records.append({
            "region": r["region"],
            "policy_name": r["policy_name"],
            "access": r["access_type"],
            "addr_start": hex(r["addr_start"]) if r["addr_start"] is not None else None,
            "addr_end": hex(r["addr_end"]) if r["addr_end"] is not None else None,
        })

    return {
        "count": len(records),
        "records": records,
        "confidence": 0.95,
        "explainability": f"MPU policies covering region {region}."
    }