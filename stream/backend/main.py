from random import choice
from fastapi import FastAPI, Request, Response
from prisma import Prisma
from secrets import token_hex
from slack_bolt import Ack, App
from fastapi_utils.tasks import repeat_every
from slack_bolt.adapter.fastapi import SlackRequestHandler
from dotenv import load_dotenv
import os
import requests

load_dotenv()

api = FastAPI()

db = Prisma()

bolt = App(
    token=os.environ["SLACK_TOKEN"], signing_secret=os.environ["SLACK_SIGNING_SECRET"]
)

bolt_handler = SlackRequestHandler(bolt)

active_stream = None


@api.get("/api/v1/stream_key/{stream_key}")
async def get_stream_by_key(stream_key: str):
    await db.connect()
    stream = await db.stream.find_first(where={"key": stream_key})
    await db.disconnect()
    return (
        stream if stream else Response(status_code=404, content="404: Stream not found")
    )


@api.get("/api/v1/user/{user_id}")
async def get_user_by_id(user_id: str):
    await db.connect()
    user = await db.user.find_first(where={"slack_id": user_id})
    await db.disconnect()
    return user if user else Response(status_code=404, content="404: User not found")


@bolt.event("app_home_opened")
def handle_app_home_opened_events(body, logger, event, client):
    client.views_publish(
        user_id=event["user"],
        # the view object that appears in the app home
        view={
            "type": "home",
            "callback_id": "home_view",
            # body of the view
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Welcome to OnBoard Live! Try sending `/onboard-live-apply` in the #onboard-live channel to get started!",
                    },
                },
            ],
        },
    )


@bolt.action("approve")
def approve(ack, body):
    ack()
    message = body["message"]
    applicant_slack_id = message["blocks"][len(message) - 3]["text"]["text"].split(": ")[1] # I hate it. You hate it. We all hate it. Carry on.
    applicant_name = message["blocks"][len(message) - 6]["text"]["text"]
    print(applicant_slack_id, applicant_name)
    # new_user = await db.user.create(
    # {"slack_id": applicant_slack_id, "name": user["name"]}
    # )
    # print(new_user.id)
    # new_stream = await db.stream.create(
    # {"user": {"connect": {"id": new_user.id}}, "key": token_hex(16)}
    # )
    # print(new_user, new_stream)


@bolt.view("apply")
def handle_application_submission(ack, body):
    ack()
    user = body["user"]["id"]
    sumbitter_convo = bolt.client.conversations_open(users=user, return_im=True)
    user_real_name = bolt.client.users_info(user=user)["user"]["real_name"]
    user_verified = (
        "Eligible L"
        not in requests.get(
            "https://verify.hackclub.dev/api/status", json={"slack_id": user}
        ).text
    )
    bolt.client.chat_postMessage(
        channel=sumbitter_convo["channel"]["id"],
        text=f"Your application has been submitted! We will review it shortly. Please do not send another application - If you haven't heard back in over 48 hours, or you forgot something in your application, please message <@{os.environ['ADMIN_SLACK_ID']}>! Here's a copy of your responses for your reference:\nSome info on your project(s): {body['view']['state']['values']['project-info']['project-info-body']['value']}{f'\nPlease fill out <https://forms.hackclub.com/eligibility?program=Onboard%20Live&slack_id={user}|the verification form>! We can only approve your application once this is done.' if not user_verified else ''}",
    )
    admin_convo = bolt.client.conversations_open(
        users=os.environ["ADMIN_SLACK_ID"], return_im=True
    )
    bolt.client.chat_postMessage(
        channel=admin_convo["channel"]["id"],
        text=":siren-real: New OnBoard Live application! :siren-real:",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":siren-real: New OnBoard Live application! :siren-real:",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": f":technologist: Name: {user_real_name}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": f":white_check_mark: Is verified: {user_verified}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": f":hammer_and_wrench: Will make: {body['view']['state']['values']['project-info']['project-info-body']['value']}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": f":pray: Will behave on stream: Yes",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": f"Slack ID: {user}",
                    "emoji": True,
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "emoji": True,
                            "text": "Approve",
                        },
                        "style": "primary",
                        "value": "approve",
                        "action_id": "approve",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "emoji": True, "text": "Deny"},
                        "style": "danger",
                        "value": "deny",
                        "action_id": "deny",
                    },
                ],
            },
        ],
    )


@bolt.command("/onboard-live-apply")
def apply(ack: Ack, command):
    ack()
    print(
        requests.post(
            "https://slack.com/api/views.open",
            headers={
                "Authorization": f"Bearer {os.environ['SLACK_TOKEN']}",
                "Content-type": "application/json; charset=utf-8",
            },
            json={
                "trigger_id": command["trigger_id"],
                "view": {
                    "type": "modal",
                    "callback_id": "apply",
                    "title": {
                        "type": "plain_text",
                        "text": "OnBoard Live Application",
                        "emoji": True,
                    },
                    "submit": {"type": "plain_text", "text": "Submit", "emoji": True},
                    "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Welcome to OnBoard Live!\n\n*Please make sure to read this form thoroughly.*\n\nWe can't wait to see what you make!\n\n_Depending on your screen, you might need to scroll down to see the whole form._",
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "input",
                            "block_id": "project-info",
                            "element": {
                                "action_id": "project-info-body",
                                "type": "plain_text_input",
                                "multiline": True,
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "I want to make...",
                                },
                            },
                            "label": {
                                "type": "plain_text",
                                "text": "What do you plan on making?\n\nNote that you can make whatever you want, this is just so we know what level you're at!",
                                "emoji": True,
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "Examples of unacceptable behavior include (but are not limited to) streaming inappropriate content or content that is unrelated to PCB design, sharing your stream key with others, trying to abuse the system, streaming work that you did not do or is not actually live (i.e. pre-recorded). Inappropriate behavior may result in removal from the Hack Club Slack or other consequences, as stated in the <https://hackclub.com/conduct/|Code of Conduct>. Any use of your stream key is your responsibilty, so don't share it with anyone for any reason. Admins will never ask for your stream key. Please report any urgent rule violations by messaging <@U05C64XMMHV>. If they do not respond in 5 minutes, please ping <!subteam^S01E4DN8S0Y|fire-fighters>.",
                            },
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "plain_text",
                                "text": "Confirm that you have read the above by following these instructions:",
                            },
                            "accessory": {
                                "type": "checkboxes",
                                "options": [
                                    {
                                        "text": {
                                            "type": "plain_text",
                                            "text": "To agree that you will be well-behaved while you're live, DO NOT check this box. Instead, check the one below.",
                                            "emoji": True,
                                        },
                                        "description": {
                                            "type": "mrkdwn",
                                            "text": "This is to make sure you're paying attention!",
                                        },
                                        "value": "value-0",
                                    },
                                    {
                                        "text": {
                                            "type": "plain_text",
                                            "text": "To agree that you will be well-behaved while you're live, check this box.",
                                            "emoji": True,
                                        },
                                        "value": "value-1",
                                    },
                                ],
                                "action_id": "checkboxes",
                            },
                        },
                        {"type": "divider"},
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": "Please ask <@U05C64XMMHV> for help if you need it!",
                                }
                            ],
                        },
                    ],
                },
            },
        ).text
    )
    # bolt.client.modal(channel=command['channel_id'], user=command['user_id'], text="Application form for OnBoard Live", blocks=[{


@bolt.action("checkboxes")
def handle_some_action(ack):
    ack()


# 		"type": "header",
# 		"text": {
# 			"type": "plain_text",
# 			"text": "Welcome to OnBoard Live!",
# 		}
# 	},
# 	{
# 		"type": "section",
# 		"text": {
# 			"type": "mrkdwn",
# 			"text": "Before you can get designing, we need a little bit of info from you. All fields are required!"
# 		}
# 	},
# 	{
# 		"type": "divider"
# 	},
# 	{
# 		"type": "input",
# 		"element": {
# 			"type": "plain_text_input",
# 			"multiline": True,
# 			"action_id": "project_ideas_input-action",
# 			"placeholder": {
# 				"type": "plain_text",
# 				"text": "I want to make a..."
# 			}
# 		},
# 		"label": {
# 			"type": "plain_text",
# 			"text": "What do you plan to make with OnBoard Live?\nThis can be changed anytime!",
# 		}
# 	},
# 	{
# 		"type": "divider"
# 	},
# 	{
# 		"type": "actions",
# 		"elements": [
# 			{
# 				"type": "button",
# 				"text": {
# 					"type": "plain_text",
# 					"text": "Apply!",
# 				},
# 				"value": "apply",
# 				"style": "primary",
# 				"action_id": "actionId-0"

# 		}]}])


@api.post("/slack/events")
async def slack_event_endpoint(req: Request):
    return await bolt_handler.handle(req)


@repeat_every(seconds=5 * 60, wait_first=True)
async def change_active_stream():
    global active_stream
    streams = []
    for stream in await db.stream.find_many():
        streams.append(stream.id)
    if len(streams) == 0:
        return
    if active_stream not in streams:
        active_stream = None
    if active_stream is None:
        active_stream = choice(streams)
    else:
        if streams.index(active_stream) + 1 == len(streams):
            active_stream = streams[0]
        else:
            active_stream = streams[streams.index(active_stream) + 1]
        bolt.client.chat_postMessage(channel="C07ERCGG989", text=f":partyparrot_wave1::partyparrot_wave2::partyparrot_wave3::partyparrot_wave4::partyparrot_wave5::partyparrot_wave6::partyparrot_wave7: Hey <@{(await db.stream.find_first(where={'id': active_stream})).user.slack_id}>, you're in focus right now! Remember to talk us through what you're doing!")  # type: ignore
