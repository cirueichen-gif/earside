# HANDOFF（交接）

> 每小塊一節，固定五欄：**做了什麼／怎麼驗／已知缺口／踩過的坑／下一步**。
> README 是「現在長怎樣」，TUNING 是「旋鈕在哪」，這份是「為什麼長這樣、哪裡痛」。

## 目前狀態

- 2026-10-26：P1a–P1d、P2 的讀（擷取／preset／規則／watch）、sentinel 開關與靈敏度完成。
- 2026-10-27：P2 收尾（哨兵 runner、觸發器、校準 CLI）、P3（合圖／預算／Eye、主動／戰鬥、vision 接事件、短句庫）、P4 打包腳本與 CI。
- **MVP 完成、可交接**：73 個測試（4 個 capture 預設 skip）；**exe 已實建 214 MB**（`dist/earside/earside.exe`，doctor 全綠、`say` 正常）。
- 未完成（不是架構問題，是環境／需求）：真實 vision 端口沒實跑（要金鑰）、exe 的 chat 還沒接真 adapters 實跑、校準 UI 只做過開啟/關閉 smoke。
- **GitHub 未推**（魚片交代等他叫）；本機變更已 commit 在 main。
- 下一段：拿真遊戲 preset 校準、接 vision 端口、用 exe 跑一次完整 chat。

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

## 校準精靈（2026-10-27）

**做了什麼**
- `eyes/calibrate.py`：`normalize_rect`（拖曳→0–1）、`build_preset`、`save_preset`、`run_editor`（Tk：抓視窗截圖、拖框、命名、選 rule、存 preset）。
- `tests/test_calibrate.py`：純函式 round-trip；不在測試裡開視窗。

**怎麼驗**
- 全套 60 tests（含 calibrate）。
- UI 尚未由魚片手動跑過（agent 只驗了 import 與純函式）。

**已知缺口**
- 還沒接 `earside calibrate` CLI 子命令。
- UI 手動 smoke（Notepad 框選→存檔→load_preset）待做。

**踩過的坑**
- 交來時 `build_preset` 少一個括號（SyntaxError），已修。

**下一步**：接 CLI、實際框一次存檔。

---

## P3 視覺（起頭，2026-10-27）

**做了什麼**
- `eyes/vision.py`：`compose_frame`（主畫面＋ROI 標籤合成 JPEG）、`VisionBudget`（每分／每小時）、`Eye`（預算＋client＋`last_error`）。

**怎麼驗**
- 合成圖／預算／假 client 測試；6 個瘦高 ROI 的下方版面回歸測試。
- 全套 60 tests。

**已知缺口**
- 還沒接 CLI／config／trigger；真正的 vision 端口未接。
- `Eye.describe()` 是同步，接事件迴圈要丟 thread。

**下一步**：接到 `watch`／`chat` 的事件，config `ports.vision` 生效。

**後續（同日）**
- 已接：`chat` 在 trigger 帶 `vision: true` 時，用 `SentinelRunner.last_frame` ＋ `Eye` 描述，併進 LLM prompt；`ports.vision` 的 enabled／預算接進 config。
- 驗證：假 Eye 回「你在倉庫補彈」，prompt 有那句話；68 tests。
- 還沒：真的 vision 端口（要金鑰）沒實跑；`Eye.describe` 用 `to_thread` 丟出去了。

---

## P2 收尾：哨兵 runner＋觸發器（2026-10-27）

**做了什麼**
- `eyes/sentinel.py`：`SentinelRunner.poll()`（一輪共用一次 grab、只回狀態變化）＋ `run()` 背景迴圈。
- `brain/triggers.py`：事件→動作，支援冷卻、`max_per_min`、`max_per_hour`、`skip_if_speaking`。
- `chat`：哨兵在背景執行緒跑；事件→觸發器→`llm` 動作會主動回一句（`linebank` 目前只印訊息，等 runtime）。
- `earside calibrate` 子命令接上校準精靈。

**怎麼驗**
- `SentinelRunner` 假擷取＋`RuleEngine`：第一幀不發、變了才 on、再變回 off。
- `TriggerEngine`：冷卻、每分上限、每小時上限（3700 秒後恢復）、說話中跳過。
- 全套 65 tests。

**已知缺口**
- 短句庫 runtime 還沒接（`linebank` 動作只印 log）。
- vision 還沒接事件；沉默／戰鬥模式還沒做。

**踩過的坑**
- `max_per_hour` 一開始只留 60 秒 deque，等於被靜默忽略；已補 `_hour_calls`。

**下一步**：短句庫 runtime、vision 動作、沉默／戰鬥。

---

## P3 主動與戰鬥（2026-10-27）

**做了什麼**
- `brain/live.py`：沉默 `silence_s`（預設 240s）→ 主動找話，每小時上限；畫面大變（`diff_ratio ≥ 0.25`）進戰鬥模式 45 秒，戰鬥中不主動、哨兵也不主動講。
- `chat` 把 `behavior.silence_s`／`max_proactive_per_hour`／`combat_exit_s` 接進來。

**怎麼驗**
- 假 conversation：沉默 241s 觸發一次、第二次被 rate limit 擋；戰鬥中 `_maybe_proactive` 不呼叫。
- 全套 67 tests。

**已知缺口**
- 主動台詞還是走 LLM；等短句庫 runtime 後，戰鬥中要能只播預錄。
- 「戰鬥模式」目前只看哨兵 `change` 的 `diff_ratio`，沒有真的看主畫面；RTS 這類小變化可能不會進戰鬥。

**下一步**：短句庫、用主畫面變化判斷戰鬥。

---

## 短句庫（2026-10-27）

**做了什麼**
- `tools/lines_build.py`：`presets/<dir>/lines/*.txt` → 每句呼叫 TTS → `cache/lines/<hash>.wav`＋`manifest.json`；失敗繼續、第二次跳過已完成。
- `brain/linebank.py`：runtime 讀 manifest（沒有就掃 hash 檔）、`pick(bank)` 輪替。
- `chat`：trigger `source=linebank` 時直接播預錄 wav＋字幕，不合成、不燒 token。

**怎麼驗**
- 4 個短句庫測試（key 穩定、註解跳過、partial success、runtime 輪替）；73 tests。

**已知缺口**
- 只支援 `presets/<dir>/lines/` 這個目錄結構；沒有 UI。
- 還沒用真 TTS 建一整包（測試用 fake）。

**下一步**：拿真 TTS 建一次 death／minimap 短句。

---

## P4 打包（2026-10-27）

**做了什麼**
- `earside.spec`（PyInstaller onedir）、`scripts/build.ps1`、`.github/workflows/ci.yml`、`docs/PACKAGING.md`。

**怎麼驗**
- spec 語法檢查、CI YAML 檢查。
- **已實建**：`dist/earside/earside.exe` 214 MB；`doctor` 全綠、`say` 2.07 秒正常；VAD 在冷凍環境走 ONNX（273 ms）。

**已知缺口**
- exe 的 `chat` 還沒用真 adapters 實跑（需要你起四個端口）。
- CI 還沒在 GitHub 上跑過（今晚不推）。
- 模型（ASR／RVC）不進 exe，文件已寫。

**下一步**：用 exe 跑一次完整 chat。

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
| 10 | LLM 打斷後 worker 卡在讀取 | cancel 關 response＋`reply` 用 `wait_for(0.1)` 交還控制；worker 可能晚一個 chunk 才結束（有限） |
| 11 | vision 下方版面越界 | `combined_w` 補 8px 間距＋回歸測試 |
| 12 | vision 大圖可能 >5MB | `compose_frame` 加上限，超過就縮圖／降品質重編 |
| 13 | 短句庫每小時上限被忽略 | `TriggerEngine` 補 `_hour_calls` |
| 14 | `linebank` 只有 log、沒真的播 | 接 `brain/linebank.py`＋`Conversation.play_wav` |

還沒修：

| # | 坑 | 影響 |
|---|---|---|
| 15 | 死亡判定約 1.0 秒 | 面板上「怎麼這麼慢」 |
| 16 | mss 抓不到被遮擋視窗 | 字幕／其他視窗會入鏡 |
| 17 | vision 端口沒實跑 | 只有假 client 測試 |
| 18 | 校準 UI 未手動驗 | 玩家可能卡在介面 |
| 19 | exe 未實建 | P4 只到腳本層 |

---

## 每段怎麼跑（開發者）

```powershell
pip install -e ".[core]"
python -m earside doctor
python -m unittest discover -s tests
```

真實端口（ASR／TTS／LLM／換嗓）放在 `local/adapters/`，不進 repo；合約見 `adapters/README.md`。
