# NixOS 整合

以下以 [jason9075/nixos-config](https://github.com/jason9075/nixos-config) 的 `taipei` 機器為例。

## 1. 安裝 package

`flake.nix`：

```nix
hypr-computer-use-mcp = {
  url = "github:jason9075/hypr-computer-use-mcp";
  inputs.nixpkgs.follows = "nixpkgs";
  inputs.flake-utils.follows = "flake-utils";
};
```

Home Manager：

```nix
home.packages = [ inputs.hypr-computer-use-mcp.packages.x86_64-linux.default ];
```

Package 會把 `grim`、`wtype`、`wlrctl` 加進 PATH。`hyprctl` 和 `Hyprland` 則刻意**不打包**，而是用
系統上的版本，因為它們必須跟正在跑的 compositor 一致。

使用 `follows` 時，package 會改用你的 nixpkgs 來 build，包括 pywayland。protocol bindings 是在 build
時用同一個 pywayland 生成的，所以不同版本都能正常運作（已驗證 pywayland 0.4.18 和 0.4.19）。

## 2. 固定 AGENT 螢幕的位置

`home/gui/hyprland.nix`：

```nix
monitor = [
  "HDMI-A-1,1920x1080@144,0x0,1"
  "AGENT,1920x1080@60,-10000x0,1"
];
```

AGENT 只有在 `realm up` 時才會建立，這條 rule 平常不會有任何作用。但一定要寫進 config：否則 config
reload 時，Hyprland 會把 AGENT 放到實體螢幕旁邊，你的滑鼠就會掉進一台看不見的螢幕。

## 3. 註冊到 Claude Code 和 Codex

兩者的設定檔都是 mutable 的（Codex 會自己寫入 trust 設定），不適合交給 Home Manager 管理，所以用
指令註冊，並指向 PATH 上的 binary 名稱：

```sh
cd ~/projects/hypr-computer-use-mcp
just install      # claude mcp add + codex mcp add，都指向 hypr-computer-use-mcp
```

之後只要 `nix flake update hypr-computer-use-mcp` 再 `nh home switch` 就能升級，不需要重新註冊。

## 4. `super+1`：看 realm，`super+2`～`0`：回來

`scripts/realm_ws.sh` 取代原本的 `workspace N`：

| 按鍵 | realm 在 AGENT 上（背景執行中） | realm 正在你的螢幕上 | 沒有 realm |
|---|---|---|---|
| `super+1` | 把 ws1 拉到你的螢幕來看 | 不變 | 一般的 `workspace 1` |
| `super+2`～`0` | 一般的 `workspace N` | 先把 ws1 送回 AGENT，再切到 N | 一般的 `workspace N` |

兩個要注意的地方：

- **不能用 `focusworkspaceoncurrentmonitor`**：它會把你目前的 workspace「交換」到 AGENT 上，你的
  ws10 就會被丟到一台看不見的螢幕。所以改用 `moveworkspacetomonitor`。
- **送回 AGENT 時要還原游標**：讓 AGENT 顯示 ws1 需要暫時 focus AGENT，而這會 warp 游標。

AGS bar 上的 workspace 按鈕也走同一個腳本，所以點按鈕和按快捷鍵的行為一致。ws1 的 icon 換成了
robot 圖示 󰚩。

另外，nested Hyprland 的視窗 class 是 `aquamarine`，所以加了一條 window rule 讓它固定進 ws1：

```nix
"workspace 1 silent, match:class ^(aquamarine)$"
```

## 5. Robot icon 顯示 agent 狀態

ws1 的 robot icon 會依 realm 狀態變色：

| 狀態 | 判斷方式 | 顏色 |
|---|---|---|
| 沒有 realm | 沒有 `realm.json`，或記錄的 compositor PID 已經不在 | 一般 |
| realm 閒置 | realm 活著，但 20 秒內沒有 tool call | 黃色 |
| **agent 正在操作** | 20 秒內有 tool call | **綠色並閃爍** |

運作方式：

- **server**：每次 tool call 解析 realm target 時，touch `$XDG_RUNTIME_DIR/hypr-cu/activity`；
  `realm down` 時刪除。
- **ags**：每 0.5 秒用 Gio 讀 `realm.json`、確認 PID 是否還活著，再看 `activity` 的修改時間，把結果
  變成 ws1 按鈕的 CSS class（`realm-idle`、`realm-active`）。tooltip 也會顯示目前狀態。

門檻設成 20 秒，是因為 agent 兩次 tool call 之間常有思考時間；門檻太短，icon 會在一個任務進行中
不斷閃爍。

開發時發現 ags 原本的程式碼假設 `focusedWorkspace` 永遠不是 null。但移除 AGENT 螢幕的瞬間它會是
null，結果拋出錯誤，workspace 按鈕的狀態就卡住不動了。現在已經加上 null 檢查。

## 6. 不再需要 uinput

早期版本的 drag 用 `/dev/uinput`，需要把使用者加進 `uinput` group。改用 wlr-virtual-pointer 之後
就不需要了，這個設定已經移除。

## 故障排除

### 按了 `super+1` 之後畫面沒反應，鍵盤也沒作用

focus 跑到看不見的 AGENT 螢幕了。在部署 `realm_ws.sh` 之前，`super+1` 是原本的 `workspace 1`，
就會這樣。按 **`super+0`**（或任何 `super+2`～`9`）就能回來：host 的 keybind 優先於 nested。

### Bar 不見了

realm 的環境變數殘留在 systemd user environment 裡。新版已經會自動還原；如果還是發生：

```sh
systemctl --user set-environment WAYLAND_DISPLAY=wayland-1 \
  HYPRLAND_INSTANCE_SIGNATURE=$(hyprctl instances -j | jq -r '.[0].instance')
systemctl --user reset-failed ags && systemctl --user restart ags
```

### realm 卡住或狀態不明

```sh
hypr-computer-use-mcp realm status    # 健康時 exit 0；有問題時 exit 1 並印出原因
hypr-computer-use-mcp realm down      # 完整清理：compositor、殘留 helper、AGENT 螢幕、環境變數
hypr-computer-use-mcp realm up        # 重建
```
