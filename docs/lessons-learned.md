# 踩坑紀錄

開發過程中遇到的問題，依照發現的先後順序排列。每一項都寫了現象、根因和解法，大部分都是實際測試時
才發現的。

## 1. MCP host 會剝掉環境變數

- **現象**：用 MCP SDK 的 stdio client 測試時，所有 `hyprctl` 呼叫都失敗，而且 stderr 是空的。
- **根因**：stdio client 預設只傳少數幾個環境變數，`HYPRLAND_INSTANCE_SIGNATURE` 和
  `WAYLAND_DISPLAY` 都不見了。另外，`hyprctl` 會把錯誤寫到 **stdout**，有時 exit code 還是 0。
- **解法**：從 `$XDG_RUNTIME_DIR/hypr/*/hyprland.lock` 找回 session；錯誤訊息改成在 stderr 為空時
  讀 stdout；dispatcher 的回應必須是 `ok` 才算成功。

## 2. fcitx5 把網址打成注音

- **現象**：agent 在網址列打 `https://www.tldraw.com/`，畫面上出現「ㄏㄩㄥ」。
- **根因**：`wtype` 送出的按鍵會經過 input method。
- **解法**：host 模式下，打字前用 `fcitx5-remote -c` 暫時關掉 IME，結束後還原原本的狀態。

## 3. 隱藏 workspace 上的 nested Hyprland 不會 render

- **現象**：nest 放在隱藏的 workspace，`grim` 截圖直接卡死。
- **根因**：host 不會送 frame callback 給看不見的視窗，nested compositor 就不會畫新的 frame，
  screencopy 永遠等不到。
- **第一個解法**：開一台 headless 螢幕 `AGENT`，讓 nest 的 workspace 成為它的 active workspace。
  能動，但造成 #4、#5 和 #15。
- **最終解法**：window rule `render_unfocused`，見 #15。

## 4. Config reload 把 AGENT 移到你的螢幕旁邊（已因 #15 移除 AGENT）

- **現象**：`nh home switch` 之後，AGENT 從 `-10000x0` 變成 `1920x0`（緊貼實體螢幕），scale 也變成 2。
- **根因**：`hyprctl keyword monitor` 是 runtime 設定，config reload 時會被清掉。
- **解法**：把 monitor rule 寫進 Hyprland config；`nest up` 也會每次重新套用。

## 5. 使用者被困在看不見的螢幕（已因 #15 移除 AGENT）

- **現象**：使用者按了 `super+1`，畫面完全沒反應，鍵盤也沒作用，最後只好登出。
- **根因**：原本的 `super+1` 是 `workspace 1`，而 ws1 在 AGENT 上，focus 就跑到看不見的螢幕。
  AGENT 不相鄰，滑鼠也移不過去。
- **解法**：`nest_ws.sh` 把 ws1 拉到目前的螢幕來顯示。其實按 `super+0` 也能救回來，因為 host 的
  keybind 優先於 nested，只是畫面沒有任何提示，使用者無從得知。

## 6. Vendored bindings 在部署時 import 失敗

- **現象**：本機測試都正常，但用 nixos-config build 出來的版本一啟動就 `ImportError: WlOutputProxy`。
- **根因**：pywayland scanner 的輸出跟 pywayland 版本綁死。0.4.19 產生單一檔案，0.4.18 產生目錄，
  匯入的名稱也不同。nixos-config 用 `follows` 換掉 nixpkgs，拿到的是 0.4.18。
- **解法**：不再 vendor，改成在 Nix build 時用同一個 pywayland 生成，連 core `wayland` 協定也一起生成，
  讓兩者的 import 一定一致。用兩個 nixpkgs 版本都實際 build 並畫過圖。
- **附帶的坑**：hatchling 預設會遵守 `.gitignore`，build 時生成的檔案會被排除在 wheel 之外，所以要在
  `pyproject.toml` 加上 `artifacts`。

## 7. uinput 的事件到不了 nest

- **現象**：用 `/dev/uinput` 實作的 drag 在 nest 裡沒有作用。
- **根因**：uinput 是 kernel 層的輸入裝置，只會被 host compositor 讀取。nested compositor 的輸入只來自
  host 轉送給它的視窗事件。
- **解法**：改用 Wayland 的 wlr-virtual-pointer 協定，直接連到 nest 的 socket。

## 8. 按住時的絕對移動不算拖曳

- **現象**：用 `motion_absolute` 拖曳，tldraw 只在起點留下一個點。
- **根因**：Hyprland 似乎把 virtual pointer 的絕對移動當成 warp，app 收不到拖曳事件。沒按住時，絕對
  移動是正常的。
- **解法**：起點用絕對定位，按住之後改送相對 `motion`，最後再對照實際游標位置修正。

## 9. pywayland 收尾時 segfault

- **現象**：腳本結束時 exit code 139。
- **根因**：proxy 的生命週期比 display 連線還長，被 GC 回收時就 crash。
- **解法**：依序 destroy pointer 和 manager、roundtrip、disconnect。照這個順序做，連續三輪都乾淨結束，
  所以 drag 可以直接在 server process 裡跑，不需要另開 subprocess。

## 10. Bar 不見了

- **現象**：使用者的 AGS bar 消失，ags service 連續重啟失敗，錯誤是 `Failed to open display`。
- **根因**：nested Hyprland 啟動時把 `WAYLAND_DISPLAY=wayland-2` 寫進 systemd/dbus 的 user
  environment。ags 剛好在那時重啟，就連進了 nest；nest 關掉後，ags 一直去連已經不存在的 socket。
- **解法**：`nest up` 後和 `nest down` 後都主動還原。`down` 一定要在 compositor 停止**之後**做，因為
  nested 結束時會再改一次：刪掉 signature，但留下自己的 `WAYLAND_DISPLAY`。
- **沒用的嘗試**：Hyprland 0.54 不支援 `HYPRLAND_NO_SD_VARS`。
- **驗證方式**：nest 開著時重啟 ags，確認 bar 出現在 host 而不是 nest。

## 11. nest 被誤認成 host

- **根因**：nest 也是一個 Hyprland instance，而且比 host 新。環境變數被剝掉時，「挑最新的 instance」
  就會挑到 nest。
- **解法**：辨識 host 時排除 `nest.json` 裡記錄的 signature，並有單元測試覆蓋。

## 12. 殘留的 helper process

- **現象**：nest 關掉後，`pgrep` 還能找到兩個 `Hyprland --config nest.conf`，`ppid=1`。
- **根因**：nested Hyprland 會 fork helper，主程式結束時它們沒有跟著退出。
- **解法**：用 nested config 的路徑比對 `/proc/*/cmdline`，找到後 `SIGKILL`。

## 13. 移除 output 會把游標移到螢幕中央（已因 #15 移除 AGENT）

- **解法**：`hyprctl output remove` 前先記下游標位置，移除後再移回去。

## 14. 讀 YouTube 推薦時遇到的輸入問題（待修）

| 現象 | 推測原因 | 暫時做法 |
|---|---|---|
| `scroll` 在 Firefox 沒有作用 | `wlrctl` 送的滾輪事件缺少 discrete 資訊 | 改按 `Page_Down` |
| 剛開好的頁面，按鍵送不進去 | 鍵盤 focus 還沒落在頁面上 | 先點一下頁面空白處 |
| 游標移動後網頁的 hover 狀態不變 | `movecursor` 是 warp，不會產生 motion 事件 | 無 |

這三個都可以改用 wlr-virtual-pointer 送出真正的 motion 和 discrete scroll 來解決。

## 15. Headless 螢幕讓兩層 compositor 空轉

- **現象**：nest 開著時 host Hyprland 約 70%、nested 約 40%，合計超過一顆 CPU 核心。htop 裡看到的
  是 `Hyprland --watchdog-fd`，容易被誤認成 watchdog 吃資源，其實那就是 host compositor 本體。
- **排查過程**：

  | 嘗試 | 結果 | 學到的事 |
  |---|---|---|
  | AGENT 從 60Hz 降到 10Hz | 沒效果 | 更新率設定沒有被拿來節流 |
  | AGENT 從 1080p 降到 720p | 131% → 128% | 不是像素量的問題 |
  | nested 關掉 blur 和 shadow | 約省 5% | 不是合成效果的問題 |
  | Firefox `layout.frame_rate = 15` | 沒效果 | 影片 frame 不經過這條路徑 |
  | 暫停 nested process | host 掉到約 21% | 成本跟著 nested 的 frame 走 |
  | **開 debug overlay** | **AGENT 674 FPS、nest 492 FPS** | 找到根因 |

- **根因**：headless 螢幕沒有 vblank。host 畫完 AGENT 就立刻送 frame callback，nest 收到就立刻畫下一張，
  兩邊互相觸發，形成沒有節流的迴圈。
- **解法**：拿掉 AGENT，nest 放在一般的隱藏 workspace，用 exec rule 套用 `render_unfocused on`。
  隱藏時 host 以 15 FPS 送 callback，總用量從約 130% 降到約 4%。
- **附帶的坑**：`render_unfocused` 只在視窗建立時生效，事後 `setprop` 沒有用，所以一定要放在 exec rule。
- **連帶的好處**：#4、#5 的問題直接消失，`super+1` 回到一般的 `workspace 1`，也不再需要切換腳本。

## 16. nest 關掉了，裡面的 Firefox 還活著

- **現象**：重啟 nest 後 `open_url` 開不出 Firefox，畫面是空的。
- **根因**：上一個 nest 的 Firefox 在 nested compositor 結束後沒有退出，被 init 收養，連著一個已經不存在
  的 display，還佔住 profile lock。Wayland client 不一定會隨著 compositor 結束。
- **解法**：`nest down` 先用 `/proc/*/environ` 裡的 `HYPRLAND_INSTANCE_SIGNATURE` 找出 nest 裡所有
  程式，`SIGTERM` 後等 5 秒，還活著才 `SIGKILL`。
- **附帶的坑**：`pid_alive` 原本把 zombie 當成還活著，`terminate` 就會白等滿 5 秒；改成讀
  `/proc/PID/stat` 的狀態欄位，`Z` 視為已結束。

## 17. 其他小坑

| 問題 | 解法 |
|---|---|
| Hyprland 的 `--socket` 必須搭配 `--wayland-fd`，不能單獨使用 | 不固定 socket 名稱，改從新出現的 lock 檔辨識 nested instance |
| nested 沒用 `start-hyprland` 啟動，會跳出 watchdog 警告 | `misc:disable_watchdog_warning = true` |
| Firefox 會把 URL 交給 host 上已經開著的 Firefox | 加上 `--no-remote` 和獨立的 profile |
| `focusworkspaceoncurrentmonitor` 會交換 workspace | 改用 `moveworkspacetomonitor` |
| Hyprland keybind 不吃 virtual keyboard 送出的按鍵 | agent 改用 `focus_window` 等 IPC tool |
| 每次開頁面都跳翻譯提示、session 還原分頁 | server 啟動 Firefox 前寫入 `user.js` 關掉這些對話框 |

## 開發心得

- **每個假設都要實測**：幾乎所有坑都是實際操作時才發現的，例如 frame callback、絕對移動、環境變數被搶。
- **用最嚴苛的條件測試**：用會剝掉環境變數的 client 測，才會抓到 #1 和 #11。
- **驗證「使用者沒被影響」**：每次測試前後都記錄 host 的 focus、workspace、游標，而不是只看 agent
  有沒有成功。
- **部署環境跟開發環境不同**：#6 只有用 nixos-config 的 nixpkgs 實際 build 才會發現。
