# Système Multi-Agents d'Évaluation des Employés (ADK)

Projet d'évaluation annuelle et de notation des employés basé sur **Google Agent Development Kit (ADK)** et **BigQuery**.
Projet GCP : `hl-gemini-usage`  
Table BigQuery : `hl_dataset_test1.hl_grad_employee-1`

---

## 🏛️ Architecture Multi-Agents

Le système repose sur un agent superviseur (**Root**) et deux sous-agents spécialisés :

```
                  ┌──────────────────────────────────────────────┐
                  │                 hl-manager                   │
                  │   (Agent Superviseur - Décision & Rating)    │
                  └──────────────┬────────────────┬──────────────┘
                                 │                │
            hl-tool-read-employee│                │hl-tool-write-employee
                                 ▼                ▼
         ┌───────────────────────────────┐ ┌───────────────────────────────┐
         │       hl-search-employee      │ │       hl-write-employee       │
         │ (Sous-agent lecture BigQuery) │ │(Sous-agent écriture BigQuery) │
         └──────────────┬────────────────┘ └──────────────┬────────────────┘
                        │tool_read                        │tool_write
                        ▼                                 ▼
         ┌─────────────────────────────────────────────────────────────────┐
         │       BigQuery : hl_dataset_test1.hl_grad_employee-1            │
         │  (id, nom, prénom, ancienneté, notation-prec, notation-encours) │
         └─────────────────────────────────────────────────────────────────┘
```

### 1. `hl-manager` (Agent Root)
- **Objectif** : Coordonner l'évaluation, analyser les performances de l'employé par rapport à l'année précédente (`notation-prec`) et proposer une note argumentée pour l'année en cours (`notation-encours`).
- **Échelle de notation** : Strictement de **A à F** (A étant la note maximale, F la plus basse).
- **Règle Human-in-the-Loop** : L'agent **ne déclenche jamais** l'écriture dans BigQuery sans la validation explicite de l'utilisateur. Il propose la note, justifie son choix, et attend la confirmation (« je valide », « oui », « enregistre »).
- **Tools** :
  - `hl_tool_read_employee` : Appelle le sous-agent `hl-search-employee` pour extraire la fiche de l'employé (id ou nom/prénom).
  - `hl_tool_write_employee` : Appelle le sous-agent `hl-write-employee` pour écrire la note validée dans la table.

### 2. `hl-search-employee` (Sous-agent)
- **Objectif** : Recherche et extraction des données employé dans BigQuery.
- **Tool** :
  - `tool_read(id, nom, prenom)` : Exécute une requête SQL paramétrée sur la table BigQuery.

### 3. `hl-write-employee` (Sous-agent)
- **Objectif** : Enregistrement et mise à jour de la note dans la colonne `notation-encours`.
- **Tool** :
  - `tool_write(notation, id, nom, prenom)` : Valide que la notation est bien entre A et F, puis exécute l'UPDATE SQL dans BigQuery.

---

## 🚀 Démarrage Rapide

### 1. Configuration de l'environnement (`.env`)
```bash
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=hl-gemini-usage
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_API_USE_CLIENT_CERTIFICATE=false
```

### 2. Interface Utilisateur Rouge (Red UI) — Connectée à Agent Engine
Pour interagir graphiquement avec l'agent déployé sur Google Cloud Agent Engine :
```bash
./run_ui.sh
# ou : PORT=8090 uv run python ui/server.py
```
Accédez à l'application web sur : **http://localhost:8090**
- Thème rouge élégant (Crimson / Bordeaux / Rubis)
- Affichage en temps réel de l'annuaire BigQuery `hl_grad_employee-1`
- Chat interactif en direct avec l'agent distant via protocole A2A
- Boutons d'actions rapides et bannière de validation humaine pour les notations

### 3. Exemple de scénario d'utilisation
1. **Utilisateur** : « *Peux-tu regarder le dossier de Claire Martin (EMP-001) ? Cette année, elle a dépassé tous ses objectifs de 30% et a mentoré 2 juniors.* »
2. **hl-manager** : Appelle `hl_tool_read_employee` ➔ `hl-search-employee` ➔ Récupère `notation-prec = 'B'`, `ancienneté = '5 ans'`.
3. **hl-manager** : Propose la note **A** avec justification et demande : « *Validez-vous cette notation pour que je l'enregistre ?* »
4. **Utilisateur** : « *Je valide cette notation, enregistre-la s'il te plaît.* »
5. **hl-manager** : Appelle `hl_tool_write_employee` ➔ `hl-write-employee` ➔ Met à jour `notation-encours = 'A'` dans BigQuery et confirme l'opération.

### 4. Déploiement Agent Engine (Vertex AI Agent Runtime)
```bash
# Vérifier le statut du déploiement
agents-cli deploy --status --project hl-gemini-usage --region us-central1

# Requêter en ligne de commande l'agent distant
agents-cli run \
  --url https://us-central1-aiplatform.googleapis.com/v1/projects/662597541283/locations/us-central1/reasoningEngines/4535318613686484992 \
  --mode a2a \
  --app-name hl-employee-eval \
  "Bonjour"
```

