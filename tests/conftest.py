"""Make the extension importable where colcon itself is not installed."""

import logging
import sys
import types

try:
    import colcon_core  # noqa: F401
except ImportError:
    # Only the few names the extension imports at module level are needed.
    core = types.ModuleType('colcon_core')
    core_logging = types.ModuleType('colcon_core.logging')
    core_logging.colcon_logger = logging.getLogger('colcon')
    plugin_system = types.ModuleType('colcon_core.plugin_system')
    plugin_system.satisfies_version = lambda *args, **kwargs: None
    verb = types.ModuleType('colcon_core.verb')

    class VerbExtensionPoint:
        EXTENSION_POINT_VERSION = '1.0'

    verb.VerbExtensionPoint = VerbExtensionPoint
    sys.modules.update({
        'colcon_core': core,
        'colcon_core.logging': core_logging,
        'colcon_core.plugin_system': plugin_system,
        'colcon_core.verb': verb,
    })
