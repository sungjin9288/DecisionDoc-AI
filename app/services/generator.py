from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.schemas import DocType, GenerateRequest
from app.services.providers.base import Provider


class DocumentGenerator:
    TEMPLATE_MAP = {
        DocType.adr: "adr.md.j2",
        DocType.onepager: "onepager.md.j2",
        DocType.eval_plan: "eval_plan.md.j2",
        DocType.ops_checklist: "ops_checklist.md.j2",
    }

    def __init__(self, provider: Provider, template_dir: Path) -> None:
        self.provider = provider
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def generate(self, payload: GenerateRequest) -> list[dict]:
        docs: list[dict] = []
        for doc_type in payload.doc_types:
            template_name = self.TEMPLATE_MAP[doc_type]
            context = self.provider.build_context(doc_type, payload)
            markdown = self.env.get_template(template_name).render(**context).strip() + "\n"
            docs.append({"doc_type": doc_type.value, "markdown": markdown})
        return docs
