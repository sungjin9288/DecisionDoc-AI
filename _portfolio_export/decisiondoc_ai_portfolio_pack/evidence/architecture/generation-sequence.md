# Generation Sequence Evidence

```mermaid
sequenceDiagram
    participant Client as Client / curl
    participant API as FastAPI /generate
    participant Auth as API key dependency
    participant Service as GenerationService
    participant Provider as MockProvider
    participant Storage as LocalStorage
    participant Templates as Jinja2 templates

    Client->>API: POST /generate with GenerateRequest
    API->>Auth: validate X-DecisionDoc-Api-Key
    Auth-->>API: accepted
    API->>Service: generate_documents(request)
    Service->>Provider: generate_bundle(schema_version, request_id)
    Provider-->>Service: structured bundle JSON
    Service->>Storage: save bundle JSON
    Service->>Templates: render selected docs
    Templates-->>Service: Markdown documents
    Service->>Storage: save export files when export endpoint is used
    Service-->>API: metadata + generated docs
    API-->>Client: JSON response
```

Runtime evidence:

- `evidence/api-responses/generate-tech-decision.json`
- `evidence/api-responses/generate-export-tech-decision.json`
- `evidence/output-artifacts/export_adr.md`
- `evidence/output-artifacts/export_onepager.md`
