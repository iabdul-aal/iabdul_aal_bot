import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

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

DEFAULT_MENTOR_LABEL = "your mentor"

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID_RAW = (os.getenv("ADMIN_ID") or "").strip()
MENTOR_LABEL = (os.getenv("MENTOR_LABEL") or DEFAULT_MENTOR_LABEL).strip()
PUBLIC_CHANNEL_URL = (os.getenv("PUBLIC_CHANNEL_URL") or "").strip()
DISCUSSION_GROUP_URL = (os.getenv("DISCUSSION_GROUP_URL") or "").strip()
DISCUSSION_GROUP_ID_RAW = (os.getenv("DISCUSSION_GROUP_ID") or "").strip()
PUBLIC_CHANNEL_ID_RAW = (os.getenv("PUBLIC_CHANNEL_ID") or "").strip()
DATA_DIR = Path(
    os.getenv("DATA_DIR")
    or os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    or Path(__file__).with_name("data")
)
ADMIN_FILE = DATA_DIR / "admin_id.txt"
DISCUSSION_FILE = DATA_DIR / "discussion_group_id.txt"
PUBLIC_CHANNEL_FILE = DATA_DIR / "public_channel_id.txt"
COUNTER_FILE = DATA_DIR / "ticket_counter.txt"
SUBMISSIONS_FILE = DATA_DIR / "submissions.jsonl"

TRACK, LEVEL, GOAL, CHALLENGE, QUESTION, CONTEXT, URGENCY, ANSWER_MODE, CONFIRM, QUICK_QUESTION = range(10)

GUIDED_REQUEST_LABEL = "Guided request"
QUICK_QUESTION_LABEL = "Quick question"
HOW_IT_WORKS_LABEL = "How it works"
PRIVATE_REPLY_LABEL = "Private reply"
PUBLIC_ANSWER_LABEL = "Public answer"
SUBMIT_LABEL = "Submit"
RESTART_LABEL = "Restart"
CANCEL_LABEL = "Cancel"
SKIP_LABEL = "Skip"

MAIN_MENU = [[GUIDED_REQUEST_LABEL, QUICK_QUESTION_LABEL], [HOW_IT_WORKS_LABEL]]
TRACK_MENU = [["AI / LLMs", "Python"], ["Backend", "Frontend"], ["Career", "General"]]
LEVEL_MENU = [["Beginner", "Intermediate", "Advanced"]]
URGENCY_MENU = [["Low", "Normal", "High"]]
ANSWER_MODE_MENU = [[PRIVATE_REPLY_LABEL, PUBLIC_ANSWER_LABEL]]
CONFIRM_MENU = [[SUBMIT_LABEL, RESTART_LABEL], [CANCEL_LABEL]]
SKIP_MENU = [[SKIP_LABEL]]

TRACK_CHOICES = {item for row in TRACK_MENU for item in row}
LEVEL_CHOICES = {item for row in LEVEL_MENU for item in row}
URGENCY_CHOICES = {item for row in URGENCY_MENU for item in row}
ANSWER_MODE_CHOICES = {item for row in ANSWER_MODE_MENU for item in row}

USER_COMMANDS = [
    BotCommand("start", "Open the mentorship bot"),
    BotCommand("ask", "Start a guided mentorship request"),
    BotCommand("quick", "Send a one-message question"),
    BotCommand("help", "See how the bot works"),
    BotCommand("cancel", "Cancel the current request"),
    BotCommand("status", "Check one of your ticket statuses"),
]

SETUP_COMMANDS = USER_COMMANDS + [
    BotCommand("claimadmin", "Claim admin access for the bot"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand("adminstatus", "Show the current admin ID"),
    BotCommand("setdiscussion", "Bind the linked discussion group"),
    BotCommand("discussionstatus", "Show the linked discussion group"),
    BotCommand("setchannel", "Bind the public answer channel"),
    BotCommand("channelstatus", "Show the public answer channel"),
    BotCommand("stats", "Show mentorship request statistics"),
    BotCommand("reply", "Send a private answer to a ticket"),
    BotCommand("replypublic", "Post a public answer through the bot"),
    BotCommand("markpublic", "Mark a ticket as answered publicly"),
]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

STORAGE_LOCK = Lock()


def parse_numeric_id(value: str) -> int | None:
    value = value.strip()
    if value and value.lstrip("-").isdigit():
        return int(value)
    return None


def build_keyboard(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_numeric_id(raw_value: str, file_path: Path) -> int | None:
    ensure_data_dir()
    numeric_id = parse_numeric_id(raw_value)
    if numeric_id is not None:
        return numeric_id
    if file_path.exists():
        stored_id = parse_numeric_id(file_path.read_text(encoding="utf-8"))
        if stored_id is not None:
            return stored_id
    return None


def save_numeric_id(file_path: Path, numeric_id: int) -> None:
    ensure_data_dir()
    file_path.write_text(str(numeric_id), encoding="utf-8")


def get_admin_id() -> int | None:
    return load_numeric_id(ADMIN_ID_RAW, ADMIN_FILE)


def save_admin_id(admin_id: int) -> None:
    save_numeric_id(ADMIN_FILE, admin_id)


def get_discussion_group_id() -> int | None:
    return load_numeric_id(DISCUSSION_GROUP_ID_RAW, DISCUSSION_FILE)


def save_discussion_group_id(discussion_group_id: int) -> None:
    save_numeric_id(DISCUSSION_FILE, discussion_group_id)


def get_public_channel_id() -> int | None:
    return load_numeric_id(PUBLIC_CHANNEL_ID_RAW, PUBLIC_CHANNEL_FILE)


def save_public_channel_id(public_channel_id: int) -> None:
    save_numeric_id(PUBLIC_CHANNEL_FILE, public_channel_id)


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


async def admin_can_manage_chat(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    user_id: int | None,
) -> bool:
    if is_admin(context, user_id):
        return True

    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is None:
        return False

    try:
        admin_member = await context.bot.get_chat_member(chat_id=chat_id, user_id=admin_id)
    except TelegramError:
        logger.exception("Failed to verify configured admin access for chat %s", chat_id)
        return False

    return admin_member.status in {"administrator", "creator"}


def _read_submissions_unlocked() -> list[dict]:
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


def read_submissions() -> list[dict]:
    with STORAGE_LOCK:
        return _read_submissions_unlocked()


def write_submissions(submissions: list[dict]) -> None:
    ensure_data_dir()
    temp_file = SUBMISSIONS_FILE.with_suffix(".tmp")
    with STORAGE_LOCK:
        with temp_file.open("w", encoding="utf-8") as handle:
            for submission in submissions:
                handle.write(json.dumps(submission, ensure_ascii=True) + "\n")
        os.replace(temp_file, SUBMISSIONS_FILE)


def reserve_submission_id() -> int:
    ensure_data_dir()
    with STORAGE_LOCK:
        current_id = parse_numeric_id(COUNTER_FILE.read_text(encoding="utf-8")) if COUNTER_FILE.exists() else None
        if current_id is None:
            submissions = _read_submissions_unlocked()
            current_id = max((int(item.get("id", 0)) for item in submissions), default=0)
        next_id = current_id + 1
        COUNTER_FILE.write_text(str(next_id), encoding="utf-8")
        return next_id


def save_submission(record: dict) -> None:
    ensure_data_dir()
    with STORAGE_LOCK:
        submissions = _read_submissions_unlocked()
        submissions.append(record)
        temp_file = SUBMISSIONS_FILE.with_suffix(".tmp")
        with temp_file.open("w", encoding="utf-8") as handle:
            for submission in submissions:
                handle.write(json.dumps(submission, ensure_ascii=True) + "\n")
        os.replace(temp_file, SUBMISSIONS_FILE)


def append_response(ticket_id: int, status: str, response: dict) -> dict | None:
    with STORAGE_LOCK:
        submissions = _read_submissions_unlocked()
        for index, submission in enumerate(submissions):
            if int(submission.get("id", 0)) != ticket_id:
                continue
            updated_at = datetime.now(timezone.utc).isoformat()
            submission["status"] = status
            submission["updated_at"] = updated_at
            response_record = dict(response)
            response_record["created_at"] = updated_at
            submission.setdefault("responses", []).append(response_record)
            submissions[index] = submission
            temp_file = SUBMISSIONS_FILE.with_suffix(".tmp")
            with temp_file.open("w", encoding="utf-8") as handle:
                for item in submissions:
                    handle.write(json.dumps(item, ensure_ascii=True) + "\n")
            os.replace(temp_file, SUBMISSIONS_FILE)
            return submission
    return None


def timestamp_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def format_status(status: str) -> str:
    labels = {
        "open": "Open",
        "answered_private": "Answered privately",
        "answered_public": "Answered publicly",
    }
    return labels.get(status, status.replace("_", " ").title())


def normalize_answer_mode(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered in {"public", PUBLIC_ANSWER_LABEL.lower()}:
        return "public"
    return "private"


def format_answer_mode(value: str) -> str:
    return PUBLIC_ANSWER_LABEL if normalize_answer_mode(value) == "public" else PRIVATE_REPLY_LABEL


def format_source(value: str) -> str:
    labels = {
        "guided_flow": "Guided request",
        "quick_message": "Quick question",
    }
    return labels.get(value, value.replace("_", " ").title())


def clean_text(value: str, fallback: str) -> str:
    text = (value or "").strip()
    return text if text else fallback


def trim_text(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def sanitize_public_text(value: str, limit: int) -> str:
    text = clean_text(value, "")
    if not text:
        return ""
    text = re.sub(r"https?://\S+|www\.\S+", "[link removed]", text, flags=re.IGNORECASE)
    text = re.sub(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[email removed]", text, flags=re.IGNORECASE)
    text = re.sub(r"\+?\d[\d\s().-]{7,}\d", "[number removed]", text)
    text = re.sub(r"@\w{3,}", "[handle removed]", text)
    return trim_text(text, limit)


def build_public_prompt(payload: dict) -> str:
    sections: list[str] = []
    goal = sanitize_public_text(payload.get("goal", ""), 180)
    challenge = sanitize_public_text(payload.get("challenge", ""), 220)
    question = sanitize_public_text(payload.get("question", ""), 420)

    if goal and goal != "Not provided":
        sections.append(f"Goal:\n{goal}")
    if challenge and challenge != "Not provided":
        sections.append(f"Focus:\n{challenge}")
    if question:
        sections.append(f"Question:\n{question}")

    if not sections:
        sections.append("Question:\nPublic answer requested.")
    return "\n\n".join(sections)


def build_public_destination_text() -> str:
    destinations: list[str] = []
    if DISCUSSION_GROUP_URL:
        destinations.append(f"discussion group: {DISCUSSION_GROUP_URL}")
    if PUBLIC_CHANNEL_URL:
        destinations.append(f"channel: {PUBLIC_CHANNEL_URL}")
    if not destinations:
        return "the public channel or discussion once configured"
    return " or ".join(destinations)


def step_text(step: int, total: int, body: str) -> str:
    return f"Step {step}/{total}\n{body}"


def build_public_notice(ticket_id: int, link: str) -> str:
    if link:
        return f"Your public answer for ticket #{ticket_id} is ready:\n{link}"
    return (
        f"Your public answer for ticket #{ticket_id} has been posted.\n"
        f"Check {build_public_destination_text()}."
    )


def build_public_answer_message(ticket_id: int, answer_text: str, link: str) -> str:
    lines = [f"Public answer for ticket #{ticket_id}"]
    if answer_text:
        lines.extend(["", answer_text])
    if link:
        lines.extend(["", f"Link: {link}"])
    elif DISCUSSION_GROUP_URL or PUBLIC_CHANNEL_URL:
        lines.extend(["", f"Open: {build_public_destination_text()}"])
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


def normalize_payload(payload: dict) -> dict:
    return {
        "track": clean_text(payload.get("track", ""), "General"),
        "level": clean_text(payload.get("level", ""), "Not provided"),
        "goal": clean_text(payload.get("goal", ""), "Not provided"),
        "challenge": clean_text(payload.get("challenge", ""), "Not provided"),
        "question": clean_text(payload.get("question", ""), "Not provided"),
        "context": clean_text(payload.get("context", ""), "No extra context"),
        "urgency": clean_text(payload.get("urgency", ""), "Normal"),
        "answer_mode": normalize_answer_mode(payload.get("answer_mode", "")),
    }


def build_submission_record(user, payload: dict, source: str) -> dict:
    normalized_payload = normalize_payload(payload)
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": reserve_submission_id(),
        "created_at": now,
        "updated_at": now,
        "display_time": timestamp_now(),
        "status": "open",
        "source": source,
        "user": {
            "id": user.id,
            "display_name": user.full_name or user.first_name or "Unknown user",
            "username": user.username or "",
        },
        "request": normalized_payload,
        "public_request": build_public_prompt(normalized_payload),
        "discussion": {"chat_id": None, "message_id": None},
        "responses": [],
    }


def format_submission(record: dict) -> str:
    user = record.get("user", {})
    request = normalize_payload(record.get("request", {}))
    username = f"@{user['username']}" if user.get("username") else "Not provided"
    ticket_id = record.get("id", "Unknown")

    return (
        f"Mentorship Ticket #{ticket_id}\n\n"
        f"Submitted: {record.get('display_time', 'Unknown')}\n"
        f"Source: {format_source(record.get('source', 'guided_flow'))}\n"
        f"Status: {format_status(record.get('status', 'open'))}\n\n"
        f"Private contact\n"
        f"Display name: {user.get('display_name', 'Unknown user')}\n"
        f"Username: {username}\n"
        f"Telegram ID: {user.get('id', 'Unknown')}\n\n"
        f"Request\n"
        f"Track: {request['track']}\n"
        f"Level: {request['level']}\n"
        f"Urgency: {request['urgency']}\n"
        f"Reply mode: {format_answer_mode(request['answer_mode'])}\n\n"
        f"Goal: {request['goal']}\n\n"
        f"Challenge:\n{request['challenge']}\n\n"
        f"Question:\n{request['question']}\n\n"
        f"Context:\n{request['context']}\n\n"
        f"Public preview\n{record.get('public_request', build_public_prompt(request))}\n\n"
        f"Admin actions\n"
        f"/reply {ticket_id} your private answer\n"
        f"/replypublic {ticket_id} your public answer\n"
        f"/markpublic {ticket_id} https://t.me/yourpost"
    )


def format_discussion_ticket(record: dict) -> str:
    request = normalize_payload(record.get("request", {}))
    public_request = record.get("public_request") or build_public_prompt(request)

    return (
        f"Anonymous Mentorship Ticket #{record['id']}\n\n"
        f"Track: {request['track']}\n"
        f"Level: {request['level']}\n"
        f"Urgency: {request['urgency']}\n\n"
        f"{public_request}\n\n"
        "Reply here with the public answer to close the ticket."
    )


def build_summary(payload: dict) -> str:
    request = normalize_payload(payload)
    return (
        "Review your mentorship request:\n\n"
        f"Track: {request['track']}\n"
        f"Level: {request['level']}\n"
        f"Urgency: {request['urgency']}\n"
        f"Reply mode: {format_answer_mode(request['answer_mode'])}\n\n"
        f"Goal:\n{request['goal']}\n\n"
        f"Challenge:\n{request['challenge']}\n\n"
        f"Question:\n{request['question']}\n\n"
        f"Context:\n{request['context']}\n\n"
        "Send Submit to deliver it, Restart to begin again, or Cancel to stop."
    )


def build_user_status(record: dict) -> str:
    request = normalize_payload(record.get("request", {}))
    lines = [
        f"Ticket #{record['id']}",
        f"Status: {format_status(record.get('status', 'open'))}",
        f"Submitted: {record.get('display_time', 'Unknown')}",
        f"Track: {request.get('track', 'General')}",
        f"Reply mode: {format_answer_mode(request.get('answer_mode', 'private'))}",
    ]

    responses = record.get("responses", [])
    if responses:
        latest = responses[-1]
        if latest.get("mode") in {"public", "public_manual"} and latest.get("link"):
            lines.append(f"Public link: {latest['link']}")
        elif latest.get("mode") == "public_discussion" and latest.get("link"):
            lines.append(f"Public link: {latest['link']}")
        elif latest.get("mode") == "public_channel" and latest.get("link"):
            lines.append(f"Public link: {latest['link']}")
        elif latest.get("mode") in {"public", "public_manual"} and DISCUSSION_GROUP_URL:
            lines.append(f"Discussion group: {DISCUSSION_GROUP_URL}")
        elif latest.get("mode") == "public_discussion" and DISCUSSION_GROUP_URL:
            lines.append(f"Discussion group: {DISCUSSION_GROUP_URL}")
        elif latest.get("mode") == "public_channel" and PUBLIC_CHANNEL_URL:
            lines.append(f"Channel: {PUBLIC_CHANNEL_URL}")

    if record.get("status") == "answered_public" and PUBLIC_CHANNEL_URL and not responses:
        lines.append(f"Channel: {PUBLIC_CHANNEL_URL}")

    discussion = record.get("discussion", {})
    if discussion.get("message_id") and record.get("status") == "open":
        lines.append("Your anonymous public ticket is queued in the discussion group.")

    return "\n".join(lines)


async def post_public_answer(
    context: ContextTypes.DEFAULT_TYPE,
    submission: dict,
    answer_text: str,
) -> tuple[str, str]:
    ticket_id = int(submission.get("id", 0))
    message_text = f"Public answer for ticket #{ticket_id}\n\n{answer_text}"
    discussion = submission.get("discussion", {})
    discussion_chat_id = discussion.get("chat_id") or context.application.bot_data.get("discussion_group_id")
    reply_to_message_id = discussion.get("message_id")
    public_channel_id = context.application.bot_data.get("public_channel_id")

    if discussion_chat_id is not None:
        sent_message = await context.bot.send_message(
            chat_id=discussion_chat_id,
            text=message_text,
            reply_to_message_id=reply_to_message_id,
        )
        return "public_discussion", getattr(sent_message, "link", "") or ""

    if public_channel_id is not None:
        sent_message = await context.bot.send_message(
            chat_id=public_channel_id,
            text=message_text,
        )
        return "public_channel", getattr(sent_message, "link", "") or ""

    raise TelegramError("No public destination configured")


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

    if record["request"]["answer_mode"] == "public" and discussion_group_id is not None:
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
    if record["request"]["answer_mode"] == "public":
        if discussion_posted:
            public_note = (
                "\nYour identity stays private. A minimal anonymous version is now queued in the discussion group."
            )
        else:
            public_note = (
                "\nYour identity stays private. If the answer is posted publicly, it will appear in "
                f"{build_public_destination_text()}."
            )
    else:
        public_note = "\nYour request stays private and the answer will be delivered here."
    await update.message.reply_text(
        f"Your mentorship request has been sent.\n"
        f"Ticket: #{record['id']}\n"
        f"Reply mode: {format_answer_mode(record['request']['answer_mode'])}{public_note}",
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
            "Use /stats to review tickets, /reply for private answers, and /replypublic for public answers.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await update.message.reply_text(
        "Welcome to the mentorship bot.\n"
        f"Your request is delivered to {MENTOR_LABEL or DEFAULT_MENTOR_LABEL}.\n\n"
        f"{GUIDED_REQUEST_LABEL} walks you through a structured request.\n"
        f"{QUICK_QUESTION_LABEL} turns one message into a tracked ticket.\n\n"
        f"{PRIVATE_REPLY_LABEL} stays inside the bot.\n"
        f"{PUBLIC_ANSWER_LABEL} keeps your identity private and only shares a minimal anonymous version.",
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
            "/setchannel binds the public answer channel.\n"
            "/channelstatus shows the public answer channel.\n"
            "/stats shows mentorship request counts.\n"
            "/reply <ticket> <message> sends a private answer.\n"
            "/replypublic <ticket> <message> posts a public answer through the bot.\n"
            "/markpublic <ticket> [link] marks a public answer.\n"
            "/start refreshes the admin view.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await update.message.reply_text(
        f"{GUIDED_REQUEST_LABEL} collects track, level, goal, blocker, and urgency.\n"
        f"{QUICK_QUESTION_LABEL} is the fastest path for a one-message request.\n"
        f"{PRIVATE_REPLY_LABEL} keeps the request and answer inside the bot.\n"
        f"{PUBLIC_ANSWER_LABEL} shares only an anonymous, minimal public version.\n"
        "Use /status <ticket_number> to check one of your ticket statuses.\n"
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
        "If you use a linked discussion group or channel for public answers, run /setdiscussion or /setchannel there once.",
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
    message = update.effective_message
    if message is None or update.effective_chat is None:
        return

    if update.effective_chat.type not in {"group", "supergroup"}:
        await message.reply_text(
            "Open the linked discussion group and run /setdiscussion there."
        )
        return

    if not await admin_can_manage_chat(
        context,
        update.effective_chat.id,
        update.effective_user.id if update.effective_user else None,
    ):
        await message.reply_text(
            "This command is available only to the configured admin or from a chat that admin already manages."
        )
        return

    discussion_group_id = update.effective_chat.id
    context.application.bot_data["discussion_group_id"] = discussion_group_id
    save_discussion_group_id(discussion_group_id)
    await message.reply_text(
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


async def set_public_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or update.effective_chat is None:
        return

    if update.effective_chat.type != "channel":
        await message.reply_text("Open the public channel and run /setchannel there.")
        return

    if not await admin_can_manage_chat(
        context,
        update.effective_chat.id,
        update.effective_user.id if update.effective_user else None,
    ):
        await message.reply_text(
            "This command is available only to the configured admin or from a channel that admin already manages."
        )
        return

    public_channel_id = update.effective_chat.id
    context.application.bot_data["public_channel_id"] = public_channel_id
    save_public_channel_id(public_channel_id)
    await message.reply_text(
        f"Public channel saved successfully.\nChannel ID: {public_channel_id}"
    )


async def channel_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    public_channel_id = context.application.bot_data.get("public_channel_id")
    if public_channel_id is None:
        await update.message.reply_text(
            "No public channel is linked yet. Run /setchannel inside the channel."
        )
        return

    await update.message.reply_text(f"Current public channel ID: {public_channel_id}")


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
    answer_mode_counter: Counter[str] = Counter()

    for submission in submissions:
        request = normalize_payload(submission.get("request", {}))
        track = request.get("track", "Unknown")
        track_counter[track] += 1
        status_counter[submission.get("status", "open")] += 1
        answer_mode_counter[request.get("answer_mode", "private")] += 1

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
        f"Private reply preference: {answer_mode_counter.get('private', 0)}\n"
        f"Public answer preference: {answer_mode_counter.get('public', 0)}\n\n"
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
        step_text(1, 8, "Choose the track that fits your request best."),
        reply_markup=build_keyboard(TRACK_MENU),
    )
    return TRACK


async def begin_quick_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END

    if is_admin(context, update.effective_user.id):
        await update.message.reply_text(
            "Admin mode is active.\nUse /stats, /reply, or /replypublic to manage tickets.",
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
    context.user_data["intake_mode"] = "quick"
    await update.message.reply_text(
        step_text(
            1,
            2,
            "Send your question in one message.\nYou can include a short bit of context if it helps.",
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    return QUICK_QUESTION


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
        step_text(
            2,
            2,
            "How should the answer be delivered?\n"
            "Private reply stays inside the bot.\n"
            "Public answer keeps your identity private and shares only a minimal anonymous version.",
        ),
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
        step_text(2, 8, "What is your current level in this area?"),
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
        step_text(3, 8, "What outcome are you trying to achieve?"),
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
    await update.message.reply_text(step_text(4, 8, "What is the main challenge or blocker right now?"))
    return CHALLENGE


async def capture_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return CHALLENGE

    challenge = (update.message.text or "").strip()
    if not challenge:
        await update.message.reply_text("Please describe the challenge you are facing.")
        return CHALLENGE

    context.user_data["request"]["challenge"] = challenge
    await update.message.reply_text(step_text(5, 8, "Write your mentorship question as clearly as you can."))
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
        step_text(
            6,
            8,
            "Share any extra context, links, or code snippets.\n"
            f"If there is nothing else to add, send {SKIP_LABEL}.",
        ),
        reply_markup=build_keyboard(SKIP_MENU),
    )
    return CONTEXT


async def capture_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return CONTEXT

    context_text = (update.message.text or "").strip()
    context.user_data["request"]["context"] = (
        "No extra context" if context_text.lower() == SKIP_LABEL.lower() else clean_text(context_text, "No extra context")
    )
    await update.message.reply_text(
        step_text(7, 8, "How urgent is this request?"),
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
        step_text(
            8,
            8,
            "How should the answer be delivered?\n"
            "Private reply stays inside the bot.\n"
            "Public answer keeps your identity private and shares only a minimal anonymous version.",
        ),
        reply_markup=build_keyboard(ANSWER_MODE_MENU),
    )
    return ANSWER_MODE


async def capture_answer_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ANSWER_MODE

    answer_mode = (update.message.text or "").strip()
    if answer_mode not in ANSWER_MODE_CHOICES:
        await update.message.reply_text(
            f"Please choose {PRIVATE_REPLY_LABEL} or {PUBLIC_ANSWER_LABEL}.",
            reply_markup=build_keyboard(ANSWER_MODE_MENU),
        )
        return ANSWER_MODE

    context.user_data["request"]["answer_mode"] = normalize_answer_mode(answer_mode)
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
        step_text(
            2,
            2,
            "How should the answer be delivered?\n"
            "Private reply stays inside the bot.\n"
            "Public answer keeps your identity private and shares only a minimal anonymous version.",
        ),
        reply_markup=build_keyboard(ANSWER_MODE_MENU),
    )
    return ANSWER_MODE


async def confirm_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return CONFIRM

    decision = (update.message.text or "").strip()
    if decision == SUBMIT_LABEL:
        source = "quick_message" if context.user_data.get("intake_mode") == "quick" else "guided_flow"
        sent = await deliver_submission(update, context, context.user_data["request"], source)
        reset_request(context)
        return ConversationHandler.END if sent else CONFIRM

    if decision == RESTART_LABEL:
        if context.user_data.get("intake_mode") == "quick":
            return await begin_quick_request(update, context)
        return await start_request(update, context)

    if decision == CANCEL_LABEL:
        return await cancel_request(update, context)

    await update.message.reply_text(
        f"Please choose {SUBMIT_LABEL}, {RESTART_LABEL}, or {CANCEL_LABEL}.",
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

    _, _, submission = find_submission(ticket_id)
    if submission is None:
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

    append_response(
        ticket_id,
        "answered_private",
        {
            "mode": "private",
            "text": answer_text,
        },
    )
    await update.message.reply_text(f"Private answer sent for ticket #{ticket_id}.")


async def reply_public_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /replypublic <ticket_number> <message>")
        return

    ticket_id = parse_ticket_id(context.args[0])
    if ticket_id is None:
        await update.message.reply_text("Ticket numbers must be numeric.")
        return

    answer_text = " ".join(context.args[1:]).strip()
    if not answer_text:
        await update.message.reply_text("Please include the public answer after the ticket number.")
        return

    _, _, submission = find_submission(ticket_id)
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    try:
        response_mode, public_link = await post_public_answer(context, submission, answer_text)
    except TelegramError:
        logger.exception("Failed to publish public answer")
        await update.message.reply_text(
            "I could not publish the public answer. Configure /setdiscussion or /setchannel, or use /markpublic with a manual link."
        )
        return

    user_id = submission.get("user", {}).get("id")
    notice_text = build_public_answer_message(ticket_id, answer_text, public_link)

    try:
        await context.bot.send_message(chat_id=user_id, text=notice_text)
    except TelegramError:
        logger.exception("Failed to notify the user about the public answer")
        await update.message.reply_text(
            f"I could not notify the user about the public answer for ticket #{ticket_id}."
        )
        return

    append_response(
        ticket_id,
        "answered_public",
        {
            "mode": response_mode,
            "text": answer_text,
            "link": public_link,
        },
    )
    await update.message.reply_text(f"Public answer posted for ticket #{ticket_id}.")


async def mark_public(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id: int | None = None
    public_link = ""
    submission: dict | None

    if context.args:
        ticket_id = parse_ticket_id(context.args[0])
        if ticket_id is None:
            await update.message.reply_text("Ticket numbers must be numeric.")
            return
        public_link = context.args[1].strip() if len(context.args) > 1 else ""
        _, _, submission = find_submission(ticket_id)
    elif update.message.reply_to_message and is_discussion_group(
        context, update.effective_chat.id if update.effective_chat else None
    ):
        _, _, submission = find_submission_by_discussion_message(
            update.effective_chat.id,
            update.message.reply_to_message.message_id,
        )
        if submission is not None:
            ticket_id = int(submission["id"])
    else:
        await update.message.reply_text("Usage: /markpublic <ticket_number> [public_post_link]")
        return

    if submission is None:
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

    append_response(
        ticket_id,
        "answered_public",
        {
            "mode": "public_manual",
            "link": public_link,
        },
    )
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

    _, _, submission = find_submission_by_discussion_message(
        update.effective_chat.id,
        update.message.reply_to_message.message_id,
    )
    if submission is None:
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

    append_response(
        ticket_id,
        "answered_public",
        {
            "mode": "public_discussion",
            "text": answer_text,
            "link": public_link,
        },
    )
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
    application.bot_data["public_channel_id"] = get_public_channel_id()
    await sync_commands(application)


def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN is missing. Set it in Railway Variables for deployment or in the local .env file."
        )

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    guided_request_pattern = rf"^{re.escape(GUIDED_REQUEST_LABEL)}$"
    quick_question_pattern = rf"^{re.escape(QUICK_QUESTION_LABEL)}$"
    how_it_works_pattern = rf"^{re.escape(HOW_IT_WORKS_LABEL)}$"

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("ask", start_request, filters=filters.ChatType.PRIVATE),
            MessageHandler(filters.ChatType.PRIVATE & filters.Regex(guided_request_pattern), start_request),
            CommandHandler("quick", begin_quick_request, filters=filters.ChatType.PRIVATE),
            MessageHandler(filters.ChatType.PRIVATE & filters.Regex(quick_question_pattern), begin_quick_request),
            MessageHandler(
                filters.ChatType.PRIVATE
                & filters.TEXT
                & ~filters.COMMAND
                & ~filters.Regex(guided_request_pattern)
                & ~filters.Regex(quick_question_pattern)
                & ~filters.Regex(how_it_works_pattern),
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
    app.add_handler(CommandHandler("setchannel", set_public_channel))
    app.add_handler(CommandHandler("channelstatus", channel_status))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reply", reply_ticket))
    app.add_handler(CommandHandler("replypublic", reply_public_ticket))
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
    app.add_handler(MessageHandler(filters.Regex(how_it_works_pattern), show_help_message))
    app.add_handler(conversation)
    app.add_handler(CommandHandler("cancel", cancel_request))

    logger.info("Mentorship bot is starting")
    app.run_polling()


if __name__ == "__main__":
    main()
