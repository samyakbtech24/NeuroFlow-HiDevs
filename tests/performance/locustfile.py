import os

from locust import HttpUser, between, events, task

ADMIN_TOKEN = None

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    import requests
    host = environment.host or "http://localhost:8000"
    res = requests.post(f"{host}/auth/token", json={"client_id": "admin", "client_secret": "admin"})
    if res.status_code == 200:
        global ADMIN_TOKEN
        ADMIN_TOKEN = res.json()["access_token"]
    else:
        print("Failed to acquire auth token for load testing!")

class BaseUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        if ADMIN_TOKEN:
            self.client.headers.update({"Authorization": f"Bearer {ADMIN_TOKEN}"})

class QueryUser(BaseUser):
    weight = 7
    
    @task
    def query_pipeline(self):
        import uuid
        self.client.post(
            "/query", 
            json={
                "query": "What is the architecture of the Transformer model?",
                "pipeline_id": str(uuid.uuid4()),
                "stream": False
            }, 
            name="/query"
        )

class IngestUser(BaseUser):
    weight = 2
    
    @task
    def ingest_document(self):
        # Cache file bytes in memory so disk I/O doesn't bottleneck Locust during high concurrency
        file_path = "tests/fixtures/test_doc.pdf"
        if not hasattr(self.__class__, 'file_bytes'):
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    self.__class__.file_bytes = f.read()
            else:
                self.__class__.file_bytes = b"%PDF-1.4 dummy pdf content"
                
        self.client.post(
            "/", 
            files={"file": ("test_doc.pdf", self.__class__.file_bytes, "application/pdf")}, 
            name="/ingest"
        )

class AdminUser(BaseUser):
    weight = 1
    
    @task
    def check_dashboards(self):
        self.client.get("/health", name="/health")
        self.client.get("/pipelines", name="/pipelines")
