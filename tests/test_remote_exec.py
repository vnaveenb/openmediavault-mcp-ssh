"""Unit tests for the remote-exec shim: argv quoting, retry semantics, and
mode dispatch. Pure-local — no NAS, no network.
"""

import subprocess
import sys

import pytest

from omv_mcp import local, ssh_remote


def _capture_exec(monkeypatch):
    calls = []

    def fake_exec(command, timeout, input_text):
        calls.append({"command": command, "timeout": timeout, "input": input_text})
        return {"stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(ssh_remote, "_exec_once", fake_exec)
    return calls


def test_argv_quoting_preserves_no_shell_semantics(monkeypatch):
    calls = _capture_exec(monkeypatch)
    ssh_remote.run_remote(["docker", "exec", "c1", "sh", "-c", 'echo "a b" | wc -l'])
    # the pipe/quotes must arrive as ONE argument to sh -c, not be interpreted
    assert calls[0]["command"].endswith("docker exec c1 sh -c 'echo \"a b\" | wc -l'")
    assert calls[0]["command"].startswith("PATH=")  # PATH guarantee for omv-rpc/docker


def test_non_string_argv_items_are_coerced(monkeypatch):
    calls = _capture_exec(monkeypatch)
    ssh_remote.run_remote(["tail", "-n", 100, "/var/log/syslog"])
    assert "tail -n 100 /var/log/syslog" in calls[0]["command"]


def test_timeout_is_not_retried(monkeypatch):
    calls = []

    def fake_exec(command, timeout, input_text):
        calls.append(command)
        raise TimeoutError("boom")

    monkeypatch.setattr(ssh_remote, "_exec_once", fake_exec)
    with pytest.raises(TimeoutError):
        ssh_remote.run_remote(["sleep", "999"], timeout=1)
    assert len(calls) == 1  # a timed-out command must never run twice


def test_dead_connection_is_retried_once(monkeypatch):
    calls = []

    def fake_exec(command, timeout, input_text):
        calls.append(command)
        if len(calls) == 1:
            raise EOFError("connection dropped")
        return {"stdout": "ok", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(ssh_remote, "_exec_once", fake_exec)
    monkeypatch.setattr(ssh_remote, "_invalidate", lambda: None)
    assert ssh_remote.run_remote(["true"])["stdout"] == "ok"
    assert len(calls) == 2


def test_mode_a_runs_local_subprocess(monkeypatch):
    monkeypatch.setattr(local.config, "OMV_HOST", "")
    r = local.run_local([sys.executable, "-c", "print('mode-a')"])
    assert r["exit_code"] == 0
    assert r["stdout"].strip() == "mode-a"


def test_mode_b_dispatches_to_ssh(monkeypatch):
    monkeypatch.setattr(local.config, "OMV_HOST", "198.51.100.1")
    seen = {}

    def fake_run_remote(argv, timeout=60, input_text=None):
        seen["argv"] = argv
        return {"stdout": "", "stderr": "", "exit_code": 0}

    monkeypatch.setattr(ssh_remote, "run_remote", fake_run_remote)
    local.run_local(["hostname"])
    assert seen["argv"] == ["hostname"]


def test_config_precedence_env_beats_config_file(tmp_path):
    """Real env var wins over config.env; config.env wins over nothing."""
    cfg_dir = tmp_path / "omv-mcp"
    cfg_dir.mkdir()
    (cfg_dir / "config.env").write_text("OMV_HOST=from-file\nOMV_SSH_PORT=2222\n")

    def load(extra_env):
        env = {
            "APPDATA": str(tmp_path),
            "XDG_CONFIG_HOME": str(tmp_path),
            "SYSTEMROOT": "C:\\Windows",  # required on Windows
            **extra_env,
        }
        out = subprocess.run(
            [sys.executable, "-c",
             "import omv_mcp.config as c; print(c.OMV_HOST, c.OMV_SSH_PORT)"],
            capture_output=True, text=True, env=env,
        )
        assert out.returncode == 0, out.stderr
        return out.stdout.split()

    assert load({}) == ["from-file", "2222"]
    assert load({"OMV_HOST": "from-env"}) == ["from-env", "2222"]
