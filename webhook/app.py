from flask import Flask, request, jsonify
import subprocess
import requests
import logging
from functools import wraps
import time

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

AUTH_TOKEN = "Splendid@20"  # Replace with your actual token

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if token != f"Bearer {AUTH_TOKEN}":
            return jsonify({"error": "Unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated

def retry(func, retries=3, delay=2):
    for i in range(retries):
        try:
            return func()
        except Exception as e:
            logging.warning(f"Retry {i+1}/{retries} failed: {e}")
            time.sleep(delay)
    raise Exception("All retries failed")

@app.route('/', methods=['GET'])
def home():
    return "Webhook server is running", 200

@app.route('/alert', methods=['POST'])
@require_auth
def alert():
    logging.info("Received alert POST request")
    data = request.json
    alert_name = data['alerts'][0]['labels']['alertname']
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    def restart_container():
        container = data['alerts'][0]['labels'].get('container', 'my_app')
        subprocess.run(f"docker logs {container} > {container}_logs_{timestamp}.log", shell=True)
        subprocess.run(f"docker restart {container}", shell=True)

    def clear_disk():
        subprocess.run(f"tar -czf logs_backup_{timestamp}.tar.gz /var/log", shell=True)
        subprocess.run("find /var/log -type f -mtime +7 -delete", shell=True)

    def create_incident():
        def send_request():
            response = requests.post(
                "https://dev184564.service-now.com/api/now/table/incident",
                auth=("admin", "*nwFnO4^b0SA"),  # Replace with your actual password
                headers={"Content-Type": "application/json"},
                json={
                    "short_description": "Critical alert triggered",
                    "description": str(data),
                    "category": "Inquiry / Help",
                    "impact": "2",
                    "urgency": "2"
                },
                verify=False
            )
            logging.info(f"ServiceNow response: {response.status_code} - {response.text}")
            return response

        return retry(send_request)

    try:
        if alert_name == "ContainerDown":
            retry(restart_container)
        elif alert_name == "DiskUsageHigh":
            retry(clear_disk)
        elif alert_name == "CriticalAlert":
            create_incident()
        logging.info(f"Processed alert: {alert_name}")
        return "Processed", 200
    except Exception as e:
        logging.error(f"Error processing alert: {e}")
        return "Error", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)