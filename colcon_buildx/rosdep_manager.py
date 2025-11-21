"""
Rosdep integration for managing ROS dependencies in cross-compilation.

This module provides functionality to install ROS package dependencies
using rosdep in both Docker and SSHFS cross-compilation methods.
"""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Set, List
from datetime import datetime


def parse_workspace_deps(workspace_path: Path) -> Set[str]:
    """
    Parse package.xml files in workspace to find dependencies.

    Args:
        workspace_path: Path to workspace root (containing src/)

    Returns:
        Set of dependency package names
    """
    print(f"📋 Parsing workspace dependencies from {workspace_path}/src")

    src_dir = workspace_path / 'src'
    if not src_dir.exists():
        print(f"⚠ Warning: src directory not found at {src_dir}")
        return set()

    dependencies = set()
    package_count = 0

    # Find all package.xml files
    for package_xml in src_dir.rglob('package.xml'):
        package_count += 1
        try:
            tree = ET.parse(package_xml)
            root = tree.getroot()

            # Extract dependencies from various tags
            for dep_type in ['depend', 'build_depend', 'exec_depend',
                           'build_export_depend', 'buildtool_depend']:
                for dep in root.findall(dep_type):
                    if dep.text:
                        dependencies.add(dep.text.strip())

        except Exception as e:
            print(f"⚠ Warning: Failed to parse {package_xml}: {e}")
            continue

    print(f"✓ Found {len(dependencies)} unique dependencies across {package_count} packages")
    return dependencies


def install_deps_docker(
    image: str,
    workspace_path: Path,
    platform: str,
    rosdep_args: str = '--ignore-src -y'
) -> str:
    """
    Install ROS dependencies inside Docker container using rosdep.

    Args:
        image: Docker image to use as base
        workspace_path: Path to workspace root
        platform: Docker platform (e.g., linux/arm64)
        rosdep_args: Additional arguments for rosdep install

    Returns:
        New synced image tag with dependencies installed

    Raises:
        RuntimeError: If dependency installation fails
    """
    from colcon_buildx.package_sync import generate_synced_tag, commit_synced_image, save_sync_manifest

    print(f"\n{'='*60}")
    print(f"Installing ROS dependencies in Docker image...")
    print(f"{'='*60}\n")

    # Parse dependencies
    deps = parse_workspace_deps(workspace_path)
    if not deps:
        print("ℹ No dependencies found in workspace")
        # Still create synced tag to mark rosdep was run
        new_tag = generate_synced_tag(image)
        subprocess.run(['docker', 'tag', image, new_tag], check=True, capture_output=True)
        return new_tag

    # Create installation script
    install_script = f"""#!/bin/bash
set -e

echo "Initializing rosdep..."
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
    rosdep init || true
fi
rosdep update

echo "Installing workspace dependencies..."
cd /workspace
rosdep install --from-paths src {rosdep_args}

echo "Cleaning up..."
apt-get clean
rm -rf /var/lib/apt/lists/*

echo "Dependencies installed successfully!"
"""

    print("🔄 Creating temporary container to install dependencies...")

    # Create container with workspace mounted
    create_cmd = [
        'docker', 'create',
        '--platform', platform,
        '-v', f'{workspace_path}:/workspace:ro',
        image,
        'bash', '-c', install_script
    ]

    try:
        result = subprocess.run(create_cmd, capture_output=True, text=True, check=True)
        container_id = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to create container: {e.stderr}")

    try:
        # Start container
        subprocess.run(['docker', 'start', container_id], check=True, capture_output=True)

        # Run installation
        print("📦 Running rosdep install...")
        exec_result = subprocess.run(
            ['docker', 'exec', container_id, 'bash', '-c', install_script],
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes timeout
        )

        if exec_result.returncode != 0:
            print(f"❌ Dependency installation failed:")
            print(exec_result.stderr)
            raise RuntimeError("rosdep install failed")

        # Show relevant output
        for line in exec_result.stdout.split('\n'):
            if 'Installing' in line or 'installed' in line or 'already installed' in line:
                print(f"  {line}")

        print(f"✓ Successfully installed workspace dependencies")

        # Commit container to new synced image
        new_tag = generate_synced_tag(image)
        commit_synced_image(container_id, new_tag)

        # Update manifest
        manifest_path = workspace_path / '.buildx-sync-manifest.json'
        metadata = {
            "base_image": image,
            "synced_image": new_tag,
            "created_date": datetime.now().isoformat(),
            "operations": [{
                "type": "rosdep",
                "timestamp": datetime.now().isoformat(),
                "dependencies_found": len(deps),
                "rosdep_args": rosdep_args
            }]
        }
        save_sync_manifest(metadata, manifest_path)

        print(f"\n{'='*60}")
        print(f"✓ Dependencies installed!")
        print(f"✓ Created synced image: {new_tag}")
        print(f"{'='*60}\n")

        return new_tag

    except subprocess.TimeoutExpired:
        raise RuntimeError("rosdep install timed out after 10 minutes")
    finally:
        # Clean up container
        subprocess.run(['docker', 'rm', '-f', container_id],
                      capture_output=True, check=False)


def install_deps_sshfs(
    ssh_target: str,
    workspace_path: Path,
    rosdep_args: str = '--ignore-src -y'
) -> bool:
    """
    Install ROS dependencies on remote device via SSH using rosdep.

    Args:
        ssh_target: SSH connection string (e.g., 'ubuntu@192.168.1.100')
        workspace_path: Local path to workspace root
        rosdep_args: Additional arguments for rosdep install

    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Installing ROS dependencies on device {ssh_target}...")
    print(f"{'='*60}\n")

    # Parse dependencies locally
    deps = parse_workspace_deps(workspace_path)
    if not deps:
        print("ℹ No dependencies found in workspace")
        return True

    # We need to copy the src directory to the device temporarily
    # to let rosdep analyze the dependencies
    print(f"📤 Copying workspace src to device for analysis...")

    # Create remote temp directory
    temp_dir_cmd = ['ssh', ssh_target, 'mktemp -d']
    try:
        result = subprocess.run(temp_dir_cmd, capture_output=True, text=True, check=True, timeout=10)
        remote_temp = result.stdout.strip()
        print(f"✓ Created temporary directory: {remote_temp}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"❌ Failed to create temporary directory on device: {e}")
        return False

    try:
        # Copy src directory to device
        src_dir = workspace_path / 'src'
        rsync_cmd = [
            'rsync', '-az', '--delete',
            f'{src_dir}/',
            f'{ssh_target}:{remote_temp}/src/'
        ]

        print(f"  Syncing {src_dir} -> {ssh_target}:{remote_temp}/src")
        rsync_result = subprocess.run(rsync_cmd, capture_output=True, text=True, timeout=120)
        if rsync_result.returncode != 0:
            print(f"❌ Failed to sync workspace to device: {rsync_result.stderr}")
            return False

        print(f"✓ Workspace synced to device")

        # Run rosdep install on device
        print(f"📦 Running rosdep install on device...")

        rosdep_cmd = f"""
cd {remote_temp}
echo "Initializing rosdep..."
if [ ! -f /etc/ros/rosdep/sources.list.d/20-default.list ]; then
    sudo rosdep init || true
fi
rosdep update

echo "Installing dependencies..."
rosdep install --from-paths src {rosdep_args}
"""

        ssh_cmd = ['ssh', ssh_target, 'bash', '-c', rosdep_cmd]

        install_result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes timeout
        )

        if install_result.returncode != 0:
            print(f"❌ rosdep install failed on device:")
            print(install_result.stderr)
            return False

        # Show relevant output
        for line in install_result.stdout.split('\n'):
            if 'Installing' in line or 'installed' in line or 'already installed' in line:
                print(f"  {line}")

        print(f"\n{'='*60}")
        print(f"✓ Successfully installed dependencies on device")
        print(f"{'='*60}\n")

        return True

    except subprocess.TimeoutExpired:
        print(f"❌ Dependency installation timed out after 10 minutes")
        return False
    except Exception as e:
        print(f"❌ Error during dependency installation: {e}")
        return False
    finally:
        # Clean up remote temp directory
        cleanup_cmd = ['ssh', ssh_target, f'rm -rf {remote_temp}']
        subprocess.run(cleanup_cmd, capture_output=True, check=False, timeout=10)


def check_rosdep_installed(ssh_target: str = None) -> bool:
    """
    Check if rosdep is installed (locally or on remote device).

    Args:
        ssh_target: Optional SSH target to check remote device. If None, checks locally.

    Returns:
        True if rosdep is available, False otherwise
    """
    if ssh_target:
        check_cmd = ['ssh', ssh_target, 'which', 'rosdep']
    else:
        check_cmd = ['which', 'rosdep']

    try:
        result = subprocess.run(check_cmd, capture_output=True, timeout=5)
        return result.returncode == 0
    except:
        return False
