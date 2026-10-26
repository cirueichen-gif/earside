# 調參數（TUNING）

改 `config.toml` 的 `[tuning]`，**重啟生效**。`python -m earside doctor` 會印出目前生效的關鍵值。
程式裡的常數只是預設值；從程式碼找參數時，每個模組頂端有指路註解。

## 耳朵（VAD／ASR）

| 參數 | 預設 | 單位 | 改了會怎樣 | 什麼時候調 |
|---|---|---|---|---|
| `vad_threshold` | 0.5 | 機率 | 起句門檻。太高漏小聲；太低把雜音當人聲 | 常漏句→降；被雜音觸發→升 |
| `vad_pre_roll_s` | 0.30 | 秒 | 開頭緩衝，不然第一個字會被吃掉 | 覺得第一字不見→加大 |
| `vad_onset_frames` | 8 | 幀（32ms） | 連續幾幀人聲才算「開始講」。8＝250ms | 常被滑鼠／雜音打斷→加大 |
| `vad_hangover_s` | 1.00 | 秒 | 靜音多久算講完。**0.7 會把「我問說」「我起」切成兩半（07 實測）**，代價是每句多等 | 句子被切一半→加大；反應慢→減小 |
| `vad_min_speech_s` | 0.25 | 秒 | 太短丟掉（咳嗽、雜音）；seconds 已含 pre-roll | 短回覆被吞→減小 |
| `vad_max_utter_s` | 15.0 | 秒 | 單句硬切上限 | 長篇被切斷→加大 |
| `asr_timeout_s` | 30.0 | 秒 | ASR 端口逾時（冷啟動載模型約 13 秒） | 冷啟常失敗→加大 |

## 嘴巴（合併／斷句／TTS／播放）

| 參數 | 預設 | 單位 | 改了會怎樣 | 什麼時候調 |
|---|---|---|---|---|
| `merge_window_s` | 0.45 | 秒 | 短句合併窗；每一輪都多等這麼久 | 她太愛搶話→加大；覺得慢→減小 |
| `fillers` | 嗯恩啊喔哦欸呃唉齁嘿ㄟ | 字串 | 哪些純語氣詞不送進 LLM | 某個口頭禪被她忽略→拿掉那個字 |
| `sentence_max_len` | 42 | 字 | 一句最多幾個字，超過硬切 | 一句太長唸不完→減小 |
| `sentence_soft_len` | 24 | 字 | 多長開始用逗號切句 | 語感太碎→加大 |
| `sapi_rate` | 175 | SAPI 語速 | 她講話多快（只有 builtin 用） | 覺得太快／太慢 |
| `playback_samplerate` | 48000 | Hz | 播放取樣率；裝置不支援會開不起來 | 音訊錯誤→改 44100 |
| `max_turns` | 10 | 輪 | 記得幾輪對話（token 也會變多） | 覺得她忘太快→加大 |
| `overlay_chars_per_line` | 30 | 字 | 字幕每行幾個字 | 字幕太擠／太散 |

## 打斷（behavior）

| 參數 | 預設 | 單位 | 改了會怎樣 | 什麼時候調 |
|---|---|---|---|---|
| `barge_in` | true | bool | 她講話時你出聲就打斷 | **喇叭模式建議 false**（她會聽到自己，自己打斷自己） |
| `echo_guard_s` | 0.4 | 秒 | 她講完後多留的尾巴，用來丟掉自己的回音 | 她回自己的話→加大；正常接話被吞→減小 |

## 哨兵（sentinel）

| 參數 | 預設 | 單位 | 改了會怎樣 | 什麼時候調 |
|---|---|---|---|---|
| `sentinel.enabled` | true | bool | 總開關；false＝完全不看螢幕（`watch` 直接跳過） | 不想被看、或只想用聽／說 |
| `sentinel.sensitivity` | 1.0 | 0.25–4.0 | 越高越容易觸發（門檻變寬鬆） | 造型／特效一直誤報→調低；該報不報→調高 |

preset 也可以有自己的 `enabled`、`sensitivity`、`game_type`；單一區域的 `rule.sensitivity` 再覆蓋一次。
**RTS 這類 UI 動畫多的遊戲，建議 0.5–0.8**；FPS 可以 1.0 上下。先跑 `watch` 乾跑看事件量再調。

死亡判定的延遲也可以調：region 的 `rule.median_frames`（預設 5，越小越快但越容易被閃光騙）＋`consecutive`（預設 3）。200ms 間隔下，5＋3 大約 1.0 秒；改 3＋2 約 0.6 秒。

## 已知的坑

- **SAPI 不能用在 talk／chat**：pyttsx3 的訊息幫浦跟串流執行緒會卡死；`builtin` 只留給 `say`。
- **echo_guard 用「句子開始講的時間」判斷**，不是文字到達時間；改 `echo_guard_s` 只影響尾巴。
- **死亡判定約 1.0 秒**（5 幀中位數＋3 幀連續，200ms 間隔）；要更快就把 region 的 `interval_ms` 調小，但 CPU 會上升。
- **麥克風**：Windows 預設輸入常常是 Stereo Mix；這台要指定 `Realtek HD Audio Mic input`（config `[audio] input_device`）。
