"""
Package synchronization utilities for cross-compilation.

This module provides functionality to synchronize package versions between
a Docker image and a target device via SSH.
"""

import subprocess
import json
import re
from datetime import datetime
from typing import Dict, Tuple, List, Set
from pathlib import Path


class PackageInfo:
    """Represents a package with its version information."""

    def __init__(self, name: str, version: str, arch: str = ""):
        self.name = name
        self.version = version
        self.arch = arch

    def __repr__(self):
        return f"{self.name}={self.version}" + (f":{self.arch}" if self.arch else "")


def extract_device_packages(ssh_target: str) -> Dict[str, PackageInfo]:
    """
    Extract installed packages from target device via SSH.

    Args:
        ssh_target: SSH connection string (e.g., 'ubuntu@192.168.1.100')

    Returns:
        Dictionary mapping package names to PackageInfo objects

    Raises:
        subprocess.CalledProcessError: If SSH connection fails
    """
    print(f"📦 Extracting package list from device {ssh_target}...")

    # Pass the entire command as a single string to SSH
    # SSH will execute it in a shell on the remote side
    remote_cmd = "dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n'"
    cmd = ['ssh', ssh_target, remote_cmd]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"SSH connection to {ssh_target} timed out")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to connect to {ssh_target}: {e.stderr}")

    packages = {}
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) >= 2:
            name = parts[0]
            version = parts[1]
            arch = parts[2] if len(parts) > 2 else ""
            packages[name] = PackageInfo(name, version, arch)

    print(f"✓ Found {len(packages)} packages on device")
    return packages


def extract_image_packages(image: str) -> Dict[str, PackageInfo]:
    """
    Extract installed packages from Docker image.

    Args:
        image: Docker image name/tag

    Returns:
        Dictionary mapping package names to PackageInfo objects

    Raises:
        subprocess.CalledProcessError: If Docker command fails
    """
    print(f"📦 Extracting package list from image {image}...")

    cmd = [
        'docker', 'run', '--rm', '--platform', 'linux/arm64',
        image,
        'dpkg-query', '-W', '-f=${Package}\t${Version}\t${Architecture}\n'
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Docker command timed out for image {image}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to query packages in image {image}: {e.stderr}")

    packages = {}
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) >= 2:
            name = parts[0]
            version = parts[1]
            arch = parts[2] if len(parts) > 2 else ""
            packages[name] = PackageInfo(name, version, arch)

    print(f"✓ Found {len(packages)} packages in image")
    return packages


def compare_packages(
    device_pkgs: Dict[str, PackageInfo],
    image_pkgs: Dict[str, PackageInfo]
) -> Tuple[Dict[str, Tuple[PackageInfo, PackageInfo]], Set[str], Set[str]]:
    """
    Compare packages between device and image.

    Args:
        device_pkgs: Packages from device
        image_pkgs: Packages from image

    Returns:
        Tuple of:
        - Dict of common packages with version differences (pkg_name -> (device_ver, image_ver))
        - Set of package names only on device
        - Set of package names only in image
    """
    device_names = set(device_pkgs.keys())
    image_names = set(image_pkgs.keys())

    common_names = device_names & image_names
    device_only = device_names - image_names
    image_only = image_names - common_names

    # Find common packages with different versions
    version_diffs = {}
    for name in common_names:
        device_pkg = device_pkgs[name]
        image_pkg = image_pkgs[name]
        if device_pkg.version != image_pkg.version:
            version_diffs[name] = (device_pkg, image_pkg)

    return version_diffs, device_only, image_only


def generate_sync_script(version_diffs: Dict[str, Tuple[PackageInfo, PackageInfo]]) -> str:
    """
    Generate bash script to sync package versions in Docker container.

    Args:
        version_diffs: Dictionary of packages with version differences

    Returns:
        Bash script as string
    """
    if not version_diffs:
        return "echo 'No packages to sync'"

    # Group packages to avoid apt conflicts
    packages_to_install = []
    for name, (device_pkg, image_pkg) in version_diffs.items():
        # Use exact version specification
        packages_to_install.append(f"{name}={device_pkg.version}")

    script = """#!/bin/bash
set -e

echo "Updating package lists..."
apt-get update -qq

echo "Syncing package versions..."
DEBIAN_FRONTEND=noninteractive apt-get install -y --allow-downgrades \\
"""

    # Add packages with proper escaping and line continuation
    for i, pkg in enumerate(packages_to_install):
        if i == len(packages_to_install) - 1:
            script += f"    \"{pkg}\"\n"
        else:
            script += f"    \"{pkg}\" \\\\\n"

    script += """
echo "Cleaning up..."
apt-get clean
rm -rf /var/lib/apt/lists/*

echo "Package sync complete!"
"""

    return script


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
        raise RuntimeError(f"Docker commit timed out")
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
        base_image: Original image name (e.g., 'registry.com/ros:jazzy-base')

    Returns:
        New tag with -synced-YYYYMMDD suffix (e.g., 'jazzy-base-synced-20250120')
    """
    # Extract just the tag portion after last colon
    if ':' in base_image:
        base_tag = base_image.split(':')[-1]
    else:
        base_tag = base_image

    # Remove existing -synced-* suffix if present
    base_tag = re.sub(r'-synced-\d{8}$', '', base_tag)

    # Add new synced suffix with current date
    date_str = datetime.now().strftime('%Y%m%d')
    return f"{base_tag}-synced-{date_str}"


def sync_packages_from_device(
    base_image: str,
    ssh_target: str,
    manifest_path: Path
) -> str:
    """
    Main function to sync packages from device to Docker image.

    Args:
        base_image: Base Docker image to sync
        ssh_target: SSH target for device connection
        manifest_path: Path to save manifest

    Returns:
        New synced image tag

    Raises:
        RuntimeError: If sync process fails
    """
    print(f"\n{'='*60}")
    print(f"Syncing packages from device {ssh_target}...")
    print(f"{'='*60}\n")

    # Extract package lists
    device_pkgs = extract_device_packages(ssh_target)
    image_pkgs = extract_image_packages(base_image)

    # Compare packages
    version_diffs, device_only, image_only = compare_packages(device_pkgs, image_pkgs)

    # Show warnings for divergent packages
    if device_only:
        device_only_list = sorted(list(device_only))[:10]  # Show first 10
        more = len(device_only) - 10
        print(f"\n⚠ Packages only on device (ignored): {', '.join(device_only_list)}" +
              (f" ... and {more} more" if more > 0 else ""))

    if image_only:
        image_only_list = sorted(list(image_only))[:10]  # Show first 10
        more = len(image_only) - 10
        print(f"⚠ Packages only in image (ignored): {', '.join(image_only_list)}" +
              (f" ... and {more} more" if more > 0 else ""))

    if not version_diffs:
        print(f"\n✓ All {len(device_pkgs & image_pkgs)} common packages are already in sync!")
        new_tag = generate_synced_tag(base_image)
        # Still create the tag to mark it as synced
        print(f"ℹ Creating synced image tag anyway: {new_tag}")

        # Just tag the existing image
        subprocess.run(
            ['docker', 'tag', base_image, new_tag],
            check=True,
            capture_output=True
        )

        # Save manifest
        metadata = {
            "base_image": base_image,
            "synced_image": new_tag,
            "created_date": datetime.now().isoformat(),
            "operations": [{
                "type": "device-sync",
                "source": ssh_target,
                "timestamp": datetime.now().isoformat(),
                "packages_synced": 0,
                "packages_device_only": len(device_only),
                "packages_image_only": len(image_only),
                "version_differences": 0
            }]
        }
        save_sync_manifest(metadata, manifest_path)

        return new_tag

    print(f"\nℹ Found {len(version_diffs)} packages with different versions")

    # Generate sync script
    sync_script = generate_sync_script(version_diffs)

    # Create temporary container and run sync script
    print(f"\n🔄 Creating temporary container to sync packages...")

    # Start container
    container_create = subprocess.run(
        ['docker', 'create', '--platform', 'linux/arm64', base_image, 'bash', '-c', sync_script],
        capture_output=True,
        text=True,
        check=True
    )
    container_id = container_create.stdout.strip()

    try:
        # Copy sync script into container
        script_process = subprocess.Popen(
            ['docker', 'exec', '-i', container_id, 'bash', '-c',
             'cat > /tmp/sync.sh && chmod +x /tmp/sync.sh'],
            stdin=subprocess.PIPE
        )
        script_process.communicate(input=sync_script.encode())

        # Start container
        subprocess.run(['docker', 'start', container_id], check=True, capture_output=True)

        # Run sync script
        print("📦 Installing synchronized packages...")
        exec_result = subprocess.run(
            ['docker', 'exec', container_id, 'bash', '/tmp/sync.sh'],
            capture_output=True,
            text=True,
            timeout=300
        )

        if exec_result.returncode != 0:
            print(f"❌ Package sync failed:")
            print(exec_result.stderr)
            raise RuntimeError("Package synchronization failed")

        print(f"✓ Synced {len(version_diffs)} packages to match device versions")

        # Commit container to new image
        new_tag = generate_synced_tag(base_image)
        commit_synced_image(container_id, new_tag)

        # Save manifest
        metadata = {
            "base_image": base_image,
            "synced_image": new_tag,
            "created_date": datetime.now().isoformat(),
            "operations": [{
                "type": "device-sync",
                "source": ssh_target,
                "timestamp": datetime.now().isoformat(),
                "packages_synced": len(version_diffs),
                "packages_device_only": len(device_only),
                "packages_image_only": len(image_only)
            }]
        }
        save_sync_manifest(metadata, manifest_path)

        print(f"\n{'='*60}")
        print(f"✓ Package sync complete!")
        print(f"✓ Created synced image: {new_tag}")
        print(f"{'='*60}\n")

        return new_tag

    finally:
        # Clean up container
        subprocess.run(['docker', 'rm', '-f', container_id],
                      capture_output=True, check=False)
