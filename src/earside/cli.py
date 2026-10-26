"""CLI：doctor / say / overlay-demo / voices。"""

from __future__ import annotations

import argparse
import socket
import sys
import time
from urllib.parse import urlparse

from .core.config import find_config, load_config
from .ports.base import PortError
from .ports.factory import make_tts


def _ping(url: str, timeout: float = 0.3) -> bool:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _overlay_options(cfg: dict) -> dict:
    opts = dict(cfg.get("subtitle", {}))
    opts["chars_per_line"] = int(cfg["tuning"].get("overlay_chars_per_line", 30))
    return opts


def cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    config_path = find_config(args.config)
    ok = True

    print(f"config        ok    {config_path or '預設值（沒有 config.toml）'}")
    t = cfg["tuning"]
    print(
        "tuning        ok    "
        f"vad={t['vad_threshold']} onset={t['vad_onset_frames']}幀 "
        f"hangover={t['vad_hangover_s']}s merge={t['merge_window_s']}s "
        f"sr={t['playback_samplerate']}"
    )

    # TTS
    tts_cfg = cfg["ports"]["tts"]
    try:
        # 注意：這裡故意用臨時 SapiTTS。SAPI engine 綁在建立它的執行緒上，
        # 不要跟之後的 TTS worker 共用實例，不然 worker 會卡死。
        tts = make_tts(tts_cfg, rate=int(cfg["tuning"].get("sapi_rate", 175)))
        t0 = time.perf_counter()
        wav = tts.synthesize("測試")
        dt = (time.perf_counter() - t0) * 1000
        print(f"tts           ok    {dt:.0f} ms，{len(wav)} bytes（{tts_cfg.get('kind')}）")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"tts           FAIL  {exc}")

    # 音訊輸出
    try:
        import sounddevice as sd

        device = sd.query_devices(kind="output")
        print(f"audio         ok    {device['name']} @ {int(device['default_samplerate'])} Hz")
        in_dev = sd.query_devices(kind="input")
        configured = cfg.get("audio", {}).get("input_device", "")
        print(f"mic           ok    預設：{in_dev['name']}")
        if configured:
            from .ears.frames import resolve_device

            resolved = resolve_device(configured)
            name = (
                sd.query_devices(resolved)["name"]
                if isinstance(resolved, int)
                else str(resolved)
            )
            print(f"mic           ok    設定：{name}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"audio         FAIL  {exc}")

    # 耳朵：VAD 模型
    try:
        from .ears.vad import SileroVAD

        t0 = time.perf_counter()
        SileroVAD()
        print(f"vad           ok    Silero {1000 * (time.perf_counter() - t0):.0f} ms（512@16k）")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"vad           FAIL  {exc}")

    # 字幕環境（不開視窗，say 才是真的測）
    try:
        import tkinter

        print(f"overlay       ok    tkinter {tkinter.TkVersion}（say 會實際開一次）")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"overlay       FAIL  {exc}")

    # 端口連通性（只探 TCP，不送請求）
    skipped: list[str] = []
    for name, cfg_key in (("asr", "asr"), ("llm", "llm")):
        pc = cfg["ports"][cfg_key]
        url = pc.get("url") or pc.get("base_url") or ""
        if pc.get("kind") == "http" and url:
            if _ping(url):
                print(f"{name:<13} ok    {url}")
            else:
                skipped.append(name)
                print(f"{name:<13} skip  {url}（沒開，之後再接）")

    if not ok:
        print("\ndoctor: 有紅字，先修")
    elif skipped:
        print(f"\ndoctor: 全綠（{'／'.join(skipped)} 未接，skip）")
    else:
        print("\ndoctor: 全綠")
    return 0 if ok else 1


def cmd_say(args: argparse.Namespace) -> int:
    import asyncio

    cfg = load_config(args.config)
    return asyncio.run(_say_async(cfg, args.text, args.no_subtitle))


async def _say_async(cfg: dict, text: str, no_subtitle: bool) -> int:
    import asyncio

    from .bubble.client import OverlayClient
    from .mouth.player import PlaybackBridge

    tuning = cfg["tuning"]
    tts = make_tts(cfg["ports"]["tts"], rate=int(tuning.get("sapi_rate", 175)))
    overlay = OverlayClient(_overlay_options(cfg)) if not no_subtitle else None
    player = PlaybackBridge(samplerate=int(tuning.get("playback_samplerate", 48000)))

    try:
        t0 = time.perf_counter()
        # SAPI 的 COM 物件不能跨執行緒；TTS 先留在呼叫端（約 0.25s）。
        # 下一小塊會把 TTS 收進自己的 worker 執行緒，由那個執行緒建 engine。
        wav = tts.synthesize(text)
        t1 = time.perf_counter()
        if overlay:
            overlay.show(text)
        duration = await player.play_async(wav)
        t2 = time.perf_counter()
        print(
            f"tts {1000 * (t1 - t0):.0f} ms ｜ 播放 {duration:.2f}s ｜ 總 {1000 * (t2 - t0):.0f} ms"
        )
        if overlay:
            await asyncio.sleep(1.2)  # 播完先留一下，再淡出
            overlay.hide()
            await asyncio.sleep(0.4)
    except (PortError, Exception) as exc:  # noqa: BLE001
        print(f"say 失敗：{exc}", file=sys.stderr)
        return 1
    finally:
        player.close()
        if overlay:
            overlay.close()
    return 0


def cmd_overlay_demo(args: argparse.Namespace) -> int:
    from .bubble.client import OverlayClient

    cfg = load_config(args.config)
    overlay = OverlayClient(_overlay_options(cfg))
    try:
        overlay.show(args.text)
        time.sleep(args.seconds)
        overlay.hide()
    finally:
        overlay.close()
    return 0


def cmd_voices(args: argparse.Namespace) -> int:
    import pyttsx3

    engine = pyttsx3.init()
    for voice in engine.getProperty("voices"):
        print(f"{voice.id}\n    {voice.name}")
    return 0


def cmd_listen(args: argparse.Namespace) -> int:
    from .ears.listener import Listener, transcribe_file
    from .ports.factory import make_asr

    cfg = load_config(args.config)
    tuning = cfg["tuning"]
    asr = (
        None
        if args.no_asr
        else make_asr(
            cfg["ports"]["asr"], timeout=float(tuning.get("asr_timeout_s", 30.0))
        )
    )

    if args.file:
        rows = transcribe_file(args.file, asr, args.max_seconds, tuning=tuning)
        for row in rows:
            print(
                f"[{row['start']:.2f}-{row['end']:.2f}] {row['text']!r}",
                flush=True,
            )
        print(f"utterances={len(rows)}", file=sys.stderr)
        return 0

    def on_text(text: str, utt: dict) -> None:
        print(f"[{utt['seconds']:.2f}s rms={utt.get('rms', 0):.3f}] {text}", flush=True)

    listener = Listener(
        asr,
        on_text=on_text,
        device=args.device or cfg.get("audio", {}).get("input_device") or None,
        dump_dir=args.dump,
        tuning=tuning,
    )
    listener.start()
    if not listener.ready.wait(timeout=20.0):
        print("耳朵起不來：VAD／麥克風 20 秒沒有回應", file=sys.stderr)
        listener.stop()
        return 1
    if listener.error:
        print(f"耳朵起不來：{listener.error}", file=sys.stderr)
        listener.stop()
        return 1
    print("聽中… Ctrl+C 停", file=sys.stderr)
    try:
        if args.seconds:
            time.sleep(args.seconds)
        else:
            while True:
                time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
    if listener.error:
        print(f"listener error: {listener.error}", file=sys.stderr)
        return 1
    print(f"listener: {listener.stats}", file=sys.stderr)
    return 0


def cmd_talk(args: argparse.Namespace) -> int:
    import asyncio
    from pathlib import Path

    from .brain.conversation import Conversation
    from .bubble.client import OverlayClient
    from .core.paths import project_root
    from .mouth.player import PlaybackBridge
    from .ports.factory import make_llm, make_tts, make_voice

    cfg = load_config(args.config)
    tuning = cfg["tuning"]
    if cfg["ports"]["tts"].get("kind") == "builtin":
        print(
            "talk 不支援 builtin SAPI（串流時 pyttsx3 會卡）；請用 http TTS，"
            "例如 edge-tts 轉接器 127.0.0.1:8803。",
            file=sys.stderr,
        )
        return 1
    llm = make_llm(cfg["ports"]["llm"])
    tts = make_tts(cfg["ports"]["tts"], rate=int(tuning.get("sapi_rate", 175)))
    voice = make_voice(cfg["ports"].get("voice", {}))
    overlay = (
        OverlayClient(_overlay_options(cfg)) if not args.no_subtitle else None
    )
    player = PlaybackBridge(samplerate=int(tuning.get("playback_samplerate", 48000)))

    persona = None
    persona_path = Path(cfg["app"].get("persona", ""))
    if not persona_path.is_absolute():
        persona_path = project_root() / persona_path
    if persona_path.is_file():
        persona = persona_path.read_text(encoding="utf-8")

    conv = Conversation(
        llm,
        tts,
        player,
        voice=voice,
        overlay=overlay,
        persona=persona,
        max_turns=int(tuning.get("max_turns", 10)),
        sentence_max_len=int(tuning.get("sentence_max_len", 42)),
        sentence_soft_len=int(tuning.get("sentence_soft_len", 24)),
    )
    try:
        asyncio.run(conv.reply(args.text))
        first = conv.stats["first_token_ms"]
        print(
            f"first_token={first:.0f} ms ｜ sentences={conv.stats['sentences']} ｜ "
            f"speak={[round(x) for x in conv.stats['speak_ms']]} ms"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"talk 失敗：{exc}", file=sys.stderr)
        return 1
    finally:
        conv.close()
        player.close()
        if overlay:
            overlay.close()
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    import asyncio
    from pathlib import Path

    from .brain.conversation import Conversation
    from .brain.live import LiveLoop
    from .bubble.client import OverlayClient
    from .core.paths import project_root
    from .ears.listener import Listener
    from .mouth.player import PlaybackBridge
    from .ports.factory import make_asr, make_llm, make_tts, make_voice

    cfg = load_config(args.config)
    tuning = cfg["tuning"]
    if cfg["ports"]["tts"].get("kind") == "builtin":
        print("chat 不支援 builtin SAPI；請用 http TTS。", file=sys.stderr)
        return 1

    llm = make_llm(cfg["ports"]["llm"])
    tts = make_tts(cfg["ports"]["tts"], rate=int(tuning.get("sapi_rate", 175)))
    asr = make_asr(
        cfg["ports"]["asr"], timeout=float(tuning.get("asr_timeout_s", 30.0))
    )
    voice = make_voice(cfg["ports"].get("voice", {}))
    overlay = OverlayClient(_overlay_options(cfg)) if not args.no_subtitle else None
    player = PlaybackBridge(samplerate=int(tuning.get("playback_samplerate", 48000)))

    persona = None
    persona_path = Path(cfg["app"].get("persona", ""))
    if not persona_path.is_absolute():
        persona_path = project_root() / persona_path
    if persona_path.is_file():
        persona = persona_path.read_text(encoding="utf-8")

    conv = Conversation(
        llm,
        tts,
        player,
        voice=voice,
        overlay=overlay,
        persona=persona,
        max_turns=int(tuning.get("max_turns", 10)),
        sentence_max_len=int(tuning.get("sentence_max_len", 42)),
        sentence_soft_len=int(tuning.get("sentence_soft_len", 24)),
        on_speak=lambda text: print(f"[say] {text}", flush=True),
    )
    listener = Listener(
        asr,
        device=args.device or cfg.get("audio", {}).get("input_device") or None,
        tuning=tuning,
    )
    live = LiveLoop(
        conv,
        listener,
        barge_in=bool(cfg["behavior"].get("barge_in", True)),
        echo_guard_s=float(cfg["behavior"].get("echo_guard_s", 0.4)),
        merge_window_s=float(tuning.get("merge_window_s", 0.45)),
        fillers=set(str(tuning.get("fillers", ""))),
    )
    try:
        asyncio.run(live.run(seconds=args.seconds or None))
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"chat 失敗：{exc}", file=sys.stderr)
        return 1
    finally:
        listener.stop()
        conv.close()
        player.close()
        if overlay:
            overlay.close()
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    import json
    import time
    from pathlib import Path

    from .eyes.capture import CaptureSession, crop_norm
    from .eyes.preset import load_preset
    from .eyes.rules import RuleEngine

    cfg = load_config(args.config)
    preset = load_preset(args.preset or cfg["app"]["preset"])
    regex = args.window or preset.match.get("window_title_regex")
    if not regex:
        print("preset 沒有 window_title_regex，請用 --window 指定", file=sys.stderr)
        return 1

    capture = CaptureSession(
        regex, backend=str(cfg.get("capture", {}).get("backend", "auto"))
    )
    engine = RuleEngine(preset)
    states = {region.name: False for region in preset.regions}
    due = {region.name: 0.0 for region in preset.regions}
    save_dir = Path(args.save) if args.save else None
    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
    saved: set[str] = set()

    started = time.monotonic()
    deadline = started + args.seconds if args.seconds else None
    try:
        while True:
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                break
            frame = None
            for region in preset.regions:
                if now < due[region.name]:
                    continue
                due[region.name] = now + region.interval_ms / 1000
                if frame is None:
                    frame = capture.grab()  # 多區共用一次抓圖
                roi = crop_norm(frame, region.rect)
                if save_dir is not None and region.name not in saved:
                    import cv2

                    cv2.imwrite(str(save_dir / f"{region.name}.png"), roi)
                    saved.add(region.name)
                result = engine.evaluate(region.name, roi)
                if result["on"] != states[region.name]:
                    states[region.name] = result["on"]
                    print(
                        json.dumps(
                            {
                                "event": f"{region.name}.{'on' if result['on'] else 'off'}",
                                "score": round(result["score"], 3),
                                "metrics": result["metrics"],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
            time.sleep(0.02)
    except Exception as exc:  # noqa: BLE001
        print(f"watch 失敗：{exc}", file=sys.stderr)
        return 1
    finally:
        capture.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="earside", description="耳邊：陪玩引擎")
    parser.add_argument("--config", default=None, help="config.toml 路徑")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="檢查設定、TTS、音訊、字幕").set_defaults(
        func=cmd_doctor
    )

    say = sub.add_parser("say", help="念一句話＋字幕（最小垂直切片）")
    say.add_argument("text")
    say.add_argument("--no-subtitle", action="store_true")
    say.set_defaults(func=cmd_say)

    demo = sub.add_parser("overlay-demo", help="只測字幕浮層")
    demo.add_argument("text", nargs="?", default="字幕測試")
    demo.add_argument("--seconds", type=float, default=4.0)
    demo.set_defaults(func=cmd_overlay_demo)

    sub.add_parser("voices", help="列出 SAPI 聲音").set_defaults(func=cmd_voices)

    listen = sub.add_parser("listen", help="聽：麥克風或 wav → VAD → ASR")
    listen.add_argument("--file", default=None, help="離線 wav 路徑")
    listen.add_argument("--seconds", type=float, default=0.0, help="麥克風跑幾秒（0=一直跑）")
    listen.add_argument("--max-seconds", type=float, default=None, help="--file 只讀前幾秒")
    listen.add_argument("--no-asr", action="store_true", help="只切句，不轉文字")
    listen.add_argument("--device", default=None, help="音訊輸入裝置（名稱或 index）")
    listen.add_argument("--dump", default=None, help="把每句話存成 wav（除錯用）")
    listen.set_defaults(func=cmd_listen)

    talk = sub.add_parser("talk", help="文字進、她回話（LLM→TTS→播放＋字幕）")
    talk.add_argument("text")
    talk.add_argument("--no-subtitle", action="store_true")
    talk.set_defaults(func=cmd_talk)

    chat = sub.add_parser("chat", help="一直聽：麥克風→大腦→嘴巴")
    chat.add_argument("--seconds", type=float, default=0.0, help="跑幾秒（0=一直跑）")
    chat.add_argument("--no-subtitle", action="store_true")
    chat.add_argument("--device", default=None, help="音訊輸入裝置（名稱或 index）")
    chat.set_defaults(func=cmd_chat)

    watch = sub.add_parser("watch", help="看螢幕：capture→區域→規則→事件（乾跑）")
    watch.add_argument("--preset", default=None)
    watch.add_argument("--window", default=None, help="覆蓋 preset 的視窗標題 regex")
    watch.add_argument("--seconds", type=float, default=0.0, help="跑幾秒（0=一直跑）")
    watch.add_argument("--save", default=None, help="把每個區域第一幀存成 png")
    watch.set_defaults(func=cmd_watch)
    return parser


def main(argv: list[str] | None = None) -> int:
    import multiprocessing

    multiprocessing.freeze_support()
    args = build_parser().parse_args(argv)
    return args.func(args)
