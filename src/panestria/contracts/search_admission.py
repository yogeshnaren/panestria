"""Immutable search budget; it cannot expand the underlying goal or policy."""

from pydantic import Field, StrictInt

from panestria.contracts.research_admission import ResearchAuthorityBinding


class SearchPlan(ResearchAuthorityBinding):
    max_queries: StrictInt = Field(ge=1, le=16)
