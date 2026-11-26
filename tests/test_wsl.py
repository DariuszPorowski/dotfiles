"""Exercise the WSL helpers with isolated files and fake native commands, never WSL."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest

from smoke import BASH, ROOT

WSL = ROOT / "home" / "dot_wsl"
UUID = "01234567-89ab-4cde-8123-0123456789ab"
DISK = r"D:\offline disks\workspaces.vhdx"
PWSH = shutil.which("pwsh")


class Fixture(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix=".wsl-fixture-")
        def cleanup():
            # Git Bash on Windows can hold a directory handle briefly after exit.
            for attempt in range(10):
                try:
                    directory.cleanup()
                    return
                except PermissionError:
                    if os.name != "nt" or attempt == 9:
                        raise
                    time.sleep(0.2)
        self.addCleanup(cleanup)
        self.cwd = Path(directory.name)
        self.env = {**os.environ, "HOME": str(self.cwd), "USERPROFILE": str(self.cwd),
                    "TMPDIR": str(self.cwd), "TEMP": str(self.cwd), "TMP": str(self.cwd),
                    "BASH_ENV": "", "ENV": "", "SUDO_USER": "owner"}

    def write(self, name, contents):
        dest = self.cwd / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(contents.encode())
        return dest

    def run_fixture(self, argv, ok=True, **env):
        proc = subprocess.run(argv, env={**self.env, **env}, cwd=self.cwd,
                              text=True, capture_output=True, timeout=45)
        self.assertEqual(proc.returncode == 0, ok, proc.stdout + proc.stderr)
        return proc.stdout + proc.stderr

    def calls(self):
        path = self.cwd / "calls"
        return path.read_text().splitlines() if path.exists() else []


@unittest.skipUnless(BASH, "Requires bash (Git Bash on Windows)")
class Guest(Fixture):
    def setUp(self):
        super().setUp()
        # No fallback to PATH, the real wsl.exe, package managers or service utilities.
        for cmd in ("dirname", "grep", "readlink", "sed", "awk", "rm", "sh"):
            self.stub(cmd, f'exec /usr/bin/{cmd} "$@"')
        self.stub("mountpoint", '[ "$OCCUPIED" = 1 ]')
        self.stub("wsl.exe", ':')
        self.stub("sudo", '''
            case $1 in
              findmnt) [ -n "$PROBE" ] && printf '%s\\n' "$PROBE" ;;
              ln|chown|chmod) : ;;
              *) exit 98 ;;
            esac''')
        self.stub("id", 'printf "owner\\n"')
        for name in ("startup.sh", "mount-workspaces.sh", "workspace-volume.sh", "vhdx-init.sh"):
            src = (WSL / name).read_text()
            self.write(name, src.replace("mount_point=/mnt/wsl/workspaces", 'mount_point="$PWD/volume"')
                       .replace("workspace_alias=/workspaces", 'workspace_alias="$PWD/alias"'))
        (self.cwd / "volume").mkdir()

    def stub(self, name, body):
        self.write("bin/" + name, "#!/bin/sh\n" + f"printf '%s\\n' '{name} '\"$*\" >> calls\n"
                   + textwrap.dedent(body).strip() + "\n").chmod(0o755)

    def shell(self, *args, ok=True, **env):
        return self.run_fixture([BASH, "--noprofile", "--norc", "-c",
                                 'export PATH="$PWD/bin"; exec sh "$@"', "fixture", *args],
                                ok, **{"OCCUPIED": "0", "PROBE": f"ext4 workspaces {UUID} /", **env})

    def test_identity_is_checked_after_attach_and_on_reuse(self):
        for occupied, probe in (("0", f"ext4 workspaces {UUID[:-1]}0 /"),
                                ("1", f"ext4 workspaces {UUID} /subdir"), ("1", "")):
            with self.subTest(occupied=occupied, probe=probe):
                self.write("calls", "")
                self.shell("mount-workspaces.sh", UUID, DISK, OCCUPIED=occupied, PROBE=probe, ok=False)
                calls = self.calls()
                self.assertEqual(f"wsl.exe --mount --vhd {DISK} --name workspaces" in calls,
                                 occupied == "0")
                self.assertFalse(any(c.startswith("sudo ln") for c in calls))
        self.shell("mount-workspaces.sh", UUID, DISK)
        self.assertTrue(any(c.startswith("sudo ln -sT --") for c in self.calls()))

    def test_alias_conflicts_and_owner_check(self):
        self.write("alias", "existing work")
        self.shell("mount-workspaces.sh", UUID, DISK, OCCUPIED="1", ok=False)
        self.assertEqual((self.cwd / "alias").read_text(), "existing work")
        self.shell("vhdx-init.sh", UUID, PROBE="ext4 workspaces wrong /", ok=False)
        self.assertFalse(any(c.startswith(("sudo ln", "sudo chown", "sudo chmod")) for c in self.calls()))
        self.shell("vhdx-init.sh", UUID)
        self.assertTrue(any(c.startswith("sudo chmod 2770 ") for c in self.calls()))

    def test_first_use_and_legacy(self):
        self.shell("startup.sh", WSL_WORKSPACES_VHDX_FILE=DISK)
        self.assertFalse(any(c.startswith(("wsl.exe", "sudo ")) for c in self.calls()))
        self.shell("mount-workspaces.sh", "--attach-bare", DISK)
        self.assertIn(f"wsl.exe --mount --vhd {DISK} --bare", self.calls())
        self.assertFalse(any(c.startswith("sudo ") for c in self.calls()))

    def prepare_cloud(self, gui):
        template = "Ubuntu-26.04" + ("-gui" if gui else "") + ".user-data"
        source = (WSL / "cloud-init" / template).read_text()
        blocks = source.split("\nruncmd:\n", 1)[1].split("\nfinal_message:", 1)[0].split("  - |\n")
        # cloud-init shellifies string entries into a single /bin/sh script.
        script = "\n".join(textwrap.dedent(b) for b in blocks)
        self.write("runcmd", script.replace("/etc/", "./etc/").replace("__RDP_PORT__", "4321")
                   .replace("__HOSTNAME__", "ubuntu-dev"))
        self.write("etc/skel/.xsession", "")
        self.stub("adduser", ":")
        self.stub("dpkg", '[ "$1" = --print-architecture ] && echo "${GUEST_ARCH:-amd64}"')
        self.stub("snap", '[ "${FAIL_TOOL:-}" != powershell ]')
        self.stub("apt-get", '''
            if [ "$*" = "--yes install xrdp" ]; then
              [ -f xrdp.service.masked ] && [ -f xrdp.socket.masked ] || exit 91
            fi
            [ "$3" != "${FAIL_TOOL:-}" ]''')
        self.stub("systemctl", '''
            case $1 in
              mask) shift; for unit do : > "$unit.masked"; done ;;
              show) if [ -f "$5.masked" ]; then printf 'masked\\n'; else printf 'not-found\\n'; fi ;;
              unmask) rm "$2.masked" ;;
              enable) [ ! -e xrdp.service.masked ] ;;
              *) exit 97 ;;
            esac''')
        if gui:
            packages = source.split("\npackages:\n", 1)[1].split("\nruncmd:", 1)[0]
            self.assertNotIn("  - xrdp", packages.splitlines())
            self.stub("cloud-init-per", '''
                [ "$1" = instance ] || exit 96
                marker="instance.$2"
                [ ! -f "$marker" ] || exit 0
                shift 2
                "$@" || exit $?
                : > "$marker"''')
            self.boot = source.split("\nbootcmd:\n  - [", 1)[1].split("]", 1)[0].split(", ")
            self.guest_boot()

    def guest_boot(self):
        self.shell("bin/" + self.boot[0], *self.boot[1:])

    def test_xrdp_mask_across_reboots(self):
        self.prepare_cloud(True)
        # Interrupted after the early stage: once-per-instance need not run again,
        # since mask (not --runtime mask) persists while runcmd has not succeeded.
        self.guest_boot()
        self.assertTrue((self.cwd / "xrdp.service.masked").is_file())
        self.assertTrue((self.cwd / "xrdp.socket.masked").is_file())
        self.write("etc/xrdp/xrdp.ini", "[Globals]\nport=3389\n")
        self.shell("runcmd")
        self.guest_boot()
        self.assertFalse((self.cwd / "xrdp.service.masked").exists())
        self.assertTrue((self.cwd / "xrdp.socket.masked").is_file())
        self.assertEqual(self.calls().count("systemctl mask xrdp.service xrdp.socket"), 1)

    def test_gui_held_before_install_and_verified_before_start(self):
        self.prepare_cloud(True)
        (self.cwd / "xrdp.socket.masked").unlink()
        self.write("etc/xrdp/xrdp.ini", "[Globals]\nport=3389\n")
        self.shell("runcmd", ok=False)
        self.assertNotIn("apt-get --yes install xrdp", self.calls())
        self.write("xrdp.socket.masked", "")
        self.write("etc/xrdp/xrdp.ini", "[Globals]\nport=3389\n Port =3389\n[other]\nport=unused\n")
        self.shell("runcmd", ok=False)
        self.assertTrue((self.cwd / "xrdp.service.masked").exists())
        self.assertNotIn("systemctl unmask xrdp.service", self.calls())
        self.write("etc/xrdp/xrdp.ini", "[Globals]\nport=3389\n[other]\nport=unused\n")
        self.shell("runcmd", FAIL_TOOL="powershell", ok=False)
        self.assertEqual((self.cwd / "etc/xrdp/xrdp.ini").read_text(),
                         "[Globals]\nport=tcp://127.0.0.1:4321\n[other]\nport=unused\n")
        self.assertIn("systemctl enable --now xrdp.service", self.calls())
        self.assertTrue((self.cwd / "xrdp.socket.masked").exists())
        self.assertIn("apt-get --yes install task", self.calls())

    def test_vendor_package_installs_are_independent(self):
        self.prepare_cloud(False)
        for failed in ("powershell", "task"):
            self.write("calls", "")
            self.shell("runcmd", FAIL_TOOL=failed, ok=False)
            self.assertIn("apt-get --yes install powershell", self.calls())
            self.assertIn("apt-get --yes install task", self.calls())
        self.shell("runcmd")

    def test_arm64_uses_native_powershell_in_both_profiles(self):
        for gui in (False, True):
            with self.subTest(gui=gui):
                self.prepare_cloud(gui)
                if gui:
                    self.write("etc/xrdp/xrdp.ini", "[Globals]\nport=3389\n")
                self.write("calls", "")
                self.shell("runcmd", GUEST_ARCH="arm64", FAIL_TOOL="powershell" if gui else "",
                           ok=not gui)
                self.assertIn("snap install powershell --classic --channel=latest/stable", self.calls())
                self.assertNotIn("apt-get --yes install powershell", self.calls())
                self.assertIn("apt-get --yes install task", self.calls())


@unittest.skipUnless(PWSH, "Requires pwsh")
class Installer(Fixture):
    def setUp(self):
        super().setUp()
        source = (WSL / "New-WSL.ps1").read_text()
        # Use real file hashing and no-replace moves against a tiny fixture image.
        self.write("New-WSL.ps1", source.replace(
            "48d56724b5c8e60f24893e83e73bbb58c60b3ca22fba3da977075420acd54104",
            hashlib.sha256(b"good").hexdigest()).replace(
            "c7d893d7ccb291009e6096c5a946937337b6fd4c426f11b6541f6cd2bf894f7d",
            hashlib.sha256(b"good-arm64").hexdigest()).replace(
            "[Runtime.InteropServices.RuntimeInformation]::OSArchitecture", "$env:FIXTURE_ARCH"))
        shutil.copytree(WSL / "cloud-init", self.cwd / "cloud-init")
        self.env.update(LOCALAPPDATA=str(self.cwd / "local"), USERNAME="Tester", FIXTURE_ARCH="X64",
                        POWERSHELL_TELEMETRY_OPTOUT="1", DOTNET_CLI_TELEMETRY_OPTOUT="1")
        self.write("fixture.ps1", r"""
$ErrorActionPreference = 'Stop'
Set-Variable -Scope Global HOME $PWD.Path -Force
function Get-CimInstance($ClassName, $Filter, $Property) {
    switch ($ClassName) {
        Win32_OptionalFeature {
            if ($Filter -ne "Name='VirtualMachinePlatform'" -or $Property -ne 'InstallState') { throw 'Unexpected feature query' }
            $state = switch ($env:MODE) { 'vmp-disabled' { 2 } 'vmp-absent' { 3 } default { 1 } }
            [pscustomobject]@{InstallState=$state}
        }
        Win32_ComputerSystem {
            if ($Property -ne 'HypervisorPresent') { throw 'Unexpected hypervisor query' }
            [pscustomobject]@{HypervisorPresent=($env:MODE -ne 'hypervisor-off')}
        }
        default { throw "Unexpected CIM query: $ClassName" }
    }
}
function wsl.exe {
    Add-Content calls ("wsl " + ($args -join ' '))
    $global:LASTEXITCODE = 0
    if ($args[0] -eq '--list' -and $env:MODE -eq 'registered') { $env:INSTANCE }
    if ($args[0] -eq '--install' -and $env:MODE -eq 'install-fail') { $global:LASTEXITCODE = 9 }
    if ($args[0] -eq '--manage' -and $env:MODE -eq 'sparse-fail') { $global:LASTEXITCODE = 8 }
    $oobe = $env:MODE -like 'oobe-*'
    $masked = "Failed to wait for network: Unexpected error while running command.`nCommand: ['systemctl', 'start', 'systemd-networkd-wait-online.service']`nExit code: 1`nReason: -`nStdout: `nStderr: Failed to start systemd-networkd-wait-online.service: Unit systemd-networkd-wait-online.service is masked."
    if ($args -contains 'cloud-init') {
        $state = if ($env:MODE -eq 'disabled' -or $oobe) { 'disabled' } else { 'done' }
        $reason = if ($oobe) { 'disabled-by-marker-file' } else { 'enabled-by-generator' }
        $ds = if ($env:MODE -eq 'wrong-datasource') { 'nocloud' } else { 'wsl' }
        $warnings = @{}
        if ($env:MODE -eq 'oobe-rebooted') { $ds = '' }
        elseif ($oobe -or $env:MODE -eq 'masked-done') {
            $warnings = @{ERROR=@($masked,$masked)}
            $global:LASTEXITCODE = 2
        }
        if ($env:MODE -eq 'degraded') { $warnings = @{ERROR=@('repository unavailable')}; $global:LASTEXITCODE = 2 }
        @{status=$state; boot_status_code=$reason; datasource=$ds; errors=@(); recoverable_errors=$warnings} | ConvertTo-Json -Depth 5 -Compress
    } elseif ($args -contains '/var/lib/cloud/data/result.json') {
        if ($env:MODE -eq 'oobe-missing') { $global:LASTEXITCODE = 1; return }
        $record = @{datasource='DataSourceWSL'; errors=@()}
        if ($env:MODE -eq 'oobe-final-error') { $record.errors = @('scripts-user failed') }
        @{v1=$record} | ConvertTo-Json -Depth 5 -Compress
    } elseif ($args -contains '/var/lib/cloud/data/status.json') {
        $record = @{datasource='DataSourceWSL'}
        foreach ($stage in 'init-local','init','modules-config','modules-final') {
            $record[$stage] = @{finished=123; errors=@(); recoverable_errors=@{}}
        }
        $record.init.recoverable_errors = @{ERROR=@($masked)}
        if ($env:MODE -eq 'oobe-mixed') { $record.init.recoverable_errors.ERROR += 'GPG key download failed' }
        if ($env:MODE -eq 'oobe-incomplete') { $record.'modules-final'.finished = $null }
        @{v1=$record} | ConvertTo-Json -Depth 6 -Compress
    } elseif ($args -contains 'sh') {
        if ($args[3] -ne $env:LOGIN) { throw 'Expected to check tools as the requested guest user' }
        if ($env:MODE -eq 'oobe-no-tools') { $global:LASTEXITCODE = 1 }
    }
}
function Invoke-WebRequest {
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    Add-Content calls "download $Uri"
    $bytes = if ($env:MODE -eq 'bad-hash') { 'bad' }
             elseif ($Uri -like '*-arm64.wsl' -and $env:MODE -ne 'wrong-arch') { 'good-arm64' }
             else { 'good' }
    [IO.File]::WriteAllText($OutFile, $bytes)
    if ($env:MODE -eq 'interrupt') { throw 'fixture download interrupted' }
}
try {
    & ./New-WSL.ps1 -Name $env:INSTANCE -Username $env:LOGIN -GUI:($env:MODE -ne 'base') -Sparse -VerifyOnly:($env:VERIFY_ONLY -eq '1')
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
""")

    def install(self, mode, ok=True, name="Ubuntu-26.04", login="dev"):
        return self.run_fixture([PWSH, "-NoProfile", "-NonInteractive", "-File", "fixture.ps1"],
                                ok, MODE=mode, INSTANCE=name, LOGIN=login)

    def test_cache_and_config_retry_without_overwrite(self):
        cache = self.cwd / "local/WSL/.images"
        cache.mkdir(parents=True)
        image = cache / "ubuntu-26.04.1-wsl-amd64.wsl"
        image.write_bytes(b"invalid old cache")
        self.install("interrupt", ok=False)
        self.assertFalse(image.exists())
        self.assertEqual(next(cache.glob("*.invalid")).read_bytes(), b"invalid old cache")
        self.install("bad-hash", ok=False)
        self.assertFalse(image.exists())
        self.assertEqual(list(cache.glob("*.part")), [])
        self.install("install-fail", ok=False)
        self.assertEqual(image.read_bytes(), b"good")
        self.assertIn("download https://releases.ubuntu.com/26.04.1/ubuntu-26.04.1-wsl-amd64.wsl", self.calls())
        config = self.cwd / ".cloud-init/Ubuntu-26.04.user-data"
        saved = config.read_bytes()
        self.assertIn(b'name: "dev"', saved)
        self.write("calls", "")
        self.assertIn("Conflicting cloud-init", self.install("ok", login="other", ok=False))
        self.assertEqual(config.read_bytes(), saved)
        self.assertFalse(any(c.startswith("wsl --install") for c in self.calls()))
        self.assertIn("Continuing first boot", self.install("sparse-fail"))
        # PowerShell function mocks consume the native end-of-options marker.
        self.assertIn("wsl --distribution Ubuntu-26.04 --user root cloud-init status --wait --format=json", self.calls())
        self.assertNotIn("wsl --distribution Ubuntu-26.04", self.calls())
        self.assertFalse(any(c.startswith("download") for c in self.calls()))
        self.assertEqual(list(config.parent.glob("*.part")), [])

    def test_first_boot_requires_completed_wsl_datasource(self):
        for mode in ("disabled", "wrong-datasource", "degraded"):
            with self.subTest(mode=mode):
                self.assertIn("cloud-init status --long", self.install(mode, ok=False))
        self.install("base", name="cli-dev")
        config = (self.cwd / ".cloud-init/cli-dev.user-data").read_text()
        self.assertIn("hostname = cli-dev", config)
        self.assertNotIn("xrdp.service", config)
        self.assertFalse(any(marker in config for marker in ("__USERNAME__", "__HOSTNAME__", "__RDP_PORT__")))

    def test_verify_existing_after_ubuntu_oobe(self):
        self.env["VERIFY_ONLY"] = "1"
        for mode in ("oobe-reported", "oobe-rebooted", "masked-done"):
            with self.subTest(mode=mode):
                output = self.install(mode, name="general-dev")
                self.assertIn("network wait unit was masked", output)
                self.assertIn("First boot verified", output)
        for mode, reason in (("oobe-missing", "missing or unreadable"), ("oobe-incomplete", "Missing completed WSL final stage"),
                             ("oobe-final-error", "No successful WSL final-stage result"),
                             ("oobe-mixed", "Unexpected recoverable cloud-init error"), ("oobe-no-tools", "Could not verify user")):
            with self.subTest(mode=mode):
                self.assertIn(reason, self.install(mode, name="general-dev", ok=False))
        self.assertTrue(all(c.startswith("wsl --distribution general-dev --user ") for c in self.calls()))
        self.assertFalse((self.cwd / ".cloud-init").exists())
        self.assertFalse((self.cwd / "local").exists())

    def test_virtualization_failures_stop_before_download(self):
        self.env["FIXTURE_ARCH"] = "Arm64"
        for mode, hint in (("vmp-disabled", "--no-distribution"), ("vmp-absent", "--no-distribution"),
                           ("hypervisor-off", "no running hypervisor")):
            with self.subTest(mode=mode):
                self.assertIn(hint, self.install(mode, ok=False))
                self.assertFalse(any(c.startswith(("download", "wsl --install")) for c in self.calls()))
                self.assertFalse((self.cwd / "local/WSL/.images").exists())
                self.assertFalse((self.cwd / ".cloud-init").exists())

    def test_retry_preserves_existing_distro_or_leftover_directory(self):
        disk = self.write("local/WSL/general-dev/ext4.vhdx", "existing data")
        self.assertIn("already registered", self.install("registered", name="general-dev", ok=False))
        self.assertIn("not registered", self.install("ok", name="general-dev", ok=False))
        self.assertEqual(disk.read_text(), "existing data")
        self.assertFalse(any(c.startswith(("download", "wsl --install", "wsl --unregister")) for c in self.calls()))

    def test_arm64_download_uses_separate_verified_cache(self):
        cache = self.cwd / "local/WSL/.images"
        cache.mkdir(parents=True)
        amd = cache / "ubuntu-26.04.1-wsl-amd64.wsl"
        arm = cache / "ubuntu-26.04.1-wsl-arm64.wsl"
        amd.write_bytes(b"good")
        self.env["FIXTURE_ARCH"] = "Arm64"
        self.assertIn("checksum mismatch", self.install("wrong-arch", ok=False))
        self.assertFalse(arm.exists())
        self.assertFalse(any(c.startswith("wsl --install") for c in self.calls()))
        self.write("calls", "")
        self.install("base", name="arm-dev")
        self.assertIn("download https://cdimage.ubuntu.com/ubuntu/releases/26.04.1/release/" + arm.name, self.calls())
        self.assertIn(f"wsl --install --from-file {arm} --name arm-dev --location {self.cwd / 'local/WSL/arm-dev'}"
                      " --version 2 --no-launch", self.calls())
        self.assertEqual(arm.read_bytes(), b"good-arm64")
        self.assertEqual(amd.read_bytes(), b"good")

    def test_incompatible_host_or_landscape_override_stops_before_install(self):
        self.env["FIXTURE_ARCH"] = "X86"
        self.assertIn("Unsupported Windows OS architecture", self.install("ok", ok=False))
        self.env["FIXTURE_ARCH"] = "X64"
        managed = self.write(".ubuntupro/.cloud-init/Ubuntu-26.04.user-data", "# managed\n")
        self.assertIn("Landscape user-data takes precedence", self.install("ok", ok=False))
        self.assertEqual(managed.read_bytes(), b"# managed\n")
        self.assertFalse((self.cwd / ".cloud-init").exists())
        self.assertEqual(self.calls(), [])

    def test_unsafe_names_rejected_before_native_calls(self):
        for name in ("a..b", "CON.example", "x.-y", "a/b"):
            with self.subTest(name=name):
                self.install("ok", name=name, ok=False)
        self.assertEqual(self.calls(), [])

    def test_vhd_confirmation_precedes_elevation(self):
        shutil.copy(WSL / "New-VHDX.ps1", self.cwd)
        self.write("confirm.ps1", r"""
$ErrorActionPreference = 'Stop'
function Start-Process { throw 'unexpected elevation' }
function New-VHD { throw 'unexpected creation' }
& ./New-VHDX.ps1 -Path ./fixture.vhdx -WhatIf
try {
    & ./New-VHDX.ps1 -Path ./fixture.vhdx -Confirm
    throw 'expected a confirmation prompt'
} catch {
    # Noninteractive hosts refuse the prompt: no elevation or VHD command may run first.
    if ($_.Exception.ToString() -notmatch 'NonInteractive') { throw }
}
""")
        self.run_fixture([PWSH, "-NoProfile", "-NonInteractive", "-File", "confirm.ps1"])
        self.assertFalse((self.cwd / "fixture.vhdx").exists())
