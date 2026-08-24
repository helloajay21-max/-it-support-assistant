# GitHub Secrets Setup — IT Support Assistant
# Same pattern as MCP-Project

Go to: GitHub Repo → Settings → Secrets and variables → Actions → New repository secret

┌──────────────────────┬────────────────────────────────────────────────────────────┐
│ Secret Name          │ Value                                                      │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ AZURE_CREDENTIALS    │ JSON from: ./scripts/create_service_principal.sh           │
│                      │ (same format as MCP-Project AZURE_CREDENTIALS)             │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ DOCKERHUB_USERNAME   │ helloajay21                                                │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ DOCKERHUB_TOKEN      │ Your Docker Hub access token (same as MCP-Project) ✅      │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ RESOURCE_GROUP       │ Ajay-Practice                                              │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ WEBAPP_NAME          │ it-support-ajay-001                                        │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ OPENAI_API_KEY       │ Same sk-... key used in MCP-Project ✅                     │
└──────────────────────┴────────────────────────────────────────────────────────────┘

That's it — only 6 secrets needed.
4 of them you already have from MCP-Project (AZURE_CREDENTIALS, DOCKERHUB_USERNAME, DOCKERHUB_TOKEN, OPENAI_API_KEY).
2 are new (RESOURCE_GROUP = Ajay-Practice, WEBAPP_NAME = it-support-ajay-001).
