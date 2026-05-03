#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper Profond - Portail Principal marchespublics.gov.ma
Utilise Playwright pour le portail PRADO (recherche avancée)
+ requests pour la section BDC
Recherche multi-mots-clés : AI, Data, Dev, Cloud, BI, ERP, etc.
"""

import asyncio
import csv
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from bs4 import BeautifulSoup

# Fix Windows console encoding via env (no wrapper to avoid buffering)
os.environ['PYTHONIOENCODING'] = 'utf-8'
import functools
print = functools.partial(print, flush=True)
import requests
from playwright.async_api import async_playwright

BASE = "https://www.marchespublics.gov.ma"

# === MOTS-CLÉS CIBLÉS pour scraping profond ===
SEARCH_KEYWORDS = [
    "logiciel", "informatique", "système d'information",
    "développement web", "application mobile", "site web",
    "plateforme numérique", "ERP", "CRM",
    "base de données", "data", "business intelligence",
    "intelligence artificielle", "automatisation",
    "cloud", "SaaS", "virtualisation", "datacenter",
    "cybersécurité", "sécurité informatique",
    "numérique", "digital", "transformation numérique",
    "maintenance informatique", "réseau informatique",
    "intégration", "migration", "progiciel",
]


class DeepScraper:
    def __init__(self, skip_enrich: bool = False, concurrency: int = 5):
        self.results = {}  # id -> consultation dict (dédoublonnage)
        self.skip_enrich = skip_enrich  # Skip enrichment for faster scraping
        self.concurrency = concurrency  # Parallel browser tabs for enrichment
        # Exclude hardware/equipment tenders early (disable via SCRAPE_EXCLUDE_EQUIPMENT=0).
        self.exclude_equipment = os.environ.get("SCRAPE_EXCLUDE_EQUIPMENT", "1").strip() != "0"
        self.skipped_equipment = 0

        # Require an equipment signal + purchase/installation signal (conservative).
        self._equipment_kw = [
            "equipement", "equipements", "materiel",
            "serveur", "serveurs", "switch", "routeur", "routeurs",
            "ordinateur", "ordinateurs", "poste de travail", "postes de travail",
            "imprimante", "imprimantes", "copieur", "scanner",
            "onduleur", "ups", "baie", "rack",
            "cablage", "wifi", "reseau",
            "camera", "videosurveillance",
            "telephonie", "ipbx", "voip",
            "fibre", "fibre optique", "salle serveur",
        ]
        self._equip_action_kw = [
            "acquisition", "achat", "fourniture", "fournitures", "livraison",
            "installation", "mise en place", "deploiement", "montage", "mise en service",
        ]
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def _is_equipment_related(self, data: dict, extra_text: str = "") -> bool:
        if not self.exclude_equipment:
            return False

        base = " ".join([
            str(data.get("objet") or ""),
            str(data.get("categorie") or ""),
            str(data.get("nature_prestation") or ""),
            str(data.get("articles") or ""),
            str(extra_text or ""),
        ])
        text = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii").lower()
        if not text:
            return False

        has_equipment = any(k in text for k in self._equipment_kw)
        if not has_equipment:
            return False

        has_action = any(k in text for k in self._equip_action_kw)
        cat = unicodedata.normalize("NFKD", str(data.get("categorie") or "")).encode("ascii", "ignore").decode("ascii").lower()
        cat_supplies = any(k in cat for k in ["fourniture", "fournitures", "equipement", "equipements", "materiel"])

        return bool(has_action or cat_supplies)

    # ===========================================
    # PARTIE 1: Portail Principal (Playwright)
    # ===========================================

    async def scrape_main_portal(self):
        """Scrape le portail principal via recherche par mots-cles"""
        print("\n" + "=" * 80)
        print("SCRAPING PORTAIL PRINCIPAL (Playwright + PRADO)")
        print("=" * 80)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            for keyword in SEARCH_KEYWORDS:
                # New context + page per keyword to avoid PRADO page crash
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()
                try:
                    count = await self._search_keyword(page, keyword)
                    status = f"+{count}" if count > 0 else "0"
                    print(f"  [{status:>4}] '{keyword}' (total: {len(self.results)})")
                except Exception as e:
                    print(f"  [ERR] '{keyword}': {str(e)[:50]}")
                finally:
                    await page.close()
                    await context.close()
                await asyncio.sleep(1)

            await browser.close()

        print(f"\n  >> Portail principal: {len(self.results)} consultations uniques")

    async def _search_keyword(self, page, keyword):
        """Lance une recherche par mot-cle sur le portail principal"""

        url = f"{BASE}/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)

        # Remplir le champ mot-cle via fill() qui declenche les events input/change
        kw_selector = '#ctl0_CONTENU_PAGE_AdvancedSearch_keywordSearch'
        try:
            await page.fill(kw_selector, keyword, timeout=5000)
        except:
            # Fallback JS
            await page.evaluate("""(keyword) => {
                const kw = document.getElementById('ctl0_CONTENU_PAGE_AdvancedSearch_keywordSearch');
                if (kw) { kw.value = keyword; kw.dispatchEvent(new Event('change')); }
            }""", keyword)

        await asyncio.sleep(0.5)

        # Cliquer "Lancer la recherche"
        search_btn = page.locator('#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche')
        try:
            await search_btn.click(timeout=10000)
        except:
            # Fallback: submit via JS
            await page.evaluate("""() => {
                const btn = document.getElementById('ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche');
                if (btn) btn.click();
            }""")

        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state('networkidle', timeout=15000)
        except:
            pass

        # Essayer d'afficher 100 resultats par page
        try:
            select_100 = page.locator('select:has(option[value="100"])')
            if await select_100.count() > 0:
                await select_100.first.select_option('100')
                await asyncio.sleep(3)
                try:
                    await page.wait_for_load_state('networkidle', timeout=10000)
                except:
                    pass
        except:
            pass

        # Extraire les resultats
        html = await page.content()
        new_count = self._parse_main_results(html, keyword)

        # Sauvegarder le 1er HTML pour debug
        if keyword == SEARCH_KEYWORDS[0]:
            with open('data/portal_main_search.html', 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"  [DEBUG] HTML sauve ({len(html)} chars), parsed {new_count} resultats")

        # Pagination (clic sur pages suivantes)
        page_num = 1
        # No hard limit by default; stop when there's no next page or nothing new is added.
        # Optional safety cap via env SCRAPE_MAX_PAGES (set to an int) if you ever need it.
        max_pages_env = os.environ.get("SCRAPE_MAX_PAGES", "").strip()
        max_pages = int(max_pages_env) if max_pages_env.isdigit() else None
        while True:
            if max_pages is not None and page_num >= max_pages:
                break
            # Chercher lien page suivante (format PRADO)
            next_link = await page.query_selector('a[title="Page suivante"], a.page-link:has-text(">")')
            if not next_link:
                # Essayer pagination numerique directe
                next_page = await page.query_selector(f'a.page-link:has-text("{page_num + 1}")')
                if not next_page:
                    break
                next_link = next_page

            try:
                await next_link.click()
                await asyncio.sleep(2)
                await page.wait_for_load_state('networkidle', timeout=10000)
                html = await page.content()
                added = self._parse_main_results(html, keyword)
                if added == 0:
                    break
                new_count += added
                page_num += 1
            except:
                break

        return new_count

    def _parse_main_results(self, html, keyword):
        """Parse les resultats du portail principal"""
        soup = BeautifulSoup(html, 'html.parser')
        count = 0

        # Log le nombre de resultats affiche
        nb_el = soup.find('h3', string=re.compile(r'Nombre de'))
        if nb_el:
            nb_text = nb_el.get_text(strip=True)
            # Extract number after ":"
            m = re.search(r':(\d+)', nb_text)
            if m:
                total_shown = int(m.group(1))
                if total_shown == 0:
                    return 0

        # Chercher les lignes de resultats (table)
        # Pattern 1: Table de resultats - liens EntrepriseDetailConsultation
        rows = soup.select('table tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 2:
                link = row.find('a', href=re.compile(r'EntrepriseDetailConsultation|DetailConsultation'))
                if link:
                    href = link.get('href', '')
                    consultation_id = self._extract_id(href)
                    if consultation_id and consultation_id not in self.results:
                        data = self._extract_row_data(cells, href, keyword)
                        if data:
                            if self._is_equipment_related(data):
                                self.skipped_equipment += 1
                                continue
                            self.results[consultation_id] = data
                            count += 1

        # Pattern 2: Tous les liens directs EntrepriseDetailConsultation
        all_links = soup.find_all('a', href=re.compile(r'EntrepriseDetailConsultation|DetailConsultation'))
        for link in all_links:
            href = link.get('href', '')
            consultation_id = self._extract_id(href)
            if consultation_id and consultation_id not in self.results:
                text = link.get_text(strip=True)
                if text and len(text) > 5:
                    data = {
                        'id': consultation_id,
                        'reference': '',
                        'objet': text[:200],
                        'acheteur': '',
                        'categorie': '',
                        'nature_prestation': '',
                        'date_publication': '',
                        'date_limite': '',
                        'lieu_execution': '',
                        'budget_estime': '',
                        'nb_articles': '',
                        'articles': '',
                        'fichiers_joints': '',
                        'email_contact': '',
                        'url': BASE + href if href.startswith('/') else href,
                        'source': f'portail_principal:{keyword}',
                    }
                    if self._is_equipment_related(data):
                        self.skipped_equipment += 1
                        continue
                    self.results[consultation_id] = data
                    count += 1

        return count

    def _extract_id(self, href):
        """Extraire un ID unique depuis l'URL"""
        # Pattern 1: /show/12345 (BDC)
        m = re.search(r'/show/(\d+)', href)
        if m:
            return m.group(1)
        # Pattern 2: refConsultation=12345 (portail principal)
        m = re.search(r'refConsultation=(\d+)', href)
        if m:
            return 'main_' + m.group(1)
        # Pattern 3: id=12345
        m = re.search(r'[?&]id=(\d+)', href)
        if m:
            return m.group(1)
        # Pattern 4: consultation/12345
        m = re.search(r'consultation/(\d+)', href)
        if m:
            return m.group(1)
        return None

    def _extract_row_data(self, cells, href, keyword):
        """Extraire les donnees d'une ligne du portail principal PRADO"""
        # Structure table PRADO:
        # Cell 0: vide/icone
        # Cell 1: Procedure | Categorie | Date publication
        # Cell 2: Reference | Objet
        # Cell 3: Lieu | Lots
        # Cell 4: Date limite
        # Cell 5: Liens detail
        # Cell 6: Actions

        def cell_text(idx):
            if idx < len(cells):
                return cells[idx].get_text(' ', strip=True)
            return ''

        c1 = cell_text(1)
        c2 = cell_text(2)
        c3 = cell_text(3)
        c4 = cell_text(4)

        # Categorie from cell 1
        categorie = ''
        for cat in ['Services', 'Fournitures', 'Travaux']:
            if cat in c1:
                categorie = cat
                break

        # Dates from cell 1 (date publication)
        dates_c1 = re.findall(r'(\d{2}/\d{2}/\d{4})', c1)
        date_pub = dates_c1[0] if dates_c1 else ''

        # Reference from cell 2 (first part before Objet)
        reference = ''
        objet = ''
        if 'Objet' in c2:
            parts = c2.split('Objet')
            ref_part = parts[0].strip()
            # Reference is usually first line
            ref_lines = [l.strip() for l in ref_part.split(' ') if l.strip() and l.strip() != '-' and l.strip() != '...']
            if ref_lines:
                reference = ref_lines[0][:50]
            # Objet after 'Objet' label
            obj_part = parts[-1].replace(':', '').strip()
            objet = obj_part[:300]
        else:
            objet = c2[:300]

        # Lieu from cell 3
        lieu = ''
        if c3:
            # Remove ... and - prefixes
            lieu_clean = c3.replace('...', '').replace(' - ', ', ').strip()
            lieu = lieu_clean[:100]

        # Date limite from cell 4
        dates_c4 = re.findall(r'(\d{2}/\d{2}/\d{4})', c4)
        date_limite = dates_c4[0] if dates_c4 else ''

        # Procedure from cell 1
        procedure = ''
        for proc in ['AOO', 'AOR', 'AOI', 'Marche negocie', 'Appel d']:
            if proc in c1:
                procedure = c1.split(proc)[0].strip() + proc if proc != 'Appel d' else ''
                break

        full_url = BASE + '/' + href.lstrip('/') if href.startswith('?') else (BASE + href if href.startswith('/') else href)

        return {
            'id': self._extract_id(href) or '',
            'reference': reference,
            'objet': objet,
            'acheteur': '',
            'categorie': categorie,
            'nature_prestation': procedure,
            'date_publication': date_pub,
            'date_limite': date_limite,
            'lieu_execution': lieu,
            'budget_estime': '',
            'nb_articles': '',
            'articles': '',
            'fichiers_joints': '',
            'email_contact': '',
            'url': full_url,
            'source': f'portail_principal:{keyword}',
        }

    def _extract_item_data(self, item, href, keyword):
        """Extraire les données d'un item card/div"""
        text = item.get_text(' ', strip=True)
        title = item.find(['h3', 'h4', 'h5', 'strong', 'b'])
        title_text = title.get_text(strip=True) if title else text[:100]

        # Dates
        dates = re.findall(r'\d{2}/\d{2}/\d{4}', text)

        return {
            'id': self._extract_id(href) or '',
            'reference': '',
            'objet': title_text[:200],
            'acheteur': '',
            'categorie': '',
            'nature_prestation': '',
            'date_publication': dates[0] if dates else '',
            'date_limite': dates[1] if len(dates) > 1 else '',
            'lieu_execution': '',
            'budget_estime': '',
            'nb_articles': '',
            'articles': '',
            'fichiers_joints': '',
            'email_contact': '',
            'url': BASE + href if href.startswith('/') else href,
            'source': f'portail_principal:{keyword}',
        }

    # ===========================================
    # PARTIE 2: Section BDC (requests, élargi)
    # ===========================================

    def scrape_bdc_all_pages(self):
        """Scrape TOUTES les pages BDC (avis d'achat) - methode prouvee"""
        print("\n" + "=" * 80)
        print("[SCAN] SCRAPING SECTION BDC (requests + BeautifulSoup)")
        print("=" * 80)

        list_url = f"{BASE}/bdc/entreprise/consultation/"

        # Phase 1: Collecter tous les liens
        print("  [1/2] Collecte des liens...")
        all_items = []
        page_num = 1
        total_pages = 1

        while page_num <= total_pages:
            url = f"{list_url}?page={page_num}" if page_num > 1 else list_url
            try:
                resp = self.session.get(url, timeout=15)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, 'html.parser')

                # Determine total pages from first page
                if page_num == 1:
                    total_pages = self._get_bdc_total_pages(soup)
                    print(f"        {total_pages} pages trouvees")

                # Extract links
                seen_ids = set()
                for link in soup.find_all('a', href=re.compile(r'/bdc/entreprise/consultation/show/\d+')):
                    href = link.get('href', '')
                    m = re.search(r'/show/(\d+)', href)
                    if m:
                        cid = m.group(1)
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            all_items.append({'id': cid, 'url': f"{BASE}{href}"})

                if page_num % 10 == 0 or page_num == 1:
                    print(f"        Page {page_num}/{total_pages}: {len(all_items)} liens")

                page_num += 1
                time.sleep(0.3)
            except Exception as e:
                print(f"  [ERR] Page {page_num}: {e}")
                break

        # Deduplicate & filter already-scraped
        unique = []
        for item in all_items:
            if item['id'] not in self.results:
                unique.append(item)
        print(f"        {len(all_items)} liens, {len(unique)} nouveaux")

        # Phase 2: Scraper les details
        print(f"  [2/2] Scraping details ({len(unique)} consultations)...")
        total_new = 0
        errors = 0
        start = time.time()

        for idx, item in enumerate(unique, 1):
            detail = self._scrape_bdc_detail(item['id'])
            if detail:
                self.results[item['id']] = detail
                total_new += 1
            else:
                errors += 1

            if idx % 50 == 0 or idx == 1:
                elapsed = time.time() - start
                rate = idx / elapsed if elapsed > 0 else 0
                eta = (len(unique) - idx) / rate if rate > 0 else 0
                print(f"        {idx}/{len(unique)} ({idx*100//len(unique)}%) | {rate:.1f}/s | ETA:{eta:.0f}s | +{total_new} ok, {errors} err")

            time.sleep(0.3)

        print(f"\n[STATS] BDC: {total_new} nouvelles consultations (total: {len(self.results)})")

    def _get_bdc_total_pages(self, soup):
        """Déterminer le nombre total de pages BDC"""
        pag = soup.select('a.page-link, a[href*="page="]')
        max_page = 1
        for p in pag:
            href = p.get('href', '')
            m = re.search(r'page=(\d+)', href)
            if m:
                max_page = max(max_page, int(m.group(1)))
        return max_page

    def _scrape_bdc_detail(self, cid):
        """Scrape une page detail BDC (logique prouvée de scrape_all_real_v2)"""
        url = f"{BASE}/bdc/entreprise/consultation/show/{cid}"
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, 'html.parser')
            text_full = soup.get_text(separator='\n')

            # Skip cancelled notices (Annule/Annulation).
            # They often show a badge "Annule" and an "Informations liees a l'annulation" section.
            if re.search(r"\bannul", text_full, re.IGNORECASE) and (
                re.search(r"\bdate d'?annulation\b", text_full, re.IGNORECASE)
                or re.search(r"\binformations?\s+li[ée]es?\s+[àa]\s+l'?annulation\b", text_full, re.IGNORECASE)
                or re.search(r"\bavis d'?annulation\b", text_full, re.IGNORECASE)
            ):
                return None

            data = {
                'id': cid,
                'reference': '',
                'objet': '',
                'acheteur': '',
                'categorie': '',
                'nature_prestation': '',
                'date_publication': '',
                'date_limite': '',
                'lieu_execution': '',
                'budget_estime': '',
                'nb_articles': '',
                'articles': '',
                'fichiers_joints': '',
                'email_contact': '',
                'url': url,
                'source': 'bdc',
            }

            # Reference: h4.mb-0
            h4 = soup.find('h4', class_='mb-0')
            if h4:
                data['reference'] = h4.get_text(strip=True).lstrip('#').strip()

            # Toutes les div.row avec separateur ||
            rows = soup.find_all('div', class_='row')
            objet_found = False

            for row in rows:
                row_text = row.get_text(separator='||', strip=True)

                # Acheteur
                if 'Acheteur' in row_text:
                    parts = row_text.split('||')
                    for i, p in enumerate(parts):
                        if 'Acheteur' in p and i + 1 < len(parts):
                            val = parts[i + 1].strip()
                            if val and val.lower() not in ['public', '']:
                                data['acheteur'] = val
                            elif i + 2 < len(parts):
                                val2 = parts[i + 2].strip() if 'Date' not in parts[i + 2] else ''
                                if val2:
                                    data['acheteur'] = val2
                    if not data['acheteur']:
                        match = re.search(r'Acheteur\s*public\|\|(.*?)(?:\|\|Date|\|\|$|$)', row_text)
                        if match and match.group(1).strip():
                            data['acheteur'] = match.group(1).strip()

                # Dates
                if 'Date mise en ligne' in row_text:
                    match = re.search(r'(\d{2}/\d{2}/\d{4})', row_text)
                    if match:
                        data['date_publication'] = match.group(1)
                    dates = re.findall(r'(\d{2}/\d{2}/\d{4})', row_text)
                    if len(dates) >= 2:
                        data['date_limite'] = dates[1]
                    elif len(dates) == 1 and 'Date limit' in row_text:
                        data['date_limite'] = dates[0]

                # Lieu
                if 'Lieu' in row_text and 'cution' in row_text:
                    parts = row_text.split('||')
                    for i, p in enumerate(parts):
                        if 'Lieu' in p and i + 1 < len(parts):
                            val = parts[i + 1].strip()
                            if val and 'Cat' not in val:
                                data['lieu_execution'] = val

                # Categorie
                if 'Cat' in row_text and 'gorie' in row_text:
                    parts = row_text.split('||')
                    for i, p in enumerate(parts):
                        if 'Cat' in p and i + 1 < len(parts):
                            val = parts[i + 1].strip()
                            if val and 'Nature' not in val:
                                data['categorie'] = val

                # Nature prestation
                if 'Nature' in row_text and 'prestation' in row_text.lower():
                    parts = row_text.split('||')
                    for i, p in enumerate(parts):
                        if 'Nature' in p and i + 1 < len(parts):
                            val = parts[i + 1].strip()
                            if val:
                                data['nature_prestation'] = val

                # Objet: premiere div.row sans label connu
                if not objet_found:
                    has_label = any(kw in row_text for kw in [
                        'Acheteur', 'Date', 'Lieu', 'Cat', 'Nature', 'Unit',
                        'Quantit', 'TVA', 'Garantie', '.zip', '.pdf', '.rar',
                        'BC ', 'Tout afficher'
                    ])
                    clean = row.get_text(strip=True)
                    if not has_label and len(clean) > 15:
                        data['objet'] = clean[:500]
                        objet_found = True

            # Dates fallback
            if not data['date_publication'] or not data['date_limite']:
                dates = re.findall(r'(\d{2}/\d{2}/\d{4})\s*\d{2}:\d{2}', text_full)
                if dates:
                    data.setdefault('date_publication', dates[0])
                if len(dates) >= 2:
                    data.setdefault('date_limite', dates[1])

            # Articles (accordion)
            articles = []
            for acc in soup.find_all('div', class_='accordion-item'):
                h2 = acc.find('h2', class_='accordion-header')
                if h2:
                    title = h2.get_text(strip=True)
                    qty = ''
                    acc_text = acc.get_text(separator='||')
                    qty_match = re.search(r'Quantit[^|]*\|\|(\d+)', acc_text)
                    if qty_match:
                        qty = qty_match.group(1)
                    articles.append(f"{title} [qty:{qty}]" if qty else title)
            if articles:
                data['articles'] = ' | '.join(articles[:20])
                data['nb_articles'] = str(len(articles))

            # Fichiers joints
            downloads = []
            for a in soup.find_all('a', href=re.compile(r'/download/')):
                fname = a.get_text(strip=True)
                if fname:
                    downloads.append(fname)
            if downloads:
                data['fichiers_joints'] = ' | '.join(downloads)

            # Email
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text_full)
            if emails:
                data['email_contact'] = emails[0]

            # Budget
            budget_match = re.search(r'([\d\s,.]+)\s*(?:MAD|DH|dirhams?)', text_full, re.I)
            if budget_match:
                data['budget_estime'] = budget_match.group(0).strip()

            time.sleep(0.3)
            if self._is_equipment_related(data, extra_text=text_full):
                self.skipped_equipment += 1
                return None
            return data

        except Exception:
            return None

    # ===========================================
    # PARTIE 3: Enrichissement détails (Playwright)
    # ===========================================

    async def enrich_main_portal_details(self):
        """Enrichir les consultations du portail principal avec le détail (parallèle)"""
        main_entries = [v for v in self.results.values() if v['source'].startswith('portail_principal')]

        # In fast mode, do a minimal enrich only for critical missing fields (buyer/budget/dates).
        minimal = bool(self.skip_enrich)
        if minimal:
            print("\n[FAST]  Mini-enrichissement activé (acheteur/budget/dates)")
            main_entries = [
                v for v in main_entries
                if (not str(v.get("acheteur") or "").strip())
                or (not str(v.get("budget_estime") or "").strip())
                or (not str(v.get("date_limite") or "").strip())
            ]
            # Keep it snappy even if caller asked high concurrency.
            self.concurrency = max(1, min(int(self.concurrency or 1), 3))

        if not main_entries:
            print("\n[SKIP]  Pas de consultations portail principal à enrichir")
            return

        print(f"\n{'=' * 80}")
        mode_lbl = "MINI" if minimal else "COMPLET"
        print(f"[DETAIL] ENRICHISSEMENT DÉTAILS {mode_lbl} ({len(main_entries)} consultations, {self.concurrency} tabs)")
        print("=" * 80)

        enriched = 0
        errors = 0
        start = time.time()

        async def _enrich_batch(batch, browser, batch_idx):
            """Enrich a batch of entries using one browser tab."""
            nonlocal enriched, errors
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            for entry in batch:
                url = entry['url']
                if not url:
                    continue
                try:
                    await page.goto(url, wait_until='networkidle', timeout=20000)
                    # Some PRADO detail pages populate key fields after initial render.
                    # Wait a bit and try to detect any structured block (table or known labels).
                    try:
                        await page.wait_for_selector("table, text=/Acheteur|Organisme|Entité|Estimation|Montant/i", timeout=6000)
                    except Exception:
                        pass
                    await asyncio.sleep(0.4 if minimal else 0.8)
                    html = await page.content()
                    detail = self._parse_detail_page(html, url, entry['source'])
                    if detail:
                        for k, v in detail.items():
                            if minimal:
                                # Only override the missing critical fields in fast mode.
                                if k not in ["acheteur", "budget_estime", "date_limite", "date_publication", "reference", "objet"]:
                                    continue
                                if v and (not entry.get(k) or k in ["acheteur", "reference"]):
                                    entry[k] = v
                            else:
                                if v and (not entry.get(k) or k in ['objet', 'acheteur', 'reference']):
                                    entry[k] = v
                    enriched += 1
                except:
                    errors += 1
            await page.close()
            await context.close()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            # Split entries into N batches for concurrent tabs
            n = self.concurrency
            batches = [main_entries[i::n] for i in range(n)]

            # Progress reporter
            async def _report_progress():
                while True:
                    await asyncio.sleep(10)
                    done = enriched + errors
                    total = len(main_entries)
                    if done >= total:
                        break
                    elapsed = time.time() - start
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (total - done) / rate if rate > 0 else 0
                    print(f"  [ENRICH] {done}/{total} ({done*100//total}%) | {rate:.1f}/s | ETA:{eta:.0f}s")

            progress_task = asyncio.create_task(_report_progress())

            # Run all batches concurrently
            await asyncio.gather(*[
                _enrich_batch(batch, browser, i) for i, batch in enumerate(batches)
            ])

            progress_task.cancel()
            await browser.close()

        elapsed = time.time() - start
        print(f"  [DONE] {enriched} enrichis, {errors} erreurs en {elapsed:.0f}s")

    def _parse_detail_page(self, html, url, source):
        """Parser générique pour une page détail"""
        soup = BeautifulSoup(html, 'html.parser')
        data = {}

        # Titre/Objet
        for tag in ['h1', 'h2', 'h3', 'h4']:
            el = soup.find(tag)
            if el:
                text = el.get_text(strip=True)
                if len(text) > 10 and 'Marchés' not in text:
                    data['objet'] = text[:200]
                    break

        # Référence
        ref_el = soup.find(string=re.compile(r'Référence|N°'))
        if ref_el:
            parent = ref_el.parent
            if parent:
                data['reference'] = parent.get_text(strip=True)[:50]

        # Dates
        all_text = soup.get_text(' ', strip=True)
        dates = re.findall(r'(\d{2}/\d{2}/\d{4})', all_text)
        if dates:
            data['date_publication'] = dates[0]
        if len(dates) > 1:
            data['date_limite'] = dates[-1]

        # Acheteur / Organisme (best-effort)
        # Prefer structured extraction below; keep this fast heuristic as early signal.
        ach_el = soup.find(string=re.compile(r'Acheteur|Organisme|Entit[ée]|Pouvoir adjudicateur|Ma[iî]tre d', re.I))
        if ach_el:
            parent = ach_el.parent
            if parent:
                # Try sibling (common in definition lists)
                next_sib = parent.find_next_sibling()
                if next_sib:
                    val = next_sib.get_text(" ", strip=True)[:150]
                    if val:
                        data['acheteur'] = val

        # --- Structured extraction (more reliable than generic heuristics) ---
        page_text = soup.get_text(" ", strip=True)

        # Detect cancelled notices (Annule/Annulation) so we can exclude them from exports/dashboard.
        if re.search(r"\bannul", page_text, re.IGNORECASE) and (
            re.search(r"\bdate d'?annulation\b", page_text, re.IGNORECASE)
            or re.search(r"\binformations?\s+li[ée]es?\s+[àa]\s+l'?annulation\b", page_text, re.IGNORECASE)
            or re.search(r"\bannul[ée]\b", page_text, re.IGNORECASE)
        ):
            data["cancelled"] = "1"

        def _norm_label(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").strip().lower())

        def _first_date_ddmmyyyy(s: str) -> str:
            m = re.search(r"(\d{2}/\d{2}/\d{4})", s or "")
            return m.group(1) if m else ""

        def _extract_budget_value(s: str) -> str:
            if not s:
                return ""
            m = re.search(r"([\d][\d\s,.]*)", s)
            if not m:
                return s.strip()[:60]
            num = m.group(1).strip()
            # Keep currency marker if present; otherwise keep only number.
            curr = " DH" if re.search(r"(mad|dh|dhs|dirhams?)", s, re.IGNORECASE) else ""
            # Preserve HT/TTC if present (helps distinguish what portal shows).
            tax = ""
            if re.search(r"\bttc\b", s, re.IGNORECASE):
                tax = " TTC"
            elif re.search(r"\bht\b", s, re.IGNORECASE):
                tax = " HT"
            return f"{num}{curr}{tax}".strip()

        label_map = {
            "acheteur public": "acheteur",
            "acheteur": "acheteur",
            "organisme": "acheteur",
            "entite": "acheteur",
            "entité": "acheteur",
            "pouvoir adjudicateur": "acheteur",
            "maitre d'ouvrage": "acheteur",
            "maître d'ouvrage": "acheteur",
            "maitre d’ouvrage": "acheteur",
            "maître d’ouvrage": "acheteur",
            "reference": "reference",
            "rÃ©fÃ©rence": "reference",
            "date et heure limite de remise des plis": "date_limite",
            "date limite de remise des plis": "date_limite",
            "date limite": "date_limite",
            "date mise en ligne": "date_publication",
            "date de mise en ligne": "date_publication",
            "estimation (en dhs ttc)": "budget_estime",
            "estimation (en dhs ttc )": "budget_estime",
            "estimation (en dhs ht)": "budget_estime",
            "estimation (en dhs)": "budget_estime",
            "estimation": "budget_estime",
            "montant estimatif": "budget_estime",
            "montant estimé": "budget_estime",
            "budget estimatif": "budget_estime",
            "budget estimé": "budget_estime",
            "estimation du cout": "budget_estime",
            "estimation du coût": "budget_estime",
        }

        # Prefer 2-column rows: [label] [value]
        for tr in soup.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) < 2:
                continue
            label = _norm_label(tds[0].get_text(" ", strip=True).strip(":"))
            value = tds[1].get_text(" ", strip=True)
            if not label or not value:
                continue

            key = None
            for lab, k in label_map.items():
                if lab in label:
                    key = k
                    break
            if not key:
                continue

            if key == "date_limite":
                d = _first_date_ddmmyyyy(value)
                if d:
                    data["date_limite"] = d
            elif key == "date_publication":
                d = _first_date_ddmmyyyy(value)
                if d:
                    data["date_publication"] = d
            elif key == "budget_estime":
                b = _extract_budget_value(value)
                if b:
                    data["budget_estime"] = b
            else:
                data[key] = value.strip()[:150]

        # Also support definition lists / label-value blocks (dt/dd, strong/label + value)
        if not data.get("acheteur") or not data.get("budget_estime"):
            # dt/dd
            for dt in soup.find_all(["dt", "th"]):
                lab = _norm_label(dt.get_text(" ", strip=True).strip(":"))
                if not lab:
                    continue
                dd = dt.find_next_sibling(["dd", "td"])
                if not dd:
                    continue
                val = dd.get_text(" ", strip=True)
                if not val:
                    continue
                target = None
                for lab_key, k in label_map.items():
                    if lab_key in lab:
                        target = k
                        break
                if not target:
                    continue
                if target == "acheteur" and not data.get("acheteur"):
                    data["acheteur"] = val.strip()[:150]
                if target == "budget_estime" and not data.get("budget_estime"):
                    b = _extract_budget_value(val)
                    if b:
                        data["budget_estime"] = b

        # Regex fallbacks (last resort)
        if not data.get("acheteur"):
            m = re.search(
                r"\b(Acheteur\s*public|Organisme|Entit[ée]|Pouvoir\s+adjudicateur|Ma[iî]tre\s+d[’']ouvrage)\s*:?\s*(.+?)(?=\s{2,}|Type d'annonce|Proc[Ã©e]dure|Cat[Ã©e]gorie|$)",
                page_text,
                re.IGNORECASE,
            )
            if m:
                # group(2) is the value
                data["acheteur"] = m.group(2).strip()[:150]

        if not data.get("date_limite"):
            m = re.search(r"Date\s+et\s+heure\s+limite[^:]*:\s*(\d{2}/\d{2}/\d{4})", page_text, re.IGNORECASE)
            if m:
                data["date_limite"] = m.group(1)

        if not data.get("budget_estime"):
            m = re.search(
                r"(Estimation|Montant\s+estimatif|Budget\s+estimatif|Montant\s+estim[ée]?)\s*(?:\([^)]*\))?\s*:?\s*([\d][\d\s,.]+)",
                page_text,
                re.IGNORECASE,
            )
            if m:
                data["budget_estime"] = _extract_budget_value(m.group(2))

        return data

    # ===========================================
    # PARTIE 4: Export
    # ===========================================

    def export_csv(self):
        """Export toutes les consultations en CSV"""
        # By default, overwrite a stable "latest" export to avoid accumulating timestamped files.
        # Set SCRAPE_TIMESTAMP_EXPORTS=1 to keep timestamped filenames.
        keep_ts = os.environ.get("SCRAPE_TIMESTAMP_EXPORTS", "0").strip() == "1"
        if keep_ts:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"data/appels_offres_profond_{timestamp}.csv"
        else:
            filename = "data/appels_offres_profond_latest.csv"

        fieldnames = [
            'id', 'reference', 'objet', 'acheteur', 'categorie',
            'nature_prestation', 'date_publication', 'date_limite',
            'lieu_execution', 'budget_estime', 'nb_articles', 'articles',
            'fichiers_joints', 'email_contact', 'url', 'source'
        ]

        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            for cid in sorted(self.results.keys()):
                # Exclude cancelled notices (Annule/Annulation).
                if str(self.results[cid].get("cancelled", "")).strip() in ("1", "true", "True"):
                    continue
                # Exclude hardware/equipment purchase + installation opportunities.
                if self._is_equipment_related(self.results[cid]):
                    continue
                row = {}
                for k in fieldnames:
                    row[k] = self.results[cid].get(k, '')
                writer.writerow(row)

        print(f"\n[FILE] CSV exporté: {filename}")
        print(f"   -> {len(self.results)} consultations totales")
        return filename

    def display_stats(self):
        """Afficher les statistiques"""
        total = len(self.results)
        bdc = sum(1 for v in self.results.values() if v['source'] == 'bdc')
        main = total - bdc

        print(f"\n{'=' * 80}")
        print("[STATS] STATISTIQUES SCRAPING PROFOND")
        print("=" * 80)
        print(f"  Total unique:        {total}")
        if self.exclude_equipment:
            print(f"  Exclues (equip.):    {self.skipped_equipment}")
        print(f"  |-- Portail principal: {main}")
        print(f"  `-- Section BDC:      {bdc}")

        # Par catégorie
        cats = {}
        for v in self.results.values():
            cat = v.get('categorie', 'N/A') or 'N/A'
            cats[cat] = cats.get(cat, 0) + 1
        print(f"\n  Par catégorie:")
        for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
            print(f"    {cat}: {cnt}")

        # Complétude
        fields = ['objet', 'acheteur', 'date_limite', 'reference']
        print(f"\n  Complétude:")
        for f in fields:
            filled = sum(1 for v in self.results.values() if v.get(f))
            pct = filled * 100 // total if total else 0
            print(f"    {f}: {filled}/{total} ({pct}%)")


async def main():
    import argparse
    parser = argparse.ArgumentParser(description='Scraper profond marchespublics.gov.ma')
    parser.add_argument('--fast', action='store_true', help='Mode rapide: skip enrichissement détails')
    parser.add_argument('--concurrency', type=int, default=5, help='Nombre de tabs parallèles pour enrichissement (défaut: 5)')
    args = parser.parse_args()

    start = time.time()
    scraper = DeepScraper(skip_enrich=args.fast, concurrency=args.concurrency)

    try:
        # Phase 1: Portail principal avec Playwright (recherche par mots-clés)
        await scraper.scrape_main_portal()

        # Phase 2: Section BDC complète
        scraper.scrape_bdc_all_pages()

        # Phase 3: Enrichir les détails du portail principal
        await scraper.enrich_main_portal_details()

    except KeyboardInterrupt:
        print("\n[WARN] Interruption! Sauvegarde des résultats partiels...")
    except Exception as e:
        print(f"\n[ERR]  Erreur: {e}")
    finally:
        if scraper.results:
            scraper.display_stats()
            csv_file = scraper.export_csv()
            elapsed = time.time() - start
            print(f"\n[TIME]  Durée totale: {elapsed:.0f}s")
            print(f"[FILE] Fichier: {csv_file}")
        else:
            print("\n[WARN] Aucun résultat à exporter")


if __name__ == '__main__':
    asyncio.run(main())
