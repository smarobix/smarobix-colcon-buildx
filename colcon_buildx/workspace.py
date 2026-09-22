# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

"""Locate the colcon workspace being built.

The workspace root is the nearest directory, starting from the current one,
that holds src/. The config file search walks the same directories, so both
stop at the same place.
"""

from pathlib import Path

# Directories to look at, the current one included, before giving up.
MAX_LEVELS = 5


def is_workspace_root(path):
    """Return True if *path* holds a src/ directory."""
    return (Path(path) / 'src').is_dir()


def search_path(start=None):
    """
    Yield *start* and then its parents, up to the workspace root.

    Stops after the first directory that holds src/, at the filesystem root,
    or after MAX_LEVELS directories, whichever comes first.

    Args:
        start: Directory to start from; the current directory by default
    """
    current = Path(start) if start else Path.cwd()
    for _ in range(MAX_LEVELS):
        yield current
        if is_workspace_root(current):
            return
        parent = current.parent
        if parent == current:
            return
        current = parent


def find_workspace_root(start=None):
    """
    Find the workspace root.

    Args:
        start: Directory to start from; the current directory by default

    Returns:
        Path of the nearest directory holding src/, or None if there is none
    """
    for directory in search_path(start):
        if is_workspace_root(directory):
            return directory
    return None


def resolve_workspace_root(workspace_root=None):
    """
    Return *workspace_root*, or else the one found from the current directory.

    Falls back to the current directory when there is no workspace root. The
    verb warns about that once, so the builders that call this stay quiet.
    """
    if workspace_root:
        return Path(workspace_root)
    return find_workspace_root() or Path.cwd()
