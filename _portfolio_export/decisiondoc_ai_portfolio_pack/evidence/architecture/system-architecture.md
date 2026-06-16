# System Architecture Evidence

```mermaid
flowchart TD
    User["User / Browser PWA"]
    StaticUI["FastAPI static UI<br/>app/static/index.html"]
    API["FastAPI API<br/>app/main.py"]
    Middleware["Middleware<br/>request id, observability, tenant, auth, audit, billing, rate limit, security headers"]
    Routers["Routers<br/>generate, health, bundles, projects, knowledge, approvals, report-workflows"]
    Generation["GenerationService<br/>app/services/generation_service.py"]
    Provider["Provider abstraction<br/>Mock / OpenAI / Gemini / Claude / Local"]
    Templates["Bundle catalog + Jinja2 templates<br/>app/bundle_catalog, app/templates"]
    Storage["Storage abstraction<br/>LocalStorage / S3Storage"]
    Response["Markdown docs, export files, API JSON response"]

    User --> StaticUI
    User --> API
    API --> Middleware
    Middleware --> Routers
    Routers --> Generation
    Generation --> Provider
    Generation --> Templates
    Generation --> Storage
    Storage --> Response
    Templates --> Response
```

Evidence files:

- `app/main.py`
- `app/routers/generate.py`
- `app/routers/health.py`
- `app/services/generation_service.py`
- `app/providers/factory.py`
- `app/storage/factory.py`
- `app/bundle_catalog/registry.py`
