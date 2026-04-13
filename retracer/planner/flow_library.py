"""Flow library — registry of known automation flows and their metadata.

Flows are loaded from the flows/ directory. Each flow has metadata
(platform, tags, description) that the planner uses for matching.
This can later be enhanced into a "flow graph" for token-efficient
LLM planning (send matching subgraph, not the full library).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FlowEntry:
    """Metadata for a single automation flow."""

    flow_id: str
    platform: str  # "ios", "tvos", "common"
    tags: frozenset[str] = frozenset()
    description: str = ""
    priority: int = 0  # Higher = preferred when multiple match


# Built-in flow registry (extend via flow_library.yaml or directory scanning)
FLOW_LIBRARY: list[FlowEntry] = [
    # Common
    FlowEntry("launch_app", "common", frozenset({"launch", "start", "open"}),
              "Launch or foreground the app"),

    # iOS / tvOS profile flows
    FlowEntry("open_profile_menu", "common",
              frozenset({"profile", "menu", "account", "settings", "navigation"}),
              "Navigate to the profile/account menu"),
    FlowEntry("switch_profile", "common",
              frozenset({"profile", "switch", "account", "user"}),
              "Switch between user profiles"),

    # Sport flows
    FlowEntry("navigate_to_sport", "common",
              frozenset({"sport", "sports", "live", "stream", "home"}),
              "Navigate to the sport section"),
    FlowEntry("sport_then_profile", "common",
              frozenset({"sport", "profile", "overlay", "menu", "modal"}),
              "Go to sport then open profile — tests overlay conflicts",
              priority=1),

    # Modal / overlay flows
    FlowEntry("trigger_modal_overlay", "common",
              frozenset({"modal", "overlay", "popup", "dialog", "sheet"}),
              "Trigger various modal/overlay states"),

    # tvOS-specific
    FlowEntry("tvos_focus_navigation", "tvos",
              frozenset({"focus", "navigation", "remote", "dpad", "tvos"}),
              "Test focus-based navigation on tvOS"),
    FlowEntry("tvos_top_shelf", "tvos",
              frozenset({"shelf", "top", "tvos", "home"}),
              "Interact with the tvOS top shelf"),

    # iOS-specific
    FlowEntry("ios_tab_navigation", "ios",
              frozenset({"tab", "navigation", "bar", "ios"}),
              "Test tab bar navigation on iOS"),
    FlowEntry("ios_pull_to_refresh", "ios",
              frozenset({"pull", "refresh", "scroll", "ios"}),
              "Test pull-to-refresh interactions"),
]


def flows_for_platform(platform: str) -> list[FlowEntry]:
    """Return flows applicable to a platform (platform-specific + common)."""
    return [f for f in FLOW_LIBRARY if f.platform in (platform, "common")]
