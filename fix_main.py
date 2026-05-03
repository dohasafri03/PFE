import os

path = r"c:\Users\pc\IdeaProjects\marche_ai_platform\api\main.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

bad_block = """        scraper.display_stats()
        csv_file = scraper.export_csv()
    background_tasks.add_task(asyncio.to_thread, lambda: asyncio.run(_run_scrape(fast_mode=fast, concurrency=conc)))
    mode = "rapide (sans enrichissement)" if fast else f"complet ({conc} tabs)"
    return {"status": "started", "message": f"Scraping lancé en arrière-plan - mode {mode}"}"""

good_block = """        scraper.display_stats()
        csv_file = scraper.export_csv()
        elapsed = time.time() - start
        _status["scraping"]["last_csv"] = csv_file
        _status["scraping"]["last_run"] = datetime.now().isoformat()
        logger.info(f"Scraping terminé en {elapsed:.0f}s → {csv_file}")
    except Exception as e:
        _status["scraping"]["error"] = str(e)
        logger.exception("Scraping failed")
    finally:
        _status["scraping"]["running"] = False

@app.post("/scrape")
async def scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    if _status["scraping"]["running"]:
        return {
            "status": "already_running",
            "message": "Scraping deja en cours",
            "scraping": dict(_status["scraping"]),
        }

    fast = req.fast_mode
    conc = req.concurrency
    background_tasks.add_task(asyncio.to_thread, lambda: asyncio.run(_run_scrape(fast_mode=fast, concurrency=conc)))
    mode = "rapide (sans enrichissement)" if fast else f"complet ({conc} tabs)"
    return {"status": "started", "message": f"Scraping lancé en arrière-plan - mode {mode}"}

@app.post("/scrape/sync")
async def scrape_sync(req: ScrapeRequest):
    if _status["scraping"]["running"]:
        return {
            "status": "already_running",
            "message": "Scraping deja en cours",
            "scraping": dict(_status["scraping"]),
        }
    fast = req.fast_mode
    conc = req.concurrency
    import asyncio
    await asyncio.to_thread(lambda: asyncio.run(_run_scrape(fast_mode=fast, concurrency=conc)))
    result = dict(_status["scraping"])
    from pathlib import Path
    if result.get("last_csv") and Path(result["last_csv"]).exists():
        result["rows"] = _count_csv_rows(Path(result["last_csv"]))
    return {"status": "done", "scraping": result}"""

content = content.replace(bad_block, good_block)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applique !")
