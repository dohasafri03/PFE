"""
Generate DOCX dossiers from RAG-enriched consultations.
Uses RAG (Groq/Ollama fallback) + pipeline's DossierGenerator.
Incremental: saves RAG cache after each enrichment so progress is not lost.
"""
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict
from datetime import datetime
from enum import Enum

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

# Import pipeline classes
sys.path.insert(0, str(Path(__file__).parent))
from core.pipeline import Consultation, Priority, DossierGenerator
from core.rag_engine import RAGEngine, RAGConfig

RAG_CACHE_FILE = "data/rag_cache_all.json"


def load_rag_cache() -> Dict[str, dict]:
    """Load incremental RAG cache from disk."""
    cache = {}
    # Load from multiple sources
    for path in [RAG_CACHE_FILE, "data/rag_test_results_20260310_232601.json"]:
        if Path(path).exists():
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for d in data:
                    cache[d['id']] = d
            elif isinstance(data, dict):
                cache.update(data)
    logger.info(f"RAG cache: {len(cache)} entries loaded")
    return cache


def save_rag_cache(cache: Dict[str, dict]):
    """Save RAG cache incrementally."""
    Path(RAG_CACHE_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(RAG_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(cache.values()), f, ensure_ascii=False, indent=2)


def apply_rag_to_consultation(c: Consultation, rag_data: dict):
    """Apply RAG data to a consultation object."""
    if rag_data.get('description_technique'):
        c.description_technique = rag_data['description_technique']
    if rag_data.get('description_fonctionnelle'):
        c.description_fonctionnelle = rag_data['description_fonctionnelle']
    if rag_data.get('requirements'):
        c.requirements = rag_data['requirements']
    if rag_data.get('forces'):
        c.strengths = rag_data['forces']
    if rag_data.get('risques'):
        c.risks = rag_data['risques']
    if rag_data.get('recommandations'):
        c.recommendations = rag_data['recommandations']


def load_consultations(csv_path: str) -> List[Consultation]:
    """Load consultations from CSV results."""
    consultations = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            priority_str = row.get('Priorite', 'COLD')
            try:
                priority = Priority(priority_str)
            except ValueError:
                priority = Priority.COLD

            c = Consultation(
                id=row.get('ID', ''),
                reference=row.get('ID', ''),
                objet=row.get('Titre', ''),
                acheteur=row.get('Client', ''),
                categorie=row.get('Categorie', ''),
                nature_prestation=row.get('Nature', ''),
                date_publication=row.get('Date_Publication', ''),
                date_limite=row.get('Date_Limite', ''),
                estimation_budget=row.get('Budget_Estime', ''),
                caution_provisoire=row.get('Caution', ''),
                procedure=row.get('Procedure', ''),
                domaines_activite=row.get('Domaines_Activite', ''),
                qualifications=row.get('Qualifications', ''),
                allotissement=row.get('Allotissement', ''),
                reservation_pme=row.get('Reservation_PME', ''),
                cps_source=row.get('CPS_Source', ''),
                url=row.get('URL_Offre', ''),
                source=row.get('Source', 'marchespublics.gov.ma'),
                priority=priority,
                score_total=float(row.get('Score', '0') or '0'),
                description_technique=row.get('Description_Technique', ''),
                description_fonctionnelle=row.get('Description_Fonctionnelle', ''),
            )
            # Parse domains
            domains_str = row.get('Domaines_Matches', '')
            if domains_str and domains_str != '-':
                c.matched_domains = [d.strip() for d in domains_str.split(',')]
            # Parse domain scores
            score_parts = row.get('Scores_Domaines', '')
            if score_parts and score_parts != '-':
                for part in score_parts.split(','):
                    if ':' in part:
                        k, v = part.split(':')
                        c.domain_scores[k.strip()] = int(v.strip())

            consultations.append(c)

    logger.info(f"Loaded {len(consultations)} consultations from CSV")
    return consultations


def main(generate_only=False, enrich_only=False):
    print("=" * 60)
    print("GENERATION DOSSIERS DOCX — RAG Incrémental + LLM")
    print("=" * 60)

    csv_path = "data/pipeline_results_20260310_132800.csv"
    output_dir = "dossiers_generes"

    # Load consultations from CSV
    consultations = load_consultations(csv_path)

    # Load RAG cache (incremental — survives restarts)
    rag_cache = load_rag_cache()

    # Apply cached RAG data to consultations
    cached_count = 0
    for c in consultations:
        ref = c.reference or c.id
        if ref in rag_cache:
            apply_rag_to_consultation(c, rag_cache[ref])
            cached_count += 1

    # Show stats
    priorities = {}
    rag_enriched = 0
    for c in consultations:
        priorities[c.priority.value] = priorities.get(c.priority.value, 0) + 1
        if c.description_technique and len(c.description_technique) > 200:
            rag_enriched += 1
    print(f"\nConsultations: {len(consultations)}")
    print(f"Distribution: {priorities}")
    print(f"Deja en cache RAG: {cached_count}")
    print(f"A enrichir: {len(consultations) - cached_count}")

    if not generate_only:
        # Initialize RAG engine
        config = RAGConfig.from_env()
        rag = RAGEngine(config)

        # Enrich ALL consultations that don't have RAG content yet
        unenriched = [c for c in consultations if not c.requirements]

        if unenriched:
            print(f"\nEnrichissement RAG de {len(unenriched)} consultations...")
            for i, c in enumerate(unenriched):
                ref = c.reference or c.id
                print(f"  [{i+1}/{len(unenriched)}] [{c.priority.value}] {ref} — {c.objet[:55]}...")
                try:
                    # Build contenu_cps if missing
                    if not c.contenu_cps:
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
                        c.contenu_cps = '\n'.join(parts)
                        c.cps_source = 'csv'

                    rag.enrich_consultation(c)
                    print(f"    ✅ OK ({len(c.description_technique)} car., {len(c.requirements)} reqs)")

                    # Save to cache immediately (incremental — survives crashes)
                    rag_cache[ref] = {
                        'id': ref,
                        'objet': c.objet,
                        'description_technique': c.description_technique,
                        'description_fonctionnelle': c.description_fonctionnelle,
                        'requirements': c.requirements,
                        'forces': c.strengths,
                        'risques': c.risks,
                        'recommandations': c.recommendations,
                    }
                    save_rag_cache(rag_cache)

                    # Rate limit pause
                    if i < len(unenriched) - 1:
                        time.sleep(12)
                except Exception as e:
                    print(f"    ❌ Erreur: {e}")
        else:
            print("\n✅ Toutes les consultations sont deja enrichies via RAG.")
    else:
        print("\n⏭ Mode --generate-only: enrichissement RAG skippé.")

    if enrich_only:
        print("\n⏭ Mode --enrich-only: generation DOCX skippée.")
        return

    # Generate DOCX dossiers for ALL 26 consultations
    print(f"\n{'=' * 60}")
    print(f"GENERATION DOSSIERS DOCX — {len(consultations)} consultations")
    print(f"{'=' * 60}")

    generator = DossierGenerator(output_dir=output_dir)
    all_paths = []
    stats = {'HOT': 0, 'WARM': 0, 'COLD': 0}

    for i, c in enumerate(consultations):
        print(f"\n[{i+1}/{len(consultations)}] [{c.priority.value}] {c.reference}")
        print(f"  Objet: {c.objet[:70]}...")
        print(f"  RAG: desc_tech={len(c.description_technique)}ch, reqs={len(c.requirements)}")

        try:
            paths = generator.generate(c)
            all_paths.extend(paths)
            stats[c.priority.value] = stats.get(c.priority.value, 0) + 1
            for p in paths:
                print(f"  📄 {p}")
        except Exception as e:
            print(f"  ❌ Erreur generation: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 60}")
    print(f"RESUME:")
    print(f"  Dossiers generes: {len(all_paths)} ({len(all_paths)//2} technique + {len(all_paths)//2} administratif)")
    print(f"  Par priorite: HOT={stats.get('HOT',0)}, WARM={stats.get('WARM',0)}, COLD={stats.get('COLD',0)}")
    print(f"  Repertoire: {output_dir}/")
    total_size = 0
    for p in all_paths:
        size = Path(p).stat().st_size / 1024
        total_size += size
    print(f"  Taille totale: {total_size:.0f} KB ({total_size/1024:.1f} MB)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate-only', action='store_true',
                        help='Skip enrichment, generate dossiers from cache only')
    parser.add_argument('--enrich-only', action='store_true',
                        help='Only enrich via RAG, skip dossier generation')
    args = parser.parse_args()
    main(generate_only=args.generate_only, enrich_only=args.enrich_only)
