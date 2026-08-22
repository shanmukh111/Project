import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import (
    FastAPI,
    HTTPException,
)

from fastapi.responses import FileResponse

from pydantic import BaseModel

from security.authorization import (
    AuthorizationError,
    authorize_email,
)

from security.pii_filter import anonymize_pii

from security.prompt_guard import (
    PromptInjectionError,
    validate_user_prompt,
)

from security.output_filter import redact_secrets


from orchestration.delivery_workflow import (
    run_delivery_workflow,
)

from reporting.charts import REPORTS_DIR

from retrieval.hybrid_rag import (
    initialize_hybrid_rag,
)


# ---------------------------------------------------------
# Public URL for Copilot Studio access
# ---------------------------------------------------------

PUBLIC_URL = os.getenv(
    "PUBLIC_URL",
    "https://bmvxdh1s-8000.asse.devtunnels.ms"
)


# ---------------------------------------------------------
# Request deduplication
#
# Copilot Studio's generative orchestrator has been observed
# calling this tool multiple times for a single user message
# (confirmed via distinct report_ids in the backend logs for
# what was clearly one question). Since that's a platform
# behavior outside this backend's control, the fix is here:
# if the same user asks the same question again within a short
# window, return the already-computed response instead of
# re-running the full agent pipeline. Real follow-up questions
# (different text) are unaffected.
# ---------------------------------------------------------

_DEDUPE_WINDOW_SECONDS = 30
_DEDUPE_CACHE_MAX_AGE_SECONDS = 300  # prune anything older than this

_recent_responses: dict[
    tuple[str, str],
    tuple[dict, float],
] = {}


def _normalize_for_dedupe(
    text: str,
) -> str:

    return " ".join(
        text.strip().lower().split()
    )


def _prune_dedupe_cache() -> None:

    now = time.time()

    stale_keys = [
        key
        for key, (_, timestamp) in _recent_responses.items()
        if now - timestamp > _DEDUPE_CACHE_MAX_AGE_SECONDS
    ]

    for key in stale_keys:
        del _recent_responses[key]


# ---------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------

@asynccontextmanager
async def lifespan(
    app: FastAPI,
):

    print(
        "[Startup] Warming Hybrid RAG..."
    )

    initialize_hybrid_rag()

    print(
        "[Startup] Hybrid RAG ready."
    )

    yield

    print(
        "[Shutdown] "
        "MAQ Delivery Agent stopped."
    )


# ---------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------

app = FastAPI(
    title=(
        "MAQ Intelligent "
        "Client Delivery Agent"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------
# Request models
#
# user_id here is expected to be the caller's real email
# (Copilot Studio's User.Email), checked against the
# allowlist in security.authorization on every request.
# There is no separate login/session step anymore - the
# email itself doubles as the key for conversational memory.
# ---------------------------------------------------------

class DeliveryQueryRequest(
    BaseModel
):

    user_question: str
    user_id: str
    project_register: list[dict] | None = None


# ---------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------

@app.get("/health")
async def health():

    return {
        "status": "ok",
        "service": (
            "maq-client-delivery-agent"
        ),
        "environment": "dev",
        "hybrid_rag": "ready",
        "architecture": (
            "single-agent-retrieval "
            "+ insight-orchestrator"
        ),
        "agents": 2,
    }


# ---------------------------------------------------------
# Report / chart serving
# ---------------------------------------------------------

@app.get("/reports/{report_id}.html")
async def get_report(
    report_id: str,
):

    report_path = (
        REPORTS_DIR /
        f"{report_id}.html"
    )

    if not report_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Report not found.",
        )

    return FileResponse(
        report_path,
        media_type="text/html",
        filename=f"MAQ-Delivery-Report-{report_id}.html",
    )



@app.get("/reports/{filename}.png")
async def get_chart(
    filename: str,
):

    chart_path = (
        REPORTS_DIR /
        f"{filename}.png"
    )

    if not chart_path.exists():

        raise HTTPException(
            status_code=404,
            detail="Chart not found.",
        )

    return FileResponse(
        chart_path,
        media_type="image/png",
    )



# ---------------------------------------------------------
# Main delivery endpoint
# ---------------------------------------------------------

@app.post("/delivery/query")
async def delivery_query(
    request: DeliveryQueryRequest,
):

    _prune_dedupe_cache()

    dedupe_key = (
        request.user_id.strip().lower(),
        _normalize_for_dedupe(
            request.user_question
        ),
    )

    now = time.time()

    cached = _recent_responses.get(dedupe_key)

    if cached:
        cached_response, cached_at = cached

        if now - cached_at < _DEDUPE_WINDOW_SECONDS:
            print(
                "[DeliveryQuery] Duplicate request "
                f"within {_DEDUPE_WINDOW_SECONDS}s - "
                "returning cached response instead of "
                "re-running the workflow."
            )

            return cached_response

    try:

        # -----------------------------
        # Authorization by email
        # -----------------------------

        access = authorize_email(
            request.user_id
        )

        print(
            "[DeliveryQuery] Authorized:",
            access.email,
        )


        sources_used = set()


        source_order = [
            "SharePoint",
            "Azure DevOps",
            "Timesheets",
            "MAQ Delivery Knowledge",
        ]


        def mark_source(
            source_name: str,
        ):

            sources_used.add(
                source_name
            )

            print(
                "[SourceTracking] "
                f"Used: {source_name}"
            )



        # -----------------------------
        # PII masking
        # -----------------------------

        pii_result = anonymize_pii(
            request.user_question
        )


        sanitized_question = (
            pii_result["sanitized_text"]
        )


        if pii_result["pii_detected"]:

            print(
                "[Security] PII detected and masked:",
                [
                    entity["entity_type"]
                    for entity
                    in pii_result["entities"]
                ],
            )



        # -----------------------------
        # Prompt guard
        # -----------------------------

        validate_user_prompt(
            sanitized_question
        )


        print(
            "[Security] Prompt guard passed."
        )



        # -----------------------------
        # Run MAF workflow
        #
        # session_id is the authorized email itself - a
        # stable per-person key for conversational memory,
        # with no separate login/session issuance needed.
        # -----------------------------

        print(
            "[DeliveryQuery] Starting "
            "delivery workflow..."
        )


        workflow_result = (
            await run_delivery_workflow(
                user_id=access.email,
                session_id=access.email,
                user_question=sanitized_question,
                mark_source=mark_source,
                sources_used=sources_used,
                project_register=request.project_register,
            )
        )



        safe_answer, secret_detected = redact_secrets(
            workflow_result["answer"]
        )


        if secret_detected:

            print(
                "[Security] Secret-like content redacted."
            )


        workflow_result["answer"] = safe_answer



        # -----------------------------
        # Source tracking
        # -----------------------------

        actual_sources = [
            source
            for source in source_order
            if source in sources_used
        ]


        print(
            "[SourceTracking] Final sources:",
            actual_sources,
        )



        # -----------------------------
        # Build absolute URLs
        # -----------------------------

        report_url = None

        if workflow_result.get(
            "report_url"
        ):

            report_url = (
                f"{PUBLIC_URL}"
                f"{workflow_result['report_url']}"
            )


        chart_urls = {}

        for key, value in workflow_result.get(
            "chart_urls",
            {}
        ).items():

            chart_urls[key] = (
                f"{PUBLIC_URL}{value}"
            )



        # -----------------------------
        # Final response
        # -----------------------------

        response_body = {

            "success": True,


            "user_id":
                access.email,


            "question":
                sanitized_question,


            "answer":
                workflow_result["answer"],


            "sources":
                actual_sources,


            "report_url":
                report_url,


            "chart_urls":
                chart_urls,


            "workflow":
                workflow_result["workflow"],

        }

        _recent_responses[dedupe_key] = (
            response_body,
            time.time(),
        )

        return response_body



    except PromptInjectionError:

        raise HTTPException(
            status_code=400,
            detail=(
                "The request was blocked by "
                "the prompt security policy."
            ),
        )



    except AuthorizationError as exc:

        print(
            "[DeliveryQuery] Authorization denied:",
            str(exc),
        )

        raise HTTPException(
            status_code=403,
            detail=(
                "You are not authorized "
                "to use this agent."
            ),
        )



    except Exception as exc:

        print(
            "[DeliveryQuery] Error:",
            type(exc).__name__,
            str(exc),
        )


        raise HTTPException(
            status_code=500,
            detail=(
                "Delivery data could not "
                "be retrieved."
            ),
        )