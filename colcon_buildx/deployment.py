# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""Deployment utilities for buildx."""

import subprocess
from pathlib import Path

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)


def deploy(install_dir, target, workspace_root=None):
    """
    Deploy build artifacts to target board via rsync.

    Args:
        install_dir: Local install directory to deploy; a relative path is
            taken relative to *workspace_root*, where the builders put it
        target: Deployment target in format user@host:/path/to/install
        workspace_root: Workspace root; the current directory if not given

    Returns:
        int: Exit code (0 for success)
    """
    # Resolving against the current directory instead missed the install
    # directory whenever colcon buildx ran from below the workspace root.
    install_path = Path(workspace_root or Path.cwd()) / install_dir

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
        subprocess.run(cmd, check=True)
        logger.info("✓ Deployment successful")
        return 0
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Deployment failed with exit code {e.returncode}")
        logger.error("💡 Ensure SSH access works and target path exists")
        return e.returncode
    except FileNotFoundError:
        logger.error("❌ rsync not found")
        logger.error("💡 Install rsync: brew install rsync (macOS) or apt install rsync (Linux)")
        return 1
