# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""
The local image copies --install-deps makes: their tag, commit and manifest.

The device sync that used to live here (--sync-from-device) is gone: it ran the
board's package versions into the image under emulation, and colcon buildx no
longer emulates. Dependencies belong in the board image itself.
"""

import subprocess
import json
import re
from datetime import datetime
from pathlib import Path


def commit_synced_image(container_id: str, new_tag: str) -> None:
    """
    Commit a container to a new Docker image tag.

    Args:
        container_id: Docker container ID
        new_tag: New image tag to create

    Raises:
        subprocess.CalledProcessError: If commit fails
    """
    print(f"💾 Committing container to image: {new_tag}...")

    cmd = ['docker', 'commit', container_id, new_tag]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        print(f"✓ Created synced image: {new_tag}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Docker commit timed out")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to commit image: {e.stderr}")


def save_sync_manifest(
    metadata: dict,
    manifest_path: Path
) -> None:
    """
    Save synchronization metadata to JSON file.

    Args:
        metadata: Dictionary containing sync metadata
        manifest_path: Path to manifest file
    """
    try:
        # Load existing manifest if it exists
        if manifest_path.exists():
            with open(manifest_path, 'r') as f:
                existing = json.load(f)
            # Append to operations list if same image
            if existing.get('synced_image') == metadata.get('synced_image'):
                if 'operations' in existing:
                    metadata['operations'] = existing['operations'] + metadata.get('operations', [])

        with open(manifest_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"✓ Saved sync manifest to {manifest_path}")
    except Exception as e:
        print(f"⚠ Warning: Failed to save manifest: {e}")


def generate_synced_tag(base_image: str) -> str:
    """
    Generate a synced image tag from base image name.

    Args:
        base_image: Original image name, e.g.
            'ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy'

    Returns:
        New full image name with a -synced-YYYYMMDD suffix, e.g.
        'ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy-synced-20260922'
    """
    # Extract repository and tag portions
    if ':' in base_image:
        repository, base_tag = base_image.rsplit(':', 1)
    else:
        repository = None
        base_tag = base_image

    # Remove existing -synced-* suffix if present
    base_tag = re.sub(r'-synced-\d{8}$', '', base_tag)

    # Add new synced suffix with current date
    date_str = datetime.now().strftime('%Y%m%d')
    synced_tag = f"{base_tag}-synced-{date_str}"

    # Return full image name with repository
    if repository:
        return f"{repository}:{synced_tag}"
    else:
        return synced_tag
