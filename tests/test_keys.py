import pytest

from hypr_computer_use.keys import KeyComboError, wtype_args


@pytest.mark.parametrize(
  "combo,expected",
  [
    ("Return", ["-k", "Return"]),
    ("enter", ["-k", "Return"]),
    ("a", ["a"]),
    ("ctrl+c", ["-M", "ctrl", "c", "-m", "ctrl"]),
    (
      "ctrl+shift+t",
      ["-M", "ctrl", "-M", "shift", "t", "-m", "shift", "-m", "ctrl"],
    ),
    ("super+1", ["-M", "logo", "1", "-m", "logo"]),
    ("super", ["-k", "Super_L"]),
    ("alt+F4", ["-M", "alt", "-k", "F4", "-m", "alt"]),
    ("ctrl+-", ["-M", "ctrl", "-k", "minus", "-m", "ctrl"]),
    ("ctrl++", ["-M", "ctrl", "-k", "plus", "-m", "ctrl"]),
    ("XF86AudioMute", ["-k", "XF86AudioMute"]),
  ],
)
def test_wtype_args(combo, expected):
  assert wtype_args(combo) == expected


@pytest.mark.parametrize("combo", ["", "ctrl+", "+a", "hyper+a"])
def test_rejects_bad_combos(combo):
  with pytest.raises(KeyComboError):
    wtype_args(combo)
