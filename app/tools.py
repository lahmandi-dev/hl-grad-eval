"""Tools for the HL Employee Evaluation multi-agent system."""

import os
from google.cloud import bigquery
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "hl-gemini-usage")
DATASET_ID = "hl_dataset_test1"
TABLE_NAME = "hl_grad_employee-1"
FULL_TABLE_ID = f"`{PROJECT_ID}.{DATASET_ID}.{TABLE_NAME}`"


def tool_read(id: str = "", nom: str = "", prenom: str = "") -> dict:
    """Récupère les informations d'un employé depuis la table BigQuery hl_grad_employee-1.

    Args:
        id: L'identifiant de l'employé (ex: 'EMP-001').
        nom: Le nom de famille de l'employé (ex: 'Martin').
        prenom: Le prénom de l'employé (ex: 'Claire').

    Returns:
        dict: Les informations complètes de l'employé ou un message d'erreur.
    """
    client = bigquery.Client(project=PROJECT_ID)
    
    id_clean = id.strip() if id else ""
    nom_clean = nom.strip() if nom else ""
    prenom_clean = prenom.strip() if prenom else ""

    if id_clean:
        query = f"""
        SELECT `id`, `nom`, `prénom`, `ancienneté`, `notation-prec`, `notation-encours`
        FROM {FULL_TABLE_ID}
        WHERE LOWER(`id`) = LOWER(@emp_id)
        LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("emp_id", "STRING", id_clean)]
        )
    elif nom_clean:
        if prenom_clean:
            query = f"""
            SELECT `id`, `nom`, `prénom`, `ancienneté`, `notation-prec`, `notation-encours`
            FROM {FULL_TABLE_ID}
            WHERE LOWER(`nom`) = LOWER(@nom) AND LOWER(`prénom`) = LOWER(@prenom)
            LIMIT 1
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("nom", "STRING", nom_clean),
                    bigquery.ScalarQueryParameter("prenom", "STRING", prenom_clean),
                ]
            )
        else:
            query = f"""
            SELECT `id`, `nom`, `prénom`, `ancienneté`, `notation-prec`, `notation-encours`
            FROM {FULL_TABLE_ID}
            WHERE LOWER(`nom`) = LOWER(@nom)
            LIMIT 1
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[bigquery.ScalarQueryParameter("nom", "STRING", nom_clean)]
            )
    else:
        return {"status": "error", "message": "Veuillez fournir au moins l'ID ou le nom de l'employé."}

    rows = list(client.query(query, job_config=job_config).result())
    if not rows:
        return {"status": "not_found", "message": f"Aucun employé trouvé avec les critères: id='{id_clean}', nom='{nom_clean}', prenom='{prenom_clean}'"}

    return {"status": "success", "employee": dict(rows[0])}


def tool_write(notation: str, id: str = "", nom: str = "", prenom: str = "") -> dict:
    """Enregistre ou met à jour la note dans la colonne notation-encours d'un employé dans BigQuery.

    Args:
        notation: La note attribuée (de 'A' à 'F', 'A' étant la meilleure note, 'F' la moins bonne).
        id: L'identifiant de l'employé (ex: 'EMP-001').
        nom: Le nom de famille de l'employé.
        prenom: Le prénom de l'employé.

    Returns:
        dict: Statut de la mise à jour et confirmation.
    """
    client = bigquery.Client(project=PROJECT_ID)
    grade = notation.strip().upper()
    valid_grades = ["A", "B", "C", "D", "E", "F"]
    if grade not in valid_grades:
        return {
            "status": "error",
            "message": f"Notation invalide '{notation}'. Le système de notation varie obligatoirement de A à F: {valid_grades}."
        }

    id_clean = id.strip() if id else ""
    nom_clean = nom.strip() if nom else ""
    prenom_clean = prenom.strip() if prenom else ""

    if id_clean:
        update_query = f"""
        UPDATE {FULL_TABLE_ID}
        SET `notation-encours` = @grade
        WHERE LOWER(`id`) = LOWER(@emp_id)
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("grade", "STRING", grade),
                bigquery.ScalarQueryParameter("emp_id", "STRING", id_clean),
            ]
        )
        target_desc = f"l'employé avec l'ID '{id_clean}'"
    elif nom_clean:
        if prenom_clean:
            update_query = f"""
            UPDATE {FULL_TABLE_ID}
            SET `notation-encours` = @grade
            WHERE LOWER(`nom`) = LOWER(@nom) AND LOWER(`prénom`) = LOWER(@prenom)
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("grade", "STRING", grade),
                    bigquery.ScalarQueryParameter("nom", "STRING", nom_clean),
                    bigquery.ScalarQueryParameter("prenom", "STRING", prenom_clean),
                ]
            )
            target_desc = f"l'employé {prenom_clean} {nom_clean}"
        else:
            update_query = f"""
            UPDATE {FULL_TABLE_ID}
            SET `notation-encours` = @grade
            WHERE LOWER(`nom`) = LOWER(@nom)
            """
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("grade", "STRING", grade),
                    bigquery.ScalarQueryParameter("nom", "STRING", nom_clean),
                ]
            )
            target_desc = f"l'employé avec le nom '{nom_clean}'"
    else:
        return {"status": "error", "message": "Veuillez fournir au moins l'ID ou le nom de l'employé pour mettre à jour sa note."}

    client.query(update_query, job_config=job_config).result()
    return {
        "status": "success",
        "message": f"La note '{grade}' a été enregistrée avec succès dans 'notation-encours' pour {target_desc}."
    }


async def hl_tool_read_employee(id: str = "", nom: str = "", prenom: str = "") -> dict:
    """Récupère les informations sur un employé avec son ID ou son nom et prénom en faisant appel au sous-agent hl-search-employee.

    Args:
        id: L'identifiant de l'employé (ex: 'EMP-001').
        nom: Le nom de famille de l'employé.
        prenom: Le prénom de l'employé.

    Returns:
        dict: Les détails complets de l'employé retournés par hl-search-employee.
    """
    from app.agent import hl_search_employee

    runner = Runner(
        agent=hl_search_employee,
        session_service=InMemorySessionService(),
        app_name="hl_search_app"
    )
    session = await runner.session_service.create_session(app_name="hl_search_app", user_id="system_manager")
    user_query = f"Recherche les informations complètes pour l'employé : id='{id}', nom='{nom}', prénom='{prenom}'"
    message_content = types.Content(role="user", parts=[types.Part.from_text(text=user_query)])
    
    responses = []
    async for event in runner.run_async(session_id=session.id, user_id="system_manager", new_message=message_content):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    responses.append(part.text)
    await runner.close()
    return {
        "status": "success",
        "result_from_subagent_hl_search_employee": "\n".join(responses)
    }


async def hl_tool_write_employee(notation: str, id: str = "", nom: str = "", prenom: str = "") -> dict:
    """Écrit une note dans la colonne notation-encours en faisant appel au sous-agent hl-write-employee.

    Args:
        notation: La note à attribuer (de A à F, A étant la meilleure, F la moins bonne).
        id: L'identifiant de l'employé.
        nom: Le nom de famille de l'employé.
        prenom: Le prénom de l'employé.

    Returns:
        dict: Le compte rendu d'écriture retourné par hl-write-employee.
    """
    from app.agent import hl_write_employee

    runner = Runner(
        agent=hl_write_employee,
        session_service=InMemorySessionService(),
        app_name="hl_write_app"
    )
    session = await runner.session_service.create_session(app_name="hl_write_app", user_id="system_manager")
    user_query = f"Écris la note '{notation}' pour l'employé : id='{id}', nom='{nom}', prénom='{prenom}'"
    message_content = types.Content(role="user", parts=[types.Part.from_text(text=user_query)])
    
    responses = []
    async for event in runner.run_async(session_id=session.id, user_id="system_manager", new_message=message_content):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    responses.append(part.text)
    await runner.close()
    return {
        "status": "success",
        "result_from_subagent_hl_write_employee": "\n".join(responses)
    }
