# UI 交接（給美工／前端）

> 現在只有命令列（CLI）跟字幕浮層，**沒有人類看得懂的控制面板**。
> 這份是給美工／UI 設計師的交接：要做什麼畫面、資產放哪、哪個畫面吃哪個檔。

## 一句話

做一個 Windows 桌面殼：左邊狀態、右邊設定、下面日誌；遊戲中只剩一顆托盤圖示＋字幕。
風格：深色、低干擾、鯨魚娘（藍色大肥魚）元素，不要電競 RGB。

---

## 一、先看這些（現有東西）

| 東西 | 路徑 |
|---|---|
| 專案根 | `C:\Users\cirue\Documents\deepseek-harness\default-workspace\大肥魚的窩\09_陪玩\earside` |
| 可跑的 exe | `...\earside\dist\earside\earside.exe`（214 MB，onedir） |
| 主要程式 | `...\earside\src\earside\`（`cli.py` 是入口） |
| 設定範例 | `...\earside\config.example.toml`（每一項都有註解） |
| 參數說明 | `...\earside\docs\TUNING.md` |
| 每段做了什麼／坑 | `...\earside\docs\HANDOFF.md` |
| 打包 | `...\earside\docs\PACKAGING.md` |
| 字幕浮層 | `...\earside\src\earside\bubble\overlay.py`（tkinter，置頂、滑鼠穿透） |
| 校準精靈（已有 Tk 版） | `...\earside\src\earside\eyes\calibrate.py` |
| 遊戲 preset | `...\earside\presets\`（`general.json` 是空白模板、`demo-color.json` 是測試） |
| 人格 | `...\earside\personas\companion_zh.md` |
| 素材放這裡 | `...\earside\assets\ui\`（先建好空資料夾與 README） |

### 現在使用者怎麼用（所以為什麼需要 UI）

```powershell
earside.exe doctor
earside.exe say "你好"
earside.exe --config local\real.toml chat
earside.exe calibrate --preset presets\demo-color.json
```

要背指令、要改 TOML。**UI 的目標就是這四件事都不用打指令。**

---

## 二、要設計的畫面（照優先序）

### 1. 主面板（最重要）

- 左側：陪伴狀態（待機／聽／想／說）、遊戲名稱、目前 preset、哨兵開關。
- 中間：大顆「開始陪伴 / 停止」、麥克風音量條、最近一句（她聽到什麼／她說了什麼）。
- 右側：快速設定（麥克風裝置、音量、字幕開關、哨兵靈敏度滑桿）。
- 底部：日誌（可收合），只顯示人類看得懂的字，不要 traceback。
- 尺寸：預設 960×640，可縮到 720×480；記住上次位置。

### 2. 設定頁（分頁）

| 分頁 | 欄位 | 對應設定 |
|---|---|---|
| 連線 | ASR／TTS／LLM／換嗓／vision 的 URL＋測試按鈕 | `[ports.*]` |
| 聲音 | 麥克風裝置、輸出裝置、音量、打斷開關 | `[audio]`、`[behavior]` |
| 字幕 | 字級、行數、位置（左下／中下／右下）、透明度、預覽 | `[subtitle]`、`[tuning]` |
| 哨兵 | 總開關、靈敏度、每個 region 的 interval、死亡判定速度 | `[sentinel]`、preset |
| 進階 | 其餘 `[tuning]`，用「這是什麼」小字說明 | `[tuning]` |

### 3. 校準頁（可先用現有 Tk，之後重畫）

- 上半：遊戲視窗截圖（等比縮放）。
- 操作：滑鼠拖一個框 → 命名（小地圖／名字／血量）→ 選規則（變化／顏色／blob／亮度／模板）。
- 右側：區域列表、即時預覽「現在 on/off」、存檔。
- 需要清楚地告訴使用者：**框越小越準、不要框到會一直動的特效**。

### 4. 字幕浮層（遊戲中）

- 圓角泡泡、9-slice、最大寬度 72% 螢幕、下方中央（可調）。
- 狀態：聽（小波形）／想（三點）／說（文字）。
- 淡入淡出 120ms；不要陰影太重、不要擋準星。
- 點擊穿透；永遠置頂；多螢幕要跟主要螢幕。

### 5. 托盤（關掉主面板後）

- 圖示：鯨魚娘頭像（16／32／48）。
- 選單：開始／停止陪伴、靜音、開啟面板、離開。
- 狀態用圖示顏色或小點表示（待機灰、聽藍、說綠）。

---

## 三、要交付的資產

| 資產 | 規格 | 備註 |
|---|---|---|
| App icon | 256×256 PNG＋SVG | 深色底可辨識 |
| 托盤 icon | 16／32／48 PNG | 小尺寸要清楚 |
| 鯨魚娘表情 | 待機／聽／想／說／死亡 5 張 | 半身，透明底，512×512 |
| 字幕泡泡 | 9-slice PNG（或 SVG） | 圓角 16px、深色 80% 透明 |
| 狀態圖示 | 麥克風、喇叭、眼睛、哨兵、齒輪 | 線性、2px、24×24 |
| 字體 | 中文：Noto Sans TC／思源黑體；數字可用 Inter | 字幕最少 28px |
| 色票 | 背景 #0F1419、面板 #171D24、主色 #4FA3FF、警告 #FFB020 | 深色為主 |

命名：`icon-app-256.png`、`bubble-9slice.png`、`mascot-listening.png`……
全部放 `assets\ui\`，不要散在工作區。

---

## 四、技術邊界（給前端／實作）

- 現在是 Python 3.12＋tkinter（字幕、校準）。**沒有** PySide／Electron。
- 建議 v1 用 **PySide6（Qt）** 重畫主面板與設定；核心邏輯（`src\earside\`）不要動，UI 只呼叫：
  - `core.config.load_config()`／寫回 TOML
  - `brain.live.LiveLoop`（開始／停止）
  - `eyes.sentinel.SentinelRunner`（狀態）
  - `bubble.client.OverlayClient`（字幕）
  - `eyes.calibrate`（校準）
- 執行緒：LiveLoop 在 asyncio；UI 用 Qt signal 接，不要直接碰 audio callback。
- 多螢幕／DPI 150% 一定要測；字幕用像素字級，不是 pt。
- 不要做：熱鍵注入、讀遊戲記憶體、繞反作弊。

---

## 五、交付格式

1. Figma（或同等）連結＋可編輯檔。
2. 匯出：每個畫面 2x PNG＋9-slice 圖＋icon SVG。
3. 一頁 spec：顏色、字級、間距、圓角、狀態變化。
4. 走查：主面板 960×640、設定 960×720、校準 1280×800、字幕 2560×1600 遊戲截圖上。

## 六、驗收（人類角度）

- 不開終端機也能：開程式 → 選麥克風 → 按開始 → 聽到她說話 → 關掉。
- 出錯時看得到「哪個端口沒開、怎麼開」，不是 traceback。
- 遊戲中主面板可完全隱藏，只剩托盤跟字幕。
