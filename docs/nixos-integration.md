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

## 2. 註冊到 Claude Code 和 Codex

兩者的設定檔都是 mutable 的（Codex 會自己寫入 trust 設定），不適合交給 Home Manager 管理，所以用
指令註冊，並指向 PATH 上的 binary 名稱：

```sh
cd ~/projects/hypr-computer-use-mcp
just install      # claude mcp add + codex mcp add，都指向 hypr-computer-use-mcp
```

之後只要 `nix flake update hypr-computer-use-mcp` 再 `nh home switch` 就能升級，不需要重新註冊。

## 3. 看 nest

nest 在 ws1，是一個普通的 workspace，`super+1` 就能切過去看，按 `super+2`～`0` 回來。

不需要任何 Hyprland 設定。nest 啟動時，用 exec rule 把視窗放進 ws1（`workspace 1 silent`），並開啟
`render_unfocused`，讓它在隱藏時持續以 15 FPS 更新。

> 早期版本需要一台 headless 螢幕 `AGENT`、對應的 monitor rule，以及特製的 `nest_ws.sh` 來處理
> `super+1`。這些都因為效能問題而拿掉了，見 [nest.md](nest.md#為什麼不用-headless-螢幕舊設計)。

## 4. 自訂 nest：桌布和 dock

nest 啟動時，如果 `$XDG_CONFIG_HOME/hypr-cu/nest.conf` 存在，會用 `source` 把它載入 nested Hyprland 的
config。檔案不存在時就不加 `source`，因為 Hyprland 會把找不到的 `source` 當成 config 錯誤。

taipei 用一個 Home Manager 模組（`home/gui/agent-nest.nix`）產生這個檔案：

```nix
xdg.configFile."hypr-cu/nest.conf".text = ''
  exec-once = ${pkgs.swaybg}/bin/swaybg -i ${../../assets/agent-nest-wallpaper.png} -m fill
  exec-once = ${pkgs.waybar}/bin/waybar -c ${dockConfig} -s ${dockStyle}
'';
```

- **桌布**：nested Hyprland 預設是全黑的背景，所以在 nest 裡跑 `swaybg` 顯示 agent 專用桌布，上面印著
  操作提示。
- **dock**：nest 底部用 `waybar` 放一條小 dock，有兩個按鈕：󰀻 開 rofi、󰅖 關閉 nest 裡 focus 中的視窗。
  一開始用的是快捷鍵（`alt+f`），後來改成 dock，原因有兩個：host 的快捷鍵佔用了 SUPER 而且優先於 nest，
  而且 nest 裡沒有 `super+q`（在 host 上它關的是整個 nest 的外層視窗），需要另一種關閉視窗的方式。
- **注意**：從 nest 的 rofi 開 Firefox，會開在你主力的 Firefox 裡，因為沒有帶 `--no-remote` 和 nest
  的 profile。要在 nest 開網頁請用 agent 的 `open_url`。
- **關閉程式**：用 dock 的 󰅖，或程式自己的 ✕ / `ctrl+q`。在 ws1 按 `super+q` 關的是整個 nest 的外層
  視窗，裡面的程式會留在背景，要用 `nest down` 才會完整清掉。

## 5. Robot icon 顯示 agent 狀態

ws1 的 icon 換成 robot 圖示 󰚩，並依 nest 狀態變色：

| 狀態 | 判斷方式 | 顏色 |
|---|---|---|
| 沒有 nest | 沒有 `nest.json`，或記錄的 compositor PID 已經不在 | 一般 |
| nest 閒置 | nest 活著，但 20 秒內沒有 tool call | 黃色 |
| **agent 正在操作** | 20 秒內有 tool call | **綠色並閃爍** |

運作方式：

- **server**：每次 tool call 解析 nest target 時，touch `$XDG_RUNTIME_DIR/hypr-cu/activity`；
  `nest down` 時刪除。
- **ags**：每 0.5 秒用 Gio 讀 `nest.json`、確認 PID 是否還活著，再看 `activity` 的修改時間，把結果
  變成 ws1 按鈕的 CSS class（`nest-idle`、`nest-active`）。tooltip 也會顯示目前狀態。

門檻設成 20 秒，是因為 agent 兩次 tool call 之間常有思考時間；門檻太短，icon 會在一個任務進行中
不斷閃爍。

開發時發現 ags 原本的程式碼假設 `focusedWorkspace` 永遠不是 null，但移除螢幕的瞬間它會是 null，
結果拋出錯誤，workspace 按鈕的狀態就卡住不動了。現在已經加上 null 檢查。

## 6. 不需要 uinput

早期版本的 drag 用 `/dev/uinput`，需要把使用者加進 `uinput` group。改用 wlr-virtual-pointer 之後
就不需要了。

## 故障排除

### Bar 不見了

nest 的環境變數殘留在 systemd user environment 裡。新版會自動還原；如果還是發生：

```sh
systemctl --user set-environment WAYLAND_DISPLAY=wayland-1 \
  HYPRLAND_INSTANCE_SIGNATURE=$(hyprctl instances -j | jq -r '.[0].instance')
systemctl --user reset-failed ags && systemctl --user restart ags
```

### nest 卡住、Firefox 開不出來，或狀態不明

```sh
hypr-computer-use-mcp nest status    # 健康時 exit 0；有問題時 exit 1 並印出原因
hypr-computer-use-mcp nest down      # 完整清理：nest 裡的程式、compositor、helper、環境變數
hypr-computer-use-mcp nest up        # 重建
```

### htop 裡的 `Hyprland --watchdog-fd` 很吃 CPU

那是 host compositor 本體，不是 watchdog（`start-hyprland` 才是 watchdog）。nest 隱藏時 host 應該只有
幾個百分點；如果很高，先確認是不是在跑舊版（有 `AGENT` 螢幕的那一版）。
