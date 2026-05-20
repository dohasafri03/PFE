# n8n – Guide de mise en place du workflow

## Architecture

```
┌─────────────┐    HTTP     ┌──────────────────────┐
│    n8n       │ ─────────► │  API FastAPI :8000    │
│  :5678       │            │                      │
│              │            │  /scrape             │ → scrape_deep.py (Playwright)
│  ⏰ Cron 9h  │            │  /pipeline/score     │ → ScoringEngine
│  ▶️ Manuel   │            │  /pipeline/run-sync  │ → Pipeline complet (7 étapes)
│  📧 Alertes  │            │  /pipeline/rag       │ → RAG enrichment (LLM)
│              │            │  /results/*          │ → CSV / Excel / Dossiers
└─────────────┘            └──────────────────────┘
```

## Démarrage rapide (local, sans Docker)

### 1. Lancer l'API

```bash
# Terminal 1 – API FastAPI
start_api.bat

# ou manuellement :
.venv\Scripts\activate
pip install fastapi uvicorn[standard]
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Vérifier : http://localhost:8000/docs (Swagger UI)

### 2. Lancer n8n

```bash
# Terminal 2 – n8n
start_n8n.bat

# ou via Docker :
docker run -it --rm -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  --add-host=host.docker.internal:host-gateway \
  -e GENERIC_TIMEZONE=Africa/Casablanca \
  docker.n8n.io/n8nio/n8n:latest

# ou via npx (Node.js) :
npx n8n start
```

Ouvrir : http://localhost:5678

### Connexion n8n (important — version 2.x)

Depuis **n8n 2.x**, les variables `N8N_BASIC_AUTH_*` (**alexsys / alexsys2026**) **ne fonctionnent plus**.

- **Première visite** : écran « Set up owner account » → choisissez un **email** et un **mot de passe** (ce sont vos identifiants n8n).
- **Visites suivantes** : connectez-vous avec cet **email + mot de passe** (pas alexsys).
- Utilisez **http://localhost:5678** (évitez de mélanger `127.0.0.1` et `localhost` pour les cookies).
- Mot de passe oublié : exécutez `scripts\reset_n8n_login.bat` puis recréez le compte propriétaire.

**Deux bases n8n possibles (Docker)** : `docker compose` créait parfois le volume `marche_ai_platform_n8n_data`, alors que `start_n8n.bat` utilise `n8n_data`. Les identifiants ne sont pas les mêmes entre les deux. Le projet force maintenant le volume **`n8n_data`** partout. Après `docker compose up -d`, utilisez les mêmes email/mot de passe que sur l’instance qui fonctionnait déjà.

### 3. Importer le workflow

1. Ouvrir n8n → **Workflows** → **Import from File**
2. Sélectionner `n8n/workflow_pipeline.json`
3. Le workflow apparaît avec tous les nœuds connectés

### 4. Configurer l'URL de l'API (important)

Le workflow utilise la variable d'environnement `API_BASE_URL` (ex: `http://api:8000` ou `http://localhost:8000`).

- Si tu lances via `docker-compose.n8n.yml` : `API_BASE_URL=http://api:8000` est déjà configuré (réseau Docker).
- Si tu lances n8n dans Docker mais l'API sur l'hôte : mets `API_BASE_URL=http://host.docker.internal:8000`.
- Si tout tourne en local (sans Docker) : mets `API_BASE_URL=http://localhost:8000`.

## Démarrage Docker (production)

```bash
docker-compose -f docker-compose.n8n.yml up -d
```

Ceci lance :
- **API** sur http://localhost:8000
- **n8n** sur http://localhost:5678

## Endpoints API

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/scrape` | Lance le scraping (async) |
| `GET` | `/scrape/status` | Statut du scraping |
| `POST` | `/pipeline/score` | Scoring seul (~1s) |
| `POST` | `/pipeline/run-sync` | Pipeline complet (attend la fin) |
| `POST` | `/pipeline/run` | Pipeline complet (async) |
| `GET` | `/pipeline/status` | Statut du pipeline |
| `POST` | `/pipeline/rag` | Enrichissement RAG/LLM |
| `GET` | `/results/latest` | Dernier rapport JSON |
| `GET` | `/results/csv` | Télécharge le CSV |
| `GET` | `/results/excel` | Télécharge l'Excel |
| `GET` | `/results/dossiers` | Liste les dossiers DOCX |

## Workflow n8n – Flux

```
⏰ Cron 9h (lun-ven)  ──┐
                         ├──► 🏥 Health Check
▶️ Lancement Manuel ────┘        │
                                 ├─ ❌ API down → erreur
                                 │
                           🔍 Lancer Scraping
                                 │
                           ⏳ Attendre 30s
                                 │
                           📊 Statut Scraping ◄──────┐
                                 │                    │
                           🔄 Encore en cours ? ─oui─ ⏳ 60s
                                 │ non
                           ❌ Erreur ? ─oui─ log erreur
                                 │ non
                           📈 Scoring IT
                                 │
                           🎯 Opportunités IT ?
                            │              │
                           oui            non → ℹ️ fin
                            │
                      🚀 Pipeline Complet
                            │
                      📁 Lister Dossiers
                            │
                      📋 Préparer Résumé
                            │
                      🔥 Hot ? ─oui─ 📧 Alerte HOT
                            │
                      📧 Rapport Quotidien
```

## Personnalisation

### Changer l'heure du Cron
Dans le nœud "⏰ Cron Quotidien 9h", modifier l'expression cron :
- `0 9 * * 1-5` = 9h du lundi au vendredi
- `0 8,14 * * *` = 8h et 14h tous les jours
- `0 */6 * * *` = toutes les 6 heures

### Activer RAG/LLM
Dans le nœud "🚀 Pipeline Complet", changer le body JSON :
```json
{
  "generate_dossiers": true,
  "use_rag": true,
  "enrich_cps": true,
  "all_priorities": true
}
```

### Ajouter des notifications Slack/Teams
Après le nœud "📋 Préparer Résumé", ajouter un nœud Slack ou Microsoft Teams.

### Configurer l'email
Les nœuds email (📧) nécessitent un credential SMTP dans n8n :
1. Settings → Credentials → Add → SMTP
2. Host: smtp.gmail.com / smtp.office365.com
3. Port: 587, User: votre email, Password: mot de passe app
