# smarobix-colcon-buildx

A colcon verb, `colcon buildx`, that cross-builds a ROS 2 workspace for arm64 and armhf boards, inside a Docker image or against a Yocto/OpenEmbedded SDK.

smarobix-buildx-images and smarobix-colcon-buildx are two halves of one toolchain. The images repository defines every supported target — board, OS, architecture and ROS 2 distro — and publishes the Docker images and ROS 2 `.deb` packages for them. smarobix-colcon-buildx is the colcon verb that cross-builds your own workspace inside one of those images. To put ROS 2 on a board, use the images repository; to build your code for that board, use colcon-buildx.

## Install

```bash
pip install "git+https://github.com/smarobix/smarobix-colcon-buildx.git"
```

You also need Docker. On an x86_64 host, register QEMU as [the install guide](docs/install.md) describes.

## Quick start

This builds a workspace for a Kria K26 running Ubuntu and ROS 2 Jazzy. In the root of your workspace, the directory that contains `src/`, create `.buildx.conf`:

```ini
method = docker
docker_image = ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy
docker_platform = linux/arm64
```

Then build:

```bash
colcon buildx
```

colcon-buildx runs `colcon build` inside the image and writes the results to `cross_build/` and `cross_install/`, next to your `src/`. Arguments it doesn't know, such as `--packages-select my_pkg`, are passed on to `colcon build`.

To copy `cross_install/` to the board, add `deploy_target = ubuntu@10.42.0.3:~/ros2_ws/install/` to the file and run `colcon buildx --deploy`. It uses `rsync --delete`, so read [Deploy](docs/sync-and-deploy.md#deploy) first.

## Other boards

The images repository publishes an image for each supported board, OS, architecture and ROS 2 distro. Its [target picker](https://smarobix.github.io/smarobix-buildx-images/) asks for your board and gives the matching `.buildx.conf`, along with how to put ROS 2 on the board.

## Documentation

The documentation is published at <https://smarobix.github.io/smarobix-buildx-images/tool/>, and its source is in [`docs/`](docs/).

| Page | What it covers |
|---|---|
| [Install](https://smarobix.github.io/smarobix-buildx-images/tool/install/) ([source](docs/install.md)) | The package, Docker and QEMU |
| [Usage](https://smarobix.github.io/smarobix-buildx-images/tool/usage/) ([source](docs/usage.md)) | Everyday commands and the files colcon-buildx writes |
| [Configuration](https://smarobix.github.io/smarobix-buildx-images/tool/config/) ([source](docs/config.md)) | Config files, search order and precedence |
| [Backends](https://smarobix.github.io/smarobix-buildx-images/tool/backends/) ([source](docs/backends.md)) | Docker images, SDK images, `--method sdk` and `--method sysroot` |
| [Sync and deploy](https://smarobix.github.io/smarobix-buildx-images/tool/sync-and-deploy/) ([source](docs/sync-and-deploy.md)) | Matching the image to the board, and copying the build to it |
| [Yocto targets](https://smarobix.github.io/smarobix-buildx-images/tool/yocto-targets/) ([source](docs/yocto-targets.md)) | Building for boards that run a meta-ros image |
| [Troubleshooting](https://smarobix.github.io/smarobix-buildx-images/tool/troubleshooting/) ([source](docs/troubleshooting.md)) | Error messages and what to do about them |
| [Command line](https://smarobix.github.io/smarobix-buildx-images/tool/reference/cli/) ([source](docs/reference/cli.md)) | Every option |
| [Config keys](https://smarobix.github.io/smarobix-buildx-images/tool/reference/config-keys/) ([source](docs/reference/config-keys.md)) | Every config file key and its default |
| [Image labels](https://smarobix.github.io/smarobix-buildx-images/tool/reference/labels/) ([source](docs/reference/labels.md)) | The labels colcon-buildx reads from an image |
| [Development](https://smarobix.github.io/smarobix-buildx-images/tool/development/) ([source](docs/development.md)) | Tests, code layout and regenerating the reference pages |

Complete config files with every key are in [`examples/`](https://github.com/smarobix/smarobix-colcon-buildx/tree/main/examples).

## Contributing

Issues and pull requests are welcome on [GitHub](https://github.com/smarobix/smarobix-colcon-buildx). [Development](docs/development.md) explains how to run the tests and keep the generated reference pages up to date.

## License

Apache License 2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2025-2026 SMAROBIX GmbH.
