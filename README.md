# colcon-buildx

A colcon extension for cross-compiling ROS 2 workspaces for embedded ARM boards, either against a board-specific Docker image or against a Yocto/OpenEmbedded SDK (such as one built with [meta-ros](https://github.com/ros/meta-ros)). Targets `arm64` (aarch64) and `armhf` (ARMv7-A hard-float), with package version sync from the target device and optional rsync deploy.

## What this does

`colcon buildx` runs your colcon build inside a Docker image that already has ROS 2 installed for the target architecture. The host stays clean (no toolchain on your laptop), the image carries the matching libc, ROS, and DDS, and the build artifacts land in `cross_install/` ready to copy to the board.

It plugs into colcon as a verb, so anything you would normally pass to `colcon build` (such as `--packages-select`, `--cmake-args`) is forwarded.

## Supported architectures

| Architecture | Tested on | Generally compatible with |
|---|---|---|
| `arm64` | Kria K26 (Humble, Jazzy) | NVIDIA Jetson, Raspberry Pi 4 / 5 (64-bit), other Cortex-A53 / A72 / A76 boards |
| `armhf` | Pynq-Z1, Pynq-Z2 (Humble, Jazzy) | Raspberry Pi 32-bit, other Cortex-A7 / A9 boards running an `arm32v7` user space |

The architecture is selected at build time by `docker_platform` (`linux/arm64` or `linux/arm/v7`) and by which Docker image you point at.

## Backends

There are three backends. Docker is the recommended path and the one used in CI. SSHFS sysroot is currently experimental and untested with the latest changes (the code path still hardcodes `aarch64-linux-gnu` sysroot layout, so it will not work as-is on `armhf`).

| Backend | Status | When to use |
|---|---|---|
| `docker` | Recommended, used in CI | You have a Docker image for the target board — either an image that runs *as* the target architecture, or a cross SDK image (see [Yocto / meta-ros targets](#yocto--meta-ros-targets)) |
| `sdk` | New | You have a Yocto/OpenEmbedded SDK installed on a Linux host |
| `sysroot` | Experimental, untested | You want to build against the live filesystem of a running board over SSHFS |

Most of this README covers the Docker backend with images that run as the target architecture. Boards running a Yocto image have their own section.

## Where the Docker images come from

The companion repository [`smarobix/smarobix-buildx-images`](https://github.com/smarobix/smarobix-buildx-images) builds and publishes board-specific Docker images that work with `colcon buildx` out of the box (Kria K26, Pynq-Z1 / Pynq-Z2, Raspberry Pi / Debian). You can also bring your own. Any image with ROS 2 installed under `/opt/ros/<distro>` and a working colcon will work.

## Yocto / meta-ros targets

Boards running a Yocto/meta-ros image (rather than Ubuntu) need binaries linked against the **meta-ros sysroot**; binaries from an Ubuntu-based image won't run on them. There are three ways to build for them. The first two cross-compile with the meta-ros SDK; the third compiles natively in a dev container built by bitbake. All three produce binaries that run on the board.

**On a Linux host with the SDK installed** (`--method sdk`):

```bash
colcon buildx --method sdk \
  --sdk-env /opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux
```

**From any host, with the SDK packaged as a Docker image** (`--method docker`):

```bash
colcon buildx --method docker --docker-image ghcr.io/smarobix/smarobix-buildx-images:k26-oesdk-jazzy
```

**Natively, in a dev container built by bitbake** from the same configuration as the board image (the images repo's `yocto/`, recipe `ros-dev-container`). It runs *as* the target architecture, so it goes through the normal Docker path with no cross toolchain involved. It also includes the Python message generator, so unlike the SDK routes, interface packages get Python bindings too:

```bash
colcon buildx --method docker --docker-image ghcr.io/smarobix/smarobix-buildx-images:k26-yocto-jazzy --docker-platform linux/arm64
```

An SDK image carries a cross toolchain and the target sysroot and runs on the **host** architecture. colcon-buildx recognises it by these image labels, skips `--platform`, and sources the SDK instead of `/opt/ros/<distro>/setup.bash`:

| Label | Example |
|---|---|
| `org.smarobix.buildx.kind` | `oe-sdk` |
| `org.smarobix.buildx.env-setup` | `/opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux` (colon-separated if several scripts) |
| `org.smarobix.buildx.target-platform` | `linux/arm64` |
| `org.smarobix.buildx.ros-distro` | `jazzy` |

The images repo's `dockerfiles/oesdk` builds one from a meta-ros SDK. Published images, all under `ghcr.io/smarobix/smarobix-buildx-images`:

| Board | SDK image | Dev container |
|---|---|---|
| Kria K26 (KV260 / KR260) | `k26-oesdk-jazzy` | `k26-yocto-jazzy` |
| Raspberry Pi 5 | `rpi5-oesdk-jazzy` | `rpi5-yocto-jazzy` |

What the SDK has to contain, and what colcon-buildx takes care of:

- **`ros-sdk-env`** (ros/meta-ros@1be4737). It sets `OE_CMAKE_TOOLCHAIN_FILE`, `PYTHON_SOABI` and `AMENT_PREFIX_PATH`. Nothing in meta-ros pulls it into an SDK by itself: build the SDK from `ros2-image-sdktest` with `TOOLCHAIN_HOST_TASK:append = " nativesdk-ros-sdk-env"`. Without it colcon-buildx stops with an error saying so. `--toolchain` overrides the toolchain file.
- **A toolchain wrapper.** The SDK's stock toolchain file only lets `find_package()` search the target sysroot, spells that sysroot in a form CMake doesn't match against, and never tells CMake where ROS is. colcon-buildx wraps it (`cross_build/buildx-toolchain.cmake`) so a workspace can find `ament_cmake` and its own packages. `--emit-mixin` writes the same settings as a colcon mixin for use with plain `colcon build`.
- **Ninja.** Meta-ros SDKs ship `ninja` but not `make`, so colcon-buildx uses Ninja unless you set `CMAKE_GENERATOR` yourself.
- `--method sdk` needs a **Linux** host, because the SDK is a Linux binary. On macOS, use an SDK image.
- No Python message bindings with the SDK routes: meta-ros SDKs don't ship `rosidl_generator_py`, so interface packages get C/C++ only. The dev container does generate them.

**Sourcing the result on the board.** A POSIX shell can't find its own path when sourcing a script, so colcon's scripts fall back to the path used at build time, which is a path on the build host. Point them at the deployed location, and source ROS itself first:

```sh
. /opt/ros/jazzy/setup.sh
COLCON_CURRENT_PREFIX=/opt/demo/cross_install . /opt/demo/cross_install/local_setup.sh
```

Use `setup.sh`, not `setup.bash`: minimal Yocto images often have no bash.

## Installation

```bash
pip install "git+https://github.com/smarobix/smarobix-colcon-buildx.git"
```

For local development:

```bash
git clone git@github.com:smarobix/smarobix-colcon-buildx.git
cd smarobix-colcon-buildx
pip install -e .
colcon buildx --help
```

## Prerequisites

Docker, `colcon-core`, and a target Docker image. If you are on an `x86_64` host you also need QEMU registered for the target platform so `docker run --platform=linux/arm64` (or `linux/arm/v7`) works.

```bash
# One-shot, register binfmt handlers for ARM emulation
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# Sanity check
docker run --rm --platform linux/arm64 alpine uname -m   # → aarch64
docker run --rm --platform linux/arm/v7 alpine uname -m  # → armv7l
```

`arm64` Macs (Apple Silicon) and ARM Linux hosts do not need QEMU.

## Quick start

In your ROS 2 workspace root, drop a `.buildx.conf`:

```bash
method = docker
docker_image = ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy
docker_platform = linux/arm64
deploy_target = ubuntu@10.42.0.3:~/ros2_ws/install/
```

Then build:

```bash
cd ~/my_ros2_workspace
colcon buildx
```

Output goes to `cross_build/` and `cross_install/` (kept separate from native `build/` and `install/` so the two trees do not collide). The container runs as your user, so everything it writes is yours and can be deleted without sudo. colcon's logs land in `cross_build/log/`.

For an `armhf` board (Pynq-Z1 example):

```bash
method = docker
docker_image = ghcr.io/smarobix/smarobix-buildx-images:pynq-v3.1.1-jazzy
docker_platform = linux/arm/v7
deploy_target = xilinx@192.168.2.99:~/ros2_ws/install/
```

See [`smarobix-buildx-images`](https://github.com/smarobix/smarobix-buildx-images) for the full list of available image tags.

## Configuration

Two formats are supported, both with the same keys.

`.buildx.conf` (key=value):

```bash
method = docker
docker_image = ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy
docker_platform = linux/arm64
build_base = cross_build
install_base = cross_install
deploy = false
deploy_target = ubuntu@10.42.0.3:~/ros2_ws/install/
```

`.buildx.yml` (YAML):

```yaml
method: docker
docker_image: ghcr.io/smarobix/smarobix-buildx-images:pynq-v3.1.1-jazzy
docker_platform: linux/arm/v7
build_base: cross_build
install_base: cross_install
```

Precedence: command-line flags override the config file, which overrides defaults. The tool walks up from `cwd` looking for `.buildx.conf`, `.buildx.yml`, or `.buildx.yaml` and stops at the workspace root (the directory containing `src/`).

## Package sync from the device

ROS 2 packages installed on a target board can drift away from what is in the Docker image (security updates, manual installs). `colcon buildx --sync-from-device` rebuilds a `*-synced-YYYYMMDD` tag of your image with package versions matching the device, and future builds pick it up automatically.

The recommended workflow treats the device as the source of truth:

```bash
# Update the device first so package versions are current
ssh ubuntu@10.42.0.3 'sudo apt-get update && sudo apt-get upgrade -y'

# Install the workspace's apt dependencies on the device
colcon buildx --install-deps-on-device ubuntu@10.42.0.3

# Sync the Docker image to match the device
colcon buildx --sync-from-device ubuntu@10.42.0.3

# Build (auto-uses the synced image)
colcon buildx
```

Pass `--use-base-image` to skip auto-detection and use the original tag.

## Deploy

Optional. If `deploy_target` is set (or passed via `--deploy-target`), `--deploy` rsyncs `cross_install/` to that path on the board after a successful build.

```bash
colcon buildx --deploy
colcon buildx --deploy --deploy-target ubuntu@other-board:~/ros2_ws/install/
```

## Common arguments

```bash
colcon buildx --packages-select my_pkg                                       # pass-through to colcon
colcon buildx --packages-skip rviz2 --deploy
colcon buildx --cmake-args -DCMAKE_BUILD_TYPE=Release
colcon buildx --method docker --docker-image my-registry/my:tag --docker-platform linux/arm/v7
colcon buildx --use-base-image                                               # skip synced-image detection
```

## Troubleshooting

`exec format error`: QEMU not registered. Re-run `docker run --rm --privileged multiarch/qemu-user-static --reset -p yes`.

`Could not find ROS 2 workspace`: `cwd` has no `src/` and neither does any parent. Run from the workspace root.

`Docker image not found`: not authenticated to the registry, or the image is on a private registry. Run `docker login` first.

Synced image not picked up: confirm it exists with `docker images | grep synced`. The auto-detect matches `<base-tag>-synced-<YYYYMMDD>`. If the base tag was renamed, re-run `--sync-from-device`.

`rosdep init` fails inside the container: the Docker image is responsible for `rosdep init` / `rosdep update` at build time. If you are bringing your own image, make sure rosdep is initialised there.

`OE_CMAKE_TOOLCHAIN_FILE unset after sourcing the SDK environment`: the SDK was built without `ros-sdk-env`. Add `nativesdk-ros-sdk-env` to `TOOLCHAIN_HOST_TASK` and rebuild it (see [Yocto / meta-ros targets](#yocto--meta-ros-targets)).

`unable to find a build program corresponding to "Unix Makefiles"`: you set `CMAKE_GENERATOR` to Makefiles against an SDK without `make`. Unset it to let colcon-buildx use the SDK's Ninja.

Builds are slow: the tool reuses persistent build / install directories for fast incremental builds. Avoid blowing them away unless you need to. Do not pass `--rebuild-container` (or its equivalents) unless you are debugging the image itself.

## Legacy `kria-build` script

The repository still ships a 269-line standalone bash script at `bin/kria-build`. It predates the colcon extension, is hardcoded for Kria and `arm64`, and is kept in tree so older deployment scripts keep working. New work should use `colcon buildx`. The standalone script will be removed once nothing depends on it.

## License

Apache License 2.0, as declared in `pyproject.toml`.
