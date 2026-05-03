#!/usr/bin/env python3
"""Rewrite n8n workflow JSON: clean encoding, no emojis, 127.0.0.1 URLs."""
import json

workflow = {
    "name": "Marche AI - Pipeline",
    "nodes": [
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {"field": "cronExpression", "expression": "0 9 * * 1-5"}
                    ]
                }
            },
            "id": "node-cron",
            "name": "Cron 9h",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 300]
        },
        {
            "parameters": {
                "url": "http://127.0.0.1:8000/health",
                "options": {"timeout": 10000}
            },
            "id": "node-health",
            "name": "Health",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [240, 380],
            "retryOnFail": True,
            "maxTries": 3,
            "waitBetweenTries": 5000
        },
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "cond-health",
                            "leftValue": "={{ $json.status }}",
                            "rightValue": "ok",
                            "operator": {"type": "string", "operation": "equals"}
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "node-check-health",
            "name": "API OK ?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [460, 380]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "http://127.0.0.1:8000/scrape",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={\"fast_mode\": true, \"concurrency\": 5}",
                "options": {"timeout": 600000}
            },
            "id": "node-scrape",
            "name": "Scrape",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [680, 320]
        },
        {
            "parameters": {"amount": 30, "unit": "seconds"},
            "id": "node-wait-scrape",
            "name": "Wait 30s",
            "type": "n8n-nodes-base.wait",
            "typeVersion": 1.1,
            "position": [880, 320]
        },
        {
            "parameters": {
                "url": "http://127.0.0.1:8000/scrape/status",
                "options": {"timeout": 10000}
            },
            "id": "node-scrape-status",
            "name": "Statut",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1080, 320]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "cond-running",
                            "leftValue": "={{ $json.running }}",
                            "rightValue": True,
                            "operator": {"type": "boolean", "operation": "true"}
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "node-scrape-done",
            "name": "En cours ?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1280, 320]
        },
        {
            "parameters": {"amount": 60, "unit": "seconds"},
            "id": "node-wait-loop",
            "name": "Wait 60s",
            "type": "n8n-nodes-base.wait",
            "typeVersion": 1.1,
            "position": [1480, 240]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "cond-error",
                            "leftValue": "={{ $json.error }}",
                            "rightValue": "",
                            "operator": {"type": "string", "operation": "notEmpty"}
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "node-scrape-error",
            "name": "Erreur ?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1480, 420]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "http://127.0.0.1:8000/pipeline/filter-it",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "{}",
                "options": {"timeout": 60000}
            },
            "id": "node-filter-it",
            "name": "Filtrer IT",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1700, 420]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [
                        {
                            "id": "cond-relevant",
                            "leftValue": "={{ $json.total_it }}",
                            "rightValue": 0,
                            "operator": {"type": "number", "operation": "gt"}
                        }
                    ],
                    "combinator": "and"
                }
            },
            "id": "node-has-results",
            "name": "IT trouvees ?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1920, 420]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "http://127.0.0.1:8000/pipeline/run-sync",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "{\n  \"generate_dossiers\": false,\n  \"use_rag\": false,\n  \"enrich_cps\": true,\n  \"all_priorities\": true\n}",
                "options": {"timeout": 1800000}
            },
            "id": "node-pipeline",
            "name": "Pipeline",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2140, 360]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "http://127.0.0.1:8000/pipeline/generate-dossiers",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "{\n  \"use_rag\": false,\n  \"convert_pdf\": true,\n  \"rate_limit\": 3.0\n}",
                "options": {"timeout": 3600000}
            },
            "id": "node-gen-dossiers",
            "name": "Dossiers RAG",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2360, 360]
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "set-summary",
                            "name": "summary",
                            "value": "=Pipeline termine\n\nScraping\n  Consultations brutes : {{ $(\"Filtrer IT\").item.json.total_brutes }}\n  Consultations IT     : {{ $(\"Filtrer IT\").item.json.total_it }}\n\nRepartition par domaine\n  AI             : {{ $(\"Filtrer IT\").item.json.par_domaine.AI ?? 0 }}\n  Data           : {{ $(\"Filtrer IT\").item.json.par_domaine.Data ?? 0 }}\n  BI             : {{ $(\"Filtrer IT\").item.json.par_domaine.BI ?? 0 }}\n  Dev            : {{ $(\"Filtrer IT\").item.json.par_domaine.Dev ?? 0 }}\n  Cloud          : {{ $(\"Filtrer IT\").item.json.par_domaine.Cloud ?? 0 }}\n  Cybersecurity  : {{ $(\"Filtrer IT\").item.json.par_domaine.Cybersecurity ?? 0 }}\n\nDossiers generes\n  DOCX : {{ $(\"Dossiers RAG\").item.json.docx_generated ?? 0 }}\n  PDF  : {{ $(\"Dossiers RAG\").item.json.pdf_generated ?? 0 }}\n  RAG  : {{ $(\"Dossiers RAG\").item.json.rag.enriched ?? 0 }} enrichis, {{ $(\"Dossiers RAG\").item.json.rag.cached ?? 0 }} en cache\n\nDate : {{ $now.toISO() }}",
                            "type": "string"
                        },
                        {
                            "id": "set-total-it",
                            "name": "total_it",
                            "value": "={{ $(\"Filtrer IT\").item.json.total_it }}",
                            "type": "number"
                        },
                        {
                            "id": "set-total-brutes",
                            "name": "total_brutes",
                            "value": "={{ $(\"Filtrer IT\").item.json.total_brutes }}",
                            "type": "number"
                        }
                    ]
                }
            },
            "id": "node-summary",
            "name": "Resume",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [2580, 360]
        },
        {
            "parameters": {
                "fromEmail": "pipeline@alexsys.ma",
                "toEmail": "team@alexsys.ma",
                "subject": "=Veille IT - {{ $json.total_it }} opportunites / {{ $json.total_brutes }} consultations",
                "emailType": "text",
                "message": "={{ $json.summary }}"
            },
            "id": "node-email",
            "name": "Rapport",
            "type": "n8n-nodes-base.emailSend",
            "typeVersion": 2.1,
            "position": [2800, 360]
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "set-no-results",
                            "name": "message",
                            "value": "=Aucune opportunite IT detectee dans les {{ $(\"Filtrer IT\").item.json.total_brutes }} consultations scrappees.",
                            "type": "string"
                        }
                    ]
                }
            },
            "id": "node-no-results",
            "name": "0 IT",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [2140, 520]
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "set-err-msg",
                            "name": "error_message",
                            "value": "=Erreur scraping : {{ $(\"Statut\").item.json.error }}\nVerifier les logs API.",
                            "type": "string"
                        }
                    ]
                }
            },
            "id": "node-scrape-fail",
            "name": "Log Erreur",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [1700, 540]
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "set-api-down",
                            "name": "error_message",
                            "value": "API non disponible. Lancer : python -m api.main",
                            "type": "string"
                        }
                    ]
                }
            },
            "id": "node-api-down",
            "name": "API Down",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [680, 480]
        }
    ],
    "connections": {
        "Cron 9h": {
            "main": [[{"node": "Health", "type": "main", "index": 0}]]
        },
        "Health": {
            "main": [[{"node": "API OK ?", "type": "main", "index": 0}]]
        },
        "API OK ?": {
            "main": [
                [{"node": "Scrape", "type": "main", "index": 0}],
                [{"node": "API Down", "type": "main", "index": 0}]
            ]
        },
        "Scrape": {
            "main": [[{"node": "Wait 30s", "type": "main", "index": 0}]]
        },
        "Wait 30s": {
            "main": [[{"node": "Statut", "type": "main", "index": 0}]]
        },
        "Statut": {
            "main": [[{"node": "En cours ?", "type": "main", "index": 0}]]
        },
        "En cours ?": {
            "main": [
                [{"node": "Wait 60s", "type": "main", "index": 0}],
                [{"node": "Erreur ?", "type": "main", "index": 0}]
            ]
        },
        "Wait 60s": {
            "main": [[{"node": "Statut", "type": "main", "index": 0}]]
        },
        "Erreur ?": {
            "main": [
                [{"node": "Log Erreur", "type": "main", "index": 0}],
                [{"node": "Filtrer IT", "type": "main", "index": 0}]
            ]
        },
        "Filtrer IT": {
            "main": [[{"node": "IT trouvees ?", "type": "main", "index": 0}]]
        },
        "IT trouvees ?": {
            "main": [
                [{"node": "Pipeline", "type": "main", "index": 0}],
                [{"node": "0 IT", "type": "main", "index": 0}]
            ]
        },
        "Pipeline": {
            "main": [[{"node": "Dossiers RAG", "type": "main", "index": 0}]]
        },
        "Dossiers RAG": {
            "main": [[{"node": "Resume", "type": "main", "index": 0}]]
        },
        "Resume": {
            "main": [[{"node": "Rapport", "type": "main", "index": 0}]]
        }
    },
    "settings": {
        "executionOrder": "v1",
        "saveManualExecutions": True,
        "callerPolicy": "workflowsFromSameOwner",
        "errorWorkflow": ""
    },
    "staticData": None,
    "tags": [
        {"name": "marches-publics"},
        {"name": "alexsys"},
        {"name": "pipeline-v2"}
    ],
    "pinData": {},
    "versionId": "3"
}

with open("n8n/workflow_pipeline.json", "w", encoding="utf-8") as f:
    json.dump(workflow, f, ensure_ascii=False, indent=2)

print(f"OK - {len(workflow['nodes'])} nodes, {len(workflow['connections'])} connections")

