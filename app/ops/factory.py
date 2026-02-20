from app.ops.service import OpsInvestigationService


def get_ops_service() -> OpsInvestigationService:
    return OpsInvestigationService()
