# Marchés Publics AI Platform

Pipeline automatisé de veille, qualification et génération de dossiers pour les appels d'offres IT depuis **marchespublics.gov.ma** pour **Alexsys Solutions** (Data, BI, IA, Cloud, Développement).

## Fonctionnalités

1. **Scraping profond** — Récupération automatique de toutes les consultations ouvertes (Playwright + requests)
2. **Scoring intelligent** — Filtrage par mots-clés pondérés → classification HOT / WARM / COLD
3. **Enrichissement CPS** — Extraction des cahiers des charges (HTML + PDF + OCR)
4. **RAG / LLM** — Enrichissement via IA (Groq / Ollama / OpenAI) : descriptions techniques, requirements, analyse stratégique
5. **Génération de dossiers** — Dossier Technique (12 sections) + Dossier Administratif (8 sections) en DOCX par offre
6. **Export structuré** — CSV + Excel stylisé (18 colonnes)

## Structure

```
marche_ai_platform/
├── core/
│   ├── pipeline.py              # Pipeline complet (scoring, CPS, NLP, DOCX, export)
│   └── rag_engine.py            # Moteur RAG (embeddings, ChromaDB, LLM)
├── scripts/
│   └── scrape_deep.py           # Scraper marchespublics.gov.ma
├── generate_dossiers_rag.py     # Script génération dossiers (incrémental)
├── data/
│   ├── pipeline_results_*.csv   # Résultats pipeline
│   ├── rag_cache_all.json       # Cache RAG incrémental
│   └── chroma_db/               # Vector store (ChromaDB)
├── dossiers_generes/            # 52 dossiers DOCX (26 technique + 26 administratif)
├── requirements.txt
├── .env                         # Configuration LLM et API keys
└── DOCUMENTATION_TECHNIQUE.md   # Documentation technique détaillée
```

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Installer Playwright (pour le scraper)
playwright install chromium

# Optionnel : modèle spaCy français (NLP avancé)
python -m spacy download fr_core_news_md

# Optionnel : Ollama pour LLM local (fallback)
# winget install Ollama.Ollama
# ollama pull gemma3:4b
```

## Configuration (.env)

```env
LLM_PROVIDER=groq                    # groq | ollama | openai
GROQ_API_KEY=gsk_...                 # Clé API Groq (gratuite sur console.groq.com)
OLLAMA_MODEL=gemma3:4b               # Modèle Ollama local (fallback)
OPENAI_API_KEY=sk-...                # Optionnel
```

## Utilisation

### 1. Scraping des consultations

```bash
python -X utf8 scripts/scrape_deep.py
# → Génère data/appels_offres_profond_YYYYMMDD_HHMMSS.csv
```

### 2. Pipeline complet (scoring → CPS → NLP → export)

```bash
python -m core.pipeline data/appels_offres_profond_XXXXXXXX.csv --output dossiers_generes --all
```

### 3. Génération de dossiers avec RAG (enrichissement LLM + DOCX)

```bash
# Enrichir via LLM + générer les dossiers DOCX
python generate_dossiers_rag.py

# Générer les DOCX depuis le cache (sans appels LLM)
python generate_dossiers_rag.py --generate-only

# Enrichir seulement (remplir le cache)
python generate_dossiers_rag.py --enrich-only
```

### 4. Tester le moteur RAG

```bash
python -m core.rag_engine
# → Vérifie embeddings, ChromaDB, LLM
```

## Stack technique

| Package | Usage |
|---------|-------|
| python-docx | Génération DOCX (dossiers technique + administratif) |
| openpyxl | Export Excel stylisé |
| chromadb | Vector store local (RAG) |
| sentence-transformers | Embeddings multilingues (local) |
| groq | LLM Groq API (Llama 3.3 70B gratuit) |
| ollama | LLM local (fallback) |
| requests + beautifulsoup4 | Scraping HTTP |
| playwright | Navigation dynamique |
| spaCy | NLP (optionnel) |

## Résultats (11 mars 2026)

- **565** consultations scrappées → **26** opportunités IT (8 HOT, 14 WARM, 4 COLD)
- **52** dossiers DOCX générés (26 technique + 26 administratif) — ~2 MB
- **7/26** enrichis via RAG (descriptions LLM ~3000 chars + 9 requirements + analyse stratégique)
