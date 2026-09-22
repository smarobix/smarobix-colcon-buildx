# SPDX-FileCopyrightText: 2025-2026 SMAROBIX GmbH
# SPDX-License-Identifier: Apache-2.0

import io
import subprocess

import pytest

from colcon_buildx import docker, package_sync

IMAGE = 'ghcr.io/smarobix/smarobix-buildx-images:pynq-v3.1.1-jazzy'


class FakeDocker:
    """Stand in for ssh and docker, recording every command."""

    def __init__(self, device='libfoo\t1.1\tarmhf\n', image='libfoo\t1.0\tarmhf\n'):
        self.device = device
        self.image = image
        self.commands = []

    def run(self, cmd, **kwargs):
        self.commands.append(cmd)
        if cmd[0] == 'ssh':
            stdout = self.device
        elif cmd[:2] == ['docker', 'run'] and 'dpkg-query' in cmd:
            stdout = self.image
        else:
            stdout = ''
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr='')

    def popen(self, cmd, **kwargs):
        self.commands.append(cmd)
        return FakeProcess()

    def docker_runs(self):
        return [c for c in self.commands if c[:2] == ['docker', 'run']]


class FakeProcess:
    returncode = 0

    def __init__(self):
        self.stdout = io.StringIO('Package sync complete!\n')

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    fake = FakeDocker()
    monkeypatch.setattr(package_sync.subprocess, 'run', fake.run)
    monkeypatch.setattr(package_sync.subprocess, 'Popen', fake.popen)
    return fake


def _platform(cmd):
    return cmd[cmd.index('--platform') + 1] if '--platform' in cmd else None


@pytest.mark.parametrize('platform', ['linux/arm/v7', 'linux/arm64'])
def test_sync_runs_the_image_as_the_configured_platform(fake, tmp_path, platform):
    package_sync.sync_packages_from_device(
        IMAGE, 'ubuntu@10.42.0.3', tmp_path / '.buildx-sync-manifest.json', platform)

    runs = fake.docker_runs()
    # One run lists the image's packages, the other installs the device's.
    assert len(runs) == 2
    assert [_platform(cmd) for cmd in runs] == [platform, platform]


def test_sync_without_a_platform_lets_docker_choose(fake, tmp_path):
    package_sync.sync_packages_from_device(
        IMAGE, 'ubuntu@10.42.0.3', tmp_path / '.buildx-sync-manifest.json')
    assert all('--platform' not in cmd for cmd in fake.docker_runs())


def test_docker_builder_passes_its_platform_to_the_sync(tmp_path, monkeypatch):
    (tmp_path / 'src').mkdir()
    monkeypatch.chdir(tmp_path)
    seen = {}

    def sync(base_image, ssh_target, manifest_path, platform=None):
        seen.update(image=base_image, platform=platform)
        return base_image + '-synced-20260922'

    monkeypatch.setattr(package_sync, 'sync_packages_from_device', sync)
    builder = docker.DockerBuilder(
        IMAGE, 'linux/arm/v7', 'cross_build', 'cross_install', use_base_image=True)
    builder.create_synced_image('ubuntu@10.42.0.3')

    assert seen == {'image': IMAGE, 'platform': 'linux/arm/v7'}
