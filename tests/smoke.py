"""Offline chezmoi integration checks. Run with Python 3 and chezmoi on PATH."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
CHEZMOI = shutil.which("chezmoi")


def find_bash():
    if os.name != "nt":
        return shutil.which("bash")
    # System32\bash.exe launches WSL; these fixtures pass Git for Windows paths.
    git = shutil.which("git")
    roots = list(Path(git).resolve().parents[:3]) if git else []
    if "ProgramFiles" in os.environ:
        roots.append(Path(os.environ["ProgramFiles"]) / "Git")
    for root in roots:
        bash = root / "bin/bash.exe"
        if bash.is_file() and (root / "cmd/git.exe").is_file():
            return str(bash)
    return None


BASH = find_bash()
FLAGS = ("CODESPACES", "REMOTE_CONTAINERS", "REMOTE_CONTAINERS_IPC", "CI",
         "GITHUB_ACTIONS", "TF_BUILD", "DOTFILES_PROVISION", "DOTFILES_VSCODE_DIFF", "DOTFILES_PROFILE",
         "GIT_CONFIG_GLOBAL")


class Dotfiles(unittest.TestCase):
    def setUp(self):
        if not CHEZMOI:
            self.fail("Install chezmoi on PATH before running these tests")
        temp = tempfile.TemporaryDirectory(prefix="dotfiles smoke ")
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.source = ROOT
        self.facts = None
        self.config = self.tmp / "chezmoi.toml"
        self.env = {k: v for k, v in os.environ.items()
                    if k.upper() not in (*FLAGS, "PSMODULEPATH")}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home),
                        XDG_CONFIG_HOME=str(self.home / ".config"),
                        XDG_CACHE_HOME=str(self.tmp / "cache"),
                        XDG_DATA_HOME=str(self.tmp / "data"),
                        DOTFILES_PROFILE="personal",  # Never query the test runner's device state.
                        DOTFILES_WINDOWS_PROFILE="/mnt/c/Users/Windows Owner",
                        GIT_CONFIG_NOSYSTEM="1")

    def cmd(self, *args, data=None):
        result = subprocess.run(args, cwd=self.home, env=self.env, input=data,
                                capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result.stdout

    def cm(self, *args, data=None):
        overrides = ("--override-data", json.dumps(self.facts)) if self.facts else ()
        return self.cmd(CHEZMOI, "--source", self.source, "--destination", self.home,
                        "--config", self.config, "--cache", self.tmp / "cache",
                        "--persistent-state", self.tmp / "state", "--no-tty",
                        "--error-on-conflict", *overrides, *args, data=data)

    def init(self):
        self.cm("init", "--config-path", self.config)
        return json.loads(self.cm("execute-template", "{{ .machine | toJson }}"))

    def put(self, name, text):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
        return path

    @unittest.skipUnless(os.name == "nt", "Native Windows profile initialization")
    def test_windows_auto_feed_profile(self):
        self.source = self.tmp / "profile checkout"
        templates = self.source / ".chezmoitemplates"
        templates.mkdir(parents=True)
        self.cmd("git", "init", "--quiet", self.source)
        shutil.copyfile(ROOT / "home/.chezmoi.toml.tmpl", self.source / ".chezmoi.toml.tmpl")
        shutil.copyfile(ROOT / "home/.chezmoitemplates/is-ci.tmpl", templates / "is-ci.tmpl")
        # Substitute only the external utility. Run the real parser and config template.
        name = "windows-entra-joined.ps1"
        probe = (ROOT / "home/.chezmoitemplates" / name).read_text()
        system_tool = "Join-Path ([Environment]::SystemDirectory) 'dsregcmd.exe'"
        self.assertIn(system_tool, probe)
        (templates / name).write_text(probe.replace(system_tool, "$env:FIXTURE_DSREG"))
        stub = self.put("dsreg.ps1", r"""
if ($args[0] -ne '/status') { throw 'Unexpected dsregcmd operation' }
Add-Content -LiteralPath $env:FIXTURE_LOG -Value 'probe'
$env:FIXTURE_STATUS -split '\r?\n'
exit [int]$env:FIXTURE_EXIT
""")
        log = self.put("probes", "")
        self.env.update(FIXTURE_DSREG=str(stub), FIXTURE_LOG=str(log), FIXTURE_EXIT="0")
        del self.env["DOTFILES_PROFILE"]
        for report, code, expected in (
            (" AzureAdJoined : YES\r\n DomainJoined : NO", "0", "work"),
            (" AzureAdJoined : NO\r\n WorkplaceJoined : YES", "0", "personal"),
            (" AzureAdJoined : YES\r\n DomainJoined : YES", "0", "work"),
            (" DomainJoined : YES", "0", "personal"),
            (" AzureAdJoined : YES", "1", "personal"),
        ):
            with self.subTest(report=report, code=code):
                self.env.update(FIXTURE_STATUS=report, FIXTURE_EXIT=code)
                self.assertEqual(self.init()["profile"], expected)

        self.env.update(FIXTURE_STATUS="AzureAdJoined : YES", FIXTURE_EXIT="0")
        # An older config had no way to distinguish a manual choice from its default.
        self.config.write_text('[data.machine]\nprofile = "personal"\n', encoding="utf-8")
        self.assertEqual(self.init()["profile"], "personal")
        self.env["DOTFILES_PROFILE"] = "auto"
        self.assertEqual(self.init()["profile"], "work")
        self.env["DOTFILES_PROFILE"] = "personal"
        self.assertEqual(self.init()["profile"], "personal")
        del self.env["DOTFILES_PROFILE"]
        self.assertEqual(self.init()["profile"], "personal")
        self.env.update(DOTFILES_PROFILE="auto", CI="true")
        self.assertEqual(self.init()["profile"], "personal")
        del self.env["CI"]
        self.facts = {"chezmoi": {"os": "linux", "kernel": {"osrelease": "fixture-WSL2-microsoft"}}}
        config = self.cm("execute-template", "--init", "--file", self.source / ".chezmoi.toml.tmpl")
        self.assertEqual(tomllib.loads(config.decode())["data"]["machine"]["profile"], "personal")
        self.assertEqual(log.read_text().splitlines(), ["probe"] * 6)

    def test_ephemeral_preserves_host_settings(self):
        self.env["DOTFILES_PROFILE"] = "work"
        self.put("personal.age", "deliberately not an identity")
        untouched = {
            ".gitconfig": "[user]\n  name = Container User\n[commit]\n  gpgSign = false\n",
            ".ssh/config": "Host fixture\n  User existing\n",
            ".ssh/authorized_keys": "# existing access policy\n",
            ".npmrc": "registry=https://registry.npmjs.org/\n",
            ".config/pip/pip.conf": "[global]\ntimeout = 5\n",
            ".config/uv/uv.toml": "# local settings\n",
            ".yarnrc.yml": "nodeLinker: node-modules\n",
            ".bunfig.toml": "[install]\nexact = true\n",
            ".config/pnpm/config.yaml": "storeDir: fixture\n",
            ".config/pdm/config.toml": "[pypi]\nverify_ssl = true\n",
        }
        for name, text in untouched.items():
            self.put(name, text)
        host_settings = "[init]\r\n  defaultBranch = host\r\n"
        config = self.put(".config/git/config", "\ufeff" + host_settings)
        if os.name != "nt":
            config.chmod(0o600)
            config.parent.chmod(0o700)
        for flag, prop in (("CODESPACES", "codespace"), ("GITHUB_ACTIONS", "ci"),
                           ("CI", "ci"), ("TF_BUILD", "ci")):
            with self.subTest(flag=flag):
                self.env.update({flag: "true", "DOTFILES_PROVISION": "1"})
                machine = self.init()
                self.assertTrue(machine[prop] and machine["ephemeral"])
                self.assertFalse(machine["wsl"])
                self.cm("apply", "--exclude=scripts")
                self.cm("verify", "--exclude=scripts")
                del self.env[flag]
        content = config.read_bytes()
        self.assertTrue(content.startswith(b"\xef\xbb\xbf[include]"))
        self.assertTrue(content.endswith(host_settings.encode()))
        self.assertEqual(content.count(b"path = dotfiles.inc"), 1)
        for name, text in untouched.items():
            self.assertEqual((self.home / name).read_bytes(), text.encode(), name)
        if os.name != "nt":
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            self.assertEqual(config.parent.stat().st_mode & 0o777, 0o700)
            self.assertIn(". ~/.commonrc", (self.home / ".bashrc").read_text())
            self.assertFalse((self.home / "AppData").exists())
        self.assertEqual(self.cmd("git", "config", "fetch.prune").strip(), b"true")
        self.assertEqual(self.cmd("git", "config", "init.defaultBranch").strip(), b"host")
        self.assertEqual(self.cmd("git", "config", "user.name").strip(), b"Container User")
        self.assertFalse((self.home / ".gh_personal.gitconfig").exists())

    @unittest.skipUnless(BASH, "Requires OpenSSH in Bash (Git Bash on Windows)")
    def test_devcontainer_signs_through_forwarded_agent(self):
        self.env["REMOTE_CONTAINERS"] = "true"
        self.facts = {"machine": {"linux": True, "windows": False, "ephemeral": True,
                                  "dev_container": True, "wsl": False, "codespace": False, "ci": False}}
        self.init()
        self.put("personal.age", "not an identity")
        copied = ("\ufeff[user]\r\n  name = Fixture\r\n  email = fixture@example.invalid\r\n"
                  "[commit]\r\n  gpgSign = false\r\n[gpg \"ssh\"]\r\n  program = C:/host-only.exe\r\n")
        config = self.put(".gitconfig", copied)
        git_dir = self.home / ".config/git"
        git_dir.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            self.cm("apply", "--exclude=scripts", config, git_dir)
        self.assertTrue(config.read_bytes().startswith(copied.encode()))
        self.assertEqual(config.read_bytes().count(b"# dotfiles: managed Git settings"), 1)
        self.assertFalse((self.home / ".gh_personal.gitconfig").exists())
        self.assertEqual(self.cmd("git", "config", "user.name").strip(), b"Fixture")
        self.assertEqual(self.cmd("git", "config", "commit.gpgSign").strip(), b"true")
        self.put("exercise-signing.sh", r"""set -eu
git init -q repo
cd repo
ssh-keygen -q -t ed25519 -C fixture-first -N '' -f "$HOME/first"
ssh-add "$HOME/first"
rm "$HOME/first"
git config gpg.ssh.allowedSignersFile "$HOME/allowed"
printf 'fixture@example.invalid %s\n' "$(cat "$HOME/first.pub")" > "$HOME/allowed"
git commit -qm single --allow-empty
git verify-commit HEAD

ssh-keygen -q -t ed25519 -C fixture-work -N '' -f "$HOME/work"
ssh-add "$HOME/work"
rm "$HOME/work"
if git commit -qm ambiguous --allow-empty 2>"$HOME/error"; then exit 1; fi
grep -q 'Select the intended 1Password public key' "$HOME/error"
git config --file "$HOME/.config/git/host-identity.inc" user.signingkey "$(cat "$HOME/work.pub")"
printf 'fixture@example.invalid %s\n' "$(cat "$HOME/work.pub")" > "$HOME/allowed"
git commit -qm container-profile --allow-empty
git verify-commit HEAD
git config user.signingkey "$(cat "$HOME/first.pub")"
printf 'fixture@example.invalid %s\n' "$(cat "$HOME/first.pub")" > "$HOME/allowed"
git commit -qm repository-override --allow-empty
git verify-commit HEAD
if SSH_AUTH_SOCK="$HOME/no-socket" git commit -qm disconnected --allow-empty; then exit 1; fi
test "$(git rev-list --count HEAD)" = 3
""")
        self.cmd(BASH, "--noprofile", "--norc", "-c", """
set -eu
unset SSH_AUTH_SOCK SSH_AGENT_PID SSH_ASKPASS GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT
export HOME="$PWD" PATH="/usr/bin:/mingw64/bin:$PATH" SSH_ASKPASS_REQUIRE=never
# Git for Windows is native; keep its Git Bash agent socket in POSIX form.
export MSYS2_ENV_CONV_EXCL=SSH_AUTH_SOCK
exec ssh-agent -a "$HOME/agent.sock" sh "$HOME/exercise-signing.sh"
""")

    def test_workstation_scripts_do_not_require_opt_in_or_key(self):
        self.env["CI"] = "false"
        machine = self.init()
        self.assertFalse(machine["ci"])
        scripts = self.cm("managed", "--include=scripts").decode().splitlines()
        if machine["ephemeral"]:  # A real container stays a container with CI=false.
            return
        if os.name == "nt":
            expected = ("10_install-pwsh-modules", "20_os-configuration",
                        "30_machine-configuration", "36_upgrade-machine-pkgs", "40_user-configuration",
                        "45_user-pkgs", "46_upgrade-user-pkgs", "40_powershell-profile")
        else:
            expected = ("20_install-pkgs", "30_configure-pkgs")
        for name in expected:
            self.assertTrue(any(name in script for script in scripts), name)
        self.assertEqual(machine["wsl"], os.name != "nt" and (
            bool(self.env.get("WSL_DISTRO_NAME")) or "microsoft" in os.uname().release.lower()))

    def test_linux_detection_without_desktop_tools(self):
        # Exercise the init template, not just its consumers. A real container
        # marker always wins and cannot be masked by a kernel fixture.
        if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
            self.skipTest("Host filesystem is itself a container")
        self.env.pop("WSL_DISTRO_NAME", None)
        for kernel, user, wsl, ephemeral in [
                ("6.8.0-generic", "dev", False, False),
                ("6.8-microsoft-standard-WSL2", "dev", True, False),
                ("6.8-microsoft-standard-WSL2", "vscode", False, True)]:
            facts = {"chezmoi": {"os": "linux", "username": user, "kernel": {"osrelease": kernel}}}
            config = self.cm("--override-data", json.dumps(facts), "execute-template", "--init",
                             "--file", ROOT / "home/.chezmoi.toml.tmpl")
            self.config.write_bytes(config)
            machine = json.loads(self.cm("execute-template", "{{ .machine | toJson }}"))
            self.assertEqual((machine["wsl"], machine["ephemeral"]), (wsl, ephemeral))
            if wsl:
                self.assertEqual(machine["windows_profile"], self.env["DOTFILES_WINDOWS_PROFILE"])

    def private_fixture(self):
        self.source = self.tmp / "fixture checkout"
        shutil.copytree(ROOT / "home", self.source / "home", ignore=shutil.ignore_patterns("encrypted", "*.age"))
        (self.source / "home/encrypted").mkdir()
        shutil.copyfile(ROOT / ".chezmoiroot", self.source / ".chezmoiroot")
        self.cmd("git", "init", "--quiet", self.source)
        # Never fetch the user's real GitHub keys during offline checks.
        ignore = self.source / "home/.chezmoiignore"
        ignore.write_text(ignore.read_text() + "\n.ssh/authorized_keys\n")
        self.facts = {"machine": {"ephemeral": False, "wsl": False}}
        key = self.home / "personal.age"
        self.cm("age-keygen", "--output", key)
        self.init()
        if 'encryption = "age"' not in self.config.read_text():
            self.config.write_text(
                'encryption = "age"\nuseBuiltinAge = true\n' + self.config.read_text()
                + f'\n[age]\nidentity = {json.dumps(str(key))}\n')
        recipient = self.cm("age-keygen", "-y", key).decode().strip()
        for profile in ("gh_personal", "gh_microsoft", "azdo_microsoft"):
            fixture = (f"name: {profile}\nemail: test@example.invalid\nsigning_key: fixture\n"
                       "github_username: fixture\norganizations:\n"
                       "  - name: fixture-org\n    tenant_id: fixture-tenant\n")
            encrypted = self.cm("--age-recipient", recipient, "encrypt", data=fixture.encode())
            (self.source / "home/encrypted" / (profile + ".yaml.age")).write_bytes(encrypted)

    def test_private_profiles_with_throwaway_identity(self):
        self.private_fixture()
        self.cm("apply", "--exclude=scripts")
        self.cm("verify", "--exclude=scripts")
        self.assertEqual(self.cmd("git", "config", "user.name").strip(), b"gh_personal")
        self.assertEqual(self.cmd("git", "config", "commit.gpgSign").strip(), b"true")
        self.assertEqual(self.cmd("git", "config", "credential.azrepos:org/fixture-org.azureAuthority").strip(),
                         b"https://login.microsoftonline.com/fixture-tenant")
        self.assertFalse((self.home / ".npmrc").exists())
        self.assertIn("ForwardAgent yes", (self.home / ".ssh/config").read_text())
        work_repo = self.home / "gh_microsoft/example"
        self.cmd("git", "init", "--quiet", work_repo)
        self.assertEqual(self.cmd("git", "-C", work_repo, "config", "user.name").strip(), b"gh_microsoft")
        if os.name != "nt":
            self.assertEqual((self.home / ".gh_personal.gitconfig").stat().st_mode & 0o077, 0)

    def test_package_feeds_are_work_only(self):
        self.private_fixture()
        self.assertEqual(self.init()["profile"], "personal")
        npm = self.put(".npmrc", "@tools:registry=https://example.invalid/npm/\r\n")
        pip_path = ("AppData/Roaming/pip/pip.ini" if os.name == "nt" else
                    "Library/Application Support/pip/pip.conf" if sys.platform == "darwin" else ".config/pip/pip.conf")
        pip = self.put(pip_path, "[global]\r\ntimeout = 20\r\n[install]\r\nno-deps = true\r\n")
        uv = self.put("AppData/Roaming/uv/uv.toml" if os.name == "nt" else ".config/uv/uv.toml",
                      '[[index]]\r\nname = "tools"\r\nurl = "https://example.invalid/simple/"\r\nexplicit = true\r\n')
        original = {p: p.read_bytes() for p in (npm, pip, uv)}
        self.cm("apply", "--exclude=scripts", *original)
        self.assertEqual({p: p.read_bytes() for p in original}, original)

        self.env["DOTFILES_PROFILE"] = "work"
        self.assertEqual(self.init()["profile"], "work")
        del self.env["DOTFILES_PROFILE"]
        self.assertEqual(self.init()["profile"], "work")
        for _ in range(2):
            self.cm("apply", "--exclude=scripts", *original)
            for path, endpoint in ((npm, "npm"), (pip, "pypi/simple"), (uv, "pypi/simple")):
                self.assertEqual(path.read_text().count(f"https://packagefeedproxy.microsoft.io/{endpoint}/"), 1)

        # Older releases wrote the same endpoints without the trailing slash.
        npm.write_bytes(npm.read_bytes().replace(b"io/npm/", b"io/npm"))
        pip.write_bytes(pip.read_bytes().replace(b"io/pypi/simple/", b"io/pypi/simple"))
        self.env["DOTFILES_PROFILE"] = "personal"
        self.assertEqual(self.init()["profile"], "personal")
        self.cm("apply", "--exclude=scripts", *original)
        self.assertEqual({p: p.read_bytes() for p in original}, original)

    def test_native_feed_configs_round_trip(self):
        self.env.pop("XDG_CONFIG_HOME", None)
        node = "https://packagefeedproxy.microsoft.io/npm/"
        python = "https://packagefeedproxy.microsoft.io/pypi/simple/"
        for platform, pdm_dir, pnpm_dir, nuget_dirs in (
            ("windows", "AppData/Local/pdm/pdm", "AppData/Local/pnpm/config", ["AppData/Roaming/NuGet"]),
            ("linux", ".config/pdm", ".config/pnpm", [".nuget/NuGet", ".config/NuGet"]),
            ("darwin", "Library/Application Support/pdm", "Library/Preferences/pnpm",
             [".nuget/NuGet", ".config/NuGet"]),
        ):
            with self.subTest(platform=platform):
                self.facts = {"chezmoi": {"os": platform, "kernel": {"osrelease": "fixture"}},
                              "machine": {"ephemeral": False, "wsl": False}}
                self.env["DOTFILES_PROFILE"] = "work"
                self.init()
                bun = self.put(".bunfig.toml", "[install] # existing\r\nexact = true\r\n[run]\r\nbun = true\r\n")
                pdm = self.put(f"{pdm_dir}/config.toml", "[pypi] # existing\nverify_ssl = true\n[tool]\nx = 1\n")
                classic = self.put(".yarnrc", "disable-self-update-check true\n")
                berry = self.put(".yarnrc.yml", 'npmScopes:\n  tools:\n    npmRegistryServer: "https://example.invalid/"\n')
                rc = self.put(f"{pnpm_dir}/rc", "@tools:registry=https://example.invalid/\n")
                yaml = self.put(f"{pnpm_dir}/config.yaml", "storeDir: fixture\n")
                original = {p: p.read_bytes() for p in (bun, pdm, classic, berry, rc, yaml)}
                primary = [self.put(f"{root}/NuGet.Config", "<configuration><!-- private sources --></configuration>")
                           for root in nuget_dirs]
                ext = "Config" if platform == "windows" else "config"
                drops = [p.parent / "config" / f"99-dotfiles-work-feeds.{ext}" for p in primary]
                for p in drops:
                    p.parent.mkdir(exist_ok=True)
                targets = [*original, *drops]
                unix_env = self.home / ".config/dotfiles/corepack.sh"
                if platform != "windows":
                    unix_env.parent.mkdir(parents=True, exist_ok=True)
                    targets.append(unix_env)
                self.cm("apply", "--exclude=scripts", *targets)
                self.cm("verify", "--exclude=scripts", *targets)
                if platform != "windows" and BASH:
                    env_check = ('unset COREPACK_NPM_REGISTRY; . "$1"; echo "$COREPACK_NPM_REGISTRY"; '
                                 'COREPACK_NPM_REGISTRY=override; . "$1"; echo "$COREPACK_NPM_REGISTRY"')
                    self.assertEqual(self.cmd(BASH, "--noprofile", "--norc", "-c", env_check,
                                              "fixture", unix_env.as_posix()).decode().splitlines(),
                                     [node.rstrip("/"), "override"])
                self.assertEqual(tomllib.loads(bun.read_text())["install"], {"exact": True, "registry": node})
                self.assertEqual(tomllib.loads(pdm.read_text())["pypi"], {"verify_ssl": True, "url": python})
                for path, item in ((classic, f'registry "{node}"'), (berry, f'npmRegistryServer: "{node}"'),
                                   (rc, f"registry={node}"), (yaml, f'registry: "{node}"')):
                    self.assertIn(item, path.read_text().splitlines())
                for path in drops:
                    xml = ElementTree.parse(path)
                    self.assertEqual(xml.find("packageSources/add").get("value"),
                                     "https://packagefeedproxy.microsoft.io/nuget/v3/index.json")
                    self.assertEqual(xml.find("disabledPackageSources/add").attrib,
                                     {"key": "nuget.org", "value": "true"})
                    self.assertIsNone(xml.find(".//clear"))
                self.env["DOTFILES_PROFILE"] = "personal"
                self.init()
                self.cm("apply", "--exclude=scripts", *targets)
                self.assertEqual({p: p.read_bytes() for p in original}, original)
                self.assertFalse(any(p.exists() for p in drops))
                self.assertFalse(unix_env.exists())
                self.assertTrue(all(b"private sources" in p.read_bytes() for p in primary))

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell Corepack environment fixture")
    def test_corepack_respects_user_and_machine_overrides(self):
        self.init()
        for profile in ("work", "personal"):
            self.facts = {"machine": {"profile": profile, "ephemeral": False}}
            rendered = self.cm("execute-template", "--file", ROOT /
                               "home/.chezmoiscripts/windows/run_onchange_after_05_corepack-registry.ps1.tmpl")
            self.put(f"{profile}.ps1", rendered.decode().replace("[Environment]::", "[FixtureEnv]::"))
        driver = self.put("env-fixture.ps1", r"""
class FixtureEnv {
    static [string] $User
    static [string] $Machine
    static [string] GetEnvironmentVariable($n, $scope) {
        if ($n -ne 'COREPACK_NPM_REGISTRY') { throw 'Unexpected variable' }
        if ($scope -eq 'User') { return [FixtureEnv]::User }
        return [FixtureEnv]::Machine
    }
    static [void] SetEnvironmentVariable($n, $v, $scope) {
        if ($scope -ne 'User' -or $n -ne 'COREPACK_NPM_REGISTRY') { throw 'Unexpected write' }
        [FixtureEnv]::User = $v
    }
}
& ./work.ps1
if ([FixtureEnv]::User -ne 'https://packagefeedproxy.microsoft.io/npm') { throw 'Missing work default' }
& ./personal.ps1
if ([FixtureEnv]::User) { throw 'Work setting left on personal profile' }
[FixtureEnv]::User = 'user override'
& ./work.ps1; & ./personal.ps1
if ([FixtureEnv]::User -ne 'user override') { throw 'Lost user override' }
[FixtureEnv]::User = ''; [FixtureEnv]::Machine = 'machine override'
& ./work.ps1
if ([FixtureEnv]::User) { throw 'Shadowed machine selection' }
""")
        self.cmd("pwsh", "-NoProfile", "-NonInteractive", "-File", driver)

    def test_git_paths_and_signing_before_tools_are_installed(self):
        self.private_fixture()
        for platform, wsl, arch in (("windows", False, "amd64"), ("linux", True, "amd64"),
                                    ("linux", False, "amd64"), ("darwin", False, "arm64"),
                                    ("linux", True, "arm64")):
            with self.subTest(platform=platform, wsl=wsl, arch=arch):
                self.facts = {
                    "chezmoi": {"arch": arch},
                    "machine": {"windows": platform == "windows", "linux": platform == "linux",
                                "mac": platform == "darwin", "wsl": wsl, "ephemeral": False,
                                "windows_profile": self.env["DOTFILES_WINDOWS_PROFILE"]},
                    "username": "linux-owner",
                }
                config = self.home / ".gitconfig"
                git_dir = self.home / ".config/git"
                git_dir.mkdir(parents=True, exist_ok=True)
                # Simulate a workstation before installing 1Password, not the reviewer's Windows PATH.
                with patch.dict(self.env, PATH=str(self.tmp / "empty-bin")):
                    self.cm("apply", "--exclude=scripts", config, git_dir / "dotfiles-workstation.inc",
                            git_dir / "dotfiles-signing.inc")
                def value(key):
                    return self.cmd("git", "config", "--includes", "--file", config, key).decode().strip()
                self.assertEqual(value("commit.gpgSign"), "true")
                self.assertEqual(value("gpg.format"), "ssh")
                self.assertEqual(value("core.symlinks"), "true")
                self.assertEqual(value("core.ignoreCase"), "false")
                self.assertEqual(value("core.fileMode"), "true")
                self.assertEqual(value("filter.lfs.required"), "true")
                if platform == "windows" or wsl:
                    prefix = self.env["DOTFILES_WINDOWS_PROFILE"] if wsl else self.home.as_posix()
                    if wsl and arch == "arm64":
                        self.assertEqual(value("gpg.ssh.program"), (git_dir / "dotfiles-agent-sign").as_posix())
                    else:
                        signer = "op-ssh-sign-wsl.exe" if wsl else "op-ssh-sign.exe"
                        self.assertEqual(value("gpg.ssh.program"),
                                         prefix + "/AppData/Local/Microsoft/WindowsApps/" + signer)
                    self.assertIn("OpenSSH/ssh.exe", value("core.sshCommand"))
                elif platform == "darwin":
                    self.assertEqual(value("gpg.ssh.program"), "/Applications/1Password.app/Contents/MacOS/op-ssh-sign")
                else:
                    self.assertEqual(value("gpg.ssh.program"), "/opt/1Password/op-ssh-sign")
                if wsl:
                    self.assertEqual(value("core.excludesfile"), prefix + "/.gitignore")
                    paths = self.cmd("git", "config", "--includes", "--file", config, "--get-all",
                                     "includeif.gitdir/i:/mnt/x/gh_microsoft/.path").decode().splitlines()
                    self.assertEqual(paths, ["~/.gh_microsoft.gitconfig", prefix + "/.gh_microsoft.gitconfig"])
                    self.put(".gh_personal.gitconfig", "[user]\n email = personal@example.invalid\n")
                    self.put(".gh_microsoft.gitconfig", "[user]\n email = work@example.invalid\n")
                    checkout = self.home / "gh_microsoft/repo"
                    self.cmd("git", "init", "--quiet", checkout)
                    self.assertEqual(self.cmd("git", "-C", checkout, "config", "--includes", "--file",
                                              config, "user.email").strip(), b"work@example.invalid")

    def test_rendered_provisioning_commands_and_syntax(self):
        self.init()
        scripts = ROOT / "home/.chezmoiscripts"
        ps_files = []
        for template in sorted(scripts.rglob("*.tmpl")):
            self.facts = {"machine": {"wsl": True, "ephemeral": False}}
            rendered = self.cm("execute-template", "--file", template).decode()
            path = self.put(template.name.removesuffix(".tmpl"), rendered)
            if template.name.endswith(".ps1.tmpl"):
                ps_files.append(path)
            elif BASH:
                self.cmd(BASH, "-n", path)
        machine = (self.home / "run_once_after_35_machine-pkgs.ps1").read_text()
        user = (self.home / "run_once_after_45_user-pkgs.ps1").read_text()
        self.assertNotIn("upgrade --all", machine)
        self.assertNotIn("upgrade --all", user)
        for package in ("Microsoft.VisualStudioCode", "Microsoft.VisualStudioCode.Insiders"):
            self.assertIn(package, user)
        modules = (self.home / "run_once_after_10_install-pwsh-modules.ps1").read_text()
        self.assertIn("-Scope AllUsers", modules)
        self.assertNotIn("-SkipPublisherCheck", modules)
        self.facts["pkgs"] = {"windows": {"winget": {"machine": []}}}
        for number, scope in ((36, "machine"), (46, "user")):
            name = f"run_once_after_{number}_upgrade-{scope}-pkgs.ps1"
            original = (self.home / name).read_bytes()
            self.assertIn(b"winget upgrade --all", original)
            self.assertIn(f"--scope {scope}".encode(), original)
            # run_once hashes the rendered body. Package-list edits must not re-arm these hooks.
            self.assertEqual(self.cm("execute-template", "--file", scripts / "windows" / (name + ".tmpl")),
                             original)
        self.assertFalse(self.cm("execute-template", "--file",
                                 scripts / "windows/run_once_after_35_machine-pkgs.ps1.tmpl").strip())
        if shutil.which("pwsh"):
            parser = (
                "$ErrorActionPreference='Stop'; foreach($path in $args) { "
                "$tokens=$null; $errors=$null; "
                "$null=[System.Management.Automation.Language.Parser]::ParseFile("
                "$path,[ref]$tokens,[ref]$errors); "
                "if($errors.Count) { throw ($errors | Out-String) } }"
            )
            runner = self.put("parse.ps1", parser)
            ps_files.extend(ROOT.glob("home/dot_wsl/*.ps1"))
            ps_files.extend(ROOT.glob("home/dot_configurations/*.ps1"))
            self.cmd("pwsh", "-NoProfile", "-File", runner, *ps_files)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell WinGet configuration fixture")
    def test_os_configuration_reports_failing_stage(self):
        self.init()
        self.facts = {"machine": {"ephemeral": False, "profile": "personal"}}
        hook = self.put("os.ps1", self.cm(
            "execute-template", "--file",
            ROOT / "home/.chezmoiscripts/windows/run_once_after_20_os-configuration.ps1.tmpl"
        ).decode())
        manifest = self.put(".configurations/os.winget", self.cm(
            "execute-template", "--file", ROOT / "home/dot_configurations/os.winget.tmpl").decode())
        shutil.copyfile(ROOT / "home/dot_configurations/Set-WinGetConfiguration.ps1",
                        manifest.parent / "Set-WinGetConfiguration.ps1")
        resources = json.loads(self.cm("execute-template",
            '{{ includeTemplate "dot_configurations/os.winget.tmpl" . | fromYaml | toJson }}'))["properties"]["resources"]
        self.assertFalse(any(r["resource"].startswith("PSDscResources/") for r in resources))

        driver = self.put("fixture.ps1", """
Set-Variable -Scope Global HOME $PWD.Path -Force
function Start-Process { throw 'Unexpected PowerShell elevation' }
function winget {
    $stage = if ($args -contains '--enable') { 'enable' } elseif ($args -contains 'validate') { 'validation' } else { 'apply' }
    Write-Output "fixture:$stage"
    $global:LASTEXITCODE = if ($stage -eq $env:FAIL_STAGE) { [int]$env:NATIVE_EXIT } else { 0 }
}
try { & $args[0] } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
""")
        stages = ["enable", "validation", "apply"]
        for stage, code in (("enable", 7), ("validation", 1), ("apply", -2147024891),
                            ("apply", -2147023174), ("apply", -1978286075), ("none", 0)):
            with self.subTest(stage=stage):
                result = subprocess.run(
                    ["pwsh", "-NoProfile", "-NonInteractive", "-File", driver, hook], cwd=self.home,
                    env={**self.env, "FAIL_STAGE": stage, "NATIVE_EXIT": str(code)},
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, int(code != 0), result.stderr)
                self.assertEqual("winget configure list --history" in result.stderr,
                                 stage == "apply" and code == -1978286075)
                reached = [s.removeprefix("fixture:") for s in result.stdout.splitlines() if s.startswith("fixture:")]
                self.assertEqual(reached, stages[:stages.index(stage) + 1] if code else stages)
                if code:
                    self.assertIn(f"WinGet {stage} failed", result.stderr)
                    self.assertIn(f"{code} (0x{code & 0xffffffff:08X})", result.stderr)
                    self.assertIn("os.winget", result.stderr)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell DSC dispatch fixture")
    def test_native_windows_os_settings(self):
        self.init()
        self.facts = {"chezmoi": {"os": "windows"}, "machine": {"windows": True, "ephemeral": False}}
        names = ["os-settings.winget", "ssh-agent.winget"]
        hooks = [ROOT / "home/.chezmoiscripts/windows" / name for name in
                 ("run_onchange_after_31_os-settings.ps1.tmpl", "run_after_32_ssh-agent.ps1.tmpl")]
        helper = self.put(".configurations/Set-WinGetConfiguration.ps1", """
param($YamlConfigFilePath, [switch]$RequireStandardUser, [switch]$TestNativeDsc)
if (-not $RequireStandardUser -or -not $TestNativeDsc) { throw 'Missing DSC guards' }
(Get-Item -LiteralPath $YamlConfigFilePath).Name
""")
        targets = [helper.parent / name for name in names]
        self.cm("apply", "--exclude=scripts", *targets)
        docs = []
        for target in targets:
            self.assertEqual(target.read_bytes(), (ROOT / "home/dot_configurations" / target.name).read_bytes())
            doc = json.loads(self.cm("execute-template",
                '{{ include (joinPath .chezmoi.destDir ".configurations" "' + target.name + '") | fromYaml | toJson }}'))
            self.assertEqual(doc["metadata"]["winget"]["processor"]["identifier"], "dscv3")
            docs.append(doc["resources"])
        self.assertEqual(len(docs[0]), 7)
        values = {}
        for unit in docs[0]:
            self.assertEqual(unit["type"], "Microsoft.Windows/Registry")
            entry = unit["properties"]
            scope = "elevated" if entry["keyPath"].startswith("HKLM\\") else "current"
            self.assertEqual(unit.get("metadata", {}).get("winget", {}).get("securityContext", "current"), scope)
            values[entry["keyPath"] + "\\" + entry["valueName"]] = entry["valueData"]
        self.assertEqual(values, {
            r"HKCU\Console\%%Startup\DelegationConsole": {"String": "{2EACA947-7F5F-4CFA-BA87-8F7FBEEFBE69}"},
            r"HKCU\Console\%%Startup\DelegationTerminal": {"String": "{E12CFF52-A866-4C77-9A90-F570A7AA2C6B}"},
            r"HKCU\Software\Microsoft\Command Processor\AutoRun": {"String": r"%USERPROFILE%\autorun.cmd"},
            r"HKCU\Software\Canonical\Ubuntu\UbuntuInsightsConsent": {"DWord": 0},
            r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Sudo\Enabled": {"DWord": 3},
            r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI\DisableAIDataAnalysis": {"DWord": 1},
            r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI\AllowRecallEnablement": {"DWord": 0},
        })
        service, = docs[1]
        self.assertEqual(service["type"], "Microsoft.Windows/Service")
        self.assertEqual(service["metadata"]["winget"]["securityContext"], "elevated")
        self.assertEqual(service["properties"], {"name": "ssh-agent", "startType": "Disabled", "status": "Stopped"})

        script = self.put(hooks[0].stem, self.cm("execute-template", "--file", hooks[0]).decode())
        driver = self.put("dispatch.ps1", """
Set-Variable -Scope Global HOME $PWD.Path -Force
& $args[0]
""")
        calls = self.cmd("pwsh", "-NoProfile", "-NonInteractive", "-File", driver, script)
        self.assertEqual(calls.decode().splitlines(), names[:1])

        for ephemeral, ci in ((True, "false"), (False, "true")):
            self.facts["machine"]["ephemeral"] = ephemeral
            with patch.dict(self.env, TF_BUILD=ci):
                managed = self.cm("managed", "--include=files").decode()
                for name in names:
                    self.assertNotIn(name, managed)
                for hook in hooks:
                    self.assertFalse(self.cm("execute-template", "--file", hook).strip())

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell OpenSSH service fixture")
    def test_ssh_agent_repeated_updates(self):
        self.source = self.tmp / "service checkout"
        hook = ".chezmoiscripts/windows/run_after_32_ssh-agent.ps1.tmpl"
        probe = ".chezmoitemplates/windows-ssh-agent-state.ps1"
        for name in (hook, probe, ".chezmoitemplates/is-ci.tmpl", "dot_configurations/ssh-agent.winget"):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "home" / name, target)
        # Real chezmoi update, with only the SCM lookup, remote pull and DSC dispatcher replaced.
        fixture_probe = self.source / probe
        fixture_probe.write_text("""
function Get-CimInstance($ClassName, $Filter, $Property, $OperationTimeoutSec, $ErrorAction) {
    if ($ClassName -ne 'Win32_Service' -or $Filter -ne "Name='ssh-agent'") { throw 'Wrong service lookup' }
    if ($env:FIXTURE_AGENT -ne 'absent') {
        $mode, $state = $env:FIXTURE_AGENT.Split('/')
        [pscustomobject]@{StartMode=$mode; State=$state}
    }
}
""" + fixture_probe.read_text(), encoding="utf-8")
        self.config.write_text(f"""
[update]
command = {json.dumps(sys.executable)}
args = ["-c", "print('Already up to date.')"]
[interpreters.ps1]
command = "pwsh"
args = ["-NoProfile", "-NonInteractive", "-File"]
""", encoding="utf-8")
        self.facts = {"machine": {"windows": True, "ephemeral": False}}
        log = self.put("dispatch.log", "")
        self.env["FIXTURE_LOG"] = str(log)
        self.put(".configurations/Set-WinGetConfiguration.ps1", """
param($YamlConfigFilePath, [switch]$RequireStandardUser, [switch]$TestNativeDsc)
if (!$RequireStandardUser -or !$TestNativeDsc) { throw 'Missing DSC guards' }
Add-Content -LiteralPath $env:FIXTURE_LOG -Value (Get-Item -LiteralPath $YamlConfigFilePath).Name
""")
        for state, run in (("absent", False), ("Manual/Stopped", True), ("Disabled/Stopped", False),
                           ("Disabled/Stopped", False), ("Disabled/Running", True)):
            with self.subTest(state=state):
                self.env["FIXTURE_AGENT"] = state
                log.write_bytes(b"")
                output = self.cm("update", "--verbose")
                self.assertEqual(b"32_ssh-agent.ps1" in output, run)
                self.assertEqual(log.read_text().splitlines(), ["ssh-agent.winget"] if run else [])

    @unittest.skipUnless(shutil.which("pwsh"), "Native DSC preflight fixture")
    def test_native_dsc_preflight(self):
        helper = (ROOT / "home/dot_configurations/Set-WinGetConfiguration.ps1").read_text()
        role = ("([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent())"
                ".IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)")
        alias = ("Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) "
                 r"'Microsoft\WindowsApps\Microsoft.DesiredStateConfiguration_8wekyb3d8bbwe\dsc.exe'")
        self.assertIn(alias, helper)
        self.assertIn(role, helper)
        script = self.put("apply.ps1", helper.replace(alias, "$env:FIXTURE_DSC").replace(role, "$false"))
        dsc = self.put("fixture dsc.ps1", """
if ($args -join ' ' -eq '--version') { "dsc $env:FIXTURE_VERSION"; exit 0 }
if ($args -join ' ' -ne 'config test --file native settings.winget --output-format json') { throw "Unexpected DSC call: $args" }
$env:FIXTURE_RESULT
exit ([int]$env:FIXTURE_TEST)
""")
        driver = self.put("test-native.ps1", """
$ErrorActionPreference = 'Stop'
function Get-PSRepository { throw 'Native resources do not use a PowerShell gallery' }
function winget {
    if ($args -contains 'validate') { throw 'Unexpected v2 catalog validation' }
    if ($args -notcontains '--enable') {
        if ($args[2] -ne 'native settings.winget') { throw 'Wrong manifest' }
        'fixture:apply'
    }
    $global:LASTEXITCODE = 0
}
try { & $args[0] -YamlConfigFilePath 'native settings.winget' -TestNativeDsc -RequireStandardUser }
catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
""")
        for version, code, states, error in (("3.2.3", "0", [True, False], ""), ("3.3.0", "0", [True], ""),
                                             ("3.1.0", "0", [], "requires stable DSC"),
                                             ("3.3.0", "2", [], "DSC preflight failed"),
                                             ("3.3.0", "0", [], "No successful DSC test results")):
            with self.subTest(version=version, code=code, states=states):
                report = {"hadErrors": False, "results": [{"result": {"inDesiredState": state}} for state in states]}
                result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", driver, script],
                                        cwd=self.home, env={**self.env, "FIXTURE_DSC": str(dsc),
                                                            "FIXTURE_VERSION": version, "FIXTURE_TEST": code,
                                                            "FIXTURE_RESULT": json.dumps(report)},
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, int(bool(error)), result.stderr)
                self.assertEqual("fixture:apply" in result.stdout, not error and not all(states))
                if error:
                    self.assertIn(error, result.stderr)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell WinGet private catalog fixture")
    def test_private_winget_catalog_validation(self):
        self.init()
        hooks = {}
        for profile in ("personal", "work"):
            self.facts = {"machine": {"ephemeral": False, "profile": profile}}
            for name, phase in (("os", "20_os"), ("machine-pkgs", "30_machine"), ("user-pkgs", "40_user")):
                config = f"dot_configurations/{name}.winget.tmpl"
                baseline = f"winget/{name}.winget"
                manifest = json.loads(self.cm("execute-template",
                                             '{{ includeTemplate "' + config + '" . | fromYaml | toJson }}'))
                raw = json.loads(self.cm("execute-template",
                                        '{{ includeTemplate "' + baseline + '" . | fromYaml | toJson }}'))
                if profile == "work":
                    for unit in manifest["properties"]["resources"]:
                        self.assertEqual(unit["directives"].pop("repository"), "azure-powershell")
                self.assertEqual(manifest, raw)  # No changed settings or resources.
                hook = self.cm("execute-template", "--file", ROOT /
                               f"home/.chezmoiscripts/windows/run_once_after_{phase}-configuration.ps1.tmpl").decode()
                self.assertEqual(" -WorkCatalogUri" in hook, profile == "work")
                self.assertEqual(" -RequireStandardUser" in hook, name != "os")
                if name != "os":
                    for unit in manifest["properties"]["resources"]:
                        self.assertEqual(unit["directives"].get("securityContext", "current"), "current", unit["id"])
                if name == "os":
                    hooks[profile] = self.put(f"os-{profile}.ps1", hook)
                    os_units = raw["properties"]["resources"]
        cfg = self.put(".configurations/os.winget", "# fixture\n")
        shutil.copyfile(ROOT / "home/dot_configurations/Set-WinGetConfiguration.ps1",
                        cfg.parent / "Set-WinGetConfiguration.ps1")
        self.put("winget-fixture.py", """
import os, sys
from pathlib import Path
if 'validate' in sys.argv:
    sys.stdout.buffer.write(Path('messages').read_bytes())
    sys.exit(int(os.environ['VALIDATE_CODE']))
if '--enable' not in sys.argv:
    Path('applied').touch()
    sys.exit(int(os.environ['APPLY_CODE']))
""")
        driver = self.put("run-winget.ps1", """
Set-Variable -Scope Global HOME $PWD.Path -Force
function Start-Process { throw 'Unexpected elevation' }
function Get-PSRepository($Name) {
    if ($Name -ne 'azure-powershell') { throw 'Unexpected repository lookup' }
    [pscustomobject]@{ InstallationPolicy = 'Trusted'; SourceLocation = $env:FIXTURE_SOURCE }
}
function winget { & $env:FIXTURE_PYTHON ./winget-fixture.py @args; $global:LASTEXITCODE = $LASTEXITCODE }
try { & $args[0] } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
""")
        notice = ("  The configuration unit is not available publicly; "
                  "ensure that anyone who will use this configuration has access to it.\n")
        transcript = ""
        for unit in os_units:
            header = unit["resource"].rsplit("/", 1)[-1]
            if unit["directives"].get("securityContext") == "elevated":
                header += "\U0001f6e1 "
            if "id" in unit:
                header += f" [{unit['id']}]"
            transcript += header + "\n" + notice
        applied = self.home / "applied"
        for profile, output, code, apply_code, should_apply in (
            ("work", transcript, 1, 0, True),
            ("work", transcript, 1, 1, True),  # A later apply failure is still fatal.
            ("work", transcript + "Service\n  The configuration unit was not found.\n", 1, 0, False),
            ("work", transcript + "Service\n", 1, 0, False),
            ("work", "", 1, 0, False),
            ("work", transcript, 2, 0, False),
            ("personal", transcript, 1, 0, False),
            ("wrong-repository", transcript, 1, 0, False),
        ):
            with self.subTest(profile=profile, output=output, code=code, apply_code=apply_code):
                self.put("messages", output)
                applied.unlink(missing_ok=True)
                mismatch = profile == "wrong-repository"
                source = "https://wrong.example.invalid/" if mismatch else "https://packagefeedproxy.microsoft.io/powershell/v2/"
                result = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", driver,
                                         hooks["work" if mismatch else profile]],
                                        cwd=self.home, env={**self.env, "FIXTURE_PYTHON": sys.executable,
                                                            "FIXTURE_SOURCE": source,
                                                            "VALIDATE_CODE": str(code), "APPLY_CODE": str(apply_code)},
                                        capture_output=True, timeout=30)
                self.assertEqual(applied.exists(), should_apply, result.stderr)
                self.assertEqual(result.returncode, int(not should_apply or apply_code != 0), result.stderr)
                if mismatch:
                    self.assertIn(b"requires the trusted azure-powershell repository", result.stderr)
                elif output:
                    self.assertIn(b"The configuration unit is not available publicly", result.stdout)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell uv setup fixture")
    def test_windows_user_python_path(self):
        self.init()
        self.facts = {"machine": {"ephemeral": False, "profile": "personal"}}
        hook = self.put("user.ps1", self.cm("execute-template", "--file", ROOT /
                        "home/.chezmoiscripts/windows/run_once_after_40_user-configuration.ps1.tmpl").decode())
        self.put(".configurations/Set-WinGetConfiguration.ps1", """
param($YamlConfigFilePath, [switch]$ValidateFirst, [switch]$RequireStandardUser)
if (!$RequireStandardUser) { throw 'Expected non-elevated user setup' }
Add-Content calls 'user packages'
""")
        uv = self.put("fixture uv.ps1", """
Add-Content calls ($args -join ' ')
if ($args[1] -eq $env:FAIL_STEP) { exit 7 }
exit 0
""")
        driver = self.put("run-user.ps1", """
Set-Variable -Scope Global HOME $PWD.Path -Force
function Get-Command($Name, $CommandType) {
    if ($Name -ne 'uv' -or $CommandType -ne 'Application') { throw 'Unexpected command lookup' }
    [pscustomobject]@{Source = $env:FIXTURE_UV}
}
try { & $args[0] } catch {
    if ($env:FAIL_STEP -and $_.Exception.Message -eq "uv python $env:FAIL_STEP failed: 7") { exit 0 }
    throw
}
if ($env:FAIL_STEP) { throw 'Ignored uv failure' }
""")
        for fail in ("", "install", "update-shell"):
            with self.subTest(fail=fail):
                calls = self.put("calls", "")
                self.env.update(FIXTURE_UV=str(uv), FAIL_STEP=fail)
                self.cmd("pwsh", "-NoProfile", "-NonInteractive", "-File", driver, hook)
                self.assertEqual(calls.read_text().splitlines(), [
                    "user packages", "python install --default 3.14 --preview-features python-install-default",
                ] + ([] if fail == "install" else ["python update-shell"]))

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell WinGet package guard")
    def test_elevated_package_hook_stops_before_discovery(self):
        self.init()
        self.facts = {"machine": {"ephemeral": False, "profile": "work"}}
        helper = (ROOT / "home/dot_configurations/Set-WinGetConfiguration.ps1").read_text()
        role = ("([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent())"
                ".IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)")
        self.assertIn(role, helper)
        self.put(".configurations/Set-WinGetConfiguration.ps1", helper.replace(role, "$true"))
        runner = self.put("run.ps1", """
Set-Variable -Scope Global HOME $PWD.Path -Force
function Start-Process { throw 'Unexpected elevation' }
function Get-PSRepository { throw 'Unexpected catalog lookup' }
function winget { throw 'Unexpected WinGet call' }
function uv { throw 'Unexpected runtime install' }
try { & $args[0] } catch {
    if ($_.Exception.Message -like 'This WinGet configuration requires a non-elevated session*') { exit 0 }
    throw
}
throw 'Expected elevated package discovery to stop'
""")
        for phase in ("30_machine", "40_user"):
            with self.subTest(phase=phase):
                hook = self.put("hook.ps1", self.cm("execute-template", "--file", ROOT /
                                f"home/.chezmoiscripts/windows/run_once_after_{phase}-configuration.ps1.tmpl").decode())
                self.cmd("pwsh", "-NoProfile", "-NonInteractive", "-File", runner, hook)

    @unittest.skipUnless(os.name == "nt", "Windows machine package bootstrap")
    def test_podman_machine_scope_and_user_install(self):
        self.init()
        self.facts = {"machine": {"windows": True, "ephemeral": False}}
        template = ROOT / "home/.chezmoiscripts/windows/run_once_after_29_podman.ps1.tmpl"
        body = self.cm("execute-template", "--file", template).decode()
        # Redirect only installation discovery; never inspect or repair real packages.
        for lookup, source in (("[Environment]::GetFolderPath('ProgramFiles')", "$env:FIXTURE_PROGRAMFILES"),
                               ("Get-PodmanInstallDir LocalMachine", "$env:FIXTURE_HKLM"),
                               ("Get-PodmanInstallDir CurrentUser", "$env:FIXTURE_HKCU")):
            self.assertIn(lookup, body)
            body = body.replace(lookup, source)
        hook = self.put("install.ps1", body)
        user = self.put("user/Programs/Podman/podman.exe", "")
        machine = self.home / "machine/Podman/podman.exe"
        machine.parent.mkdir(parents=True)
        custom = self.home / "custom location/podman.exe"
        custom.parent.mkdir()
        self.env.update(LOCALAPPDATA=str(self.home / "user"), FIXTURE_PROGRAMFILES=str(self.home / "machine"),
                        FIXTURE_HKCU="", FIXTURE_HKLM="")
        driver = self.put("install-test.ps1", """
$env:Path = $PWD.Path
function winget {
    $verb = $args[0]
    if ($verb -notin 'install','repair' -or $args -notcontains 'Podman.CLI' -or $args -notcontains '--exact' -or
        ($args -contains '--no-upgrade') -ne ($verb -eq 'install') -or
        ($args -contains 'ALLUSERS=1') -ne ($verb -eq 'install') -or $args -contains '--force') { throw "Wrong call: $args" }
    Add-Content calls $verb
    $code = if ($verb -eq 'install') { [int]$env:INSTALL_EXIT } else { [int]$env:REPAIR_EXIT }
    if ($code -eq 0 -and $env:CREATE_EXE) { [IO.File]::WriteAllText($env:CREATE_EXE, '') }
    $global:LASTEXITCODE = $code
}
try { & $args[0] } catch {
    if ($env:EXPECTED_ERROR -and $_.Exception.Message.Contains($env:EXPECTED_ERROR)) { exit 0 }
    throw
}
if ($env:EXPECTED_ERROR) { throw 'Missing expected install or repair failure' }
""")
        def check(calls, *, install=0, repair=0, create=None, error=""):
            self.env.update(INSTALL_EXIT=str(install), REPAIR_EXIT=str(repair),
                            CREATE_EXE=str(create) if create else "", EXPECTED_ERROR=error)
            log = self.put("calls", "")
            self.cmd("pwsh", "-NoProfile", "-NonInteractive", "-File", driver, hook)
            self.assertEqual(log.read_text().splitlines(), calls)

        check([])  # Do not duplicate a per-user install.
        user.unlink()
        check(["install"], create=machine)
        check([])
        machine.unlink()
        for hive in ("FIXTURE_HKCU", "FIXTURE_HKLM"):
            with self.subTest(hive=hive):
                self.env[hive] = str(custom.parent)
                custom.touch()
                check([])  # A custom MSI install is usable even with a stale PATH.
                custom.unlink()
                self.env[hive] = ""

        self.env["FIXTURE_HKCU"] = str(custom.parent)
        current = -1978335135  # --no-upgrade finds an existing registration.
        check(["install", "repair"], install=-1978335189, create=custom)
        check([])
        custom.unlink()
        check(["install", "repair"], install=current, error="after WinGet repair (exit 0)")
        check(["install", "repair"], install=current, repair=7, error="after WinGet repair (exit 7)")
        check(["install"], create=user, error="machine MSI InstallDir")  # Not success for a fresh all-users install.

    @unittest.skipUnless(os.name == "nt", "Windows machine package bootstrap")
    def test_machine_node_default_and_podman_cli(self):
        self.init()
        hook = self.cm("execute-template", "--file", ROOT /
                       "home/.chezmoiscripts/windows/run_once_after_35_machine-pkgs.ps1.tmpl").decode()
        # Run the rendered package body, not the UAC handoff. No real registry or installer calls.
        body = hook[hook.index("$machinePackages = @("):]
        for original, fixture in (("[Environment]::GetFolderPath('ProgramFiles')", "$PWD.Path"),
                                  (r"WinGet\Links\fnm.exe", r"WinGet\Links\fnm.ps1")):
            self.assertIn(original, body)
            body = body.replace(original, fixture)
        self.put("machine.ps1", body)
        self.put("fnm/aliases/default/node.exe", "")
        self.put("WinGet/Links/fnm.ps1", """
if ($env:FNM_DIR -ne (Join-Path $PWD 'fnm')) { throw 'Wrong version store' }
Add-Content calls "fnm $args"
if ($env:FAIL_INSTALL -and $args[0] -eq 'install') { exit 7 }
exit 0
""")
        driver = self.put("run.ps1", r"""
$ErrorActionPreference = 'Stop'
function winget { Add-Content calls "winget $args"; $global:LASTEXITCODE = 0 }
function Get-Item($LiteralPath) {
    $key = [pscustomobject]@{ PSPath = 'fixture' }
    $key | Add-Member ScriptMethod GetValue {
        return '%SystemRoot%\System32'
    }
    $key | Add-Member ScriptMethod GetValueKind { 'ExpandString' }
    $key
}
function New-ItemProperty($LiteralPath, $Name, $Value, $PropertyType, [switch]$Force) {
    if ($LiteralPath -ne 'fixture' -or $PropertyType -ne 'ExpandString') { throw 'Invalid PATH write' }
    Add-Content calls "publish $Value"
}
try { & .\machine.ps1 } catch {
    if ($env:FAIL_INSTALL -and $_.Exception.Message -like '*--lts failed: 7') { exit 0 }
    throw
}
if ($env:FAIL_INSTALL) { throw 'Ignored failed install' }
""")
        for fail in (False, True):
            with self.subTest(fail=fail):
                log = self.put("calls", "")
                self.env["FAIL_INSTALL"] = "1" if fail else ""
                self.cmd("powershell.exe", "-NoProfile", "-NonInteractive", "-File", driver)
                calls = log.read_text().splitlines()
                installs = [line.split()[3] for line in calls if line.startswith("winget install --id ")]
                self.assertEqual(installs, ["Schniz.fnm"])
                self.assertIn("--scope machine", calls[0])
                node = [line for line in calls if line.startswith("fnm ")]
                self.assertEqual(node, ["fnm install --lts"] + ([] if fail else ["fnm default lts-latest"]))
                published = [line for line in calls if line.startswith("publish ")]
                self.assertEqual(published, [] if fail else
                                 [rf"publish {self.home}\fnm\aliases\default;%SystemRoot%\System32"])

    def test_platform_script_selection(self):
        for platform, wsl, ephemeral in (("windows", False, False), ("linux", False, False),
                                          ("linux", True, False), ("linux", False, True)):
            with self.subTest(platform=platform, wsl=wsl, ephemeral=ephemeral):
                self.facts = {
                    "chezmoi": {"os": platform, "kernel": {"osrelease": "fixture"}},
                    "machine": {"windows": platform == "windows", "linux": platform == "linux",
                                "wsl": wsl, "ephemeral": ephemeral},
                }
                self.init()
                managed = self.cm("managed", "--include=scripts").decode()
                if platform == "windows":
                    self.assertIn("20_os-configuration", managed)
                    self.assertIn("36_upgrade-machine-pkgs", managed)
                    self.assertIn("46_upgrade-user-pkgs", managed)
                    self.assertNotIn("20_install-pkgs", managed)
                else:
                    self.assertIn("20_install-pkgs", managed)
                    self.assertIn("30_configure-pkgs", managed)
                    self.assertNotIn("20_os-configuration", managed)

    @unittest.skipUnless(BASH, "Bash is required for installer command fixtures")
    def test_unix_podman_system_compatibility(self):
        self.init()
        template = ROOT / "home/.chezmoiscripts/run_after_50_podman-compat.sh.tmpl"
        self.facts = {"machine": {"linux": True, "mac": False, "ephemeral": True}}
        self.assertFalse(self.cm("execute-template", "--file", template).strip())
        self.facts["machine"]["ephemeral"] = False
        with patch.dict(self.env, CI="true"):
            self.assertFalse(self.cm("execute-template", "--file", template).strip())
        hook = self.put("podman-compat.sh", self.cm("execute-template", "--file", template).decode())
        driver = '''
command() {
  case "$2" in
    podman) [ -n "$FIXTURE_PODMAN" ] && echo "$FIXTURE_PODMAN" ;;
    docker) [ "$FIXTURE_DOCKER" = yes ] ;;
    apt-get) return 0 ;;
    *) return 1 ;;
  esac
}
sudo() { echo "sudo $*"; }
ln() { echo "ln $*"; }
source "$1"
'''
        for podman, docker, install in (("", "no", False), ("/usr/bin/podman", "no", True),
                                        ("/usr/bin/podman", "yes", False), ("/home/me/bin/podman", "no", False)):
            self.env.update(FIXTURE_PODMAN=podman, FIXTURE_DOCKER=docker)
            lines = self.cmd(BASH, "--norc", "--noprofile", "-c", driver, "fixture", hook.as_posix())
            self.assertEqual(lines.decode().splitlines(), ["sudo apt-get install --yes --no-remove --no-install-recommends podman-docker"]
                             if install else [])

    @unittest.skipUnless(BASH, "Bash is required for installer command fixtures")
    def test_linux_installs_and_font_setup_with_fake_commands(self):
        self.init()
        driver = r'''
installed=0
command() {
  if [ "$1" = -v ]; then
    case "$2" in
      task|aliae) return 1 ;;
      oh-my-posh) [ "$installed" = 1 ]; return ;;
      socat) return 1 ;;
      apt-get) return 0 ;;
    esac
  fi
  builtin command "$@"
}
curl() {
  [ -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ] || return 77
  case "$*" in
    *taskfile.dev*) tool=task ;;
    *ohmyposh.dev*) tool=oh-my-posh ;;
    *aliae.dev*) tool=aliae ;;
    *) return 78 ;;
  esac
  printf 'printf "%%s\\n" "%s $*" >> "$DOTFILES_INSTALL_LOG"\n' "$tool"
}
sudo() { printf 'sudo %s\n' "$*" >> "$DOTFILES_INSTALL_LOG"; }
source "$1"
installed=1
oh-my-posh() { printf 'oh-my-posh %s\n' "$*" >> "$DOTFILES_INSTALL_LOG"; }
source "$2"
'''
        for wsl in (False, True):
            with self.subTest(wsl=wsl):
                self.facts = {"machine": {"wsl": wsl}}
                paths = []
                for name in ("20_install-pkgs", "30_configure-pkgs"):
                    paths.append(self.put(name + ".sh", self.cm(
                        "execute-template", "--file",
                        ROOT / f"home/.chezmoiscripts/linux/run_once_after_{name}.sh.tmpl"
                    ).decode()))
                log = self.put("install.log", "")
                self.env.update(DOTFILES_INSTALL_LOG=log.as_posix(),
                                GH_TOKEN="fixture-only", GITHUB_TOKEN="fixture-only")
                self.cmd(BASH, "--noprofile", "--norc", "-c", driver, "fixture",
                         *(path.as_posix() for path in paths))
                lines = log.read_text().splitlines()
                for tool, option in (("task", "-b "), ("oh-my-posh", "-d "), ("aliae", "-d ")):
                    self.assertTrue(any(line.startswith(tool + " ") and option in line
                                        for line in lines), tool)
                self.assertIn("oh-my-posh font install meslo", lines)
                self.assertEqual("sudo apt-get install --yes socat" in lines, wsl)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell profile deployment")
    def test_powershell_profiles_update_in_disposable_home(self):
        self.init()
        shared = self.put(".config/powershell/Microsoft.PowerShell_profile.ps1", "# shared\n")
        vscode = shared.with_name("Microsoft.VSCode_profile.ps1")
        self.cm("apply", "--exclude=scripts", vscode)
        seed = vscode.read_bytes()
        custom = self.put(f"Documents/PowerShell/{vscode.name}", "# my VS Code profile\n")
        custom_content = custom.read_bytes()
        editions = ("PowerShell", "WindowsPowerShell")
        for edition in editions:
            self.put(f"Documents/{edition}/{shared.name}", "# previous managed profile\n")
        rendered = self.cm(
            "execute-template", "--file",
            ROOT / "home/.chezmoiscripts/windows/run_onchange_after_40_powershell-profile.ps1.tmpl"
        ).decode()
        # Replace only the OS known-folder lookups. Never copy to real Documents.
        for folder in ("UserProfile", "MyDocuments"):
            lookup = f"[Environment]::GetFolderPath('{folder}')"
            self.assertIn(lookup, rendered)
            rendered = rendered.replace(lookup, f"$env:FIXTURE_{folder}")
        path = self.put("profiles.ps1", rendered)
        redirected = self.tmp / "redirected"
        commercial = self.tmp / "commercial"
        self.env.update(FIXTURE_MyDocuments=str(redirected), OneDriveCommercial=str(commercial),
                        FIXTURE_UserProfile=str(self.tmp / "different user"))
        self.cmd("powershell.exe", "-NoProfile", "-File", path)
        self.assertFalse(redirected.exists() or commercial.exists())
        self.env["FIXTURE_UserProfile"] = str(self.home)
        for text in ("# shared\n", "# updated\n"):
            shared.write_bytes(text.encode())
            self.cmd("powershell.exe", "-NoProfile", "-File", path)
            for documents in (self.home / "Documents", redirected, commercial / "Documents"):
                for edition in editions:
                    self.assertEqual((documents / edition / shared.name).read_bytes(), shared.read_bytes())
                    dest = documents / edition / vscode.name
                    self.assertEqual(dest.read_bytes(), custom_content if dest == custom else seed)

    @unittest.skipUnless(os.name == "nt" and shutil.which("pwsh"), "Windows PowerShell profile startup")
    def test_powershell_profile_recovers_stale_path(self):
        self.init()
        profiles = self.home / ".config/powershell"
        profiles.parent.mkdir(exist_ok=True)
        self.cm("apply", "--exclude=scripts", profiles)
        console = profiles / "Microsoft.PowerShell_profile.ps1"
        # Substitute the registry read; never change HKCU or run tools from the workstation's PATH.
        lookup = "[Environment]::GetEnvironmentVariable('Path', 'User')"
        rendered = console.read_text(encoding="utf-8-sig")
        self.assertIn(lookup, rendered)
        console.write_text(rendered.replace(lookup, "$env:FIXTURE_USER_PATH"), encoding="utf-8")
        tools = self.put("user tools/oh-my-posh.cmd", """@echo off
if not "%~1"=="init" exit /b 1
if not "%~4"=="%FIXTURE_THEME%" exit /b 1
echo function global:prompt { 'fixture prompt' }
""").parent
        process_bin = str(self.home / "VS Code bin")
        self.env.update(FIXTURE_PROCESS_BIN=process_bin, FIXTURE_TOOLS=str(tools),
                        FIXTURE_USER_PATH=f"{process_bin.upper()};;%FIXTURE_TOOLS%;%FIXTURE_TOOLS%")
        driver = self.put("startup.ps1", """
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$env:PSModulePath = Join-Path $PSHOME 'Modules'
$env:Path = $env:FIXTURE_PROCESS_BIN
$imports = @()
function Get-Module($Name, [switch]$ListAvailable) { $Name }
function Import-Module($Name) { $script:imports += $Name }
. $args[0]
if ($env:Path -cne "$env:FIXTURE_PROCESS_BIN;$env:FIXTURE_TOOLS") { throw 'Changed PATH precedence or duplicates' }
if ((prompt) -ne 'fixture prompt') { throw 'Oh My Posh did not initialize with the expected theme' }
$expectWinGet = $env:FIXTURE_WINGET -eq '1' -and $PSVersionTable.PSVersion -ge [version]'7.4'
if (('Microsoft.WinGet.CommandNotFound' -in $imports) -ne $expectWinGet) { throw 'Wrong WinGet import' }
if ('Terminal-Icons' -notin $imports -or 'PSReadLine' -notin $imports) { throw 'Skipped independent modules' }
if ($env:FIXTURE_PODMAN -eq '1') {
    if ((docker run 'two words') -ne 'run|two words' -or $LASTEXITCODE -ne 17) { throw 'Wrong docker command' }
    if ((docker-compose 'two words') -ne 'compose|two words' -or $LASTEXITCODE -ne 17) { throw 'Wrong compose command' }
} elseif ((Test-Path Alias:docker) -or (Test-Path Function:docker-compose)) { throw 'Unexpected Docker mappings' }
""")
        theme = self.put(".oh-my-posh.json", "{}")
        self.env.update(FIXTURE_THEME=str(theme), FIXTURE_WINGET="0")
        self.cmd("pwsh", "-NoProfile", "-NonInteractive", "-File", driver, profiles / "Microsoft.VSCode_profile.ps1")
        theme.unlink()
        (tools / "winget.exe").touch()  # Used for application discovery only.
        (tools / "podman.cmd").write_text('@echo off\necho %~1^|%~2\nexit /b 17\n')
        self.env.update(FIXTURE_THEME="", FIXTURE_WINGET="1", FIXTURE_PODMAN="1")
        for shell in ("pwsh", "powershell.exe"):
            with self.subTest(shell=shell):
                self.cmd(shell, "-NoProfile", "-NonInteractive", "-File", driver, console)

    @unittest.skipUnless(os.name == "nt", "Windows module bootstrap")
    def test_inbox_module_manager_fails_before_elevation(self):
        self.init()
        hook = self.put("modules.ps1", self.cm(
            "execute-template", "--file",
            ROOT / "home/.chezmoiscripts/windows/run_once_after_10_install-pwsh-modules.ps1.tmpl"
        ).decode())
        driver = self.put("preflight.ps1", """
function Get-Module { }
function Get-Command { [pscustomobject]@{ Parameters = @{} } }
function Start-Process { throw 'Unexpected elevation' }
function Set-PSRepository { throw 'Unexpected repository change' }
function Install-Module { throw 'Unexpected install' }
try { & $args[0] } catch {
    if ($_.Exception.Message -like '*Install PowerShell 7*') { exit 0 }
    throw
}
throw 'Expected preflight to stop'
""")
        self.cmd("powershell.exe", "-NoProfile", "-NonInteractive", "-File", driver, hook)

    def module_hook_fixture(self, profile):
        self.facts = {"pkgs": {"windows": {"psGallery": ["Fixture.Module"]}},
                      "machine": {"profile": profile, "ephemeral": False}}
        rendered = self.cm("execute-template", "--file",
                           ROOT / "home/.chezmoiscripts/windows/run_once_after_10_install-pwsh-modules.ps1.tmpl")
        # Exercise only the elevated body, with no UAC, real repositories or installs.
        script = rendered.decode().replace("\r\n", "\n")
        discovery, _, _ = script.partition("$installer = Get-Command")
        _, handoff, body = script.partition("exit $child.ExitCode\n}\n")
        self.assertTrue(handoff)
        return self.put(f"modules-{profile}.ps1", discovery + body)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell module bootstrap")
    def test_psgallery_bootstrap(self):
        self.init()
        hook = self.module_hook_fixture("personal")
        driver = self.put("gallery-fixture.ps1", """
$ErrorActionPreference = 'Stop'
$hook = $args[0]
function Import-Module {}
function Get-Module { [pscustomobject]@{Name='Fixture.Module'; ModuleBase=$global:moduleBase} }
function Get-PSRepository($Name) {
    if ($global:offline) { throw 'Unexpected gallery lookup for an available all-users module' }
    if (-not $Name) { [pscustomobject]@{ Name = 'Internal'; InstallationPolicy = 'Trusted' } }
    if ($global:policy -ne 'Missing') {
        [pscustomobject]@{ Name = 'PSGallery'; InstallationPolicy = $global:policy; SourceLocation = $global:url }
    }
}
function Register-PSRepository { throw "Legacy NuGet call: Missing option value for: '-source'" }
function Register-PackageSource($Name, $ProviderName, [switch]$Trusted) {
    if ($Name -ne 'PSGallery' -or $ProviderName -ne 'PowerShellGet' -or -not $Trusted -or
        $global:policy -ne 'Missing') { throw 'Unexpected registration' }
    $global:policy = 'Trusted'
}
function Set-PSRepository($Name, $InstallationPolicy) {
    if ($Name -ne 'PSGallery' -or $global:policy -eq 'Missing') { throw "Repository not found: $Name" }
    $global:policy = $InstallationPolicy
    'trust'
}
function Install-Module($Name, $Repository, $Scope, [switch]$AcceptLicense, [switch]$Force) {
    if ($Repository -ne 'PSGallery' -or $global:policy -ne 'Trusted') { throw 'Gallery not ready' }
    $Name
}
$global:moduleBase = [Environment]::GetFolderPath('ProgramFiles') + '\\PowerShell\\Modules\\Fixture.Module'
$global:offline = $true
& $hook
$global:offline = $false
$global:moduleBase = Join-Path $HOME 'Documents/PowerShell/Modules/Fixture.Module'
$global:url = 'https://gallery.example.invalid/api/v2'
foreach ($initial in 'Missing', 'Untrusted', 'Trusted') {
    $global:policy = $initial
    $events = @(& $hook)
    "$initial=$($events -join ',')"
}
$global:policy = 'Missing'
$global:url = ''
try { & $hook; throw 'Accepted an empty source URL' } catch {
    if ($_.Exception.Message -notlike 'PSGallery has no source URL.*') { throw }
}
""")
        lines = self.cmd("pwsh", "-NoProfile", "-NonInteractive", "-File", driver, hook).decode().splitlines()
        self.assertIn("Missing=Fixture.Module", lines)
        self.assertIn("Untrusted=trust,Fixture.Module", lines)
        self.assertIn("Trusted=Fixture.Module", lines)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell module bootstrap")
    def test_work_modules_use_managed_repository_only(self):
        self.init()
        work, personal = (self.module_hook_fixture(profile) for profile in ("work", "personal"))
        driver = self.put("work-gallery.ps1", """
$ErrorActionPreference = 'Stop'
$work, $personal = $args
function Get-Module {}
function Import-Module {}
function Get-PSRepository {
    [pscustomobject]@{Name='PSGallery'; SourceLocation='https://public.example.invalid'; InstallationPolicy='Trusted'}
    if ($case -ne 'missing') {
        [pscustomobject]@{Name='azure-powershell'; SourceLocation=$url; InstallationPolicy=$policy}
    }
}
function Register-PackageSource { throw 'Unexpected repository registration' }
function Set-PSRepository { throw 'Unexpected repository change' }
function Install-Module($Name, $Repository, $Scope, [switch]$AcceptLicense, [switch]$Force) {
    $global:attempts++
    if ($Repository -ne 'azure-powershell' -or $Scope -ne 'AllUsers') { throw 'Wrong install source/scope' }
    if ($case -eq 'unavailable') { throw 'Fixture dependency unavailable from CFS' }
}
foreach ($case in 'managed','missing','wrong-uri','untrusted','unavailable','personal-conflict') {
    $url = 'https://packagefeedproxy.microsoft.io/powershell/v2/'
    $policy = 'Trusted'
    if ($case -eq 'wrong-uri') { $url = 'https://wrong.example.invalid/' }
    if ($case -eq 'untrusted') { $policy = 'Untrusted' }
    $expected = switch ($case) {
        'missing'           { '*missing for the installing account*' }
        'wrong-uri'         { '*registration was not changed*' }
        'untrusted'         { '*registration was not changed*' }
        'unavailable'       { 'Fixture dependency unavailable from CFS' }
        'personal-conflict' { '*no public repository was restored or used*' }
    }
    $global:attempts = 0
    try {
        if ($case -eq 'personal-conflict') { & $personal } else { & $work }
        if ($expected) { throw "Unexpected success: $case" }
    } catch {
        if (-not $expected -or $_.Exception.Message -notlike $expected) { throw }
    }
    if ($global:attempts -ne [int]($case -in 'managed','unavailable')) { throw "Wrong attempt count: $case" }
}
""")
        self.cmd("pwsh", "-NoProfile", "-NonInteractive", "-File", driver, work, personal)
        self.facts["machine"].update(profile="work", ephemeral=True)
        template = ROOT / "home/.chezmoiscripts/windows/run_once_after_10_install-pwsh-modules.ps1.tmpl"
        self.assertFalse(self.cm("execute-template", "--file", template).strip())
        self.facts["machine"]["ephemeral"] = False  # Even a cached workstation config cannot opt CI in.
        with patch.dict(self.env, TF_BUILD="True"):
            self.assertFalse(self.cm("execute-template", "--file", template).strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
