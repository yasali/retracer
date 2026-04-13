"""Platform abstraction — data-driven config per target ecosystem.

Inspired by Graphify's LanguageConfig pattern: instead of scattering
platform-specific logic across every module, each platform is described
by a single PlatformConfig. The generic pipeline works against this
interface. Adding a new platform = defining a new config + handler functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Protocol

if TYPE_CHECKING:
    from pathlib import Path


class DeviceInfo(Protocol):
    """Minimal device/simulator info returned by discovery."""

    @property
    def device_id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def is_booted(self) -> bool: ...


@dataclass(frozen=True)
class PlatformConfig:
    """Data-driven platform descriptor.

    Every platform-specific behaviour is declared here as config or
    as a pluggable callable. The pipeline code never checks
    `if platform == "ios"` — it calls these functions.
    """

    name: str
    display_name: str
    default_automation: str  # "maestro", "xcuitest", "appium", "playwright"
    flow_extensions: tuple[str, ...] = (".yaml",)
    flow_dirs: tuple[str, ...] = ("flows/maestro/common",)

    # Callable hooks — platform provides implementations
    discover_devices: Callable[[], list[dict]] | None = None
    install_app: Callable[..., bool] | None = None
    launch_app: Callable[..., bool] | None = None
    capture_screenshot: Callable[..., Path] | None = None
    check_app_running: Callable[..., bool] | None = None

    # Preflight requirements
    required_tools: tuple[str, ...] = ()
    supports_simulator: bool = False
    supports_real_device: bool = False

    # Extra metadata for extensibility
    metadata: dict = field(default_factory=dict)


# Registry of known platforms
_PLATFORMS: dict[str, PlatformConfig] = {}


def register_platform(config: PlatformConfig) -> PlatformConfig:
    """Register a platform config in the global registry."""
    _PLATFORMS[config.name] = config
    return config


def get_platform(name: str) -> PlatformConfig:
    """Look up a registered platform by name."""
    if name not in _PLATFORMS:
        available = ", ".join(_PLATFORMS.keys()) or "(none)"
        raise ValueError(f"Unknown platform: {name!r}. Available: {available}")
    return _PLATFORMS[name]


def available_platforms() -> list[str]:
    """Return names of all registered platforms."""
    return list(_PLATFORMS.keys())
