# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""Cross-compilation build verb for colcon."""

import re
import textwrap
from pathlib import Path

from colcon_core.plugin_system import satisfies_version
from colcon_core.verb import VerbExtensionPoint
from colcon_core.logging import colcon_logger

from colcon_buildx.config import CONFIG_NAMES
from colcon_buildx.workspace import MAX_LEVELS, find_workspace_root

logger = colcon_logger.getChild(__name__)

METHODS = ('docker', 'sysroot', 'sdk')

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
    # Kept unexpanded so --help and the docs show it as written; the sysroot
    # builder expands it.
    'sysroot_mount': '~/mnt/board-sysroot',
    'rosdep_args': '--ignore-src -y',
    'deploy': False,
    'install_deps': False,
    'use_base_image': False,
    'no_mount': False,
    'emit_mixin': False,
}

# Keys accepted in .buildx.conf / .buildx.yml. Anything else is a typo, and
# silently ignoring it is how the wrong architecture reaches a board.
CONFIG_KEYS = frozenset(DEFAULTS) | {
    'docker_image',
    'sysroot_host',
    'toolchain',
    'sdk_env',
    'deploy_target',
}

# One-off actions that replace the build and then exit. They are flags only: a
# config file carrying one would turn every build in that workspace into a
# device sync, which is why they are called out rather than merely ignored.
ACTION_FLAGS = ('sync_from_device', 'install_deps_on_device')

# Shown after the options in --help. colcon keeps its line breaks, so it is
# wrapped by hand; the names and numbers come from the code it describes.
EPILOG = f"""\
Configuration files:
  Settings can also come from a file. Without --config, colcon buildx looks
  in the current directory for {', '.join(CONFIG_NAMES[:-1])} and {CONFIG_NAMES[-1]},
  in that order, then in each parent directory in turn. The search stops at
  the workspace root, the first directory that holds src/, and after at
  most {MAX_LEVELS} directories, the current one included. The first file found is
  used; files are not merged.

  Keys are the long option names with underscores, e.g. docker_image for
  --docker-image. --config and the arguments passed through to colcon build
  cannot be set in a file. Commented examples of every key:
  https://github.com/smarobix/smarobix-colcon-buildx/tree/main/examples

Precedence:
  command line > config file > built-in defaults.
  An on/off option such as --deploy can only switch a setting on from the
  command line; if the config file switches it on, edit the file to turn it
  off.
"""


def _without_hyphen_breaks(formatter_class):
    """
    Return *formatter_class*, changed to wrap help text only at spaces.

    argparse also wraps at hyphens, which splits option names across lines:
    "--install-deps-on-" then "device". That reads as a different option, and
    the reference docs are generated from this text. Line breaks written into
    a help string are kept, as colcon's own formatter does.
    """
    class Formatter(formatter_class):
        def _split_lines(self, text, width):
            lines = []
            for line in text.splitlines():
                line = re.sub(r'\s+', ' ', line).strip()
                lines += textwrap.wrap(
                    line, width, break_on_hyphens=False, break_long_words=False) or ['']
            return lines

    return Formatter


def _workspace_root():
    """
    Return the workspace root, or the current directory with a warning.

    Falling back silently meant a run from outside the workspace built,
    mounted and synced the wrong directory without saying so.
    """
    root = find_workspace_root()
    if root is not None:
        return root

    cwd = Path.cwd()
    logger.warning(
        f"⚠ No workspace root found: no src/ directory in {cwd} or the "
        f"{MAX_LEVELS - 1} directories above it. Using the current directory as "
        "the workspace root; run colcon buildx from your workspace root instead.")
    return cwd


class BuildxVerb(VerbExtensionPoint):
    """Cross-compile a ROS 2 workspace for arm64 and armhf boards."""

    def __init__(self):
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser):
        """Add command line arguments for cross-compilation."""
        # colcon's formatter keeps the epilog's line breaks as written.
        parser.epilog = EPILOG
        parser.formatter_class = _without_hyphen_breaks(parser.formatter_class)

        parser.add_argument(
            '--method',
            choices=list(METHODS),
            default=None,
            help='How to build: docker builds in a container image; sdk builds '
                 'against a Yocto/OE SDK installed on this Linux host; sysroot '
                 "builds against the board's root filesystem mounted over SSHFS "
                 f"(experimental). Default: {DEFAULTS['method']}"
        )
        parser.add_argument(
            '--config',
            metavar='FILE',
            type=str,
            help='Read settings from FILE instead of searching for a config '
                 'file; see the Notes below'
        )
        parser.add_argument(
            '--build-base',
            metavar='DIR',
            default=None,
            help='Build directory, relative to the workspace root '
                 f"(default: {DEFAULTS['build_base']})"
        )
        parser.add_argument(
            '--install-base',
            metavar='DIR',
            default=None,
            help='Install directory, relative to the workspace root; --deploy '
                 f"copies it to the board (default: {DEFAULTS['install_base']})"
        )
        parser.add_argument(
            '--toolchain',
            metavar='FILE',
            help='CMake toolchain file. Required for --method sysroot. With '
                 '--method sdk, or --method docker and a cross SDK image, it '
                 "replaces the SDK's own toolchain file (OE_CMAKE_TOOLCHAIN_FILE); "
                 'for an image, give the path inside the container. Images that '
                 'run as the target ignore it'
        )

        docker_group = parser.add_argument_group('Docker options (--method docker)')
        docker_group.add_argument(
            '--docker-image',
            metavar='IMAGE',
            help='Image to build in; required for --method docker, e.g. '
                 'ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy. If a local '
                 '<tag>-synced-YYYYMMDD copy of it exists, made by '
                 '--sync-from-device or --install-deps, the newest one is used '
                 'instead'
        )
        docker_group.add_argument(
            '--docker-platform',
            metavar='PLATFORM',
            default=None,
            help='Docker platform of the target, which the image runs as: '
                 'linux/arm64, or linux/arm/v7 for armhf boards. Also used by '
                 '--sync-from-device and --install-deps. Cross SDK images ignore '
                 'it and run on the host architecture '
                 f"(default: {DEFAULTS['docker_platform']})"
        )
        docker_group.add_argument(
            '--use-base-image',
            action='store_true',
            default=None,
            help='Build in --docker-image itself, even if a local -synced- copy '
                 'of it exists'
        )
        docker_group.add_argument(
            '--sync-from-device',
            metavar='SSH_TARGET',
            help="Read the board's installed Debian packages over SSH, install "
                 'the same versions into a copy of --docker-image, tag it '
                 '<tag>-synced-YYYYMMDD, and exit without building. '
                 'E.g. ubuntu@10.42.0.3. Not for cross SDK images'
        )

        sdk_group = parser.add_argument_group('SDK options (--method sdk)')
        sdk_group.add_argument(
            '--sdk-env',
            metavar='SCRIPTS',
            help='SDK environment script to source; several are separated by '
                 'colons and sourced in order. Required for --method sdk, e.g. '
                 '/opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux'
        )
        sdk_group.add_argument(
            '--emit-mixin',
            action='store_true',
            default=None,
            help='Also write a colcon mixin with the SDK cross-build settings to '
                 '.buildx/mixin/ in the workspace, for a plain '
                 '`colcon build --mixin buildx`'
        )

        sysroot_group = parser.add_argument_group(
            'SSHFS sysroot options (--method sysroot, experimental)')
        sysroot_group.add_argument(
            '--sysroot-host',
            metavar='HOST',
            help='Board whose root filesystem is mounted over SSHFS, as host or '
                 'user@host, e.g. my-board. Required for --method sysroot'
        )
        sysroot_group.add_argument(
            '--sysroot-mount',
            metavar='DIR',
            default=None,
            help="Local mount point for the board's root filesystem "
                 f"(default: {DEFAULTS['sysroot_mount']})"
        )
        sysroot_group.add_argument(
            '--no-mount',
            action='store_true',
            default=None,
            help='Use a sysroot already mounted at --sysroot-mount instead of '
                 'mounting it'
        )

        deps_group = parser.add_argument_group('Dependency options')
        deps_group.add_argument(
            '--install-deps',
            action='store_true',
            default=None,
            help='Run rosdep install for the workspace before building. '
                 '--method docker: installs into a new local image, '
                 '<tag>-synced-YYYYMMDD, and not on the board. '
                 '--method sysroot: installs on the board (--sysroot-host) over '
                 'SSH. --method sdk: ignored, as the SDK sysroot is fixed when '
                 'the SDK is built. To install on the board and match the image '
                 'to it, use --install-deps-on-device, then --sync-from-device'
        )
        deps_group.add_argument(
            '--rosdep-args',
            metavar='ARGS',
            default=None,
            help='Arguments for rosdep install, used by --install-deps and '
                 '--install-deps-on-device. Pass them as one word, e.g. '
                 '--rosdep-args="--ignore-src -y -r" '
                 f"(default: {DEFAULTS['rosdep_args']})"
        )
        deps_group.add_argument(
            '--install-deps-on-device',
            metavar='SSH_TARGET',
            help='Copy src/ to the board, run rosdep install there over SSH, '
                 'and exit without building. sudo on the board may ask for a '
                 'password. Works with any --method. E.g. ubuntu@10.42.0.3'
        )

        deploy_group = parser.add_argument_group('Deployment options')
        deploy_group.add_argument(
            '--deploy',
            action='store_true',
            default=None,
            help='After a successful build, copy the install directory to '
                 '--deploy-target with rsync --delete, which removes files '
                 'there that are not in the local install directory'
        )
        deploy_group.add_argument(
            '--deploy-target',
            metavar='TARGET',
            help='rsync destination for --deploy, as user@host:path, e.g. '
                 'ubuntu@10.42.0.3:~/ros2_ws/install/'
        )

        # Pass-through colcon args
        parser.add_argument(
            'colcon_args',
            nargs='*',
            help='Further arguments for colcon build, e.g. --packages-select '
                 'my_package'
        )

    def main(self, *, context):
        """Execute the cross-compilation build."""
        from colcon_buildx.config import find_config_file, merge_settings, read_config_file

        args = context.args

        # Precedence: command line > config file > DEFAULTS.
        config = None
        config_file = find_config_file(args.config)
        if config_file:
            config = read_config_file(config_file)
        if config is not None:
            # Printed, like the image in use: with settings coming from three
            # places, which file was read is the first thing to check.
            print(f"ℹ️  Config file: {config_file}")
        unknown = merge_settings(args, config, DEFAULTS, CONFIG_KEYS)
        for key in unknown:
            if key in ACTION_FLAGS:
                flag = '--' + key.replace('_', '-')
                logger.warning(
                    f"⚠ {key} is a command-line action, not a config key; ignoring it. "
                    f"Run `colcon buildx {flag} <user@host>` instead.")
            else:
                logger.warning(f"⚠ Ignoring unrecognised config key: {key}")

        # choices= no longer covers a value arriving from the config file.
        if args.method not in METHODS:
            logger.error(f"❌ Unknown method: {args.method}")
            logger.error(f"💡 Valid methods: {', '.join(METHODS)}")
            return 1

        logger.info(f"🔧 Cross-compilation method: {args.method}")

        # Checked before a build that can take an hour, not after it.
        if args.deploy and not args.deploy_target:
            logger.error("❌ --deploy-target is required when --deploy is used")
            logger.error("💡 Example: --deploy-target ubuntu@10.42.0.3:~/ros2_ws/install/")
            return 1

        workspace_root = _workspace_root()

        try:
            # Handle --install-deps-on-device (standalone operation, works with any method)
            if args.install_deps_on_device:
                from colcon_buildx.rosdep_manager import install_deps_sshfs

                logger.info(f"📦 Installing workspace dependencies on device: {args.install_deps_on_device}")

                success = install_deps_sshfs(
                    args.install_deps_on_device,
                    workspace_root,
                    args.rosdep_args
                )
                if not success:
                    logger.error("❌ Failed to install dependencies on device")
                    return 1

                logger.info("✅ Dependencies installed on device")
                if args.method == 'docker':
                    print("ℹ️  Next, match the build image to the board: "
                          f"colcon buildx --sync-from-device {args.install_deps_on_device}")

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
                    no_mount=args.no_mount,
                    workspace_root=workspace_root
                )

                # Install dependencies if requested
                if args.install_deps:
                    logger.info("📦 Installing workspace dependencies on device...")
                    if not builder.install_dependencies(args.rosdep_args):
                        logger.error("❌ Failed to install dependencies")
                        return 1

            elif args.method == 'sdk':
                # Yocto / OpenEmbedded SDK installed on this host
                if not args.sdk_env:
                    logger.error("❌ --sdk-env is required for sdk method")
                    logger.error("💡 Example: --sdk-env /opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux")
                    return 1

                if args.install_deps:
                    logger.warning(
                        "⚠ Ignoring --install-deps: an SDK's sysroot is fixed when the SDK is "
                        "built. Add the dependencies to the Yocto image and rebuild the SDK.")

                from colcon_buildx.sdk import SdkBuilder
                builder = SdkBuilder(
                    env_setup=args.sdk_env,
                    build_base=args.build_base,
                    install_base=args.install_base,
                    toolchain_file=args.toolchain,
                    emit_mixin=args.emit_mixin,
                    workspace_root=workspace_root
                )

            elif args.method == 'docker':
                # Docker-based cross-compilation
                if not args.docker_image:
                    logger.error("❌ --docker-image is required for docker method")
                    logger.error("💡 Example: --docker-image ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy")
                    return 1

                from colcon_buildx.docker import DockerBuilder

                builder = DockerBuilder(
                    image=args.docker_image,
                    platform=args.docker_platform,
                    build_base=args.build_base,
                    install_base=args.install_base,
                    use_base_image=args.use_base_image,
                    toolchain=args.toolchain,
                    workspace_root=workspace_root
                )

                # Sync from device if requested (standalone operation)
                if args.sync_from_device:
                    logger.info(f"📦 Syncing packages from device: {args.sync_from_device}")
                    synced_image = builder.create_synced_image(args.sync_from_device)
                    if not synced_image:
                        logger.error("❌ Failed to create synced image")
                        return 1
                    logger.info("✅ Package sync complete")
                    print("ℹ️  Next, build: colcon buildx picks up the synced image by itself")
                    # This is a standalone operation, exit after completion
                    return 0

                # Install dependencies if requested (with warning for Docker method)
                if args.install_deps:
                    # One warning, so that the advice stays together with it.
                    logger.warning(
                        "⚠ --install-deps installs dependencies into a local copy of the "
                        "Docker image only; the board will NOT have them.\n"
                        "  To install them on the board and build against the same versions, "
                        "with SSH_TARGET such as ubuntu@10.42.0.3:\n"
                        "    1. colcon buildx --install-deps-on-device SSH_TARGET\n"
                        "    2. colcon buildx --sync-from-device SSH_TARGET\n"
                        "    3. colcon buildx")
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
                from colcon_buildx.deployment import deploy
                logger.info(f"🚀 Deploying to {args.deploy_target}...")
                deploy_result = deploy(args.install_base, args.deploy_target, workspace_root)
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
