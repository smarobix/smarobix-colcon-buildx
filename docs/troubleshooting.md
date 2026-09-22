# Troubleshooting

Each entry starts with the message you see. colcon-buildx's own messages come through colcon's logger, so on screen they carry a timestamp, the logger name and a status symbol in front.

## Setup and configuration

### `Ignoring unrecognised config key: KEY`

The config file has a key colcon-buildx doesn't know, and the run carries on without it. Usually it is a typo; the [config keys reference](reference/config-keys.md) lists the valid ones. `colcon_args` is not a key: put colcon arguments on the command line.

### `Specified config file not found: PATH`

The file given with `--config` doesn't exist. The run carries on with no config file at all, so it probably uses the wrong image. Check the path.

### `Failed to load config from FILE: ERROR`

The config file couldn't be parsed, usually a YAML syntax error. The run carries on without it.

### `Unknown method: METHOD`

`method` in the config file is not `docker`, `sdk` or `sysroot`.

### `No workspace root found: no src/ directory in DIR or the 4 directories above it`

colcon-buildx uses the current directory as the workspace root instead, so the build finds no packages, or writes its output somewhere you don't expect. Run `colcon buildx` from the workspace root, the directory that holds `src/`.

### `sync_from_device is a command-line action, not a config key; ignoring it`

`sync_from_device` or `install_deps_on_device` is set in a config file. Both are one-off actions rather than settings, so the build carries on without them. Run `colcon buildx --sync-from-device ubuntu@10.42.0.3` or `colcon buildx --install-deps-on-device ubuntu@10.42.0.3` instead; see [Sync and deploy](sync-and-deploy.md).

## Docker

### `Docker daemon is not running` or `Docker not found`

Start Docker Desktop, or on Linux run `sudo systemctl start docker`. If Docker isn't installed, install it from <https://docs.docker.com/get-docker/>.

### `--docker-image is required for docker method`

No image is configured. Set `docker_image` in `.buildx.conf`, or pass `--docker-image`. Check that the config file is being found: see the [search order](config.md#search-order).

### `Failed to pull image: IMAGE`

The image isn't local and couldn't be pulled. Check the name and tag against the images site's [target reference](https://smarobix.github.io/smarobix-buildx-images/reference/targets/). The published images are public, so they need no login; an image on a private registry needs `docker login` first.

### `no matching manifest for linux/amd64`

You are using an SDK image, such as `k26-oesdk-jazzy`, on an x86_64 host. colcon-buildx starts SDK images without `--platform`, and the published tags have only an arm64 entry. Pull the image for arm64 once, then build again:

```bash
docker pull --platform linux/arm64 ghcr.io/smarobix/smarobix-buildx-images:k26-oesdk-jazzy
```

### `exec format error`

The host can't run the image's architecture because QEMU isn't registered. Register it:

```bash
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
```

Also check that `docker_platform` matches the image: `linux/arm64` for arm64 images, `linux/arm/v7` for armhf ones. See [Install](install.md#docker-and-qemu).

### `Could not determine ROS distro from 'IMAGE', assuming jazzy`

The image has no `org.smarobix.buildx.ros-distro` label and its name doesn't contain a known distro. If it isn't a Jazzy image, add the label to it; see [Image labels](reference/labels.md).

### `Image declares org.smarobix.buildx.kind=oe-sdk but no org.smarobix.buildx.env-setup`

The SDK image is missing the label that names its environment script, and the build stops with `Cross SDK image has no org.smarobix.buildx.env-setup label`. Add the label to the image; see [Image labels](reference/labels.md).

### A synced image isn't picked up

List the synced images with `docker images | grep synced`. A build uses the newest local image tagged `<tag>-synced-<YYYYMMDD>`, for exactly the tag you configured and in the same repository, unless `--use-base-image` or `use_base_image = true` is set. If you changed `docker_image`, run `--sync-from-device` again.

### `IMAGE is a cross SDK image: ... cannot be synced to a board`

`--sync-from-device` compares the board's Debian packages with the image's, which only makes sense for an image that runs as the target. An SDK image runs on the host, and the target's libraries come from the SDK's sysroot, which is fixed when the SDK is built. `--install-deps` is ignored for the same reason, with a warning.

### `Ignoring --toolchain: IMAGE runs as the target and builds natively`

A toolchain file is for a cross build. Only `--method sdk`, or `--method docker` with a cross SDK image, uses one; with an image that runs as the target, drop the option.

### A build still uses an old synced image

Pass `--use-base-image` for one build, or delete the synced images with `docker rmi` to go back to the published tag.

### `rosdep` fails during `--install-deps`

colcon-buildx runs `rosdep init` itself when rosdep has no sources yet, then `rosdep update` and `apt-get update`, in a container of the image, before `rosdep install`. If one of these fails:

- `rosdep: command not found`: the image has no rosdep. Install `python3-rosdep` in your image, or use one that has it.
- `rosdep update` errors: the container has no network access to GitHub, where the rosdep sources live.
- `Cannot locate rosdep definition for [NAME]`: `NAME` from a `package.xml` isn't in the rosdep database. Fix the dependency name, or add `--skip-keys NAME` to `--rosdep-args`.

### Builds are slow

colcon-buildx keeps `cross_build/` and `cross_install/` between runs, so later builds are incremental. Don't delete them unless you have to.

An image for another architecture runs under QEMU, where every compiler process is emulated. An arm64 host, such as an Apple Silicon Mac, builds arm64 images natively.

## Yocto SDKs

### `OE_CMAKE_TOOLCHAIN_FILE unset after sourcing the SDK environment`

With `--method sdk` the message reads `OE_CMAKE_TOOLCHAIN_FILE is unset after sourcing the SDK environment`. Either way, the SDK was built without `ros-sdk-env`. Add `nativesdk-ros-sdk-env` to `TOOLCHAIN_HOST_TASK` and rebuild it; see [Yocto targets](yocto-targets.md#what-the-sdk-has-to-contain). Or name a toolchain file directly with `--toolchain`, which works with `--method sdk` and with a cross SDK image; for an image, give the path inside the container.

### `--method sdk requires a Linux host`

An OE/Yocto SDK is a Linux program. On macOS, use an SDK image with the Docker method instead, as in [Yocto targets](yocto-targets.md#three-ways-to-build).

### `--sdk-env is required for sdk method` or `SDK environment script not found: PATH`

`--sdk-env` (or `sdk_env`) must point at the SDK's `environment-setup-*` script, for example `/opt/ros-sdk/environment-setup-cortexa72-cortexa53-oe-linux` for a K26 SDK installed in `/opt/ros-sdk`. The suffix is `-oe-linux`.

### `Failed to source the SDK environment`

Sourcing the script failed; the lines after the message show the shell's error. The SDK's host tools must match the host's architecture: the published SDK installers are for arm64 Linux hosts.

### `unable to find a build program corresponding to "Unix Makefiles"`

`CMAKE_GENERATOR` is set to a Makefile generator, and the SDK has no `make`. Unset `CMAKE_GENERATOR`, and colcon-buildx uses the SDK's Ninja.

### Tests fail to configure

Pass `--cmake-args -DBUILD_TESTING=OFF`. A cross build can't run the lint tests that `ros2 pkg create` adds, and the Yocto dev container ships the linters' CMake hooks without the linters.

### `ros2 topic echo` can't show a message type built with an SDK

Neither SDK route generates Python message bindings. Build interface packages in the dev container instead, or use `ros2 topic info` to check that messages flow.

## Sysroot

### `--toolchain is required for sysroot method` or `--sysroot-host is required for sysroot method`

The sysroot method needs both: a CMake toolchain file for your cross compiler, and the board to mount. See [Backends](backends.md#sysroot-experimental).

### `SSHFS mount failed` mentioning `allow_other`

colcon-buildx mounts with `-o allow_other`, which FUSE allows for a user other than root only when `/etc/fuse.conf` contains the line `user_allow_other`. Add it, then run the build again.

## Deploy

### `--deploy-target is required when --deploy is used`

Set `deploy_target` in the config file, or pass `--deploy-target`, for example `ubuntu@10.42.0.3:~/ros2_ws/install/`. colcon-buildx checks this before it starts the build, so nothing is lost.

### `Install directory not found: PATH`

There is nothing at `install_base` under the workspace root to deploy. Build first, and check `install_base` if you changed it.

### Files on the board disappeared after a deploy

`--deploy` runs `rsync --delete`, which removes everything in the target directory that isn't in `cross_install/`. Point `deploy_target` at a directory used only for this workspace's install tree; see [Deploy](sync-and-deploy.md#deploy).

### `Deployment failed with exit code N`

rsync failed. Check that `ssh` to the board works without a password prompt, and that the board has `rsync`. Minimal Yocto images may not; copy with tar over SSH instead, as in [Yocto targets](yocto-targets.md#deploying-and-sourcing-on-the-board).
