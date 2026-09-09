"""Yocto / OpenEmbedded SDK cross-compilation builder.

Uses an SDK produced by ``bitbake -c populate_sdk`` and installed on this host,
the way meta-ros intends it to be used. The SDK carries the cross toolchain and
target sysroot, so nothing here runs target code and no emulation is involved.

The environment is set up by sourcing the SDK's own scripts rather than by
reconstructing it: ``ros-sdk-env.sh`` derives PYTHON_SOABI at runtime from a
real extension module in the target sysroot, which is what removes the
hand-maintained SOABI strings and host libpython symlinks that cross-compiling
against a vendor sysroot otherwise needs.
"""

import os
import shlex
import subprocess
import sys
from pathlib import Path

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)

# Variables read back out of the sourced SDK environment.
PROBE_VARS = (
    'OE_CMAKE_TOOLCHAIN_FILE',
    'OECORE_NATIVE_SYSROOT',
    'OECORE_TARGET_SYSROOT',
    'PYTHON_SOABI',
    'ROS_DISTRO',
)


class SdkBuilder:
    """Handles cross-compilation using an OE/Yocto SDK installed on this host."""

    def __init__(self, env_setup, build_base, install_base,
                 toolchain_file=None, emit_mixin=False):
        """
        Initialize SDK builder.

        Args:
            env_setup: Colon-separated list of SDK scripts to source, in order
            build_base: Build directory
            install_base: Install directory
            toolchain_file: Override for the SDK's own CMake toolchain file
            emit_mixin: Also write a colcon mixin describing these settings
        """
        self.env_setup = [p for p in str(env_setup).split(':') if p]
        self.build_base = build_base
        self.install_base = install_base
        self.toolchain_file = toolchain_file
        self.emit_mixin = emit_mixin
        self.workspace_root = self._find_workspace_root()

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

    def check_host(self):
        """Yocto SDK installers are Linux binaries; nothing else can run them."""
        if sys.platform.startswith('linux'):
            return True
        logger.error(f"❌ --method sdk requires a Linux host (this is {sys.platform})")
        logger.error("💡 An OE/Yocto SDK is a Linux binary and cannot run here.")
        logger.info("ℹ Use a cross SDK container instead, which runs on any host:")
        logger.info("    colcon buildx --method docker --docker-image <oe-sdk image>")
        return False

    def check_env_setup(self):
        """Confirm every script we are about to source exists."""
        missing = [p for p in self.env_setup if not Path(p).is_file()]
        for path in missing:
            logger.error(f"❌ SDK environment script not found: {path}")
        if missing:
            logger.info("💡 Point --sdk-env at the SDK's environment-setup-* script")
        return not missing

    def _source_prefix(self):
        """Shell snippet that sources every configured SDK script."""
        return ' && '.join(f'. {shlex.quote(p)}' for p in self.env_setup)

    def write_toolchain_wrapper(self, toolchain):
        """
        Wrap the SDK toolchain so the workspace can find its own packages.

        The SDK ships the stock OE toolchain file, which sets

            CMAKE_FIND_ROOT_PATH               <target sysroot>
            CMAKE_FIND_ROOT_PATH_MODE_PACKAGE  ONLY

        so find_package() searches the sysroot and nothing else. Any package
        that depends on another package in the same workspace then fails to
        configure. Appending the colcon install prefix to the find roots is the
        smallest fix that keeps the SDK's own settings intact.
        """
        build_dir = self.workspace_root / self.build_base
        build_dir.mkdir(parents=True, exist_ok=True)
        install_dir = self.workspace_root / self.install_base

        wrapper = build_dir / 'buildx-toolchain.cmake'
        wrapper.write_text(
            'include("%s")\n'
            'list(APPEND CMAKE_FIND_ROOT_PATH "%s")\n' % (toolchain, install_dir))
        return wrapper

    def probe_env(self):
        """Source the SDK scripts and read back the variables we care about."""
        script = (
            f'{self._source_prefix()} && '
            f'for v in {" ".join(PROBE_VARS)}; do '
            'printf "%s=%s\\n" "$v" "${!v-}"; '
            'done'
        )
        result = subprocess.run(
            ['bash', '-c', script], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("❌ Failed to source the SDK environment")
            logger.error(result.stderr.strip())
            return None

        env = {}
        for line in result.stdout.splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                env[key] = value
        return env

    def write_mixin(self, env):
        """
        Write a colcon mixin describing this SDK's cross-build settings.

        A sysroot, a toolchain triple and a Python SOABI are the same three
        inputs every cross-build here needs, whichever backend produced them.
        Emitting them as a mixin makes the configuration usable with a plain
        `colcon build --mixin`, and composable with the mixins krs_firmware
        generates, rather than only from this extension.
        """
        toolchain = self.toolchain_file or env.get('OE_CMAKE_TOOLCHAIN_FILE')
        cmake_args = [f'-DCMAKE_TOOLCHAIN_FILE={self.write_toolchain_wrapper(toolchain)}']
        if env.get('PYTHON_SOABI'):
            cmake_args.append(f'-DPYTHON_SOABI={env["PYTHON_SOABI"]}')

        mixin_dir = self.workspace_root / '.buildx' / 'mixin'
        mixin_dir.mkdir(parents=True, exist_ok=True)

        body = 'build:\n  buildx:\n    merge-install: true\n    cmake-args:\n'
        body += ''.join(f'      - "{arg}"\n' for arg in cmake_args)
        (mixin_dir / 'buildx.mixin').write_text(body)
        (mixin_dir / 'index.yaml').write_text('mixin:\n  - buildx.mixin\n')

        logger.info(f"✓ Wrote colcon mixin to {mixin_dir}")
        logger.info("ℹ Register it with:")
        logger.info(f"    colcon mixin add buildx file://{mixin_dir}/index.yaml")
        logger.info("    colcon mixin update buildx")

    def build(self, extra_args=None):
        """Execute colcon build inside the sourced SDK environment."""
        extra_args = extra_args or []

        if not self.check_host():
            return 1
        if not self.env_setup:
            logger.error("❌ No SDK environment script configured")
            return 1
        if not self.check_env_setup():
            return 1

        env = self.probe_env()
        if env is None:
            return 1

        toolchain = self.toolchain_file or env.get('OE_CMAKE_TOOLCHAIN_FILE')
        if not toolchain:
            logger.error(
                "❌ OE_CMAKE_TOOLCHAIN_FILE is unset after sourcing the SDK environment")
            logger.error(
                "💡 The SDK predates ros-sdk-env (ros/meta-ros@1be4737), or is missing it.")
            logger.info("ℹ Pass --toolchain to point at the toolchain file directly.")
            return 1

        # Printed rather than logged: which sysroot and SOABI a cross-build
        # actually picked up is the thing you need to see, and colcon keeps
        # logger.info off the console by default.
        if env.get('ROS_DISTRO'):
            print(f"✓ Using ROS {env['ROS_DISTRO']} from the SDK")
        if env.get('PYTHON_SOABI'):
            print(f"✓ Target Python SOABI: {env['PYTHON_SOABI']}")
        print(f"✓ Toolchain file: {toolchain}")

        if self.emit_mixin:
            self.write_mixin(env)

        wrapper = self.write_toolchain_wrapper(toolchain)
        build_dir = self.workspace_root / self.build_base

        # CMAKE_TOOLCHAIN_FILE goes through the environment rather than
        # --cmake-args, which would collide with a user-supplied one. CMake has
        # honoured the environment variable since 3.21.
        script = (
            'set -e && '
            f'{self._source_prefix()} && '
            f'export ROS_WORKSPACE={shlex.quote(str(self.workspace_root))} && '
            f'export CMAKE_TOOLCHAIN_FILE={shlex.quote(str(wrapper))} && '
            'colcon build'
            f' --build-base {shlex.quote(str(build_dir))}'
            f' --install-base {shlex.quote(str(self.workspace_root / self.install_base))}'
            f' --merge-install {shlex.join(extra_args)}'
        )

        logger.info("🔨 Building against the SDK...")
        logger.info(f"   ROS_WORKSPACE: {self.workspace_root}")
        logger.info(f"   Build args: {' '.join(extra_args)}")

        try:
            return subprocess.run(['bash', '-c', script]).returncode
        except KeyboardInterrupt:
            logger.info("\n⚠️  Build interrupted by user")
            return 130
