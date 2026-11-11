# colcon buildx

`colcon buildx` builds a ROS 2 workspace on your computer for the robot or board it will run on, and copies the result there. You name the robot's image in a two-line config file. The build runs on your computer's own architecture: nothing runs under emulation, and nothing needs installing except Docker.

[OEROS](https://github.com/oerosproject) is a reference distribution for ROS 2 robots, built with Yocto and meta-ros. Besides the robot's image, it publishes a stack of container images, among them SDK images that build software for the robot. colcon buildx uses those SDK images to build your workspace for a robot that runs OEROS.

## Install

```bash
python3 -m venv ~/.venvs/buildx && . ~/.venvs/buildx/bin/activate
pip install "git+https://github.com/smarobix/smarobix-colcon-buildx.git"
colcon buildx --help
```

You also need Docker.

## Quick start

In the workspace root, the directory that holds `src/`, create `.buildx.conf`:

```ini
method = docker
docker_image = ghcr.io/oerosproject/oeros-sdk-cross:lyrical-arm64
```

Then run `colcon buildx`. The result for the robot is in `cross_install/`, owned by you; colcon's build tree is in `cross_build/`. Arguments that colcon buildx does not know, such as `--packages-select my_pkg`, go to `colcon build`. To copy the result to the robot, add `deploy_target = root@my-robot.local:/opt/ws/install/` and run `colcon buildx --deploy`.

That image is for an x86_64 computer and an arm64 robot. The [OEROS guide](docs/oeros.md) shows which image fits your computer and robot, and how colcon buildx works with it.

## Boards without OEROS

For a 32-bit ARM board that keeps its vendor's image, such as PYNQ on a Pynq-Z1 or a 32-bit Raspberry Pi OS, name the board's image instead. colcon buildx copies its filesystem into a cross image for your computer and builds against it. [smarobix-buildx-images](https://github.com/smarobix/smarobix-buildx-images) publishes such images, and ROS 2 for those boards as a `.deb`. For 64-bit boards on Ubuntu or Debian, [pixi and RoboStack](https://robostack.github.io/) already cover the same ground.

## Limits

- **SDK images make no Python bindings for messages.** C++ nodes on the robot can use your messages; `rclpy` and the `ros2` command line cannot. Message packages that Python must use belong in the robot's image.
- **Board images must be Ubuntu or Debian**, because the cross compiler comes from the same release.
- **A package that runs a program it just built** during its own build, as some code generators do, fails: that program is built for the robot and cannot run on your computer. Build such a package into the robot's image.
- **`--install-deps` only works with an image of your computer's architecture.** It installs into a local copy of the image, not on the robot, so the versions may differ from what the robot has. Adding the dependency to the robot's image is the better fix.
- **A board image's Docker `ENV` is not carried into its cross image**, so settings such as an `LD_LIBRARY_PATH` it sets are lost.

## Documentation

The documentation site is <https://smarobix.github.io/smarobix-buildx-images/>. In this repository:

- [OEROS robots](docs/oeros.md): which image to use, how colcon buildx works with it, and how to label an image of your own.
- [Reference](docs/reference.md): every option, config key and method. Generated from the code.
- [Troubleshooting](docs/troubleshooting.md): error messages and what to do about them.

Complete config files with every key are in [`examples/`](examples/).

## Development

```bash
git clone https://github.com/smarobix/smarobix-colcon-buildx.git && cd smarobix-colcon-buildx
python3 -m venv ~/.venvs/buildx-dev && . ~/.venvs/buildx-dev/bin/activate
pip install -e ".[test]"
pytest -q && flake8
```

The tests need no Docker, SDK or board. To add an option: declare it in `BuildxVerb.add_arguments` with `default=None`, put its default in `DEFAULTS` or its name in `CONFIG_KEYS`, add it to both files in `examples/`, and regenerate the reference with `python tools/gen_docs.py`. CI checks that the generated page is current and that the relative links in `README.md` and `docs/` resolve (`python tools/check_links.py`).

The images colcon buildx derives are built from the recipes in [`colcon_buildx/docker/recipes/`](colcon_buildx/docker/recipes/); their tags include a hash of the recipes, so a change to a recipe rebuilds them. The diagrams in `docs/img/` come from `tools/gen_diagrams.py`.

Pages in `docs/` are also copied into the documentation site, so they use plain CommonMark, relative links between themselves, and absolute URLs to anything else.

Every source file carries an SPDX header (`Apache-2.0`, `SMAROBIX GmbH`); files that cannot are covered by `REUSE.toml`, and `reuse lint` runs in CI.

## License

Apache License 2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE). Copyright 2025-2026 SMAROBIX GmbH.
