import os
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
    SessionExpiredError,
    create_login_session,
    end_login_session,
    resolve_login_session,
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
# ---------------------------------------------------------

class DeliveryQueryRequest(
    BaseModel
):

    user_question: str
    session_id: str


class LoginRequest(BaseModel):

    user_id: str


class LogoutRequest(BaseModel):

    session_id: str



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
# Authentication
# ---------------------------------------------------------

@app.post("/auth/login")
async def login(
    request: LoginRequest,
):

    try:

        session = create_login_session(
            request.user_id
        )

    except AuthorizationError:

        raise HTTPException(
            status_code=401,
            detail="Invalid user_id.",
        )

    return {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "role": session.role,
    }



@app.post("/auth/logout")
async def logout(
    request: LogoutRequest,
):

    end_login_session(
        request.session_id
    )

    return {
        "success": True,
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

    try:

        access = resolve_login_session(
            request.session_id
        )


        print(
            "[DeliveryQuery] Session resolved for user:",
            access.user_id,
        )


        sources_used = set()


        source_order = [
            "Azure DevOps",
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
        # -----------------------------

        print(
            "[DeliveryQuery] Starting "
            "delivery workflow..."
        )


        workflow_result = (
            await run_delivery_workflow(
                user_id=access.user_id,
                session_id=request.session_id,
                user_question=sanitized_question,
                mark_source=mark_source,
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

        return {

            "success": True,


            "user_id":
                access.user_id,


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



    except PromptInjectionError:

        raise HTTPException(
            status_code=400,
            detail=(
                "The request was blocked by "
                "the prompt security policy."
            ),
        )



    except SessionExpiredError:

        raise HTTPException(
            status_code=401,
            detail=(
                "Session invalid or expired."
            ),
        )



    except AuthorizationError:

        raise HTTPException(
            status_code=403,
            detail=(
                "Not authorized."
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