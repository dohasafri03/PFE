import json

path = 'c:/Users/pc/IdeaProjects/marche_ai_platform/n8n/workflow_pipeline.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

bad_names = ["Wait 30s", "Statut", "En cours ?", "Wait 60s", "Erreur ?"]
data['nodes'] = [n for n in data['nodes'] if n['name'] not in bad_names]

# Transform Scrape node
for n in data['nodes']:
    if n['name'] == 'Scrape':
        url_expr = n['parameters']['url']
        n['parameters']['url'] = url_expr.replace("'/scrape'", "'/scrape/sync'")
        n['parameters']['options']['timeout'] = 900000

# Create new IF node
new_if = {
  "parameters": {
    "conditions": {
      "options": {
        "caseSensitive": True,
        "leftValue": "",
        "typeValidation": "strict"
      },
      "conditions": [
        {
          "id": "cond-sync-error",
          "leftValue": "={{ $json.scraping.error }}",
          "rightValue": "",
          "operator": {
            "type": "string",
            "operation": "notEmpty"
          }
        }
      ],
      "combinator": "and"
    }
  },
  "id": "node-scrape-sync-error",
  "name": "Check Erreur Sync",
  "type": "n8n-nodes-base.if",
  "typeVersion": 2,
  "position": [900, 320]
}
data['nodes'].append(new_if)

# Connections
data['connections']['Scrape'] = {
    "main": [
        [{"node": "Check Erreur Sync", "type": "main", "index": 0}]
    ]
}

data['connections']['Check Erreur Sync'] = {
    "main": [
        [{"node": "Log Erreur", "type": "main", "index": 0}],
        [{"node": "Filtrer IT", "type": "main", "index": 0}]
    ]
}

for k in bad_names:
    data['connections'].pop(k, None)
    
# Update Log Erreur
for n in data['nodes']:
    if n['name'] == 'Log Erreur':
        n['parameters']['assignments']['assignments'][0]['value'] = "=Erreur scraping : {{ $(\"Scrape\").item.json.scraping.error }}\\nVerifier les logs API."
        
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)

print("Workflow patched successfully!")
