# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import os
from collections.abc import AsyncIterator

import google.auth
from a2a.server.tasks import InMemoryTaskStore
from dotenv import load_dotenv
from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.cloud import logging as google_cloud_logging

from app.app_utils import services
from app.app_utils.a2a import attach_a2a_routes
from app.app_utils.typing import Feedback

load_dotenv()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from app.agent import app as adk_app
    from app.agent import root_agent

    runner = Runner(
        app=adk_app,
        session_service=services.get_session_service(),
        artifact_service=services.get_artifact_service(),
        auto_create_session=True,
    )
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )
    yield


app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,
    allow_origins=allow_origins,
    session_service_uri=services.SESSION_SERVICE_URI,
    otel_to_cloud=True,
    lifespan=lifespan,
)
app.title = "hl-employee-eval"
app.description = "API for interacting with the Agent hl-employee-eval"


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


# --- Red UI & Helper Endpoints ---
from pathlib import Path
from typing import Optional
import uuid
from fastapi.responses import HTMLResponse
from fastapi import HTTPException
from pydantic import BaseModel
from google.genai import types as genai_types
from google.cloud import bigquery

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


@app.get("/ui", response_class=HTMLResponse)
async def serve_ui():
    """Serve the Red UI HTML interface."""
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        alt = Path(__file__).resolve().parent.parent / "ui" / "templates" / "index.html"
        if alt.exists():
            return HTMLResponse(content=alt.read_text(encoding="utf-8"))
        raise HTTPException(status_code=404, detail="Template UI introuvable")
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/employees")
async def get_employees():
    """Retrieve employees list from BigQuery table."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "hl-gemini-usage")
    bq_client = bigquery.Client(project=project)
    query = f"SELECT * FROM `{project}.hl_dataset_test1.hl_grad_employee-1` ORDER BY id"
    rows = list(bq_client.query(query).result())
    employees = []
    for row in rows:
        d = dict(row)
        employees.append({
            "id": d.get("id"),
            "nom": d.get("nom"),
            "prenom": d.get("prénom") or d.get("prenom"),
            "anciennete": d.get("ancienneté") or d.get("anciennete"),
            "notation_prec": d.get("notation-prec") or d.get("notation_prec"),
            "notation_encours": d.get("notation-encours") or d.get("notation_encours"),
        })
    return {"employees": employees}


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Direct in-process chat with the ADK Runner."""
    runner = getattr(app.state, "runner", None)
    if not runner:
        raise HTTPException(status_code=503, detail="Runner non initialisé")
    session_id = req.session_id or str(uuid.uuid4())
    msg = genai_types.Content(parts=[genai_types.Part.from_text(text=req.message)])
    texts = []
    async for event in runner.run_async(user_id="user", session_id=session_id, new_message=msg):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    texts.append(part.text)
    full_text = "".join(texts).strip()
    if not full_text:
        full_text = "Aucune réponse de l'agent."
    return ChatResponse(response=full_text, session_id=session_id)


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

