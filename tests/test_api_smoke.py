"""API 冒烟测试：认证、知识库、文档、会话与对话全链路。"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from api import app


class TestApiSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.username = f"test_{int(time.time())}"
        cls.password = "test-pass-123"

        response = cls.client.post(
            "/register",
            json={"username": cls.username, "password": cls.password},
        )
        if response.status_code != 200:
            raise AssertionError(f"注册失败: {response.status_code} {response.text}")

        response = cls.client.post(
            "/login",
            json={"username": cls.username, "password": cls.password},
        )
        if response.status_code != 200:
            raise AssertionError(f"登录失败: {response.status_code} {response.text}")
        data = response.json()
        cls.token = data["access_token"]
        cls.refresh_token = data["refresh_token"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}
        cls.kb_id = None
        cls.conversation_id = None

    def test_01_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("components", response.json())

    def test_02_me(self):
        response = self.client.get("/users/me", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], self.username)

    def test_03_refresh(self):
        response = self.client.post(
            "/refresh", json={"refresh_token": self.refresh_token}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("access_token", response.json())

    def test_04_knowledge_base_crud(self):
        response = self.client.post(
            "/knowledge-bases",
            headers=self.headers,
            json={"name": "冒烟测试知识库", "description": "smoke"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        TestApiSmoke.kb_id = response.json()["id"]

        response = self.client.get("/knowledge-bases", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any(kb["id"] == self.kb_id for kb in response.json())
        )

    def test_05_upload_and_index(self):
        self.assertIsNotNone(self.kb_id)

        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(
                "Nova 平台支持多知识库。\n\n"
                "每个知识库可以上传 TXT、Markdown 或 CSV 文档。\n\n"
                "检索使用向量相似度。\n"
            )
            temp_path = f.name

        try:
            with open(temp_path, "rb") as f:
                response = self.client.post(
                    f"/knowledge-bases/{self.kb_id}/documents",
                    headers=self.headers,
                    files={"file": ("doc.txt", f, "text/plain")},
                )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["status"], "pending")

            deadline = time.time() + 90
            status = None
            while time.time() < deadline:
                response = self.client.get(
                    f"/knowledge-bases/{self.kb_id}/index-status",
                    headers=self.headers,
                )
                self.assertEqual(response.status_code, 200)
                body = response.json()
                if body.get("ready"):
                    status = body
                    break
                time.sleep(1)

            self.assertIsNotNone(
                status, "索引未在超时时间内就绪"
            )
            self.assertTrue(status["documents"][0]["status"], "ready")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_06_conversation_crud(self):
        response = self.client.post(
            "/conversations",
            headers=self.headers,
            json={
                "title": "冒烟测试会话",
                "knowledge_base_id": self.kb_id,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        TestApiSmoke.conversation_id = response.json()["id"]

        response = self.client.get(
            "/conversations",
            headers=self.headers,
            params={"knowledge_base_id": self.kb_id},
        )
        self.assertEqual(response.status_code, 200)

    def test_07_chat(self):
        response = self.client.post(
            "/chat",
            headers=self.headers,
            json={
                "message": "Nova 平台支持哪些文档格式？",
                "conversation_id": self.conversation_id,
                "knowledge_base_id": self.kb_id,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("answer", body)
        self.assertIsInstance(body.get("sources"), list)

    def test_08_messages_paginated(self):
        response = self.client.get(
            f"/conversations/{self.conversation_id}/messages",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("total", body)
        self.assertGreaterEqual(body["total"], 2)

    def test_08b_chat_stream(self):
        with self.client.stream(
            "POST",
            "/chat/stream",
            headers=self.headers,
            json={
                "message": "Nova 平台是什么？",
                "conversation_id": self.conversation_id,
                "knowledge_base_id": self.kb_id,
            },
        ) as response:
            if response.status_code != 200:
                self.fail(f"流式接口返回 {response.status_code}")

            collected = ""
            saw_done = False
            for chunk in response.iter_text():
                collected += chunk
                if '"type": "done"' in collected:
                    saw_done = True
                    break

            self.assertTrue(
                saw_done, f"未收到 done 事件：{collected[:500]}"
            )
            self.assertIn('"type": "delta"', collected)

    def test_09_coding_agent_disabled_by_default(self):
        response = self.client.post(
            "/coding-agent",
            headers=self.headers,
            json={"task": "检查 /chat 接口"},
        )
        # 默认关闭：非管理员 403；即使管理员也需要开关
        self.assertIn(response.status_code, (403, 403), response.text)

    def test_10_cross_user_isolation(self):
        other = f"other_{int(time.time())}"
        response = self.client.post(
            "/register",
            json={"username": other, "password": "other-pass-123"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        login = self.client.post(
            "/login",
            json={"username": other, "password": "other-pass-123"},
        )
        other_headers = {
            "Authorization": f"Bearer {login.json()['access_token']}"
        }

        response = self.client.get(
            f"/conversations/{self.conversation_id}/messages",
            headers=other_headers,
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.delete(
            f"/knowledge-bases/{self.kb_id}",
            headers=other_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_11_cleanup(self):
        response = self.client.delete(
            f"/knowledge-bases/{self.kb_id}",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
