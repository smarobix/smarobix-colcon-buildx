"""Deployment utilities for buildx."""

import subprocess
from pathlib import Path

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)


def deploy(install_dir, target):
    """
    Deploy build artifacts to target board via rsync.

    Args:
        install_dir: Local install directory to deploy
        target: Deployment target in format user@host:/path/to/install

    Returns:
        int: Exit code (0 for success)
    """
    install_path = Path(install_dir)

    if not install_path.exists():
        logger.error(f"❌ Install directory not found: {install_path}")
        return 1

    # Ensure target ends with / for rsync directory sync
    if not target.endswith('/'):
        target += '/'

    logger.info(f"📤 Deploying {install_path} to {target}")

    cmd = [
        'rsync',
        '-avz',
        '--delete',
        f'{install_path}/',
        target
    ]

    try:
        result = subprocess.run(cmd, check=True)
        logger.info(f"✓ Deployment successful")
        return 0
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Deployment failed with exit code {e.returncode}")
        logger.error("💡 Ensure SSH access works and target path exists")
        return e.returncode
    except FileNotFoundError:
        logger.error("❌ rsync not found")
        logger.error("💡 Install rsync: brew install rsync (macOS) or apt install rsync (Linux)")
        return 1
