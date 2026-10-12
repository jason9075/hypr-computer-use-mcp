from hypr_computer_use.realm import RealmState, _write_state, read_state


def test_state_round_trip(tmp_path):
  state = RealmState("sig", "wayland-2", 1234)
  _write_state(str(tmp_path), state)
  assert read_state(str(tmp_path)) == state


def test_missing_or_corrupt_state_is_none(tmp_path):
  assert read_state(str(tmp_path)) is None
  (tmp_path / "hypr-cu").mkdir()
  (tmp_path / "hypr-cu" / "realm.json").write_text("{not json")
  assert read_state(str(tmp_path)) is None
