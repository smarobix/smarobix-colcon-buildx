# colcon-buildx

`colcon buildx` is a colcon verb that cross-builds a ROS 2 workspace for arm64 and armhf boards. It runs the build inside a Docker image made for the target board, or against a Yocto/OpenEmbedded SDK. It can also match the image's package versions to what is installed on the board, and copy the result to the board with rsync.

With the Docker method, your host needs no toolchain at all. The image carries the target's C library, ROS 2 and DDS, so what you build links against the same libraries the board has. colcon-buildx plugs into colcon as a verb, so the arguments you would give `colcon build`, such as `--packages-select`, work with `colcon buildx` too.

smarobix-buildx-images and smarobix-colcon-buildx are two halves of one toolchain. The images repository defines every supported target — board, OS, architecture and ROS 2 distro — and publishes the Docker images and ROS 2 `.deb` packages for them. smarobix-colcon-buildx is the colcon verb that cross-builds your own workspace inside one of those images. To put ROS 2 on a board, use the images repository; to build your code for that board, use colcon-buildx.

## Two separate jobs

Getting your code running on a board takes two steps, and colcon-buildx does only the second.

1. **Put ROS 2 on the board.** How depends on the board:
   - a K26 running Ubuntu uses the official ROS apt packages from packages.ros.org;
   - a Pynq, or a Raspberry Pi running Debian, uses a `.deb` from the images repository;
   - a Yocto board has ROS built into its image, which you build from the images repository's `yocto/` configuration. Board images aren't published.

   The [target picker](https://smarobix.github.io/smarobix-buildx-images/) gives the exact steps for each board.
2. **Cross-build your own workspace** with `colcon buildx` and the image that matches the board. This is the same on every target, Pynq and Yocto boards included.

## Backends at a glance

`--method` (or `method` in the config file) picks how the build runs. The Docker method covers two kinds of image, which colcon-buildx tells apart by the image's [labels](reference/labels.md).

| Method | Image or SDK | Where the compiler runs | Host | Status |
|---|---|---|---|---|
| `docker` | An image that runs *as* the target, for example `k26-jazzy` | In the container, natively or under QEMU | Any host with Docker | Recommended |
| `docker` | A cross SDK image, for example `k26-oesdk-jazzy` | In the container, on the host architecture | Any host with Docker; the published SDK images are native on arm64 hosts and emulated on x86_64 | Supported |
| `sdk` | A Yocto/OE SDK installed on this host | On the host | Linux | Supported |
| `sysroot` | The board's own filesystem, mounted over SSHFS | On the host, with your toolchain file | Linux, aarch64 targets only | Experimental |

[Backends](backends.md) describes each one in detail.

## Where to go next

- [Install](install.md): the package, Docker and QEMU.
- [Usage](usage.md): the quick start and everyday commands.
- [Configuration](config.md): config files, their search order and precedence.
- [Backends](backends.md): what each `--method` does and needs.
- [Sync and deploy](sync-and-deploy.md): match the image to the board, and copy the build to it.
- [Yocto targets](yocto-targets.md): building for boards that run a meta-ros Yocto image.
- [Troubleshooting](troubleshooting.md): error messages and what to do about them.
- [Development](development.md): running the tests and working on colcon-buildx.
- Reference: [command line](reference/cli.md), [config keys](reference/config-keys.md), [image labels](reference/labels.md).

To choose an image for your board, see the images repository's [target reference](https://smarobix.github.io/smarobix-buildx-images/reference/targets/) and the boards they have been [tested on](https://smarobix.github.io/smarobix-buildx-images/reference/tested-hardware/).

Nothing in colcon-buildx is tied to those boards. It works with any image that has ROS 2 under `/opt/ros/<distro>` and a working colcon, so an arm64 image suits an NVIDIA Jetson or another Cortex-A53/A72/A76 board, and an armhf image suits a Cortex-A7 or A9 board running an ARMv7 user space. What has actually been tested is on the page above.
