# Development

## Setting up

```bash
git clone https://github.com/smarobix/smarobix-colcon-buildx.git
cd smarobix-colcon-buildx
python3 -m venv ~/.venvs/buildx-dev
. ~/.venvs/buildx-dev/bin/activate
pip install -e ".[test]"
```

The virtual environment lives outside the checkout, so linters and `git status` don't see it.

The editable install registers the `buildx` verb with colcon, so `colcon buildx --help` runs the code in your checkout.

## Running the tests

```bash
pytest -q
flake8
```

`flake8` reads its settings from [`.flake8`](https://github.com/smarobix/smarobix-colcon-buildx/blob/main/.flake8), so it needs no arguments. CI runs both on every pull request, on the oldest and the newest Python the package is tested with; [`test.yml`](https://github.com/smarobix/smarobix-colcon-buildx/blob/main/.github/workflows/test.yml) has the matrix. The tests don't need Docker, an SDK or a board. They don't need colcon either: `tests/conftest.py` stands in for the few colcon names the extension imports when `colcon-core` isn't installed.

## Code layout

| Path | What it holds |
|---|---|
| `colcon_buildx/__init__.py` | The version, and the ROS 2 distros the extension knows about. |
| `colcon_buildx/verb/buildx.py` | The `buildx` verb: its command-line options, `DEFAULTS`, `CONFIG_KEYS`, `ACTION_FLAGS`, the `--help` epilog, and the dispatch to a backend. |
| `colcon_buildx/config/` | Finding and reading config files, and merging them with the command line and the defaults. |
| `colcon_buildx/workspace.py` | Finding the workspace root, which the config search and every backend share. |
| `colcon_buildx/docker/` | The Docker backend, the image label names, and synced-image detection. |
| `colcon_buildx/sdk/` | The `sdk` backend and `--emit-mixin`. |
| `colcon_buildx/sysroot/` | The experimental SSHFS `sysroot` backend. |
| `colcon_buildx/toolchain.py` | The CMake toolchain wrapper shared by both SDK routes. |
| `colcon_buildx/package_sync.py` | `--sync-from-device`. |
| `colcon_buildx/rosdep_manager.py` | `--install-deps` and `--install-deps-on-device`. |
| `colcon_buildx/deployment.py` | `--deploy`. |
| `examples/` | Complete config files, one per format. |
| `tests/` | The pytest suite. |
| `tools/gen_docs.py` | Generates the command-line and config-key reference pages. |
| `tools/check_links.py` | Checks the relative links in `README.md` and `docs/`. |

Every option is declared with `default=None`, and its real default lives in `DEFAULTS`. That keeps "not given on the command line" apart from "given with the default value", which is what lets a config file fill in any option. `CONFIG_KEYS` is every key a config file may set; anything else is reported as unrecognised. `ACTION_FLAGS` holds the one-off device actions, which are flags only, so a config file that names one gets a warning that points at the flag.

## Adding an option

1. Add the flag in `BuildxVerb.add_arguments`, with `default=None`.
2. If it has a default, add it to `DEFAULTS`. If a config file may set it but it has no default, add its name to `CONFIG_KEYS`. If it is a one-off action that replaces the build, add it to `ACTION_FLAGS` instead of `CONFIG_KEYS`.
3. Add it to both files in `examples/`, with a comment.
4. Regenerate the reference pages, as below.

## The documentation

The pages in `docs/` are published as part of the images repository's site, under [`tool/`](https://smarobix.github.io/smarobix-buildx-images/tool/). The site copies this repository's `docs/` directory when it builds, so write them to work both on GitHub and in the site:

- plain CommonMark with GitHub tables and fenced code blocks, and no MkDocs-only syntax;
- relative links between pages in `docs/`;
- absolute `https://github.com/smarobix/smarobix-colcon-buildx/blob/main/...` links to anything outside `docs/`, such as the README or the code, because it isn't part of the site;
- absolute `https://smarobix.github.io/smarobix-buildx-images/...` links to the images repository's pages.

Two reference pages are generated from the code: [`reference/cli.md`](reference/cli.md) from the argument parser, and [`reference/config-keys.md`](reference/config-keys.md) from `DEFAULTS` and `CONFIG_KEYS`. Don't edit them by hand. After changing an option, its help text or a default, regenerate them and commit the result:

```bash
python tools/gen_docs.py
```

CI runs two checks from [`docs.yml`](https://github.com/smarobix/smarobix-colcon-buildx/blob/main/.github/workflows/docs.yml) when the code, the docs or the tools change. Run them locally before you push:

```bash
python tools/gen_docs.py --check   # fails if a generated page is out of date
python tools/check_links.py        # fails on a broken relative link or anchor
```

The link check also rejects a relative link from `docs/` to a file outside it, and an anchor that GitHub and MkDocs would spell differently.

## Licensing

The code is under the Apache License 2.0. Every source file starts with an SPDX header:

```python
# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0
```

Markdown, example configs and other files that can't carry a header are covered by [`REUSE.toml`](https://github.com/smarobix/smarobix-colcon-buildx/blob/main/REUSE.toml). CI checks this with `reuse lint`.
