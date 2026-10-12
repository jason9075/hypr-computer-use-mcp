# 截圖與輸入

## 座標系統

模型看到的是縮小過的截圖，所以每個 x/y 參數都是「**最近一次截圖**裡的像素座標」。server 負責換算成
Hyprland 的全域 logical 座標。

```
截圖像素 ──(÷ factor)──> 螢幕內 logical 座標 ──(+ 螢幕位置)──> 全域 logical 座標
```

`geometry.py` 的 `Viewport` 記錄了換算需要的所有資訊：

```python
@dataclass(frozen=True)
class Viewport:
  monitor: str
  origin_x: int     # 螢幕在全域 layout 的位置
  origin_y: int
  logical_w: int    # logical 尺寸（已除以 scale、已處理旋轉）
  logical_h: int
  factor: float     # 每個 logical 像素對應幾個截圖像素
```

- **縮圖**：`factor = min(1, MAX_EDGE / 長邊)`，預設長邊不超過 1280px。高解析度截圖很耗 token，
  而且模型的座標準確度也會下降。
- **HiDPI**：先除以 monitor 的 `scale` 得到 logical 尺寸。
- **旋轉**：`transform` 是奇數（90° / 270°）時，寬高要對調。
- **邊界檢查**：超出截圖範圍的座標會直接回錯誤，不會點到奇怪的地方。

截圖用 `grim -o <monitor> -s <factor>`。`grim` 的 `-s` 是相對於 logical 尺寸的比例，所以截出來的圖
剛好就是 `Viewport.image_size`，不需要再用 Pillow 縮放。

每個 session（host 或 realm）各自記住最後一張截圖的 `Viewport`，避免兩邊的座標混在一起。

## 點擊與捲動：`wlrctl`

```
hyprctl dispatch movecursor X Y    # 移到全域 logical 座標
wlrctl pointer click left          # 透過 wlr-virtual-pointer 點擊
wlrctl pointer scroll DY DX        # 一格滾輪 = 15 個 axis 單位
```

`wlrctl` 走 Wayland 的 virtual-pointer 協定，**不需要 root、uinput 或常駐 daemon**，這是選它而不是
`ydotool` 的原因。

## 鍵盤：`wtype`

- `type_text`：`wtype -- "text"`，支援 Unicode（`→`、`🎯`、中文都可以）。
- `key`：`keys.py` 把 `"ctrl+shift+t"` 轉成 `wtype -M ctrl -M shift t -m shift -m ctrl`。
  - 單一字元走 wtype 的文字路徑，標點符號的 keysym 交給 wtype 處理。
  - `-` 會被當成選項，所以改用 keysym `minus`；`ctrl++` 代表 ctrl 加上 plus 鍵。
  - 常見別名：`enter`、`esc`、`backspace`、`pageup`、`f1`…`f24`、`super`／`win`／`cmd`（都對應到 `logo`）。

### fcitx5 會吃掉按鍵（只影響 host 模式）

`wtype` 送出的按鍵會經過 input method。fcitx5 注音開著時，打 `https://...` 會變成「ㄏㄩㄥ」。所以在
host 模式下，打字前先用 `fcitx5-remote -c` 暫時關掉 IME，結束後如果原本是開著的，就用
`fcitx5-remote -o` 再打開。realm 裡沒有跑 input method，所以不需要這麼做。

### 限制：Hyprland keybind 不吃 virtual keyboard

`wtype` 送出 `super+m` 時，Hyprland 不會觸發對應的 keybind。agent 要切換視窗，應該用
`focus_window` 這類 IPC tool，不要依賴 WM 快捷鍵。

## 拖曳：wlr-virtual-pointer + pywayland

拖曳需要「按住 → 移動 → 放開」，而 `wlrctl` 只有一次完成的 click。這部分的演進：

| 嘗試 | 結果 |
|---|---|
| evdev `/dev/uinput` | ❌ uinput 是 kernel 層的裝置，事件只會進 **host** 的 seat，到不了 realm；而且還需要額外的 group 權限 |
| virtual pointer + `motion_absolute` | ❌ 只在起點留下一個點，後面的移動都沒有被當成拖曳 |
| virtual pointer + 相對 `motion` | ✅ tldraw 的矩形、箭頭、畫筆線條、GIMP 的筆刷都正確 |

### 為什麼絕對移動不行

實測：沒有按住按鍵時，`motion_absolute` 能正確移動游標。但按住按鍵後，app 收不到移動事件。推測是
Hyprland 把 virtual pointer 的絕對移動當成 warp 處理，而 warp 不會產生 client 端的拖曳事件。改成相對
移動之後，游標位置完全精準，app 也確實收到了拖曳。

### 實作（`vpointer.py`）

```
1. hyprctl movecursor 到起點          ← 絕對定位（沒按住，所以沒問題）
2. button(BTN_LEFT, pressed)
3. 沿路徑送相對 motion(dx, dy)，每步間隔 15ms
4. 讀取實際游標位置，有偏差就補一個修正量  ← 防止 pointer acceleration 造成的誤差
5. button(BTN_LEFT, released)         ← 放在 finally，保證一定會放開
```

連線用 socket 的**絕對路徑**（`$XDG_RUNTIME_DIR/wayland-2`），不依賴 server process 自己的環境變數。

收尾的順序很重要：先 destroy pointer 和 manager，做一次 roundtrip，再 disconnect。順序錯了，pywayland
會在回收 proxy 時 segfault。
