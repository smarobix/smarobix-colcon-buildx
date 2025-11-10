"""Docker-based cross-compilation builder."""

import os
import subprocess
from pathlib import Path

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)


class DockerBuilder:
    """Handles cross-compilation using Docker containers."""

    def __init__(self, image, platform, build_base, install_base):
        """
        Initialize Docker builder.

        Args:
            image: Docker image for cross-compilation
            platform: Target platform (e.g., linux/arm64)
            build_base: Build directory
            install_base: Install directory
        """
        self.image = image
        self.platform = platform
        self.build_base = build_base
        self.install_base = install_base
        self.workspace_root = self._find_workspace_root()
        self.container_name = 'colcon-buildx-builder'

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
            capture_output=True
        )

        if result.returncode == 0:
            logger.info(f"✓ Image found locally: {self.image}")
            return True

        # Image not found locally, try to pull
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
            logger.error("💡 Ensure you're logged in: docker login git.smarobox.de:5050")
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
