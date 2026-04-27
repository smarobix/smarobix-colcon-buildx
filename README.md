# colcon-buildx

A colcon extension for cross-compiling ROS 2 workspaces against board-specific Docker images. Targets embedded ARM boards on both `arm64` (aarch64) and `armhf` (ARMv7-A hard-float) architectures, with package version sync from the target device and optional rsync deploy.

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

There are two backends. Docker is the recommended path and the one used in CI. SSHFS sysroot is currently experimental and untested with the latest changes (the code path still hardcodes `aarch64-linux-gnu` sysroot layout, so it will not work as-is on `armhf`).

| Backend | Status | When to use |
|---|---|---|
| `docker` | Recommended, used in CI | You have a Docker image for the target board |
| `sysroot` | Experimental, untested | You want to build against the live filesystem of a running board over SSHFS |

The rest of this README focuses on the Docker backend.

## Where the Docker images come from

The companion repository [`smarobix/buildx-docker-images`](https://github.com/smarobix/buildx-docker-images) builds and publishes board-specific Docker images that work with `colcon buildx` out of the box (Kria K26 today, Pynq-Z1 / Pynq-Z2 in progress). You can also bring your own. Any image with ROS 2 installed under `/opt/ros/<distro>` and a working colcon will work.

## Installation

```bash
pip install git+ssh://git@gitlab.com/smarobix/research-and-development/fpga/kria_ros_buildx_compile.git
```

For local development:

```bash
git clone git@github.com:smarobix/colcon-buildx.git
cd colcon-buildx
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
docker_image = sapertuz/smrbx-buildx:kv26-jazzy
docker_platform = linux/arm64
deploy_target = ubuntu@10.42.0.3:~/ros2_ws/install/
```

Then build:

```bash
cd ~/my_ros2_workspace
colcon buildx
```

Output goes to `cross_build/` and `cross_install/` (kept separate from native `build/` and `install/` so the two trees do not collide).

For an `armhf` board (Pynq-Z1 example):

```bash
method = docker
docker_image = sapertuz/smrbx-buildx:pynq-z1-jazzy
docker_platform = linux/arm/v7
deploy_target = xilinx@192.168.2.99:~/ros2_ws/install/
```

See [`buildx-docker-images`](https://github.com/smarobix/buildx-docker-images) for the full list of available image tags.

## Configuration

Two formats are supported, both with the same keys.

`.buildx.conf` (key=value):

```bash
method = docker
docker_image = sapertuz/smrbx-buildx:kv26-jazzy
docker_platform = linux/arm64
build_base = cross_build
install_base = cross_install
deploy = false
deploy_target = ubuntu@10.42.0.3:~/ros2_ws/install/
```

`.buildx.yml` (YAML):

```yaml
method: docker
docker_image: sapertuz/smrbx-buildx:pynq-z1-jazzy
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

Builds are slow: the tool reuses persistent build / install directories for fast incremental builds. Avoid blowing them away unless you need to. Do not pass `--rebuild-container` (or its equivalents) unless you are debugging the image itself.

## Legacy `kria-build` script

The repository still ships a 269-line standalone bash script at `bin/kria-build`. It predates the colcon extension, is hardcoded for Kria and `arm64`, and is kept in tree so older deployment scripts keep working. New work should use `colcon buildx`. The standalone script will be removed once nothing depends on it.

## License

License to be finalized before public release.
