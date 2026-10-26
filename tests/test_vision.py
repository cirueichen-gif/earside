"""Vision 模組單元測試：合圖、預算、Eye 流程。"""

import unittest
import cv2
import numpy as np

from earside.eyes.vision import Eye, VisionBudget, compose_frame, DEFAULT_VISION_PROMPT


class FakeVisionClient:
    """測試用假 Vision Client，記錄收到的請求並支援模擬例外。"""

    def __init__(self, reply: str = "模擬視覺描述：你在推塔，周圍安全。", should_raise: bool = False):
        self.reply = reply
        self.should_raise = should_raise
        self.calls: list[tuple[bytes, str]] = []

    def describe(self, image_bytes: bytes, prompt: str) -> str:
        if self.should_raise:
            raise RuntimeError("Fake client connection timeout")
        self.calls.append((image_bytes, prompt))
        return self.reply


class TestComposeFrame(unittest.TestCase):
    def setUp(self):
        # 1280x720 黑底，中間畫一個白色實心方塊
        self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(self.frame, (500, 300), (780, 420), (255, 255, 255), -1)

    def test_compose_without_regions(self):
        # 空 regions 應回傳主畫面 JPEG bytes
        jpeg_bytes = compose_frame(self.frame, regions=[])
        self.assertIsInstance(jpeg_bytes, bytes)
        self.assertGreater(len(jpeg_bytes), 0)

        # 解碼檢查
        decoded = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape[:2], (720, 1280))
        # 檢查白色方塊中心 (640, 360) 是否保留
        self.assertTrue(np.all(decoded[360, 640] > 200))

    def test_compose_with_regions(self):
        # 包含兩個 ROI
        regions = [
            ("minimap", (0.0, 0.0, 0.2, 0.2)),
            ("hp_bar", (0.4, 0.8, 0.2, 0.05)),
        ]
        jpeg_bytes = compose_frame(self.frame, regions=regions, max_width=1280)
        self.assertIsInstance(jpeg_bytes, bytes)
        self.assertGreater(len(jpeg_bytes), 0)

        decoded = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
        self.assertIsNotNone(decoded)
        # 側邊欄加上去之後寬度應該大於 1280
        h, w = decoded.shape[:2]
        self.assertGreaterEqual(w, 1280)
        self.assertGreaterEqual(h, 720)


class TestVisionBudget(unittest.TestCase):
    def test_minute_budget_limit_and_recovery(self):
        # 每分鐘最多 3 次，每小時 10 次
        budget = VisionBudget(max_per_minute=3, max_per_hour=10)

        # t = 0 時消耗 3 次
        self.assertTrue(budget.allow(now=0.0))
        self.assertTrue(budget.spend(now=0.0))
        self.assertTrue(budget.spend(now=0.0))
        self.assertTrue(budget.spend(now=0.0))

        # 第 4 次應該被拒絕
        self.assertFalse(budget.allow(now=0.0))
        self.assertFalse(budget.spend(now=0.0))

        # t = 30 仍應被拒絕
        self.assertFalse(budget.allow(now=30.0))

        # t = 60.1（超過 60 秒）應該恢復額度
        self.assertTrue(budget.allow(now=60.1))
        self.assertTrue(budget.spend(now=60.1))

    def test_hour_budget_limit(self):
        # 每分鐘 5 次，每小時 2 次
        budget = VisionBudget(max_per_minute=5, max_per_hour=2)

        self.assertTrue(budget.spend(now=0.0))
        self.assertTrue(budget.spend(now=10.0))
        # 每小時上限 2 次，第 3 次在第 70 秒（雖然每分鐘額度釋放了，但每小時未釋放）
        self.assertFalse(budget.allow(now=70.0))
        self.assertFalse(budget.spend(now=70.0))

        # 過了 3600 秒恢復
        self.assertTrue(budget.allow(now=3605.0))
        self.assertTrue(budget.spend(now=3605.0))

    def test_reset(self):
        budget = VisionBudget(max_per_minute=1, max_per_hour=1)
        self.assertTrue(budget.spend(now=0.0))
        self.assertFalse(budget.allow(now=0.0))
        budget.reset()
        self.assertTrue(budget.allow(now=0.0))


class TestEye(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        cv2.rectangle(self.frame, (500, 300), (780, 420), (255, 255, 255), -1)

    def test_eye_normal_flow(self):
        fake_client = FakeVisionClient(reply="畫面正常，英雄在吃兵")
        budget = VisionBudget(max_per_minute=2, max_per_hour=10)
        eye = Eye(client=fake_client, budget=budget)

        res = eye.describe(self.frame, regions=[("minimap", (0.0, 0.0, 0.15, 0.15))], now=0.0)
        self.assertEqual(res, "畫面正常，英雄在吃兵")
        self.assertIsNone(eye.last_error)
        self.assertEqual(len(fake_client.calls), 1)

        # 驗證傳送給 client 的資料
        img_bytes, prompt = fake_client.calls[0]
        self.assertIsInstance(img_bytes, bytes)
        self.assertEqual(prompt, DEFAULT_VISION_PROMPT)

    def test_eye_out_of_budget_returns_none(self):
        fake_client = FakeVisionClient()
        budget = VisionBudget(max_per_minute=1, max_per_hour=5)
        eye = Eye(client=fake_client, budget=budget)

        # 第 1 次成功
        r1 = eye.describe(self.frame, regions=None, now=0.0)
        self.assertIsNotNone(r1)
        self.assertEqual(len(fake_client.calls), 1)

        # 第 2 次預算用完，回傳 None 且不會呼叫 client
        r2 = eye.describe(self.frame, regions=None, now=10.0)
        self.assertIsNone(r2)
        self.assertEqual(len(fake_client.calls), 1)

    def test_eye_client_error_handling(self):
        fake_client = FakeVisionClient(should_raise=True)
        budget = VisionBudget(max_per_minute=2, max_per_hour=5)
        eye = Eye(client=fake_client, budget=budget)

        res = eye.describe(self.frame, regions=None, now=0.0)
        self.assertIsNone(res)
        self.assertIsNotNone(eye.last_error)
        self.assertIn("Fake client connection timeout", eye.last_error)


if __name__ == "__main__":
    unittest.main()
