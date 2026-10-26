# PACKAGING（打包與發布說明）

本文檔記錄 `earside`（Windows 陪玩引擎）的 PyInstaller 打包流程、體積預期、系統安全機制（SAC / SmartScreen）因應方式、模型管理策略與 Release 發布指引。

---

## 1. 快速開始（建置指南）

### 前置條件
- Windows 10 / 11 64-bit
- Python 3.11+（建議 3.12）
- 已安裝專案依賴與 PyInstaller：
  ```powershell
  pip install -e ".[core]"
  pip install pyinstaller
  ```

### 執行打包
專案提供自動化 PowerShell 打包腳本 `scripts/build.ps1`：

```powershell
# 完整建置：執行單元測試 -> PyInstaller 打包
powershell -ExecutionPolicy Bypass -File scripts/build.ps1

# 清理舊產物並打包
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -Clean

# 跳過測試直接打包
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -SkipTests
```

產物將輸出至：
`dist/earside/`（onedir 模式，主執行檔為 `dist/earside/earside.exe`）。

### 實測（2026-10-27）
- PyInstaller 6.22.3、Python 3.12，建置約 50 秒。
- **`dist` 214 MB**（spec 砍掉 CUDA/TensorRT DLL；沒砍的話 1.8 GB）。
- `earside.exe doctor` 全綠（asr／llm skip），`say "測試"` 正常出聲＋字幕。
- 冷凍環境沒有 torch：VAD 自動走 `models/silero_vad.onnx`（onnxruntime CPU，273 ms）。
- 入口用 `launcher.py` 絕對 import；直接拿 `src/earside/__main__.py` 當 entry 會相對 import 失敗。
- exe 預設載入 `_internal/config.example.toml`（SAPI）。要聊天／接自己的端口，用
  `earside.exe --config <你的 config.toml> chat`，或把 config 放進 `_internal/`。

---

## 2. 體積預期與排除策略

PyInstaller 採用 `onedir` 模式而非 `onefile`，原因在於：
1. `onefile` 每次啟動需在 `%TEMP%` 解壓縮數百 MB 資料，增加 3–8 秒啟動延遲。
2. `onedir` 利於本地替換配置與更新。

### 體積構成預期
- **總目錄大小**：約 **180 MB – 260 MB**。
- **主要體積貢獻**：
  - `onnxruntime` + `opencv-python-headless`：約 120–160 MB。
  - `numpy` + 音訊相關 C 擴展庫（`soundfile`、`sounddevice`、`soxr`）：約 40–60 MB。
  - Python 執行時與標準庫：約 20–30 MB。

### 排除項目（Excludes）
`earside.spec` 明確排除了未使用的重型科學運算依賴，防止體積暴增至數 GB：
- `matplotlib`、`scipy`、`pandas`
- `torch`、`torchvision`、`torchaudio`（VAD 採用 onnxruntime 推理，不依賴完整 PyTorch）
- `IPython`、`jupyter`、`pytest`

---

## 3. SAC 與 SmartScreen 警告因應

### 核心原則：開發者本機原始碼跑，exe 給外部使用者

本機 Windows 若啟用了 **Smart App Control (SAC)** 或嚴格的 **Windows Defender SmartScreen**：
- 未經 EV 代碼簽名（Code Signing Certificate）自編譯的 exe 會被系統直接攔截封鎖（提示「Smart App Control 已封鎖此應用程式」）。
- **因此：**
  - **開發者本機開發／使用**：強烈建議直接透過原始碼與虛擬環境執行：
    ```powershell
    python -m earside doctor
    python -m earside chat
    ```
  - **產物 exe**：主要用於分發給未開啟 SAC 的使用者、或搭配專用簽章流程發布。

### 外部使用者若遇到 SmartScreen 提示
- 若未購買簽章憑證，使用者首次執行時會出現「Windows 已保護您的電腦」藍色彈窗。
- 點選「其他資訊」→「仍要執行」。

---

## 4. 模型與資源管理（模型不進 exe）

本專案遵循「**引擎與模型權重分離**」原則：
- **隨 exe 打包進去（Datas）**：
  - `personas/`：預設人設 markdown 檔案。
  - `presets/`：遊戲色彩校準預設 JSON。
  - `config.example.toml`：預設範例配置。
- **絕不打包進 exe（使用者本地存放）**：
  - **語音模型 / 換嗓權重**：RVC 模型權重（`.pth`、`.index`）、CosyVoice 等重型檔案動輒 100MB–2GB，應存放於 `local/` 或由 adapter 獨立載入。
  - **Silero VAD ONNX 模型**：由 `silero-vad` 套件快取或外部下載，避免重複膨脹打包體積。
  - **真實適配器端口配置**：`local/adapters/` 與包含 API Token 的 `config.toml` 均在 `.gitignore` 中，打包時絕不外洩。

---

## 5. Release 發布流程

當準備發布新版本時：

1. **版本號確認**：更新 `pyproject.toml` 中的 `version`。
2. **本機打包與測試**：
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -Clean
   ```
3. **驗證產物目錄完整性**：
   檢查 `dist/earside/` 下應包含：
   - `earside.exe`
   - `personas/`
   - `presets/`
   - `config.example.toml`
   - 各類 `.dll` 與 `_internal/` 依賴庫
4. **打包壓縮**：
   將 `dist/earside/` 目錄壓縮為 `earside-v<VERSION>-windows-x64.zip`。
5. **發布 GitHub Release**：
   - 建立對應版本 Tag（例如 `v0.1.0`）。
   - 上傳 `.zip` 產物至 GitHub Releases。
   - 附上 Release Notes、MD5/SHA256 校驗碼與 SmartScreen 解除指引。
