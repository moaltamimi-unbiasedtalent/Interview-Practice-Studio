"""Company & opportunity context — time-sensitive, evidence-grounded employer
research, kept strictly separate from the permanent occupational knowledge base.
"""

from src.copilot.company.context import (
    build_company_context,
    classify_source,
    validate_url,
)
from src.copilot.company.models import CompanyContext, CompanySource
from src.copilot.company.provider import (
    FetchedDocument,
    NullResearchProvider,
    WebResearchProvider,
)

__all__ = [
    "CompanyContext", "CompanySource",
    "build_company_context", "validate_url", "classify_source",
    "WebResearchProvider", "NullResearchProvider", "FetchedDocument",
]
