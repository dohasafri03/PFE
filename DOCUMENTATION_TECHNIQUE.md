# Marché AI Platform — Documentation Technique

## Vue d'ensemble

**Marché AI Platform** est une plateforme d'intelligence artificielle pour la veille et l'analyse automatique des appels d'offres publics marocains, développée pour **Alexsys Solutions** (Data | BI | IA | Cloud | Développement).

La plateforme automatise le cycle complet : de la détection des opportunités sur le portail **marchespublics.gov.ma** jusqu'à la génération de dossiers de candidature prêts à soumettre.

---

## Mise à jour (2026-03-24)

Les changements ci-dessous ont été ajoutés pour stabiliser l'exécution locale et aligner les données affichées sur le portail :

- Budget (Dhs) : correction du parsing `984 000,00` (évite le x100) + affichage au format portail `984 000,00 DH` dans le Dashboard et l'email.
- Génération dossiers : génération uniquement pour les opportunités qualifiées (`Priorite != EXCLUDED`) quand on part de `pipeline_results_*.csv`.
- Service (AI/DATA/CLOUD/DEV/IT) : détection par mots-clés dans `Titre + Domaines_Activite + Qualification` avec garde-fou (maintenance/support/licences -> IT).
- Likes / Profil / Notifications : endpoints API + UI Dashboard (auth requise).
- Workflow n8n : ajout du node `Top Opportunities` (appel `POST /pipeline/score`) + email HTML pro via `email_html`.
- Local : passage sur le port **8001** par défaut pour éviter les conflits Windows sur `:8000` (Docker/WSL/anciennes instances).

---

## Démarrage (Local / Docker)

### Local (recommandé pour debug)

- API : `start_api.bat` lance FastAPI sur `http://127.0.0.1:8001`
- Dashboard : par défaut utilise `VITE_API_URL` sinon `http://localhost:8001`
- n8n : dans le workflow, `API_BASE_URL` doit pointer vers `http://127.0.0.1:8001`

### Docker (production-like)

- `docker-compose.n8n.yml` fournit :
  - API `http://localhost:8000`
  - n8n `http://localhost:5678`
  - variable n8n : `API_BASE_URL=http://api:8000` (réseau Docker)

---

## Authentification (Dashboard)

- Login API : `POST /auth/login` (cookie `marche_ai_token` HttpOnly)
- Utilisateur par défaut : `admin / admin`
- Stockage local : `data/users.json` (hash PBKDF2 + salt)
- Changement mot de passe : `POST /auth/change-password`

## Architecture

```
marche_ai_platform/
│
├── api/                           # FastAPI (endpoints + orchestration)
├── app/                           # SQLAlchemy (SQLite) + models/init
├── Dashboard/                      # Frontend React (Dashboard UI)
├── n8n/                            # Workflow n8n (JSON + README)
├── scripts/
│   └── scrape_deep.py              # Scraper profond (Playwright + Requests)
│
├── core/
│   ├── pipeline.py                 # Pipeline d'analyse en 7 étapes (~2400 lignes)
│   │   ├── Consultation             # Dataclass (30+ champs)
│   │   ├── ScoringEngine            # Qualification par mots-clés pondérés
│   │   ├── CPSExtractor             # Extraction CPS (HTML + PDF + OCR)
│   │   ├── NLPAnalyzer              # Analyse NLP (spaCy)
│   │   ├── DossierGenerator         # Génération DOCX (12 sections tech + 8 admin)
│   │   └── Pipeline                 # Orchestrateur 7 étapes
│   │
│   └── rag_engine.py               # Moteur RAG (~600 lignes)
│       ├── RAGConfig                # Configuration (Groq/Ollama/OpenAI)
│       ├── RAGEngine                # Indexation + Retrieval + Génération LLM
│       ├── chunk_text()             # Découpage texte en chunks
│       └── enrich_consultation()    # Pipeline RAG complet par consultation
│
├── generate_dossiers_rag.py         # Script génération dossiers (incrémental)
├── data/
│   ├── pipeline_results_*.csv       # Export pipeline (scoring + enrichissement + URL + budget)
│   ├── rag_cache_all.json           # Cache RAG incrémental
│   └── chroma_db/                   # Vector store ChromaDB (persistant)
├── dossiers_generes/                # Dossiers DOCX générés par consultation
├── requirements.txt
└── .env                             # Variables d'environnement (LLM, API keys)
```

---

## Backend API (FastAPI)

### URLs

- Local (debug) : `http://127.0.0.1:8001`
- Docker compose : `http://localhost:8000`

### Endpoints principaux

- `GET /health` : statut (scraping/pipeline + dernier CSV)
- `POST /scrape` + `GET /scrape/status` : scraping (mode rapide/complet)
- `POST /pipeline/run-sync` : pipeline complet (pour n8n)
- `POST /pipeline/score` : scoring seul (rapide) + enrichissement depuis `pipeline_results_*.csv`
- `POST /pipeline/generate-dossiers` : génération dossiers (DOCX/PDF) uniquement pour opportunités qualifiées si `pipeline_results_*.csv` est disponible
- `GET /results/opportunities` : données Dashboard (depuis `pipeline_results_*.csv`, `EXCLUDED` exclu par défaut)
- `GET /results/dossiers/index` : index des dossiers (page Reports)

### Auth / profil / likes / notifications

- `POST /auth/login` / `POST /auth/logout` / `GET /auth/me`
- `POST /auth/change-password`
- `GET/POST /profile/me`, `GET /profile/stats`, `GET/POST /profile/preferences`
- `POST /like/{id}` + `GET /liked` + `GET /recommended`
- `GET /notifications`, `POST /notifications/read/{id}`, `POST /notifications/read_all`

---

## Budget (format portail)

### Source

Le portail fournit souvent une estimation au format : `984 000,00` (séparateur milliers = espace, décimales = virgule).

### Parsing et affichage

- Parsing côté backend : conversion fiable `984 000,00` -> `984000.0` (évite les erreurs x100).
- Affichage côté Dashboard/email : format exact portail `984 000,00 DH`.

---

## Workflow n8n (workflow_pipeline.json)

### Variables

- `API_BASE_URL` : base URL de l'API (local: `http://127.0.0.1:8001`, docker: `http://api:8000`)
- `DASHBOARD_URL` : lien du bouton "Open Dashboard" dans l'email

### Structure (simplifiée)

`Health` -> `Scrape` -> `Filtrer IT` -> `Pipeline` -> `Dossiers RAG` -> `Top Opportunities` -> `Resume` -> `Rapport`

- `Top Opportunities` appelle `POST /pipeline/score` pour générer le Top 10 + budgets + deadlines + URLs (table HTML).
- `Rapport` envoie le contenu HTML `email_html` (SaaS style, responsive, badges HOT/WARM/COLD, CTA).

---

## Les 7 étapes du Pipeline

### Étape 1 — Scraping (Veille automatique)
**Fichier :** `scripts/scrape_deep.py` (796 lignes)

**Ce qu'il fait :**
- Scrape le portail national des marchés publics (marchespublics.gov.ma)
- Couvre les **deux sous-portails** : PRADO (ancien) et BDC (nouveau)
- Recherche avec **25+ mots-clés** ciblés IT (logiciel, ERP, cloud, BI, cybersécurité...)
- Dédoublonne automatiquement les résultats
- Exporte un CSV structuré avec 16 colonnes

**Technologies et pourquoi :**

| Technologie | Rôle | Pourquoi ce choix |
|---|---|---|
| **Playwright** | Navigation web dynamique | Le portail PRADO utilise JavaScript pour le rendu — impossible avec requests seul. Playwright pilote un vrai navigateur (Chromium) et attend le chargement JS |
| **Requests** | HTTP statique | Le portail BDC est en HTML statique — requests est plus rapide et léger que Playwright pour ces pages |
| **BeautifulSoup4** | Parsing HTML | Standard Python pour extraire des données de pages HTML. Tolérant aux erreurs de markup |

**Résultat :** ~565 consultations scrappées → CSV source

---

### Étape 2 — Scoring (Qualification automatique)
**Classe :** `ScoringEngine`

**Ce qu'il fait :**
- Score chaque consultation selon **4 domaines** Alexsys : Dev, Data, IA, Cloud
- Utilise des **regex pondérés** (poids 1 à 3 selon la pertinence du mot-clé)
- Applique des **patterns d'exclusion** (travaux BTP, fournitures médicales, véhicules...)
- Avec **override** : si un mot-clé IT fort est détecté, annule l'exclusion
- Classifie : **HOT** (≥4) / **WARM** (≥2) / **COLD** (≥1) / **EXCLUDED**

**Pourquoi des regex pondérés plutôt qu'un LLM :**
- **Gratuit** — pas de coût API
- **Déterministe** — même consultation = même score, toujours
- **Ultra-rapide** — 565 consultations scorées en <1 seconde
- **Transparent** — on voit exactement quels mots-clés ont matché et leur poids
- **Suffisant** — pour du filtrage binaire (pertinent/non pertinent), les regex fonctionnent très bien

**Résultat :** 8 HOT + 14 WARM + 4 COLD = 26 opportunités IT sur 565

---

### Étape 3 — Enrichissement CPS (Extraction détaillée)
**Classe :** `CPSExtractor`

**Ce qu'il fait :**
- Pour chaque consultation qualifiée, accède à la **page de détail** sur le portail
- Extrait les champs structurés : budget estimé, caution provisoire, procédure, domaines d'activité, qualifications requises, allotissement, réservation PME
- Deux modes d'extraction selon le sous-portail :

| Source | Méthode | Données extraites |
|---|---|---|
| **PRADO** (HTML) | Scraping avec `requests` + `BeautifulSoup` + regex multi-lignes | Budget, caution, procédure, domaines, qualifications, PME |
| **BDC** (PDF) | Téléchargement ZIP → extraction PDF → texte ou OCR | Contenu du cahier des charges |

**Technologies et pourquoi :**

| Technologie | Rôle | Pourquoi |
|---|---|---|
| **Requests + Session** | HTTP avec cookies | Le portail exige une session active (warm-up GET pour les cookies). Sans ça → 403 Forbidden |
| **BeautifulSoup4** | Parsing HTML | Extraction du texte brut de la page de détail PRADO |
| **Regex multi-lignes** | Extraction champs | Les valeurs sont sur des lignes séparées des labels. Ex: `Estimation (en Dhs TTC)\n*\n:\n14 800 000,00`. Les regex gèrent ces sauts de ligne |
| **PyMuPDF (fitz)** | Extraction texte PDF | Rapide, pur Python, extrait le texte des PDF vectoriels sans OCR. Plus rapide et léger que pdfplumber |
| **Pytesseract + Pillow** | OCR (PDF scannés) | Certains CPS sont des scans image. Tesseract fait l'OCR en français/arabe (`fra+ara`). Pillow convertit les pages en images |

**Résultat :** 21/26 consultations enrichies (20 PRADO + 1 BDC), 5 échouées (authentification requise)

---

### Étape 3.5 — Enrichissement RAG (LLM)
**Classe :** `RAGEngine` (fichier `core/rag_engine.py`, ~600 lignes)

**Ce qu'il fait :**
- **Indexation** : Découpe le contenu CPS en chunks (800 chars, overlap 100) → Embeddings multilingues → Stockage dans ChromaDB
- **Retrieval** : Pour chaque prompt, recherche les chunks les plus pertinents via similarité cosinus
- **Génération LLM** : Utilise le contexte récupéré + contexte Alexsys Solutions pour générer :
  - **Description technique** (~3000 chars) — analyse structurée des besoins, volets Dev/Data/Infra
  - **Description fonctionnelle** (~2500 chars) — objectifs, livrables, bénéfices client
  - **Requirements** (6-10 items) — compétences et qualifications requises
  - **Analyse stratégique** — score d'adéquation, forces, risques, recommandations

**Chaîne de fallback LLM :**
1. **Groq** (primaire) — API gratuite, Llama 3.3 70B, ~2-3s/appel
2. **Ollama** (fallback) — Local, gemma3:4b, ~18-40s/appel sur CPU
3. **OpenAI** (fallback) — GPT-4o, payant

**Cache incrémental :** Chaque enrichissement est sauvegardé dans `data/rag_cache_all.json` pour résister aux crashs et limites API.

**Technologies et pourquoi :**

| Technologie | Rôle | Pourquoi |
|---|---|---|
| **ChromaDB** | Vector store local | Persistant, pur Python, pas de serveur externe. Stocke embeddings + métadonnées |
| **sentence-transformers** | Embeddings | Modèle `paraphrase-multilingual-MiniLM-L12-v2` (384 dims) — multilingue FR/AR/EN, local, gratuit, rapide |
| **Groq API** | LLM principal | Gratuit (100K tokens/jour), Llama 3.3 70B, très rapide (inférence GroqChip) |
| **Ollama** | LLM local | Fallback quand Groq est épuisé. gemma3:4b sur CPU. Aucune dépendance cloud |
| **PyTorch** | Backend ML | Requis par sentence-transformers. Version CPU (pas de GPU nécessaire) |

**Résultat :** Descriptions riches et personnalisées (vs templates statiques), analyse stratégique avec forces/risques

---

### Étape 4 — Analyse NLP
**Classe :** `NLPAnalyzer`

**Ce qu'il fait :**
- Extraction d'entités nommées (organisations, produits, lieux)
- Catégorisation automatique par domaine (Dev/Logiciel, Data/BI, IA/ML, Cloud/Infra)
- Score de confiance basé sur le scoring
- Résumé automatique (3 premières phrases)
- Complète les descriptions si pas de contenu RAG

**Technologies et pourquoi :**

| Technologie | Rôle | Pourquoi |
|---|---|---|
| **spaCy** (`fr_core_news_md`) | NLP français | Modèle français pré-entraîné, rapide, offline. NER + segmentation de phrases |

**Note :** Le NLP est optionnel — le pipeline fonctionne sans spaCy. Avec RAG activé, les descriptions LLM remplacent les templates NLP.

---

### Étape 5 — Génération de dossiers
**Classe :** `DossierGenerator`

**Ce qu'il fait :**
Pour chaque consultation qualifiée, génère :

1. **Dossier Technique** (.docx) — **12 sections** :
   1. Page de garde Alexsys Solutions
   2. Informations de la consultation
   3. Description technique détaillée (rendu Markdown → DOCX)
   4. Description fonctionnelle (rendu Markdown → DOCX)
   5. Requirements (compétences et qualifications)
   6. **Analyse stratégique** (points forts, risques, recommandations)
   7. Méthodologie proposée
   8. Architecture technique
   9. Équipe projet
   10. Planning prévisionnel
   11. Livrables
   12. Garantie et maintenance

2. **Dossier Administratif** (.docx) — 8 sections :
   - Page de garde
   - Informations de l'entreprise (raison sociale, siège, RC, IF, ICE...)
   - Données de la consultation
   - Check-list des pièces requises

**Markdown → DOCX :** La méthode `_add_markdown_text()` convertit le Markdown généré par le LLM en mise en forme DOCX (gras, titres, listes à puces, listes numérotées, gras inline).

**Technologies et pourquoi :**

| Technologie | Rôle | Pourquoi |
|---|---|---|
| **python-docx** | Génération Word | Standard pour créer des DOCX en Python. Supporte le formatage (gras, couleurs, tailles, tableaux). Les marchés publics marocains demandent souvent des dossiers en Word |

---

### Étape 6 — Export des résultats
**Ce qu'il fait :**
- Export **CSV** (séparateur `;`, encodage UTF-8 BOM) — compatible Excel FR
- Export **Excel** (.xlsx) avec mise en forme conditionnelle :
  - En-têtes colorés (bleu foncé)
  - Colonnes auto-dimensionnées
  - Filtre automatique

**18 colonnes exportées :**
ID, Priorité, Qualification, Titre, Client, Deadline, Budget Estimé, Caution, Procédure, Domaines d'Activité, Qualifications, Allotissement, Réservation PME, CPS Source, Description Technique, Description Fonctionnelle, Requirements, URL Offre

**Technologies et pourquoi :**

| Technologie | Rôle | Pourquoi |
|---|---|---|
| **openpyxl** | Génération Excel | Permet de créer des .xlsx avec style (couleurs, filtres, largeurs). Le CSV seul ne supporte pas le formatage |

---

## Stack technologique complète

| Couche | Technologie | Version | Rôle |
|---|---|---|---|
| **Langage** | Python | 3.13 | Écosystème riche pour le data/scraping/NLP/IA |
| **Scraping dynamique** | Playwright | 1.58.0 | Rendu JavaScript (portail PRADO) |
| **Scraping statique** | Requests | 2.32.5 | HTTP simple (portail BDC) |
| **Parsing HTML** | BeautifulSoup4 | 4.14.3 | Extraction données des pages web |
| **Extraction PDF** | PyMuPDF | 1.27.2 | Texte des PDF vectoriels |
| **OCR** | Pytesseract + Pillow | 0.3.13 / 12.1.1 | PDF scannés → texte (fra+ara) |
| **Embeddings** | sentence-transformers | 5.2.3 | Embeddings multilingues FR/AR/EN (384 dims, local) |
| **Vector Store** | ChromaDB | 1.5.5 | Stockage et recherche vectorielle locale persistante |
| **LLM (cloud)** | Groq API | — | Llama 3.3 70B (gratuit, 100K tokens/jour) |
| **LLM (local)** | Ollama + gemma3:4b | — | Fallback local CPU (aucun cloud requis) |
| **LLM (fallback)** | OpenAI API | — | GPT-4o (payant, en secours) |
| **ML Backend** | PyTorch | 2.10.0+cpu | Backend pour sentence-transformers |
| **NLP** | spaCy (fr_core_news_md) | ≥3.7 | Entités, catégorisation (optionnel) |
| **Génération DOCX** | python-docx | 1.2.0 | Dossiers technique + administratif |
| **Export Excel** | openpyxl | 3.1.5 | Export xlsx avec mise en forme |
| **OS** | Windows 10 | — | Environnement de développement |

---

## Architecture IA : NLP + RAG/LLM

### Couche 1 : NLP classique (scoring + filtrage)
- **Coût : 0€** — regex pondérés + spaCy en local
- **Vitesse** — 565 consultations scorées en <1 seconde
- **Déterminisme** — même consultation = même score, toujours
- **Rôle** — filtrage rapide (565 → 26 opportunités)

### Couche 2 : RAG/LLM (enrichissement + rédaction)
- **Coût : 0€** — Groq API gratuite (100K tokens/jour) + Ollama local en fallback
- **Vitesse** — ~10s par consultation (Groq) / ~90s (Ollama CPU)
- **Rôle** — Génération de contenu riche et personnalisé pour les dossiers :
  - Descriptions techniques et fonctionnelles contextualisées
  - Requirements extraits intelligemment
  - Analyse stratégique (forces, risques, recommandations)

### Chaîne de fallback LLM
```
Groq (Llama 3.3 70B) → Ollama (gemma3:4b local) → OpenAI (GPT-4o)
          ↓                      ↓                       ↓
   Gratuit, rapide        Gratuit, lent CPU         Payant, rapide
   100K tokens/jour       Illimité                  Budget requis
```

### Cache RAG incrémental
- Chaque enrichissement est sauvegardé dans `data/rag_cache_all.json`
- Résiste aux crashes, limites API, et redémarrages
- Le script `generate_dossiers_rag.py` reprend automatiquement depuis le cache

---

## Commandes

```bash
# 1. Scraping (veille)
python -X utf8 scripts/scrape_deep.py

# 2. Pipeline complet (scoring + enrichissement + NLP + génération + export)
python -m core.pipeline data/appels_offres_profond_XXXXXXXX.csv --output dossiers_generes --all

# 3. Pipeline avec RAG activé (scoring + CPS + NLP + RAG + génération)
python -m core.pipeline data/appels_offres_profond_XXXXXXXX.csv --rag --output dossiers_generes

# 4. Pipeline sans génération de dossiers (analyse seule)
python -m core.pipeline data/appels_offres_profond_XXXXXXXX.csv --no-generate

# 5. Pipeline HOT seulement
python -m core.pipeline data/appels_offres_profond_XXXXXXXX.csv --hot-only

# 6. Génération dossiers RAG — enrichissement + DOCX (toutes les 26 consultations)
python generate_dossiers_rag.py

# 7. Génération dossiers RAG — DOCX seulement (depuis cache, sans appels LLM)
python generate_dossiers_rag.py --generate-only

# 8. Enrichissement RAG seul (remplir le cache, sans générer de DOCX)
python generate_dossiers_rag.py --enrich-only

# 9. Test du moteur RAG (vérifier embeddings, ChromaDB, LLM)
python -m core.rag_engine
```

---

## Résultats actuels (11 mars 2026)

| Métrique | Valeur |
|---|---|
| Consultations scrappées | 565 |
| Opportunités IT détectées | 26 (4.6%) |
| Priorité HOT | 8 |
| Priorité WARM | 14 |
| Priorité COLD | 4 |
| Consultations enrichies (CPS) | 21/26 (81%) |
| Budget extrait | 17/26 |
| Domaines d'activité | 20/26 |
| Réservation PME | 17/26 |
| **RAG enrichies (LLM)** | **7/26** |
| **Dossiers DOCX générés** | **52** (26 technique + 26 administratif) |
| **Taille totale dossiers** | **~2 MB** |

---

## Portails couverts

| Portail | URL | Type | Méthode |
|---|---|---|---|
| **PRADO** (ancien) | marchespublics.gov.ma/?page=... | HTML dynamique (JS) | Playwright (scraping) + Requests (enrichissement) |
| **BDC** (nouveau) | marchespublics.gov.ma/bdc/... | HTML statique | Requests + ZIP/PDF extraction |

---

## Variables d'environnement (.env)

```env
# LLM / RAG
LLM_PROVIDER=groq                    # groq | ollama | openai
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=gsk_...                  # Clé API Groq (gratuite)
OLLAMA_MODEL=gemma3:4b               # Modèle Ollama local
OLLAMA_BASE_URL=http://localhost:11434
OPENAI_MODEL=gpt-4o
OPENAI_API_KEY=sk-...                 # Optionnel

# Embeddings
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

---

*Document mis à jour le 11 mars 2026 — Alexsys Solutions*
