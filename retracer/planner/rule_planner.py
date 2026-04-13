"""Rule-based planner — keyword matching against the flow library.

This is the MVP planner. It scores flows by keyword overlap with the
bug description. Designed to be replaced by an LLM planner without
changing any other module (same PlannerAdapter interface).
"""

from __future__ import annotations

import re

from retracer.models.pipeline_context import PlanResult
from retracer.planner.base import register_planner
from retracer.planner.flow_library import flows_for_platform


class RuleBasedPlanner:
    @property
    def name(self) -> str:
        return "rule"

    def plan(
        self,
        *,
        description: str,
        platform: str,
        fixture: str | None = None,
        image_path: str | None = None,
    ) -> PlanResult:
        words = set(re.findall(r"[a-z]+", description.lower()))
        candidates = flows_for_platform(platform)

        scored: list[tuple[int, str, str]] = []
        for flow in candidates:
            overlap = len(words & flow.tags)
            if overlap > 0:
                score = overlap + flow.priority
                scored.append((score, flow.flow_id, f"matched {overlap} keyword(s): {words & flow.tags}"))

        # Sort by score descending, take top 5
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:5]

        # Always include launch_app as the first flow
        flow_ids = ["launch_app"]
        reasoning = ["launch_app: always included as warm-up"]

        for score, flow_id, reason in top:
            if flow_id not in flow_ids:
                flow_ids.append(flow_id)
                reasoning.append(f"{flow_id}: score={score}, {reason}")

        # If no keyword matches, include a generic fallback
        if len(flow_ids) == 1:
            flow_ids.append("open_profile_menu")
            reasoning.append("open_profile_menu: fallback (no keyword matches)")

        return PlanResult(
            flow_ids=flow_ids,
            reasoning=reasoning,
            planner_name=self.name,
        )


register_planner(RuleBasedPlanner())
