"""
Test RAG enrichment on pipeline results.
Loads the 26 consultations from the results CSV and applies RAG generation via Groq.
"""
import csv
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

from core.rag_engine import RAGEngine, RAGConfig


@dataclass
class SimpleConsultation:
    """Lightweight consultation for RAG testing."""
    id: str = ""
    reference: str = ""
    objet: str = ""
    acheteur: str = ""
    procedure: str = ""
    estimation_budget: str = ""
    caution_provisoire: str = ""
    domaines_activite: str = ""
    qualifications: str = ""
    allotissement: str = ""
    reservation_pme: str = ""
    nature_prestation: str = ""
    lieu_execution: str = ""
    email_contact: str = ""
    fichiers_joints: str = ""
    url: str = ""
    articles: str = ""
    contenu_cps: str = ""
    cps_source: str = ""
    priority: str = "WARM"
    score_total: float = 0.0
    matched_domains: List[str] = field(default_factory=list)
    is_excluded: bool = False
    # Fields to be filled by RAG
    description_technique: str = ""
    description_fonctionnelle: str = ""
    requirements: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


def load_from_csv(csv_path: str) -> List[SimpleConsultation]:
    """Load consultations from pipeline results CSV."""
    consultations = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            c = SimpleConsultation(
                id=row.get('ID', ''),
                reference=row.get('ID', ''),
                objet=row.get('Titre', ''),
                acheteur=row.get('Client', ''),
                procedure=row.get('Procedure', ''),
                estimation_budget=row.get('Budget_Estime', ''),
                caution_provisoire=row.get('Caution', ''),
                domaines_activite=row.get('Domaines_Activite', ''),
                qualifications=row.get('Qualifications', ''),
                allotissement=row.get('Allotissement', ''),
                reservation_pme=row.get('Reservation_PME', ''),
                cps_source=row.get('CPS_Source', ''),
                url=row.get('URL_Offre', ''),
                priority=row.get('Priorite', 'WARM'),
                description_technique=row.get('Description_Technique', ''),
                description_fonctionnelle=row.get('Description_Fonctionnelle', ''),
            )
            # Parse matched domains from domaines_activite
            if c.domaines_activite and c.domaines_activite != '-':
                c.matched_domains = [d.strip() for d in c.domaines_activite.split(',')]
            # Build contenu_cps from existing descriptions for indexing
            parts = []
            if c.objet:
                parts.append(f"Objet: {c.objet}")
            if c.acheteur:
                parts.append(f"Acheteur: {c.acheteur}")
            if c.estimation_budget and c.estimation_budget != '-':
                parts.append(f"Budget: {c.estimation_budget}")
            if c.domaines_activite and c.domaines_activite != '-':
                parts.append(f"Domaines: {c.domaines_activite}")
            if c.qualifications and c.qualifications != '-':
                parts.append(f"Qualifications: {c.qualifications}")
            if c.reservation_pme and c.reservation_pme != '-':
                parts.append(f"PME: {c.reservation_pme}")
            if c.description_technique and c.description_technique != '-':
                parts.append(f"Description technique: {c.description_technique}")
            c.contenu_cps = '\n'.join(parts)
            consultations.append(c)
    return consultations


def main():
    print("=" * 60)
    print("TEST RAG - Enrichissement des consultations via Groq")
    print("=" * 60)

    # Load consultations
    csv_path = "data/pipeline_results_20260310_132800.csv"
    consultations = load_from_csv(csv_path)
    print(f"\n{len(consultations)} consultations chargées")

    # Show priority distribution
    priorities = {}
    for c in consultations:
        priorities[c.priority] = priorities.get(c.priority, 0) + 1
    print(f"Distribution: {priorities}")

    # Initialize RAG
    print("\nInitialisation du RAG Engine...")
    config = RAGConfig.from_env()
    print(f"  LLM: {config.llm_provider} / {config.groq_model}")
    print(f"  Embeddings: {config.embedding_model}")
    rag = RAGEngine(config)

    # Test on first 3 HOT consultations
    hot = [c for c in consultations if c.priority == 'HOT']
    test_set = hot[:3] if len(hot) >= 3 else hot + [c for c in consultations if c.priority == 'WARM'][:3 - len(hot)]

    print(f"\nTest sur {len(test_set)} consultations HOT:")
    for i, c in enumerate(test_set):
        print(f"\n{'─' * 60}")
        print(f"[{i+1}/{len(test_set)}] {c.id} — {c.objet[:80]}...")
        print(f"  Client: {c.acheteur}")
        print(f"  Budget: {c.estimation_budget}")
        print(f"  Domaines: {c.domaines_activite}")

        start = time.time()
        success = rag.enrich_consultation(c)
        elapsed = time.time() - start

        if success:
            print(f"  ✅ RAG enrichissement réussi ({elapsed:.1f}s)")
            print(f"\n  📝 Description Technique (extrait):")
            print(f"  {c.description_technique[:300]}...")
            print(f"\n  📋 Description Fonctionnelle (extrait):")
            print(f"  {c.description_fonctionnelle[:300]}...")
            print(f"\n  📌 Requirements ({len(c.requirements)}):")
            for r in c.requirements[:5]:
                print(f"    • {r}")
            print(f"\n  💪 Forces: {c.strengths[:3]}")
            print(f"  ⚠️  Risques: {c.risks[:3]}")
            print(f"  💡 Recommandations: {c.recommendations[:3]}")
        else:
            print(f"  ❌ Échec ({elapsed:.1f}s)")

        # Rate limit: Groq free tier = 30 req/min -> wait 2s between consultations
        if i < len(test_set) - 1:
            print("  ⏳ Pause 8s (rate limit Groq)...")
            time.sleep(8)

    # Save enriched results
    output = []
    for c in test_set:
        output.append({
            "id": c.id,
            "titre": c.objet,
            "client": c.acheteur,
            "priorite": c.priority,
            "description_technique": c.description_technique,
            "description_fonctionnelle": c.description_fonctionnelle,
            "requirements": c.requirements,
            "forces": c.strengths,
            "risques": c.risks,
            "recommandations": c.recommendations,
        })

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = f"data/rag_test_results_{ts}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n\n{'=' * 60}")
    print(f"Résultats sauvegardés: {output_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
