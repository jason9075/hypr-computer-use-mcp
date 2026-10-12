from hypr_computer_use.realm import (
  RealmState,
  _write_state,
  activity_path,
  mark_activity,
  read_state,
)


def test_state_round_trip(tmp_path):
  state = RealmState("sig", "wayland-2", 1234)
  _write_state(str(tmp_path), state)
  assert read_state(str(tmp_path)) == state


def test_missing_or_corrupt_state_is_none(tmp_path):
  assert read_state(str(tmp_path)) is None
  (tmp_path / "hypr-cu").mkdir()
  (tmp_path / "hypr-cu" / "realm.json").write_text("{not json")
  assert read_state(str(tmp_path)) is None


def test_mark_activity_bumps_mtime(tmp_path):
  _write_state(str(tmp_path), RealmState("sig", "wayland-2", 1))
  mark_activity(str(tmp_path))
  first = activity_path(str(tmp_path)).stat().st_mtime_ns
  mark_activity(str(tmp_path))
  assert activity_path(str(tmp_path)).stat().st_mtime_ns >= first


def test_mark_activity_without_state_dir_is_silent(tmp_path):
  mark_activity(str(tmp_path / "missing"))
