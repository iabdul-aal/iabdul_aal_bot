import json
import logging
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)


load_dotenv()

DEFAULT_MENTOR_USERNAME = "@islamibr29"
DEFAULT_PUBLIC_CHANNEL_URL = "https://t.me/iabdul_aal"
DEFAULT_DISCUSSION_GROUP_URL = "https://t.me/+dFtrvA9rLjwxN2U0"

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID_RAW = (os.getenv("ADMIN_ID") or "").strip()
MENTOR_USERNAME = (os.getenv("MENTOR_USERNAME") or DEFAULT_MENTOR_USERNAME).strip()
PUBLIC_CHANNEL_URL = (os.getenv("PUBLIC_CHANNEL_URL") or DEFAULT_PUBLIC_CHANNEL_URL).strip()
DISCUSSION_GROUP_URL = (os.getenv("DISCUSSION_GROUP_URL") or DEFAULT_DISCUSSION_GROUP_URL).strip()
DISCUSSION_GROUP_ID_RAW = (os.getenv("DISCUSSION_GROUP_ID") or "").strip()
DATA_DIR = Path(
    os.getenv("DATA_DIR")
    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    or Path(__file__).with_name("data")
)
ADMIN_FILE = DATA_DIR / "admin_id.txt"
DISCUSSION_FILE = DATA_DIR / "discussion_group_id.txt"
SUBMISSIONS_FILE = DATA_DIR / "submissions.jsonl"

TRACK, LEVEL, GOAL, CHALLENGE, QUESTION, CONTEXT, URGENCY, ANSWER_MODE, CONFIRM, QUICK_QUESTION = range(10)

MAIN_MENU = [["Ask for mentorship"], ["How it works"]]
TRACK_MENU = [["AI / LLMs", "Python"], ["Backend", "Frontend"], ["Career", "General"]]
LEVEL_MENU = [["Beginner", "Intermediate", "Advanced"]]
URGENCY_MENU = [["Low", "Normal", "High"]]
ANSWER_MODE_MENU = [["Private", "Public"]]
CONFIRM_MENU = [["Submit", "Restart"], ["Cancel"]]

TRACK_CHOICES = {item for row in TRACK_MENU for item in row}
LEVEL_CHOICES = {item for row in LEVEL_MENU for item in row}
URGENCY_CHOICES = {item for row in URGENCY_MENU for item in row}
ANSWER_MODE_CHOICES = {item for row in ANSWER_MODE_MENU for item in row}

USER_COMMANDS = [
    BotCommand("start", "Open the mentorship bot"),
    BotCommand("ask", "Start a guided mentorship request"),
    BotCommand("help", "See how the bot works"),
    BotCommand("cancel", "Cancel the current guided request"),
    BotCommand("status", "Check one of your ticket statuses"),
]

SETUP_COMMANDS = USER_COMMANDS + [
    BotCommand("claimadmin", "Claim admin access for the bot"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand("adminstatus", "Show the current admin ID"),
    BotCommand("setdiscussion", "Bind the linked discussion group"),
    BotCommand("discussionstatus", "Show the linked discussion group"),
    BotCommand("stats", "Show mentorship request statistics"),
    BotCommand("reply", "Send a private answer to a ticket"),
    BotCommand("markpublic", "Mark a ticket as answered publicly"),
]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def parse_numeric_id(value: str) -> int | None:
    value = value.strip()
    if value and value.lstrip("-").isdigit():
        return int(value)
    return None


def build_keyboard(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_admin_id() -> int | None:
    ensure_data_dir()
    admin_id = parse_numeric_id(ADMIN_ID_RAW)
    if admin_id is not None:
        return admin_id
    if ADMIN_FILE.exists():
        stored_id = parse_numeric_id(ADMIN_FILE.read_text(encoding="utf-8"))
        if stored_id is not None:
            return stored_id
    return None


def save_admin_id(admin_id: int) -> None:
    ensure_data_dir()
    ADMIN_FILE.write_text(str(admin_id), encoding="utf-8")


def get_discussion_group_id() -> int | None:
    ensure_data_dir()
    discussion_group_id = parse_numeric_id(DISCUSSION_GROUP_ID_RAW)
    if discussion_group_id is not None:
        return discussion_group_id
    if DISCUSSION_FILE.exists():
        stored_id = parse_numeric_id(DISCUSSION_FILE.read_text(encoding="utf-8"))
        if stored_id is not None:
            return stored_id
    return None


def save_discussion_group_id(discussion_group_id: int) -> None:
    ensure_data_dir()
    DISCUSSION_FILE.write_text(str(discussion_group_id), encoding="utf-8")


async def sync_commands(application: Application) -> None:
    admin_id = application.bot_data.get("admin_id")
    await application.bot.set_my_commands(
        SETUP_COMMANDS if admin_id is None else USER_COMMANDS,
        scope=BotCommandScopeAllPrivateChats(),
    )

    if admin_id is not None:
        await application.bot.set_my_commands(
            ADMIN_COMMANDS,
            scope=BotCommandScopeChat(admin_id),
        )


def is_admin(context: ContextTypes.DEFAULT_TYPE, user_id: int | None) -> bool:
    admin_id = context.application.bot_data.get("admin_id")
    return admin_id is not None and user_id == admin_id


def is_discussion_group(context: ContextTypes.DEFAULT_TYPE, chat_id: int | None) -> bool:
    discussion_group_id = context.application.bot_data.get("discussion_group_id")
    return discussion_group_id is not None and chat_id == discussion_group_id


def read_submissions() -> list[dict]:
    ensure_data_dir()
    if not SUBMISSIONS_FILE.exists():
        return []

    submissions: list[dict] = []
    with SUBMISSIONS_FILE.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                submissions.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed submission line")
    return submissions


def write_submissions(submissions: list[dict]) -> None:
    ensure_data_dir()
    with SUBMISSIONS_FILE.open("w", encoding="utf-8") as handle:
        for submission in submissions:
            handle.write(json.dumps(submission, ensure_ascii=True) + "\n")


def next_submission_id() -> int:
    submissions = read_submissions()
    if not submissions:
        return 1
    return max(int(item.get("id", 0)) for item in submissions) + 1


def save_submission(record: dict) -> None:
    ensure_data_dir()
    with SUBMISSIONS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def timestamp_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def format_status(status: str) -> str:
    labels = {
        "open": "Open",
        "answered_private": "Answered privately",
        "answered_public": "Answered publicly",
    }
    return labels.get(status, status.replace("_", " ").title())


def build_public_notice(ticket_id: int, link: str) -> str:
    if link:
        return f"Your public answer for ticket #{ticket_id} is available here:\n{link}"
    if DISCUSSION_GROUP_URL:
        return (
            f"Your public answer for ticket #{ticket_id} is ready.\n"
            f"Check the discussion group: {DISCUSSION_GROUP_URL}"
        )
    if PUBLIC_CHANNEL_URL:
        return (
            f"Your public answer for ticket #{ticket_id} is ready.\n"
            f"Check the channel: {PUBLIC_CHANNEL_URL}"
        )
    return (
        f"Your public answer for ticket #{ticket_id} has been posted.\n"
        "Check the public channel for this ticket number."
    )


def build_public_answer_message(ticket_id: int, answer_text: str, link: str) -> str:
    lines = [f"Public answer for ticket #{ticket_id} has been posted."]
    if link:
        lines.append(f"Link: {link}")
    elif DISCUSSION_GROUP_URL:
        lines.append(f"Discussion group: {DISCUSSION_GROUP_URL}")
    elif PUBLIC_CHANNEL_URL:
        lines.append(f"Channel: {PUBLIC_CHANNEL_URL}")
    if answer_text:
        lines.append("")
        lines.append("Answer:")
        lines.append(answer_text)
    return "\n".join(lines)


def find_submission(ticket_id: int) -> tuple[list[dict], int | None, dict | None]:
    submissions = read_submissions()
    for index, submission in enumerate(submissions):
        if int(submission.get("id", 0)) == ticket_id:
            return submissions, index, submission
    return submissions, None, None


def find_submission_by_discussion_message(
    chat_id: int,
    message_id: int,
) -> tuple[list[dict], int | None, dict | None]:
    submissions = read_submissions()
    for index, submission in enumerate(submissions):
        discussion = submission.get("discussion", {})
        if discussion.get("chat_id") == chat_id and discussion.get("message_id") == message_id:
            return submissions, index, submission
    return submissions, None, None


def parse_ticket_id(value: str) -> int | None:
    return parse_numeric_id(value)


def build_submission_record(user, payload: dict, source: str) -> dict:
    return {
        "id": next_submission_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "display_time": timestamp_now(),
        "status": "open",
        "source": source,
        "user": {
            "id": user.id,
            "full_name": user.full_name or user.first_name or "Unknown user",
            "username": user.username or "",
        },
        "request": payload,
        "discussion": {"chat_id": None, "message_id": None},
        "responses": [],
    }


def format_submission(record: dict) -> str:
    user = record["user"]
    request = record["request"]
    username = f"@{user['username']}" if user["username"] else "No username"
    ticket_id = record["id"]

    return (
        f"Mentorship Ticket #{ticket_id}\n\n"
        f"Submitted: {record['display_time']}\n"
        f"Source: {record['source']}\n\n"
        f"Name: {user['full_name']}\n"
        f"Username: {username}\n"
        f"User ID: {user['id']}\n\n"
        f"Track: {request['track']}\n"
        f"Level: {request['level']}\n"
        f"Goal: {request['goal']}\n\n"
        f"Challenge:\n{request['challenge']}\n\n"
        f"Question:\n{request['question']}\n\n"
        f"Context:\n{request['context']}\n\n"
        f"Urgency: {request['urgency']}\n"
        f"Preferred answer: {request['answer_mode']}\n"
        f"Status: {format_status(record.get('status', 'open'))}\n\n"
        f"Admin actions:\n"
        f"/reply {ticket_id} your private answer\n"
        f"/markpublic {ticket_id} https://t.me/yourchannel/123"
    )


def format_discussion_ticket(record: dict) -> str:
    user = record["user"]
    request = record["request"]
    username = f"@{user['username']}" if user["username"] else "No username"

    return (
        f"Public Mentorship Ticket #{record['id']}\n\n"
        f"Name: {user['full_name']}\n"
        f"Username: {username}\n"
        f"Track: {request['track']}\n"
        f"Level: {request['level']}\n"
        f"Urgency: {request['urgency']}\n\n"
        f"Goal:\n{request['goal']}\n\n"
        f"Challenge:\n{request['challenge']}\n\n"
        f"Question:\n{request['question']}\n\n"
        f"Context:\n{request['context']}\n\n"
        "Reply to this message with the public answer to close the ticket."
    )


def build_summary(payload: dict) -> str:
    return (
        "Review your mentorship request:\n\n"
        f"Track: {payload['track']}\n"
        f"Level: {payload['level']}\n"
        f"Goal: {payload['goal']}\n\n"
        f"Challenge:\n{payload['challenge']}\n\n"
        f"Question:\n{payload['question']}\n\n"
        f"Context:\n{payload['context']}\n\n"
        f"Urgency: {payload['urgency']}\n"
        f"Preferred answer: {payload['answer_mode']}\n\n"
        "Send Submit to deliver it, Restart to begin again, or Cancel to stop."
    )


def build_user_status(record: dict) -> str:
    request = record["request"]
    lines = [
        f"Ticket #{record['id']}",
        f"Status: {format_status(record.get('status', 'open'))}",
        f"Submitted: {record.get('display_time', 'Unknown')}",
        f"Track: {request.get('track', 'General')}",
        f"Preferred answer: {request.get('answer_mode', 'Private')}",
    ]

    responses = record.get("responses", [])
    if responses:
        latest = responses[-1]
        lines.append(f"Latest update: {format_status(record.get('status', 'open'))}")
        if latest.get("mode") == "public" and latest.get("link"):
            lines.append(f"Public link: {latest['link']}")
        elif latest.get("mode") == "public_discussion" and latest.get("link"):
            lines.append(f"Discussion link: {latest['link']}")
        elif latest.get("mode") == "public" and DISCUSSION_GROUP_URL:
            lines.append(f"Discussion group: {DISCUSSION_GROUP_URL}")
        elif latest.get("mode") == "public_discussion" and DISCUSSION_GROUP_URL:
            lines.append(f"Discussion group: {DISCUSSION_GROUP_URL}")
        elif latest.get("mode") == "public" and PUBLIC_CHANNEL_URL:
            lines.append(f"Channel: {PUBLIC_CHANNEL_URL}")
        elif latest.get("mode") == "public_discussion":
            lines.append("Discussion answer has been posted.")

    if record.get("status") == "answered_public" and PUBLIC_CHANNEL_URL and not responses:
        lines.append(f"Channel: {PUBLIC_CHANNEL_URL}")

    discussion = record.get("discussion", {})
    if discussion.get("message_id") and record.get("status") == "open":
        lines.append("Public ticket is queued in the discussion group.")

    return "\n".join(lines)


async def deliver_submission(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    payload: dict,
    source: str,
) -> bool:
    if update.effective_user is None or update.message is None:
        return False

    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is None:
        await update.message.reply_text(
            "The mentor has not finished setup yet. Please try again soon.",
            reply_markup=build_keyboard(MAIN_MENU),
        )
        return False

    record = build_submission_record(update.effective_user, payload, source)
    discussion_group_id = context.application.bot_data.get("discussion_group_id")
    discussion_posted = False

    try:
        await context.bot.send_message(chat_id=admin_id, text=format_submission(record))
    except TelegramError:
        logger.exception("Failed to forward mentorship request")
        await update.message.reply_text(
            "I could not deliver your request right now. Please try again in a moment.",
            reply_markup=build_keyboard(MAIN_MENU),
        )
        return False

    if payload["answer_mode"] == "Public" and discussion_group_id is not None:
        try:
            discussion_message = await context.bot.send_message(
                chat_id=discussion_group_id,
                text=format_discussion_ticket(record),
            )
            record["discussion"] = {
                "chat_id": discussion_message.chat_id,
                "message_id": discussion_message.message_id,
            }
            discussion_posted = True
        except TelegramError:
            logger.exception("Failed to mirror public ticket to discussion group")

    save_submission(record)
    public_note = ""
    if payload["answer_mode"] == "Public":
        if discussion_posted:
            public_note = (
                f"\nYour ticket was also posted to the linked discussion group as ticket #{record['id']}."
            )
        else:
            public_note = (
                f"\nIf the answer is posted publicly, look for ticket #{record['id']}"
                + (f" in {PUBLIC_CHANNEL_URL}" if PUBLIC_CHANNEL_URL else " in the public discussion.")
            )
    else:
        public_note = f"\nIf needed, the mentor can answer you privately on Telegram for ticket #{record['id']}."
    await update.message.reply_text(
        f"Your mentorship request has been sent successfully.\n"
        f"Ticket: #{record['id']}\n"
        f"Preferred answer: {payload['answer_mode']}{public_note}",
        reply_markup=build_keyboard(MAIN_MENU),
    )
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if context.application.bot_data.get("admin_id") is None:
        await update.message.reply_text(
            "This mentorship bot is almost ready.\n"
            "If you are the owner, send /claimadmin once from your Telegram account.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text(
            "Admin mode is active.\n"
            "Use /stats to view submission counts and wait for incoming mentorship requests.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await update.message.reply_text(
        f"Welcome to {MENTOR_USERNAME}'s mentorship bot.\n"
        "You can send a quick question directly, or choose Ask for mentorship for a guided request.\n"
        "Each request gets a ticket number, and you can choose whether the answer should be private or public.",
        reply_markup=build_keyboard(MAIN_MENU),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text(
            "/adminstatus shows the current admin.\n"
            "/setdiscussion binds the linked discussion group.\n"
            "/discussionstatus shows the linked discussion group.\n"
            "/stats shows mentorship request counts.\n"
            "/reply <ticket> <message> sends a private answer.\n"
            "/markpublic <ticket> [link] marks a public answer.\n"
            "/start refreshes the admin view.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await update.message.reply_text(
        "Send a question directly for a quick submission.\n"
        "Use /ask for a guided mentorship request with track, level, goal, and urgency.\n"
        "You will be asked whether you want the answer privately or publicly.\n"
        "Use /status <ticket_number> to check one of your ticket statuses.\n"
        f"Public updates may appear in {PUBLIC_CHANNEL_URL} or the linked discussion group.\n"
        "Use /cancel any time during the guided flow.",
        reply_markup=build_keyboard(MAIN_MENU),
    )


async def claim_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if user is None or update.message is None:
        return

    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is not None:
        if user.id == admin_id:
            await update.message.reply_text("You are already the admin.")
        else:
            await update.message.reply_text("An admin is already configured for this bot.")
        return

    context.application.bot_data["admin_id"] = user.id
    save_admin_id(user.id)
    await sync_commands(context.application)
    await update.message.reply_text(
        "Admin saved successfully.\n"
        "The mentorship bot is ready to receive requests.\n"
        "If you use a linked discussion group for public answers, run /setdiscussion there once.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is None:
        await update.message.reply_text("No admin is configured yet. Send /claimadmin to set one.")
        return

    await update.message.reply_text(f"Current admin ID: {admin_id}")


async def set_discussion_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None or update.effective_chat is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    if update.effective_chat.type not in {"group", "supergroup"}:
        await update.message.reply_text(
            "Open the linked discussion group and run /setdiscussion there."
        )
        return

    discussion_group_id = update.effective_chat.id
    context.application.bot_data["discussion_group_id"] = discussion_group_id
    save_discussion_group_id(discussion_group_id)
    await update.message.reply_text(
        f"Discussion group saved successfully.\nGroup ID: {discussion_group_id}"
    )


async def discussion_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    discussion_group_id = context.application.bot_data.get("discussion_group_id")
    if discussion_group_id is None:
        await update.message.reply_text(
            "No discussion group is linked yet. Run /setdiscussion inside the linked group."
        )
        return

    await update.message.reply_text(f"Current discussion group ID: {discussion_group_id}")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("This command is available only to the admin.")
        return

    submissions = read_submissions()
    if not submissions:
        await update.message.reply_text("No mentorship requests have been submitted yet.")
        return

    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=7)
    recent_count = 0
    track_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()

    for submission in submissions:
        request = submission.get("request", {})
        track = request.get("track", "Unknown")
        track_counter[track] += 1
        status_counter[submission.get("status", "open")] += 1

        created_at = submission.get("created_at")
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at)
                if created_dt >= recent_cutoff:
                    recent_count += 1
            except ValueError:
                logger.warning("Skipping malformed timestamp in submissions file")

    top_tracks = "\n".join(
        f"- {track}: {count}" for track, count in track_counter.most_common(5)
    )

    await update.message.reply_text(
        f"Total requests: {len(submissions)}\n"
        f"Last 7 days: {recent_count}\n\n"
        f"Open: {status_counter.get('open', 0)}\n"
        f"Answered privately: {status_counter.get('answered_private', 0)}\n"
        f"Answered publicly: {status_counter.get('answered_public', 0)}\n\n"
        f"Top tracks:\n{top_tracks}"
    )


def reset_request(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["request"] = {}
    context.user_data["intake_mode"] = ""


async def start_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    if is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text(
            "Admin mode is active. This guided mentorship flow is for users.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    if context.application.bot_data.get("admin_id") is None:
        await update.message.reply_text(
            "The mentor has not finished setup yet. Please try again soon.",
            reply_markup=build_keyboard(MAIN_MENU),
        )
        return ConversationHandler.END

    reset_request(context)
    context.user_data["intake_mode"] = "guided"
    await update.message.reply_text(
        "Choose the mentorship track that fits your request best.",
        reply_markup=build_keyboard(TRACK_MENU),
    )
    return TRACK


async def start_quick_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END

    if is_admin(context, update.effective_user.id):
        await update.message.reply_text(
            "Admin mode is active.\nUse /stats, /reply, or /markpublic to manage tickets.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    if context.application.bot_data.get("admin_id") is None:
        await update.message.reply_text(
            "The mentor has not finished setup yet. Please try again soon.",
            reply_markup=build_keyboard(MAIN_MENU),
        )
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    if not text:
        return ConversationHandler.END

    reset_request(context)
    context.user_data["intake_mode"] = "quick"
    context.user_data["request"] = {
        "track": "General",
        "level": "Not provided",
        "goal": "Not provided",
        "challenge": "Not provided",
        "question": text,
        "context": "No extra context",
        "urgency": "Normal",
    }
    await update.message.reply_text(
        "Do you want the answer sent privately or posted publicly with your ticket number?",
        reply_markup=build_keyboard(ANSWER_MODE_MENU),
    )
    return ANSWER_MODE


async def capture_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return TRACK

    track = (update.message.text or "").strip()
    if track not in TRACK_CHOICES:
        await update.message.reply_text(
            "Please choose one of the track options from the keyboard.",
            reply_markup=build_keyboard(TRACK_MENU),
        )
        return TRACK

    context.user_data["request"]["track"] = track
    await update.message.reply_text(
        "What is your current level in this area?",
        reply_markup=build_keyboard(LEVEL_MENU),
    )
    return LEVEL


async def capture_level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return LEVEL

    level = (update.message.text or "").strip()
    if level not in LEVEL_CHOICES:
        await update.message.reply_text(
            "Please choose Beginner, Intermediate, or Advanced.",
            reply_markup=build_keyboard(LEVEL_MENU),
        )
        return LEVEL

    context.user_data["request"]["level"] = level
    await update.message.reply_text(
        "What outcome are you trying to achieve?",
        reply_markup=ReplyKeyboardRemove(),
    )
    return GOAL


async def capture_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return GOAL

    goal = (update.message.text or "").strip()
    if not goal:
        await update.message.reply_text("Please write a short goal so the mentor has context.")
        return GOAL

    context.user_data["request"]["goal"] = goal
    await update.message.reply_text("What is the main challenge or blocker right now?")
    return CHALLENGE


async def capture_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return CHALLENGE

    challenge = (update.message.text or "").strip()
    if not challenge:
        await update.message.reply_text("Please describe the challenge you are facing.")
        return CHALLENGE

    context.user_data["request"]["challenge"] = challenge
    await update.message.reply_text("Write your mentorship question as clearly as you can.")
    return QUESTION


async def capture_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return QUESTION

    question = (update.message.text or "").strip()
    if not question:
        await update.message.reply_text("Please send the question you want help with.")
        return QUESTION

    context.user_data["request"]["question"] = question
    await update.message.reply_text(
        "Share any extra context, links, or code snippets.\n"
        "If there is nothing else to add, send Skip."
    )
    return CONTEXT


async def capture_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return CONTEXT

    context_text = (update.message.text or "").strip()
    context.user_data["request"]["context"] = context_text if context_text.lower() != "skip" else "No extra context"
    await update.message.reply_text(
        "How urgent is this request?",
        reply_markup=build_keyboard(URGENCY_MENU),
    )
    return URGENCY


async def capture_urgency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return URGENCY

    urgency = (update.message.text or "").strip()
    if urgency not in URGENCY_CHOICES:
        await update.message.reply_text(
            "Please choose Low, Normal, or High.",
            reply_markup=build_keyboard(URGENCY_MENU),
        )
        return URGENCY

    context.user_data["request"]["urgency"] = urgency
    await update.message.reply_text(
        "Do you want the answer sent privately or posted publicly with your ticket number?",
        reply_markup=build_keyboard(ANSWER_MODE_MENU),
    )
    return ANSWER_MODE


async def capture_answer_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ANSWER_MODE

    answer_mode = (update.message.text or "").strip()
    if answer_mode not in ANSWER_MODE_CHOICES:
        await update.message.reply_text(
            "Please choose Private or Public.",
            reply_markup=build_keyboard(ANSWER_MODE_MENU),
        )
        return ANSWER_MODE

    context.user_data["request"]["answer_mode"] = answer_mode
    await update.message.reply_text(
        build_summary(context.user_data["request"]),
        reply_markup=build_keyboard(CONFIRM_MENU),
    )
    return CONFIRM


async def capture_quick_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return QUICK_QUESTION

    question = (update.message.text or "").strip()
    if not question:
        await update.message.reply_text("Please send the question you want to track.")
        return QUICK_QUESTION

    context.user_data["request"] = {
        "track": "General",
        "level": "Not provided",
        "goal": "Not provided",
        "challenge": "Not provided",
        "question": question,
        "context": "No extra context",
        "urgency": "Normal",
    }
    await update.message.reply_text(
        "Do you want the answer sent privately or posted publicly with your ticket number?",
        reply_markup=build_keyboard(ANSWER_MODE_MENU),
    )
    return ANSWER_MODE


async def confirm_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return CONFIRM

    decision = (update.message.text or "").strip()
    if decision == "Submit":
        source = "quick_message" if context.user_data.get("intake_mode") == "quick" else "guided_flow"
        sent = await deliver_submission(update, context, context.user_data["request"], source)
        reset_request(context)
        return ConversationHandler.END if sent else CONFIRM

    if decision == "Restart":
        if context.user_data.get("intake_mode") == "quick":
            reset_request(context)
            context.user_data["intake_mode"] = "quick"
            await update.message.reply_text(
                "Send your question again to create a new tracked ticket.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return QUICK_QUESTION
        return await start_request(update, context)

    if decision == "Cancel":
        return await cancel_request(update, context)

    await update.message.reply_text(
        "Please choose Submit, Restart, or Cancel.",
        reply_markup=build_keyboard(CONFIRM_MENU),
    )
    return CONFIRM


async def cancel_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reset_request(context)
    if update.message is not None:
        await update.message.reply_text(
            "Your current mentorship request was cancelled.",
            reply_markup=build_keyboard(MAIN_MENU),
        )
    return ConversationHandler.END


async def show_help_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await help_command(update, context)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not context.args:
        await update.message.reply_text("Usage: /status <ticket_number>")
        return

    ticket_id = parse_ticket_id(context.args[0])
    if ticket_id is None:
        await update.message.reply_text("Ticket numbers must be numeric.")
        return

    _, _, submission = find_submission(ticket_id)
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    is_ticket_owner = submission.get("user", {}).get("id") == update.effective_user.id
    if not is_ticket_owner and not is_admin(context, update.effective_user.id):
        await update.message.reply_text("You can only check your own tickets.")
        return

    await update.message.reply_text(build_user_status(submission))


async def reply_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /reply <ticket_number> <message>")
        return

    ticket_id = parse_ticket_id(context.args[0])
    if ticket_id is None:
        await update.message.reply_text("Ticket numbers must be numeric.")
        return

    answer_text = " ".join(context.args[1:]).strip()
    if not answer_text:
        await update.message.reply_text("Please include the private answer after the ticket number.")
        return

    submissions, index, submission = find_submission(ticket_id)
    if submission is None or index is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    user_id = submission.get("user", {}).get("id")
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"Private answer for ticket #{ticket_id}\n\n"
                f"{answer_text}"
            ),
        )
    except TelegramError:
        logger.exception("Failed to send private answer")
        await update.message.reply_text(
            f"I could not deliver the private answer for ticket #{ticket_id}."
        )
        return

    submission["status"] = "answered_private"
    submission["updated_at"] = datetime.now(timezone.utc).isoformat()
    submission.setdefault("responses", []).append(
        {
            "mode": "private",
            "text": answer_text,
            "created_at": submission["updated_at"],
        }
    )
    submissions[index] = submission
    write_submissions(submissions)
    await update.message.reply_text(f"Private answer sent for ticket #{ticket_id}.")


async def mark_public(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id: int | None = None
    public_link = ""
    submissions: list[dict]
    index: int | None
    submission: dict | None

    if context.args:
        ticket_id = parse_ticket_id(context.args[0])
        if ticket_id is None:
            await update.message.reply_text("Ticket numbers must be numeric.")
            return
        public_link = context.args[1].strip() if len(context.args) > 1 else ""
        submissions, index, submission = find_submission(ticket_id)
    elif update.message.reply_to_message and is_discussion_group(
        context, update.effective_chat.id if update.effective_chat else None
    ):
        submissions, index, submission = find_submission_by_discussion_message(
            update.effective_chat.id,
            update.message.reply_to_message.message_id,
        )
        if submission is not None:
            ticket_id = int(submission["id"])
    else:
        await update.message.reply_text("Usage: /markpublic <ticket_number> [public_post_link]")
        return

    if submission is None or index is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    user_id = submission.get("user", {}).get("id")
    notice_text = build_public_notice(ticket_id, public_link)

    try:
        await context.bot.send_message(chat_id=user_id, text=notice_text)
    except TelegramError:
        logger.exception("Failed to send public-answer notice")
        await update.message.reply_text(
            f"I could not notify the user about the public answer for ticket #{ticket_id}."
        )
        return

    submission["status"] = "answered_public"
    submission["updated_at"] = datetime.now(timezone.utc).isoformat()
    submission.setdefault("responses", []).append(
        {
            "mode": "public",
            "link": public_link,
            "created_at": submission["updated_at"],
        }
    )
    submissions[index] = submission
    write_submissions(submissions)
    await update.message.reply_text(f"Ticket #{ticket_id} marked as answered publicly.")


async def handle_discussion_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None or update.effective_chat is None:
        return

    if not is_admin(context, update.effective_user.id):
        return

    if not is_discussion_group(context, update.effective_chat.id):
        return

    if update.message.reply_to_message is None:
        return

    answer_text = (update.message.text or "").strip()
    if not answer_text:
        return

    submissions, index, submission = find_submission_by_discussion_message(
        update.effective_chat.id,
        update.message.reply_to_message.message_id,
    )
    if submission is None or index is None:
        return

    ticket_id = int(submission["id"])
    user_id = submission.get("user", {}).get("id")
    public_link = getattr(update.message, "link", "") or ""
    notice_text = build_public_answer_message(ticket_id, answer_text, public_link)

    try:
        await context.bot.send_message(chat_id=user_id, text=notice_text)
    except TelegramError:
        logger.exception("Failed to send discussion-group public answer")
        await update.message.reply_text(
            f"I could not notify the user about the public answer for ticket #{ticket_id}."
        )
        return

    submission["status"] = "answered_public"
    submission["updated_at"] = datetime.now(timezone.utc).isoformat()
    submission.setdefault("responses", []).append(
        {
            "mode": "public_discussion",
            "text": answer_text,
            "link": public_link,
            "created_at": submission["updated_at"],
        }
    )
    submissions[index] = submission
    write_submissions(submissions)
    await update.message.reply_text(f"Public discussion reply recorded for ticket #{ticket_id}.")


async def delete_join_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_chat is None:
        return

    if update.effective_chat.type not in {"group", "supergroup"}:
        return

    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
    except TelegramError:
        logger.exception("Failed to delete new-member service message")


async def post_init(application: Application) -> None:
    application.bot_data["admin_id"] = get_admin_id()
    application.bot_data["discussion_group_id"] = get_discussion_group_id()
    await sync_commands(application)


def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN is missing. Set it in Railway Variables for deployment or in the local .env file."
        )

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("ask", start_request, filters=filters.ChatType.PRIVATE),
            MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r"^Ask for mentorship$"), start_request),
            MessageHandler(
                filters.ChatType.PRIVATE
                & filters.TEXT
                & ~filters.COMMAND
                & ~filters.Regex(r"^Ask for mentorship$")
                & ~filters.Regex(r"^How it works$"),
                start_quick_request,
            ),
        ],
        states={
            TRACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_track)],
            LEVEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_level)],
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_goal)],
            CHALLENGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_challenge)],
            QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_question)],
            CONTEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_context)],
            URGENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_urgency)],
            ANSWER_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_answer_mode)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_request)],
            QUICK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_quick_question)],
        },
        fallbacks=[CommandHandler("cancel", cancel_request)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("claimadmin", claim_admin))
    app.add_handler(CommandHandler("adminstatus", admin_status))
    app.add_handler(CommandHandler("setdiscussion", set_discussion_group))
    app.add_handler(CommandHandler("discussionstatus", discussion_status))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reply", reply_ticket))
    app.add_handler(CommandHandler("markpublic", mark_public))
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.StatusUpdate.NEW_CHAT_MEMBERS,
            delete_join_messages,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS & filters.REPLY & filters.TEXT & ~filters.COMMAND,
            handle_discussion_reply,
        )
    )
    app.add_handler(MessageHandler(filters.Regex(r"^How it works$"), show_help_message))
    app.add_handler(conversation)
    app.add_handler(CommandHandler("cancel", cancel_request))

    logger.info("Mentorship bot is starting")
    app.run_polling()


if __name__ == "__main__":
    main()
