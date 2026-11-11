# colcon buildx and the OEROS images

This page is for the people who build the OEROS images. It covers what colcon buildx needs from an SDK image, and what it works around in the images published on 30 Oct 2026. Each workaround comes with its fix in meta-ros or meta-oeros. colcon buildx checks for each problem before it applies the workaround, so the workarounds turn themselves off as the images are fixed.

## What colcon buildx needs from an SDK image

- **An OE/Yocto SDK**: an `environment-setup-*` script, the target sysroot, and the cross toolchain, wherever `populate_sdk` installed them. colcon buildx finds the script under `/usr/local/*/` and `/opt/`, or takes the path from the `org.smarobix.buildx.env-setup` [label](labels.md).
- **ROS 2 in the target sysroot**, under `/opt/ros/<distro>`.
- **A label that marks the image as an SDK**: `io.oeros.sdk=cross`, which the OEROS images already carry, or `org.smarobix.buildx.kind=oe-sdk`. The image must be for the architecture of the computer it runs on (`io.oeros.sdk-host-arch`).

The build tools come from the SDK itself for now: its `cmake`, `ninja`, `python3` and `colcon`. colcon buildx brings a shell. The direction agreed on 11 Nov 2026 is that SDK images carry no build tools and colcon stays with the developer. colcon buildx's prepared layer is where those tools would come from. That is the next step; it is not implemented yet.

## What colcon buildx works around in the 30 Oct images

Verified with `oeros-sdk-cross:lyrical-arm64-20261030` on x86_64 Linux and `oeros-sdk-target:lyrical-arm64-20261030` on Apple silicon. In both cases the result ran in `oeros-ros-base:lyrical-arm64-20261030`.

| What happens with the image as published | What colcon buildx does | Fix upstream |
|---|---|---|
| **No ROS package configures.** `rcutils` exports `ament_cmake_ros_core`, which the images do not contain. meta-ros maps the dependency to `ament-cmake-ros-core-native`, which serves the image's own build only. Affects `oeros-sdk-cross` and `oeros-sdk-target`. | Builds `ament_cmake_ros_core` (CMake files only) from `ros2/ament_cmake_ros` at the version of the image's `ament_cmake_ros`, into the target's `/opt/ros/<distro>`. | Add `ament-cmake-ros-core` to `ROS_SDK_TARGET_PACKAGES` in `meta-ros2-{kilted,lyrical,rolling}/conf/ros-distro/include/*/ros-sdk.inc`, and to the dev and target images. Jazzy and Humble are not affected. |
| **The cross image does not start.** `/usr/bin/sh`, `/usr/bin/bash` and `/usr/bin/env` point into the SDK at files that do not exist. The SDK's own `python3` is a `#!/bin/bash` wrapper. | Adds a static BusyBox, points the broken links at it, and runs the `#!/bin/bash` wrappers in its `sh`. | Add `nativesdk-bash` (and `nativesdk-coreutils`) to the SDK, or point the image's links at a shell the image has. |
| **No `ros-sdk-env` for Lyrical.** meta-ros adds `nativesdk-ros-sdk-env` to Jazzy's SDK list only, so `OE_CMAKE_TOOLCHAIN_FILE`, `PYTHON_SOABI` and the ROS environment are not set. | Sets what `ros-sdk-env` would set, with the target's ROS setup sourced from the sysroot. | Add `nativesdk-ros-sdk-env` to `ROS_SDK_HOST_PACKAGES` for Humble, Kilted, Lyrical and Rolling, as for Jazzy. |
| **CMake picks the target's `ninja`.** The sysroot carries aarch64 `cmake`, `make` and `ninja`, and the toolchain file lets CMake search it for programs. | Its toolchain wrapper sets `CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER`. | Set the same in the SDK's toolchain, or keep build tools out of the target sysroot. |
| **Binaries from the dev image need `libatomic.so.1`**, which `oeros-ros-base` does not ship. `rcutils` exports `-latomic`, and the dev image's gcc links without `--as-needed`, which Yocto builds use by default. | Links with `-Wl,--as-needed` in images that run as the target. | Default `LDFLAGS` with `--as-needed` in the dev and target images, or ship `libatomic` in the runtime images. |
| **Python extensions cannot find `Python.h` and get the build host's suffix.** FindPython asks the SDK's own Python, whose sysroot has no headers, and an x86_64 SDK names pybind11 modules for x86_64. | Its toolchain wrapper points `Python3_INCLUDE_DIR` at the target sysroot and names modules with `PYTHON_SOABI`, as meta-ros image builds do with `-DPYTHON_SOABI`. | Nothing to fix in the images. `ros-sdk-env` exports `PYTHON_SOABI`; a consumer has to pass it to CMake. |

## The SDK's scope

meta-ros SDKs carry the C and C++ message generators only (`ros-sdk.inc`, every distro). Message packages built with an SDK therefore get no Python bindings. `rclpy` nodes and the `ros2` CLI on the robot cannot use them; such message packages belong in the image, as recipes. Python nodes themselves need no cross-build. `oeros-sdk-target` includes the Python generator, so messages built with it work from Python too.

## Trying it

```bash
pip install "git+https://github.com/smarobix/smarobix-colcon-buildx.git"
cd <workspace root>
printf 'method = docker\ndocker_image = ghcr.io/oerosproject/oeros-sdk-cross:lyrical-arm64\n' > .buildx.conf
colcon buildx
```

On an arm64 computer, use `oeros-sdk-target:lyrical-arm64`. colcon buildx prints each step of the preparation the first time; `docker image ls colcon-buildx` lists the images it made.
