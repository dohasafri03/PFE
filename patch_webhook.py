import sys
import re
import json

# 1. Update api/main.py
main_file = r'c:\Users\pc\IdeaProjects\marche_ai_platform\api\main.py'
with open(main_file, 'r', encoding='utf-8') as f:
    text = f.read()

if "from typing import Optional" not in text:
    text = "from typing import Optional\n" + text

# Update ScrapeRequest
if "webhook_url: Optional[str]" not in text:
    text = re.sub(
        r'(class ScrapeRequest\(BaseModel\):\n\s+fast_mode: bool = True\n\s+concurrency: int = 5\n)',
        r'\1    webhook_url: Optional[str] = None\n',
        text
    )

# Update _run_scrape signature
if "webhook_url: Optional[str] = None" not in text:
    text = text.replace(
        'async def _run_scrape(fast_mode: bool = False, concurrency: int = 5):',
        'async def _run_scrape(fast_mode: bool = False, concurrency: int = 5, webhook_url: Optional[str] = None):'
    )

# Update _run_scrape finally block
old_finally = """    finally:\n        _status["scraping"]["running"] = False"""
new_finally = """    finally:
        _status["scraping"]["running"] = False
        if webhook_url:
            try:
                import requests
                logger.info(f"Appel du webhook n8n: {webhook_url}")
                requests.post(webhook_url, json={"status": "done", "scraping": dict(_status["scraping"])}, timeout=10)
            except Exception as e:
                logger.error(f"Echec appel webhook: {e}")"""
if "Appel du webhook n8n" not in text:
    text = text.replace(old_finally, new_finally)

# Update background_tasks call in scrape (Wait, don't break if already matched!)
if "webhook_url=req.webhook_url" not in text:
    text = text.replace(
        'lambda: asyncio.run(_run_scrape(fast_mode=fast, concurrency=conc))',
        'lambda: asyncio.run(_run_scrape(fast_mode=fast, concurrency=conc, webhook_url=req.webhook_url))'
    )

with open(main_file, 'w', encoding='utf-8') as f:
    f.write(text)

# 2. Update n8n workflow
wf_path = r'c:\Users\pc\IdeaProjects\marche_ai_platform\n8n\workflow_pipeline.json'
with open(wf_path, 'r', encoding='utf-8') as f:
    wf = json.load(f)

# Find Scrape node, Check Erreur node
for n in wf.get('nodes', []):
    if n['name'] == 'Scrape':
        # Use async endpoint
        if "'/scrape/sync'" in n['parameters']['url']:
            n['parameters']['url'] = n['parameters']['url'].replace("'/scrape/sync'", "'/scrape'")
        # Include webhook_url
        n['parameters']['jsonBody'] = '={\n  "fast_mode": true,\n  "concurrency": 5,\n  "webhook_url": "{{ $execution.resumeUrl }}"\n}'
        if 'options' not in n['parameters']:
            n['parameters']['options'] = {}
        n['parameters']['options']['timeout'] = 10000

    if n['name'] == 'Check Erreur Sync':
        n['name'] = 'Check Erreur Webhook'
        n['parameters']['conditions']['conditions'][0]['leftValue'] = '={{ $json.body.scraping.error }}'

    if n['name'] == 'Log Erreur':
        n['parameters']['assignments']['assignments'][0]['value'] = '=Erreur scraping : {{ $("Wait Webhook").item.json.body.scraping.error }}\\nVerifier les logs API.'

# Ensure Wait Webhook node exists
has_wait_webhook = any(n['name'] == 'Wait Webhook' for n in wf.get('nodes', []))
if not has_wait_webhook:
    wait_node = {
        "parameters": {
            "resumeOption": "webhook",
            "options": {}
        },
        "id": "node-wait-webhook-real",
        "name": "Wait Webhook",
        "type": "n8n-nodes-base.wait",
        "typeVersion": 1.1,
        "position": [780, 320]
    }
    wf['nodes'].append(wait_node)

# Fix Connections:
# Scrape -> Wait Webhook
wf['connections']['Scrape'] = {
    "main": [
        [{"node": "Wait Webhook", "type": "main", "index": 0}]
    ]
}
# Wait Webhook -> Check Erreur Webhook
wf['connections']['Wait Webhook'] = {
    "main": [
        [{"node": "Check Erreur Webhook", "type": "main", "index": 0}]
    ]
}
# Check Erreur Webhook -> Log Erreur, Filtrer IT
for k in list(wf['connections'].keys()):
    if k == 'Check Erreur Sync':
        wf['connections']['Check Erreur Webhook'] = wf['connections'].pop(k)

with open(wf_path, 'w', encoding='utf-8') as f:
    json.dump(wf, f, indent=2)

print("Patch Webhook applique !")
