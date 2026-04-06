"""Feature module registry.

Central place to register all feature modules. The pipeline iterates
this registry to compute the full feature vector for each date.
"""

from __future__ import annotations

from clickhouse_connect.driver import Client

from dataplat.algo.features.base import FeatureModule

# Registry: module_name → class
FEATURE_REGISTRY: dict[str, type[FeatureModule]] = {}


def register(cls: type[FeatureModule]) -> type[FeatureModule]:
    """Decorator to register a feature module."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} must define a 'name' class attribute")
    FEATURE_REGISTRY[cls.name] = cls
    return cls


def get_all_modules(client: Client) -> list[FeatureModule]:
    """Instantiate all registered feature modules with the given client."""
    # Import submodules to trigger @register decorators
    import dataplat.algo.features.cross_asset  # noqa: F401
    import dataplat.algo.features.equity  # noqa: F401
    import dataplat.algo.features.macro  # noqa: F401
    import dataplat.algo.features.options  # noqa: F401

    return [cls(client) for cls in FEATURE_REGISTRY.values()]
