def validate_agent_result(
    result,
    expected_type,
) -> bool:
    """
    Validates structured evidence returned by
    an evidence agent.
    """

    if result is None:
        return False

    value = getattr(
        result,
        "value",
        None,
    )

    if value is None:
        return False

    if not isinstance(
        value,
        expected_type,
    ):
        return False

    if not value.success:
        return False

    if not value.summary.strip():
        return False

    return True


async def run_with_single_retry(
    run_function,
    branch_name: str,
    expected_type,
):
    """
    Runs one evidence branch.

    If the first attempt fails, retry once.
    If both fail, return graceful-degradation metadata.
    """

    try:
        result = await run_function()

        print(
            f"[Workflow] {branch_name} structured type:",
            type(
                getattr(
                    result,
                    "value",
                    None,
                )
            ).__name__,
        )

        if validate_agent_result(
            result,
            expected_type,
        ):
            return {
                "success": True,
                "status": "success",
                "text": result.value.model_dump_json(
                    indent=2
                ),
                "evidence_dict": result.value.model_dump(),
                "attempts": 1,
            }

        raise RuntimeError(
            f"{branch_name} returned empty evidence."
        )

    except Exception as first_error:

        print(
            f"[Workflow] {branch_name} "
            f"attempt 1 failed: "
            f"{type(first_error).__name__}: "
            f"{first_error}"
        )

        try:
            print(
                f"[Workflow] Retrying "
                f"{branch_name} once..."
            )

            result = await run_function()

            print(
                f"[Workflow] {branch_name} retry structured type:",
                type(
                    getattr(
                        result,
                        "value",
                        None,
                    )
                ).__name__,
            )

            if validate_agent_result(
                result,
                expected_type,
            ):
                return {
                    "success": True,
                    "status": (
                        "success_after_retry"
                    ),
                    "text": result.value.model_dump_json(
                        indent=2
                    ),
                    "evidence_dict": result.value.model_dump(),
                    "attempts": 2,
                }

            raise RuntimeError(
                f"{branch_name} returned "
                "empty evidence after retry."
            )

        except Exception as second_error:

            print(
                f"[Workflow] {branch_name} "
                f"attempt 2 failed: "
                f"{type(second_error).__name__}: "
                f"{second_error}"
            )

            return {
                "success": False,
                "status": "unavailable",
                "text": (
                    f"{branch_name} evidence "
                    "is unavailable for this request."
                ),
                "evidence_dict": {},
                "attempts": 2,
            }