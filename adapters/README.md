# 端口（Ports）

核心只認這裡的合約；換模型就是換一個本機 HTTP 服務。實作放 `local/adapters/`（gitignore），這個資料夾只放說明。

## ASR

```
POST /stt
Content-Type: multipart/form-data
  audio: utterance.wav（16k mono 佳）
  lang: zh

→ 200 {"text": "今天天氣很好", "lang": "zh", "confidence": 0.9}
```

## TTS

```
POST /tts
{"text": "今天天氣很好", "voice": "default", "format": "wav"}

→ 200 audio/wav
```

建議回 48kHz 單聲道 PCM16；核心會自己重取樣。

## 換嗓（可選）

```
POST /voice
Content-Type: multipart/form-data
  audio: tts.wav
  pitch: 0

→ 200 audio/wav
```

## LLM

OpenAI 相容：

```
POST /v1/chat/completions
{"model": "...", "messages": [{"role": "user", "content": "..."}], "stream": true}

→ text/event-stream
data: {"choices": [{"delta": {"content": "你"}}]}

data: [DONE]
```

## 視覺（可選）

同一支 `/v1/chat/completions`，訊息裡放 `image_url`（base64 data URL）。

## 最小實作建議

- 只綁 `127.0.0.1`。
- 一次一個請求（模型多半不是執行緒安全）。
- 失敗回 502，核心會降級。
