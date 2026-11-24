# SPDX-FileCopyrightText: 2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0
#
# Runs once while colcon-buildx prepares an image whose rcutils exports ament_cmake_ros_core but
# which does not have it (meta-ros Kilted and later). The package is CMake files only, no compiled
# code, so building it with the image's own cmake and no cross toolchain gives exactly what the
# target would have installed. The source, ros2/ament_cmake_ros at the version of the image's
# ament_cmake_ros, was downloaded by the Dockerfile.

set -e
export PATH="$PATH:/opt/buildx/bin"
. /opt/buildx/env.sh
prefix="$BUILDX_SYSROOT/opt/ros/$ROS_DISTRO"

cd /opt/buildx/src
tar -xzf ament_cmake_ros.tar.gz
src=$(ls -d /opt/buildx/src/ament_cmake_ros-*/ament_cmake_ros_core)
generator=""
command -v ninja >/dev/null 2>&1 && generator="-G Ninja"
# shellcheck disable=SC2086
cmake -S "$src" -B /tmp/ament_cmake_ros_core $generator \
  -DCMAKE_TOOLCHAIN_FILE= \
  -DCMAKE_INSTALL_PREFIX="$prefix" \
  -DCMAKE_PREFIX_PATH="$prefix" \
  -DBUILD_TESTING=OFF
cmake --build /tmp/ament_cmake_ros_core
cmake --install /tmp/ament_cmake_ros_core
rm -rf /tmp/ament_cmake_ros_core /opt/buildx/src
echo "colcon-buildx: added ament_cmake_ros_core to $prefix"
