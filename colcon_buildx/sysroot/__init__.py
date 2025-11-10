"""SSHFS-based cross-compilation builder."""

import os
import subprocess
from pathlib import Path

from colcon_core.logging import colcon_logger

logger = colcon_logger.getChild(__name__)


class SysrootBuilder:
    """Handles cross-compilation using SSHFS-mounted sysroot."""

    def __init__(self, sysroot_host, sysroot_mount, toolchain_file,
                 build_base, install_base, no_mount=False):
        """
        Initialize sysroot builder.

        Args:
            sysroot_host: Hostname/IP of target board (e.g., kria-vision-home)
            sysroot_mount: Local mount point for sysroot
            toolchain_file: Path to CMake toolchain file
            build_base: Build directory
            install_base: Install directory
            no_mount: Skip mounting (sysroot already mounted)
        """
        self.sysroot_host = sysroot_host
        self.sysroot_mount = Path(sysroot_mount).expanduser()
        self.toolchain_file = Path(toolchain_file).resolve()
        self.build_base = build_base
        self.install_base = install_base
        self.no_mount = no_mount
        self._mounted_by_us = False

    def is_mounted(self):
        """Check if sysroot is currently mounted."""
        result = subprocess.run(
            ['mountpoint', '-q', str(self.sysroot_mount)],
            capture_output=True
        )
        return result.returncode == 0

    def mount_sysroot(self):
        """Mount the sysroot via SSHFS."""
        if self.no_mount:
            if not self.is_mounted():
                logger.error(f"❌ Sysroot not mounted at {self.sysroot_mount} and --no-mount specified")
                return False
            logger.info(f"✓ Using pre-mounted sysroot at {self.sysroot_mount}")
            return True

        # Create mount point
        self.sysroot_mount.mkdir(parents=True, exist_ok=True)

        if self.is_mounted():
            logger.info(f"✓ Sysroot already mounted at {self.sysroot_mount}")
            return True

        logger.info(f"📡 Mounting sysroot from {self.sysroot_host}...")
        cmd = [
            'sshfs',
            f'{self.sysroot_host}:/',
            str(self.sysroot_mount),
            '-o', 'allow_other,default_permissions'
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"✓ Sysroot mounted at {self.sysroot_mount}")
            self._mounted_by_us = True
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ SSHFS mount failed: {e.stderr}")
            logger.error("💡 Ensure SSHFS is installed: brew install macfuse sshfs (macOS) or apt install sshfs (Linux)")
            logger.error(f"💡 Ensure SSH access works: ssh {self.sysroot_host}")
            return False
        except FileNotFoundError:
            logger.error("❌ SSHFS not found. Install it first:")
            logger.error("   macOS: brew install macfuse sshfs")
            logger.error("   Linux: sudo apt install sshfs")
            return False

    def unmount_sysroot(self):
        """Unmount the sysroot."""
        if not self._mounted_by_us or self.no_mount:
            return True

        if not self.is_mounted():
            return True

        logger.info("🔻 Unmounting sysroot...")
        try:
            subprocess.run(['fusermount', '-u', str(self.sysroot_mount)], check=True)
            logger.info("✓ Sysroot unmounted")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠️  Failed to unmount sysroot: {e}")
            return False
        except FileNotFoundError:
            # Try umount on macOS
            try:
                subprocess.run(['umount', str(self.sysroot_mount)], check=True)
                logger.info("✓ Sysroot unmounted")
                return True
            except subprocess.CalledProcessError:
                logger.warning(f"⚠️  Failed to unmount sysroot")
                return False

    def setup_environment(self):
        """Set up environment variables for cross-compilation."""
        env = os.environ.copy()

        # Basic sysroot paths
        env['CMAKE_SYSROOT'] = str(self.sysroot_mount)
        env['SYSROOT_PATH'] = str(self.sysroot_mount)

        # ROS setup - try to detect ROS distro
        ros_distros = ['jazzy', 'humble', 'iron', 'rolling']
        for distro in ros_distros:
            ros_path = self.sysroot_mount / 'opt' / 'ros' / distro
            if ros_path.exists():
                env['CMAKE_PREFIX_PATH'] = f'{ros_path}:{self.sysroot_mount}/usr/lib/aarch64-linux-gnu/cmake'
                logger.info(f"✓ Detected ROS {distro} in sysroot")
                break

        # Python cross-compile support (try multiple versions)
        python_versions = ['3.12', '3.11', '3.10', '3.9']
        for py_ver in python_versions:
            python_path = self.sysroot_mount / 'usr' / 'bin' / f'python{py_ver}'
            if python_path.exists():
                env['PYTHON_EXECUTABLE'] = str(python_path)
                env['PYTHON_INCLUDE_DIR'] = str(self.sysroot_mount / 'usr' / 'include' / f'python{py_ver}')
                env['PYTHON_LIBRARY'] = str(self.sysroot_mount / 'usr' / 'lib' / 'aarch64-linux-gnu' / f'libpython{py_ver}.so')
                logger.info(f"✓ Using Python {py_ver} from sysroot")
                break

        # Disable Python bindings generation (often problematic in cross-compilation)
        env['AMENT_IGNORE_BUILTIN_GENERATORS'] = 'rosidl_generator_py'

        # OpenCV paths (if custom installation exists)
        opencv_path = self.sysroot_mount / 'opt' / 'install'
        if opencv_path.exists():
            env['OpenCV_DIR'] = str(opencv_path / 'lib' / 'cmake' / 'opencv4')
            env['LD_LIBRARY_PATH'] = f'{opencv_path / "lib"}:{env.get("LD_LIBRARY_PATH", "")}'
            logger.info(f"✓ Using custom OpenCV from {opencv_path}")

        # Colcon log path
        env['COLCON_LOG_PATH'] = f'{self.build_base}/../log'

        return env

    def build(self, extra_args=None):
        """Execute colcon build with cross-compilation settings."""
        extra_args = extra_args or []

        # Mount sysroot
        if not self.mount_sysroot():
            return 1

        try:
            # Validate toolchain file
            if not self.toolchain_file.exists():
                logger.error(f"❌ Toolchain file not found: {self.toolchain_file}")
                return 1

            # Build command
            cmd = [
                'colcon', 'build',
                '--build-base', self.build_base,
                '--install-base', self.install_base,
                '--cmake-args',
                f'-DCMAKE_TOOLCHAIN_FILE={self.toolchain_file}',
                '-DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=ONLY',
                '-DPython3_FIND_STRATEGY=LOCATION',
            ] + extra_args

            logger.info(f"🔨 Building with: colcon build {' '.join(extra_args)}")

            # Set up environment and run
            env = self.setup_environment()
            result = subprocess.run(cmd, env=env)

            return result.returncode

        finally:
            # Always try to unmount
            self.unmount_sysroot()
