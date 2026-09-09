"""Cross-compilation build verb for colcon."""

import os
from pathlib import Path

from colcon_core.plugin_system import satisfies_version
from colcon_core.verb import VerbExtensionPoint
from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)

METHODS = ('docker', 'sysroot')

# Fallback values, applied only after the command line and the config file have
# had their say. Every argument below is declared with ``default=None`` so that
# "not supplied on the command line" stays distinguishable from "supplied with
# a value that happens to equal the default"; argparse defaults would make the
# config file unreachable for these keys.
DEFAULTS = {
    'method': 'docker',
    'build_base': 'cross_build',
    'install_base': 'cross_install',
    'docker_platform': 'linux/arm64',
    'sysroot_mount': os.path.expanduser('~/mnt/board-sysroot'),
    'rosdep_args': '--ignore-src -y',
    'deploy': False,
    'install_deps': False,
    'use_base_image': False,
    'no_mount': False,
}

# Keys accepted in .buildx.conf / .buildx.yml. Anything else is a typo, and
# silently ignoring it is how the wrong architecture reaches a board.
CONFIG_KEYS = frozenset(DEFAULTS) | {
    'docker_image',
    'sysroot_host',
    'toolchain',
    'deploy_target',
    'sync_from_device',
    'install_deps_on_device',
}


def _find_workspace_root(start=None):
    """Walk up from *start* to the directory containing src/."""
    current = Path(start or Path.cwd())
    for _ in range(5):
        if (current / 'src').is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return Path(start or Path.cwd())


class BuildxVerb(VerbExtensionPoint):
    """Cross-compile ROS 2 workspace for embedded ARM boards."""

    def __init__(self):
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser):
        """Add command line arguments for cross-compilation."""
        # Build method
        parser.add_argument(
            '--method',
            choices=list(METHODS),
            default=None,
            help='Build method: docker (container-based) or sysroot (SSHFS mount). '
                 'Default: docker'
        )

        # Common arguments
        parser.add_argument(
            '--config',
            type=str,
            help='Configuration file (default: search for .buildx.conf or .buildx.yml in workspace)'
        )
        parser.add_argument(
            '--build-base',
            default=None,
            help='Build directory for cross-compiled artifacts (default: cross_build)'
        )
        parser.add_argument(
            '--install-base',
            default=None,
            help='Install directory for cross-compiled artifacts (default: cross_install)'
        )

        # Sysroot-specific arguments
        sysroot_group = parser.add_argument_group('SSHFS Sysroot Options (--method sysroot)')
        sysroot_group.add_argument(
            '--sysroot-host',
            help='Hostname or IP of the target board for sysroot access (e.g., kria-vision-home)'
        )
        sysroot_group.add_argument(
            '--sysroot-mount',
            default=None,
            help='Local mount point for board sysroot (default: ~/mnt/board-sysroot)'
        )
        sysroot_group.add_argument(
            '--toolchain',
            help='Path to CMake toolchain file (required for sysroot method)'
        )
        sysroot_group.add_argument(
            '--no-mount',
            action='store_true',
            default=None,
            help='Skip SSHFS mounting (assume sysroot already mounted)'
        )

        # Note: --install-deps and --rosdep-args also work with sysroot method

        # Docker-specific arguments
        docker_group = parser.add_argument_group('Docker Options (--method docker)')
        docker_group.add_argument(
            '--docker-image',
            help='Docker image for cross-compilation (e.g., sapertuz/smrbx-buildx:kv26-jazzy)'
        )
        docker_group.add_argument(
            '--docker-platform',
            default=None,
            help='Target platform for Docker (default: linux/arm64)'
        )
        docker_group.add_argument(
            '--sync-from-device',
            metavar='SSH_TARGET',
            help='Sync package versions from target device (e.g., ubuntu@192.168.1.100). Creates local synced image.'
        )
        docker_group.add_argument(
            '--use-base-image',
            action='store_true',
            default=None,
            help='Force use of base image, skip auto-detection of synced images'
        )
        docker_group.add_argument(
            '--install-deps',
            action='store_true',
            default=None,
            help='Install workspace dependencies using rosdep in Docker image (for dev only, see --install-deps-on-device)'
        )
        docker_group.add_argument(
            '--rosdep-args',
            default=None,
            help='Additional arguments to pass to rosdep install (default: --ignore-src -y)'
        )

        # Device dependency installation
        deps_group = parser.add_argument_group('Device Dependency Options')
        deps_group.add_argument(
            '--install-deps-on-device',
            metavar='SSH_TARGET',
            help='Install workspace dependencies on target device via SSH (e.g., ubuntu@10.42.0.3). Recommended before --sync-from-device.'
        )

        # Deployment
        deploy_group = parser.add_argument_group('Deployment Options')
        deploy_group.add_argument(
            '--deploy',
            action='store_true',
            default=None,
            help='Deploy build results to target board after successful build'
        )
        deploy_group.add_argument(
            '--deploy-target',
            help='Deployment target in format user@host:/path/to/install (e.g., ubuntu@10.42.0.3:~/ros2_ws/install/)'
        )

        # Pass-through colcon args
        parser.add_argument(
            'colcon_args',
            nargs='*',
            help='Additional arguments to pass to colcon build (e.g., --packages-select my_package)'
        )

    def main(self, *, context):
        """Execute the cross-compilation build."""
        from colcon_buildx.config import load_config, merge_settings

        args = context.args

        # Precedence: command line > config file > DEFAULTS.
        config = load_config(args.config)
        if config:
            logger.info("📝 Loaded configuration from file")
        unknown = merge_settings(args, config, DEFAULTS, CONFIG_KEYS)
        for key in unknown:
            logger.warning(f"⚠ Ignoring unrecognised config key: {key}")

        # choices= no longer covers a value arriving from the config file.
        if args.method not in METHODS:
            logger.error(f"❌ Unknown method: {args.method}")
            logger.info(f"💡 Valid methods: {', '.join(METHODS)}")
            return 1

        logger.info(f"🔧 Cross-compilation method: {args.method}")

        try:
            # Handle --install-deps-on-device (standalone operation, works with any method)
            if args.install_deps_on_device:
                from colcon_buildx.rosdep_manager import install_deps_sshfs

                logger.info(f"📦 Installing workspace dependencies on device: {args.install_deps_on_device}")

                success = install_deps_sshfs(
                    args.install_deps_on_device,
                    _find_workspace_root(),
                    args.rosdep_args
                )
                if not success:
                    logger.error("❌ Failed to install dependencies on device")
                    return 1

                logger.info("✅ Dependencies installed on device")
                logger.info("ℹ Next step: run --sync-from-device to update Docker image")

                # This is a standalone operation, exit after completion
                return 0

            if args.method == 'sysroot':
                # SSHFS-based cross-compilation
                if not args.toolchain:
                    logger.error("❌ --toolchain is required for sysroot method")
                    return 1
                if not args.sysroot_host:
                    logger.error("❌ --sysroot-host is required for sysroot method")
                    return 1

                from colcon_buildx.sysroot import SysrootBuilder
                builder = SysrootBuilder(
                    sysroot_host=args.sysroot_host,
                    sysroot_mount=args.sysroot_mount,
                    toolchain_file=args.toolchain,
                    build_base=args.build_base,
                    install_base=args.install_base,
                    no_mount=args.no_mount
                )

                # Install dependencies if requested
                if args.install_deps:
                    logger.info("📦 Installing workspace dependencies on device...")
                    if not builder.install_dependencies(args.rosdep_args):
                        logger.error("❌ Failed to install dependencies")
                        return 1

            elif args.method == 'docker':
                # Docker-based cross-compilation
                if not args.docker_image:
                    logger.error("❌ --docker-image is required for docker method")
                    logger.info("💡 Example: --docker-image sapertuz/smrbx-buildx:kv26-jazzy")
                    return 1

                from colcon_buildx.docker import DockerBuilder

                builder = DockerBuilder(
                    image=args.docker_image,
                    platform=args.docker_platform,
                    build_base=args.build_base,
                    install_base=args.install_base,
                    use_base_image=args.use_base_image
                )

                # Sync from device if requested (standalone operation)
                if args.sync_from_device:
                    logger.info(f"📦 Syncing packages from device: {args.sync_from_device}")
                    synced_image = builder.create_synced_image(args.sync_from_device)
                    if not synced_image:
                        logger.error("❌ Failed to create synced image")
                        return 1
                    logger.info("✅ Package sync complete")
                    logger.info("ℹ Next step: run 'colcon buildx' to build with synced image")
                    # This is a standalone operation, exit after completion
                    return 0

                # Install dependencies if requested (with warning for Docker method)
                if args.install_deps:
                    logger.warning("⚠ Warning: --install-deps only installs dependencies in the Docker image.")
                    logger.warning("  The target device will NOT have these dependencies installed.")
                    logger.info("ℹ Recommended workflow:")
                    logger.info("  1. colcon buildx --install-deps-on-device <device>")
                    logger.info("  2. colcon buildx --sync-from-device <device>")
                    logger.info("  3. colcon buildx")
                    logger.info("📦 Installing workspace dependencies in Docker image...")
                    updated_image = builder.install_dependencies(args.rosdep_args)
                    if not updated_image:
                        logger.error("❌ Failed to install dependencies")
                        return 1
                    # Update builder to use updated image
                    builder.image = updated_image

            # Execute the build
            logger.info("🚀 Starting cross-compilation build...")
            result = builder.build(extra_args=args.colcon_args or [])
            if result != 0:
                logger.error(f"❌ Build failed with exit code {result}")
                return result

            logger.info("✅ Cross-compilation completed successfully")

            # Optional deployment
            if args.deploy:
                if not args.deploy_target:
                    logger.error("❌ --deploy-target is required when --deploy is used")
                    logger.info("💡 Example: --deploy-target ubuntu@10.42.0.3:~/ros2_ws/install/")
                    return 1

                from colcon_buildx.deployment import deploy
                logger.info(f"🚀 Deploying to {args.deploy_target}...")
                deploy_result = deploy(args.install_base, args.deploy_target)
                if deploy_result != 0:
                    logger.error("❌ Deployment failed")
                    return deploy_result

                logger.info("✅ Deployment completed successfully")

            return 0

        except Exception as e:
            logger.error(f"❌ Error during cross-compilation: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return 1
