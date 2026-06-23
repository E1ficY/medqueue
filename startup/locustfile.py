from locust import HttpUser, task, between
import random
import json

# ── Test credentials ──────────────────────────────────────────────────────────
TEST_USERS = [
    {"login": "testuser1", "password": "TestPass123!"},
    {"login": "testuser2", "password": "TestPass123!"},
    {"login": "testuser3", "password": "TestPass123!"},
]

class MedQueueUser(HttpUser):
    """
    Simulates a realistic MedQueue patient user session.
    Think ratio:
      - 60% browse (main, doctors, hospitals)
      - 25% profile / booking
      - 10% subscription page
      -  5% checkout flow
    """
    wait_time = between(1, 5)

    def on_start(self):
        """Log in before the test starts."""
        creds = random.choice(TEST_USERS)
        resp = self.client.post(
            "/api/auth/login/",
            json={
                "login": creds["login"],
                "password": creds["password"],
                "captcha_token": "XXXX.DUMMY.TOKEN.XXXX",  # bypassed in test mode
            },
            headers={"Content-Type": "application/json"},
            name="POST /api/auth/login/",
            catch_response=True,
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
                self.access_token = data.get("access", "")
                self.user_id = data.get("user", {}).get("id", "")
            except Exception:
                self.access_token = ""
                self.user_id = ""
            resp.success()
        else:
            self.access_token = ""
            resp.failure(f"Login failed: {resp.status_code} {resp.text[:200]}")

    def _auth_headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    # ── High-frequency: page views ────────────────────────────────────────────

    @task(10)
    def browse_main(self):
        self.client.get("/main.html", name="GET /main.html")

    @task(8)
    def browse_doctors(self):
        self.client.get("/doctors.html", name="GET /doctors.html")

    @task(6)
    def api_doctors_list(self):
        self.client.get(
            "/api/doctors/",
            headers=self._auth_headers(),
            name="GET /api/doctors/",
        )

    @task(5)
    def api_hospitals_list(self):
        self.client.get(
            "/api/hospitals/",
            headers=self._auth_headers(),
            name="GET /api/hospitals/",
        )

    # ── Medium: profile & appointments ───────────────────────────────────────

    @task(4)
    def browse_profile(self):
        self.client.get("/profile.html", name="GET /profile.html")

    @task(4)
    def api_profile(self):
        self.client.get(
            "/api/profile/",
            headers=self._auth_headers(),
            name="GET /api/profile/",
        )

    @task(3)
    def api_appointments_list(self):
        self.client.get(
            "/api/appointments/",
            headers=self._auth_headers(),
            name="GET /api/appointments/",
        )

    @task(2)
    def browse_recording(self):
        self.client.get("/recording.html", name="GET /recording.html")

    # ── Low: subscription & checkout ─────────────────────────────────────────

    @task(2)
    def browse_subscription(self):
        self.client.get("/subscription.html", name="GET /subscription.html")

    @task(1)
    def browse_checkout(self):
        self.client.get("/card-checkout.html", name="GET /card-checkout.html")

    # ── Very low: admin panel (only some users have access) ───────────────────

    @task(1)
    def api_health(self):
        self.client.get(
            "/api/health/",
            name="GET /api/health/",
        )
