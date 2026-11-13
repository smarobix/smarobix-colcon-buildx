# Troubleshooting

Each entry starts with the message you see. colcon buildx's messages come through colcon's logger, so on screen they carry a timestamp and a status symbol in front.

## Configuration

**`Ignoring unrecognised config key: KEY`.** A typo, or `colcon_args`, which is not a key: colcon arguments go on the command line. The [reference](reference.md) lists the keys. The run carries on without the key.

**`Specified config file not found: PATH`** or **`Failed to load config from FILE`.** The run carries on with no config file at all, so it probably uses the wrong image. Fix the path or the syntax.

**`No workspace root found: no src/ directory in DIR or the 4 directories above it`.** Run `colcon buildx` from the workspace root, the directory that holds `src/`.

## The image

**`Docker daemon is not running`.** Start Docker Desktop, or `sudo systemctl start docker`.

**`--docker-image is required for docker method`.** No image is configured. Set `docker_image`, and check that the config file is found: every run prints `Config file:` with the path it read.

**`Failed to pull image`.** Check the image name and tag. The OEROS images and this project's images need no login.

**`does not run images under emulation`.** The image is for another architecture than your computer, and colcon buildx will not emulate it. The message names the image to use instead: on an arm64 computer, `oeros-sdk-target` rather than `oeros-sdk-cross`; for an OEROS robot, its SDK image rather than the robot's own image. See [OEROS robots](oeros.md#pick-an-image).

**`Building colcon-buildx:prepared-... failed`** or **`Building colcon-buildx:cross-... failed`.** Preparing an SDK image, or building the cross image for a board image, failed; Docker's output above the message says where. Both need network access the first time: BusyBox from Docker Hub, `ament_cmake_ros` from GitHub, and the release's packages for a cross image.

**`colcon buildx builds a cross image from Ubuntu and Debian board images only`.** The cross compiler comes from the board image's own release, so other distributions have none to offer. For a Yocto board, use an SDK image of its build.

**`target pythonX.Y, host pythonX.Z: the host release must match the target's`.** The board image's Python is not its release's own, so the cross image cannot report the board's Python ABI. Use an image with the release's Python.

**`No ROS 2 installation (/opt/ros/<distro>) found`.** The SDK's sysroot, or the image, has no ROS 2. Check the tag.

**`Could not determine ROS distro from 'IMAGE', assuming jazzy`.** The image has no `org.smarobix.buildx.ros-distro` label and no distro in its name. Add the [label](oeros.md#your-own-image).

**Builds are slow.** `cross_build/` and `cross_install/` are kept between runs, so later builds are incremental; do not delete them. The first build with a new image version also prepares it, or builds its cross image, once.

## Dependencies

**`--install-deps runs the image's own apt`.** Installing packages runs the image's apt, which an image of another architecture can only do under emulation. Add the packages where the image is built, or run on a computer of the image's architecture.

**`Ignoring --install-deps: IMAGE is a cross SDK image`.** An SDK's sysroot is fixed when the SDK is built. Add the dependency to the robot's image; see [OEROS robots](oeros.md#dependencies).

**`rosdep` fails during `--install-deps`.** `rosdep: command not found` means the image has no rosdep. An error from `rosdep update` means the container cannot reach GitHub. `Cannot locate rosdep definition for NAME` means the name in `package.xml` is not in the rosdep database; fix it, or pass `--rosdep-args="--ignore-src -y --skip-keys NAME"`.

**A build uses an old `-synced-` image.** `--install-deps` saves its result as a local `<tag>-synced-<date>` image, and later builds take the newest one for the configured tag; `docker images | grep synced` lists them. `--use-base-image` builds in the configured image once, and `docker rmi` on the synced images goes back for good.

## The build

**Tests fail to configure.** Pass `--cmake-args -DBUILD_TESTING=OFF`. A cross build cannot run the lint tests that `ros2 pkg create` adds.

**`ros2 topic echo` on the robot cannot show a message type you built.** meta-ros SDKs generate no Python bindings for messages. Put the message package into the robot's image as a recipe, or build it with `oeros-sdk-target`; `ros2 topic info` works meanwhile.

**`libatomic.so.1: cannot open shared object file` on the robot.** The program was linked without `--as-needed` and the robot's image has no `libatomic`. colcon buildx links with `--as-needed` in the OEROS images it prepares; build again with the current version.

**`unable to find a build program corresponding to "Unix Makefiles"`.** The SDK has no `make`. Unset `CMAKE_GENERATOR`, and colcon buildx uses the SDK's Ninja.

## Deploy

**`--deploy-target is required when --deploy is used`.** Set `deploy_target`, or pass `--deploy-target user@host:path/`. This is checked before the build starts, so nothing is lost.

**`Deployment failed with exit code N`.** rsync failed. Check that `ssh` to the robot works without a password prompt and that the robot has `rsync`.

**Files on the robot disappeared after a deploy.** `--deploy` runs `rsync --delete`. Point `deploy_target` at a directory used only for this workspace's install tree.
