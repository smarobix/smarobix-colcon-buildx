# Backends

`--method` chooses how the build runs: `docker` (the default), `sdk` or `sysroot`. The Docker method handles two kinds of image, told apart by the image's `org.smarobix.buildx.kind` [label](reference/labels.md), so there are four cases in all.

| | Docker, target image | Docker, SDK image | `sdk` | `sysroot` |
|---|---|---|---|---|
| Example | `k26-jazzy` | `k26-oesdk-jazzy` | an SDK in `/opt/ros-sdk` | the board over SSHFS |
| Compiles | natively, as the target | cross, on the host architecture | cross, on the host | cross, on the host |
| Host | any, with Docker | any, with Docker | Linux | Linux |
| Target architectures | arm64, armhf | whatever the SDK targets | whatever the SDK targets | aarch64 only |
| Python message bindings | yes | no | no | no |
| `--docker-platform` | used | ignored | not applicable | not applicable |
| `--toolchain` | ignored | replaces the SDK's | replaces the SDK's | required |
| Status | recommended | supported | supported | experimental |

Why there are native and cross images at all is explained on the images site, in [native vs cross](https://smarobix.github.io/smarobix-buildx-images/explanation/native-vs-cross/).

## Docker, with an image that runs as the target

This is the default. The image is a root filesystem for the target board, with ROS 2 in `/opt/ros/<distro>`, the compilers and colcon. Its kind label is absent, which means `ros-apt`, or set to `yocto-native`, which is handled the same way.

For each build, colcon-buildx:

1. checks that Docker is running;
2. picks the image: the newest local `<tag>-synced-<YYYYMMDD>` if there is one and you haven't passed `--use-base-image` (see [Sync and deploy](sync-and-deploy.md)), otherwise the tag you configured;
3. pulls it if it isn't local. It tries the host's platform first and then `docker_platform`;
4. runs `docker run --platform <docker_platform>` with `src/` mounted read-only at `/workspace/src` and the build and install directories mounted read-write;
5. inside, sources `/opt/ros/<distro>/setup.bash` and runs `colcon build --merge-install` with any extra arguments you gave.

The container runs with your user and group ID and `HOME=/tmp`, so the files it writes are yours. When the host's architecture differs from the image's, Docker runs the container under QEMU; [Install](install.md#docker-and-qemu) covers setting that up.

`docker_platform` has to match the image: `linux/arm64` for arm64 images and `linux/arm/v7` for armhf ones. The default is `linux/arm64`. The same platform is used by `--sync-from-device` and `--install-deps`, which run the image too.

`--toolchain` is for cross builds, so an image that runs as the target ignores it and says so.

Any image with ROS 2 in `/opt/ros/<distro>`, bash and colcon works, including your own. The [label reference](reference/labels.md#bringing-your-own-image) lists what else it should have.

## Docker, with a cross SDK image

An SDK image holds a Yocto/OE SDK: a cross toolchain plus the target's sysroot. It runs on the build host's architecture, not the target's, and carries the label `org.smarobix.buildx.kind=oe-sdk`. When colcon-buildx sees that label, it:

- runs the container without `--platform`, so `--docker-platform` has no effect;
- sources the scripts named in `org.smarobix.buildx.env-setup` instead of `/opt/ros/<distro>/setup.bash`;
- stops with an error if `OE_CMAKE_TOOLCHAIN_FILE` is still unset after that and you gave no `--toolchain`, because the SDK was built without `ros-sdk-env`;
- writes a toolchain wrapper, `cross_build/buildx-toolchain.cmake`, and points `CMAKE_TOOLCHAIN_FILE` at it;
- uses Ninja if the SDK has it and you haven't set `CMAKE_GENERATOR`.

The published SDK images, `k26-oesdk-jazzy` and `rpi5-oesdk-jazzy`, contain SDK host tools built for aarch64. They run natively on Apple Silicon and on arm64 Linux, and under QEMU on x86_64. On x86_64, pull them with `--platform linux/arm64` before the first build; [Install](install.md#sdk-images-on-x86_64) has the command.

`--toolchain FILE` wraps `FILE` instead of the SDK's own toolchain file, and skips the `OE_CMAKE_TOOLCHAIN_FILE` check. `FILE` is a path inside the container, not on the host.

`--sync-from-device` and `--install-deps` don't apply to an SDK image: it runs on the host, and the target's libraries come from the SDK's sysroot. colcon-buildx refuses the first and ignores the second, with a message saying why.

Interface packages get C and C++ code only, because meta-ros SDKs don't ship the Python message generator.

[Yocto targets](yocto-targets.md) explains what the SDK has to contain and what the toolchain wrapper fixes.

## sdk

`--method sdk` builds against a Yocto/OE SDK installed on this host, the way meta-ros intends its SDKs to be used. It needs a Linux host whose architecture matches the SDK's host tools, and `--sdk-env` (or `sdk_env`) pointing at the SDK's environment script:

```bash
colcon buildx --method sdk \
  --sdk-env /opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux
```

`--sdk-env` takes several scripts separated by colons; they are sourced in that order. colcon-buildx sources them, prints the ROS distro, target Python SOABI and toolchain file it found, writes the same toolchain wrapper as for an SDK image, and runs `colcon build --merge-install` on the host. Nothing is emulated.

- `--toolchain FILE` wraps `FILE` instead of the SDK's `OE_CMAKE_TOOLCHAIN_FILE`.
- Ninja is used as for an SDK image.
- On macOS or Windows it stops with `--method sdk requires a Linux host`. Use an SDK image there.
- There are no Python message bindings, for the same reason as with an SDK image.
- `--install-deps` is ignored with a warning. An SDK's sysroot is fixed when the SDK is built, so add the dependencies to the Yocto image and rebuild the SDK.

### Using the SDK settings with plain colcon

`--emit-mixin` also writes the cross-build settings as a colcon mixin, so `colcon build` can use them without colcon-buildx. It is written during a normal `--method sdk` run:

```bash
colcon buildx --method sdk \
  --sdk-env /opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux \
  --emit-mixin
```

The mixin goes to `.buildx/mixin/` in the workspace root. It sets `merge-install` and passes `CMAKE_TOOLCHAIN_FILE`, pointing at the wrapper in `cross_build/`, and `PYTHON_SOABI` as CMake arguments. Registering it needs the `colcon-mixin` extension. From the workspace root:

```bash
colcon mixin add buildx "file://$PWD/.buildx/mixin/index.yaml"
colcon mixin update buildx
```

Then build from the workspace root, in a shell where the SDK environment is sourced. colcon-buildx also sets `ROS_WORKSPACE` to the workspace root for its own builds, so do the same:

```bash
. /opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux
export ROS_WORKSPACE="$PWD"
colcon build --mixin buildx --install-base cross_install
```

Keep `--install-base` the same as `install_base`: the wrapper adds that directory to CMake's search roots, which is how packages find each other. The wrapper lives in `cross_build/`, so run `--emit-mixin` again if you delete that directory.

## sysroot (experimental)

`--method sysroot` mounts the board's root filesystem over SSHFS and cross-compiles against it on the host, with a CMake toolchain file you supply for your aarch64 cross compiler. It is experimental, and the least used of the four routes. In this example the toolchain file is `~/toolchains/aarch64.cmake`:

```bash
colcon buildx --method sysroot \
  --sysroot-host ubuntu@10.42.0.3 \
  --toolchain ~/toolchains/aarch64.cmake
```

- **aarch64 targets only.** It looks for libraries and Python under `usr/lib/aarch64-linux-gnu`, so it doesn't work for armhf boards.
- **No Python message bindings.** It turns off `rosidl_generator_py`.
- **FUSE `allow_other`.** It mounts with `sshfs -o allow_other,default_permissions`. On Linux, a user other than root may only do that when `/etc/fuse.conf` contains the line `user_allow_other`.
- **Linux host.** It uses `mountpoint` and `fusermount`, and runs the host's `colcon` from the workspace root, as the other methods do.
- `--toolchain` and `--sysroot-host` are required. `--sysroot-host` is anything `ssh` accepts.
- The mount point is `~/mnt/board-sysroot` unless you set `--sysroot-mount`. colcon-buildx unmounts it after the build if it mounted it.
- `--no-mount` uses a sysroot you have already mounted at the mount point, and fails if nothing is mounted there.
- `--install-deps` installs the workspace's dependencies on the board over SSH, as `--install-deps-on-device` does.
