# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""Configuration file handling for buildx."""

from pathlib import Path
import yaml

from colcon_core.logging import colcon_logger

from colcon_buildx.workspace import search_path

logger = colcon_logger.getChild(__name__)

# Looked for in this order in each directory; the first one found is used and
# the others are ignored.
CONFIG_NAMES = ('.buildx.conf', '.buildx.yml', '.buildx.yaml')


def find_config_file(config_path=None):
    """
    Find the configuration file.

    Searches in order:
    1. Provided path (--config argument)
    2. .buildx.conf, .buildx.yml, .buildx.yaml in the current directory
    3. The same names in each parent directory, stopping at the workspace
       root (the first directory with src/) or after MAX_LEVELS directories

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

    for directory in search_path():
        for name in CONFIG_NAMES:
            config_file = directory / name
            if config_file.exists():
                logger.debug(f"Found configuration file: {config_file}")
                return config_file

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
    return read_config_file(config_file)


def read_config_file(config_file):
    """
    Read one configuration file, choosing the format by its suffix.

    Args:
        config_file: Path to the file

    Returns:
        dict: Configuration dictionary, or None if the file could not be read
    """
    try:
        if config_file.suffix in ['.yml', '.yaml']:
            return load_yaml_config(config_file)
        else:
            return load_conf_config(config_file)
    except Exception as e:
        logger.warning(f"Failed to load config from {config_file}: {e}")
        return None


def normalize_key(key):
    """
    Spell a config key the way CONFIG_KEYS does.

    Both formats accept the flag's own spelling, so docker-image and
    docker_image are the same key.
    """
    return str(key).strip().replace('-', '_')


def load_yaml_config(config_file):
    """Load YAML configuration file."""
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise ValueError('expected "key: value" pairs at the top level')
    return {normalize_key(key): value for key, value in config.items()}


def load_conf_config(config_file):
    """
    Load simple key=value configuration file.

    Format:
        # Comments start with #
        key = value
        another_key = another value

    Keys with hyphens are converted to underscores (docker-image → docker_image)
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
                key = normalize_key(key)
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
