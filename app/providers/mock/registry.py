"""Registry mapping (bundle_id, doc_key) -> mock content builder function."""
from typing import Any

from app.providers.mock.fixtures_bid_decision import (
    _bid_decision_checklist,
    _bid_decision_go_no_go_memo,
    _bid_decision_handoff,
    _bid_decision_opportunity_brief,
)
from app.providers.mock.fixtures_business import (
    _business_execution_roadmap,
    _business_market_analysis,
    _business_model,
    _business_overview,
)
from app.providers.mock.fixtures_edu import (
    _edu_assessment,
    _edu_curriculum,
    _edu_objective,
    _edu_operation_plan,
)
from app.providers.mock.fixtures_presentation import (
    _presentation_qa_preparation,
    _presentation_slide_script,
    _presentation_slide_structure,
)
from app.providers.mock.fixtures_proposal import (
    _proposal_business_understanding,
    _proposal_execution_plan,
    _proposal_expected_impact,
    _proposal_tech_proposal,
)
from app.providers.mock.fixtures_rfp_performance import (
    _performance_overview,
    _performance_quality_risk,
    _rfp_analysis_summary,
    _rfp_analysis_win_strategy,
)


# ===========================================================================
# Registry: (bundle_id, doc_key) → content builder function
# ===========================================================================
_CONTENT_BUILDERS: dict[tuple[str, str], Any] = {
    ("bid_decision_kr",  "opportunity_brief"):      _bid_decision_opportunity_brief,
    ("bid_decision_kr",  "go_no_go_memo"):          _bid_decision_go_no_go_memo,
    ("bid_decision_kr",  "bid_readiness_checklist"): _bid_decision_checklist,
    ("bid_decision_kr",  "proposal_kickoff_summary"): _bid_decision_handoff,
    ("proposal_kr",      "business_understanding"): _proposal_business_understanding,
    ("proposal_kr",      "tech_proposal"):          _proposal_tech_proposal,
    ("proposal_kr",      "execution_plan"):         _proposal_execution_plan,
    ("proposal_kr",      "expected_impact"):        _proposal_expected_impact,
    ("rfp_analysis_kr",  "rfp_summary"):            _rfp_analysis_summary,
    ("rfp_analysis_kr",  "win_strategy"):           _rfp_analysis_win_strategy,
    ("performance_plan_kr", "performance_overview"): _performance_overview,
    ("performance_plan_kr", "quality_risk_plan"):    _performance_quality_risk,
    ("business_plan_kr", "business_overview"):      _business_overview,
    ("business_plan_kr", "market_analysis"):        _business_market_analysis,
    ("business_plan_kr", "business_model"):         _business_model,
    ("business_plan_kr", "execution_roadmap"):      _business_execution_roadmap,
    ("edu_plan_kr",      "edu_objective"):          _edu_objective,
    ("edu_plan_kr",      "curriculum"):             _edu_curriculum,
    ("edu_plan_kr",      "assessment"):             _edu_assessment,
    ("edu_plan_kr",      "operation_plan"):         _edu_operation_plan,
    ("presentation_kr",  "slide_structure"):        _presentation_slide_structure,
    ("presentation_kr",  "slide_script"):           _presentation_slide_script,
    ("presentation_kr",  "qa_preparation"):         _presentation_qa_preparation,
}
