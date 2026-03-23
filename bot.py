import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    KeyboardButton,
    KeyboardButtonRequestChat,
    MessageOriginChannel,
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


def normalize_https_url(value: str) -> str:
    url = (value or "").strip()
    if not url:
        return ""

    if "://" not in url:
        url = f"https://{url.lstrip('/')}"

    parsed = urlsplit(url)
    if not parsed.netloc:
        return ""
    if any(char.isspace() for char in parsed.netloc):
        return ""
    if "." not in parsed.netloc and parsed.netloc.lower() != "localhost":
        return ""

    return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID_RAW = (os.getenv("ADMIN_ID") or "").strip()
MENTOR_LABEL = (os.getenv("MENTOR_LABEL") or DEFAULT_MENTOR_LABEL).strip()
MENTOR_IDENTITY_TEXT = (os.getenv("MENTOR_IDENTITY_TEXT") or "").strip()
MENTOR_IDENTITY_DEFAULT = (os.getenv("MENTOR_IDENTITY_DEFAULT") or "hidden").strip().lower()
MENTOR_AVAILABILITY_TEXT = (
    os.getenv("MENTOR_AVAILABILITY_TEXT")
    or "Replies are handled in planned batches. High urgency means time-sensitive, not instant."
).strip()
PUBLIC_CHANNEL_URL = normalize_https_url(os.getenv("PUBLIC_CHANNEL_URL") or "")
DISCUSSION_GROUP_URL = normalize_https_url(os.getenv("DISCUSSION_GROUP_URL") or "")
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
TAGS_FILE = DATA_DIR / "saved_tags.json"

TRACK, LEVEL, GOAL, CHALLENGE, QUESTION, CONTEXT, URGENCY, ANSWER_MODE, CONTACT_VISIBILITY, CONFIRM, QUICK_QUESTION = range(11)

GUIDED_REQUEST_LABEL = "Guided request"
QUICK_QUESTION_LABEL = "Quick question"
HOW_IT_WORKS_LABEL = "How it works"
RESPONSE_TIMES_LABEL = "Response times"
DASHBOARD_LABEL = "Dashboard"
TEMPLATES_LABEL = "Templates"
TAGS_LABEL = "Tags"
PRIVATE_REPLY_LABEL = "Private reply"
PUBLIC_ANSWER_LABEL = "Public answer"
SHOW_CONTACT_LABEL = "Share contact"
HIDE_CONTACT_LABEL = "Hide contact"
SHOW_IDENTITY_LABEL = "Show identity"
HIDE_IDENTITY_LABEL = "Hide identity"
SUBMIT_LABEL = "Submit"
RESTART_LABEL = "Restart"
CANCEL_LABEL = "Cancel"
SKIP_LABEL = "Skip"
PICK_CHANNEL_LABEL = "Choose channel"
PICK_DISCUSSION_LABEL = "Choose discussion group"

CHANNEL_PICKER_REQUEST_ID = 7001
DISCUSSION_PICKER_REQUEST_ID = 7002

MAIN_MENU = [[GUIDED_REQUEST_LABEL, QUICK_QUESTION_LABEL], [HOW_IT_WORKS_LABEL, RESPONSE_TIMES_LABEL]]
ADMIN_MENU = [[DASHBOARD_LABEL, TEMPLATES_LABEL], [TAGS_LABEL, RESPONSE_TIMES_LABEL]]
TRACK_MENU = [
    ["Research direction", "Technical guidance"],
    ["Project review", "Academic growth"],
    ["Career", "Startup advice"],
    ["Study strategy", "Write my own"],
]
LEVEL_MENU = [
    ["School student", "University student"],
    ["Postgraduate", "Founder / early career"],
    ["Working professional", "Write my own"],
]
URGENCY_MENU = [["Low", "Normal", "High"]]
ANSWER_MODE_MENU = [[PRIVATE_REPLY_LABEL, PUBLIC_ANSWER_LABEL]]
CONTACT_VISIBILITY_MENU = [[SHOW_CONTACT_LABEL, HIDE_CONTACT_LABEL]]
IDENTITY_VISIBILITY_CHOICES = {SHOW_IDENTITY_LABEL, HIDE_IDENTITY_LABEL}
CONFIRM_MENU = [[SUBMIT_LABEL, RESTART_LABEL], [CANCEL_LABEL]]
SKIP_MENU = [[SKIP_LABEL]]

TRACK_CHOICES = {item for row in TRACK_MENU for item in row}
LEVEL_CHOICES = {item for row in LEVEL_MENU for item in row}
URGENCY_CHOICES = {item for row in URGENCY_MENU for item in row}
ANSWER_MODE_CHOICES = {item for row in ANSWER_MODE_MENU for item in row}
CONTACT_VISIBILITY_CHOICES = {item for row in CONTACT_VISIBILITY_MENU for item in row}
TAG_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
TAG_PLACEHOLDER_PATTERN = re.compile(r"\{\{([a-zA-Z0-9_-]+)\}\}")

USER_COMMANDS = [
    BotCommand("start", "Open the mentorship bot"),
    BotCommand("ask", "Start a guided mentorship request"),
    BotCommand("quick", "Send a one-message question"),
    BotCommand("availability", "See response windows"),
    BotCommand("help", "See how the bot works"),
    BotCommand("cancel", "Cancel the current request"),
    BotCommand("status", "Check one of your ticket statuses"),
]

SETUP_COMMANDS = USER_COMMANDS + [
    BotCommand("claimadmin", "Claim admin access for the bot"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand("adminstatus", "Show the current admin ID"),
    BotCommand("dashboard", "Show the mentor dashboard"),
    BotCommand("templates", "List ready reply templates"),
    BotCommand("tags", "List available saved tags"),
    BotCommand("savetag", "Save a reusable reply tag"),
    BotCommand("deletetag", "Delete a saved reply tag"),
    BotCommand("setdiscussion", "Bind the linked discussion group"),
    BotCommand("discussionstatus", "Show the linked discussion group"),
    BotCommand("setchannel", "Bind the public answer channel"),
    BotCommand("channelstatus", "Show the public answer channel"),
    BotCommand("stats", "Show mentorship request statistics"),
    BotCommand("reply", "Send a private answer to a ticket"),
    BotCommand("quickreply", "Send a ready private reply template"),
    BotCommand("replypublic", "Post a public answer through the bot"),
    BotCommand("markpublic", "Mark a ticket as answered publicly"),
]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

STORAGE_LOCK = Lock()

FAST_REPLY_TEMPLATES = {
    "queue": {
        "title": "Queued for next slot",
        "body": (
            "Your request is in the queue for the next response window.\n"
            "I answer in focused batches so replies can stay useful, concise, and accurate."
        ),
    },
    "need_context": {
        "title": "Need more context",
        "body": (
            "I can help, but I need one sharper round of context first.\n"
            "Please reply with:\n"
            "1. your current stage\n"
            "2. the exact outcome you want\n"
            "3. the main blocker\n"
            "4. any deadline or time pressure"
        ),
    },
    "narrow_scope": {
        "title": "Narrow the scope",
        "body": (
            "To make this useful quickly, choose one target only for the next step.\n"
            "Reply with the single question that matters most right now."
        ),
    },
    "send_material": {
        "title": "Send the key material",
        "body": (
            "Please send only the most relevant material for review.\n"
            "Good examples are one abstract, one figure, one page, one proposal section, or one short problem statement."
        ),
    },
    "career_next": {
        "title": "Career next step",
        "body": (
            "The best next step is usually to reduce this to one near-term move.\n"
            "Reply with your target role or direction, your current profile, and the single gap you want to close first."
        ),
    },
    "startup_focus": {
        "title": "Startup focus",
        "body": (
            "For startup advice, the fastest useful path is to clarify the user, the pain point, and the next validation step.\n"
            "Reply with those three points in short form."
        ),
    },
    "out_of_scope": {
        "title": "Outside scope",
        "body": (
            "This exact request is outside the scope I can answer responsibly.\n"
            "If you want, send a narrower version focused on one decision, one draft, one experiment, or one next step."
        ),
    },
    "public_summary": {
        "title": "Public summary suggestion",
        "body": (
            "This looks like a good candidate for a short public answer because others may benefit too.\n"
            "If needed, I can still keep the public version anonymous and minimal."
        ),
    },
}


def parse_numeric_id(value: str) -> int | None:
    value = value.strip()
    if value and value.lstrip("-").isdigit():
        return int(value)
    return None


def build_keyboard(rows: list[list[object]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def build_chat_request_keyboard(button_text: str, request_chat: KeyboardButtonRequestChat) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(button_text, request_chat=request_chat)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


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


def normalize_tag_name(value: str) -> str | None:
    name = (value or "").strip().lower().replace(" ", "_")
    if TAG_NAME_PATTERN.fullmatch(name):
        return name
    return None


def read_saved_tags() -> dict[str, str]:
    with STORAGE_LOCK:
        ensure_data_dir()
        if not TAGS_FILE.exists():
            return {}

        try:
            payload = json.loads(TAGS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read saved tags")
            return {}

        if not isinstance(payload, dict):
            return {}

        tags: dict[str, str] = {}
        for raw_name, raw_value in payload.items():
            name = normalize_tag_name(str(raw_name))
            value = str(raw_value).strip()
            if name and value:
                tags[name] = value
        return dict(sorted(tags.items()))


def save_saved_tags(tags: dict[str, str]) -> None:
    with STORAGE_LOCK:
        ensure_data_dir()
        normalized: dict[str, str] = {}
        for raw_name, raw_value in tags.items():
            name = normalize_tag_name(str(raw_name))
            value = str(raw_value).strip()
            if name and value:
                normalized[name] = value
        TAGS_FILE.write_text(
            json.dumps(dict(sorted(normalized.items())), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def read_env_tags() -> dict[str, str]:
    tags: dict[str, str] = {}
    for key, value in os.environ.items():
        if not key.startswith("TAG_"):
            continue
        name = normalize_tag_name(key[4:])
        text = (value or "").strip()
        if name and text:
            tags[name] = text
    return dict(sorted(tags.items()))


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
    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is None:
        return False

    if user_id is not None and user_id != admin_id:
        return False

    try:
        admin_member = await context.bot.get_chat_member(chat_id=chat_id, user_id=admin_id)
    except TelegramError:
        logger.exception("Failed to verify configured admin access for chat %s", chat_id)
        return False

    return admin_member.status in {"administrator", "creator"}


def extract_forwarded_chat(message) -> tuple[int, str | None] | tuple[None, None]:
    forward_origin = getattr(message, "forward_origin", None)
    if isinstance(forward_origin, MessageOriginChannel):
        return forward_origin.chat.id, getattr(forward_origin.chat, "title", None)

    forward_from_chat = getattr(message, "forward_from_chat", None)
    if forward_from_chat is not None:
        return forward_from_chat.id, getattr(forward_from_chat, "title", None)

    return None, None


async def resolve_chat_reference(context: ContextTypes.DEFAULT_TYPE, value: str):
    reference = (value or "").strip()
    if not reference:
        return None

    if not reference.startswith("@") and not reference.lstrip("-").isdigit():
        reference = f"@{reference}"

    numeric_id = parse_numeric_id(reference)
    chat_ref = numeric_id if numeric_id is not None else reference
    try:
        return await context.bot.get_chat(chat_id=chat_ref)
    except TelegramError:
        logger.exception("Failed to resolve chat reference %s", reference)
        return None


async def validate_public_channel(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> tuple[bool, str]:
    if not await admin_can_manage_chat(context, chat_id, context.application.bot_data.get("admin_id")):
        return False, "The configured admin account must also be an administrator in that channel."

    try:
        bot_member = await context.bot.get_chat_member(chat_id=chat_id, user_id=context.bot.id)
    except TelegramError:
        logger.exception("Failed to read bot membership for channel %s", chat_id)
        return False, "I can see that channel ID, but I could not verify the bot's access there."

    if bot_member.status not in {"administrator", "creator"}:
        return False, "The bot must be an administrator in that channel before it can post public answers."

    if bot_member.status != "creator" and not getattr(bot_member, "can_post_messages", False):
        return False, "The bot is in that channel, but it still needs the Post Messages admin right."

    return True, ""


async def validate_discussion_group(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> tuple[bool, str]:
    if not await admin_can_manage_chat(context, chat_id, context.application.bot_data.get("admin_id")):
        return False, "The configured admin account must also be an administrator in that discussion group."

    try:
        bot_member = await context.bot.get_chat_member(chat_id=chat_id, user_id=context.bot.id)
    except TelegramError:
        logger.exception("Failed to read bot membership for discussion group %s", chat_id)
        return False, "I can see that group ID, but I could not verify the bot's access there."

    if bot_member.status not in {"administrator", "creator", "member"}:
        return False, "The bot must be added to that discussion group before it can use it."

    return True, ""


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


def allows_public_reply(value: str) -> bool:
    return normalize_answer_mode(value) == "public"


def answer_mode_policy_text(value: str) -> str:
    if allows_public_reply(value):
        return "Public allowed. You may answer publicly or switch to a private reply if that is more useful."
    return "Private only. This ticket cannot be turned into a public answer."


def answer_mode_policy_short(value: str) -> str:
    return "Public flexible" if allows_public_reply(value) else "Private only"


def suggest_quick_reply_template(request: dict) -> str | None:
    track = request.get("track", "").lower()
    combined_text = " ".join(
        [
            request.get("track", ""),
            request.get("goal", ""),
            request.get("challenge", ""),
            request.get("question", ""),
            request.get("context", ""),
        ]
    ).lower()
    if request.get("goal") == "Not provided" or request.get("question") == "Not provided":
        return "need_context"
    if request.get("context") == "No extra context":
        return "need_context"
    if len(request.get("question", "")) > 220 or request.get("question", "").count("?") > 1:
        return "narrow_scope"
    if "startup" in track or "startup" in combined_text:
        return "startup_focus"
    if "career" in track or any(keyword in combined_text for keyword in ["cv", "resume", "linkedin", "job"]):
        return "career_next"
    return None


def build_fast_route_hint(request: dict) -> str:
    if request.get("goal") == "Not provided" and request.get("challenge") == "Not provided":
        return "Ask for one target outcome and one main blocker before going deeper."
    if request.get("question") == "Not provided":
        return "Ask the user to send one direct question."
    if request.get("context") == "No extra context":
        return "Keep the reply short or ask for one missing detail only."
    if request.get("urgency") == "High":
        return "Lead with the next concrete step first, then add only essential explanation."
    if len(request.get("question", "")) > 220 or request.get("question", "").count("?") > 1:
        return "Narrow the answer to the main decision or the first next step."
    return "Enough detail is present for a direct, focused answer."


def build_fast_read_section(request: dict, ticket_id: int | str) -> str:
    template_key = suggest_quick_reply_template(request)
    template_line = (
        f"Suggested quick reply: /quickreply {ticket_id} {template_key}"
        if template_key
        else "Suggested quick reply: answer directly"
    )
    return (
        "Fast read\n"
        f"Main ask: {trim_text(request['question'], 180)}\n"
        f"Wanted outcome: {trim_text(request['goal'], 140)}\n"
        f"Main blocker: {trim_text(request['challenge'], 140)}\n"
        f"Fastest route: {build_fast_route_hint(request)}\n"
        f"{template_line}"
    )


def public_reply_block_message(ticket_id: int) -> str:
    return (
        f"Ticket #{ticket_id} is locked to private replies because the user selected {PRIVATE_REPLY_LABEL}.\n"
        "Use /reply or reply to the private bot thread instead."
    )


def private_thread_enabled(submission: dict) -> bool:
    request = normalize_payload(submission.get("request", {}))
    if not allows_public_reply(request.get("answer_mode", "private")):
        return True

    if submission.get("status") == "answered_private":
        return True

    for response in submission.get("responses", []):
        if response.get("mode") in {"private", "private_thread"}:
            return True
        if response.get("direction") in {"mentor_to_user", "user_to_mentor"}:
            return True

    return False


def normalize_contact_visibility(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered in {"hide", "hidden", HIDE_CONTACT_LABEL.lower()}:
        return "hidden"
    return "shown"


def format_contact_visibility(value: str) -> str:
    return "Hidden from mentor view" if normalize_contact_visibility(value) == "hidden" else "Shown to mentor"


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


def format_tag_preview(value: str) -> str:
    return trim_text(re.sub(r"\s+", " ", value).strip(), 72)


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


def build_contact_visibility_prompt(user) -> str:
    display_name = user.full_name or user.first_name or "Unknown user"
    username = f"@{user.username}" if user.username else "Not set"
    return (
        "What the bot receives from Telegram\n\n"
        f"Display name: {display_name}\n"
        f"Username: {username}\n"
        f"Telegram routing ID: {user.id}\n\n"
        "Why this matters\n"
        "The bot uses this data to keep your ticket connected and deliver replies.\n"
        "You can choose whether these details stay visible in the mentor view.\n"
        "If you hide them, the bot still keeps the routing ID privately so answers can reach you."
    )


def default_identity_visibility() -> str:
    return "show" if MENTOR_IDENTITY_DEFAULT == "show" else "hide"


def render_mentor_signature(mode: str) -> str:
    if mode != "show":
        return ""
    if MENTOR_IDENTITY_TEXT:
        return MENTOR_IDENTITY_TEXT
    return f"From {MENTOR_LABEL or DEFAULT_MENTOR_LABEL}"


def apply_identity_signature(message_text: str, mode: str) -> str:
    signature = render_mentor_signature(mode)
    if not signature:
        return message_text
    return f"{message_text}\n\n{signature}"


def build_builtin_tags() -> dict[str, str]:
    tags = {
        "mentor": MENTOR_LABEL or DEFAULT_MENTOR_LABEL,
        "availability": MENTOR_AVAILABILITY_TEXT,
    }
    identity = render_mentor_signature("show")
    if identity:
        tags["identity"] = identity
    if PUBLIC_CHANNEL_URL:
        tags["public_channel"] = PUBLIC_CHANNEL_URL
        tags["channel"] = PUBLIC_CHANNEL_URL
    if DISCUSSION_GROUP_URL:
        tags["discussion_group"] = DISCUSSION_GROUP_URL
        tags["discussion"] = DISCUSSION_GROUP_URL
    return tags


def build_tag_catalog(extra_tags: dict[str, str] | None = None) -> dict[str, str]:
    tags = build_builtin_tags()
    tags.update(read_env_tags())
    tags.update(read_saved_tags())
    if extra_tags:
        for raw_name, raw_value in extra_tags.items():
            name = normalize_tag_name(raw_name)
            value = (raw_value or "").strip()
            if name and value:
                tags[name] = value
    return tags


def expand_saved_tags(
    value: str,
    extra_tags: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    expanded = value
    catalog = build_tag_catalog(extra_tags)

    for _ in range(5):
        changed = False

        def replace(match: re.Match[str]) -> str:
            nonlocal changed
            name = normalize_tag_name(match.group(1)) or match.group(1).strip().lower()
            replacement = catalog.get(name)
            if replacement is None:
                return match.group(0)
            changed = True
            return replacement

        next_text = TAG_PLACEHOLDER_PATTERN.sub(replace, expanded)
        expanded = next_text
        if not changed:
            break

    missing = sorted(
        {
            normalize_tag_name(match.group(1)) or match.group(1).strip().lower()
            for match in TAG_PLACEHOLDER_PATTERN.finditer(expanded)
        }
    )
    return expanded, missing


def build_unknown_tags_message(missing_tags: list[str]) -> str:
    placeholders = ", ".join(f"{{{{{name}}}}}" for name in missing_tags)
    return (
        f"Unknown tag: {placeholders}" if len(missing_tags) == 1 else f"Unknown tags: {placeholders}"
    ) + "\nUse /tags to list the available tags or /savetag to add one."


def build_tags_message() -> str:
    builtin_tags = build_builtin_tags()
    env_tags = read_env_tags()
    saved_tags = read_saved_tags()

    lines = [
        "Saved tags",
        "",
        "Use {{tag_name}} inside /reply, /replypublic, /quickreply, or an admin private-thread reply.",
        "Priority: saved tag in bot -> TAG_ value from .env -> built-in tag.",
    ]

    sections = [
        ("Built in", builtin_tags),
        ("From .env", env_tags),
        ("Saved in bot", saved_tags),
    ]
    for title, tags in sections:
        lines.append("")
        lines.append(title)
        if not tags:
            lines.append("None")
            continue
        for name, raw_value in sorted(tags.items()):
            preview, _ = expand_saved_tags(raw_value)
            lines.append(f"{{{{{name}}}}} -> {format_tag_preview(preview)}")

    lines.extend(
        [
            "",
            "Dynamic",
            "{{ticket}} -> current ticket number",
            "{{ticket_id}} -> current ticket number",
        ]
    )

    lines.extend(
        [
            "",
            "Manage",
            "/savetag website https://your-site.example",
            "/deletetag website",
        ]
    )
    return "\n".join(lines)


def build_availability_message() -> str:
    availability_text, _ = expand_saved_tags(MENTOR_AVAILABILITY_TEXT)
    return (
        "What to expect\n\n"
        "This mentorship is free and designed to stay accurate, practical, and to the point.\n"
        "Requests are handled in focused batches so time can be used well across everyone.\n\n"
        f"Response windows\n{availability_text}\n\n"
        "Best way to get a strong answer\n"
        "Send one clear goal, one main blocker, and one direct question."
    )


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def format_age_short(value: str | None) -> str:
    created_at = parse_iso_datetime(value)
    if created_at is None:
        return "unknown"

    now = datetime.now(timezone.utc)
    delta = now - created_at
    if delta.days >= 1:
        return f"{delta.days}d"
    hours = delta.seconds // 3600
    if hours >= 1:
        return f"{hours}h"
    minutes = max(delta.seconds // 60, 1)
    return f"{minutes}m"


def classify_queue_state(submission: dict) -> str:
    request = normalize_payload(submission.get("request", {}))
    if submission.get("status") == "answered_public":
        return "done_public"

    if allows_public_reply(request.get("answer_mode", "private")) and not private_thread_enabled(submission):
        return "awaiting_public" if submission.get("status") == "open" else "done_public"

    responses = submission.get("responses", [])
    if not responses:
        return "awaiting_private"

    latest = responses[-1]
    direction = latest.get("direction")
    if direction == "user_to_mentor":
        return "awaiting_private"
    if direction == "mentor_to_user":
        return "waiting_user"

    if submission.get("status") == "open":
        return "awaiting_private"
    return "waiting_user"


def queue_priority_key(submission: dict) -> tuple[int, datetime, int]:
    request = normalize_payload(submission.get("request", {}))
    urgency_rank = {"High": 0, "Normal": 1, "Low": 2}.get(request.get("urgency", "Normal"), 1)
    created_at = parse_iso_datetime(submission.get("created_at")) or datetime.max.replace(tzinfo=timezone.utc)
    return urgency_rank, created_at, int(submission.get("id", 0))


def build_dashboard_message(submissions: list[dict]) -> str:
    availability_text, _ = expand_saved_tags(MENTOR_AVAILABILITY_TEXT)
    if not submissions:
        return (
            "Mentor Dashboard\n\n"
            "No tickets yet.\n\n"
            f"Response windows\n{availability_text}"
        )

    waiting_private: list[dict] = []
    waiting_public: list[dict] = []
    waiting_user: list[dict] = []
    high_priority = 0

    for submission in submissions:
        state = classify_queue_state(submission)
        request = normalize_payload(submission.get("request", {}))
        if state == "awaiting_private":
            waiting_private.append(submission)
            if request.get("urgency") == "High":
                high_priority += 1
        elif state == "awaiting_public":
            waiting_public.append(submission)
            if request.get("urgency") == "High":
                high_priority += 1
        elif state == "waiting_user":
            waiting_user.append(submission)

    waiting_on_you = sorted(waiting_private + waiting_public, key=queue_priority_key)
    preview_lines = []
    for submission in waiting_on_you[:6]:
        request = normalize_payload(submission.get("request", {}))
        preview_lines.append(
            f"#{submission['id']} | {answer_mode_policy_short(request.get('answer_mode', 'private'))} | "
            f"{request['urgency']} | {trim_text(request['track'], 20)} | "
            f"{trim_text(request['question'], 52)} | {format_age_short(submission.get('created_at'))}"
        )

    preview_text = "\n".join(preview_lines) if preview_lines else "No tickets currently waiting on you."

    return (
        "Mentor Dashboard\n\n"
        f"Total tickets: {len(submissions)}\n"
        f"Waiting on you: {len(waiting_on_you)}\n"
        f"Private queue: {len(waiting_private)}\n"
        f"Public queue: {len(waiting_public)}\n"
        f"Waiting on user: {len(waiting_user)}\n"
        f"High priority waiting: {high_priority}\n\n"
        f"Response windows\n{availability_text}\n\n"
        f"Next tickets\n{preview_text}\n\n"
        "Fast actions\n"
        "/templates\n"
        "/tags\n"
        "/quickreply <ticket> queue\n"
        "/quickreply <ticket> need_context\n"
        "/quickreply <ticket> queue show"
    )


def build_templates_message() -> str:
    lines = ["Ready reply templates", ""]
    for key, template in FAST_REPLY_TEMPLATES.items():
        lines.append(f"{key}: {template['title']}")
    lines.extend(
        [
            "",
            "Usage",
            "/quickreply <ticket> <template>",
            "/quickreply <ticket> <template> show",
            "/quickreply <ticket> <template> hide",
            "You can also reply to a private ticket message with /quickreply <template> [show|hide].",
            "Saved tags like {{website}} are expanded before sending.",
        ]
    )
    return "\n".join(lines)


def build_public_notice(ticket_id: int, link: str) -> str:
    link = normalize_https_url(link)
    if link:
        return f"Your public answer for ticket #{ticket_id} is ready:\n{link}"
    return (
        f"Your public answer for ticket #{ticket_id} has been posted.\n"
        f"Check {build_public_destination_text()}."
    )


def build_public_answer_message(ticket_id: int, answer_text: str, link: str) -> str:
    link = normalize_https_url(link)
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


def resolve_private_thread_context(submission: dict, chat_id: int, message_id: int) -> dict | None:
    thread = submission.get("private_thread", {})
    responses = submission.get("responses", [])
    admin_chat_id = thread.get("admin_chat_id")
    user_chat_id = thread.get("user_chat_id") or submission.get("user", {}).get("id")
    admin_root_message_id = thread.get("admin_root_message_id")
    user_root_message_id = thread.get("user_root_message_id")

    if chat_id == admin_chat_id:
        if message_id == admin_root_message_id:
            return {
                "side": "admin",
                "remote_chat_id": user_chat_id,
                "remote_reply_to_message_id": user_root_message_id,
            }
        for response in responses:
            if response.get("admin_message_id") == message_id:
                return {
                    "side": "admin",
                    "remote_chat_id": user_chat_id,
                    "remote_reply_to_message_id": response.get("user_message_id") or user_root_message_id,
                }

    if not private_thread_enabled(submission):
        return None

    if chat_id == user_chat_id:
        if message_id == user_root_message_id:
            return {
                "side": "user",
                "remote_chat_id": admin_chat_id,
                "remote_reply_to_message_id": admin_root_message_id,
            }
        for response in responses:
            if response.get("user_message_id") == message_id:
                return {
                    "side": "user",
                    "remote_chat_id": admin_chat_id,
                    "remote_reply_to_message_id": response.get("admin_message_id") or admin_root_message_id,
                }

    return None


def find_submission_by_private_message(
    chat_id: int,
    message_id: int,
) -> tuple[list[dict], int | None, dict | None, dict | None]:
    submissions = read_submissions()
    for index, submission in enumerate(submissions):
        thread_context = resolve_private_thread_context(submission, chat_id, message_id)
        if thread_context is not None:
            return submissions, index, submission, thread_context
    return submissions, None, None, None


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
        "contact_visibility": normalize_contact_visibility(payload.get("contact_visibility", "")),
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
        "private_thread": {
            "admin_chat_id": None,
            "admin_root_message_id": None,
            "user_chat_id": user.id,
            "user_root_message_id": None,
        },
        "discussion": {"chat_id": None, "message_id": None},
        "responses": [],
    }


def format_submission(record: dict) -> str:
    user = record.get("user", {})
    request = normalize_payload(record.get("request", {}))
    ticket_id = record.get("id", "Unknown")
    contact_visibility = normalize_contact_visibility(request.get("contact_visibility", "shown"))
    public_actions_allowed = allows_public_reply(request.get("answer_mode", "private"))

    if contact_visibility == "hidden":
        contact_lines = (
            "Private contact\n"
            "The requester chose to hide their display name, username, and Telegram ID in the mentor view.\n"
            "The bot still keeps the delivery route privately so replies can be sent."
        )
    else:
        username = f"@{user['username']}" if user.get("username") else "Not provided"
        contact_lines = (
            "Private contact\n"
            f"Display name: {user.get('display_name', 'Unknown user')}\n"
            f"Username: {username}\n"
            f"Telegram ID: {user.get('id', 'Unknown')}"
        )

    action_lines = [
        "Admin actions",
        f"/reply {ticket_id} your private answer",
    ]
    suggested_template = suggest_quick_reply_template(request)
    if suggested_template:
        action_lines.append(f"/quickreply {ticket_id} {suggested_template}")
    if public_actions_allowed:
        action_lines.append(f"/replypublic {ticket_id} your public answer")
        action_lines.append(f"/markpublic {ticket_id} https://t.me/yourpost")
    else:
        action_lines.append("Public answer blocked for this ticket.")
    action_text = "\n".join(action_lines)

    return (
        f"Mentorship Ticket #{ticket_id}\n\n"
        f"Submitted: {record.get('display_time', 'Unknown')}\n"
        f"Source: {format_source(record.get('source', 'guided_flow'))}\n"
        f"Status: {format_status(record.get('status', 'open'))}\n\n"
        f"{build_fast_read_section(request, ticket_id)}\n\n"
        f"Reply policy\n{answer_mode_policy_text(request['answer_mode'])}\n\n"
        f"{contact_lines}\n\n"
        f"Request\n"
        f"Topic: {request['track']}\n"
        f"Stage: {request['level']}\n"
        f"Urgency: {request['urgency']}\n"
        f"Requested reply mode: {format_answer_mode(request['answer_mode'])}\n\n"
        f"Contact in mentor view: {format_contact_visibility(request['contact_visibility'])}\n\n"
        f"Goal: {request['goal']}\n\n"
        f"Challenge:\n{request['challenge']}\n\n"
        f"Question:\n{request['question']}\n\n"
        f"Context:\n{request['context']}\n\n"
        f"Public preview\n{record.get('public_request', build_public_prompt(request))}\n\n"
        "Private bot thread\n"
        "Reply to this message to answer privately or continue the private conversation through the bot.\n\n"
        f"{action_text}"
    )


def format_discussion_ticket(record: dict) -> str:
    request = normalize_payload(record.get("request", {}))
    public_request = record.get("public_request") or build_public_prompt(request)

    return (
        f"Anonymous Mentorship Ticket #{record['id']}\n\n"
        f"Topic: {request['track']}\n"
        f"Stage: {request['level']}\n"
        f"Urgency: {request['urgency']}\n\n"
        f"{public_request}\n\n"
        "Reply here with the public answer to close the ticket."
    )


def build_summary(payload: dict) -> str:
    request = normalize_payload(payload)
    return (
        "Review your mentorship request:\n\n"
        f"Topic: {request['track']}\n"
        f"Stage: {request['level']}\n"
        f"Urgency: {request['urgency']}\n"
        f"Requested reply mode: {format_answer_mode(request['answer_mode'])}\n"
        f"Reply policy: {answer_mode_policy_text(request['answer_mode'])}\n\n"
        f"Contact in mentor view: {format_contact_visibility(request['contact_visibility'])}\n\n"
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
        f"Topic: {request.get('track', 'General')}",
        f"Requested reply mode: {format_answer_mode(request.get('answer_mode', 'private'))}",
        f"Reply policy: {answer_mode_policy_text(request.get('answer_mode', 'private'))}",
        f"Contact in mentor view: {format_contact_visibility(request.get('contact_visibility', 'shown'))}",
    ]

    if allows_public_reply(request.get("answer_mode", "private")) and private_thread_enabled(record):
        lines.append("Current route: Private reply in the bot")

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
    if private_thread_enabled(record):
        lines.append("Reply to the private ticket thread in the bot to continue the same conversation.")

    return "\n".join(lines)


def get_latest_private_thread_message_id(submission: dict, side: str) -> int | None:
    thread = submission.get("private_thread", {})
    responses = submission.get("responses", [])

    key = "user_message_id" if side == "user" else "admin_message_id"
    root_key = "user_root_message_id" if side == "user" else "admin_root_message_id"

    for response in reversed(responses):
        message_id = response.get(key)
        if message_id is not None:
            return message_id

    return thread.get(root_key)


async def send_private_ticket_message(
    context: ContextTypes.DEFAULT_TYPE,
    submission: dict,
    ticket_id: int,
    message_text: str,
    admin_message_id: int | None,
    direction: str,
) -> tuple[bool, str]:
    user_id = submission.get("user", {}).get("id")
    if user_id is None:
        return False, "I could not find the Telegram user for this ticket."

    request = normalize_payload(submission.get("request", {}))
    if allows_public_reply(request.get("answer_mode", "private")) and not private_thread_enabled(submission):
        message_text = (
            f"{message_text}\n\n"
            "Reply to this message if you want to continue privately in the bot."
        )

    reply_target_message_id = get_latest_private_thread_message_id(submission, "user")
    try:
        sent_message = await context.bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_to_message_id=reply_target_message_id,
        )
    except TelegramError:
        logger.exception("Failed to send private ticket message")
        return False, f"I could not deliver the private message for ticket #{ticket_id}."

    append_response(
        ticket_id,
        "answered_private",
        {
            "mode": "private_thread" if direction == "mentor_to_user" else "private",
            "direction": direction,
            "text": message_text,
            "admin_message_id": admin_message_id,
            "user_message_id": sent_message.message_id,
        },
    )
    return True, ""


def resolve_quick_reply_target(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[int | None, dict | None, int]:
    if update.message is None:
        return None, None, 0

    if context.args:
        ticket_id = parse_ticket_id(context.args[0])
        if ticket_id is not None:
            _, _, submission = find_submission(ticket_id)
            return ticket_id, submission, 1

    replied_message = getattr(update.message, "reply_to_message", None)
    if replied_message is None or update.effective_chat is None:
        return None, None, 0

    _, _, submission, thread_context = find_submission_by_private_message(
        update.effective_chat.id,
        replied_message.message_id,
    )
    if submission is None or thread_context is None or thread_context.get("side") != "admin":
        return None, None, 0

    return int(submission["id"]), submission, 0


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
        admin_ticket_message = await context.bot.send_message(chat_id=admin_id, text=format_submission(record))
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
        public_note = (
            "\nYour request stays private and the answer will be delivered here.\n"
            "Reply to this message or any later private reply from the bot to continue the same ticket."
        )
    user_confirmation_message = await update.message.reply_text(
        f"Your mentorship request has been sent.\n"
        f"Ticket: #{record['id']}\n"
        f"Requested reply mode: {format_answer_mode(record['request']['answer_mode'])}\n"
        f"Reply policy: {answer_mode_policy_text(record['request']['answer_mode'])}\n"
        f"Contact in mentor view: {format_contact_visibility(record['request']['contact_visibility'])}"
        f"{public_note}",
        reply_markup=build_keyboard(MAIN_MENU),
    )
    record["private_thread"] = {
        "admin_chat_id": admin_id,
        "admin_root_message_id": admin_ticket_message.message_id,
        "user_chat_id": update.effective_user.id,
        "user_root_message_id": user_confirmation_message.message_id,
    }
    save_submission(record)
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
            build_dashboard_message(read_submissions()),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    await update.message.reply_text(
        "Welcome to the mentorship bot.\n"
        f"Your request is delivered to {MENTOR_LABEL or DEFAULT_MENTOR_LABEL}.\n\n"
        "This is a free service designed to stay practical, concise, and sustainable.\n\n"
        "You can ask about research direction, technical guidance, project review, academic growth, career questions, startup ideas, or your own custom topic.\n\n"
        f"{GUIDED_REQUEST_LABEL} explains each step and helps you shape a stronger request.\n"
        f"{QUICK_QUESTION_LABEL} turns one message into a tracked ticket.\n\n"
        "The bot receives your Telegram display name, username, and routing ID so replies can reach you.\n"
        "Before submitting, you can choose whether those details stay visible in the mentor view.\n\n"
        f"{PRIVATE_REPLY_LABEL} stays inside the bot and cannot be turned into a public answer later.\n"
        f"{PUBLIC_ANSWER_LABEL} keeps your identity private and may still be answered privately if that is more useful.",
        reply_markup=build_keyboard(MAIN_MENU),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text(
            "/adminstatus shows the current admin.\n"
            "/dashboard shows the current mentor queue and reply slots.\n"
            "/templates lists the ready private reply templates.\n"
            "/tags lists saved shortcuts like {{website}}.\n"
            "/savetag stores a reusable reply tag.\n"
            "/deletetag removes a saved reply tag.\n"
            "/quickreply sends a template in one step.\n"
            "/setdiscussion opens a private chat picker for the discussion group.\n"
            "/discussionstatus shows the linked discussion group.\n"
            "/setchannel opens a private chat picker for the public channel.\n"
            "/channelstatus shows the public answer channel.\n"
            "/availability shows the public response-window message.\n"
            f"{PRIVATE_REPLY_LABEL} tickets are locked private and cannot be answered publicly.\n"
            f"{PUBLIC_ANSWER_LABEL} tickets may still be answered privately when that is more useful.\n"
            "/stats shows mentorship request counts.\n"
            "Reply to a private ticket message to continue the private conversation through the bot.\n"
            "/reply <ticket> <message> still sends a private answer if you prefer commands.\n"
            "/replypublic <ticket> <message> posts a public answer through the bot.\n"
            "/markpublic <ticket> [link] marks a public answer.\n"
            "/start refreshes the admin view.",
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    await update.message.reply_text(
        "This bot is designed for student and early-career mentorship across research direction, technical guidance, project review, academic growth, career planning, startup advice, and related custom topics.\n\n"
        f"{GUIDED_REQUEST_LABEL} asks for your topic, stage, goal, blocker, and urgency so the mentor can answer with the right depth.\n"
        f"{QUICK_QUESTION_LABEL} is the fastest path if you already know your one main question.\n\n"
        "The bot receives your Telegram display name, username, and routing ID to deliver answers. You can keep those visible to the mentor or hide them in the mentor view.\n\n"
        f"{PRIVATE_REPLY_LABEL} keeps the request and answer inside the bot and locks the ticket to private-only replies.\n"
        f"{PUBLIC_ANSWER_LABEL} shares only an anonymous, minimal public version and may still be answered privately if that is more useful.\n"
        "If your ticket is being handled privately in the bot, reply to the confirmation or any later private bot reply to continue the same conversation.\n"
        f"{RESPONSE_TIMES_LABEL} or /availability shows how reply windows work.\n"
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
        "Use /setdiscussion and /setchannel from your private admin chat to connect the public destinations.\n"
        "Use /dashboard to keep the queue under control, /templates for fast replies, and /tags for saved shortcuts.",
        reply_markup=build_keyboard(ADMIN_MENU),
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

    if update.effective_chat.type == "private":
        if not is_admin(context, update.effective_user.id if update.effective_user else None):
            await message.reply_text("This command is available only to the admin.")
            return

        request_chat = KeyboardButtonRequestChat(
            request_id=DISCUSSION_PICKER_REQUEST_ID,
            chat_is_channel=False,
            bot_is_member=True,
            request_title=True,
            request_username=True,
        )
        await message.reply_text(
            "Choose the discussion group from Telegram's chat picker.\n"
            "This is the recommended setup path for discussion replies.",
            reply_markup=build_chat_request_keyboard(PICK_DISCUSSION_LABEL, request_chat),
        )
        return

    if update.effective_chat.type not in {"group", "supergroup"}:
        await message.reply_text(
            "Use /setdiscussion in your private chat with the bot, then choose the discussion group."
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
    valid, error_message = await validate_discussion_group(context, discussion_group_id)
    if not valid:
        await message.reply_text(error_message)
        return
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
            "No discussion group is linked yet. Run /setdiscussion in your private admin chat and choose the group."
        )
        return

    await update.message.reply_text(f"Current discussion group ID: {discussion_group_id}")


async def set_public_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or update.effective_chat is None:
        return

    if update.effective_chat.type != "private" and update.effective_user is None:
        await message.reply_text("Use /setchannel in your private chat with the bot, then choose the channel there.")
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await message.reply_text("This command is available only to the admin.")
        return

    if context.args:
        chat = await resolve_chat_reference(context, context.args[0])
        if chat is None:
            await message.reply_text("I could not find that channel. Send /setchannel in private and choose it from the picker instead.")
            return
        if chat.type != "channel":
            await message.reply_text("That chat is not a channel.")
            return
        valid, error_message = await validate_public_channel(context, chat.id)
        if not valid:
            await message.reply_text(error_message)
            return
        context.application.bot_data["public_channel_id"] = chat.id
        save_public_channel_id(chat.id)
        await message.reply_text(
            f"Public channel saved successfully.\nChannel ID: {chat.id}"
            + (f"\nUsername: @{chat.username}" if getattr(chat, "username", None) else "")
        )
        return

    replied_message = getattr(message, "reply_to_message", None)
    if replied_message is not None:
        forwarded_chat_id, forwarded_title = extract_forwarded_chat(replied_message)
        if forwarded_chat_id is None:
            await message.reply_text("Reply to a forwarded channel post, or use the picker button instead.")
            return
        valid, error_message = await validate_public_channel(context, forwarded_chat_id)
        if not valid:
            await message.reply_text(error_message)
            return
        context.application.bot_data["public_channel_id"] = forwarded_chat_id
        save_public_channel_id(forwarded_chat_id)
        await message.reply_text(
            f"Public channel saved successfully.\nChannel ID: {forwarded_chat_id}"
            + (f"\nTitle: {forwarded_title}" if forwarded_title else "")
        )
        return

    if update.effective_chat.type != "private":
        await message.reply_text("Use /setchannel in your private chat with the bot, then choose the channel there.")
        return

    request_chat = KeyboardButtonRequestChat(
        request_id=CHANNEL_PICKER_REQUEST_ID,
        chat_is_channel=True,
        bot_is_member=True,
        request_title=True,
        request_username=True,
    )
    await message.reply_text(
        "Choose the public channel from Telegram's chat picker.\n"
        "You can also reply to a forwarded post from that channel with /setchannel, or send /setchannel <chat_id_or_username>.",
        reply_markup=build_chat_request_keyboard(PICK_CHANNEL_LABEL, request_chat),
    )


async def channel_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    public_channel_id = context.application.bot_data.get("public_channel_id")
    if public_channel_id is None:
        await update.message.reply_text(
            "No public channel is linked yet. Run /setchannel in your private admin chat and choose the channel."
        )
        return

    await update.message.reply_text(f"Current public channel ID: {public_channel_id}")


async def handle_chat_shared(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.chat_shared is None or update.effective_user is None:
        return

    if update.effective_chat is None or update.effective_chat.type != "private":
        return

    if not is_admin(context, update.effective_user.id):
        await message.reply_text("This setup action is available only to the admin.")
        return

    shared = message.chat_shared
    if shared.request_id == CHANNEL_PICKER_REQUEST_ID:
        valid, error_message = await validate_public_channel(context, shared.chat_id)
        if not valid:
            await message.reply_text(error_message, reply_markup=ReplyKeyboardRemove())
            return

        context.application.bot_data["public_channel_id"] = shared.chat_id
        save_public_channel_id(shared.chat_id)
        await message.reply_text(
            f"Public channel saved successfully.\nChannel ID: {shared.chat_id}"
            + (f"\nTitle: {shared.title}" if shared.title else "")
            + (f"\nUsername: @{shared.username}" if shared.username else ""),
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if shared.request_id == DISCUSSION_PICKER_REQUEST_ID:
        valid, error_message = await validate_discussion_group(context, shared.chat_id)
        if not valid:
            await message.reply_text(error_message, reply_markup=ReplyKeyboardRemove())
            return

        context.application.bot_data["discussion_group_id"] = shared.chat_id
        save_discussion_group_id(shared.chat_id)
        await message.reply_text(
            f"Discussion group saved successfully.\nGroup ID: {shared.chat_id}"
            + (f"\nTitle: {shared.title}" if shared.title else ""),
            reply_markup=ReplyKeyboardRemove(),
        )


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
        f"Top topics:\n{top_tracks}"
    )


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("This command is available only to the admin.")
        return

    await update.message.reply_text(
        build_dashboard_message(read_submissions()),
        reply_markup=build_keyboard(ADMIN_MENU),
    )


async def templates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("This command is available only to the admin.")
        return

    await update.message.reply_text(
        build_templates_message(),
        reply_markup=build_keyboard(ADMIN_MENU),
    )


async def availability_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    reply_markup = build_keyboard(ADMIN_MENU) if is_admin(
        context, update.effective_user.id if update.effective_user else None
    ) else build_keyboard(MAIN_MENU)
    await update.message.reply_text(build_availability_message(), reply_markup=reply_markup)


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("This command is available only to the admin.")
        return

    await update.message.reply_text(
        build_tags_message(),
        reply_markup=build_keyboard(ADMIN_MENU),
    )


async def save_tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("This command is available only to the admin.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /savetag <name> <value>")
        return

    tag_name = normalize_tag_name(context.args[0])
    if tag_name is None:
        await update.message.reply_text("Tag names must use letters, numbers, hyphens, or underscores only.")
        return

    tag_value = " ".join(context.args[1:]).strip()
    if not tag_value:
        await update.message.reply_text("Please include the saved value after the tag name.")
        return

    saved_tags = read_saved_tags()
    saved_tags[tag_name] = tag_value
    save_saved_tags(saved_tags)

    override_note = ""
    if tag_name in read_env_tags():
        override_note = "\nThis saved tag now overrides the TAG_ value with the same name from .env."
    elif tag_name in build_builtin_tags():
        override_note = "\nThis saved tag now overrides the built-in tag with the same name."

    await update.message.reply_text(
        f"Saved {{{{{tag_name}}}}}.\nValue: {tag_value}{override_note}",
        reply_markup=build_keyboard(ADMIN_MENU),
    )


async def delete_tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("This command is available only to the admin.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /deletetag <name>")
        return

    tag_name = normalize_tag_name(context.args[0])
    if tag_name is None:
        await update.message.reply_text("Tag names must use letters, numbers, hyphens, or underscores only.")
        return

    saved_tags = read_saved_tags()
    if tag_name not in saved_tags:
        await update.message.reply_text(
            f"{{{{{tag_name}}}}} is not saved in the bot.\nUse /tags to see what is available."
        )
        return

    saved_tags.pop(tag_name, None)
    save_saved_tags(saved_tags)

    fallback_note = ""
    if tag_name in read_env_tags():
        fallback_note = "\nThe TAG_ value from .env with the same name is still available."
    elif tag_name in build_builtin_tags():
        fallback_note = "\nThe built-in tag with the same name is still available."

    await update.message.reply_text(
        f"Deleted {{{{{tag_name}}}}}.{fallback_note}",
        reply_markup=build_keyboard(ADMIN_MENU),
    )


def reset_request(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["request"] = {}
    context.user_data["intake_mode"] = ""


async def start_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return ConversationHandler.END

    if is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text(
            "Admin mode is active. Use Dashboard for the queue, Templates for fast replies, or Tags for saved shortcuts.",
            reply_markup=build_keyboard(ADMIN_MENU),
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
        step_text(
            1,
            9,
            "Choose the topic that fits your request best.\n"
            "You can tap a suggestion or write your own topic.",
        ),
        reply_markup=build_keyboard(TRACK_MENU),
    )
    return TRACK


async def begin_quick_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END

    if is_admin(context, update.effective_user.id):
        await update.message.reply_text(
            "Admin mode is active.\nUse Dashboard for the queue, Templates for fast replies, and Tags for saved shortcuts.",
            reply_markup=build_keyboard(ADMIN_MENU),
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
            3,
            "Send your question in one message.\n"
            "Make it one clear question if possible so the mentor can answer faster.\n"
            "You can ask about research direction, technical guidance, project review, academic growth, career, startup ideas, or your own topic.",
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    return QUICK_QUESTION


async def start_quick_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.effective_user is None:
        return ConversationHandler.END

    if is_admin(context, update.effective_user.id):
        await update.message.reply_text(
            "Admin mode is active.\nUse Dashboard for the queue, Templates for fast replies, and Tags for saved shortcuts.",
            reply_markup=build_keyboard(ADMIN_MENU),
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
        "track": "General / custom",
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
            3,
            "How should the answer be delivered?\n"
            "Private reply keeps the request and answer inside the bot.\n"
            "Public answer keeps your identity private and only shares a minimal anonymous version if needed.",
        ),
        reply_markup=build_keyboard(ANSWER_MODE_MENU),
    )
    return ANSWER_MODE


async def capture_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return TRACK

    track = (update.message.text or "").strip()
    if not track:
        await update.message.reply_text(
            "Choose one of the suggested topics or write your own.",
            reply_markup=build_keyboard(TRACK_MENU),
        )
        return TRACK

    context.user_data["request"]["track"] = track
    await update.message.reply_text(
        step_text(
            2,
            9,
            "What stage are you at right now?\n"
            "You can tap a suggestion or write your own stage.",
        ),
        reply_markup=build_keyboard(LEVEL_MENU),
    )
    return LEVEL


async def capture_level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return LEVEL

    level = (update.message.text or "").strip()
    if not level:
        await update.message.reply_text(
            "Share your current stage so the answer matches where you are now.",
            reply_markup=build_keyboard(LEVEL_MENU),
        )
        return LEVEL

    context.user_data["request"]["level"] = level
    await update.message.reply_text(
        step_text(
            3,
            9,
            "What outcome are you trying to achieve?\n"
            "State one concrete outcome so the mentor can focus on the result you want, not just the problem.",
        ),
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
    await update.message.reply_text(
        step_text(
            4,
            9,
            "What is the main challenge or blocker right now?\n"
            "Name the one main blocker so the mentor can avoid generic advice.",
        )
    )
    return CHALLENGE


async def capture_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return CHALLENGE

    challenge = (update.message.text or "").strip()
    if not challenge:
        await update.message.reply_text("Please describe the challenge you are facing.")
        return CHALLENGE

    context.user_data["request"]["challenge"] = challenge
    await update.message.reply_text(
        step_text(
            5,
            9,
            "Write your question as clearly as you can.\n"
            "A single direct question usually gets a faster and more useful answer.",
        )
    )
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
            9,
            "Share any extra context, links, deadlines, or attempts so far.\n"
            "Only include what matters for this case.\n"
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
        step_text(
            7,
            9,
            "How urgent is this request?\n"
            "This helps the mentor prioritize the queue.",
        ),
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
            9,
            "How should the answer be delivered?\n"
            "Private reply keeps the request and answer inside the bot and cannot be switched to public later.\n"
            "Public answer keeps your identity private and may still be answered privately if that is more useful.",
        ),
        reply_markup=build_keyboard(ANSWER_MODE_MENU),
    )
    return ANSWER_MODE


async def capture_answer_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None or update.effective_user is None:
        return ANSWER_MODE

    answer_mode = (update.message.text or "").strip()
    if answer_mode not in ANSWER_MODE_CHOICES:
        await update.message.reply_text(
            f"Please choose {PRIVATE_REPLY_LABEL} or {PUBLIC_ANSWER_LABEL}.",
            reply_markup=build_keyboard(ANSWER_MODE_MENU),
        )
        return ANSWER_MODE

    context.user_data["request"]["answer_mode"] = normalize_answer_mode(answer_mode)
    total_steps = 3 if context.user_data.get("intake_mode") == "quick" else 9
    await update.message.reply_text(
        step_text(total_steps, total_steps, build_contact_visibility_prompt(update.effective_user)),
        reply_markup=build_keyboard(CONTACT_VISIBILITY_MENU),
    )
    return CONTACT_VISIBILITY


async def capture_contact_visibility(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return CONTACT_VISIBILITY

    visibility = (update.message.text or "").strip()
    if visibility not in CONTACT_VISIBILITY_CHOICES:
        await update.message.reply_text(
            f"Please choose {SHOW_CONTACT_LABEL} or {HIDE_CONTACT_LABEL}.",
            reply_markup=build_keyboard(CONTACT_VISIBILITY_MENU),
        )
        return CONTACT_VISIBILITY

    context.user_data["request"]["contact_visibility"] = normalize_contact_visibility(visibility)
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
        "track": "General / custom",
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
            3,
            "How should the answer be delivered?\n"
            "Private reply keeps the request and answer inside the bot and cannot be switched to public later.\n"
            "Public answer keeps your identity private and may still be answered privately if that is more useful.",
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

    request = normalize_payload(submission.get("request", {}))
    if not allows_public_reply(request.get("answer_mode", "private")):
        await update.message.reply_text(
            public_reply_block_message(ticket_id),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    answer_text, missing_tags = expand_saved_tags(
        answer_text,
        {"ticket": str(ticket_id), "ticket_id": str(ticket_id)},
    )
    if missing_tags:
        await update.message.reply_text(
            build_unknown_tags_message(missing_tags),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    sent, error_message = await send_private_ticket_message(
        context,
        submission,
        ticket_id,
        f"Private answer for ticket #{ticket_id}\n\n{answer_text}",
        update.message.message_id,
        "mentor_to_user",
    )
    if not sent:
        await update.message.reply_text(error_message)
        return
    await update.message.reply_text(f"Private answer sent for ticket #{ticket_id}.")


async def quick_reply_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, args_offset = resolve_quick_reply_target(update, context)
    if ticket_id is None or submission is None:
        await update.message.reply_text(
            "Usage: /quickreply <ticket_number> <template> [show|hide]\n"
            "Or reply to a private ticket message with /quickreply <template> [show|hide]."
        )
        return

    template_args = context.args[args_offset:]
    if not template_args:
        await update.message.reply_text(
            "Choose a template.\n"
            "Use /templates to list the available quick replies."
        )
        return

    template_key = template_args[0].strip().lower()
    template = FAST_REPLY_TEMPLATES.get(template_key)
    if template is None:
        await update.message.reply_text(
            f"Unknown template: {template_key}\nUse /templates to list the available quick replies."
        )
        return

    identity_mode = default_identity_visibility()
    if len(template_args) > 1:
        visibility_arg = template_args[1].strip().lower()
        if visibility_arg in {"show", "signed", SHOW_IDENTITY_LABEL.lower()}:
            identity_mode = "show"
        elif visibility_arg in {"hide", "hidden", HIDE_IDENTITY_LABEL.lower()}:
            identity_mode = "hide"
        else:
            await update.message.reply_text("Identity mode must be show or hide.")
            return

    reply_text = apply_identity_signature(template["body"], identity_mode)
    reply_text, missing_tags = expand_saved_tags(
        reply_text,
        {"ticket": str(ticket_id), "ticket_id": str(ticket_id)},
    )
    if missing_tags:
        await update.message.reply_text(
            build_unknown_tags_message(missing_tags),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    sent, error_message = await send_private_ticket_message(
        context,
        submission,
        ticket_id,
        f"Private answer for ticket #{ticket_id}\n\n{reply_text}",
        update.message.message_id,
        "mentor_to_user",
    )
    if not sent:
        await update.message.reply_text(error_message)
        return

    await update.message.reply_text(
        f"Quick reply sent for ticket #{ticket_id}.\n"
        f"Template: {template_key}\n"
        f"Mentor identity: {'shown' if identity_mode == 'show' else 'hidden'}",
        reply_markup=build_keyboard(ADMIN_MENU),
    )


async def handle_private_thread_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None or update.effective_chat is None:
        return

    if update.effective_chat.type != "private":
        return

    if update.message.reply_to_message is None:
        return

    reply_text = (update.message.text or "").strip()
    if not reply_text:
        return

    _, _, submission, thread_context = find_submission_by_private_message(
        update.effective_chat.id,
        update.message.reply_to_message.message_id,
    )
    if submission is None or thread_context is None:
        if is_admin(context, update.effective_user.id):
            await update.message.reply_text(
                "Reply to a ticket message or a private-thread relay to continue a private ticket."
            )
        return

    ticket_id = int(submission["id"])

    if thread_context["side"] == "admin":
        reply_text, missing_tags = expand_saved_tags(
            reply_text,
            {"ticket": str(ticket_id), "ticket_id": str(ticket_id)},
        )
        if missing_tags:
            await update.message.reply_text(
                build_unknown_tags_message(missing_tags),
                reply_markup=build_keyboard(ADMIN_MENU),
            )
            return

        sent, error_message = await send_private_ticket_message(
            context,
            submission,
            ticket_id,
            f"Private reply for ticket #{ticket_id}\n\n{reply_text}",
            update.message.message_id,
            "mentor_to_user",
        )
        if not sent:
            await update.message.reply_text(error_message)
            return
        return

    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is None or submission.get("user", {}).get("id") != update.effective_user.id:
        return

    try:
        sent_message = await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"Private follow-up for ticket #{ticket_id}\n\n"
                f"{reply_text}\n\n"
                "Reply to this message to answer through the bot."
            ),
            reply_to_message_id=thread_context.get("remote_reply_to_message_id"),
        )
    except TelegramError:
        logger.exception("Failed to relay user private-thread reply")
        await update.message.reply_text(
            "I could not send your private follow-up right now. Please try again in a moment."
        )
        return

    append_response(
        ticket_id,
        "open",
        {
            "mode": "private_thread",
            "direction": "user_to_mentor",
            "text": reply_text,
            "admin_message_id": sent_message.message_id,
            "user_message_id": update.message.message_id,
        },
    )


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

    request = normalize_payload(submission.get("request", {}))
    if not allows_public_reply(request.get("answer_mode", "private")):
        await update.message.reply_text(
            public_reply_block_message(ticket_id),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    answer_text, missing_tags = expand_saved_tags(
        answer_text,
        {"ticket": str(ticket_id), "ticket_id": str(ticket_id)},
    )
    if missing_tags:
        await update.message.reply_text(
            build_unknown_tags_message(missing_tags),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    try:
        response_mode, public_link = await post_public_answer(context, submission, answer_text)
    except TelegramError:
        logger.exception("Failed to publish public answer")
        await update.message.reply_text(
            "I could not publish the public answer. Configure /setdiscussion or /setchannel, or use /markpublic with a manual link."
        )
        return
    public_link = normalize_https_url(public_link)

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
        public_link = normalize_https_url(context.args[1]) if len(context.args) > 1 else ""
        if len(context.args) > 1 and not public_link:
            await update.message.reply_text("Public links must be valid https URLs.")
            return
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

    request = normalize_payload(submission.get("request", {}))
    if not allows_public_reply(request.get("answer_mode", "private")):
        await update.message.reply_text(
            public_reply_block_message(ticket_id),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
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
    request = normalize_payload(submission.get("request", {}))
    if not allows_public_reply(request.get("answer_mode", "private")):
        await update.message.reply_text(public_reply_block_message(ticket_id))
        return

    user_id = submission.get("user", {}).get("id")
    public_link = getattr(update.message, "link", "") or ""
    public_link = normalize_https_url(public_link)
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
    response_times_pattern = rf"^{re.escape(RESPONSE_TIMES_LABEL)}$"
    dashboard_pattern = rf"^{re.escape(DASHBOARD_LABEL)}$"
    templates_pattern = rf"^{re.escape(TEMPLATES_LABEL)}$"
    tags_pattern = rf"^{re.escape(TAGS_LABEL)}$"

    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("ask", start_request, filters=filters.ChatType.PRIVATE),
            MessageHandler(
                filters.ChatType.PRIVATE & filters.Regex(guided_request_pattern) & ~filters.REPLY,
                start_request,
            ),
            CommandHandler("quick", begin_quick_request, filters=filters.ChatType.PRIVATE),
            MessageHandler(
                filters.ChatType.PRIVATE & filters.Regex(quick_question_pattern) & ~filters.REPLY,
                begin_quick_request,
            ),
            MessageHandler(
                filters.ChatType.PRIVATE
                & filters.TEXT
                & ~filters.REPLY
                & ~filters.COMMAND
                & ~filters.Regex(guided_request_pattern)
                & ~filters.Regex(quick_question_pattern)
                & ~filters.Regex(response_times_pattern)
                & ~filters.Regex(dashboard_pattern)
                & ~filters.Regex(templates_pattern)
                & ~filters.Regex(tags_pattern)
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
            CONTACT_VISIBILITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_contact_visibility)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_request)],
            QUICK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_quick_question)],
        },
        fallbacks=[CommandHandler("cancel", cancel_request)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("availability", availability_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("claimadmin", claim_admin))
    app.add_handler(CommandHandler("adminstatus", admin_status))
    app.add_handler(CommandHandler("dashboard", dashboard_command))
    app.add_handler(CommandHandler("templates", templates_command))
    app.add_handler(CommandHandler("tags", tags_command))
    app.add_handler(CommandHandler("savetag", save_tag_command))
    app.add_handler(CommandHandler("deletetag", delete_tag_command))
    app.add_handler(CommandHandler("setdiscussion", set_discussion_group))
    app.add_handler(CommandHandler("discussionstatus", discussion_status))
    app.add_handler(CommandHandler("setchannel", set_public_channel))
    app.add_handler(CommandHandler("channelstatus", channel_status))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.StatusUpdate.CHAT_SHARED,
            handle_chat_shared,
        )
    )
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reply", reply_ticket))
    app.add_handler(CommandHandler("quickreply", quick_reply_ticket))
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
    app.add_handler(
        MessageHandler(filters.Regex(how_it_works_pattern) & ~filters.REPLY, show_help_message)
    )
    app.add_handler(
        MessageHandler(filters.Regex(response_times_pattern) & ~filters.REPLY, availability_command)
    )
    app.add_handler(
        MessageHandler(filters.Regex(dashboard_pattern) & ~filters.REPLY, dashboard_command)
    )
    app.add_handler(
        MessageHandler(filters.Regex(templates_pattern) & ~filters.REPLY, templates_command)
    )
    app.add_handler(
        MessageHandler(filters.Regex(tags_pattern) & ~filters.REPLY, tags_command)
    )
    app.add_handler(conversation)
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.REPLY & filters.TEXT & ~filters.COMMAND,
            handle_private_thread_reply,
        )
    )
    app.add_handler(CommandHandler("cancel", cancel_request))

    logger.info("Mentorship bot is starting")
    app.run_polling()


if __name__ == "__main__":
    main()
