# colcon buildx

`colcon buildx` builds a ROS 2 workspace for a robot against the robot's own software image, then copies the result to the robot. You name the image in a two-line config file: an [OEROS](https://github.com/oerosproject) SDK image, the SDK of your own Yocto build, or the image your board runs. The build runs on your computer's own architecture. Nothing runs under emulation, and nothing needs installing except Docker.

For OEROS, this covers two stages of the onboarding journey in [spec 0012](https://github.com/robwoolley/oerosproject/blob/main/specs/0012-onboarding-howtos-quickstart.md): stage 3, building a ROS application with the cross-compiled SDK, and stage 5, the edit, build, deploy and run loop with a robot on the desk.

## Install

```bash
python3 -m venv ~/.venvs/buildx && . ~/.venvs/buildx/bin/activate
pip install "git+https://github.com/smarobix/smarobix-colcon-buildx.git"
colcon buildx --help
```

You also need Docker. QEMU is not needed.

## Quick start: an OEROS robot

In the workspace root, the directory that holds `src/`, create `.buildx.conf`:

```ini
method = docker
docker_image = ghcr.io/oerosproject/oeros-sdk-cross:lyrical-arm64
```

Then run `colcon buildx`. The result for the robot is in `cross_install/`, owned by you; colcon's build tree is in `cross_build/`. Arguments that colcon buildx does not know, such as `--packages-select my_pkg`, go to `colcon build`. Later builds are incremental.

For example, with the ROS 2 examples:

```bash
mkdir -p ~/ws/src && cd ~/ws
git clone -b lyrical https://github.com/ros2/examples src/examples
printf 'method = docker\ndocker_image = ghcr.io/oerosproject/oeros-sdk-cross:lyrical-arm64\n' > .buildx.conf
colcon buildx --packages-up-to examples_rclcpp_minimal_publisher
```

The first build with a new image takes an extra few seconds, plus the image download: colcon buildx prepares the image once (see [what colcon buildx does with an image](#what-colcon-buildx-does-with-an-image)).

To copy the result to the robot, add the destination and pass `--deploy`:

```ini
deploy_target = root@my-robot.local:/opt/ws/install/
```

```bash
colcon buildx --deploy
```

`--deploy` runs `rsync --delete` into that directory, so give it a directory of its own. The robot needs `rsync` for this. On the robot, the OEROS images use a POSIX shell, so name the prefix when you source it:

```sh
. /opt/ros/lyrical/setup.sh
COLCON_CURRENT_PREFIX=/opt/ws/install . /opt/ws/install/local_setup.sh
ros2 run examples_rclcpp_minimal_publisher publisher_member_function
```

## Which image

| Your computer | Your robot | `docker_image` |
|---|---|---|
| x86_64 (Linux, or Docker Desktop on Windows or an Intel Mac) | OEROS, arm64 | `ghcr.io/oerosproject/oeros-sdk-cross:<distro>-arm64` |
| arm64 (Apple silicon, an arm64 Linux machine) | OEROS, arm64 | `ghcr.io/oerosproject/oeros-sdk-target:<distro>-arm64` |
| either | your own Yocto/OE build | an SDK image of the same build; see [labels](docs/labels.md) |
| either | an Ubuntu image made for an armhf or arm64 board, such as PYNQ on a Pynq-Z1 | that board image, for example `ghcr.io/smarobix/smarobix-buildx-images:pynq-v3.1.1-jazzy` |

If the image would need emulation, such as an x86_64 SDK image on Apple silicon, colcon buildx stops and names the image to use instead. The OEROS image tags carry the ROS distro and the robot's architecture: `lyrical-arm64` builds for arm64 robots running OEROS Lyrical.

## What colcon buildx does with an image

colcon buildx never runs an image made for another architecture. It looks at the image's labels and architecture and, once per image version, makes the image it builds in:

- **An SDK image is prepared.** colcon buildx adds a thin layer on top with a shell, an environment script, and whatever the SDK lacks for a ROS workspace. The SDK image only has to provide the toolchain and the target's sysroot. The layer is tagged `colcon-buildx:prepared-<id>`.
- **An image of your computer's architecture runs as it is.** Examples are a dev container such as `oeros-sdk-target` on an arm64 computer, or an arm64 board image on Apple silicon. OEROS images are prepared as well.
- **A board image of another architecture becomes a sysroot.** colcon buildx copies its filesystem into a *cross image* built from the same Ubuntu release, which has that release's cross compiler. Compiler, glibc and Python then match the board. Copying a filesystem runs nothing from it. The result is tagged `colcon-buildx:cross-<id>` and takes under a minute to build.

For the OEROS images of 30 Oct 2026, preparing adds a shell, the SDK environment that `ros-sdk-env` would set, and `ament_cmake_ros_core`, without which no ROS package configures. [docs/oeros.md](docs/oeros.md) lists each of these with its fix in meta-ros. Once the images carry them, the preparation leaves them alone.

The builds run as your user, with `src/` mounted read-only. Old prepared and cross images are removed by `docker image prune` like any other unused image.

## On a production line: an installed SDK

A team that ships keeps its SDK as an installer, with its SBOM, rather than as a Docker image. On a Linux computer with the SDK installed:

```bash
colcon buildx --method sdk --sdk-env /opt/oeros-sdk/environment-setup-armv8a-oeros-linux
```

This uses the same toolchain wrapper as the Docker route. `--emit-mixin` also writes the settings as a colcon mixin, so a plain `colcon build --mixin buildx` gives the same build.

## What to expect

Measured on 11 Nov 2026 with a four-package workspace: messages, a C++ node, a Python package and a pybind11 module.

- `oeros-sdk-cross:lyrical-arm64` as published, on an x86_64 Linux workstation: 12 s cold, 5 s after a one-line change. The result runs in `oeros-ros-base:lyrical-arm64`.
- `oeros-sdk-target:lyrical-arm64` on Apple silicon: 12 s cold, 4 s after a one-line change. The result runs in `oeros-ros-base:lyrical-arm64`, Python listener included.
- The KV260 SDK image from a meta-ros Jazzy build, on Apple silicon: 9 s cold. The same route's result has run on the KV260 itself.
- The PYNQ image for the Pynq-Z1 (Ubuntu 22.04, armhf), on x86_64: 7 s cold, 3 s after a one-line change. A run on the board is pending.

## Limits

- **SDK images make no Python message bindings.** meta-ros SDKs carry the C and C++ generators only. Message packages that `rclpy` or the `ros2` CLI on the robot must use belong in the image, as recipes. `oeros-sdk-target` does have the Python generator.
- **Cross images are made from Ubuntu board images only.** Debian and Raspberry Pi OS images are not supported yet.
- **Nothing that runs target programs during the build.** A package that does needs to be built into the image, or on the robot.
- **`--install-deps` and `--sync-from-device` run the image's own apt.** They work with images of your computer's architecture only. For other images, add the packages where the image is built.
- **A board image's Docker `ENV` is not carried into its cross image.** For example, PYNQ's `LD_LIBRARY_PATH` for OpenCV is lost.

## Methods

`--method`, or `method` in the config file, picks how the build runs.

| Method | Builds against | Runs on | Status |
|---|---|---|---|
| `docker` | an image: SDK, dev container or board image | any computer with Docker | recommended |
| `sdk` | a Yocto/OE SDK installed on this computer | Linux | supported |
| `sysroot` | the board's own filesystem, mounted over SSHFS | Linux, aarch64 boards | deprecated: use the board's image with `docker` |

## Documentation

- [OEROS images](docs/oeros.md): what colcon buildx needs from an SDK image, and what it works around in the published ones.
- [Reference](docs/reference.md): every option, config key and method. Generated from the code.
- [Troubleshooting](docs/troubleshooting.md): error messages and what to do about them.
- [Image labels](docs/labels.md): the contract between colcon buildx and the images it uses.

Complete config files with every key are in [`examples/`](examples/).

## Development

```bash
git clone https://github.com/smarobix/smarobix-colcon-buildx.git && cd smarobix-colcon-buildx
python3 -m venv ~/.venvs/buildx-dev && . ~/.venvs/buildx-dev/bin/activate
pip install -e ".[test]"
pytest -q && flake8
```

The tests need no Docker, SDK or board. To add an option: declare it in `BuildxVerb.add_arguments` with `default=None`, put its default in `DEFAULTS` or its name in `CONFIG_KEYS` (or in `ACTION_FLAGS` for a one-off device action), add it to both files in `examples/`, and regenerate the reference with `python tools/gen_docs.py`. CI checks that the generated page is current and that the relative links in `README.md` and `docs/` resolve (`python tools/check_links.py`).

The images colcon buildx derives are built from the recipes in [`colcon_buildx/docker/recipes/`](colcon_buildx/docker/recipes/). Their tags include a hash of the recipes, so a change to a recipe rebuilds them.

Every source file carries an SPDX header (`Apache-2.0`, `SMAROBIX GmbH`); files that cannot are covered by `REUSE.toml`, and `reuse lint` runs in CI.

## License

Apache License 2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2025-2026 SMAROBIX GmbH.
