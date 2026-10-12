import os

from hypr_computer_use.session import discover


def _instance(runtime, sig, pid, display):
  d = runtime / "hypr" / sig
  d.mkdir(parents=True)
  (d / "hyprland.lock").write_text(f"{pid}\n{display}\n")


def test_noop_when_env_complete(tmp_path):
  env = {"XDG_RUNTIME_DIR": "x", "HYPRLAND_INSTANCE_SIGNATURE": "s", "WAYLAND_DISPLAY": "w"}
  assert discover(env) == {}


def test_recovers_from_live_instance(tmp_path):
  _instance(tmp_path, "sig_live", os.getpid(), "wayland-7")
  assert discover({"XDG_RUNTIME_DIR": str(tmp_path)}) == {
    "HYPRLAND_INSTANCE_SIGNATURE": "sig_live",
    "WAYLAND_DISPLAY": "wayland-7",
  }


def test_skips_dead_instances(tmp_path):
  _instance(tmp_path, "sig_dead", 2**22 + 1, "wayland-9")
  assert discover({"XDG_RUNTIME_DIR": str(tmp_path)}) == {}


def test_keeps_existing_values(tmp_path):
  _instance(tmp_path, "sig_live", os.getpid(), "wayland-7")
  env = {"XDG_RUNTIME_DIR": str(tmp_path), "WAYLAND_DISPLAY": "wayland-0"}
  assert discover(env) == {"HYPRLAND_INSTANCE_SIGNATURE": "sig_live"}
