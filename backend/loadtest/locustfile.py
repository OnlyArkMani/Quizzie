"""
Locust scenario: a realistic exam session per simulated student.

    pip install locust
    python -m loadtest.seed --students 500          # writes loadtest/fixture.json
    locust -f loadtest/locustfile.py --host http://localhost:8000 \
           --users 500 --spawn-rate 50 --run-time 10m

Each user: start/resume -> load state + questions -> answer questions with
periodic auto-saves (every ~10 s, like the real frontend) -> submit once.
The seeded exam is 180 minutes long, so no one hits the deadline.
"""
import json
import random
import uuid
from itertools import count
from pathlib import Path

from locust import HttpUser, between, task

FIXTURE = json.loads(Path(__file__).with_name("fixture.json").read_text())
_next_token = count()


class Student(HttpUser):
    wait_time = between(5, 15)          # think time between auto-saves

    def on_start(self):
        tokens = FIXTURE["student_tokens"]
        self.headers = {"Authorization": f"Bearer {tokens[next(_next_token) % len(tokens)]}"}
        exam_id = FIXTURE["exam_id"]
        r = self.client.post("/api/v1/attempts/start", json={"exam_id": exam_id},
                             headers=self.headers, name="POST /attempts/start")
        self.attempt_id = r.json()["id"]
        self.client.get(f"/api/v1/attempts/{self.attempt_id}/state",
                        headers=self.headers, name="GET /attempts/{id}/state")
        self.client.get(f"/api/v1/exams/{exam_id}/questions",
                        headers=self.headers, name="GET /exams/{id}/questions")
        self.seq = 0
        self.saves = 0
        self.submitted = False
        self.idem = str(uuid.uuid4())

    @task
    def answer_and_autosave(self):
        if self.submitted:
            return
        # A few edits since the last save, sent as one delta.
        batch = []
        for q in random.sample(FIXTURE["questions"], k=random.randint(1, 3)):
            self.seq += 1
            batch.append({"question_id": q["id"],
                          "selected_option_ids": [random.choice(q["options"])],
                          "client_seq": self.seq})
        self.client.post(f"/api/v1/attempts/{self.attempt_id}/auto-save",
                         json={"responses": batch}, headers=self.headers,
                         name="POST /attempts/{id}/auto-save")
        self.client.get(f"/api/v1/monitor/enhanced/attempt/{self.attempt_id}/health",
                        headers=self.headers, name="GET /monitor/.../health")
        self.saves += 1
        if self.saves >= 20:
            self.client.post(f"/api/v1/attempts/{self.attempt_id}/submit",
                             json={"responses": []},
                             headers={**self.headers, "Idempotency-Key": self.idem},
                             name="POST /attempts/{id}/submit")
            self.submitted = True
