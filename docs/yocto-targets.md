# Yocto targets

Boards running a Yocto image built with [meta-ros](https://github.com/ros/meta-ros) need binaries linked against that image's own libraries. Binaries built in an Ubuntu or Debian image won't run on them; the images site explains why in [Ubuntu vs Yocto](https://smarobix.github.io/smarobix-buildx-images/explanation/ubuntu-vs-yocto/).

This page covers what colcon-buildx does for these boards. The images site's [meta-ros tutorial](https://smarobix.github.io/smarobix-buildx-images/tutorials/meta-ros/) walks through the whole thing on a Kria KV260: creating a workspace, building it all three ways, and running it on the board.

## Three ways to build

All three produce binaries for the board's Yocto image. The published images and SDKs are for ROS 2 Jazzy on the Kria K26 (KV260 and KR260) and the Raspberry Pi 5; the images site's [target reference](https://smarobix.github.io/smarobix-buildx-images/reference/targets/) lists them.

| Route | K26 | Raspberry Pi 5 | Host | Python message bindings |
|---|---|---|---|---|
| SDK image | `k26-oesdk-jazzy` | `rpi5-oesdk-jazzy` | any, with Docker | no |
| Dev container | `k26-yocto-jazzy` | `rpi5-yocto-jazzy` | any, with Docker | yes |
| SDK on the host | `environment-setup-cortexa72-cortexa53-oe-linux` | `environment-setup-cortexa76-oe-linux` | arm64 Linux | no |

The commands below are for the K26. For a Pi 5, use the names from the other column.

**SDK image.** A cross SDK in a container, recognised by its [labels](reference/labels.md). On x86_64, pull it for arm64 first, as [Install](install.md#sdk-images-on-x86_64) describes.

```bash
colcon buildx --method docker \
  --docker-image ghcr.io/smarobix/smarobix-buildx-images:k26-oesdk-jazzy \
  --cmake-args -DBUILD_TESTING=OFF
```

**Dev container.** An aarch64 image of the board's own userspace plus compilers and `-dev` packages, which bitbake builds from the same configuration as the board image (recipe `ros-dev-container`). It compiles natively, under QEMU on x86_64, and it is the only route that also generates Python message bindings. Its kind label is `yocto-native`, which colcon-buildx handles like any image that runs as the target.

```bash
colcon buildx --method docker --docker-platform linux/arm64 \
  --docker-image ghcr.io/smarobix/smarobix-buildx-images:k26-yocto-jazzy \
  --cmake-args -DBUILD_TESTING=OFF
```

**SDK on the host.** `--method sdk`, with the SDK installed in `/opt/ros-sdk`. The published SDK installers need an arm64 Linux host; the tutorial shows how to [download and install one](https://smarobix.github.io/smarobix-buildx-images/tutorials/meta-ros/).

```bash
colcon buildx --method sdk \
  --sdk-env /opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux \
  --cmake-args -DBUILD_TESTING=OFF
```

The SDK's environment script is named after the CPU tune: `cortexa72-cortexa53` for the K26, `cortexa76` for the Pi 5. The suffix is `-oe-linux`.

`-DBUILD_TESTING=OFF` is there because `ros2 pkg create` adds lint tests, which a cross build can't run. The dev container also ships the linters' CMake hooks without the linters themselves, so configuring with tests on fails there.

## What the SDK has to contain

Both SDK routes, the SDK image and `--method sdk`, need an SDK built with **`ros-sdk-env`** ([ros/meta-ros@1be4737](https://github.com/ros/meta-ros/commit/1be4737)). It sets `OE_CMAKE_TOOLCHAIN_FILE`, `PYTHON_SOABI` and `AMENT_PREFIX_PATH`. Nothing in meta-ros pulls it into an SDK by itself, so build the SDK from `ros2-image-sdktest` with:

```text
TOOLCHAIN_HOST_TASK:append = " nativesdk-ros-sdk-env"
```

Without it, colcon-buildx stops with an error that says so. The published SDKs and SDK images include it. `--method sdk` also accepts `--toolchain` to name the toolchain file directly.

meta-ros SDKs don't include `rosidl_generator_py`, so interface packages get C and C++ code only with either SDK route.

## What colcon-buildx adds

**A toolchain wrapper.** The SDK's stock CMake toolchain file is fine for building one library against the target sysroot, but not for a workspace of ROS packages that depend on each other. colcon-buildx writes `cross_build/buildx-toolchain.cmake`, which includes the SDK's file and then fixes three things:

1. The stock file never normalises its sysroot path, and CMake compares paths as text. A path inside the sysroot that is spelled differently gets re-rooted into one that doesn't exist, and is dropped. The wrapper normalises the search roots.
2. `find_package()` may search only the target sysroot, so a package can't find the packages built before it in the same workspace. The wrapper adds the install directory to the search roots.
3. `ros-sdk-env` exports `AMENT_PREFIX_PATH` but not `CMAKE_PREFIX_PATH`, so the first `find_package(ament_cmake)` fails. The wrapper adds the `AMENT_PREFIX_PATH` entries to `CMAKE_PREFIX_PATH`.

The wrapper is rewritten only when its contents change, so an incremental build doesn't reconfigure every package. `--emit-mixin` writes the same settings as a colcon mixin for plain `colcon build`; see [Backends](backends.md#using-the-sdk-settings-with-plain-colcon).

**Ninja.** meta-ros SDKs ship `ninja` but not `make`, so colcon-buildx sets `CMAKE_GENERATOR=Ninja` when the SDK has ninja and you haven't set `CMAKE_GENERATOR` yourself.

## Deploying and sourcing on the board

A minimal Yocto image has no bash, only BusyBox `ash`, and may have no rsync, which `--deploy` needs. The tutorial copies the install tree with tar over SSH instead. Replace `10.42.0.3` with your board's address:

```bash
# from the workspace root on the build host
tar -cf - cross_install \
  | ssh root@10.42.0.3 'rm -rf /opt/demo && mkdir -p /opt/demo && tar -C /opt/demo -xf -'
```

On the board, source `setup.sh`, not `setup.bash`. A POSIX shell can't find the path of a script it is sourcing, so colcon's scripts fall back to the path used at build time, not the one on the board. Tell them where the install tree is now with `COLCON_CURRENT_PREFIX`, and source ROS itself first:

```sh
. /opt/ros/jazzy/setup.sh
COLCON_CURRENT_PREFIX=/opt/demo/cross_install . /opt/demo/cross_install/local_setup.sh
```

## Rebuilding the images

The board images aren't published. They, the SDKs and the dev containers are built from the `yocto/` configuration in the images repository, and the SDK images from those SDKs. The images site describes [how to rebuild them](https://smarobix.github.io/smarobix-buildx-images/maintain/yocto/).
