# -*- coding: utf-8 -*-
"""auto_clicker · 无头自检（不创建 tkinter 界面，不产生真实鼠标点击）。

验证两件事：
1. core.config 的默认值合并、脏数据回落、JSON 保存/读取往返；
2. core.clicker.ClickEngine 的次数模式、停止、固定坐标/按键参数。
   点击函数被打桩替换，只验证引擎状态机，不会真的移动鼠标。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core import config as cfg          # noqa: E402
from core import clicker as clicker_mod  # noqa: E402


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class StubPyAutoGUI:
    """记录调用、不触碰真实鼠标的 pyautogui 替身。"""

    FailSafeException = RuntimeError

    def __init__(self):
        self.clicks = []

    def click(self, x=None, y=None, button="left"):
        self.clicks.append((x, y, button))

    def doubleClick(self, button="left"):
        self.clicks.append(("double", None, button))


def check_settings() -> dict:
    with tempfile.TemporaryDirectory(prefix="auto_clicker_selfcheck_") as tmp:
        missing = os.path.join(tmp, "missing.json")
        defaults = cfg.load_settings(missing)
        check(defaults == cfg.DEFAULTS, "配置文件缺失时未回退默认值")
        check(defaults is not cfg.DEFAULTS, "缺失时返回了默认字典本体，存在被污染风险")

        dirty_path = os.path.join(tmp, "dirty.json")
        with open(dirty_path, "w", encoding="utf-8") as fh:
            json.dump({
                "interval_ms": "250",       # 字符串数字 → int
                "button": "right",
                "jitter_ms": "oops",        # 非法 → 回退默认
                "unknown_key": 1,
            }, fh, ensure_ascii=False)

        loaded = cfg.load_settings(dirty_path)
        check(loaded["interval_ms"] == 250 and isinstance(loaded["interval_ms"], int),
              f"interval_ms 类型校正失败: {loaded['interval_ms']!r}")
        check(loaded["button"] == "right", "合法字段未生效")
        check(loaded["jitter_ms"] == cfg.DEFAULTS["jitter_ms"],
              "非法字段未回退默认值")
        check("unknown_key" not in loaded, "未知字段未被丢弃")

        cfg.save_settings(dirty_path, loaded)
        with open(dirty_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        check(raw == loaded, "save_settings 写出的 JSON 与内存不一致")
        check(cfg.load_settings(dirty_path) == loaded, "配置保存/读取往返不一致")
        return loaded


def make_engine(**overrides):
    engine = clicker_mod.ClickEngine()
    engine.interval_ms = 1
    engine.jitter_ms = 0
    for key, value in overrides.items():
        setattr(engine, key, value)
    return engine


def check_click_engine(stub: StubPyAutoGUI) -> int:
    clicker_mod.pyautogui = stub

    # 1) 次数模式：点满 5 次自动停止
    engine = make_engine(repeat_mode="count", repeat_count=5, button="right")
    engine.start()
    check(wait_until(lambda: not engine.is_running), "次数模式未在超时内停止")
    check(engine.clicks_done == 5, f"次数模式点击数错误: {engine.clicks_done}")
    check(len(stub.clicks) == 5, f"打桩点击调用次数错误: {len(stub.clicks)}")
    check(all(call[2] == "right" for call in stub.clicks), "鼠标按键参数未透传")

    # 2) 无限模式 + stop()：点击应停止且计数不再增长
    stub.clicks.clear()
    engine2 = make_engine(repeat_mode="infinite")
    engine2.start()
    check(wait_until(lambda: engine2.clicks_done >= 3), "无限模式未开始点击")
    engine2.stop()
    check(wait_until(lambda: not engine2.is_running), "stop() 后线程未退出")
    done = engine2.clicks_done
    time.sleep(0.05)
    check(engine2.clicks_done == done, "stop() 后仍在继续点击")

    # 3) 固定坐标模式下 x/y 必须透传
    stub.clicks.clear()
    engine3 = make_engine(repeat_mode="count", repeat_count=1,
                          location_mode="fixed", fixed_x=123, fixed_y=456)
    engine3.start()
    check(wait_until(lambda: not engine3.is_running), "固定坐标模式未停止")
    check(stub.clicks == [(123, 456, "left")],
          f"固定坐标参数未透传: {stub.clicks!r}")
    return engine.clicks_done + done + engine3.clicks_done


def main() -> int:
    try:
        loaded = check_settings()
        stub = StubPyAutoGUI()
        total_clicks = check_click_engine(stub)
        print(
            "selfcheck ok: 配置默认值/类型校正/未知字段丢弃/JSON 往返正确；"
            f"ClickEngine 次数模式 5 次、无限模式 stop、固定坐标 (123,456) 均正确"
            f"（打桩共 {total_clicks} 次点击，无真实鼠标事件）"
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
