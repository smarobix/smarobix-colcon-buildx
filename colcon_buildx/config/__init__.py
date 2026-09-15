"""Configuration file handling for buildx."""

import os
from pathlib import Path
import yaml

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)


def find_config_file(config_path=None):
    """
    Find the configuration file.

    Searches in order:
    1. Provided path (--config argument)
    2. .buildx.conf in current directory
    3. .buildx.yml / .buildx.yaml in current directory
    4. Same files in parent directories (up to workspace root with src/)

    Args:
        config_path: Optional explicit path to config file

    Returns:
        Path to config file or None if not found
    """
    if config_path:
        path = Path(config_path)
        if path.exists():
            return path
        logger.warning(f"Specified config file not found: {config_path}")
        return None

    # Search for config file in current directory and parents
    current = Path.cwd()
    config_names = ['.buildx.conf', '.buildx.yml', '.buildx.yaml']

    for _ in range(5):  # Search up to 5 levels
        for name in config_names:
            config_file = current / name
            if config_file.exists():
                logger.debug(f"Found configuration file: {config_file}")
                return config_file

        # Check if we're at workspace root (has src/ directory)
        if (current / 'src').is_dir():
            break

        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    return None


def load_config(config_path=None):
    """
    Load configuration from file.

    Supports both YAML (.yml, .yaml) and simple key=value format (.conf).

    Args:
        config_path: Optional path to config file

    Returns:
        dict: Configuration dictionary or None if no config found
    """
    config_file = find_config_file(config_path)
    if not config_file:
        return None

    try:
        if config_file.suffix in ['.yml', '.yaml']:
            return load_yaml_config(config_file)
        else:
            return load_conf_config(config_file)
    except Exception as e:
        logger.warning(f"Failed to load config from {config_file}: {e}")
        return None


def load_yaml_config(config_file):
    """Load YAML configuration file."""
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    return config or {}


def load_conf_config(config_file):
    """
    Load simple key=value configuration file.

    Format:
        # Comments start with #
        key = value
        another_key = another value

    Keys with hyphens are converted to underscores (--docker-image → docker_image)
    """
    config = {}
    with open(config_file, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip().replace('-', '_')  # Convert --arg-name to arg_name
                value = value.strip()

                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                # Convert boolean strings
                if value.lower() in ['true', 'yes', '1']:
                    value = True
                elif value.lower() in ['false', 'no', '0']:
                    value = False

                config[key] = value

    return config


def merge_settings(args, config, defaults, known_keys=None):
    """
    Resolve settings with precedence: command line > config file > defaults.

    Every option is declared with ``default=None`` so that "not supplied on the
    command line" is unambiguous. Anything still ``None`` after parsing falls
    through to the config file, and then to *defaults*.

    Inferring it instead -- treating any falsy value as "not supplied" -- drops
    every config key whose flag carries an argparse default, which is what this
    replaces.

    Args:
        args: Parsed argparse namespace, mutated in place
        config: Configuration dictionary (may be None)
        defaults: Mapping of setting name to fallback value
        known_keys: Recognised config keys; anything else is reported back

    Returns:
        list: Config keys that were not recognised, in file order
    """
    unknown = []

    for key, value in (config or {}).items():
        if known_keys is not None and key not in known_keys:
            unknown.append(key)
            continue
        if getattr(args, key, None) is None:
            setattr(args, key, value)

    for key, value in defaults.items():
        if getattr(args, key, None) is None:
            setattr(args, key, value)

    return unknown
