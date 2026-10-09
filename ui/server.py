"""FastAPI Server for the HL Manager Red UI.
Connects directly to the deployed Agent Engine runtime on Google Cloud Vertex AI.
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional

# Ensure mTLS bypass
os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"
if "GOOGLE_API_CERTIFICATE_CONFIG" in os.environ:
    del os.environ["GOOGLE_API_CERTIFICATE_CONFIG"]

import google.auth
import google.auth.transport.requests
import httpx
import uvicorn
from a2a.client import ClientConfig, ClientFactory
from a2a.types import AgentCard, Message, Part, Role, TextPart, TransportProtocol
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from google.cloud import bigquery
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
TEMPLATES_DIR = BASE_DIR / "templates"

# Load deployment metadata
METADATA_FILE = PROJECT_DIR / "deployment_metadata.json"
DEFAULT_RUNTIME_ID = "projects/662597541283/locations/us-central1/reasoningEngines/4535318613686484992"
DEFAULT_LOCATION = "us-central1"
DEFAULT_PROJECT = "hl-gemini-usage"
DEFAULT_APP_NAME = "hl-employee-eval"

runtime_id = DEFAULT_RUNTIME_ID
location = DEFAULT_LOCATION
project = DEFAULT_PROJECT
app_name = DEFAULT_APP_NAME

if METADATA_FILE.exists():
    try:
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            meta = json.load(f)
            runtime_id = meta.get("remote_agent_runtime_id", DEFAULT_RUNTIME_ID)
            # parse location from runtime_id: projects/.../locations/{location}/...
            parts = runtime_id.split("/")
            if "locations" in parts:
                loc_idx = parts.index("locations")
                location = parts[loc_idx + 1]
    except Exception as e:
        print(f"Warning: Could not read {METADATA_FILE}: {e}")

A2A_CARD_URL = (
    f"https://{location}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{runtime_id}/api/a2a/{app_name}/.well-known/agent-card.json"
)
A2A_BASE_URL = (
    f"https://{location}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{runtime_id}/api/a2a/{app_name}"
)

app = FastAPI(title="HL-Manager Red UI", description="Interface utilisateur rouge pour l'agent RH déployé sur Agent Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_gcp_bearer_token() -> str:
    """Retrieve an active bearer token using Application Default Credentials."""
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    auth_req = google.auth.transport.requests.Request()
    creds.refresh(auth_req)
    return creds.token


from ui.auth import authenticate_user, create_access_token, verify_token
from fastapi import Header, Depends


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    username: str
    role: str = "RH Manager"


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """Validate Bearer token from request headers."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentification requise : en-tête Authorization manquant.")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Format d'authentification invalide. Utilisez 'Bearer <token>'.")
    token = authorization.split("Bearer ", 1)[1].strip()
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalide ou session expirée. Veuillez vous reconnecter.")
    return payload


@app.post("/api/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate user and issue access token."""
    if not authenticate_user(req.username, req.password):
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect.")
    token = create_access_token(req.username)
    return LoginResponse(access_token=token, username=req.username)


@app.get("/api/auth/verify")
async def verify_auth(user: dict = Depends(get_current_user)):
    """Verify active token."""
    return {"status": "authenticated", "user": user}


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = TEMPLATES_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="index.html non trouvé")
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "agent_name": "hl_manager",
        "project": project,
        "location": location,
        "runtime_id": runtime_id,
        "card_url": A2A_CARD_URL,
    }


@app.get("/api/employees")
async def get_employees(user: dict = Depends(get_current_user)):
    """Retrieve the current employees table from BigQuery (Protected)."""
    try:
        bq_client = bigquery.Client(project=project)
        query = f"SELECT * FROM `{project}.hl_dataset_test1.hl_grad_employee-1` ORDER BY id"
        query_job = bq_client.query(query)
        rows = list(query_job.result())
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur BigQuery: {str(e)}")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """Send a message to the deployed Agent Runtime via A2A (Protected)."""
    token = get_gcp_bearer_token()
    headers = {"Authorization": f"Bearer {token}"}
    session_id = request.session_id or str(uuid.uuid4())

    async with httpx.AsyncClient(headers=headers, timeout=120) as client:
        try:
            resp = await client.get(A2A_CARD_URL)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Échec de récupération de l'agent card: {resp.text}",
                )
            card = AgentCard(**resp.json())
            card.url = A2A_BASE_URL

            factory = ClientFactory(
                ClientConfig(
                    supported_transports=[
                        TransportProtocol.jsonrpc,
                        TransportProtocol.http_json,
                    ],
                    httpx_client=client,
                )
            )
            a2a_client = factory.create(card)

            msg = Message(
                message_id=str(uuid.uuid4()),
                role=Role.user,
                parts=[Part(root=TextPart(text=request.message))],
                context_id=session_id,
            )

            output_texts = []
            returned_session_id = session_id
            async for event in a2a_client.send_message(msg):
                if isinstance(event, tuple):
                    task, update = event
                    if task and task.context_id:
                        returned_session_id = task.context_id
                    if update and hasattr(update, "artifact"):
                        for part in update.artifact.parts:
                            if hasattr(part.root, "text"):
                                output_texts.append(part.root.text)
                    elif update is None and task and task.artifacts:
                        for artifact in task.artifacts:
                            for part in artifact.parts:
                                if hasattr(part.root, "text"):
                                    output_texts.append(part.root.text)

            full_reply = "".join(output_texts).strip()
            if not full_reply:
                full_reply = "Aucune réponse texte renvoyée par l'agent."

            return ChatResponse(response=full_reply, session_id=returned_session_id)
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(status_code=500, detail=f"Erreur d'appel agent: {str(e)}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8090"))
    print(f"Démarrage de la Red UI sur http://localhost:{port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
