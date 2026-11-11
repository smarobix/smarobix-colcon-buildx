# Troubleshooting

Each entry starts with the message you see. colcon-buildx's messages come through colcon's logger, so on screen they carry a timestamp and a status symbol in front.

## Configuration

**`Ignoring unrecognised config key: KEY`.** A typo, or `colcon_args`, which is not a key: colcon arguments go on the command line. The [reference](reference.md) lists the keys. The run carries on without the key, so a misspelt `docker_platform` would build for the default architecture.

**`Specified config file not found: PATH`** or **`Failed to load config from FILE`.** The run carries on with no config file at all, so it probably uses the wrong image. Fix the path or the syntax.

**`No workspace root found: no src/ directory in DIR or the 4 directories above it`.** Run `colcon buildx` from the workspace root, the directory that holds `src/`.

**`sync_from_device is a command-line action, not a config key`.** `--sync-from-device` and `--install-deps-on-device` are one-off actions and cannot live in a config file, where they would turn every build into a device operation.

## Docker

**`Docker daemon is not running`.** Start Docker Desktop, or `sudo systemctl start docker`.

**`--docker-image is required for docker method`.** No image is configured. Set `docker_image`, and check that the config file is found: every run prints `Config file:` with the path it read.

**`Failed to pull image`.** Check the tag against the [targets reference](https://smarobix.github.io/smarobix-buildx-images/reference/targets/). The published images need no login.

**`does not run images under emulation`.** The image is for another architecture, and colcon-buildx will not emulate it. The message names the image to use instead: on Apple silicon, `oeros-sdk-target` rather than `oeros-sdk-cross`; for an OEROS robot, the SDK image rather than the robot's own image.

**`Building colcon-buildx:prepared-... failed` or `Building colcon-buildx:cross-... failed`.** Preparing an image or building a cross image failed; Docker's output above the message says where. Both need network access the first time: BusyBox from Docker Hub, `ament_cmake_ros` from GitHub, Ubuntu and ROS packages for a cross image.

**`colcon buildx builds a cross image from Ubuntu board images only`.** A board image of another architecture is turned into a cross image from the same Ubuntu release. Debian and Raspberry Pi OS images are not supported yet.

**`target pythonX.Y, host pythonX.Z: the host release must match the target's`.** The board image's Python is not the one of its Ubuntu release, so the host side cannot report the target's ABI. Use an image with the release's own Python.

**`Could not determine ROS distro from 'IMAGE', assuming jazzy`.** The image has no `org.smarobix.buildx.ros-distro` label and no distro in its name. Add the [label](labels.md).

**A build uses an old synced image, or ignores a new sync.** A build takes the newest local `<tag>-synced-<date>` image for exactly the configured tag; `docker images | grep synced` lists them. `--use-base-image` builds in the published tag once, `docker rmi` on the synced images goes back for good, and after changing `docker_image` you need to sync again.

**`--install-deps runs the image's own apt`** or **`--sync-from-device runs the image's own apt`.** Installing packages into an image runs its apt, which an image of another architecture can only do under emulation. Run it on a computer of the image's architecture, or add the packages where the image is built.

**`IMAGE is a cross SDK image ... cannot be synced`.** An SDK image runs on the host and takes its target libraries from the SDK's sysroot. Sync and `--install-deps` do not apply to it.

**`rosdep` fails during `--install-deps`.** `rosdep: command not found` means the image has no rosdep. An error from `rosdep update` means the container has no network access to GitHub. `Cannot locate rosdep definition for NAME` means the name in `package.xml` is not in the rosdep database; fix it, or pass `--rosdep-args="--ignore-src -y --skip-keys NAME"`.

**Builds are slow.** `cross_build/` and `cross_install/` are kept between runs, so later builds are incremental; do not delete them. The first build with a new image also prepares the image, or builds its cross image, once.

## Yocto SDKs

**`OE_CMAKE_TOOLCHAIN_FILE unset after sourcing the SDK environment`.** With `--method sdk`, the SDK was built without `ros-sdk-env`. Rebuild it with `nativesdk-ros-sdk-env` in `TOOLCHAIN_HOST_TASK`, or name its toolchain file with `--toolchain`. SDK images are prepared with a stand-in and do not need it.

**`Could not find a package configuration file provided by "ament_cmake_ros_core"`.** With `--method sdk`, the SDK lacks `ament_cmake_ros_core` (meta-ros Kilted and later, see [OEROS images](oeros.md)). SDK images get it when colcon-buildx prepares them.

**`libatomic.so.1: cannot open shared object file` on the robot.** The program was linked without `--as-needed` and the robot's image has no `libatomic`. colcon-buildx links with `--as-needed` in images it prepares; rebuild with the current version.

**`--method sdk requires a Linux host`.** An OE SDK is a Linux program. On macOS, use an SDK image with the Docker method.

**`SDK environment script not found`** or **`Failed to source the SDK environment`.** `--sdk-env` must point at the SDK's `environment-setup-*-oe-linux` script, and the SDK's host tools must match the host: the published installers are for arm64 Linux.

**`unable to find a build program corresponding to "Unix Makefiles"`.** The SDK has no `make`. Unset `CMAKE_GENERATOR`, and colcon-buildx uses the SDK's Ninja.

**Tests fail to configure.** Pass `--cmake-args -DBUILD_TESTING=OFF`. A cross build cannot run the lint tests that `ros2 pkg create` adds, and the dev container ships the linters' CMake hooks without the linters.

**`ros2 topic echo` cannot show a message type built with an SDK.** meta-ros SDKs generate no Python message bindings. Put the message package into the image as a recipe, build it with `oeros-sdk-target`, or check with `ros2 topic info`.

## Deploy

**`--deploy-target is required when --deploy is used`.** Set `deploy_target`, or pass `--deploy-target user@host:path/`. This is checked before the build starts, so nothing is lost.

**`Deployment failed with exit code N`.** rsync failed. Check that `ssh` to the board works without a password prompt and that the board has `rsync`.

**Files on the board disappeared after a deploy.** `--deploy` runs `rsync --delete`. Point `deploy_target` at a directory used only for this workspace's install tree.

## Sysroot

**`SSHFS mount failed` mentioning `allow_other`.** FUSE allows `allow_other` for a user other than root only when `/etc/fuse.conf` contains the line `user_allow_other`. Add it and run the build again.
