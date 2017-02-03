import requests

headers = {"Authorization": "Token superSecretApiToken"}
r = requests.post('http://localhost:8000/api/pattern/',
        headers=headers,
        json={"lava_server": "https://validation.linaro.org",
              "lava_job_id": "12346.1",
              "build_job_name": "team/project/build_number",
              "build_job_url": "https://ci.linaro.org/job/my-project/123"})
print r.status_code
print r.json()
