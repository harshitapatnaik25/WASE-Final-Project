import os
import time
import threading
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv()

# -----------------------------
# Environment Variables
# -----------------------------
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
JENKINS_URL = os.environ["JENKINS_URL"].rstrip("/")
JENKINS_USER = os.environ["JENKINS_USER"]
JENKINS_API_TOKEN = os.environ["JENKINS_API_TOKEN"]
DEFAULT_SLACK_CHANNEL = os.environ.get("DEFAULT_SLACK_CHANNEL", "cicd-status")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 30))  # seconds

# -----------------------------
# Slack App (Socket Mode)
# -----------------------------
bolt_app = App(token=SLACK_BOT_TOKEN)

# Keep track of last known build number for each job
job_last_build = {}

# -----------------------------
# Jenkins helpers
# -----------------------------
def get_all_jobs():
    """Fetch all Jenkins jobs with their last build number."""
    url = f"{JENKINS_URL}/api/json?tree=jobs[name,url,lastBuild[number,result,building]]"
    r = requests.get(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN))
    r.raise_for_status()
    jobs = r.json().get("jobs", [])
    return jobs

def post_to_slack(channel: str, text: str):
    """Send message to Slack."""
    bolt_app.client.chat_postMessage(channel=channel, text=text)

def monitor_jenkins():
    """Background thread to poll Jenkins and post updates to Slack."""
    global job_last_build
    while True:
        try:
            jobs = get_all_jobs()
            for job in jobs:
                job_name = job["name"]
                last_build = job.get("lastBuild")
                if not last_build:
                    continue
                build_number = last_build["number"]
                building = last_build.get("building", False)
                result = last_build.get("result")

                # If we haven't seen this build yet
                if job_name not in job_last_build or build_number > job_last_build[job_name]:
                    job_last_build[job_name] = build_number
                    build_url = f"{job['url']}{build_number}/"

                    if building:
                        post_to_slack(DEFAULT_SLACK_CHANNEL, f"🚀 Jenkins job *{job_name}* started build *#{build_number}*.\n{build_url}")
                    elif result:
                        post_to_slack(DEFAULT_SLACK_CHANNEL, f"✅ Jenkins job *{job_name}* finished build *#{build_number}* with *{result}*.\n{build_url}")
        except Exception as e:
            print(f"Error monitoring Jenkins: {e}")

        time.sleep(POLL_INTERVAL)

# -----------------------------
# Respond to mentions
# -----------------------------
@bolt_app.event("app_mention")
def mention_handler(event, say):
    user = event.get("user")
    say(f"Hi <@{user}>! I automatically post Jenkins job statuses here.")

# -----------------------------
# Handle /build slash command
# -----------------------------
@bolt_app.command("/build")
def handle_build_command(ack, body, say, logger):
    ack("Received your build request!")

    user = body.get("user_name")
    say(f"Hi @{user}, your Jenkins build request has been received.")

    job_name = "jenkins-job"  # <-- Replace with your actual Jenkins job name
    url = f"{JENKINS_URL}/job/{job_name}/build"

    try:
        logger.info(f"Triggering Jenkins build at: {url}")
        r = requests.post(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN))
        logger.info(f"Response: {r.status_code} - {r.text}")

        if r.status_code == 201:
            say(f"🎉 Jenkins job *{job_name}* has been triggered successfully!")
        else:
            say(f"⚠️ Failed to trigger Jenkins job. Status code: {r.status_code}")
    except Exception as e:
        logger.error(f"Error triggering Jenkins build: {e}")
        say(f"❌ Error triggering Jenkins build: {e}")

# -----------------------------
# Start Socket Mode and Jenkins monitor
# -----------------------------
if __name__ == "__main__":
    threading.Thread(target=monitor_jenkins, daemon=True).start()
    handler = SocketModeHandler(bolt_app, SLACK_APP_TOKEN)
    print("Starting Slack Socket Mode client and Jenkins monitor...")
    handler.start()