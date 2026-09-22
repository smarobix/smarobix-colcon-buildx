# Sync and deploy

Three options connect a build to a real board over SSH:

- `--install-deps-on-device` installs your workspace's dependencies on the board;
- `--sync-from-device` makes a local copy of the image whose package versions match the board;
- `--deploy` copies `cross_install/` to the board after a build.

The first two only work with boards and images that use apt and dpkg, such as Ubuntu on a K26, PYNQ, and Raspberry Pi OS or Debian. Both work for arm64 and armhf boards; `--sync-from-device` runs the image with the configured `docker_platform`. Use SSH keys, because colcon-buildx opens several SSH connections per run.

## The device is the source of truth

Packages on a board drift away from the image over time, through security updates and packages installed by hand. A binary built against newer headers than the board has, or against a library the board lacks, fails when it runs. The fix is to treat the board as the reference, and make the image match it:

```bash
# 1. bring the board up to date
ssh ubuntu@10.42.0.3 'sudo apt-get update && sudo apt-get upgrade -y'

# 2. install the workspace's dependencies on the board
colcon buildx --install-deps-on-device ubuntu@10.42.0.3

# 3. make the image match the board
colcon buildx --sync-from-device ubuntu@10.42.0.3

# 4. build; this uses the synced image automatically
colcon buildx
```

Steps 2 and 3 each do only that one thing and then exit, without building. For that reason, don't set `install_deps_on_device` or `sync_from_device` in a config file: every run would then do the step and skip the build.

## Installing dependencies on the board

`--install-deps-on-device SSH_TARGET`:

1. reads the `package.xml` files under `src/` and stops early if they declare no dependencies;
2. copies `src/` to a temporary directory on the board with rsync;
3. takes the ROS distro from the first directory in `/opt/ros` on the board;
4. runs `sudo rosdep init` if rosdep has no sources yet, then `rosdep update` and `rosdep install --from-paths src`, with `rosdep_args` (default `--ignore-src -y`);
5. deletes the temporary directory.

It runs interactively, so `sudo` can ask for a password. The board needs `rosdep` (on Debian and Ubuntu, the `python3-rosdep` package) and `rsync`, and bash as the SSH user's login shell. It works with any `--method`.

## Syncing the image from the board

`--sync-from-device SSH_TARGET` works with the Docker method only. It:

1. lists the packages installed on the board with `dpkg-query`, and the packages in the configured image;
2. for each package in both whose version differs, installs the board's version in a container of the image, downgrading if needed;
3. installs the packages that are only on the board, where the image's apt sources have them;
4. leaves alone the packages that are only in the image;
5. commits the container as a local image, `<tag>-synced-<YYYYMMDD>`, where the suffix is today's date. Nothing is pushed.

It always starts from the tag you configured, not from an earlier synced image. Under QEMU it can take a while.

It also writes two files into the workspace root:

- `.buildx-sync-manifest.json`, which records the base image, the synced image and what the sync did;
- `cross_log/sync-packages-<YYYYMMDD-HHMMSS>.log`, when there was anything to change: a report of every package it version-matched, installed, couldn't find or failed to install, with the reason.

Add both to your workspace's `.gitignore`.

### Which image a build uses

Every Docker build looks for local images whose tag is `<tag>-synced-<YYYYMMDD>`, for the tag you configured, and uses the newest. For `k26-jazzy`, that is the newest `k26-jazzy-synced-` image. The build prints `Using synced image:` with its name, or `Using base image:` when there is none.

To build with the tag as published, pass `--use-base-image` or set `use_base_image = true`. To go back to the published tag for good, delete the synced images with `docker rmi`.

`--install-deps` with the Docker method also commits a `<tag>-synced-<YYYYMMDD>` image and updates the manifest, so later builds pick that image up the same way. Its packages are installed only in the image, not on the board.

## Deploy

`--deploy` copies the install directory to the board after a successful build. It needs `deploy_target` in the config file, or `--deploy-target` on the command line:

```bash
colcon buildx --deploy
colcon buildx --deploy --deploy-target ubuntu@10.42.0.3:~/ros2_ws/install/
```

It runs:

```bash
rsync -avz --delete cross_install/ ubuntu@10.42.0.3:~/ros2_ws/install/
```

**`--delete` removes every file in the target directory that isn't in `cross_install/`.** Point `deploy_target` at a directory that holds only this workspace's install tree, never at a home directory, `/opt/ros` or anything else you want to keep. colcon-buildx adds a trailing `/` to the target, so rsync copies the contents of `cross_install/` into it.

Both the host and the board need `rsync`, and the host needs SSH access to the board. Run it from the workspace root. If `deploy = true` is in the config file, every successful build deploys.

On the board, source ROS first and then the workspace. The install tree is a merged one, so its setup scripts are at the top:

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/local_setup.bash
```

Boards running a minimal Yocto image may have no rsync and no bash. [Yocto targets](yocto-targets.md#deploying-and-sourcing-on-the-board) shows how to copy and source the result there.
