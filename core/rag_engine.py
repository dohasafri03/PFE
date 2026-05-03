"""
RAG Engine — Retrieval-Augmented Generation pour les marchés publics.

Utilise :
- ChromaDB comme vector store local (persistant)
- sentence-transformers pour les embeddings (local, gratuit)
- Ollama (Mistral) comme LLM principal (local, gratuit)
- OpenAI (GPT-4o) comme fallback optionnel

Usage:
    from core.rag_engine import RAGEngine
    rag = RAGEngine()
    rag.index_consultation(consultation)
    result = rag.generate_dossier_technique(consultation)
"""

import json
import logging
import os
import re
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


# ============================================================
# Configuration
# ============================================================

@dataclass
class RAGConfig:
    """Configuration for the RAG engine."""
    # Embeddings
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    # Vector store
    chroma_persist_dir: str = "data/chroma_db"
    collection_name: str = "consultations"
    # LLM
    llm_provider: str = "groq"  # "groq", "ollama", or "openai"
    ollama_model: str = "mistral"
    ollama_base_url: str = "http://localhost:11434"
    openai_model: str = "gpt-4o"
    openai_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_api_key: str = ""
    # Chunking
    chunk_size: int = 800
    chunk_overlap: int = 100
    # Generation
    max_context_chunks: int = 10
    temperature: float = 0.3

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Load config from environment / .env file."""
        # Try loading .env
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    os.environ.setdefault(key.strip(), val.strip())

        return cls(
            embedding_model=os.environ.get('EMBEDDING_MODEL', cls.embedding_model),
            ollama_model=os.environ.get('OLLAMA_MODEL', 'mistral'),
            ollama_base_url=os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434'),
            openai_model=os.environ.get('OPENAI_MODEL', 'gpt-4o'),
            openai_api_key=os.environ.get('OPENAI_API_KEY', ''),
            groq_model=os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile'),
            groq_api_key=os.environ.get('GROQ_API_KEY', ''),
            llm_provider=os.environ.get('LLM_PROVIDER', 'groq'),
        )


# ============================================================
# Text Chunking
# ============================================================

def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """Split text into overlapping chunks by sentence boundaries."""
    if not text or len(text) < chunk_size:
        return [text] if text else []

    # Split by sentences (French punctuation)
    sentences = re.split(r'(?<=[.!?;])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 > chunk_size and current:
            chunks.append(current.strip())
            # Keep overlap from end of current chunk
            words = current.split()
            overlap_text = ' '.join(words[-overlap // 5:]) if len(words) > overlap // 5 else ''
            current = overlap_text + ' ' + sentence
        else:
            current = (current + ' ' + sentence).strip()

    if current.strip():
        chunks.append(current.strip())

    return chunks


# ============================================================
# RAG Engine
# ============================================================

class RAGEngine:
    """
    Retrieval-Augmented Generation engine.

    Indexes consultation data into ChromaDB, then uses an LLM
    to generate high-quality technical/administrative dossier content
    grounded in the actual CPS/consultation data.
    """

    # Alexsys Solutions company context for the LLM
    COMPANY_CONTEXT = """
Alexsys Solutions est une ESN marocaine experte et leader dans les services IT et la transformation digitale :
- Siège social : 37 Allée des Eucalyptus, Ain-Sebaa, 20590, Casablanca
- Domaines d'expertise : Intégration Data & BI, Intelligence Artificielle (LLMs, RAG, Machine Learning), Cloud & Infrastructure, Cybersécurité, Développement logiciel sur-mesure (Web, Mobile).
- Technologies maîtrisées courantes : Python, Java/Spring, .NET, Node.js, React, Power BI, Tableau, Azure, AWS, GCP, Docker, Kubernetes.
- Certifications & Partenariats : Microsoft Gold Partner, AWS Advanced Partner.
- Méthodologies de gestion : Agile/Scrum, DevOps, ITIL V4, PMBOK.
- Références : Plusieurs projets d'envergure réalisés pour l'administration publique (CNOPS, Ministères) et les banques/assurances marocaines. Nous avons une forte compréhension des normes de qualité de l'État marocain.
"""

    def __init__(self, config: Optional[RAGConfig] = None):
        self.config = config or RAGConfig.from_env()
        self._embedder = None
        self._collection = None
        self._chroma_client = None

    # ---- Lazy initialization ----

    @property
    def embedder(self):
        """Lazy-load the sentence-transformers model."""
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.config.embedding_model}")
            self._embedder = SentenceTransformer(self.config.embedding_model)
            logger.info("Embedding model loaded")
        return self._embedder

    @property
    def collection(self):
        """Lazy-init ChromaDB collection."""
        if self._collection is None:
            import chromadb
            persist_dir = Path(self.config.chroma_persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(path=str(persist_dir))
            self._collection = self._chroma_client.get_or_create_collection(
                name=self.config.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB collection '{self.config.collection_name}' ready ({self._collection.count()} docs)")
        return self._collection

    # ---- Indexing ----

    def index_consultation(self, consultation) -> int:
        """
        Index a consultation's content into the vector store.
        Returns number of chunks indexed.
        """
        ref = consultation.reference or consultation.id
        # Build indexable text from all available fields
        parts = []
        if consultation.objet:
            parts.append(f"Objet: {consultation.objet}")
        if consultation.acheteur:
            parts.append(f"Acheteur: {consultation.acheteur}")
        if consultation.nature_prestation:
            parts.append(f"Nature: {consultation.nature_prestation}")
        if consultation.articles:
            parts.append(f"Articles: {consultation.articles}")
        if consultation.estimation_budget:
            parts.append(f"Budget estimé: {consultation.estimation_budget}")
        if consultation.procedure:
            parts.append(f"Procédure: {consultation.procedure}")
        if consultation.domaines_activite:
            parts.append(f"Domaines d'activité: {consultation.domaines_activite}")
        if consultation.qualifications:
            parts.append(f"Qualifications requises: {consultation.qualifications}")
        if consultation.reservation_pme:
            parts.append(f"Réservation: {consultation.reservation_pme}")
        if consultation.allotissement:
            parts.append(f"Allotissement: {consultation.allotissement}")
        if consultation.contenu_cps:
            parts.append(f"Contenu CPS:\n{consultation.contenu_cps}")

        full_text = '\n'.join(parts)
        if not full_text.strip():
            return 0

        # Chunk the text
        chunks = chunk_text(full_text, self.config.chunk_size, self.config.chunk_overlap)
        if not chunks:
            return 0

        # Generate embeddings
        embeddings = self.embedder.encode(chunks).tolist()

        # Upsert into ChromaDB (use hash-based IDs for deduplication)
        ids = []
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(f"{ref}_{i}_{chunk[:50]}".encode()).hexdigest()
            ids.append(chunk_id)

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=[{
                "reference": ref,
                "chunk_index": i,
                "source": consultation.cps_source or "csv",
                "priority": consultation.priority.value if hasattr(consultation.priority, 'value') else str(consultation.priority),
            } for i, _ in enumerate(chunks)]
        )

        logger.debug(f"Indexed {len(chunks)} chunks for {ref}")
        return len(chunks)

    def index_all(self, consultations: list) -> Dict[str, int]:
        """Index all relevant consultations. Returns stats."""
        total_chunks = 0
        indexed = 0
        for c in consultations:
            if hasattr(c, 'is_excluded') and c.is_excluded:
                continue
            n = self.index_consultation(c)
            if n > 0:
                indexed += 1
                total_chunks += n
        logger.info(f"Indexed {indexed} consultations ({total_chunks} chunks total)")
        return {"indexed": indexed, "total_chunks": total_chunks}

    # ---- Retrieval ----

    def retrieve(self, query: str, n_results: int = 5, filter_ref: Optional[str] = None) -> List[Dict]:
        """
        Retrieve the most relevant chunks for a query.
        Optionally filter by consultation reference.
        """
        query_embedding = self.embedder.encode([query]).tolist()

        where_filter = {"reference": filter_ref} if filter_ref else None

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=min(n_results, self.collection.count() or 1),
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )

        chunks = []
        if results and results['documents']:
            for doc, meta, dist in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                chunks.append({
                    "text": doc,
                    "metadata": meta,
                    "similarity": 1 - dist,  # cosine distance → similarity
                })
        return chunks

    # ---- LLM Generation ----

    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """Call the configured LLM (Groq, Ollama, or OpenAI)."""
        if self.config.llm_provider == "groq":
            return self._call_groq(prompt, system_prompt)
        elif self.config.llm_provider == "ollama":
            return self._call_ollama(prompt, system_prompt)
        elif self.config.llm_provider == "openai":
            return self._call_openai(prompt, system_prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {self.config.llm_provider}")

    def _call_groq(self, prompt: str, system_prompt: str = "") -> str:
        """Call Groq API (free, fast inference on Llama/Mixtral)."""
        try:
            from groq import Groq
            client = Groq(api_key=self.config.groq_api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.config.groq_model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=2000,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Groq error: {e}. Trying Ollama fallback...")
            try:
                return self._call_ollama(prompt, system_prompt)
            except Exception:
                if self.config.openai_api_key:
                    return self._call_openai(prompt, system_prompt)
                raise

    def _call_ollama(self, prompt: str, system_prompt: str = "") -> str:
        """Call Ollama local LLM."""
        try:
            import ollama as ollama_client
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = ollama_client.chat(
                model=self.config.ollama_model,
                messages=messages,
                options={"temperature": self.config.temperature}
            )
            return response['message']['content']
        except Exception as e:
            logger.warning(f"Ollama error: {e}. Trying OpenAI fallback...")
            if self.config.openai_api_key:
                return self._call_openai(prompt, system_prompt)
            raise

    def _call_openai(self, prompt: str, system_prompt: str = "") -> str:
        """Call OpenAI API."""
        from openai import OpenAI
        client = OpenAI(api_key=self.config.openai_api_key)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.config.openai_model,
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=2000,
        )
        return response.choices[0].message.content

    # ---- High-level generation methods ----

    def generate_dossier_complet(self, consultation) -> Dict[str, Any]:
        """Generate all dossier content and analysis in a single LLM call for maximum speed."""
        ref = consultation.reference or consultation.id
        objet = consultation.objet

        # 1. Retrieve a broader, mixed context
        query = f"description technique besoins fonctionnels exigences qualifications critères {objet}"
        chunks = self.retrieve(query, n_results=self.config.max_context_chunks, filter_ref=ref)
        context = "\n---\n".join([c["text"] for c in chunks]) if chunks else "Pas de contexte CPS disponible."

        system_prompt = f"""Tu es un super-expert en réponse aux appels d'offres publics marocains.
Tu représentes l'entreprise Alexsys Solutions.

{self.COMPANY_CONTEXT}

La consigne :
Tu dois rédiger l'intégralité de l'approche technique, fonctionnelle, stratégique, et les exigences en 1 seul appel.
- Rédige en français professionnel, très précis, en citant activement des éléments du contexte CPS.
- INTERDICTION d'être générique ou creux. Relie l'expertise d'Alexsys au besoin spécifique du client.
- Renvoie UNIQUEMENT un objet JSON valide, strict, selon cette structure exacte (ne mets aucun bloc de texte markdown hors du JSON) :

{{
  "description_technique": "Description technique (max 500 mots, fais le lien métier)...",
  "description_fonctionnelle": "Description des objectifs et livrables (max 400 mots)...",
  "requirements": ["Compétence 1 requise", "Compétence 2 requise", "Profil 1 exigé"],
  "score_adequation": 85,
  "forces": ["Force 1 (ex: très aligné avec nos certifs)", "Force 2"],
  "risques": ["Risque 1", "Risque 2"],
  "recommandations": ["Rec 1", "Rec 2"],
  "resume": "Résumé global de la réponse en 2 ou 3 phrases."
}}"""

        prompt = f"""Génère le dossier complet et structuré en JSON pour l'appel d'offres suivant :

**Objet :** {objet}
**Acheteur :** {consultation.acheteur or 'Non spécifié'}
**Budget estimé :** {consultation.estimation_budget or 'Non communiqué'}
**Procédure :** {consultation.procedure or 'Non spécifiée'}
**Qualifications requises :** {consultation.qualifications or 'Non spécifiées'}
**Domaines matchés :** {', '.join(consultation.matched_domains) if consultation.matched_domains else 'IT'}

**Contexte extrait du cahier des charges (CPS) :**
{context}

JSON Reply uniquement:"""

        try:
            response = self._call_llm(prompt, system_prompt)
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group())
            else:
                logger.warning(f"RAG JSON parse error for {ref}. Fallback parsing active.")
                return {}
        except Exception as e:
            logger.error(f"RAG full generation error for {ref}: {e}")
            return {}

    # ---- Batch operations ----

    def enrich_consultation(self, consultation) -> bool:
        """
        Full RAG enrichment: index + generate descriptions + analysis using a single fast LLM call.
        Updates consultation in-place. Returns True if successful.
        """
        ref = consultation.reference or consultation.id
        try:
            # 1. Index
            n_chunks = self.index_consultation(consultation)
            logger.debug(f"RAG: indexed {n_chunks} chunks for {ref}")

            # 2. Generate EVERYTHING in one burst call (75% faster)
            dossier = self.generate_dossier_complet(consultation)
            
            if not dossier:
                logger.warning(f"RAG returned empty dossier for {ref}")
                return False

            # 3. Map values to consultation
            if dossier.get('description_technique'):
                consultation.description_technique = dossier['description_technique']
                
            if dossier.get('description_fonctionnelle'):
                consultation.description_fonctionnelle = dossier['description_fonctionnelle']
                
            if dossier.get('requirements'):
                consultation.requirements = dossier['requirements']

            consultation.strengths = dossier.get('forces', [])
            consultation.risks = dossier.get('risques', [])
            consultation.recommendations = dossier.get('recommandations', [])

            return True

        except Exception as e:
            logger.error(f"RAG enrichment failed for {ref}: {e}")
            return False


# ============================================================
# CLI for testing
# ============================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    print("=== RAG Engine Test ===")

    config = RAGConfig.from_env()
    print(f"LLM Provider: {config.llm_provider}")
    print(f"Ollama model: {config.ollama_model}")
    print(f"Embedding model: {config.embedding_model}")

    rag = RAGEngine(config)

    # Quick test: embed a sample text
    print("\nTesting embeddings...")
    test_text = "Acquisition de matériel informatique et logiciels pour la cybersécurité"
    embedding = rag.embedder.encode([test_text])
    print(f"Embedding shape: {embedding.shape}")

    # Test ChromaDB
    print("\nTesting ChromaDB...")
    print(f"Collection count: {rag.collection.count()}")

    # Test LLM
    print("\nTesting LLM...")
    try:
        response = rag._call_llm("Dis 'bonjour' en une phrase courte.")
        print(f"LLM response: {response}")
    except Exception as e:
        print(f"LLM error: {e}")

    print("\n=== Done ===")
