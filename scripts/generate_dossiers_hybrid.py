"""
Génération hybride de dossiers — RAG (Groq) + Pipeline (templates).

Flux :
  1. Lit le CSV filtré IT (format filter_it.py : 14 colonnes, ; sep)
  2. Enrichit via RAG (Groq gratuit) : desc. technique, fonctionnelle, exigences,
     analyse stratégique  (cache incrémental pour ne pas refaire)
  3. Fallback NLP-templates si RAG échoue pour une consultation
  4. Génère DOCX (technique + administratif) via DossierGenerator
  5. Convertit en PDF via docx2pdf (COM Word sur Windows)
  6. Retourne des stats JSON (compatible endpoint API)

Usage CLI :
    python scripts/generate_dossiers_hybrid.py                    # auto-detect CSV
    python scripts/generate_dossiers_hybrid.py data/my_file.csv   # CSV explicite
    python scripts/generate_dossiers_hybrid.py --pdf-only         # juste conversion
"""
import csv
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)
os.environ["PYTHONIOENCODING"] = "utf-8"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from core.pipeline import Consultation, Priority, DossierGenerator, NLPAnalyzer

# ── RAG cache ────────────────────────────────────────────────────────────────
RAG_CACHE = PROJECT_ROOT / "data" / "rag_cache_hybrid.json"


def _load_cache() -> Dict[str, dict]:
    if RAG_CACHE.exists():
        with open(RAG_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {d["id"]: d for d in data if "id" in d}
        return data
    return {}


def _save_cache(cache: Dict[str, dict]):
    RAG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(RAG_CACHE, "w", encoding="utf-8") as f:
        json.dump(list(cache.values()), f, ensure_ascii=False, indent=2)


# ── CSV → Consultation ──────────────────────────────────────────────────────
def _load_it_csv(csv_path: str) -> List[Consultation]:
    """Load consultations from a CSV produced by filter_it.py (14 cols, ; sep)."""
    consultations = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            c = Consultation(
                id=row.get("reference", ""),
                reference=row.get("reference", ""),
                objet=row.get("objet", ""),
                acheteur=row.get("acheteur", ""),
                categorie=row.get("categorie", ""),
                nature_prestation=row.get("nature_prestation", ""),
                date_publication=row.get("date_publication", ""),
                date_limite=row.get("date_limite", ""),
                lieu_execution=row.get("lieu_execution", ""),
                budget_estime=row.get("budget_estime", ""),
                url=row.get("url", ""),
                source=row.get("source", ""),
            )
            # Reconstruct domain matching from domaines_it column
            domaines_raw = row.get("domaines_it", "")
            if domaines_raw:
                domains = [d.strip() for d in domaines_raw.split(",")]
                # Map to pipeline domain names (lowercase)
                mapping = {
                    "AI": "ai", "Data": "data", "BI": "data",
                    "Dev": "dev", "Cloud": "cloud", "Cybersecurity": "dev",
                }
                c.matched_domains = list({mapping.get(d, d.lower()) for d in domains})
            # All IT consultations are at least COLD
            c.priority = Priority.COLD
            c.score_total = 5
            # Pre-fill descriptions from CSV if present (from filter_it.py)
            c.description_technique = (row.get("description_technique", "") or "").replace(" | ", "\n")
            c.description_fonctionnelle = (row.get("description_fonctionnelle", "") or "").replace(" | ", "\n")
            consultations.append(c)
    logger.info(f"Loaded {len(consultations)} IT consultations from {csv_path}")
    return consultations


def _parse_priority(value: str) -> Priority:
    v = (value or "").strip().upper()
    if v == "HOT":
        return Priority.HOT
    if v == "WARM":
        return Priority.WARM
    if v == "COLD":
        return Priority.COLD
    return Priority.EXCLUDED


def _parse_domains_from_qualification(value: str) -> List[str]:
    """Parse domain labels from the pipeline Qualification field (ex: 'DEV / DATA - Score 7')."""
    if not value:
        return []
    base = value.split("- Score", 1)[0].strip()
    if not base or base.lower().startswith("score"):
        return []
    parts = [p.strip().upper() for p in base.split("/") if p.strip()]
    mapping = {"AI": "ai", "DATA": "data", "DEV": "dev", "CLOUD": "cloud", "BI": "data"}
    return list({mapping.get(p, p.lower()) for p in parts})


def _parse_score_from_qualification(value: str) -> int:
    m = re.search(r"score\\s*(\\d+)", value or "", flags=re.IGNORECASE)
    if not m:
        return 0
    try:
        return int(m.group(1))
    except Exception:
        return 0


def _parse_requirements_list(value: str) -> List[str]:
    raw = (value or "").strip()
    if not raw or raw == "-":
        return []
    parts = [p.strip() for p in re.split(r"\\s*\\|\\s*", raw) if p.strip()]
    if len(parts) == 1:
        parts = [p.strip() for p in raw.splitlines() if p.strip()]
    return parts


def _load_pipeline_results_csv(csv_path: str) -> List[Consultation]:
    """
    Load consultations from `data/pipeline_results_*.csv`.

    Important: only keep qualified opportunities (Priorite != EXCLUDED).
    """
    consultations: List[Consultation] = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            priority = _parse_priority(row.get("Priorite", ""))
            if priority == Priority.EXCLUDED:
                continue

            ref = (row.get("ID") or "").strip()
            if not ref:
                continue

            qual = (row.get("Qualification") or "").strip()
            c = Consultation(
                id=ref,
                reference=ref,
                objet=(row.get("Titre") or "").strip(),
                acheteur=(row.get("Client") or "").strip(),
                date_limite=(row.get("Deadline") or "").strip(),
                budget_estime=(row.get("Budget_Estime") or "").strip(),
                url=(row.get("URL_Offre") or "").strip(),
            )
            c.priority = priority
            c.matched_domains = _parse_domains_from_qualification(qual)
            c.score_total = _parse_score_from_qualification(qual)
            c.domaines_activite = (row.get("Domaines_Activite") or "").strip()
            c.qualifications = (row.get("Qualifications") or "").strip()

            c.description_technique = (row.get("Description_Technique") or "").strip()
            c.description_fonctionnelle = (row.get("Description_Fonctionnelle") or "").strip()
            c.requirements = _parse_requirements_list(row.get("Requirements") or "")

            consultations.append(c)

    logger.info(f"Loaded {len(consultations)} qualified consultations from {csv_path}")
    return consultations


def _parse_deadline_to_date(value: str):
    """
    Best-effort parse for deadlines coming from the portal / pipeline exports.
    Returns a `datetime.date` or None.
    """
    from datetime import datetime

    if not value:
        return None
    s = str(value).strip()
    if not s or s in {"-", "N/A", "NA"}:
        return None

    # Common formats we see across the project
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:len(fmt)], fmt).date()
        except Exception:
            pass
    # Try ISO
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _ref_clean(ref: str) -> str:
    return re.sub(r"[^\w\-]", "_", (ref or ""))[:30]


def _has_both_docx_dossiers(output_dir: str, ref: str) -> bool:
    """
    True if both technical + administrative DOCX already exist for this ref.

    Note: PDF may still be missing (conversion can fail). Those refs are tracked
    separately so we can run PDF conversion without regenerating DOCX.
    Naming comes from `core/pipeline.py`:
      dossier_technique_{ref_clean}_YYYYMMDD.docx
      dossier_administratif_{ref_clean}_YYYYMMDD.docx
    """
    ref_clean = _ref_clean(ref)
    dossier_dir = Path(output_dir) / ref_clean
    if not dossier_dir.is_dir():
        return False

    def _has(pattern: str) -> bool:
        for p in dossier_dir.glob(pattern):
            if p.is_file() and not p.name.startswith("~$"):
                return True
        return False

    return _has(f"dossier_technique_{ref_clean}_*.docx") and _has(f"dossier_administratif_{ref_clean}_*.docx")


def _latest_pair_docx_paths(output_dir: str, ref: str) -> List[str]:
    """Latest (by mtime) technical + administratif DOCX for a reference, if any."""
    ref_clean = _ref_clean(ref)
    dossier_dir = Path(output_dir) / ref_clean
    if not dossier_dir.is_dir():
        return []
    out: List[str] = []
    for pattern in (f"dossier_technique_{ref_clean}_*.docx", f"dossier_administratif_{ref_clean}_*.docx"):
        matches = [p for p in dossier_dir.glob(pattern) if p.is_file() and not p.name.startswith("~$")]
        if not matches:
            continue
        latest = max(matches, key=lambda p: p.stat().st_mtime)
        out.append(str(latest))
    return out


def _detect_csv_kind(csv_path: str) -> str:
    """Return 'pipeline_results' or 'filter_it' based on CSV headers."""
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            header = f.readline()
        if "Priorite" in header and "Qualification" in header and "URL_Offre" in header:
            return "pipeline_results"
    except Exception:
        pass
    return "filter_it"


# ── RAG enrichment ──────────────────────────────────────────────────────────
def _enrich_rag(consultations: List[Consultation], cache: Dict[str, dict],
                rate_limit: float = 6.0) -> Dict[str, int]:
    """Enrich consultations via RAG. Updates in-place + saves cache incrementally."""
    from core.rag_engine import RAGEngine, RAGConfig

    config = RAGConfig.from_env()
    rag = RAGEngine(config)

    stats = {"enriched": 0, "cached": 0, "failed": 0}
    total = len(consultations)

    for i, c in enumerate(consultations, 1):
        ref = c.reference or c.id
        # Skip if already cached with good content
        if ref in cache and len(cache[ref].get("description_technique", "")) > 200:
            _apply_cache(c, cache[ref])
            stats["cached"] += 1
            logger.info(f"  [{i}/{total}] {ref} — cache ✅")
            continue

        logger.info(f"  [{i}/{total}] {ref} — enrichissement RAG…")
        try:
            # Build minimal CPS context from available fields
            if not c.contenu_cps:
                parts = [f"Objet: {c.objet}"]
                if c.acheteur:
                    parts.append(f"Acheteur: {c.acheteur}")
                if c.budget_estime and c.budget_estime != "-":
                    parts.append(f"Budget: {c.budget_estime}")
                if c.categorie:
                    parts.append(f"Catégorie: {c.categorie}")
                if c.nature_prestation:
                    parts.append(f"Nature: {c.nature_prestation}")
                c.contenu_cps = "\n".join(parts)
                c.cps_source = "csv"

            rag.enrich_consultation(c)
            stats["enriched"] += 1
            logger.info(f"    ✅ desc={len(c.description_technique)}ch, reqs={len(c.requirements)}")

            # Save to cache immediately
            cache[ref] = {
                "id": ref,
                "objet": c.objet,
                "description_technique": c.description_technique,
                "description_fonctionnelle": c.description_fonctionnelle,
                "requirements": c.requirements,
                "forces": c.strengths,
                "risques": c.risks,
                "recommandations": c.recommendations,
            }
            _save_cache(cache)

            # Rate limit
            if i < total:
                time.sleep(rate_limit)

        except Exception as e:
            logger.warning(f"    ❌ RAG failed: {e}")
            stats["failed"] += 1

    return stats


def _apply_cache(c: Consultation, data: dict):
    """Apply cached RAG data to consultation."""
    if data.get("description_technique"):
        c.description_technique = data["description_technique"]
    if data.get("description_fonctionnelle"):
        c.description_fonctionnelle = data["description_fonctionnelle"]
    if data.get("requirements"):
        c.requirements = data["requirements"]
    if data.get("forces"):
        c.strengths = data["forces"]
    if data.get("risques"):
        c.risks = data["risques"]
    if data.get("recommandations"):
        c.recommendations = data["recommandations"]


# ── NLP Fallback ────────────────────────────────────────────────────────────
def _fallback_nlp(consultations: List[Consultation]) -> int:
    """Fill missing descriptions/recommendations with NLP templates."""
    analyzer = NLPAnalyzer.__new__(NLPAnalyzer)
    analyzer._nlp = None
    filled = 0
    for c in consultations:
        needs_fill = (
            len(c.description_technique or "") < 100
            or len(c.description_fonctionnelle or "") < 100
            or not c.strengths
        )
        if needs_fill:
            try:
                analyzer.generate_descriptions(c)
                analyzer.generate_recommendations(c)
                filled += 1
            except Exception as e:
                logger.debug(f"NLP fallback error for {c.reference}: {e}")
    logger.info(f"NLP fallback: {filled} consultations complétées")
    return filled


# ── DOCX Generation ─────────────────────────────────────────────────────────
def _generate_docx(consultations: List[Consultation],
                   output_dir: str = "dossiers_generes") -> List[str]:
    """Generate DOCX dossiers for all consultations."""
    generator = DossierGenerator(output_dir=output_dir)
    all_paths = []
    for i, c in enumerate(consultations, 1):
        logger.info(f"  [{i}/{len(consultations)}] DOCX: {c.reference}")
        try:
            paths = generator.generate(c)
            all_paths.extend(paths)
            for p in paths:
                logger.info(f"    📄 {Path(p).name}")
        except Exception as e:
            logger.error(f"    ❌ Erreur DOCX: {e}")
    return all_paths


# ── PDF Conversion ──────────────────────────────────────────────────────────
def _libreoffice_convert_one(docx_path: str) -> Optional[str]:
    """Convert a single DOCX to PDF using LibreOffice/soffice (cross-platform)."""
    import shutil
    import subprocess

    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        return None
    p = Path(docx_path).resolve()
    if not p.is_file():
        return None
    out_dir = str(p.parent)
    try:
        subprocess.run(
            [exe, "--headless", "--convert-to", "pdf", "--outdir", out_dir, str(p)],
            capture_output=True,
            timeout=120,
            check=True,
        )
    except Exception as e:
        logger.debug("LibreOffice PDF failed for %s: %s", p.name, e)
        return None
    pdf = p.with_suffix(".pdf")
    return str(pdf) if pdf.is_file() else None


def _convert_to_pdf(docx_paths: List[str]) -> List[str]:
    """Convert DOCX files to PDF.

    - Windows: tries docx2pdf (Word COM) first, then LibreOffice if installed.
    - Linux/Docker: LibreOffice headless.
    """
    import platform

    is_win = platform.system() == "Windows"
    docx2pdf_convert = None
    if is_win:
        try:
            from docx2pdf import convert as docx2pdf_convert  # type: ignore
        except ImportError:
            docx2pdf_convert = None
            logger.warning("docx2pdf non installé — pip install docx2pdf (sinon LibreOffice uniquement)")

    pdf_paths: List[str] = []
    for docx_path in docx_paths:
        p = Path(docx_path)
        if not p.is_file() or p.suffix.lower() != ".docx" or p.name.startswith("~$"):
            continue
        pdf_path = p.with_suffix(".pdf")
        if pdf_path.is_file():
            pdf_paths.append(str(pdf_path))
            continue

        converted = False
        if is_win and docx2pdf_convert is not None:
            try:
                docx2pdf_convert(str(p), str(pdf_path))
                if pdf_path.is_file():
                    pdf_paths.append(str(pdf_path))
                    logger.info(f"    📕 {pdf_path.name} (docx2pdf)")
                    converted = True
            except Exception as e:
                logger.warning(f"    ⚠️ docx2pdf failed for {p.name}: {e}")

        if not converted:
            lo = _libreoffice_convert_one(str(p))
            if lo:
                pdf_paths.append(lo)
                logger.info(f"    📕 {Path(lo).name} (LibreOffice)")
            else:
                logger.warning(f"    ⚠️ PDF conversion failed: {p.name}")

    return pdf_paths


# ── Main orchestrator ───────────────────────────────────────────────────────
def generate_dossiers_hybrid(
    csv_path: Optional[str] = None,
    output_dir: str = "dossiers_generes",
    use_rag: bool = True,
    convert_pdf: bool = True,
    rate_limit: float = 6.0,
    only_references: Optional[list] = None,
    min_priority: str = "WARM",
    include_liked: bool = True,
    liked_ids: Optional[list] = None,
    only_active: bool = True,
    max_consultations: int = 120,
    skip_existing: bool = True,
) -> dict:
    """
    Main entry point — returns stats dict (API-compatible).

    Parameters:
        csv_path:    Path to filtered IT CSV (auto-detect if None)
        output_dir:  Directory for generated DOCX/PDF
        use_rag:     Enable RAG enrichment via Groq
        convert_pdf: Convert DOCX to PDF after generation
        rate_limit:  Seconds between RAG API calls
    """
    print("=" * 65)
    print("  GÉNÉRATION DOSSIERS HYBRIDE — RAG + Pipeline")
    print("=" * 65)

    # ── 1. Find CSV ──────────────────────────────────────────────────────
    if not csv_path:
        data_dir = PROJECT_ROOT / "data"
        # Prefer pipeline_results (already scored; includes Priorite) so we can skip EXCLUDED.
        candidates = sorted(data_dir.glob("pipeline_results_*.csv"), reverse=True)
        if not candidates:
            # Legacy fallback: filtered IT CSV (no Priorite column).
            candidates = sorted(data_dir.glob("appels_offres_*_IT.csv"), reverse=True)
        if not candidates:
            raise FileNotFoundError("Aucun CSV trouve dans data/")
        csv_path = str(candidates[0])

    print(f"\n📂 CSV: {csv_path}")

    # ── 2. Load consultations ────────────────────────────────────────────
    kind = _detect_csv_kind(csv_path)
    consultations = _load_pipeline_results_csv(csv_path) if kind == "pipeline_results" else _load_it_csv(csv_path)
    if not consultations:
        return {"error": "Aucune consultation chargee", "total": 0}
    print(f"   {len(consultations)} consultations {'qualifiees' if kind == 'pipeline_results' else 'IT'} chargees")

    # If explicitly requested, keep only matching references/ids (prevents mismatched dossiers).
    if only_references:
        wanted = set(str(x).strip() for x in (only_references or []) if str(x).strip())
        if wanted:
            consultations = [
                c for c in consultations
                if str(getattr(c, "reference", "") or getattr(c, "id", "") or "").strip() in wanted
            ]
            print(f"   Filtre references: {len(consultations)} selectionnees")

    # ── 2.1 Select which consultations to generate dossiers for ──────────
    liked_set = set(str(x) for x in (liked_ids or []) if str(x).strip())
    prio = str(min_priority or "WARM").upper()
    prio_order = {Priority.HOT: 0, Priority.WARM: 1, Priority.COLD: 2, Priority.EXCLUDED: 9}
    min_p = Priority.WARM if prio == "WARM" else (Priority.HOT if prio == "HOT" else Priority.COLD)

    from datetime import date
    today = date.today()

    selected = []
    skipped_existing_refs: List[str] = []
    skipped_deadline = 0
    skipped_existing = 0
    for c in consultations:
        ref = str(c.reference or c.id or "").strip()
        if not ref:
            continue

        # Deadline filter: keep only active opportunities.
        if only_active:
            d = _parse_deadline_to_date(getattr(c, "date_limite", "") or "")
            if d and d < today:
                skipped_deadline += 1
                continue

        # Priority filter: generate for HOT/WARM by default; also allow liked items.
        if prio_order.get(getattr(c, "priority", Priority.COLD), 9) > prio_order.get(min_p, 9):
            if not (include_liked and ref in liked_set):
                continue

        if skip_existing and _has_both_docx_dossiers(output_dir, ref):
            skipped_existing_refs.append(ref)
            skipped_existing += 1
            continue

        selected.append(c)

    # Sort: HOT first, then score desc
    selected.sort(key=lambda x: (prio_order.get(getattr(x, "priority", Priority.COLD), 9), -(getattr(x, "score_total", 0) or 0)))
    if max_consultations and len(selected) > int(max_consultations):
        selected = selected[: int(max_consultations)]

    consultations = selected
    print(f"   Selection: {len(consultations)} (deadline expired: {skipped_deadline}, already generated: {skipped_existing})")

    # ── 3. RAG enrichment ────────────────────────────────────────────────
    cache = _load_cache()
    rag_stats = {"enriched": 0, "cached": 0, "failed": 0}

    if use_rag:
        print(f"\n🤖 Enrichissement RAG (Groq)…")
        rag_stats = _enrich_rag(consultations, cache, rate_limit=rate_limit)
        print(f"   RAG: {rag_stats['enriched']} enrichis, "
              f"{rag_stats['cached']} en cache, {rag_stats['failed']} échecs")

    # ── 4. NLP fallback for any gaps ─────────────────────────────────────
    print(f"\n📝 Fallback NLP templates…")
    nlp_filled = _fallback_nlp(consultations)

    # ── 5. Generate DOCX ────────────────────────────────────────────────
    print(f"\n📄 Génération DOCX ({len(consultations)} consultations)…")
    docx_paths = _generate_docx(consultations, output_dir)
    print(f"   {len(docx_paths)} fichiers DOCX générés")

    # ── 6. Convert to PDF (nouveaux DOCX + dossiers existants sans PDF) ───
    pdf_paths: List[str] = []
    docx_to_convert: List[str] = []
    if convert_pdf:
        docx_for_pdf: List[str] = []
        seen_paths: Set[str] = set()
        for p in docx_paths:
            ap = str(Path(p).resolve())
            if ap not in seen_paths:
                seen_paths.add(ap)
                docx_for_pdf.append(ap)
        for ref in skipped_existing_refs:
            for p in _latest_pair_docx_paths(output_dir, ref):
                ap = str(Path(p).resolve())
                if ap not in seen_paths:
                    seen_paths.add(ap)
                    docx_for_pdf.append(ap)
        docx_to_convert = [
            p for p in docx_for_pdf
            if Path(p).suffix.lower() == ".docx" and not Path(p).with_suffix(".pdf").is_file()
        ]
        if docx_to_convert:
            print(f"\n📕 Conversion PDF ({len(docx_to_convert)} DOCX sans PDF associé)…")
            pdf_paths = _convert_to_pdf(docx_to_convert)
            print(f"   {len(pdf_paths)} fichiers PDF générés")

    # ── 7. Summary ──────────────────────────────────────────────────────
    total_size_kb = sum(
        Path(p).stat().st_size / 1024
        for p in docx_paths + pdf_paths
        if Path(p).exists()
    )

    result = {
        "status": "completed",
        "csv_source": csv_path,
        "total_consultations": len(consultations),
        "rag": rag_stats,
        "nlp_fallback": nlp_filled,
        "docx_generated": len(docx_paths),
        "pdf_generated": len(pdf_paths),
        "pdf_docx_attempted": len(docx_to_convert),
        "total_files": len(docx_paths) + len(pdf_paths),
        "total_size_mb": round(total_size_kb / 1024, 2),
        "output_dir": output_dir,
        "generated_at": datetime.now().isoformat(),
    }

    print(f"\n{'=' * 65}")
    print(f"  RÉSUMÉ")
    print(f"    Consultations IT  : {len(consultations)}")
    print(f"    RAG enrichment    : {rag_stats['enriched']} (cache: {rag_stats['cached']})")
    print(f"    NLP fallback      : {nlp_filled}")
    print(f"    DOCX générés      : {len(docx_paths)}")
    print(f"    PDF générés       : {len(pdf_paths)}")
    print(f"    Taille totale     : {total_size_kb/1024:.1f} MB")
    print(f"    Répertoire        : {output_dir}/")
    print(f"{'=' * 65}")

    return result


# ── CLI ─────────────────────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(description="Génération hybride de dossiers (RAG + Pipeline)")
    parser.add_argument("csv", nargs="?", default=None, help="Chemin CSV filtré IT")
    parser.add_argument("--no-rag", action="store_true", help="Désactiver RAG (templates seuls)")
    parser.add_argument("--no-pdf", action="store_true", help="Ne pas convertir en PDF")
    parser.add_argument("--pdf-only", action="store_true", help="Convertir seulement les DOCX existants en PDF")
    parser.add_argument("--output", default="dossiers_generes", help="Répertoire de sortie")
    parser.add_argument("--rate-limit", type=float, default=6.0, help="Délai entre appels RAG (secondes)")
    args = parser.parse_args()

    if args.pdf_only:
        # Convert all existing DOCX to PDF
        out_dir = Path(args.output)
        docx_files = list(out_dir.rglob("*.docx"))
        # Only convert those without a matching PDF
        to_convert = [
            str(d) for d in docx_files
            if not d.with_suffix(".pdf").exists()
        ]
        print(f"📕 Converting {len(to_convert)} DOCX to PDF…")
        pdfs = _convert_to_pdf(to_convert)
        print(f"✅ {len(pdfs)} PDF créés")
        return

    result = generate_dossiers_hybrid(
        csv_path=args.csv,
        output_dir=args.output,
        use_rag=not args.no_rag,
        convert_pdf=not args.no_pdf,
        rate_limit=args.rate_limit,
    )
    print(f"\nJSON: {json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
