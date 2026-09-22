# Configuration

Every setting can come from three places. The first one that has a value wins:

1. the command line;
2. a config file;
3. the built-in default.

A flag on the command line wins even when its value equals the default.

## Config file names

colcon-buildx reads at most one config file per run, in one of two formats with the same keys:

| File | Format |
|---|---|
| `.buildx.conf` | `key = value` lines |
| `.buildx.yml` or `.buildx.yaml` | a YAML mapping |

## Search order

With `--config PATH`, colcon-buildx reads that file. The format follows the extension: `.yml` and `.yaml` are read as YAML, anything else as `key = value`. If the file doesn't exist, it prints `Specified config file not found: PATH` and carries on with no config file.

Without `--config`, it starts in the current directory and looks for `.buildx.conf`, `.buildx.yml` and `.buildx.yaml`, in that order. If none is there, it moves up to the parent directory and tries again. It stops at the workspace root, the directory that contains `src/`, and goes at most four levels up. The first file it finds is the only one it reads; files are never merged.

If a file can't be parsed, colcon-buildx prints `Failed to load config from FILE: ERROR` and carries on without it.

## The `.conf` format

```ini
# Kria K26 running Ubuntu 24.04 and ROS 2 Jazzy
method = docker
docker_image = ghcr.io/smarobix/smarobix-buildx-images:k26-jazzy
docker_platform = linux/arm64
deploy_target = ubuntu@10.42.0.3:~/ros2_ws/install/
```

- One `key = value` per line. Spaces around `=` are optional.
- A line that starts with `#` is a comment. A `#` after a value is part of the value, so put comments on their own line.
- Quotes around a whole value are removed.
- `true`, `yes` and `1` mean true; `false`, `no` and `0` mean false. Case doesn't matter.
- Keys may use hyphens instead of underscores: `docker-image` is the same key as `docker_image`.

## The YAML format

```yaml
# Pynq-Z1 or Pynq-Z2 running PYNQ v3.1.1 and ROS 2 Jazzy
method: docker
docker_image: ghcr.io/smarobix/smarobix-buildx-images:pynq-v3.1.1-jazzy
docker_platform: linux/arm/v7
```

Booleans are YAML booleans (`true`, `false`). Hyphenated keys work here too.

## Keys

A key is the name of the command-line option without the leading `--`, with underscores for hyphens: `--docker-image` becomes `docker_image`. The [config keys reference](reference/config-keys.md) lists every key with its default and its flag.

Two things on the command line have no key:

- `--config` itself;
- the arguments passed through to `colcon build`, such as `--packages-select`. There is no `colcon_args` key; put colcon arguments on the command line.

A key colcon-buildx doesn't know is ignored with a warning, `Ignoring unrecognised config key: KEY`. The run carries on, so check for the warning after editing the file. A misspelt `docker_platform` would otherwise build silently for the default architecture.

A `method` other than `docker`, `sdk` or `sysroot` stops the run with `Unknown method`.

Complete examples that set every key, with a comment on each, are in the repository: [`examples/buildx.conf`](https://github.com/smarobix/smarobix-colcon-buildx/blob/main/examples/buildx.conf) and [`examples/buildx.yml`](https://github.com/smarobix/smarobix-colcon-buildx/blob/main/examples/buildx.yml). Copy one to your workspace root as `.buildx.conf` or `.buildx.yml` and delete what you don't need.

## Keys that change what every run does

A config file applies to every run, so some keys are better left on the command line.

- **`sync_from_device` and `install_deps_on_device`.** With either one set in a config file, every `colcon buildx` run does only that step and exits without building. Pass `--sync-from-device` and `--install-deps-on-device` on the command line when you need them. See [Sync and deploy](sync-and-deploy.md).
- **`deploy = true`.** Every successful build is followed by `rsync --delete` to `deploy_target`, which removes anything else in that directory on the board. See [Deploy](sync-and-deploy.md#deploy).
- **`install_deps = true`.** With the Docker method, every build first runs `rosdep install` and commits a new image.

Boolean options have no "off" switch on the command line. If the config file sets `deploy = true`, a run without deploying needs another config file, given with `--config`.

## Several boards in one workspace

Keep one config file per board and choose one with `--config`. Give each its own `build_base` and `install_base`, so that the boards' build trees don't mix:

```ini
# ~/ros2_ws/pynq.buildx.conf
method = docker
docker_image = ghcr.io/smarobix/smarobix-buildx-images:pynq-v3.1.1-jazzy
docker_platform = linux/arm/v7
build_base = cross_build_pynq
install_base = cross_install_pynq
```

```bash
cd ~/ros2_ws
colcon buildx --config pynq.buildx.conf
```
