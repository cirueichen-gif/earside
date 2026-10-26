# HANDOFF（交接）

> 每小塊一節，固定五欄：**做了什麼／怎麼驗／已知缺口／踩過的坑／下一步**。
> README 是「現在長怎樣」，TUNING 是「旋鈕在哪」，這份是「為什麼長這樣、哪裡痛」。

## 目前狀態

- 2026-10-26：P1a–P1d、P2 的讀（擷取／preset／規則／watch）、sentinel 開關與靈敏度完成。
- 41 個測試（4 個 capture 預設 skip）；public repo：https://github.com/cirueichen-gif/earside
- 下一段：P3 眼睛（vision）、校準精靈、LLM 串流真取消。

> 註：第一次公開上傳時把早期 commit 壓成一個 Initial，所以 P1a–P2 在 git 歷史裡看不出分段。之後每小塊一個 commit。

---

## P1a 骨架（2026-10-26）

**做了什麼**
- `core/`：config（TOML＋`[tuning]`）、事件匯流排、路徑。
- `ports/`：合約（asr／tts／voice／llm／vision）＋ HTTP／builtin 實作＋factory。
- `mouth/player.py`：PlaybackBridge（PortAudio callback 只做複製；中止用 flag，不重建 stream）。
- `bubble/`：字幕子進程（multiprocessing）＋click-through／DPI aware。
- `cli.py`：doctor／say／overlay-demo。

**怎麼驗**
- `doctor` 全綠；`say "測試，聽得到嗎？"` → tts ~460ms、播放 2.07s。
- 字幕截圖確認黑底白字、下方中央、滑鼠穿透（exstyle 0x80800a8）。

**已知缺口**
- builtin SAPI 不能用在 talk／chat（見坑 1、2）。
- TTS 每次仍會開 engine；之後可做常駐 worker。

**踩過的坑**
- 同步 `play()` 會凍結 event loop 1.0 秒；改 `play_async`（to_thread）。
- Tk 字級是 points，150% 縮放會爆版；改負數像素。

**下一步**：P1b。

---

## P1b 耳朵（2026-10-26）

**做了什麼**
- `ears/frames.py`：麥克風（裝置原生率→soxr→16k）＋檔案來源；`to_wav_bytes`。
- `ears/vad.py`：Silero VAD（512@16k）、pre-roll、hangover、onset 幀數、min/max 長度。
- `ears/listener.py`：背景執行緒跑 VAD＋ASR；`ready`／`error` 讓 CLI 大聲失敗。
- `cli.py listen`：`--file`／`--seconds`／`--no-asr`／`--dump`。

**怎麼驗**
- `listen --file test_speech.wav` → `[0.00-3.84] '今天天氣很好，這是一段測試語音。'`
- `listen --seconds 4` → 126 幀、dropped 0。
- 實測 12k 正弦 44.1k→16k：soxr rms 0.001（線性內插是 0.707）。

**已知缺口**
- ASR 在消費端同一條執行緒同步跑；ASR 慢時 queue 會滿、開始丟最舊（`drops` 有計數）。
- 沒有熱鍵（反作弊考量），裝置只能改 config／`--device`。

**踩過的坑**
- 44.1k→16k 線性內插會混疊（坑 3）；這台裝置直接要 16000 會 `Invalid device`。
- 麥克風預設輸入是 Stereo Mix，會把系統聲音當人聲（坑 6 的鄰居）。

**下一步**：P1c。

---

## P1c 嘴巴（2026-10-26）

**做了什麼**
- `brain/sentences.py`：串流斷句＋`speakable`（去標記／code／網址）。
- `brain/conversation.py`：LLM 串流（執行緒）→ 斷句 → TTS worker →（可選）換嗓 → 播放＋字幕；history／cancel／stats。
- `mouth/tts_worker.py`：TTS 專用執行緒（COM 綁在同一條）。
- `cli.py talk`：文字進、她回話。

**怎麼驗**
- 真實鏈（DSH→edge-tts→RVC）：`first_token=5239ms`、2 句、speak `[4468, 6786] ms`。
- 用 mock LLM 也能跑：`tests/_mock_llm.py`。

**已知缺口**
- LLM 串流打斷只停消費端，HTTP 仍讀到完、token 照燒（坑 11）。
- TTS 若是 builtin SAPI 會卡死（坑 1、2）。

**踩過的坑**
- pyttsx3 的 engine 綁執行緒；丟 `to_thread` 會卡 >90 秒。
- SAPI 的 `runAndWait` 需要 STA；worker 要 `CoInitializeEx(APARTMENTTHREADED)`。

**下一步**：P1d。

---

## P1d 一直聽（2026-10-26）

**做了什麼**
- `brain/live.py`：LiveLoop（listener→queue→Conversation）；filler filter、短句合併、VAD onset 打斷、echo window。
- `cli.py chat`：麥克風→大腦→嘴巴。

**怎麼驗**
- 真人 50 秒一輪：
  - 「嗯。」→「嗯。我在。」
  - 「啊。」→「快半夜了，你是睡不著還是不想睡。」
  - 「怎麼了？」「要寫作業。」→「哪門課的，要寫什麼。」
  - 「剛忙在寫作業。」→「講清楚了，我能幫的就幫。」
- 合併窗 0.45 秒；barge onset 8 幀＝250ms。

**已知缺口**
- 喇叭模式仍可能自打斷（echo guard 只是尾巴）；建議 `barge_in=false`。
- 打斷沒取消 LLM 串流（坑 11）。

**踩過的坑**
- echo guard 不能比「文字到達時間」；要用 `utt.wall_start`（句子開始講的時間）。
- 單幀 VAD 就 barge 會被滑鼠／特效切斷；改 onset 連續 8 幀。

**下一步**：P2。

---

## P2 讀（2026-10-26）

**做了什麼**
- `eyes/capture.py`：視窗尋找（EnumWindows）、DWM 客戶區、mss 擷取、ROI clamp；`crop_norm` 共用。
- `eyes/preset.py`：preset 載入／驗證（含 `game_type`／`enabled`／`sensitivity`）。
- `eyes/rules.py`：六種規則＋每區 state（時域中位數、滑動基準、consecutive）；靈敏度換算。
- `cli.py watch`：capture→preset→rules→事件；`--seconds`／`--save`／`--sensitivity`；多區共用一次 `grab()`。

**怎麼驗**
- Notepad 實抓：1904×1170、std 11.36、grab 25.8ms；ROI 正常。
- `tests/_color_window.py`＋`presets/demo-color.json`：6 秒 7 個 on/off。
- 41 tests（capture 那 4 個要 `EARSIDE_CAPTURE_TEST=1`）。

**已知缺口**
- 死亡判定實際約 1.0 秒（5 幀中位數＋3 幀連續），不是 0.3 秒（坑 10）。
- 被遮擋的視窗 mss 抓不到；字幕浮層壓在區域上會被拍進去（坑 9）。
- 校準精靈、觸發器接嘴巴還沒做。

**踩過的坑**
- WGC 未實作，`auto` 若 import 到 `windows_capture` 會每次 grab 都炸；改一率 mss。
- `capture` 測試會開記事本搶焦點；改預設 skip。

**下一步**：P3 眼睛（vision）／校準精靈。

---

## Sentinels 開關與靈敏度（2026-10-26）

**做了什麼**
- `[sentinel] enabled/sensitivity`；preset `enabled/sensitivity/game_type`；`rule.sensitivity` 可覆蓋。
- `example-rts.json`＋`presets/README.md`。
- `doctor` 印 sentinel；`watch --sensitivity`。

**怎麼驗**
- sensitivity 1.0／2.0／0.5、region override 共 5 個測試。
- `enabled=false` → `watch` 印訊息、exit 0、不抓圖。

**已知缺口**
- 靈敏度目前是「門檻縮放」，不是動態自適應；特效多的遊戲還是要人工調。

**下一步**：等真實遊戲 preset 回饋再調預設值。

---

## 坑表（最值錢）

已修：

| # | 坑 | 解法 |
|---|---|---|
| 1 | SAPI 的 COM 綁執行緒，跨執行緒呼叫卡死 | `mouth/tts_worker.py` 專用執行緒 |
| 2 | pyttsx3 不能跟串流同時跑 | `talk`／`chat` 拒絕 builtin TTS |
| 3 | 44.1k→16k 線性內插混疊 | 改 soxr 串流（12k 從 0.707→0.001） |
| 4 | Tk 字級是 points，150% 爆版 | 傳負數像素＋動態行高 |
| 5 | 同步播放凍結 event loop | `play_async`（to_thread） |
| 6 | ASR 冷啟動 12.8s > 10s timeout | timeout 30s＋`--preload` |
| 7 | WGC 未實作但 auto 會選它 | auto 一律 mss |
| 8 | 單幀 VAD 就打斷 | `vad_onset_frames=8`（250ms） |
| 9 | echo guard 用文字到達時間會誤殺 | 改用 `utt.wall_start` |

還沒修：

| # | 坑 | 影響 |
|---|---|---|
| 10 | 死亡判定約 1.0 秒 | 面板上「怎麼這麼慢」 |
| 11 | LLM 串流打斷沒真取消 | token 照燒 |
| 12 | mss 抓不到被遮擋視窗 | 字幕／其他視窗會入鏡 |
| — | 校準精靈未做 | 玩家得手改 JSON |

---

## 每段怎麼跑（開發者）

```powershell
pip install -e ".[core]"
python -m earside doctor
python -m unittest discover -s tests
```

真實端口（ASR／TTS／LLM／換嗓）放在 `local/adapters/`，不進 repo；合約見 `adapters/README.md`。
