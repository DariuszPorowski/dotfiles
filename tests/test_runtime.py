"""Offline runtime and shell-startup regressions; no installed SDK or agent is used."""

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import time
import unittest

from smoke import BASH, CHEZMOI, ROOT


SCRIPTS = ROOT / "home/dot_taskfiles/scripts"
GO = SCRIPTS / "executable_setup_golang.sh"
FNM = SCRIPTS / "executable_setup_fnm.sh"
COMMON = ROOT / "home/dot_commonrc.tmpl"


@unittest.skipUnless(BASH, "requires Bash")
class Runtime(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix=".runtime fixture ", dir=ROOT)
        self.addCleanup(self.cleanup_home, work)
        self.home = Path(work.name)
        self.env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "COMSPEC", "PATH")
                    if k in os.environ}
        self.env.update(HOME=str(self.home), USERPROFILE=str(self.home), MSYS="winsymlinks:sys",
                        TEMP=str(self.home), TMP=str(self.home), TMPDIR=str(self.home),
                        XDG_CONFIG_HOME=str(self.home / "config"), XDG_CACHE_HOME=str(self.home / "cache"))
        self.tool("fake/curl", 'echo unexpected-download >> "$HOME/curl.log"; exit 88')
        self.tool("fake/ssh-add", "exit 2")
        self.tool("fake/fnm", '[ "$1" != env ] || echo "export FNM_TEST=host"')
        self.tool("fake/go", "echo host-go")

    @staticmethod
    def cleanup_home(work):
        # Windows scanners can briefly hold a directory handle after a shell exits.
        for attempt in range(10):
            try:
                work.cleanup()
                return
            except PermissionError as exc:
                if getattr(exc, "winerror", None) != 32 or attempt == 9:
                    raise
                time.sleep(0.1)

    def put(self, name, data):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode())
        return path

    def tool(self, name, body):
        self.put(name, "#!/bin/sh\n" + body + "\n").chmod(0o755)

    def bash(self, script, *args, status=0, interactive=False):
        # Start from an empty environment and resolve optional integrations only
        # to fixture tools. In particular, never initialize a real agent/manager.
        setup = r'''
cd -- "$1" || exit 1
shift
export HOME="$PWD" PATH="$PWD/fake:/usr/bin:/bin" TMPDIR="$PWD"
export XDG_CONFIG_HOME="$HOME/config" XDG_STATE_HOME="$HOME/state" XDG_RUNTIME_DIR="$HOME/run"
export DBUS_SESSION_BUS_ADDRESS=fixture
command() {
  if [[ $1 == -v ]]; then
    case "$2" in mise|aliae|oh-my-posh|chezmoi|uv|uvx|helm|gh) return 1 ;; esac
  fi
  builtin command "$@"
}
function /mnt/c/Windows/System32/cmd.exe { echo fixture; }
'''
        result = subprocess.run([BASH, "--noprofile", "--norc", *(["-i"] if interactive else []),
                                 "-c", setup + "\n" + script, "fixture", self.home.as_posix(),
                                 *(str(x) for x in args)], cwd=ROOT, env=self.env, text=True,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertEqual(result.returncode, status, result.stderr + result.stdout)
        return result.stdout.splitlines()

    def commonrc(self, wsl=False):
        if not CHEZMOI:
            self.skipTest("requires chezmoi to render the shell template")
        cfg = self.put("fixture.toml", "")
        result = subprocess.run([CHEZMOI, "--source", self.home, "--destination", self.home,
                                 "--cache", self.home / "cache", "--config", cfg, "--no-tty",
                                 "--override-data", json.dumps({"machine": {"wsl": wsl}}),
                                 "execute-template", "--file", COMMON], cwd=self.home,
                                env=self.env, check=True, capture_output=True, timeout=30)
        self.put("commonrc", result.stdout.decode())

    @staticmethod
    def go_body(version):
        return f'[ "$1" = version ] && [ "$GOTOOLCHAIN" = local ] || exit 1\necho "go version {version} linux/amd64"'

    def test_pinned_go_selects_custom_sdk_offline_without_changing_profiles(self):
        self.commonrc()
        self.put("Dev Tools/go/VERSION", "go1.24.1\n")
        self.tool("Dev Tools/go/bin/go", self.go_body("go1.24.1"))
        for name in (".bashrc", ".zshrc"):
            self.put(name, "# user owned\n")
        self.bash('set -e; ln -s "$HOME/Dev Tools" sdk; bash "$1" 1.24.1 sdk; bash "$1" go1.24.1 sdk', GO)
        lines = self.bash('''
export GOPATH="$HOME/work space" GOBIN="$HOME/tool bin"
source commonrc; first=$PATH; source commonrc
[[ $PATH == "$first" && $GOPATH == "$HOME/work space" && $GOBIN == "$HOME/tool bin" ]] || exit 1
GOTOOLCHAIN=local go version
''', interactive=True)
        self.assertIn("go version go1.24.1 linux/amd64", lines)
        for name in (".bashrc", ".zshrc"):
            self.assertEqual((self.home / name).read_bytes(), b"# user owned\n")
        self.assertFalse((self.home / "curl.log").exists())

    def test_podman_shell_aliases(self):
        self.commonrc()
        self.tool("fake/podman", 'printf "<%s>\\n" "$@"; exit 17')
        lines = self.bash('''
source commonrc
eval 'docker run "two words"'
[[ $? == 17 ]] || exit 1
eval 'docker-compose -f "compose file.yml" up'
[[ $? == 17 ]] || exit 1
''', interactive=True)
        self.assertEqual(lines, ["<run>", "<two words>", "<compose>", "<-f>", "<compose file.yml>", "<up>"])
        (self.home / "fake/podman").unlink()
        self.bash('''
export PATH="$PWD/fake"
alias docker='existing-docker'
source commonrc
[[ $(alias docker) == *existing-docker* ]] && ! alias docker-compose >/dev/null 2>&1
''', interactive=True)

    @unittest.skipIf(sys.platform == "darwin", "the Linux archive installer uses GNU mv")
    def test_go_repairs_mixed_sdk_only_after_verifying_replacement(self):
        version = "go1.24.1"
        self.put("prefix/go/VERSION", version + "\n")
        self.tool("prefix/go/bin/go", self.go_body("go1.19.1"))
        archive = self.home / "fixture.tar.gz"
        with tarfile.open(archive, "w:gz") as out:
            for path, content, mode in (("go/VERSION", version, 0o644),
                                        ("go/bin/go", "#!/bin/sh\n" + self.go_body(version), 0o755)):
                data = content.encode()
                info = tarfile.TarInfo(path)
                info.size, info.mode = len(data), mode
                out.addfile(info, io.BytesIO(data))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.tool("fake/jq", f'printf "%s\\t%s\\t%s\\n" {version} sdk.tar.gz "$(cat "$HOME/digest")"')
        self.tool("fake/curl", '''
while [ "$1" != "-o" ]; do shift; done
case "$3" in *mode=json*) echo fixture > "$2";; */sdk.tar.gz) cp "$HOME/fixture.tar.gz" "$2";; *) exit 88;; esac''')
        # The stage is under the fixture prefix, never in a system temp dir.
        self.tool("fake/mktemp", 'd=${2%.*}.fixture; mkdir "$d" && echo "$d"')
        self.put("digest", "0" * 64)
        self.bash('bash "$1" 1.24.1 prefix', GO, status=1)
        self.assertIn("go1.19.1", (self.home / "prefix/go/bin/go").read_text())
        self.put("digest", digest)
        self.bash('bash "$1" 1.24.1 prefix', GO)
        self.assertIn(version, (self.home / "prefix/go/bin/go").read_text())

    def test_fnm_pin_precedence_and_precise_fish_migration(self):
        self.commonrc()
        self.tool("Node Tools/fnm", "echo 'fnm 1.0.0'")
        self.tool("new-fnm", '''
case "$1" in
  --version) echo 'fnm 1.38.1';;
  env) [ "$*" = 'env --use-on-cd --version-file-strategy=recursive --shell bash' ] &&
       echo 'export FNM_TEST=selected';;
esac''')
        self.tool("fake/curl", 'cat "$HOME/mock-fnm-install"')
        self.put("mock-fnm-install", '''
[ "$1" = --skip-shell ] && [ "$2" = --install-dir ] &&
[ "$3" = "$HOME/Node Tools" ] && [ "$4" = --release ] && [ "$5" = v1.38.1 ] || exit 89
cp "$HOME/new-fnm" "$3/fnm"
''')
        fish = self.put("config/fish/config.fish", "")
        self.bash('''printf '%s\\n' "export PATH=\\$PATH:$HOME/Node Tools" \\
  'eval "$(fnm env --use-on-cd --shell fish)"' '# fnm env: keep my hook' >config/fish/config.fish
printf 'set -gx USER_SETTING 1' >>config/fish/config.fish''')
        self.bash('bash "$1" 1.38.1 "$HOME/Node Tools"', FNM)
        self.tool("fake/curl", 'echo unexpected-download >> "$HOME/curl.log"; exit 88')
        self.bash('bash "$1" v1.38.1 "$HOME/Node Tools"', FNM)
        self.assertEqual(fish.read_bytes(), b"# fnm env: keep my hook\nset -gx USER_SETTING 1")
        lines = self.bash('source commonrc; echo "$FNM_TEST"; fnm --version', interactive=True)
        self.assertEqual(lines, ["selected", "fnm 1.38.1"])
        self.assertFalse((self.home / "curl.log").exists())
        fish.unlink()
        hook = self.home / "config/fish/conf.d/dotfiles-fnm.fish"
        hook.unlink()
        self.bash('bash "$1" 1.38.1 "$HOME/Node Tools"', FNM)
        self.assertIn("--shell fish | source", hook.read_text())
        self.assertFalse(fish.exists())
        for name in (".bashrc", ".zshrc"):
            self.assertFalse((self.home / name).exists())

    def test_forwarded_empty_and_stale_agent_selection(self):
        self.commonrc(wsl=True)
        self.tool("fake/ssh-add", '''
[ "$1" = -l ] || exit 99
case "$SSH_AUTH_SOCK" in
  */forwarded) exit 0;; */empty) exit 1;;
  */dotfiles-ssh/agent.sock) exit "$SERVICE";;
  */.ssh/agent.sock) exit 0;; *) exit 2;;
esac''')
        self.tool(".local/bin/1p-ssh-agent-relay.sh", 'echo started >> "$HOME/relay.log"')
        for inherited, service, wanted in (("forwarded", 0, "forwarded"), ("empty", 0, "empty"),
                                           ("", 0, "run/dotfiles-ssh/agent.sock"),
                                           ("stale", 1, "run/dotfiles-ssh/agent.sock"),
                                           ("stale", 2, ".ssh/agent.sock")):
            with self.subTest(inherited=inherited, service=service):
                self.bash('''
export SERVICE="$2"; if [[ -n $1 ]]; then export SSH_AUTH_SOCK="$HOME/$1"; fi
source commonrc; [[ $SSH_AUTH_SOCK == "$HOME/$3" ]]
''', inherited, service, wanted, interactive=True)
        self.assertEqual((self.home / "relay.log").read_text().splitlines(), ["started"])

    def test_git_clean_continues_after_refusal_and_stops_on_fetch_failure(self):
        task = (ROOT / "home/Taskfile.yml").read_text(encoding="utf-8").split("\n  git:clean:\n", 1)[1]
        body = task.split("      - cmd: |\n", 1)[1]
        self.put("clean.sh", "set -o pipefail\n" + textwrap.dedent(body))
        self.tool("fake/git", '''
case "$1" in
  fetch) exit "$FETCH";;
  for-each-ref)
    case "$2" in *refname:lstrip=2*) name=release;; *) name=heads/release;; esac
    printf 'busy [gone]\\ntracking [ahead 1]\\n%s [gone]\\n' "$name";;
  branch) [ "$2 $3" = "-d --" ] || exit 99
    echo "$4" >> "$HOME/candidates"; [ "$4" != busy ];;
  *) exit 99;;
esac''')
        self.bash("FETCH=1 bash clean.sh", status=1)
        self.assertFalse((self.home / "candidates").exists())
        self.bash("FETCH=0 bash clean.sh", status=1)
        self.assertEqual((self.home / "candidates").read_text().splitlines(), ["busy", "release"])
