import os
import time
import threading
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

# Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]
JENKINS_URL = os.environ["JENKINS_URL"].rstrip("/")
JENKINS_USER = os.environ["JENKINS_USER"]
JENKINS_API_TOKEN = os.environ["JENKINS_API_TOKEN"]
DEFAULT_SLACK_CHANNEL = os.environ.get("DEFAULT_SLACK_CHANNEL", "cicd-status")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 10))

# Initialize Slack Bolt app
bolt_app = App(token=SLACK_BOT_TOKEN)
job_last_build = {}

def get_all_jobs():
    """Fetch all Jenkins jobs and their last build details."""
    url = f"{JENKINS_URL}/api/json?tree=jobs[name,url,lastBuild[number,result,building]]"
    r = requests.get(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN))
    r.raise_for_status()
    return r.json().get("jobs", [])

def post_to_slack(channel, text):
    """Post message to Slack."""
    bolt_app.client.chat_postMessage(channel=channel, text=text)

def monitor_jenkins():
    """Continuously monitor Jenkins and auto-post updates to Slack."""
    global job_last_build
    print("🚀 Jenkins monitor started.")
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

                # Check if this is a new build
                if job_name not in job_last_build or build_number > job_last_build[job_name]:
                    job_last_build[job_name] = build_number
                    build_url = f"{job['url']}{build_number}/"

                    if building:
                        post_to_slack(
                            DEFAULT_SLACK_CHANNEL,
                            f"🚀 Jenkins job *{job_name}* started build *#{build_number}*.\n{build_url}"
                        )
                    elif result:
                        if result == "SUCCESS":
                            post_to_slack(
                                DEFAULT_SLACK_CHANNEL,
                                f"✅ Jenkins job *{job_name}* finished build *#{build_number}* with *{result}*.\n{build_url}"
                            )
                        elif result == "FAILURE":
                            post_to_slack(
                                DEFAULT_SLACK_CHANNEL,
                                f"❌ Jenkins job *{job_name}* finished build *#{build_number}* with *{result}*.\n{build_url}"
                            )
                        elif result == "ABORTED":
                            post_to_slack(
                                DEFAULT_SLACK_CHANNEL,
                                f"🚫 Jenkins job *{job_name}* finished build *#{build_number}* with *{result}*.\n{build_url}"
                            )
                        else:
                            post_to_slack(
                                DEFAULT_SLACK_CHANNEL,
                                f"⚠️ Jenkins job *{job_name}* finished build *#{build_number}* with *{result}*.\n{build_url}"
                            )

        except Exception as e:
            print(f"Error monitoring Jenkins: {e}")

        time.sleep(POLL_INTERVAL)

@bolt_app.event("app_mention")
def mention_handler(event, say):
    user = event.get("user")
    say(f"Hi <@{user}>! I automatically post Jenkins job statuses here.")

@bolt_app.command("/build")
def handle_build_command(ack, body, say):
    """Trigger all Jenkins jobs when /build command is used."""
    ack("Received your build request!")
    user = body.get("user_name")
    say(f"Hi @{user}, your Jenkins build request has been received.")

    try:
        jobs = get_all_jobs()
        if not jobs:
            say("⚠️ No Jenkins jobs found.")
            return

        for job in jobs:
            job_name = job["name"]
            url = f"{JENKINS_URL}/job/{job_name}/build"
            r = requests.post(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN))
            if r.status_code == 201:
                say(f"✅ Jenkins job *{job_name}* has been triggered successfully!")
            else:
                say(f"⚠️ Failed to trigger Jenkins job: *{job_name}*. Status code: {r.status_code}")

    except Exception as e:
        say(f"❌ Error triggering Jenkins build: {e}")

if __name__ == "__main__":
    threading.Thread(target=monitor_jenkins, daemon=True).start()
    handler = SocketModeHandler(bolt_app, SLACK_APP_TOKEN)
    print("Starting Slack Socket Mode client and Jenkins monitor...")
    handler.start()

