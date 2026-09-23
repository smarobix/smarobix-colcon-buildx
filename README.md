# smarobix-colcon-buildx

`colcon buildx` is a colcon verb that cross-builds a ROS 2 workspace for arm64 and armhf boards, inside a Docker image made for the board or against a Yocto/OpenEmbedded SDK, and copies the result to the board. The images come from [smarobix-buildx-images](https://github.com/smarobix/smarobix-buildx-images), which also puts ROS 2 on boards that have no official packages. The documentation for both is one site: <https://smarobix.github.io/smarobix-buildx-images/>.

## Install

```bash
python3 -m venv ~/.venvs/buildx && . ~/.venvs/buildx/bin/activate
pip install "git+https://github.com/smarobix/smarobix-colcon-buildx.git"
colcon buildx --help
```

You also need Docker. On an x86_64 host, register QEMU once with `docker run --rm --privileged multiarch/qemu-user-static --reset -p yes`.

## Quick start

For a Kria K26 running Ubuntu 24.04 and ROS 2 Jazzy, create `.buildx.conf` in the workspace root, the directory that holds `src/`:

```ini
method = docker
docker_image = ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy
docker_platform = linux/arm64
deploy_target = ubuntu@10.42.0.3:~/ros2_ws/install/
```

Then `colcon buildx`. It runs `colcon build` inside the image and writes the result to `cross_build/` and `cross_install/`, next to `src/`, owned by you. Arguments it does not know, such as `--packages-select my_pkg`, go to `colcon build`. `colcon buildx --deploy` then copies `cross_install/` to the board with `rsync --delete`.

The [guided tutorial](https://smarobix.github.io/smarobix-buildx-images/start/setup/) covers every supported board, from an empty workspace to a node running on the board.

## Methods

`--method`, or `method` in the config file, picks how the build runs. The Docker method covers two kinds of image, told apart by the image's [labels](docs/labels.md).

| Method | Image or SDK | Compiles | Host | Status |
|---|---|---|---|---|
| `docker` | an image that runs *as* the board, such as `k26-jazzy` | in the container, natively or under QEMU | any, with Docker | recommended |
| `docker` | a cross SDK image, such as `k26-oesdk-jazzy` | in the container, on the host's architecture | any, with Docker | supported |
| `sdk` | a Yocto/OE SDK installed on this host | on the host | Linux | supported |
| `sysroot` | the board's own filesystem, mounted over SSHFS | on the host, with your toolchain file | Linux, aarch64 boards | experimental |

## Documentation

- [Reference](docs/reference.md): every option, config key and method. Generated from the code.
- [Troubleshooting](docs/troubleshooting.md): error messages and what to do about them.
- [Image labels](docs/labels.md): the contract between colcon-buildx and the images it uses.

These pages are served on the site under [`tool/`](https://smarobix.github.io/smarobix-buildx-images/tool/reference/). Complete config files with every key are in [`examples/`](examples/).

## Development

```bash
git clone https://github.com/smarobix/smarobix-colcon-buildx.git && cd smarobix-colcon-buildx
python3 -m venv ~/.venvs/buildx-dev && . ~/.venvs/buildx-dev/bin/activate
pip install -e ".[test]"
pytest -q && flake8
```

The tests need no Docker, SDK or board. To add an option: declare it in `BuildxVerb.add_arguments` with `default=None`, put its default in `DEFAULTS` or its name in `CONFIG_KEYS` (or in `ACTION_FLAGS` for a one-off device action), add it to both files in `examples/`, and regenerate the reference with `python tools/gen_docs.py`. CI checks that the generated page is current and that the relative links in `README.md` and `docs/` resolve (`python tools/check_links.py`).

Pages in `docs/` are also copied into the images site, so they use plain CommonMark, relative links between themselves, and absolute URLs to anything else.

Every source file carries an SPDX header (`Apache-2.0`, `SMAROBIX GmbH`); files that cannot are covered by `REUSE.toml`, and `reuse lint` runs in CI.

## License

Apache License 2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2025-2026 SMAROBIX GmbH.
