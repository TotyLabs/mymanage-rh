from locust import HttpUser, task, between

class PayrollUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def index(self):
        self.client.get("/")

    @task(1)
    def health(self):
        self.client.get("/health")
