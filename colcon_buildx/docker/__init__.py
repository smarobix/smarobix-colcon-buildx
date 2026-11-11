# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""Docker-based cross-compilation builder."""

import os
import shlex
import subprocess
import re
from datetime import datetime

from colcon_core.logging import colcon_logger

from colcon_buildx import DEFAULT_ROS_DISTRO, ROS_DISTROS
from colcon_buildx.docker import images
from colcon_buildx.docker.images import (  # noqa: F401 (re-exported: docs and tests use them)
    KIND_OE_SDK, KIND_ROS_APT, KIND_SYSROOT_CROSS, KIND_YOCTO_NATIVE, LABEL_ENV_SETUP, LABEL_KIND,
    LABEL_ROS_DISTRO, LABEL_TARGET_PLATFORM, LABEL_TOOLCHAIN, ImageError)
from colcon_buildx.workspace import resolve_workspace_root

logger = colcon_logger.getChild(__name__)

SDK_WORKSPACE = '/workspace'
SDK_BUILD_DIR = SDK_WORKSPACE + '/cross_build'
SDK_INSTALL_DIR = SDK_WORKSPACE + '/cross_install'

# Platforms tried, in order, when an image has no variant for the host and no
# --docker-platform was given: the boards colcon buildx builds for.
PULL_FALLBACKS = ('linux/arm64', 'linux/arm/v7')


def _user_args():
    """
    Run the build as the invoking user rather than as root.

    Containers run as root by default, so everything they write into the
    bind-mounted build and install directories came out owned by root: on a
    host without sudo the user could not even delete their own build tree.
    HOME points somewhere writable because the host user has no home inside
    the image.
    """
    if not hasattr(os, 'getuid') or os.getuid() == 0:
        return []
    return ['--user', f'{os.getuid()}:{os.getgid()}', '-e', 'HOME=/tmp']


def _shell_command(script):
    """
    Return the container command that runs *script*: in bash where the image has it, else in sh.

    The ROS setup scripts and ros-sdk-env prefer bash; an SDK image may have
    none, and colcon-buildx then supplies BusyBox's sh. The script travels in
    the environment, so neither shell has to parse it as an argument first.
    """
    return (['-e', f'BUILDX_SCRIPT={script}'],
            ['sh', '-c', 'if command -v bash >/dev/null 2>&1; then exec bash -c "$BUILDX_SCRIPT"; '
                         'fi; exec sh -c "$BUILDX_SCRIPT"'])


class DockerBuilder:
    """Handles cross-compilation using Docker containers."""

    def __init__(self, image, platform, build_base, install_base, use_base_image=False,
                 toolchain=None, workspace_root=None):
        """
        Initialize Docker builder.

        Args:
            image: Docker image for cross-compilation
            platform: Target platform (e.g., linux/arm64)
            build_base: Build directory
            install_base: Install directory
            use_base_image: Force use of base image, skip synced image detection
            toolchain: For a cross SDK image, a CMake toolchain file (as seen
                inside the container) to use instead of the SDK's own
            workspace_root: Workspace root; found from the current directory by default
        """
        self.base_image = image
        self.platform = platform
        self.build_base = build_base
        self.install_base = install_base
        self.toolchain = toolchain
        self.workspace_root = resolve_workspace_root(workspace_root)
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

                    logger.debug(
                        f"   Checking: {line} → repo={repo}, tag={tag}, "
                        f"pattern={regex_pattern}, match={bool(is_match)}")

                    # generate_synced_tag keeps the repository, so a synced
                    # copy of this image lives in the same one. The same tag in
                    # another repository, a mirror say, is a different image.
                    if is_match and repo == registry_and_repo:
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
                # Printed: a build silently using an older image than the one
                # asked for is surprising, and this is the way out.
                print("   Pass --use-base-image to build in the base image instead")

                return newest_image

        except subprocess.CalledProcessError as e:
            logger.debug(f"Failed to list docker images: {e}")

        # No synced image found
        print(f"ℹ️  Using base image: {self.base_image}")
        logger.info("ℹ️  Run --sync-from-device <target> to create synced version")
        return self.base_image

    def _refuse_foreign(self, image, action):
        """
        Return an error message if *image* would have to run under emulation, else None.

        --install-deps and --sync-from-device install packages by running the
        image's own apt, which an image of another architecture can only do
        under emulation. colcon buildx does not emulate.
        """
        inspected = self._inspect(image)
        if inspected is None:
            return None
        arch = images.normalize_arch(inspected.get('Architecture'))
        host = images.host_arch()
        if arch == host:
            return None
        return (f"{action} runs the image's own apt, and {image} is {arch} while this host is "
                f"{host}; colcon buildx does not run images under emulation. Run it on an {arch} "
                "host, or add the packages to the image where the image is built.")

    def create_synced_image(self, ssh_target):
        """
        Create a synced version of the base image from target device.

        Args:
            ssh_target: SSH connection string (e.g., 'ubuntu@10.42.0.3')

        Returns:
            New synced image tag, or None if sync failed
        """
        from colcon_buildx.package_sync import sync_packages_from_device

        if self._is_cross_sdk(self.base_image):
            logger.error(
                f"❌ {self.base_image} is a cross SDK image: it runs on the host, so its "
                "packages are not the target's and cannot be synced to a board.")
            logger.error(
                "💡 The target's libraries come from the SDK's sysroot, which is fixed "
                "when the SDK is built.")
            return None
        refusal = self._refuse_foreign(self.base_image, '--sync-from-device')
        if refusal:
            logger.error(f"❌ {refusal}")
            return None

        manifest_path = self.workspace_root / '.buildx-sync-manifest.json'

        try:
            synced_tag = sync_packages_from_device(
                self.base_image,
                ssh_target,
                manifest_path,
                platform=self.platform
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

        if self._is_cross_sdk(self.image):
            logger.warning(
                f"⚠ Ignoring --install-deps: {self.image} is a cross SDK image. Its "
                "sysroot is fixed when the SDK is built; rosdep cannot add to it.")
            return self.image
        refusal = self._refuse_foreign(self.image, '--install-deps')
        if refusal:
            logger.error(f"❌ {refusal}")
            return None

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

    def _inspect(self, image=None):
        """Return the `docker image inspect` object for *image*, or None."""
        return images.inspect(image or self.image)

    def _is_cross_sdk(self, image):
        """
        Return True if *image* is a local cross SDK image.

        An image that is not local yet cannot be told apart, and is taken not to
        be one; the operation that needs it pulls it and goes ahead.
        """
        labels = images.labels_of(self._inspect(image))
        return labels.get(LABEL_KIND) == KIND_OE_SDK or labels.get(images.OEROS_SDK) == 'cross'

    def _apply_labels(self, inspected):
        """Read buildx labels off an inspected image and configure from them."""
        self.labels = images.labels_of(inspected)

        self.kind = self.labels.get(LABEL_KIND, KIND_ROS_APT)
        env_setup = self.labels.get(LABEL_ENV_SETUP, '')
        self.env_setup = [p for p in env_setup.split(':') if p]

        if self.kind == KIND_OE_SDK and not self.env_setup:
            logger.warning(
                f"⚠️  Image declares {LABEL_KIND}={KIND_OE_SDK} but no "
                f"{LABEL_ENV_SETUP}; cannot set up the SDK environment")

    def check_image_exists(self):
        """Check if the Docker image exists locally or can be pulled."""
        logger.info(f"🔍 Checking for Docker image: {self.image}")

        if self._inspect() is not None:
            print("✓ Image found locally")
            return True

        # Not local. The host's own variant first: an SDK image runs on the
        # host. A board image has none, so try the board platforms next.
        logger.warning("⚠️  Image not found locally, attempting to pull...")
        logger.info(f"📥 Pulling image: {self.image}")
        pulled = subprocess.run(['docker', 'pull', self.image]).returncode == 0
        for platform in ([self.platform] if self.platform else []) + list(images_fallbacks()):
            if pulled:
                break
            logger.info(f"   Retrying with platform {platform}")
            pulled = subprocess.run(
                ['docker', 'pull', '--platform', platform, self.image]).returncode == 0

        if not pulled:
            logger.error(f"❌ Failed to pull image: {self.image}")
            logger.error("💡 Check image name and tag are correct")
            return False

        logger.info("✓ Successfully pulled image")
        return True

    def resolve_image(self):
        """
        Turn the given image into the one the build runs in, and configure from it.

        Prepares an SDK or OEROS image, or builds the cross image for a board
        image of another architecture, once per image version. Nothing runs
        under emulation.

        Returns:
            True on success; False after logging why not
        """
        inspected = self._inspect()
        if inspected is None:
            logger.error(f"❌ Cannot inspect {self.image}")
            return False
        arch = images.normalize_arch(inspected.get('Architecture'))
        host = images.host_arch()
        try:
            action, kind = images.classify(images.labels_of(inspected), arch, host)
            if action == images.PREPARE:
                self.image = images.prepare(self.image, inspected, kind)
                inspected = self._inspect()
            elif action == images.CROSS:
                self.image = images.derive_cross(self.image, inspected)
                inspected = self._inspect()
        except images.ImageError as e:
            logger.error(f"❌ {e}")
            return False

        self._apply_labels(inspected)
        target = self.labels.get(LABEL_TARGET_PLATFORM) or images.image_platform(inspected)
        if self.image != self.base_image:
            print(f"ℹ️  Building in {self.image}, made from {self.base_image}")
        print(f"   Kind: {self.kind}, target {target}, host {host}; nothing runs under emulation")
        return True

    def detect_ros_distro(self):
        """Determine the ROS distro, preferring the image label over the tag."""
        labelled = self.labels.get(LABEL_ROS_DISTRO)
        if labelled:
            return labelled

        image_lower = self.base_image.lower()
        for distro in ROS_DISTROS:
            if distro in image_lower:
                return distro
        logger.warning(
            f"⚠️  Could not determine ROS distro from '{self.base_image}', assuming "
            f"{DEFAULT_ROS_DISTRO}. Set the {LABEL_ROS_DISTRO} label on the image "
            "to be explicit.")
        return DEFAULT_ROS_DISTRO

    def _colcon(self, extra_args):
        """The colcon build command line shared by every kind of image."""
        # Logs go into the mounted build base: under --user the container cannot
        # write /workspace, and inside it they were lost anyway.
        return (f'colcon --log-base {SDK_BUILD_DIR}/log build'
                f' --build-base {SDK_BUILD_DIR}'
                f' --install-base {SDK_INSTALL_DIR}'
                f' --merge-install {shlex.join(extra_args)}')

    def _run(self, build_dir, install_dir, script):
        """docker run for *script*; the image runs on the host's own architecture."""
        env, command = _shell_command(script)
        # No --platform: every image colcon buildx runs is the host's own.
        return [
            'docker', 'run',
            '--rm',
            *_user_args(),
            *env,
            '-v', f'{self.workspace_root}/src:{SDK_WORKSPACE}/src:ro',  # Read-only source
            '-v', f'{build_dir}:{SDK_BUILD_DIR}',
            '-v', f'{install_dir}:{SDK_INSTALL_DIR}',
            '-w', SDK_WORKSPACE,
            '--entrypoint', '',
            self.image,
            *command,
        ]

    def _native_command(self, build_dir, install_dir, extra_args):
        """docker run for an image of the host's architecture that runs as the target."""
        if self.toolchain:
            logger.warning(
                f"⚠ Ignoring --toolchain: {self.image} runs as the target and builds "
                "natively. Only a cross SDK image uses a toolchain file.")

        if self.env_setup:
            setup = ' && '.join(f'. {shlex.quote(p)}' for p in self.env_setup)
        else:
            ros_distro = self.detect_ros_distro()
            logger.info(f"✓ Using ROS {ros_distro}")
            setup = f'. /opt/ros/{ros_distro}/setup.sh'
        return self._run(build_dir, install_dir, f'{setup} && {self._colcon(extra_args)}')

    def _oe_sdk_command(self, build_dir, install_dir, extra_args):
        """docker run for a cross SDK image, which runs on the host architecture."""
        from colcon_buildx.toolchain import ENV_TOOLCHAIN, WRAPPER_NAME, write_wrapper

        sources = ' && '.join(f'. {shlex.quote(p)}' for p in self.env_setup)

        # The wrapper refers to $ENV{OE_CMAKE_TOOLCHAIN_FILE} rather than a path,
        # so it can be written here on the host into the bind-mounted build base
        # even though that variable only exists once the SDK is sourced in the
        # container. --toolchain replaces it with a path inside the container.
        write_wrapper(build_dir / WRAPPER_NAME, SDK_INSTALL_DIR, self.toolchain or ENV_TOOLCHAIN)
        wrapper = f'{SDK_BUILD_DIR}/{WRAPPER_NAME}'

        # A prepared image sets OE_CMAKE_TOOLCHAIN_FILE even without ros-sdk-env;
        # an image used as it is may not, unless the user named a toolchain.
        if self.toolchain:
            toolchain_check = ''
        else:
            toolchain_check = (
                'if [ -z "$OE_CMAKE_TOOLCHAIN_FILE" ]; then '
                '  echo "OE_CMAKE_TOOLCHAIN_FILE unset after sourcing the SDK environment;'
                ' name the SDK toolchain file with --toolchain" >&2; '
                '  exit 1; '
                'fi && '
            )

        # CMAKE_TOOLCHAIN_FILE is passed through the environment rather than as
        # --cmake-args: colcon's --cmake-args would collide with a user-supplied
        # one, and CMake has honoured the environment variable since 3.21.
        script = (
            'set -e && '
            f'{sources} && '
            f'export ROS_WORKSPACE={SDK_WORKSPACE} && '
            f'{toolchain_check}'
            f'export CMAKE_TOOLCHAIN_FILE={wrapper} && '
            # Meta-ros SDKs ship ninja but not make. Use Ninja when the sourced
            # environment has it and the user has not chosen a generator; an SDK
            # without ninja keeps CMake's default.
            'if [ -z "${CMAKE_GENERATOR:-}" ] && command -v ninja >/dev/null; then '
            'export CMAKE_GENERATOR=Ninja; fi && '
            f'{self._colcon(extra_args)}'
        )
        return self._run(build_dir, install_dir, script)

    def _cross_command(self, build_dir, install_dir, extra_args):
        """docker run for a cross image: the target image as sysroot, the host's cross gcc."""
        toolchain = self.toolchain or self.labels.get(LABEL_TOOLCHAIN, '/opt/buildx/toolchain.cmake')
        sources = ' && '.join(f'. {shlex.quote(p)}' for p in self.env_setup)
        script = (
            'set -e && '
            f'{sources} && '
            f'export BUILDX_INSTALL_BASE={SDK_INSTALL_DIR} && '
            f'export CMAKE_TOOLCHAIN_FILE={shlex.quote(toolchain)} && '
            'if [ -z "${CMAKE_GENERATOR:-}" ] && command -v ninja >/dev/null; then '
            'export CMAKE_GENERATOR=Ninja; fi && '
            f'{self._colcon(extra_args)}'
        )
        return self._run(build_dir, install_dir, script)

    def build(self, extra_args=None):
        """Execute colcon build inside Docker container."""
        extra_args = extra_args or []

        # Check Docker availability
        if not self.check_docker():
            return 1

        # Check/pull image, then turn it into the one to build in
        if not self.check_image_exists() or not self.resolve_image():
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
        elif self.kind == KIND_SYSROOT_CROSS:
            docker_cmd = self._cross_command(build_dir, install_dir, extra_args)
        else:
            docker_cmd = self._native_command(build_dir, install_dir, extra_args)

        logger.info("🚀 Starting Docker container...")
        logger.info(f"   Image: {self.image}")
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


def images_fallbacks():
    """Board platforms to try when pulling an image with no variant for the host."""
    return PULL_FALLBACKS
