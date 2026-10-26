# earside（耳邊）

Windows 桌面陪玩引擎：用「區域」看螢幕、用「端口」接耳朵／嘴巴／大腦／眼睛，字幕浮在畫面上。
不注入遊戲、不讀記憶體、不模擬輸入。

> 早期版本。架構優先，參數都留在 `[tuning]`，之後可以慢慢調。

## 現在有什麼

- **聽**：麥克風 → Silero VAD（512@16k、soxr 抗混疊）→ ASR 端口
- **說**：LLM 串流 → 斷句 → TTS 端口 →（可選）換嗓 → 播放＋字幕
- **寫**：置頂、滑鼠穿透、per-monitor DPI aware 的字幕條
- **讀**：mss 擷取視窗 → preset 區域 → 哨兵規則（相對亮度比、顏色、blob、模板、變化；OCR 佔位）。有總開關與靈敏度，RTS／FPS 各自調。
- **一直聽**：`chat`（VAD onset 打斷、echo guard、短句合併）
- **可調參數**：`[tuning]`，見 [docs/TUNING.md](docs/TUNING.md)

## 安裝

Python 3.11+。

```powershell
pip install -e ".[core]"
```

ASR／TTS／LLM／換嗓都不內建，走本機 HTTP 端口（見下）。

## 快速開始

```powershell
python -m earside doctor
python -m earside say "你好"                       # Windows SAPI＋字幕
python -m earside listen --seconds 5 --no-asr      # 只測 VAD 切句
python -m earside listen --file speech.wav         # 離線切句＋ASR
python -m earside watch --preset presets/demo-color.json --seconds 5
```

`talk`／`chat` 需要 LLM／TTS／ASR 端口；`talk` 不支援 builtin SAPI（pyttsx3 與串流執行緒會卡死）。

## 端口（Ports）

核心只認合約，不認模型。實作可以放 `local/adapters/`（已 gitignore），`adapters/` 只放說明。

| 端口 | 端點 | 契約 |
|---|---|---|
| `asr` | `POST /stt` | multipart `audio`（wav）＋`lang` → `{"text": "...", "lang": "zh", "confidence": 0.9}` |
| `tts` | `POST /tts` | `{"text","voice","format":"wav"}` → `audio/wav`（建議 48k mono） |
| `voice` | `POST /voice` | multipart `audio`＋`pitch` → `audio/wav` |
| `llm` | `POST /v1/chat/completions` | OpenAI 相容，`stream: true` 回 SSE |
| `vision` | `POST /v1/chat/completions` | 同上，多模態 `image_url` |

合約細節在 [adapters/README.md](adapters/README.md)。

## 設定

複製 `config.example.toml` 成 `config.toml`。`doctor` 會印出目前生效的關鍵參數。
`[tuning]` 的每個值、單位、改了會怎樣，都在 [docs/TUNING.md](docs/TUNING.md)。
每段做了什麼、怎麼驗、踩過哪些坑，在 [docs/HANDOFF.md](docs/HANDOFF.md)。

## 測試

```powershell
python -m unittest discover -s tests
```

`test_capture` 會真的開記事本抓視窗，預設跳過；要跑設 `EARSIDE_CAPTURE_TEST=1`。

## 安全邊界

- 只做被動的事：擷取（mss）、聽麥克風、畫置頂視窗。
- 不注入 DLL、不讀遊戲記憶體、不模擬鍵鼠、不繞反作弊。
- 不保證每款遊戲／反作弊允許，使用前自己確認；截圖只送給你選的端口。
- 喇叭模式請把 `behavior.barge_in` 設 false（她會聽到自己）。

## License

MIT，見 [LICENSE](LICENSE)。
