import os, time, threading, requests
from slack_bolt import App  # Slack Bolt framework for building Slack apps
from slack_bolt.adapter.socket_mode import SocketModeHandler  # For running Slack app in Socket Mode
from dotenv import load_dotenv  # To load environment variables from .env file
from requests.auth import HTTPBasicAuth  # To authenticate with Jenkins API using username and API token

# Load environment variables from .env file
load_dotenv()

# --- Environment Variable Setup ---
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]  # Slack bot token for authentication
SLACK_APP_TOKEN = os.environ["SLACK_APP_TOKEN"]  # Slack app-level token for socket connection
JENKINS_URL = os.environ["JENKINS_URL"].rstrip("/")  # Jenkins base URL (trim trailing slash)
JENKINS_USER = os.environ["JENKINS_USER"]  # Jenkins username
JENKINS_API_TOKEN = os.environ["JENKINS_API_TOKEN"]  # Jenkins API token for authentication
DEFAULT_SLACK_CHANNEL = os.environ.get("DEFAULT_SLACK_CHANNEL", "cicd-status")  # Default Slack channel name
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 30))  # Polling interval in seconds to check Jenkins

# Initialize Slack Bolt app
bolt_app = App(token=SLACK_BOT_TOKEN)

# stores the last known build number of each Jenkins job
job_last_build = {}

# --- Function to fetch all Jenkins jobs and their last build details ---
def get_all_jobs():
    # Jenkins API endpoint for listing all jobs and their build information
    url = f"{JENKINS_URL}/api/json?tree=jobs[name,url,lastBuild[number,result,building]]"
    r = requests.get(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN))  # Authenticated GET request
    r.raise_for_status()  # Raise an exception if request fails
    return r.json().get("jobs", [])  # Return list of job objects

# --- Function to post messages to Slack ---
def post_to_slack(channel, text):
    # Sends a message to the specified Slack channel
    bolt_app.client.chat_postMessage(channel=channel, text=text)

# --- Background thread function to monitor Jenkins jobs ---
def monitor_jenkins():
    global job_last_build
    while True:  
        try:
            jobs = get_all_jobs()  # Fetch all Jenkins jobs
            for job in jobs:
                job_name = job["name"] 
                last_build = job.get("lastBuild")  # Get last build info

               
                if not last_build:
                    continue

                build_number = last_build["number"]  
                building = last_build.get("building", False)  
                result = last_build.get("result")  # Get the build result (SUCCESS, FAILURE, etc.)

                if job_name not in job_last_build or build_number > job_last_build[job_name]:
                    job_last_build[job_name] = build_number  
                    build_url = f"{job['url']}{build_number}/"  

                    # Notify on Slack depending on build state
                    if building:
                        post_to_slack(
                            DEFAULT_SLACK_CHANNEL,
                            f"🚀 Jenkins job *{job_name}* started build *#{build_number}*.\n{build_url}"
                        )
                    elif result:
                        post_to_slack(
                            DEFAULT_SLACK_CHANNEL,
                            f"✅ Jenkins job *{job_name}* finished build *#{build_number}* with *{result}*.\n{build_url}"
                        )
        except Exception as e:
            print(f"Error monitoring Jenkins: {e}")

        # Wait for specified polling interval before next check
        time.sleep(POLL_INTERVAL)

# --- Slack Event Handler for Mentions ---
@bolt_app.event("app_mention")
def mention_handler(event, say):
    # When bot is mentioned in a Slack message, respond politely
    user = event.get("user")
    say(f"Hi <@{user}>! I automatically post Jenkins job statuses here.")

# --- Slack Slash Command (/build) Handler ---
@bolt_app.command("/build")
def handle_build_command(ack, body, say, logger):
    # Acknowledge the command immediately to Slack (avoid timeout)
    ack("Received your build request!")

    user = body.get("user_name")  # Extract username who triggered the command
    say(f"Hi @{user}, your Jenkins build request has been received.")

    job_name = "jenkins-job"  # Default Jenkins job name to trigger
    url = f"{JENKINS_URL}/job/{job_name}/build"  # Jenkins API endpoint to trigger build

    try:
        # Send a POST request to trigger the Jenkins job
        r = requests.post(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN))
        if r.status_code == 201:
            say(f"🎉 Jenkins job *{job_name}* has been triggered successfully!")
        else:
            say(f"⚠️ Failed to trigger Jenkins job. Status code: {r.status_code}")
    except Exception as e:
        say(f"❌ Error triggering Jenkins build: {e}")

# --- Main Entry Point ---
if __name__ == "__main__":
    # Start background thread to monitor Jenkins builds
    threading.Thread(target=monitor_jenkins, daemon=True).start()

    # Initialize Slack Socket Mode handler (keeps app running and connected)
    handler = SocketModeHandler(bolt_app, SLACK_APP_TOKEN)
    print("Starting Slack Socket Mode client and Jenkins monitor...")

    # Start Slack app in Socket Mode
    handler.start()
