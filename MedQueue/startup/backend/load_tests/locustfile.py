from locust import HttpUser, task, between


class MedQueueApiUser(HttpUser):
    wait_time = between(1, 3)

    @task(4)
    def hospitals(self):
        self.client.get('/api/hospitals/?page_size=100', name='GET /api/hospitals')

    @task(3)
    def doctors(self):
        self.client.get('/api/doctors/', name='GET /api/doctors')

    @task(2)
    def ai_chat(self):
        payload = {'message': 'У меня болит горло, к кому идти?'}
        self.client.post('/api/ai/chat/', json=payload, name='POST /api/ai/chat')

    @task(1)
    def open_main(self):
        self.client.get('/main.html', name='GET /main.html')
