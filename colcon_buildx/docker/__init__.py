"""Docker-based cross-compilation builder."""

import os
import subprocess
import re
from pathlib import Path
from datetime import datetime

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)


class DockerBuilder:
    """Handles cross-compilation using Docker containers."""

    def __init__(self, image, platform, build_base, install_base, use_base_image=False):
        """
        Initialize Docker builder.

        Args:
            image: Docker image for cross-compilation
            platform: Target platform (e.g., linux/arm64)
            build_base: Build directory
            install_base: Install directory
            use_base_image: Force use of base image, skip synced image detection
        """
        self.base_image = image
        self.platform = platform
        self.build_base = build_base
        self.install_base = install_base
        self.workspace_root = self._find_workspace_root()
        self.container_name = 'colcon-buildx-builder'
        self.use_base_image = use_base_image

        # Detect synced image if not forcing base
        if not use_base_image:
            self.image = self.detect_synced_image()
        else:
            self.image = self.base_image

    def _find_workspace_root(self):
        """Find the workspace root by looking for src/ directory."""
        current = Path.cwd()
        for _ in range(5):
            if (current / 'src').is_dir():
                return current
            parent = current.parent
            if parent == current:
                break
            current = parent
        return Path.cwd()

    def detect_synced_image(self):
        """
        Detect if a synced version of the base image exists locally.

        Returns:
            Synced image name if found, otherwise base image name
        """
        # Extract base tag from full image name
        if ':' in self.base_image:
            registry_and_repo, base_tag = self.base_image.rsplit(':', 1)
        else:
            registry_and_repo = self.base_image
            base_tag = 'latest'

        # Remove any existing -synced-YYYYMMDD suffix
        base_tag_clean = re.sub(r'-synced-\d{8}$', '', base_tag)

        # Search for synced images matching pattern
        pattern = f"{base_tag_clean}-synced-*"

        logger.debug(f"🔍 Searching for synced images...")
        logger.debug(f"   Base image: {self.base_image}")
        logger.debug(f"   Registry/repo: {registry_and_repo}")
        logger.debug(f"   Base tag: {base_tag}")
        logger.debug(f"   Clean tag: {base_tag_clean}")
        logger.debug(f"   Pattern: {pattern}")

        try:
            result = subprocess.run(
                ['docker', 'images', '--format', '{{.Repository}}:{{.Tag}}'],
                capture_output=True,
                text=True,
                check=True
            )

            synced_images = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                # Check if this image matches our pattern
                if ':' in line:
                    repo, tag = line.rsplit(':', 1)
                    # Match against base tag pattern
                    regex_pattern = f"{re.escape(base_tag_clean)}-synced-\\d{{8}}$"
                    is_match = re.match(regex_pattern, tag)

                    logger.debug(f"   Checking: {line} → repo={repo}, tag={tag}, pattern={regex_pattern}, match={bool(is_match)}")

                    if is_match:
                        synced_images.append((tag, line))

            if synced_images:
                # Sort by date (newest first)
                synced_images.sort(reverse=True, key=lambda x: x[0])
                newest_tag, newest_image = synced_images[0]

                # Extract date from tag
                date_match = re.search(r'-synced-(\d{8})$', newest_tag)
                date_str = date_match.group(1) if date_match else 'unknown'

                # Format date nicely for display
                try:
                    date_obj = datetime.strptime(date_str, '%Y%m%d')
                    formatted_date = date_obj.strftime('%Y-%m-%d')
                except:
                    formatted_date = date_str

                print(f"ℹ️  Using synced image: {newest_image}")
                print(f"   Synced on: {formatted_date}")
                logger.info(f"ℹ️  Run with --use-base-image to use original base image instead")

                return newest_image

        except subprocess.CalledProcessError as e:
            logger.debug(f"Failed to list docker images: {e}")
            pass

        # No synced image found
        print(f"ℹ️  Using base image: {self.base_image}")
        logger.info(f"ℹ️  Run --sync-from-device <target> to create synced version")
        return self.base_image

    def create_synced_image(self, ssh_target):
        """
        Create a synced version of the base image from target device.

        Args:
            ssh_target: SSH connection string (e.g., 'ubuntu@192.168.1.100')

        Returns:
            New synced image tag, or None if sync failed
        """
        from colcon_buildx.package_sync import sync_packages_from_device

        manifest_path = self.workspace_root / '.buildx-sync-manifest.json'

        try:
            synced_tag = sync_packages_from_device(
                self.base_image,
                ssh_target,
                manifest_path
            )
            return synced_tag
        except Exception as e:
            logger.error(f"❌ Failed to sync packages: {e}")
            return None

    def install_dependencies(self, rosdep_args='--ignore-src -y'):
        """
        Install workspace dependencies using rosdep.

        Args:
            rosdep_args: Additional arguments for rosdep install

        Returns:
            New synced image tag with dependencies installed, or None if failed
        """
        from colcon_buildx.rosdep_manager import install_deps_docker

        try:
            # Use current image (could be base or already synced)
            updated_tag = install_deps_docker(
                self.image,
                self.workspace_root,
                self.platform,
                rosdep_args
            )
            return updated_tag
        except Exception as e:
            logger.error(f"❌ Failed to install dependencies: {e}")
            return None

    def check_docker(self):
        """Check if Docker is available and running."""
        try:
            result = subprocess.run(['docker', 'info'], capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError:
            logger.error("❌ Docker daemon is not running")
            logger.error("💡 Start Docker Desktop or run: sudo systemctl start docker")
            return False
        except FileNotFoundError:
            logger.error("❌ Docker not found")
            logger.error("💡 Install Docker: https://docs.docker.com/get-docker/")
            return False

    def check_image_exists(self):
        """Check if the Docker image exists locally or can be pulled."""
        logger.info(f"🔍 Checking for Docker image: {self.image}")

        # Try to inspect the image
        result = subprocess.run(
            ['docker', 'image', 'inspect', self.image],
            capture_output=True,
            text=True
        )

        logger.debug(f"   docker inspect return code: {result.returncode}")
        if result.returncode != 0:
            logger.debug(f"   stderr: {result.stderr}")
            logger.debug(f"   stdout: {result.stdout}")

        if result.returncode == 0:
            print(f"✓ Image found locally")
            return True

        # Image not found locally, try to pull
        logger.warning(f"⚠️  Image not found locally, attempting to pull...")
        logger.info(f"📥 Pulling image: {self.image}")
        logger.info(f"   Platform: {self.platform}")

        try:
            result = subprocess.run(
                ['docker', 'pull', '--platform', self.platform, self.image],
                check=True
            )
            logger.info(f"✓ Successfully pulled image")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to pull image: {self.image}")
            logger.error(f"💡 Check image name and tag are correct")
            return False

    def detect_ros_distro(self):
        """Detect ROS distro from the Docker image name."""
        image_lower = self.image.lower()
        if 'jazzy' in image_lower:
            return 'jazzy'
        elif 'humble' in image_lower:
            return 'humble'
        elif 'iron' in image_lower:
            return 'iron'
        else:
            return 'jazzy'  # default

    def build(self, extra_args=None):
        """Execute colcon build inside Docker container."""
        extra_args = extra_args or []

        # Check Docker availability
        if not self.check_docker():
            return 1

        # Check/pull image
        if not self.check_image_exists():
            return 1

        ros_distro = self.detect_ros_distro()
        logger.info(f"✓ Using ROS {ros_distro}")

        # Prepare build directories
        build_dir = self.workspace_root / self.build_base
        install_dir = self.workspace_root / self.install_base
        build_dir.mkdir(parents=True, exist_ok=True)
        install_dir.mkdir(parents=True, exist_ok=True)

        # Build command to run inside container
        colcon_cmd = ' '.join([
            'bash -c "',
            f'source /opt/ros/{ros_distro}/setup.bash &&',
            'colcon build',
            '--build-base /workspace/cross_build',
            '--install-base /workspace/cross_install',
            '--merge-install',
        ] + extra_args + ['"'])

        # Docker run command
        docker_cmd = [
            'docker', 'run',
            '--rm',
            '--platform', self.platform,
            '-v', f'{self.workspace_root}/src:/workspace/src:ro',  # Read-only source
            '-v', f'{build_dir}:/workspace/cross_build',
            '-v', f'{install_dir}:/workspace/cross_install',
            '-w', '/workspace',
            self.image,
            'bash', '-c',
            f'source /opt/ros/{ros_distro}/setup.bash && colcon build --build-base /workspace/cross_build --install-base /workspace/cross_install --merge-install {" ".join(extra_args)}'
        ]

        logger.info(f"🚀 Starting Docker container...")
        logger.info(f"   Image: {self.image}")
        logger.info(f"   Platform: {self.platform}")
        logger.info(f"   Workspace: {self.workspace_root}")
        logger.info(f"   Build args: {' '.join(extra_args)}")

        try:
            result = subprocess.run(docker_cmd)
            return result.returncode
        except KeyboardInterrupt:
            logger.info("\n⚠️  Build interrupted by user")
            return 130
        except Exception as e:
            logger.error(f"❌ Docker build failed: {e}")
            return 1
