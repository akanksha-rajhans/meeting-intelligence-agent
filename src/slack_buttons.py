import re
from datetime import datetime
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from src.config import SLACK_BOT_TOKEN, SLACK_APP_TOKEN, PROCESSED_DIR
from src.notifier import Notifier  # import the notifier you updated

app = App(token=SLACK_BOT_TOKEN)

# Make Bolt's client importable everywhere
bolt_client = app.client

notifier = Notifier(token=SLACK_BOT_TOKEN, default_channel="general")  # adjust default channel


# mark_done handler (your existing)
@app.action(re.compile(r"mark_done_.*"))
def handle_mark_done(ack, body, client, logger):
    ack()
    print("DEBUG action body:", body)
    action_id = body["actions"][0]["value"]
    print("DEBUG action value:", action_id)
    print("DEBUG action value:", action_id)
    if notifier.mark_done(action_id):
        client.chat_postMessage(channel=body["user"]["id"], text="Task marked done ✅")
    else:
        client.chat_postMessage(channel=body["user"]["id"], text="Sorry, task not found or already deleted.")

# snooze handler (1 day snooze)
@app.action(re.compile(r"snooze_1d_(.*)"))
def handle_snooze(ack, body, client, logger):
    ack()
    action_id = body["actions"][0]["value"]
    if notifier.snooze_action(action_id, days=1):
        client.chat_postMessage(channel=body["user"]["id"], text="Task snoozed for 1 day ⏰")
    else:
        client.chat_postMessage(channel=body["user"]["id"], text="Could not snooze task (not found or deleted).")

# delete handler
@app.action(re.compile(r"delete_(.*)"))
def handle_delete(ack, body, client, logger):
    ack()
    action_id = body["actions"][0]["value"]
    if notifier.delete_action(action_id):
        client.chat_postMessage(channel=body["user"]["id"], text="Task deleted 🗑️")
    else:
        client.chat_postMessage(channel=body["user"]["id"], text="Could not delete task (not found).")

def send_via_bolt(channel, text=None, blocks=None):
    return app.client.chat_postMessage(
        channel=channel,
        text=text or " ",
        blocks=blocks
    )

if __name__ == "__main__":
    print("🟢 Slack button server started")
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
