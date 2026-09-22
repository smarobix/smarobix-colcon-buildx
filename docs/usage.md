# Usage

This page covers cross-building your own workspace. It assumes ROS 2 is already on the board; the [target picker](https://smarobix.github.io/smarobix-buildx-images/) shows how to put it there.

## Quick start

In the root of your ROS 2 workspace, the directory that contains `src/`, create `.buildx.conf`:

```ini
method = docker
docker_image = ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy
docker_platform = linux/arm64
deploy_target = ubuntu@10.42.0.3:~/ros2_ws/install/
```

Then build:

```bash
cd ~/ros2_ws
colcon buildx
```

colcon-buildx prints the config file it read and the image it is using, pulls the image if it isn't local yet, and runs `colcon build` inside it with your `src/` mounted read-only.

The results go to `cross_build/` and `cross_install/`. They are kept apart from a native `build/` and `install/`, so a host build and a cross build in the same workspace don't overwrite each other. colcon's logs go to `cross_build/log/`, and colcon-buildx's own run log goes to `log/` at the workspace root. The container runs as your user, so you own everything it writes and can delete it without sudo.

To copy the result to the board after the build, add `--deploy`. It uses `rsync --delete`, so read [Deploy](sync-and-deploy.md#deploy) first.

The full walkthrough, from an empty workspace to a node running on a K26, is the images site's [first cross-build tutorial](https://smarobix.github.io/smarobix-buildx-images/tutorials/first-cross-build/).

## Other boards

Each board, OS and ROS 2 distro has its own image tag and Docker platform. The [target picker](https://smarobix.github.io/smarobix-buildx-images/) gives the matching `.buildx.conf`, and the [target reference](https://smarobix.github.io/smarobix-buildx-images/reference/targets/) lists every published image.

A Pynq-Z1 or Pynq-Z2 running PYNQ v3.1.1 and ROS 2 Jazzy is an armhf board:

```ini
method = docker
docker_image = ghcr.io/smarobix/smarobix-buildx-images:pynq-v3.1.1-jazzy
docker_platform = linux/arm/v7
deploy_target = xilinx@192.168.2.99:~/ros2_ws/install/
```

`xilinx` and `192.168.2.99` are the PYNQ image's default user and static address. ROS 2 itself goes on the Pynq as a `.deb` from the images repository; colcon-buildx builds your workspace against the matching image, as on every other board.

For boards running a Yocto image, see [Yocto targets](yocto-targets.md).

## Passing arguments to colcon

colcon-buildx forwards any argument it doesn't recognise to `colcon build`:

```bash
colcon buildx --packages-select my_pkg
colcon buildx --packages-skip rviz2 --deploy
colcon buildx --cmake-args -DCMAKE_BUILD_TYPE=Release
colcon buildx --cmake-args -DBUILD_TESTING=OFF
```

colcon-buildx sets colcon's `--build-base` and `--install-base` from its own options of the same name, and the `docker` and `sdk` methods always build with `--merge-install`.

colcon arguments can't be set in a config file. Put them on the command line, or in a shell alias.

## Common options

```bash
# use another image or platform for this run only
colcon buildx --docker-image ghcr.io/smarobix/smarobix-buildx-images:rpi-armv7-bookworm-jazzy --docker-platform linux/arm/v7

# ignore a synced image and build with the tag as published
colcon buildx --use-base-image

# read a config file from somewhere other than the workspace
colcon buildx --config ~/boards/kv260.buildx.conf
```

Every option can also be set in a config file; see [Configuration](config.md). The [command-line reference](reference/cli.md) lists all of them.

## The workspace root

colcon-buildx looks for the workspace root, the directory with `src/` in it, starting at the current directory and moving up through its parents; it looks at five directories in all, the current one included. The build and install directories are created there, whichever directory you started the command in, and only its `src/` is mounted into the container.

If it finds no `src/`, it warns and uses the current directory as the workspace root:

```text
No workspace root found: no src/ directory in /home/you/tmp or the 4
directories above it. Using the current directory as the workspace root;
run colcon buildx from your workspace root instead.
```

The config file search walks the same directories, so both stop in the same place.

## The ROS 2 distro

In an image that runs as the target, colcon-buildx sources `/opt/ros/<distro>/setup.bash` before building. It takes the distro from the image's `org.smarobix.buildx.ros-distro` label. Without the label, it looks for a known distro name in the image name, taking the first of `jazzy`, `humble`, `kilted` and `rolling` that appears; if there is none, it assumes `jazzy` and prints a warning. The published images have the distro in their tag, so this works for them without the label.

## Installing workspace dependencies

`--install-deps` runs `rosdep install` for the packages in `src/`. What it installs into depends on the method:

| Method | `--install-deps` installs into |
|---|---|
| `docker` | A copy of the image, which colcon-buildx commits as `<tag>-synced-<YYYYMMDD>` (the suffix is today's date) and uses for later builds. The board doesn't get these packages. With a cross SDK image it is ignored with a warning. |
| `sysroot` | The board, over SSH, as `--install-deps-on-device` does. |
| `sdk` | Nothing; it is ignored with a warning. An SDK's sysroot is fixed when the SDK is built, so add the dependencies to the Yocto image and rebuild the SDK. |

With the Docker method, a dependency installed only in the image leaves you with a binary the board can't run. Install dependencies on the board first and then sync the image from it; [Sync and deploy](sync-and-deploy.md) describes that workflow.

`--rosdep-args` replaces the arguments passed to `rosdep install`. The default is `--ignore-src -y`.

## Files colcon-buildx writes

All of these are in the workspace root. Add the ones you use to your workspace's `.gitignore`.

| Path | Written by |
|---|---|
| `cross_build/` | Every build. Holds colcon's build tree, the SDK toolchain wrapper `buildx-toolchain.cmake`, and with the Docker method colcon's logs. |
| `cross_install/` | Every build. This is what `--deploy` copies to the board. |
| `log/` | Builds with `--method sdk` or `--method sysroot`, which leave colcon's logs in its usual place. |
| `.buildx-sync-manifest.json` | `--sync-from-device` and `--install-deps` with the Docker method. |
| `cross_log/sync-packages-*.log` | `--sync-from-device`. |
| `.buildx/mixin/` | `--emit-mixin` with `--method sdk`. |
