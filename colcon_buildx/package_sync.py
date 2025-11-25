"""
Package synchronization utilities for cross-compilation.

This module provides functionality to synchronize package versions between
a Docker image and a target device via SSH.
"""

import subprocess
import json
import re
import sys
from collections import deque
from datetime import datetime
from typing import Dict, Tuple, Set
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


def generate_sync_script(
    version_diffs: Dict[str, Tuple[PackageInfo, PackageInfo]],
    device_only_pkgs: Dict[str, PackageInfo] = None
) -> str:
    """
    Generate bash script to sync package versions in Docker container.

    Args:
        version_diffs: Dictionary of packages with version differences
        device_only_pkgs: Dictionary of packages only on device (to be installed)

    Returns:
        Bash script as string
    """
    device_only_pkgs = device_only_pkgs or {}

    if not version_diffs and not device_only_pkgs:
        return "echo 'No packages to sync'"

    # Build list of packages to version-match
    packages_to_upgrade = []
    for name, (device_pkg, _) in version_diffs.items():
        # Use exact version specification
        packages_to_upgrade.append(f"{name}={device_pkg.version}")

    # Build list of device-only packages (just names for availability check)
    device_only_names = list(device_only_pkgs.keys())

    # Build version mapping as bash variable (format: "pkg1|version1 pkg2|version2")
    version_map_entries = []
    for name, pkg_info in device_only_pkgs.items():
        version_map_entries.append(f"{name}|{pkg_info.version}")
    version_map_str = " ".join(version_map_entries)

    script = """#!/bin/bash
set -e

# Simple progress bar: [processed|remaining]
show_progress_bar() {
    local installed=$1
    local failed=$2
    local total=$3
    local width=40

    # Block characters array: ▏ ▎ ▍ ▌ ▋ ▊ ▉ █
    local -a BLOCKS=('▏' '▎' '▍' '▌' '▋' '▊' '▉' '█')

    # Calculate processed (installed + failed)
    local processed=$((installed + failed))

    # Calculate widths in eighths for smooth rendering
    local total_eighths=$((width * 8))
    local processed_eighths=$((processed * total_eighths / total))

    # Build processed bar (full blocks + partial)
    local processed_full=$((processed_eighths / 8))
    local processed_partial=$((processed_eighths % 8))

    local processed_bar=""
    local i
    for ((i=0; i<processed_full; i++)); do
        processed_bar="${processed_bar}${BLOCKS[7]}"
    done
    [ $processed_partial -gt 0 ] && processed_bar="${processed_bar}${BLOCKS[$((processed_partial-1))]}"

    # Calculate remaining
    local processed_chars=$((processed_full))
    [ $processed_partial -gt 0 ] && processed_chars=$((processed_chars + 1))
    local remaining_chars=$((width - processed_chars))
    local remaining_bar=$(printf '%*s' "$remaining_chars" '')

    # Simple output - no colors, just the bar
    printf "PROGRESS_BAR:[%s%s] %d/%d (%d ok %d fail)\\n" "$processed_bar" "$remaining_bar" "$processed" "$total" "$installed" "$failed"
}

echo "Updating package lists..."
apt-get update -qq

"""

    if packages_to_upgrade:
        upgrade_str = " ".join(packages_to_upgrade)
        script += f"""echo "Version-matching {len(packages_to_upgrade)} packages..."
DEBIAN_FRONTEND=noninteractive apt-get install -y --allow-downgrades {upgrade_str}

"""

    if device_only_names:
        # Generate script that checks availability before installing
        # Uses batch installation with fallback to individual packages on failure
        packages_list = " ".join(device_only_names)
        total_packages = len(device_only_names)
        script += f"""
echo "Checking availability of {total_packages} device-only packages..."
DEVICE_ONLY_PACKAGES="{packages_list}"
VERSION_MAP="{version_map_str}"
AVAILABLE_PACKAGES=""
UNAVAILABLE_PACKAGES=""
AVAILABLE_COUNT=0
UNAVAILABLE_COUNT=0
CHECKED_COUNT=0
TOTAL_COUNT={total_packages}

# Function to get version for a package from VERSION_MAP
get_version() {{
    local pkg=$1
    for entry in $VERSION_MAP; do
        IFS='|' read -r p v <<< "$entry"
        if [ "$p" = "$pkg" ]; then
            echo "$v"
            return
        fi
    done
    echo "unknown"
}}

for pkg in $DEVICE_ONLY_PACKAGES; do
    CHECKED_COUNT=$((CHECKED_COUNT + 1))
    if apt-cache show "$pkg" > /dev/null 2>&1; then
        AVAILABLE_PACKAGES="$AVAILABLE_PACKAGES $pkg"
        AVAILABLE_COUNT=$((AVAILABLE_COUNT + 1))
    else
        UNAVAILABLE_PACKAGES="$UNAVAILABLE_PACKAGES $pkg"
        UNAVAILABLE_COUNT=$((UNAVAILABLE_COUNT + 1))
        # Output with version
        PKG_VERSION=$(get_version "$pkg")
        echo "SYNC_UNAVAILABLE_PKG:$pkg|$PKG_VERSION"
    fi
    # Show progress bar
    show_progress_bar $AVAILABLE_COUNT $UNAVAILABLE_COUNT $TOTAL_COUNT
done

# Clear progress bar and show final result
printf "\\n"
echo "Availability check complete: $AVAILABLE_COUNT available, $UNAVAILABLE_COUNT unavailable"

if [ $UNAVAILABLE_COUNT -gt 0 ]; then
    echo "⚠ Skipping $UNAVAILABLE_COUNT unavailable packages (not in Docker repos)"
fi

if [ $AVAILABLE_COUNT -gt 0 ]; then
    echo "Installing $AVAILABLE_COUNT available device-only packages..."

    # Try bulk install first - fastest option
    set +e  # Don't exit on error
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $AVAILABLE_PACKAGES 2>&1
    BULK_RESULT=$?
    set -e

    if [ $BULK_RESULT -ne 0 ]; then
        echo "⚠ Bulk install failed, falling back to individual package installation..."
        FAILED_PACKAGES=""
        FAILED_COUNT=0
        INSTALLED_COUNT=0
        INSTALL_TOTAL=$AVAILABLE_COUNT

        # Don't exit on errors for individual package installation
        set +e

        SUCCESSFUL_COUNT=0

        for pkg in $AVAILABLE_PACKAGES; do
            PKG_VERSION=$(get_version "$pkg")
            INSTALL_OUTPUT=$(DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$pkg" 2>&1)
            INSTALL_RESULT=$?

            if [ $INSTALL_RESULT -ne 0 ]; then
                FAILED_PACKAGES="$FAILED_PACKAGES $pkg"
                FAILED_COUNT=$((FAILED_COUNT + 1))
                # Extract the error reason (last non-empty line or E: line)
                ERROR_REASON=$(echo "$INSTALL_OUTPUT" | grep -E "^E:|Unable to|has no installation|dependency|held|unmet" | tail -1 | sed 's/^E: //')
                if [ -z "$ERROR_REASON" ]; then
                    ERROR_REASON="Unknown error"
                fi
                # Output parseable marker for Python to capture (pkg|version|reason format)
                echo "SYNC_FAILED_PKG:$pkg|$PKG_VERSION|$ERROR_REASON"
            else
                SUCCESSFUL_COUNT=$((SUCCESSFUL_COUNT + 1))
                # Output marker for successfully installed package
                echo "SYNC_INSTALLED_PKG:$pkg|$PKG_VERSION"
            fi

            # Update progress bar
            show_progress_bar $SUCCESSFUL_COUNT $FAILED_COUNT $INSTALL_TOTAL
        done

        # Clear progress bar and show final result
        printf "\\n"

        # Re-enable exit on error for rest of script
        set -e

        if [ $FAILED_COUNT -gt 0 ]; then
            echo "⚠ Failed to install $FAILED_COUNT packages (unmet dependencies or virtual)"
            echo "SYNC_STATS:failed=$FAILED_COUNT,success=$((INSTALL_TOTAL - FAILED_COUNT))"
        fi

        SUCCESSFUL=$((INSTALL_TOTAL - FAILED_COUNT))
        echo "✓ Successfully installed $SUCCESSFUL packages"
    else
        echo "✓ Bulk install completed successfully"
    fi
else
    echo "No device-only packages available in Docker repos"
fi

"""

    script += """echo "Cleaning up..."
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
        base_image: Original image name (e.g., 'registry.com/ros:jazzy-base' or 'kv26:jazzy-base')

    Returns:
        New full image name with -synced-YYYYMMDD suffix (e.g., 'kv26:jazzy-base-synced-20251125')
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

    # Build dict of device-only packages for installation
    device_only_pkgs = {name: device_pkgs[name] for name in device_only}

    # Show info about packages
    if device_only:
        device_only_list = sorted(list(device_only))[:10]  # Show first 10
        more = len(device_only) - 10
        print(f"\nℹ Packages only on device (will install): {', '.join(device_only_list)}" +
              (f" ... and {more} more" if more > 0 else ""))

    if image_only:
        image_only_list = sorted(list(image_only))[:10]  # Show first 10
        more = len(image_only) - 10
        print(f"⚠ Packages only in image (ignored): {', '.join(image_only_list)}" +
              (f" ... and {more} more" if more > 0 else ""))

    if not version_diffs and not device_only:
        print(f"\n✓ All packages are already in sync!")
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
                "packages_installed": 0,
                "packages_image_only": len(image_only),
                "version_differences": 0
            }]
        }
        save_sync_manifest(metadata, manifest_path)

        return new_tag

    # Summary of what will happen
    if version_diffs:
        print(f"\nℹ Found {len(version_diffs)} packages with different versions (will upgrade)")
    if device_only:
        print(f"ℹ Found {len(device_only)} device-only packages (will install)")

    # Generate sync script with both version diffs and device-only packages
    sync_script = generate_sync_script(version_diffs, device_only_pkgs)

    # Run sync in a container and keep it running so we can commit
    print(f"\n🔄 Creating container and syncing packages...")

    # Use docker run with a name so we can commit it afterward
    # Run the sync script directly, container stays around after completion
    container_name = f"buildx-sync-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    try:
        # Run sync script in container (don't use --rm so we can commit)
        # Show filtered progress output
        print("📦 Installing synchronized packages (this may take a while with QEMU)...")

        process = subprocess.Popen(
            [
                'docker', 'run',
                '--name', container_name,
                '--platform', 'linux/arm64',
                base_image,
                'bash', '-c', sync_script
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',  # Replace invalid UTF-8 bytes
            bufsize=1  # Line buffered
        )

        # Keywords that indicate progress - show these lines
        progress_keywords = [
            'Updating package',
            'Version-matching',
            'Progress:',
            'Install progress:',
            'Availability check',
            'Skipping',
            'Installing',
            'Setting up',
            'Unpacking',
            'Cleaning up',
            'Package sync complete',
            'available',
            'unavailable',
            'Bulk install',
            'falling back',
            'Successfully installed',
            'Failed to install',
        ]

        last_output = []  # Keep last few lines for error reporting
        unavailable_packages = []  # [(pkg, version)]
        failed_packages = []  # [(pkg, version, reason)]
        installed_packages = []  # [(pkg, version)]
        sync_stats = {}  # Track install statistics

        try:
            for line in iter(process.stdout.readline, ''):
                if not line:
                    break
                line = line.rstrip()
                last_output.append(line)
                if len(last_output) > 20:
                    last_output.pop(0)

                # Parse special markers
                if line.startswith('SYNC_UNAVAILABLE_PKG:'):
                    data = line.split(':', 1)[1]
                    if '|' in data:
                        pkg, version = data.split('|', 1)
                        unavailable_packages.append((pkg, version))
                    continue
                elif line.startswith('SYNC_FAILED_PKG:'):
                    data = line.split(':', 1)[1]
                    parts = data.split('|')
                    if len(parts) >= 3:
                        pkg, version, reason = parts[0], parts[1], '|'.join(parts[2:])
                    elif len(parts) == 2:
                        pkg, version, reason = parts[0], parts[1], "Unknown error"
                    else:
                        pkg, version, reason = parts[0], "unknown", "Unknown error"
                    failed_packages.append((pkg, version, reason))
                    continue
                elif line.startswith('SYNC_INSTALLED_PKG:'):
                    data = line.split(':', 1)[1]
                    if '|' in data:
                        pkg, version = data.split('|', 1)
                        installed_packages.append((pkg, version))
                    continue
                elif line.startswith('SYNC_STATS:'):
                    # Parse stats like "failed=10,success=20"
                    stats_str = line.split(':', 1)[1]
                    for pair in stats_str.split(','):
                        k, v = pair.split('=')
                        sync_stats[k] = int(v)
                    continue

                # Handle progress bar lines
                if line.startswith('PROGRESS_BAR:'):
                    # Extract the progress bar content (after the marker)
                    bar_content = line[13:]  # Skip "PROGRESS_BAR:"
                    # Print with carriage return for in-place update
                    print(f'\r  {bar_content}', end='', flush=True)
                    continue
                # Show other lines that indicate progress
                elif any(kw in line for kw in progress_keywords):
                    # Clear any progress bar first, then show message
                    if line.strip():  # Only print non-empty lines
                        print('\r' + ' ' * 80 + '\r', end='')  # Clear line
                        # Truncate long lines
                        if len(line) > 100:
                            line = line[:97] + "..."
                        print(f"  {line}")
                        sys.stdout.flush()
                    else:
                        # Empty line - just clear the progress bar
                        print('\r' + ' ' * 80 + '\r')

            process.wait(timeout=3600)  # 60 minutes timeout

        except subprocess.TimeoutExpired:
            process.kill()
            raise

        if process.returncode != 0:
            print(f"❌ Package sync failed. Last output:")
            for line in last_output[-10:]:
                print(f"  {line}")
            raise RuntimeError("Package synchronization failed")

        # Calculate stats
        installed_count = len(installed_packages)
        failed_count = len(failed_packages)
        unavailable_count = len(unavailable_packages)

        # Summary message with actual stats
        if version_diffs:
            print(f"✓ Version-matched {len(version_diffs)} packages")
        if device_only:
            print(f"✓ Device-only packages: {installed_count} installed, {failed_count} failed, {unavailable_count} unavailable")

        # Save detailed log to cross_log directory
        log_dir = manifest_path.parent / 'cross_log'
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"sync-packages-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

        with open(log_file, 'w') as f:
            f.write(f"Package Sync Report\n")
            f.write(f"{'='*60}\n")
            f.write(f"Date: {datetime.now().isoformat()}\n")
            f.write(f"Device: {ssh_target}\n")
            f.write(f"Base Image: {base_image}\n\n")

            f.write(f"Summary:\n")
            f.write(f"  - Version-matched: {len(version_diffs)}\n")
            f.write(f"  - Device-only attempted: {len(device_only)}\n")
            f.write(f"  - Successfully installed: {installed_count}\n")
            f.write(f"  - Failed to install: {failed_count}\n")
            f.write(f"  - Unavailable in repos: {unavailable_count}\n\n")

            # Version-matched packages
            if version_diffs:
                f.write(f"Version-Matched Packages ({len(version_diffs)}):\n")
                f.write(f"{'='*60}\n")
                for name, (device_pkg, image_pkg) in sorted(version_diffs.items()):
                    f.write(f"  {name}:{image_pkg.version}->{device_pkg.version}\n")
                f.write("\n")

            # Successfully installed packages
            if installed_packages:
                f.write(f"Successfully Installed ({len(installed_packages)}):\n")
                f.write(f"{'='*60}\n")
                for pkg, version in sorted(installed_packages, key=lambda x: x[0]):
                    f.write(f"  {pkg}:{version}\n")
                f.write("\n")

            # Unavailable packages
            if unavailable_packages:
                f.write(f"Unavailable Packages ({len(unavailable_packages)}):\n")
                f.write(f"{'='*60}\n")
                for pkg, version in sorted(unavailable_packages, key=lambda x: x[0]):
                    f.write(f"  {pkg}:{version}\n")
                f.write("\n")

            # Failed packages with reasons
            if failed_packages:
                f.write(f"Failed Packages ({len(failed_packages)}):\n")
                f.write(f"{'='*60}\n")
                for pkg, version, reason in sorted(failed_packages, key=lambda x: x[0]):
                    f.write(f"  {pkg}:{version} - {reason}\n")
                f.write("\n")

        print(f"📝 Detailed sync log saved to: {log_file}")

        # Commit container to new image
        new_tag = generate_synced_tag(base_image)
        commit_synced_image(container_name, new_tag)

        # Save manifest with actual stats
        metadata = {
            "base_image": base_image,
            "synced_image": new_tag,
            "created_date": datetime.now().isoformat(),
            "sync_log": str(log_file),
            "operations": [{
                "type": "device-sync",
                "source": ssh_target,
                "timestamp": datetime.now().isoformat(),
                "packages_version_matched": len(version_diffs),
                "packages_device_only": len(device_only),
                "packages_installed": installed_count,
                "packages_failed": failed_count,
                "packages_unavailable": unavailable_count,
                "packages_image_only": len(image_only)
            }]
        }
        save_sync_manifest(metadata, manifest_path)

        print(f"\n{'='*60}")
        print(f"✓ Package sync complete!")
        print(f"✓ Created synced image: {new_tag}")
        print(f"{'='*60}\n")

        return new_tag

    except subprocess.TimeoutExpired:
        raise RuntimeError("Package sync timed out after 30 minutes")
    finally:
        # Clean up container
        subprocess.run(['docker', 'rm', '-f', container_name],
                      capture_output=True, check=False)
