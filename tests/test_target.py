import os

import pytest

from hypr_computer_use.target import Target, TargetError, host_target, live_instances


def _instance(runtime, sig, pid, display):
  d = runtime / "hypr" / sig
  d.mkdir(parents=True)
  (d / "hyprland.lock").write_text(f"{pid}\n{display}\n")


def test_env_wins_when_complete(tmp_path):
  env = {
    "XDG_RUNTIME_DIR": str(tmp_path),
    "HYPRLAND_INSTANCE_SIGNATURE": "s",
    "WAYLAND_DISPLAY": "w",
  }
  assert host_target(env) == Target("host", "s", "w", str(tmp_path))


def test_recovers_from_live_instance(tmp_path):
  _instance(tmp_path, "sig_live", os.getpid(), "wayland-7")
  t = host_target({"XDG_RUNTIME_DIR": str(tmp_path)})
  assert (t.signature, t.wayland_display) == ("sig_live", "wayland-7")


def test_skips_dead_instances(tmp_path):
  _instance(tmp_path, "sig_dead", 2**22 + 1, "wayland-9")
  assert live_instances(str(tmp_path)) == []
  with pytest.raises(TargetError):
    host_target({"XDG_RUNTIME_DIR": str(tmp_path)})


def test_excludes_realm_even_if_newest(tmp_path):
  _instance(tmp_path, "sig_host", os.getpid(), "wayland-1")
  _instance(tmp_path, "sig_realm", os.getpid(), "wayland-2")
  # The realm's lock is newer, which a naive "newest instance" pick would choose.
  os.utime(tmp_path / "hypr" / "sig_host" / "hyprland.lock", (0, 0))
  t = host_target({"XDG_RUNTIME_DIR": str(tmp_path)}, frozenset({"sig_realm"}))
  assert t.signature == "sig_host"


def test_env_pointing_at_realm_is_ignored(tmp_path):
  _instance(tmp_path, "sig_host", os.getpid(), "wayland-1")
  env = {
    "XDG_RUNTIME_DIR": str(tmp_path),
    "HYPRLAND_INSTANCE_SIGNATURE": "sig_realm",
    "WAYLAND_DISPLAY": "wayland-2",
  }
  assert host_target(env, frozenset({"sig_realm"})).signature == "sig_host"


def test_target_env_and_socket():
  t = Target("realm", "sig", "wayland-2", "/run/user/1000")
  env = t.env({"PATH": "/bin", "WAYLAND_DISPLAY": "wayland-1"})
  assert env["WAYLAND_DISPLAY"] == "wayland-2" and env["PATH"] == "/bin"
  assert t.socket_path == "/run/user/1000/wayland-2"
