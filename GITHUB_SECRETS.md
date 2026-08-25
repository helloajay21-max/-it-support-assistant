# GitHub Secrets Setup — IT Support Assistant
# Same pattern as MCP-Project

Go to: GitHub Repo → Settings → Secrets and variables → Actions → New repository secret

┌──────────────────────┬────────────────────────────────────────────────────────────┐
│ Secret Name          │ Value                                                      │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ AZURE_CREDENTIALS    │ JSON from: ./scripts/create_service_principal.sh           │
│                      │ (same format as MCP-Project AZURE_CREDENTIALS)             │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ DOCKERHUB_USERNAME   │ your-dockerhub-username                                    │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ DOCKERHUB_TOKEN      │ Your Docker Hub access token (same as MCP-Project) ✅      │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ RESOURCE_GROUP       │ your-resource-group                                        │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ WEBAPP_NAME          │ your-webapp-name                                           │
├──────────────────────┼────────────────────────────────────────────────────────────┤
│ OPENAI_API_KEY       │ sk-...                                                     │
└──────────────────────┴────────────────────────────────────────────────────────────┘

That's it — only 6 secrets needed.
Set the values for your own Azure and Docker Hub environment.
