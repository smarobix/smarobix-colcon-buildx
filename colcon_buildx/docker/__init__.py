"""Docker-based cross-compilation builder."""

import json
import shlex
import subprocess
import re
from pathlib import Path
from datetime import datetime

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)

# Image labels. An image that declares kind=oe-sdk holds a cross toolchain and
# runs on the *host* architecture, unlike the apt/source images here, which run
# as the target architecture under emulation and build natively inside it.
LABEL_KIND = 'org.smarobix.buildx.kind'
LABEL_ENV_SETUP = 'org.smarobix.buildx.env-setup'
LABEL_TARGET_PLATFORM = 'org.smarobix.buildx.target-platform'
LABEL_ROS_DISTRO = 'org.smarobix.buildx.ros-distro'

KIND_ROS_APT = 'ros-apt'
KIND_OE_SDK = 'oe-sdk'

SDK_WORKSPACE = '/workspace'
SDK_BUILD_DIR = SDK_WORKSPACE + '/cross_build'
SDK_INSTALL_DIR = SDK_WORKSPACE + '/cross_install'

# The SDK's toolchain file sets
#     CMAKE_FIND_ROOT_PATH       <target sysroot>
#     CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY
# so find_package() searches the sysroot and nothing else -- a workspace cannot
# find the packages it just built itself, and any package with an intra-workspace
# dependency fails to configure. Wrap the SDK's toolchain in one that appends the
# colcon install prefix to the find roots, and point CMake at the wrapper.
TOOLCHAIN_WRAPPER = 'include("{sdk_toolchain}")\nlist(APPEND CMAKE_FIND_ROOT_PATH "{install_dir}")\n'


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

        # Populated from image labels once the image is available locally.
        self.labels = {}
        self.kind = KIND_ROS_APT
        self.env_setup = []

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

        logger.debug("🔍 Searching for synced images...")
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
                except ValueError:
                    formatted_date = date_str

                print(f"ℹ️  Using synced image: {newest_image}")
                print(f"   Synced on: {formatted_date}")
                logger.info("ℹ️  Run with --use-base-image to use original base image instead")

                return newest_image

        except subprocess.CalledProcessError as e:
            logger.debug(f"Failed to list docker images: {e}")

        # No synced image found
        print(f"ℹ️  Using base image: {self.base_image}")
        logger.info("ℹ️  Run --sync-from-device <target> to create synced version")
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
            subprocess.run(['docker', 'info'], capture_output=True, check=True)
            return True
        except subprocess.CalledProcessError:
            logger.error("❌ Docker daemon is not running")
            logger.error("💡 Start Docker Desktop or run: sudo systemctl start docker")
            return False
        except FileNotFoundError:
            logger.error("❌ Docker not found")
            logger.error("💡 Install Docker: https://docs.docker.com/get-docker/")
            return False

    def _inspect(self):
        """Return the `docker image inspect` object for the image, or None."""
        result = subprocess.run(
            ['docker', 'image', 'inspect', self.image],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            logger.debug(f"   docker inspect return code: {result.returncode}")
            logger.debug(f"   stderr: {result.stderr}")
            return None
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.debug(f"   could not parse inspect output: {e}")
            return None
        return parsed[0] if parsed else None

    def _apply_labels(self, inspected):
        """Read buildx labels off an inspected image and configure from them."""
        self.labels = (inspected or {}).get('Config', {}).get('Labels') or {}

        self.kind = self.labels.get(LABEL_KIND, KIND_ROS_APT)
        env_setup = self.labels.get(LABEL_ENV_SETUP, '')
        self.env_setup = [p for p in env_setup.split(':') if p]

        if self.kind == KIND_OE_SDK:
            if not self.env_setup:
                logger.warning(
                    f"⚠️  Image declares {LABEL_KIND}={KIND_OE_SDK} but no "
                    f"{LABEL_ENV_SETUP}; cannot set up the SDK environment")
            target = self.labels.get(LABEL_TARGET_PLATFORM)
            print("ℹ️  Cross SDK image — running on the host architecture, not under emulation")
            if target:
                print(f"   Target platform: {target}")

    def check_image_exists(self):
        """Check if the Docker image exists locally or can be pulled."""
        logger.info(f"🔍 Checking for Docker image: {self.image}")

        inspected = self._inspect()
        if inspected is not None:
            print("✓ Image found locally")
            self._apply_labels(inspected)
            return True

        # Image not found locally, try to pull. The platform is unknown until
        # the image has been inspected, so pull the host-native variant and let
        # the labels decide; a target-architecture image without a host-native
        # variant is retried explicitly below.
        logger.warning("⚠️  Image not found locally, attempting to pull...")
        logger.info(f"📥 Pulling image: {self.image}")

        pulled = subprocess.run(['docker', 'pull', self.image]).returncode == 0
        if not pulled and self.platform:
            logger.info(f"   Retrying with platform {self.platform}")
            pulled = subprocess.run(
                ['docker', 'pull', '--platform', self.platform, self.image]
            ).returncode == 0

        if not pulled:
            logger.error(f"❌ Failed to pull image: {self.image}")
            logger.error("💡 Check image name and tag are correct")
            return False

        logger.info("✓ Successfully pulled image")
        self._apply_labels(self._inspect())
        return True

    def detect_ros_distro(self):
        """Determine the ROS distro, preferring the image label over the tag."""
        labelled = self.labels.get(LABEL_ROS_DISTRO)
        if labelled:
            return labelled

        image_lower = self.image.lower()
        for distro in ('jazzy', 'humble', 'iron', 'rolling'):
            if distro in image_lower:
                return distro
        logger.warning(
            f"⚠️  Could not determine ROS distro from '{self.image}', assuming jazzy. "
            f"Set the {LABEL_ROS_DISTRO} label on the image to be explicit.")
        return 'jazzy'

    def _native_command(self, build_dir, install_dir, extra_args):
        """docker run for an image that runs as the target architecture."""
        ros_distro = self.detect_ros_distro()
        logger.info(f"✓ Using ROS {ros_distro}")

        script = (
            f'source /opt/ros/{ros_distro}/setup.bash && '
            f'colcon build'
            f' --build-base {SDK_WORKSPACE}/cross_build'
            f' --install-base {SDK_WORKSPACE}/cross_install'
            f' --merge-install {shlex.join(extra_args)}'
        )

        return [
            'docker', 'run',
            '--rm',
            '--platform', self.platform,
            '-v', f'{self.workspace_root}/src:{SDK_WORKSPACE}/src:ro',  # Read-only source
            '-v', f'{build_dir}:{SDK_WORKSPACE}/cross_build',
            '-v', f'{install_dir}:{SDK_WORKSPACE}/cross_install',
            '-w', SDK_WORKSPACE,
            self.image,
            'bash', '-c', script,
        ]

    def _oe_sdk_command(self, build_dir, install_dir, extra_args):
        """docker run for a cross SDK image, which runs on the host architecture."""
        sources = ' && '.join(f'. {shlex.quote(p)}' for p in self.env_setup)

        # CMAKE_TOOLCHAIN_FILE is passed through the environment rather than as
        # --cmake-args: colcon's --cmake-args would collide with a user-supplied
        # one, and CMake has honoured the environment variable since 3.21.
        # The wrapper is written inside the container: the SDK toolchain path is
        # only known after its environment scripts have been sourced.
        wrapper = SDK_BUILD_DIR + '/buildx-toolchain.cmake'
        script = (
            'set -e && '
            f'{sources} && '
            f'export ROS_WORKSPACE={SDK_WORKSPACE} && '
            'if [ -z "$OE_CMAKE_TOOLCHAIN_FILE" ]; then '
            '  echo "OE_CMAKE_TOOLCHAIN_FILE unset after sourcing the SDK environment;'
            ' the SDK is missing ros-sdk-env (ros/meta-ros@1be4737), or was built from'
            ' a target that does not pull it in -- use ros2-image-sdktest, not'
            ' ros-image-core" >&2; '
            '  exit 1; '
            'fi && '
            f'printf \'include("%s")\\nlist(APPEND CMAKE_FIND_ROOT_PATH "%s")\\n\''
            f' "$OE_CMAKE_TOOLCHAIN_FILE" {SDK_INSTALL_DIR} > {wrapper} && '
            f'export CMAKE_TOOLCHAIN_FILE={wrapper} && '
            f'colcon build'
            f' --build-base {SDK_BUILD_DIR}'
            f' --install-base {SDK_INSTALL_DIR}'
            f' --merge-install {shlex.join(extra_args)}'
        )

        # No --platform: the SDK cross-compiles, so the container should run the
        # host-native variant of the manifest rather than be emulated.
        return [
            'docker', 'run',
            '--rm',
            '-v', f'{self.workspace_root}/src:{SDK_WORKSPACE}/src:ro',  # Read-only source
            '-v', f'{build_dir}:{SDK_BUILD_DIR}',
            '-v', f'{install_dir}:{SDK_INSTALL_DIR}',
            '-w', SDK_WORKSPACE,
            self.image,
            'bash', '-c', script,
        ]

    def build(self, extra_args=None):
        """Execute colcon build inside Docker container."""
        extra_args = extra_args or []

        # Check Docker availability
        if not self.check_docker():
            return 1

        # Check/pull image; this is what populates the labels
        if not self.check_image_exists():
            return 1

        # Prepare build directories
        build_dir = self.workspace_root / self.build_base
        install_dir = self.workspace_root / self.install_base
        build_dir.mkdir(parents=True, exist_ok=True)
        install_dir.mkdir(parents=True, exist_ok=True)

        if self.kind == KIND_OE_SDK:
            if not self.env_setup:
                logger.error(f"❌ Cross SDK image has no {LABEL_ENV_SETUP} label")
                return 1
            docker_cmd = self._oe_sdk_command(build_dir, install_dir, extra_args)
        else:
            docker_cmd = self._native_command(build_dir, install_dir, extra_args)

        logger.info("🚀 Starting Docker container...")
        logger.info(f"   Image: {self.image}")
        logger.info(f"   Kind: {self.kind}")
        logger.info(f"   Platform: {'host-native' if self.kind == KIND_OE_SDK else self.platform}")
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
