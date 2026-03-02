@kernel_function(
    name="count_resource_groups",
    description=(
        "Count how many resource groups (RGs/regions) exist WITHIN each MPU/XPU instance. "
        "Use this when user asks: "
        "'how many RGs per XPU' "
        "'number of RGs supported per XPU' "
        "'count regions in each MPU' "
        "'RG count for each XPU' "
        "This counts the REGIONS (0,1,2...) inside each MPU, NOT the number of MPUs."
    ),
)
async def count_resource_groups(
    self,
    project: Annotated[str, "Project/chip name (e.g., KAANAPALI)"],
    version: Annotated[Optional[str], "Version number"] = None,
    mpu_name: Annotated[
        Optional[str],
        "Specific MPU/XPU name to count RGs for (optional)",
    ] = None,
    show_details: Annotated[bool, "Show detailed region list"] = False,
) -> str:
    """
    Count resource groups per MPU/XPU using Redis SCAN.

    Args:
        project: Project/chip name
        version: Optional version (defaults to latest)
        mpu_name: Optional specific MPU name

    Returns:
        JSON string with RG count per XPU/MPU
    """

    logger.info(
        f"count_resource_groups called: project={project}, version={version}, mpu_name={mpu_name}"
    )

    try:
        # Step 1: Resolve chip and version
        chip_id = await self.engine.orchestrator.resolve_project(project)
        is_latest_request = version is None

        if not version:
            version = await self.engine.orchestrator.resolve_latest_version(chip_id)
            logger.info(f"Resolved latest version: {version}")
            await self.engine.orchestrator.ensure_ingested(chip_id, version)

        # Step 2: Get MPU list
        mpu_list = await self.engine.orchestrator.get_mpu_list(
            str(chip_id), version
        )

        # Filter by specific MPU if requested
        if mpu_name:
            mpu_list = [mpu for mpu in mpu_list if mpu.lower() == mpu_name.lower()]
            if not mpu_list:
                return json.dumps(
                    {
                        "error": f"MPU/XPU '{mpu_name}' not found in project {project}",
                        "project": project,
                        "version": version,
                    }
                )

        # Step 3: Count RGs for each MPU using Redis SCAN
        redis_client = self.engine.orchestrator.redis
        mpu_rg_counts = []
        total_rgs = 0

        for mpu in mpu_list:
            try:
                # Build Redis key pattern
                key_pattern = f"ipcat:region:{chip_id}:{version}:{mpu}:*"
                logger.debug(f"Scanning pattern: {key_pattern}")

                # Count matching keys using SCAN
                matching_keys = []
                cursor = 0

                # Check if redis client is async or sync
                if hasattr(redis_client.scan, "__call__") and not hasattr(redis_client.scan, "__await__"):
                    # Synchronous scan
                    while True:
                        cursor, keys = redis_client.scan(
                            cursor, match=key_pattern, count=100
                        )
                        matching_keys.extend(keys)
                        if cursor == 0:
                            break
                else:
                    # Async path continues below...
                    pass
