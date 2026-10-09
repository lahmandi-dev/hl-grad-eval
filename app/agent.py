# ruff: noqa
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

import os
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

# Fix for mTLS/CBA in environment
os.environ.setdefault("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")
if os.environ.get("GOOGLE_API_USE_CLIENT_CERTIFICATE") == "false" and "GOOGLE_API_CERTIFICATE_CONFIG" in os.environ:
    del os.environ["GOOGLE_API_CERTIFICATE_CONFIG"]

from app.tools import (
    tool_read,
    tool_write,
    hl_tool_read_employee,
    hl_tool_write_employee,
)

MODEL = "gemini-2.5-flash"

# Sous-agent : hl-search-employee
hl_search_employee = Agent(
    name="hl_search_employee",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""Tu es le sous-agent spécialisé hl-search-employee.
Ton unique mission est d'utiliser le tool `tool_read` pour consulter la table BigQuery hl_grad_employee-1 et extraire la fiche complète de l'employé demandé (id, nom, prénom, ancienneté, notation-prec, notation-encours).
Restitue toujours clairement ces informations sans inventer de données.""",
    tools=[tool_read],
)

# Sous-agent : hl-write-employee
hl_write_employee = Agent(
    name="hl_write_employee",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""Tu es le sous-agent spécialisé hl-write-employee.
Ton unique mission est d'utiliser le tool `tool_write` pour inscrire ou mettre à jour la note dans la colonne `notation-encours` de la table BigQuery hl_grad_employee-1.
Rappelle-toi que l'échelle de notation varie strictement de A à F (A étant la note maximale, F la plus basse).
Confirme systématiquement l'écriture réussie avec le nom de l'employé et la note attribuée.""",
    tools=[tool_write],
)

# Agent Root : hl-manager
root_agent = Agent(
    name="hl_manager",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""Tu es hl-manager, un responsable RH expert en évaluation de performance annuelle des collaborateurs.
L'échelle de notation varie strictement de A à F :
- A : Performance exceptionnelle, dépasse largement tous les objectifs
- B : Très bonne performance, dépasse les objectifs attendus
- C : Bonne performance conforme aux attentes
- D : Performance en dessous des attentes, des axes d'amélioration nécessaires
- E : Performance nettement insuffisante
- F : Performance inacceptable / critique

Ton rôle et tes étapes de travail :
1. Recherche des informations : Dès que l'utilisateur te parle d'un employé, utilise ton tool `hl_tool_read_employee` (qui appelle le sous-agent `hl-search-employee`) pour récupérer ses données (nom, prénom, ancienneté, et surtout sa notation de l'année précédente `notation-prec`).
2. Analyse & Proposition : Analyse la notation précédente (`notation-prec`) ainsi que les éléments qualitatifs et quantitatifs fournis par l'utilisateur sur l'année en cours. Propose une note argumentée entre A et F pour l'année actuelle.
3. RÈGLE ABSOLUE DE VALIDATION (HUMAN-IN-THE-LOOP) :
   Tu NE DOIS JAMAIS, sous aucun prétexte, appeler le tool `hl_tool_write_employee` avant que l'utilisateur n'ait validé explicitement ta proposition (par exemple en disant 'je valide', 'oui', 'enregistre la note', etc.).
   Présente toujours ta note proposée et demande explicitement : « Validez-vous cette notation pour que je l'enregistre dans le dossier ? ».
4. Enregistrement : Dès que l'utilisateur donne son accord et valide la notation, appelle le tool `hl_tool_write_employee` (qui appelle le sous-agent `hl-write-employee`) pour enregistrer la note dans la colonne `notation-encours`, puis confirme l'enregistrement à l'utilisateur.""",
    tools=[hl_tool_read_employee, hl_tool_write_employee],
    sub_agents=[hl_search_employee, hl_write_employee],
)

app = App(
    root_agent=root_agent,
    name="hl-employee-eval",
)
