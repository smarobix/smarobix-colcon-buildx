# SPDX-FileCopyrightText: 2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0
#
# Runs once per image, in a copy of it with a static busybox added, and prints what colcon-buildx
# needs to know as KEY=VALUE lines. BusyBox sh; nothing from the image itself has to work.
# BUILDX_ENV_SETUP: the image's env-setup label, if it has one.

env_setup=""
for f in $(echo "${BUILDX_ENV_SETUP:-}" | tr ':' ' '); do
  case "$f" in */environment-setup-*) env_setup=$f; break ;; esac
done
if [ -z "$env_setup" ]; then
  # OE/Yocto SDKs install to a directory of their own; the OEROS images use
  # /usr/local/oe-sdk-hardcoded-buildpath, populate_sdk defaults to /opt/<distro>/<version>.
  for f in /usr/local/*/environment-setup-* /opt/*/environment-setup-* /opt/*/*/environment-setup-*; do
    if [ -f "$f" ]; then env_setup=$f; break; fi
  done
fi

sysroot=""
native=""
arch=""
if [ -n "$env_setup" ]; then
  value() { sed -n "s/^export $1=//p" "$env_setup" | head -n 1 | tr -d '"'; }
  sysroot=$(value SDKTARGETSYSROOT)
  native=$(value OECORE_NATIVE_SYSROOT)
  arch=$(value OECORE_TARGET_ARCH)
fi
echo "ENV_SETUP=$env_setup"
echo "SYSROOT=$sysroot"
echo "NATIVE_SYSROOT=$native"
echo "TARGET_ARCH=$arch"
[ -n "$native" ] && [ -f "$native/environment-setup.d/ros-sdk-env.sh" ] && echo "ROS_SDK_ENV=1"

distro=$(ls "$sysroot/opt/ros" 2>/dev/null | head -n 1)
echo "ROS_DISTRO=$distro"

python=$(cd "$sysroot/usr/lib" 2>/dev/null && ls -d python3.* 2>/dev/null | head -n 1)
echo "PYTHON=$python"
soabi=$(ls "$sysroot/usr/lib/$python/lib-dynload/" 2>/dev/null \
  | sed -n 's/^[^.]*\.\(cpython-[^.]*\)\.so$/\1/p' | head -n 1)
echo "PYTHON_SOABI=$soabi"

# Kilted and later: rcutils exports ament_cmake_ros_core, which meta-ros stages for the build only
# (ament-cmake-ros-core-native), so it is missing from the images and SDKs built from them.
ros="$sysroot/opt/ros/$distro"
if [ -n "$distro" ] && [ ! -d "$ros/share/ament_cmake_ros_core" ] \
   && grep -qs ament_cmake_ros_core "$ros"/share/rcutils/cmake/*.cmake; then
  version=$(sed -n 's:.*<version>\(.*\)</version>.*:\1:p' "$ros/share/ament_cmake_ros/package.xml" 2>/dev/null | head -n 1)
  echo "AMENT_CMAKE_ROS_CORE=${version:-unknown}"
fi
