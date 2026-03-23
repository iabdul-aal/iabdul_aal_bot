import csv
import html
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv
from telegram import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    LinkPreviewOptions,
    MessageOriginChannel,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
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


def decode_env_text(value: str) -> str:
    return (value or "").strip().replace("\\n", "\n")


def escape_html(value: object) -> str:
    return html.escape(str(value or ""))

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID_RAW = (os.getenv("ADMIN_ID") or "").strip()
MENTOR_LABEL = (os.getenv("MENTOR_LABEL") or DEFAULT_MENTOR_LABEL).strip()
MENTOR_IDENTITY_TEXT = decode_env_text(os.getenv("MENTOR_IDENTITY_TEXT") or "")
MENTOR_IDENTITY_DEFAULT = (os.getenv("MENTOR_IDENTITY_DEFAULT") or "hidden").strip().lower()
REQUIRE_PERSISTENT_STORAGE_RAW = (os.getenv("REQUIRE_PERSISTENT_STORAGE") or "").strip().lower()
MENTOR_LOGO_URL = normalize_https_url(os.getenv("MENTOR_LOGO_URL") or "")
CALENDLY_URL = normalize_https_url(os.getenv("CALENDLY_URL") or "")
CALENDLY_LABEL = (os.getenv("CALENDLY_LABEL") or "Book a meeting").strip() or "Book a meeting"
CALENDLY_TEXT = decode_env_text(
    os.getenv("CALENDLY_TEXT")
    or "Use this when a live meeting is the fastest way to move the case forward.\n"
    "Best for decision-heavy questions, detailed reviews, or cases where text back-and-forth would cost more time."
)
CTA_CHANNEL_URL = normalize_https_url(os.getenv("CTA_CHANNEL_URL") or "")
CTA_WEBSITE_URL = normalize_https_url(os.getenv("CTA_WEBSITE_URL") or "")
CTA_SERVICES_URL = normalize_https_url(os.getenv("CTA_SERVICES_URL") or "")
CTA_EXTRA_TEXT = decode_env_text(os.getenv("CTA_EXTRA_TEXT") or "")
MENTOR_AVAILABILITY_TEXT = (
    os.getenv("MENTOR_AVAILABILITY_TEXT")
    or "Replies are handled in planned batches. High urgency means time-sensitive, not instant."
)
MENTOR_AVAILABILITY_TEXT = decode_env_text(MENTOR_AVAILABILITY_TEXT)
PUBLIC_CHANNEL_URL = normalize_https_url(os.getenv("PUBLIC_CHANNEL_URL") or "")
DISCUSSION_GROUP_URL = normalize_https_url(os.getenv("DISCUSSION_GROUP_URL") or "")
DISCUSSION_GROUP_ID_RAW = (os.getenv("DISCUSSION_GROUP_ID") or "").strip()
PUBLIC_CHANNEL_ID_RAW = (os.getenv("PUBLIC_CHANNEL_ID") or "").strip()
RAILWAY_VOLUME_MOUNT_PATH = (os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
RAILWAY_VOLUME_NAME = (os.getenv("RAILWAY_VOLUME_NAME") or "").strip()
DATA_DIR = Path(
    os.getenv("DATA_DIR")
    or RAILWAY_VOLUME_MOUNT_PATH
    or Path(__file__).with_name("data")
)
ADMIN_FILE = DATA_DIR / "admin_id.txt"
DISCUSSION_FILE = DATA_DIR / "discussion_group_id.txt"
PUBLIC_CHANNEL_FILE = DATA_DIR / "public_channel_id.txt"
COUNTER_FILE = DATA_DIR / "ticket_counter.txt"
SUBMISSIONS_FILE = DATA_DIR / "submissions.jsonl"
SUBMISSIONS_CSV_FILE = DATA_DIR / "submissions.csv"
TAGS_FILE = DATA_DIR / "saved_tags.json"
USERS_FILE = DATA_DIR / "known_users.json"

REQUEST_KIND, TRACK, LEVEL, GOAL, CHALLENGE, QUESTION, CONTEXT, URGENCY, ANSWER_MODE, CONTACT_VISIBILITY, CONFIRM, QUICK_QUESTION = range(12)

GUIDED_REQUEST_LABEL = "Add details"
QUICK_QUESTION_LABEL = "Quick question"
HOW_IT_WORKS_LABEL = "How it works"
RESPONSE_TIMES_LABEL = "Response times"
BOOK_MEETING_LABEL = "Book a meeting"
SERVICES_LABEL = "Get other services"
CONTACT_LABEL = "Contact"
WEBSITE_LABEL = "Browse website"
DASHBOARD_LABEL = "Dashboard"
TEMPLATES_LABEL = "Templates"
TAGS_LABEL = "Tags"
PRIVATE_REPLY_LABEL = "Private reply"
PUBLIC_ANSWER_LABEL = "Public answer"
SHOW_CONTACT_LABEL = "Show my details"
HIDE_CONTACT_LABEL = "Keep them private"
SHOW_IDENTITY_LABEL = "Show identity"
HIDE_IDENTITY_LABEL = "Hide identity"
SUBMIT_LABEL = "Submit"
RESTART_LABEL = "Restart"
CANCEL_LABEL = "Cancel"
SKIP_LABEL = "Skip"
PICK_CHANNEL_LABEL = "Choose channel"
PICK_DISCUSSION_LABEL = "Choose discussion group"
MENTORSHIP_REQUEST_LABEL = "Mentorship"
TECHNICAL_SERVICE_LABEL = "Technical service"
RESEARCH_COLLABORATION_LABEL = "Research collaboration"
SPEAKING_WORKSHOP_LABEL = "Speaking or workshop"
OTHER_REQUEST_LABEL = "Other"
USER_CONTINUE_CALLBACK_PREFIX = "user:continue:"
USER_CLOSE_CALLBACK_PREFIX = "user:close:"
MAX_ATTACHMENT_CAPTION_LENGTH = 1024

CHANNEL_PICKER_REQUEST_ID = 7001
DISCUSSION_PICKER_REQUEST_ID = 7002

MAIN_MENU = [
    [GUIDED_REQUEST_LABEL, QUICK_QUESTION_LABEL],
    [HOW_IT_WORKS_LABEL, RESPONSE_TIMES_LABEL],
    [BOOK_MEETING_LABEL, SERVICES_LABEL],
    [CONTACT_LABEL, WEBSITE_LABEL],
]
ADMIN_MENU = [[DASHBOARD_LABEL, TEMPLATES_LABEL], [TAGS_LABEL, RESPONSE_TIMES_LABEL]]
REQUEST_KIND_MENU = [
    [MENTORSHIP_REQUEST_LABEL, TECHNICAL_SERVICE_LABEL],
    [RESEARCH_COLLABORATION_LABEL, SPEAKING_WORKSHOP_LABEL],
    [OTHER_REQUEST_LABEL],
]
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
WEBSITE_NAV_ITEMS = [
    ("About", "about"),
    ("Publications", "publications"),
    ("Projects", "projects"),
    ("Materials", "materials"),
    ("Talks", "talks"),
    ("Services", "services"),
    ("Articles", "articles"),
    ("Ventures", "ventures"),
    ("Contact", "contact"),
    ("CV", "cv"),
]
PROFILE_SCOPE_LINES = [
    "Mentorship and technical guidance",
    "Photonic device design support",
    "Research workflow engineering",
    "Physics-informed optimization support",
]

TRACK_CHOICES = {item for row in TRACK_MENU for item in row}
LEVEL_CHOICES = {item for row in LEVEL_MENU for item in row}
URGENCY_CHOICES = {item for row in URGENCY_MENU for item in row}
ANSWER_MODE_CHOICES = {item for row in ANSWER_MODE_MENU for item in row}
CONTACT_VISIBILITY_CHOICES = {item for row in CONTACT_VISIBILITY_MENU for item in row}
REQUEST_KIND_CHOICES = {item for row in REQUEST_KIND_MENU for item in row}
TAG_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
TAG_PLACEHOLDER_PATTERN = re.compile(r"\{\{([a-zA-Z0-9_-]+)\}\}")
SUBMISSION_CSV_COLUMNS = [
    "id",
    "created_at",
    "updated_at",
    "display_time",
    "status",
    "source",
    "user_id",
    "user_display_name",
    "user_username",
    "request_kind",
    "track",
    "level",
    "urgency",
    "answer_mode",
    "contact_visibility",
    "goal",
    "challenge",
    "question",
    "context",
    "public_request",
    "response_count",
    "note_count",
    "todo_count",
    "open_todo_count",
    "private_thread_json",
    "discussion_json",
    "notes_json",
    "todos_json",
    "responses_json",
]

ADMIN_COMMANDS = [
    BotCommand("start", "Open the admin dashboard"),
    BotCommand("help", "Show admin commands"),
    BotCommand("adminstatus", "Show the current admin ID"),
    BotCommand("storagestatus", "Show queue storage status"),
    BotCommand("dashboard", "Show the admin dashboard"),
    BotCommand("ticket", "Show one ticket by ID"),
    BotCommand("tickets", "List tickets by queue state"),
    BotCommand("note", "Add an internal note to a ticket"),
    BotCommand("notes", "Show ticket notes"),
    BotCommand("todo", "Add a checklist item to a ticket"),
    BotCommand("todos", "Show ticket checklist"),
    BotCommand("tododone", "Mark a checklist item done"),
    BotCommand("todoundo", "Reopen a checklist item"),
    BotCommand("todoremind", "Set a checklist reminder"),
    BotCommand("templates", "List ready reply templates"),
    BotCommand("tags", "List available saved tags"),
    BotCommand("savetag", "Save a reusable reply tag"),
    BotCommand("deletetag", "Delete a saved reply tag"),
    BotCommand("setdiscussion", "Bind the linked discussion group"),
    BotCommand("discussionstatus", "Show the linked discussion group"),
    BotCommand("setchannel", "Bind the public answer channel"),
    BotCommand("channelstatus", "Show the public answer channel"),
    BotCommand("stats", "Show request statistics"),
    BotCommand("reply", "Send a private answer to a ticket"),
    BotCommand("sendmeeting", "Send a ticket-specific meeting invite"),
    BotCommand("meetingstatus", "Show Calendly booking setup"),
    BotCommand("quickreply", "Send a ready private reply template"),
    BotCommand("replypublic", "Post a public answer through the bot"),
    BotCommand("markpublic", "Mark a ticket as answered publicly"),
    BotCommand("endticket", "End a ticket and stop further replies"),
]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

STORAGE_LOCK = Lock()
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
PRIVATE_TICKET_IDLE_TIMEOUT = timedelta(days=1)
PUBLIC_TICKET_IDLE_TIMEOUT = timedelta(days=3)

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
    "meeting_invite": {
        "title": "Meeting invite",
        "body": (
            "A live meeting looks like the fastest route for this case.\n"
            "If the booking form has notes, mention ticket #{{ticket}} so the meeting stays tied to this case."
        ),
    },
}

DEFAULT_ADMIN_TICKET_LIST_LIMIT = 10
MAX_ADMIN_TICKET_LIST_LIMIT = 25
MAX_TICKET_NOTES_PREVIEW = 6
TODO_REMINDER_SWEEP_SECONDS = 300
TICKET_LIST_SCOPE_ALIASES = {
    "queue": "queue",
    "waiting": "queue",
    "open": "queue",
    "private": "awaiting_private",
    "public": "awaiting_public",
    "waiting_user": "waiting_user",
    "user": "waiting_user",
    "ended": "done_closed",
    "closed": "done_closed",
    "all": "all",
}
TODO_OWNER_ALIASES = {
    "admin": "admin",
    "me": "admin",
    "self": "admin",
    "internal": "admin",
    "user": "user",
    "requester": "user",
    "client": "user",
    "them": "user",
    "him": "user",
}


def parse_numeric_id(value: str) -> int | None:
    value = value.strip()
    if value and value.lstrip("-").isdigit():
        return int(value)
    return None


def build_keyboard(rows: list[list[object]]) -> ReplyKeyboardMarkup:
    if rows is MAIN_MENU:
        rows = build_user_main_menu()
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def feature_booking_enabled() -> bool:
    return booking_enabled()


def feature_services_enabled() -> bool:
    return bool(cta_services_url())


def feature_contact_enabled() -> bool:
    return any([contact_page_url(), contact_email(), linkedin_url(), whatsapp_url(), calendly_url()])


def feature_website_enabled() -> bool:
    return bool(website_navigation_links())


def feature_profile_enabled() -> bool:
    return any([website_page_url("about"), cta_website_url(), cta_services_url(), cv_page_url(), github_url(), orcid_url(), scholar_url()])


def feature_channel_updates_enabled() -> bool:
    return bool(get_public_channel_id() or cta_channel_url())


def build_user_commands() -> list[BotCommand]:
    commands = [
        BotCommand("start", "Open the request bot"),
        BotCommand("quick", "Send a one-message request"),
    ]
    if feature_booking_enabled():
        commands.append(BotCommand("meeting", "Open the meeting link"))
    if feature_services_enabled():
        commands.append(BotCommand("services", "Open the services page"))
    if feature_contact_enabled():
        commands.append(BotCommand("contact", "Open contact routes"))
    if feature_website_enabled():
        commands.append(BotCommand("website", "Browse the website"))
    if feature_profile_enabled():
        commands.append(BotCommand("profile", "Open the profile snapshot"))
    commands.extend(
        [
            BotCommand("availability", "See response windows"),
            BotCommand("help", "See how the bot works"),
        ]
    )
    if feature_channel_updates_enabled():
        commands.extend(
            [
                BotCommand("muteupdates", "Pause channel news in the bot"),
                BotCommand("resumeupdates", "Resume channel news in the bot"),
            ]
        )
    commands.extend(
        [
            BotCommand("cancel", "Cancel the current request"),
            BotCommand("status", "Check one of your ticket statuses"),
        ]
    )
    return commands


def build_setup_commands() -> list[BotCommand]:
    return build_user_commands() + [BotCommand("claimadmin", "Claim admin access for the bot")]


def build_user_main_menu() -> list[list[object]]:
    rows: list[list[object]] = [[QUICK_QUESTION_LABEL]]
    secondary_row: list[object] = []
    if feature_booking_enabled():
        secondary_row.append(BOOK_MEETING_LABEL)
    if feature_services_enabled():
        secondary_row.append(SERVICES_LABEL)
    if secondary_row:
        rows.append(secondary_row)
    return rows


def user_main_menu_markup() -> ReplyKeyboardMarkup:
    return build_keyboard(build_user_main_menu())


def admin_menu_markup() -> ReplyKeyboardMarkup:
    return build_keyboard(ADMIN_MENU)


def standard_private_menu(admin_view: bool) -> ReplyKeyboardMarkup:
    return admin_menu_markup() if admin_view else user_main_menu_markup()


def build_chat_request_keyboard(button_text: str, request_chat: KeyboardButtonRequestChat) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(button_text, request_chat=request_chat)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def chunk_items(items: list, size: int) -> list[list]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def build_copy_button(label: str, value: str) -> InlineKeyboardButton:
    text = (value[:256] if value else label).strip("\n")
    return InlineKeyboardButton(label, copy_text=CopyTextButton(text))


def build_inline_markup(buttons: list[InlineKeyboardButton], columns: int = 2) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    return InlineKeyboardMarkup(chunk_items(buttons, columns))


def merge_inline_markups(*markups: InlineKeyboardMarkup | None) -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for markup in markups:
        if markup is None:
            continue
        for row in markup.inline_keyboard:
            for button in row:
                copy_text = getattr(getattr(button, "copy_text", None), "text", None)
                signature = (button.text, button.url, button.callback_data, copy_text)
                if signature in seen:
                    continue
                seen.add(signature)
                buttons.append(button)
    return build_inline_markup(buttons)


def env_flag(value: str, default: bool) -> bool:
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


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


def read_configured_tag(name: str) -> str:
    normalized_name = normalize_tag_name(name)
    if not normalized_name:
        return ""
    saved_tags = read_saved_tags()
    if normalized_name in saved_tags:
        return saved_tags[normalized_name].strip()
    return read_env_tags().get(normalized_name, "").strip()


def read_known_users() -> dict[str, dict]:
    with STORAGE_LOCK:
        ensure_data_dir()
        if not USERS_FILE.exists():
            return {}

        try:
            payload = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read known users")
            return {}

        if not isinstance(payload, dict):
            return {}

        users: dict[str, dict] = {}
        for raw_id, raw_record in payload.items():
            user_id = parse_numeric_id(str(raw_id))
            if user_id is None or not isinstance(raw_record, dict):
                continue
            users[str(user_id)] = {
                "id": user_id,
                "display_name": clean_text(str(raw_record.get("display_name", "")), "Unknown user"),
                "username": (raw_record.get("username") or "").strip(),
                "updates_enabled": bool(raw_record.get("updates_enabled", True)),
                "first_seen": clean_text(str(raw_record.get("first_seen", "")), timestamp_now()),
                "last_seen": clean_text(str(raw_record.get("last_seen", "")), timestamp_now()),
            }
        return users


def save_known_users(users: dict[str, dict]) -> None:
    with STORAGE_LOCK:
        ensure_data_dir()
        normalized: dict[str, dict] = {}
        for raw_id, raw_record in users.items():
            user_id = parse_numeric_id(str(raw_id))
            if user_id is None or not isinstance(raw_record, dict):
                continue
            normalized[str(user_id)] = {
                "id": user_id,
                "display_name": clean_text(str(raw_record.get("display_name", "")), "Unknown user"),
                "username": (raw_record.get("username") or "").strip(),
                "updates_enabled": bool(raw_record.get("updates_enabled", True)),
                "first_seen": clean_text(str(raw_record.get("first_seen", "")), timestamp_now()),
                "last_seen": clean_text(str(raw_record.get("last_seen", "")), timestamp_now()),
            }
        USERS_FILE.write_text(
            json.dumps(dict(sorted(normalized.items())), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def remember_known_user(user, updates_enabled: bool | None = None) -> None:
    if user is None:
        return

    users = read_known_users()
    key = str(user.id)
    now = timestamp_now()
    existing = users.get(key, {})
    users[key] = {
        "id": user.id,
        "display_name": user.full_name or user.first_name or existing.get("display_name") or "Unknown user",
        "username": user.username or existing.get("username", ""),
        "updates_enabled": existing.get("updates_enabled", True) if updates_enabled is None else updates_enabled,
        "first_seen": existing.get("first_seen", now),
        "last_seen": now,
    }
    save_known_users(users)


def set_user_updates_preference(user_id: int, enabled: bool) -> dict | None:
    users = read_known_users()
    key = str(user_id)
    if key not in users:
        users[key] = {
            "id": user_id,
            "display_name": "Unknown user",
            "username": "",
            "updates_enabled": enabled,
            "first_seen": timestamp_now(),
            "last_seen": timestamp_now(),
        }
    else:
        users[key]["updates_enabled"] = enabled
        users[key]["last_seen"] = timestamp_now()
    save_known_users(users)
    return users.get(key)


def user_updates_enabled(user_id: int) -> bool:
    users = read_known_users()
    record = users.get(str(user_id))
    return True if record is None else bool(record.get("updates_enabled", True))


def collect_broadcast_targets(admin_id: int | None) -> list[int]:
    known_users = read_known_users()
    target_ids = {
        int(user_id)
        for user_id, record in known_users.items()
        if bool(record.get("updates_enabled", True))
    }
    for submission in read_submissions():
        user_id = submission.get("user", {}).get("id")
        if not isinstance(user_id, int):
            continue
        known_record = known_users.get(str(user_id))
        if known_record is not None and not bool(known_record.get("updates_enabled", True)):
            continue
        if user_id > 0:
            target_ids.add(user_id)
    if admin_id is not None and admin_id in target_ids:
        target_ids.remove(admin_id)
    return sorted(target_ids)


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


def is_running_on_railway() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "RAILWAY_PROJECT_ID",
            "RAILWAY_SERVICE_ID",
            "RAILWAY_ENVIRONMENT_ID",
            "RAILWAY_DEPLOYMENT_ID",
        )
    )


def data_dir_is_under(path: Path, parent: Path) -> bool:
    try:
        resolved_path = path.resolve()
        resolved_parent = parent.resolve()
    except OSError:
        return False
    return resolved_path == resolved_parent or resolved_parent in resolved_path.parents


def storage_mode() -> str:
    if RAILWAY_VOLUME_MOUNT_PATH and data_dir_is_under(DATA_DIR, Path(RAILWAY_VOLUME_MOUNT_PATH)):
        return "railway_volume"
    if is_running_on_railway():
        return "railway_ephemeral"
    return "local_filesystem"


def require_persistent_storage() -> bool:
    return env_flag(REQUIRE_PERSISTENT_STORAGE_RAW, False)


def build_storage_status_message() -> str:
    mode = storage_mode()
    queue_count = len(read_submissions())
    lines = [
        "Storage status",
        "",
        f"Data directory: {DATA_DIR}",
        f"Storage mode: {mode}",
        f"Running on Railway: {'yes' if is_running_on_railway() else 'no'}",
        f"Persistent storage required: {'yes' if require_persistent_storage() else 'no'}",
        f"Queued tickets on disk: {queue_count}",
    ]
    if RAILWAY_VOLUME_MOUNT_PATH:
        lines.append(f"Railway volume mount path: {RAILWAY_VOLUME_MOUNT_PATH}")
    if RAILWAY_VOLUME_NAME:
        lines.append(f"Railway volume name: {RAILWAY_VOLUME_NAME}")

    if mode == "railway_volume":
        lines.extend(
            [
                "",
                "Queue storage is on a Railway Volume and should survive redeploys.",
            ]
        )
    elif mode == "railway_ephemeral":
        lines.extend(
            [
                "",
                "Warning: this deployment is using ephemeral filesystem storage.",
                "A new deploy can reset the queue and break replies to older tickets.",
                "Attach a Railway Volume and mount it to /app/data, or point DATA_DIR at the mounted volume path.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Queue storage is using the local filesystem for this environment.",
            ]
        )

    return "\n".join(lines)


def validate_storage_configuration() -> None:
    ensure_data_dir()
    mode = storage_mode()
    logger.info("Queue storage path: %s", DATA_DIR)
    logger.info("Queue storage mode: %s", mode)
    if require_persistent_storage() and mode == "railway_ephemeral":
        raise RuntimeError(
            "Persistent queue storage is not configured for Railway.\n"
            "Attach a Railway Volume and mount it to /app/data, or set DATA_DIR to the mounted volume path.\n"
            "If you intentionally want ephemeral storage, set REQUIRE_PERSISTENT_STORAGE=false."
        )
    if mode == "railway_ephemeral":
        logger.warning(
            "Railway volume not detected. Queue data is running on ephemeral storage and may reset on deploy or restart. "
            "Set REQUIRE_PERSISTENT_STORAGE=true after attaching a Railway Volume if you want startup to enforce persistence."
        )


async def sync_commands(application: Application) -> None:
    admin_id = application.bot_data.get("admin_id")
    await application.bot.set_my_commands(
        build_setup_commands() if admin_id is None else build_user_commands(),
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


def submission_csv_row(submission: dict) -> dict[str, str]:
    request = normalize_payload(submission.get("request", {}))
    user = submission.get("user", {})
    notes = submission.get("notes", [])
    todos = submission.get("todos", [])
    responses = submission.get("responses", [])
    return {
        "id": str(int(submission.get("id", 0))),
        "created_at": str(submission.get("created_at", "")),
        "updated_at": str(submission.get("updated_at", "")),
        "display_time": str(submission.get("display_time", "")),
        "status": str(submission.get("status", "")),
        "source": str(submission.get("source", "")),
        "user_id": str(user.get("id", "")),
        "user_display_name": str(user.get("display_name", "")),
        "user_username": str(user.get("username", "")),
        "request_kind": str(request.get("request_kind", "")),
        "track": str(request.get("track", "")),
        "level": str(request.get("level", "")),
        "urgency": str(request.get("urgency", "")),
        "answer_mode": str(request.get("answer_mode", "")),
        "contact_visibility": str(request.get("contact_visibility", "")),
        "goal": str(request.get("goal", "")),
        "challenge": str(request.get("challenge", "")),
        "question": str(request.get("question", "")),
        "context": str(request.get("context", "")),
        "public_request": str(submission.get("public_request", "")),
        "response_count": str(len(responses)),
        "note_count": str(len(notes)),
        "todo_count": str(len(todos)),
        "open_todo_count": str(sum(1 for todo in todos if todo.get("status") != "done")),
        "private_thread_json": json.dumps(submission.get("private_thread", {}), ensure_ascii=False),
        "discussion_json": json.dumps(submission.get("discussion", {}), ensure_ascii=False),
        "notes_json": json.dumps(notes, ensure_ascii=False),
        "todos_json": json.dumps(todos, ensure_ascii=False),
        "responses_json": json.dumps(responses, ensure_ascii=False),
    }


def write_submissions_csv_unlocked(submissions: list[dict]) -> None:
    temp_csv = SUBMISSIONS_CSV_FILE.with_suffix(".csv.tmp")
    with temp_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUBMISSION_CSV_COLUMNS)
        writer.writeheader()
        for submission in submissions:
            writer.writerow(submission_csv_row(submission))
    os.replace(temp_csv, SUBMISSIONS_CSV_FILE)


def parse_submission_csv_json(raw_value: str, fallback):
    text = (raw_value or "").strip()
    if not text:
        return fallback
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return fallback


def read_submissions_csv_unlocked() -> list[dict]:
    ensure_data_dir()
    if not SUBMISSIONS_CSV_FILE.exists():
        return []

    submissions: list[dict] = []
    with SUBMISSIONS_CSV_FILE.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ticket_id = parse_numeric_id(str(row.get("id", "")))
            if ticket_id is None:
                continue
            submissions.append(
                {
                    "id": ticket_id,
                    "created_at": str(row.get("created_at", "")),
                    "updated_at": str(row.get("updated_at", "")),
                    "display_time": str(row.get("display_time", "")),
                    "status": str(row.get("status", "")),
                    "source": str(row.get("source", "")),
                    "user": {
                        "id": parse_numeric_id(str(row.get("user_id", ""))),
                        "display_name": str(row.get("user_display_name", "")),
                        "username": str(row.get("user_username", "")),
                    },
                    "request": normalize_payload(
                        {
                            "request_kind": row.get("request_kind", ""),
                            "track": row.get("track", ""),
                            "level": row.get("level", ""),
                            "urgency": row.get("urgency", ""),
                            "answer_mode": row.get("answer_mode", ""),
                            "contact_visibility": row.get("contact_visibility", ""),
                            "goal": row.get("goal", ""),
                            "challenge": row.get("challenge", ""),
                            "question": row.get("question", ""),
                            "context": row.get("context", ""),
                        }
                    ),
                    "public_request": str(row.get("public_request", "")),
                    "private_thread": parse_submission_csv_json(row.get("private_thread_json", ""), {}),
                    "discussion": parse_submission_csv_json(row.get("discussion_json", ""), {}),
                    "notes": parse_submission_csv_json(row.get("notes_json", ""), []),
                    "todos": parse_submission_csv_json(row.get("todos_json", ""), []),
                    "responses": parse_submission_csv_json(row.get("responses_json", ""), []),
                }
            )
    return submissions


def persist_submissions_unlocked(submissions: list[dict]) -> None:
    temp_file = SUBMISSIONS_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as handle:
        for submission in submissions:
            handle.write(json.dumps(submission, ensure_ascii=True) + "\n")
    os.replace(temp_file, SUBMISSIONS_FILE)
    write_submissions_csv_unlocked(submissions)


def _read_submissions_unlocked() -> list[dict]:
    ensure_data_dir()
    if not SUBMISSIONS_FILE.exists():
        return read_submissions_csv_unlocked()

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
    with STORAGE_LOCK:
        persist_submissions_unlocked(submissions)


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
        persist_submissions_unlocked(submissions)


def mutate_submission(
    ticket_id: int,
    mutate_callback,
) -> dict | None:
    with STORAGE_LOCK:
        submissions = _read_submissions_unlocked()
        for index, submission in enumerate(submissions):
            if int(submission.get("id", 0)) != ticket_id:
                continue

            updated_at = datetime.now(timezone.utc).isoformat()
            changed = mutate_callback(submission, updated_at)
            if not changed:
                return submission

            submission["updated_at"] = updated_at
            submissions[index] = submission
            persist_submissions_unlocked(submissions)
            return submission
    return None


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
            persist_submissions_unlocked(submissions)
            return submission
    return None


def timestamp_now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def format_display_datetime(value: str | None) -> str:
    parsed = parse_iso_datetime(value)
    if parsed is None:
        return "Not set"
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def format_status(status: str) -> str:
    labels = {
        "open": "Open",
        "answered_private": "Answered privately",
        "answered_public": "Answered publicly",
        "ended": "Ended",
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


def normalize_request_kind(value: str) -> str:
    lowered = (value or "").strip().lower()
    if not lowered:
        return "mentorship"
    if lowered in {MENTORSHIP_REQUEST_LABEL.lower(), "mentor", "mentorship"}:
        return "mentorship"
    if lowered in {TECHNICAL_SERVICE_LABEL.lower(), "service", "technical service", "technical_support"}:
        return "technical_service"
    if lowered in {RESEARCH_COLLABORATION_LABEL.lower(), "collaboration", "research collaboration"}:
        return "research_collaboration"
    if lowered in {SPEAKING_WORKSHOP_LABEL.lower(), "speaking", "workshop", "speaking or workshop"}:
        return "speaking_workshop"
    return "other"


def format_request_kind(value: str) -> str:
    labels = {
        "mentorship": MENTORSHIP_REQUEST_LABEL,
        "technical_service": TECHNICAL_SERVICE_LABEL,
        "research_collaboration": RESEARCH_COLLABORATION_LABEL,
        "speaking_workshop": SPEAKING_WORKSHOP_LABEL,
        "other": OTHER_REQUEST_LABEL,
    }
    return labels.get(normalize_request_kind(value), OTHER_REQUEST_LABEL)


def short_request_kind_label(value: str) -> str:
    labels = {
        "mentorship": "Mentorship",
        "technical_service": "Service",
        "research_collaboration": "Collab",
        "speaking_workshop": "Speaking",
        "other": "Other",
    }
    return labels.get(normalize_request_kind(value), "Other")


def track_menu_for_request_kind(value: str) -> list[list[str]]:
    normalized_kind = normalize_request_kind(value)
    menus = {
        "mentorship": TRACK_MENU,
        "technical_service": [
            ["Photonic design", "Simulation workflow"],
            ["Physics-informed optimization", "Research workflow"],
            ["Technical review", "Write my own"],
        ],
        "research_collaboration": [
            ["Joint research", "Project collaboration"],
            ["Student project support", "Publication planning"],
            ["Lab or team support", "Write my own"],
        ],
        "speaking_workshop": [
            ["Talk invitation", "Workshop"],
            ["Panel or Q&A", "Student session"],
            ["Community event", "Write my own"],
        ],
    }
    return menus.get(normalized_kind, TRACK_MENU)


def build_track_prompt(value: str) -> str:
    prompts = {
        "mentorship": "Choose the topic that fits your request best.",
        "technical_service": "Choose the service scope that fits your request best.",
        "research_collaboration": "Choose the collaboration area that fits your request best.",
        "speaking_workshop": "Choose the speaking or workshop topic that fits your request best.",
        "other": "Choose the topic that fits your request best.",
    }
    prompt = prompts.get(normalize_request_kind(value), prompts["other"])
    return f"{prompt}\nYou can tap a suggestion or write your own topic."


def intake_total_steps(mode: str) -> int:
    return 3 if mode == "quick" else 4


def is_specific_track(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return lowered not in {"", "general", "general / custom", "write my own"}


def looks_like_direct_question(value: str) -> bool:
    text = (value or "").strip().lower()
    if not text or text == "not provided":
        return False
    starters = (
        "what ",
        "how ",
        "why ",
        "should ",
        "can ",
        "could ",
        "would ",
        "will ",
        "is ",
        "are ",
        "do ",
        "does ",
        "which ",
        "where ",
        "when ",
    )
    return "?" in text or text.startswith(starters)


def assess_request_quality(request: dict) -> dict[str, str | int]:
    score = 0
    improvements: list[str] = []
    goal = request.get("goal", "Not provided")
    challenge = request.get("challenge", "Not provided")
    question = request.get("question", "Not provided")
    context = request.get("context", "No extra context")

    if is_specific_track(request.get("track", "")):
        score += 5
    else:
        improvements.append("add a short topic if it changes the answer")

    if request.get("level") != "Not provided":
        score += 5
    else:
        improvements.append("share your stage if it changes the answer")

    if goal != "Not provided":
        score += 10
    else:
        improvements.append("add one concrete outcome")

    if challenge != "Not provided":
        score += 10
    else:
        improvements.append("name the main blocker")

    if question != "Not provided":
        score += 15
        if looks_like_direct_question(question):
            score += 15
        else:
            improvements.append("turn the request into one direct question")

        if len(question) <= 220 and question.count("?") <= 1:
            score += 15
        else:
            improvements.append("reduce it to one focused question")
    else:
        improvements.append("ask one direct question")

    if context != "No extra context":
        score += 20
    else:
        improvements.append("add one context detail, attempt, or deadline")

    if request.get("urgency") in URGENCY_CHOICES:
        score += 5

    if score >= 90:
        grade = "A"
        label = "Very ready"
    elif score >= 80:
        grade = "B"
        label = "Ready"
    elif score >= 65:
        grade = "C"
        label = "Usable"
    elif score >= 50:
        grade = "D"
        label = "Needs sharpening"
    else:
        grade = "E"
        label = "Needs context"

    improvement = improvements[0] if improvements else "Ready for a focused answer."
    return {
        "score": score,
        "grade": grade,
        "label": label,
        "improvement": improvement,
    }


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
    quality = assess_request_quality(request)
    if int(quality["score"]) < 45:
        return "need_context"
    if request.get("question") == "Not provided":
        return "need_context"
    if (
        request.get("context") == "No extra context"
        and request.get("goal") == "Not provided"
        and request.get("challenge") == "Not provided"
    ):
        return "need_context"
    if len(request.get("question", "")) > 220 or request.get("question", "").count("?") > 1:
        return "narrow_scope"
    if "startup" in track or "startup" in combined_text:
        return "startup_focus"
    if "career" in track or any(keyword in combined_text for keyword in ["cv", "resume", "linkedin", "job"]):
        return "career_next"
    return None


def build_fast_route_hint(request: dict) -> str:
    quality = assess_request_quality(request)
    request_kind = normalize_request_kind(request.get("request_kind", ""))
    if request_kind in {"technical_service", "research_collaboration", "speaking_workshop"} and allows_public_reply(
        request.get("answer_mode", "private")
    ):
        return "Consider a private reply first. Scoped work and collaboration requests are usually handled best privately."
    if int(quality["score"]) < 45:
        return "Ask for one sharper round of context before giving a detailed answer."
    if (
        request.get("goal") == "Not provided"
        and request.get("challenge") == "Not provided"
        and request.get("context") == "No extra context"
    ):
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
    quality = assess_request_quality(request)
    template_key = suggest_quick_reply_template(request)
    lines = [
        "Fast read",
        f"Request grade: {quality['grade']} ({quality['score']}/100, {quality['label']})",
        f"Main ask: {trim_text(request['question'], 180)}",
    ]
    if request.get("request_kind", "mentorship") not in {"mentorship", "other"}:
        lines.append(f"Request type: {format_request_kind(request.get('request_kind', 'mentorship'))}")
    if request.get("goal") != "Not provided":
        lines.append(f"Wanted outcome: {trim_text(request['goal'], 140)}")
    if request.get("challenge") != "Not provided":
        lines.append(f"Main blocker: {trim_text(request['challenge'], 140)}")
    lines.extend(
        [
            f"Fastest route: {build_fast_route_hint(request)}",
            f"Best improvement: {quality['improvement']}",
            (
                f"Suggested quick reply: /quickreply {ticket_id} {template_key}"
                if template_key
                else "Suggested quick reply: answer directly"
            ),
        ]
    )
    return "\n".join(lines)


def public_reply_block_message(ticket_id: int) -> str:
    return (
        f"Ticket #{ticket_id} is locked to private replies because the user selected {PRIVATE_REPLY_LABEL}.\n"
        "Use /reply or reply to the private bot thread instead."
    )


def ended_ticket_message(ticket_id: int) -> str:
    return (
        f"Ticket #{ticket_id} has already been ended.\n"
        "Start a new ticket if you want help with a new or continued question."
    )


def public_followup_command(ticket_id: int) -> str:
    return f"/followup {ticket_id}"


def ticket_is_ended(submission: dict) -> bool:
    return submission.get("status") == "ended"


def latest_public_response(submission: dict) -> dict | None:
    for response in reversed(submission.get("responses", [])):
        if response.get("mode") in {"public", "public_manual", "public_discussion", "public_channel"}:
            return response
    return None


def ticket_has_public_answer(submission: dict) -> bool:
    return latest_public_response(submission) is not None or submission.get("status") == "answered_public"


def user_followup_available(submission: dict) -> bool:
    if ticket_is_ended(submission):
        return False
    if latest_public_response(submission) is not None:
        return True
    return any(response.get("direction") == "mentor_to_user" for response in submission.get("responses", []))


def latest_public_link(submission: dict) -> str:
    public_response = latest_public_response(submission) or {}
    return normalize_https_url(public_response.get("link", ""))


def user_ticket_callback_data(prefix: str, ticket_id: int) -> str:
    return f"{prefix}{ticket_id}"


def build_user_ticket_markup(
    submission: dict,
    public_link: str = "",
    force_continue: bool = False,
) -> InlineKeyboardMarkup | None:
    ticket_id = int(submission.get("id", 0))
    buttons: list[InlineKeyboardButton] = []
    resolved_public_link = normalize_https_url(public_link) or latest_public_link(submission)
    if force_continue or user_followup_available(submission):
        buttons.append(
            InlineKeyboardButton(
                "Continue ticket",
                callback_data=user_ticket_callback_data(USER_CONTINUE_CALLBACK_PREFIX, ticket_id),
            )
        )
    meeting_link = build_meeting_link(ticket_id, submission)
    if meeting_link and not ticket_is_ended(submission):
        buttons.append(InlineKeyboardButton("Book meeting", url=meeting_link))
    if resolved_public_link:
        buttons.append(InlineKeyboardButton("Open answer", url=resolved_public_link))
    about_url = mentor_about_url()
    if about_url:
        buttons.append(InlineKeyboardButton("About mentor", url=about_url))
    if not ticket_is_ended(submission):
        buttons.append(
            InlineKeyboardButton(
                "Close ticket",
                callback_data=user_ticket_callback_data(USER_CLOSE_CALLBACK_PREFIX, ticket_id),
            )
        )
    return build_inline_markup(buttons)


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


def public_followup_enabled(submission: dict) -> bool:
    request = normalize_payload(submission.get("request", {}))
    return (
        allows_public_reply(request.get("answer_mode", "private"))
        and ticket_has_public_answer(submission)
        and not private_thread_enabled(submission)
        and not ticket_is_ended(submission)
    )


def normalize_contact_visibility(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered in {"hide", "hidden", HIDE_CONTACT_LABEL.lower()}:
        return "hidden"
    return "shown"


def format_contact_visibility(value: str) -> str:
    return "Private" if normalize_contact_visibility(value) == "hidden" else "Visible to admin"


def format_source(value: str) -> str:
    labels = {
        "guided_flow": "Guided request",
        "quick_message": "Quick request",
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


def message_has_attachment(message) -> bool:
    return getattr(message, "effective_attachment", None) is not None


def message_supports_caption(message) -> bool:
    return any(
        [
            getattr(message, "photo", None),
            getattr(message, "video", None) is not None,
            getattr(message, "voice", None) is not None,
            getattr(message, "audio", None) is not None,
            getattr(message, "document", None) is not None,
            getattr(message, "animation", None) is not None,
        ]
    )


def message_body_text(message) -> str:
    return (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()


def message_content_summary(message) -> str:
    body = message_body_text(message)
    if body:
        return body

    document = getattr(message, "document", None)
    if document is not None:
        filename = clean_text(getattr(document, "file_name", ""), "")
        return f"[Document: {filename}]" if filename else "[Document]"
    if getattr(message, "photo", None):
        return "[Photo]"
    if getattr(message, "video", None) is not None:
        return "[Video]"
    if getattr(message, "voice", None) is not None:
        return "[Voice note]"
    if getattr(message, "audio", None) is not None:
        return "[Audio]"
    if getattr(message, "video_note", None) is not None:
        return "[Video note]"
    if getattr(message, "animation", None) is not None:
        return "[Animation]"
    if getattr(message, "sticker", None) is not None:
        return "[Sticker]"
    return "[Attachment]"


def build_attachment_caption(prefix: str, body: str) -> str:
    clean_prefix = clean_text(prefix, "Ticket update")
    clean_body = clean_text(body, "")
    if not clean_body:
        return trim_text(clean_prefix, MAX_ATTACHMENT_CAPTION_LENGTH)

    remaining = max(MAX_ATTACHMENT_CAPTION_LENGTH - len(clean_prefix) - 2, 1)
    return f"{clean_prefix}\n\n{trim_text(clean_body, remaining)}"


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
    request_kind = normalize_request_kind(payload.get("request_kind", ""))
    goal = sanitize_public_text(payload.get("goal", ""), 180)
    challenge = sanitize_public_text(payload.get("challenge", ""), 220)
    question = sanitize_public_text(payload.get("question", ""), 420)

    if request_kind != "mentorship":
        sections.append(f"Request type:\n{format_request_kind(request_kind)}")
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
        destinations.append("the discussion group")
    if PUBLIC_CHANNEL_URL:
        destinations.append("the public channel")
    if not destinations:
        return "the public channel or discussion once configured"
    return " or ".join(destinations)


def calendly_url() -> str:
    if CALENDLY_URL:
        return CALENDLY_URL
    return normalize_https_url(read_configured_tag("booking"))


def booking_enabled() -> bool:
    return bool(calendly_url())


def add_query_params(url: str, params: dict[str, str]) -> str:
    normalized_url = normalize_https_url(url)
    if not normalized_url:
        return ""

    parsed = urlsplit(normalized_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        if key and value:
            query[key] = value
    return urlunsplit(
        (
            "https",
            parsed.netloc,
            parsed.path,
            urlencode(query),
            parsed.fragment,
        )
    )


def build_meeting_link(ticket_id: int | None = None, submission: dict | None = None) -> str:
    base_url = calendly_url()
    if not base_url:
        return ""

    params = {
        "utm_source": "telegram-bot",
        "utm_medium": "request-bot",
    }
    if ticket_id is not None:
        params["utm_campaign"] = f"ticket-{ticket_id}"
    if submission is not None:
        request = normalize_payload(submission.get("request", {}))
        params["utm_content"] = normalize_answer_mode(request.get("answer_mode", "private"))
    return add_query_params(base_url, params)


def build_ticket_tags(ticket_id: int, submission: dict | None = None) -> dict[str, str]:
    tags = {
        "ticket": str(ticket_id),
        "ticket_id": str(ticket_id),
    }
    meeting_link = build_meeting_link(ticket_id, submission)
    if meeting_link:
        tags["booking"] = meeting_link
        tags["meeting_link"] = meeting_link
        tags["booking_link"] = meeting_link
        tags["calendly"] = meeting_link
    return tags


def build_meeting_message(ticket_id: int | None = None, submission: dict | None = None, admin_view: bool = False) -> str:
    link = build_meeting_link(ticket_id, submission)
    if not link:
        if admin_view:
            return (
                "Meeting booking is not configured yet.\n"
                "Set CALENDLY_URL or a booking tag to enable it."
            )
        return "Meeting booking is not available right now."

    lines = ["Meeting", f"Use this when a short call with {MENTOR_LABEL or DEFAULT_MENTOR_LABEL} will move the request faster."]
    if ticket_id is not None:
        lines.extend(
            [
                "",
                f"Ticket: #{ticket_id}",
                f"If the booking form has notes, mention ticket #{ticket_id}.",
            ]
        )
    return "\n".join(lines)


def build_meeting_markup(link: str, ticket_id: int | None = None, admin: bool = False) -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    if link:
        buttons.append(InlineKeyboardButton("Open booking page", url=link))
        if admin:
            buttons.append(build_copy_button("Copy meeting link", link))
    if admin and ticket_id is not None:
        buttons.append(build_copy_button("Copy /sendmeeting", f"/sendmeeting {ticket_id}"))
    return build_inline_markup(buttons)


def build_meeting_status_message() -> str:
    base_url = calendly_url()
    if not base_url:
        return (
            "Calendly booking is not configured.\n\n"
            "Set CALENDLY_URL in Railway or .env, or define TAG_BOOKING, to enable booking links.\n"
            "Ticket-specific meeting links will then add tracking parameters automatically."
        )

    return (
        "Meeting booking status\n\n"
        f"Label: {CALENDLY_LABEL}\n"
        f"Base link: {base_url}\n\n"
        "Ticket-specific links add tracking parameters so bookings can stay tied to the right ticket.\n"
        "Fast actions\n"
        "/sendmeeting <ticket>\n"
        "/meeting <ticket>\n"
        "{{meeting_link}}"
    )


def build_services_message(admin_view: bool = False) -> str:
    link = cta_services_url()
    if not link:
        if admin_view:
            return (
                "The services page is not configured yet.\n"
                "Set CTA_SERVICES_URL directly, or set CTA_WEBSITE_URL or TAG_WEBSITE so the bot can open /services."
            )
        return "That page is not available right now."

    return f"Services\nSee where {MENTOR_LABEL or DEFAULT_MENTOR_LABEL} can help beyond a single question."


def build_services_markup(link: str) -> InlineKeyboardMarkup | None:
    if not link:
        return None

    buttons = [
        InlineKeyboardButton("Open services page", url=link),
        build_copy_button("Copy services link", link),
    ]
    return build_inline_markup(buttons)


def cta_channel_url() -> str:
    return CTA_CHANNEL_URL or PUBLIC_CHANNEL_URL


def mentor_about_url() -> str:
    return website_page_url("about") or cta_website_url() or linkedin_url()


def cta_website_url() -> str:
    if CTA_WEBSITE_URL:
        return CTA_WEBSITE_URL
    return normalize_https_url(read_configured_tag("website"))


def configured_url_tag(name: str) -> str:
    return normalize_https_url(read_configured_tag(name))


def website_page_url(section: str) -> str:
    normalized_section = (section or "").strip().strip("/")
    if not normalized_section:
        return cta_website_url()

    direct_url = configured_url_tag(normalized_section)
    if direct_url:
        return direct_url

    website_url = cta_website_url()
    if not website_url:
        return ""

    parsed = urlsplit(website_url)
    base_path = parsed.path.rstrip("/")
    section_path = f"/{normalized_section}"
    if base_path == section_path or base_path.endswith(section_path):
        page_path = base_path
    else:
        page_path = f"{base_path}/{normalized_section}" if base_path else section_path
    return urlunsplit((parsed.scheme, parsed.netloc, page_path, "", ""))


def contact_page_url() -> str:
    return website_page_url("contact")


def cv_page_url() -> str:
    return website_page_url("cv")


def contact_email() -> str:
    value = read_configured_tag("email")
    if not value or "@" not in value or any(char.isspace() for char in value):
        return ""
    return value


def linkedin_url() -> str:
    return configured_url_tag("linkedin")


def whatsapp_url() -> str:
    return configured_url_tag("whatsapp")


def github_url() -> str:
    return configured_url_tag("github")


def orcid_url() -> str:
    return configured_url_tag("orcid")


def scholar_url() -> str:
    return configured_url_tag("scholar")


def cta_services_url() -> str:
    if CTA_SERVICES_URL:
        return CTA_SERVICES_URL
    return website_page_url("services")


def build_contact_message(admin_view: bool = False) -> str:
    email = contact_email()
    contact_url = contact_page_url()
    booking_url = calendly_url()
    linkedin = linkedin_url()
    whatsapp = whatsapp_url()

    if not any([email, contact_url, booking_url, linkedin, whatsapp]):
        if admin_view:
            return (
                "Direct contact routes are not configured yet.\n"
                "Set CTA_WEBSITE_URL or TAG_CONTACT first, and optionally define tags like TAG_EMAIL, TAG_LINKEDIN, or TAG_WHATSAPP."
            )
        return "Direct contact routes are not available right now."

    return f"Contact\nChoose how you'd like to reach {MENTOR_LABEL or DEFAULT_MENTOR_LABEL}."


def build_contact_markup() -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    contact_url = contact_page_url()
    booking_url = calendly_url()
    linkedin = linkedin_url()
    whatsapp = whatsapp_url()
    email = contact_email()
    if contact_url:
        buttons.append(InlineKeyboardButton("Open contact page", url=contact_url))
    if booking_url:
        buttons.append(InlineKeyboardButton("Book a call", url=booking_url))
    if linkedin:
        buttons.append(InlineKeyboardButton("LinkedIn", url=linkedin))
    if whatsapp:
        buttons.append(InlineKeyboardButton("WhatsApp", url=whatsapp))
    if email:
        buttons.append(build_copy_button("Copy email", email))
    return build_inline_markup(buttons)


def website_navigation_links() -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    website_url = cta_website_url()
    if website_url:
        links.append(("Home", website_url))
    for label, section in WEBSITE_NAV_ITEMS:
        url = website_page_url(section)
        if url:
            links.append((label, url))
    return links


def build_website_message(admin_view: bool = False) -> str:
    links = website_navigation_links()
    if not links:
        if admin_view:
            return (
                "The website is not configured yet.\n"
                "Set CTA_WEBSITE_URL or TAG_WEBSITE so the bot can open the website sections."
            )
        return "The website is not available right now."

    return "Website\nOpen a section below."


def build_website_markup() -> InlineKeyboardMarkup | None:
    buttons = [InlineKeyboardButton(label, url=url) for label, url in website_navigation_links()]
    website_url = cta_website_url()
    if website_url:
        buttons.append(build_copy_button("Copy website", website_url))
    return build_inline_markup(buttons)


def build_profile_message(admin_view: bool = False) -> str:
    if not admin_view and not feature_profile_enabled():
        return "The public profile is not available right now."

    about_url = website_page_url("about") or cta_website_url()
    publications_url = website_page_url("publications")
    talks_url = website_page_url("talks")
    projects_url = website_page_url("projects")
    services_url = cta_services_url()
    cv_url = cv_page_url()
    lines = [f"Profile: {MENTOR_LABEL or DEFAULT_MENTOR_LABEL}"]
    if MENTOR_IDENTITY_TEXT:
        lines.extend(["", MENTOR_IDENTITY_TEXT])
    lines.extend(["", "Use the buttons below for background, publications, projects, and current scope.", "", "Current scope"])
    lines.extend(f"- {item}" for item in PROFILE_SCOPE_LINES)
    return "\n".join(line for line in lines if line)


def build_profile_markup() -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    about_url = website_page_url("about") or cta_website_url()
    publications_url = website_page_url("publications")
    talks_url = website_page_url("talks")
    projects_url = website_page_url("projects")
    services_url = cta_services_url()
    cv_url = cv_page_url()
    github = github_url()
    orcid = orcid_url()
    scholar = scholar_url()
    if about_url:
        buttons.append(InlineKeyboardButton("About", url=about_url))
    if publications_url:
        buttons.append(InlineKeyboardButton("Publications", url=publications_url))
    if talks_url:
        buttons.append(InlineKeyboardButton("Talks", url=talks_url))
    if projects_url:
        buttons.append(InlineKeyboardButton("Projects", url=projects_url))
    if services_url:
        buttons.append(InlineKeyboardButton("Services", url=services_url))
    if cv_url:
        buttons.append(InlineKeyboardButton("CV", url=cv_url))
    if github:
        buttons.append(InlineKeyboardButton("GitHub", url=github))
    if orcid:
        buttons.append(InlineKeyboardButton("ORCID", url=orcid))
    if scholar:
        buttons.append(InlineKeyboardButton("Scholar", url=scholar))
    return build_inline_markup(buttons)


def build_user_start_message() -> str:
    mentor_name = escape_html(MENTOR_LABEL or DEFAULT_MENTOR_LABEL)
    lines = ["<b>Welcome</b>"]
    lines.append(f"Free mentorship with <b>{mentor_name}</b>.")
    lines.extend(
        [
            "",
            "<b>Start here</b>",
            f"- <b>{escape_html(QUICK_QUESTION_LABEL)}</b> for the fastest mentorship question",
            "- If context matters, include it in the same message",
        ]
    )
    if feature_booking_enabled():
        lines.append(f"- <b>{escape_html(BOOK_MEETING_LABEL)}</b> if a call is the better route")
    if feature_services_enabled():
        lines.append(f"- <b>{escape_html(SERVICES_LABEL)}</b> for work beyond mentorship")
    lines.extend(
        [
            "",
            "Your Telegram details are only used to route replies.",
            "You can decide whether your name and username stay visible to the admin.",
        ]
    )
    if feature_channel_updates_enabled():
        lines.append("Use /muteupdates if you want to pause channel updates in the bot.")
    return "\n".join(lines)


def build_user_help_message() -> str:
    lines = [
        "<b>How this works</b>",
        "- This bot is mainly for mentorship questions",
        f"- <b>{escape_html(QUICK_QUESTION_LABEL)}</b> is the default and fastest option",
        "- Start with one clear question",
        "- Put any useful context in the same message",
        "- Use /status <ticket> to check progress",
        "- Use /cancel to stop the current guided flow",
    ]
    extra_routes: list[str] = []
    if feature_booking_enabled():
        extra_routes.append("/meeting")
    if feature_services_enabled():
        extra_routes.append("/services")
    if feature_contact_enabled():
        extra_routes.append("/contact")
    if feature_website_enabled():
        extra_routes.append("/website")
    if feature_profile_enabled():
        extra_routes.append("/profile")
    if extra_routes:
        lines.extend(["", "<b>More</b>", "- " + "  ".join(extra_routes)])
    if feature_channel_updates_enabled():
        lines.append("- /muteupdates and /resumeupdates control channel updates in the bot")
    return "\n".join(lines)


def mentor_brand_snippet() -> str:
    ignored = {"regards", "best", "thanks", "thank you", "from"}
    mentor_name = (MENTOR_LABEL or DEFAULT_MENTOR_LABEL).strip().lower()
    for raw_line in MENTOR_IDENTITY_TEXT.splitlines():
        line = raw_line.strip()
        lowered = line.lower().rstrip(",:")
        if not line:
            continue
        if lowered in ignored:
            continue
        if "@" in line or "http" in lowered or ".com" in lowered or ".io" in lowered:
            continue
        if mentor_name and lowered == mentor_name:
            continue
        return trim_text(line, 90)
    return ""


def build_start_brand_message() -> str:
    mentor_name = escape_html(MENTOR_LABEL or DEFAULT_MENTOR_LABEL)
    lines = [f"<b>Who replies here?</b>", mentor_name]
    snippet = mentor_brand_snippet()
    if snippet:
        lines.append(escape_html(snippet))
    notes: list[str] = []
    if mentor_about_url():
        notes.append("Use About mentor to see background.")
    if cta_channel_url():
        notes.append("Channel is optional if you want public notes.")
    if notes:
        lines.extend(["", " ".join(notes)])
    return "\n".join(lines)


def build_start_brand_markup() -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    channel_url = cta_channel_url()
    about_url = mentor_about_url()
    if about_url:
        buttons.append(InlineKeyboardButton("About mentor", url=about_url))
    if channel_url:
        buttons.append(InlineKeyboardButton("Follow channel", url=channel_url))
    return build_inline_markup(buttons)


def build_user_cta_lines(ticket_id: int | None = None, submission: dict | None = None) -> list[str]:
    lines: list[str] = []
    if CTA_EXTRA_TEXT:
        lines.append(CTA_EXTRA_TEXT)
    return lines


def append_user_cta(text: str, ticket_id: int | None = None, submission: dict | None = None) -> str:
    cta_lines = build_user_cta_lines(ticket_id, submission)
    if not cta_lines:
        return text
    return f"{text}\n\n" + "\n".join(cta_lines)


async def reply_with_optional_logo(message, text: str, reply_markup, parse_mode: str | None = None) -> None:
    if MENTOR_LOGO_URL:
        try:
            await message.reply_photo(
                photo=MENTOR_LOGO_URL,
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            )
            return
        except TelegramError:
            logger.exception("Failed to send mentor logo")

    await message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        link_preview_options=NO_PREVIEW,
    )


def build_public_posted_at_text(mode: str | None, link: str = "") -> str:
    if mode == "public_discussion":
        return "the linked discussion group"
    if mode == "public_channel":
        return "the linked public channel"
    if normalize_https_url(link):
        return "the published post"
    return build_public_destination_text()


def should_skip_channel_broadcast(message) -> bool:
    text = ((getattr(message, "text", None) or getattr(message, "caption", None) or "")).strip()
    return bool(re.match(r"^(Public answer|Update) for ticket #\d+", text))


def step_text(step: int, total: int, body: str) -> str:
    return f"Step {step}/{total}\n{body}"


def build_contact_visibility_prompt(user) -> str:
    display_name = user.full_name or user.first_name or "Unknown user"
    username = f"@{user.username}" if user.username else "Not set"
    return (
        "How should your details appear?\n\n"
        f"Name: {display_name}\n"
        f"Username: {username}\n\n"
        "The bot still keeps the private routing details it needs to deliver replies.\n"
        "Choose whether your name and username stay visible to the admin."
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
    if MENTOR_LOGO_URL:
        tags["logo"] = MENTOR_LOGO_URL
    booking_url = calendly_url()
    if booking_url:
        tags["booking"] = booking_url
        tags["booking_link"] = booking_url
        tags["calendly"] = booking_url
        tags["meeting_link"] = booking_url
    if PUBLIC_CHANNEL_URL:
        tags["public_channel"] = PUBLIC_CHANNEL_URL
        tags["channel"] = PUBLIC_CHANNEL_URL
    channel_url = cta_channel_url()
    if channel_url:
        tags["cta_channel"] = channel_url
    website_url = cta_website_url()
    if website_url:
        tags["cta_website"] = website_url
    services_url = cta_services_url()
    if services_url:
        tags["cta_services"] = services_url
        tags["services"] = services_url
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
        "Use the copy buttons below to place a tag quickly.",
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
            "{{meeting_link}} -> ticket-specific Calendly link when a ticket number is available",
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


def build_tags_markup() -> InlineKeyboardMarkup:
    tag_names = sorted(
        set(build_builtin_tags()) | set(read_env_tags()) | set(read_saved_tags()) | {"ticket", "ticket_id"}
    )
    buttons = [build_copy_button(f"{{{{{name}}}}}", f"{{{{{name}}}}}") for name in tag_names]
    return InlineKeyboardMarkup(chunk_items(buttons, 2))


def build_admin_help_message() -> str:
    return (
        "<b>Admin guide</b>\n\n"
        "Start with /dashboard for the queue overview.\n"
        "Open one case with /ticket <ticket> or scan the queue with /tickets.\n"
        "Use /reply to answer, /note for internal context, and /todo for follow-up tracking.\n"
        "Use /templates and /tags when you want faster replies or reusable text.\n"
        "Use /storagestatus, /setdiscussion, /setchannel, and /meetingstatus when checking setup.\n\n"
        "The buttons below copy the most common command patterns."
    )


def build_admin_help_markup() -> InlineKeyboardMarkup:
    buttons = [
        build_copy_button("Copy /dashboard", "/dashboard"),
        build_copy_button("Copy /tickets", "/tickets"),
        build_copy_button("Copy /ticket", "/ticket "),
        build_copy_button("Copy /reply", "/reply "),
        build_copy_button("Copy /todo", "/todo "),
        build_copy_button("Copy /note", "/note "),
        build_copy_button("Copy /templates", "/templates"),
        build_copy_button("Copy /tags", "/tags"),
        build_copy_button("Copy /storagestatus", "/storagestatus"),
        build_copy_button("Copy /meetingstatus", "/meetingstatus"),
    ]
    return build_inline_markup(buttons)


def build_availability_message() -> str:
    availability_text, _ = expand_saved_tags(MENTOR_AVAILABILITY_TEXT)
    message = (
        "Response times\n\n"
        "Requests are handled in focused batches so replies can stay useful and clear.\n\n"
        f"Current timing\n{availability_text}\n\n"
        "Best results come from one clear goal, one blocker, and one direct question.\n"
        "Private tickets close after 1 day without a reply. Public tickets close after 3 days without a follow-up."
    )
    if booking_enabled():
        message += "\n\nIf a call would be faster, use /meeting."
    return message


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


def latest_response(submission: dict) -> dict | None:
    responses = submission.get("responses", [])
    return responses[-1] if responses else None


def normalize_ticket_owner(value: str) -> str | None:
    return TODO_OWNER_ALIASES.get((value or "").strip().lower())


def todo_owner_label(owner: str) -> str:
    return "Admin" if owner == "admin" else "User"


def todo_status_marker(todo: dict) -> str:
    return "[x]" if todo.get("status") == "done" else "[ ]"


def ticket_notes(submission: dict) -> list[dict]:
    notes: list[dict] = []
    for raw_note in submission.get("notes", []):
        if not isinstance(raw_note, dict):
            continue
        note_id = parse_numeric_id(str(raw_note.get("id", "")))
        text = clean_text(str(raw_note.get("text", "")), "")
        if note_id is None or not text:
            continue
        notes.append(
            {
                "id": note_id,
                "text": text,
                "created_at": str(raw_note.get("created_at", "")).strip(),
                "author": clean_text(str(raw_note.get("author", "")), "admin"),
            }
        )
    return notes


def ticket_todos(submission: dict) -> list[dict]:
    todos: list[dict] = []
    for raw_todo in submission.get("todos", []):
        if not isinstance(raw_todo, dict):
            continue
        todo_id = parse_numeric_id(str(raw_todo.get("id", "")))
        owner = normalize_ticket_owner(str(raw_todo.get("owner", "")))
        text = clean_text(str(raw_todo.get("text", "")), "")
        if todo_id is None or owner is None or not text:
            continue
        status = "done" if str(raw_todo.get("status", "")).strip().lower() == "done" else "open"
        todos.append(
            {
                "id": todo_id,
                "owner": owner,
                "text": text,
                "status": status,
                "created_at": str(raw_todo.get("created_at", "")).strip(),
                "updated_at": str(raw_todo.get("updated_at", "")).strip(),
                "done_at": str(raw_todo.get("done_at", "")).strip(),
                "remind_at": str(raw_todo.get("remind_at", "")).strip(),
                "reminder_sent_at": str(raw_todo.get("reminder_sent_at", "")).strip(),
            }
        )
    return todos


def next_ticket_item_id(items: list[dict]) -> int:
    return max((int(item.get("id", 0)) for item in items), default=0) + 1


def find_ticket_todo(submission: dict, todo_id: int) -> dict | None:
    for todo in ticket_todos(submission):
        if int(todo.get("id", 0)) == todo_id:
            return todo
    return None


def open_ticket_todos(submission: dict, owner: str | None = None) -> list[dict]:
    todos = [todo for todo in ticket_todos(submission) if todo.get("status") != "done"]
    if owner is not None:
        todos = [todo for todo in todos if todo.get("owner") == owner]
    return todos


def count_open_ticket_todos(submission: dict, owner: str | None = None) -> int:
    return len(open_ticket_todos(submission, owner))


def has_open_user_todos(submission: dict) -> bool:
    return bool(open_ticket_todos(submission, "user"))


def parse_reminder_offset(value: str) -> timedelta | None:
    match = re.fullmatch(r"(\d+)([mhd])", (value or "").strip().lower())
    if match is None:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if amount <= 0:
        return None
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)


def build_todo_usage() -> str:
    return (
        "Usage: /todo <ticket_number> <admin|user> <task>\n"
        "Or reply to an admin-side ticket message with /todo <admin|user> <task>.\n"
        "Examples:\n"
        "/todo 42 user Find one referral for the target role\n"
        "/todo 42 admin Review the next follow-up"
    )


def build_todo_reminder_usage() -> str:
    return (
        "Usage: /todoremind <ticket_number> <todo_id> <30m|2h|3d|off>\n"
        "Or reply to an admin-side ticket message with /todoremind <todo_id> <30m|2h|3d|off>."
    )


def build_notes_usage() -> str:
    return (
        "Usage: /note <ticket_number> <text>\n"
        "Or reply to an admin-side ticket message with /note <text>."
    )


def format_todo_line(todo: dict, include_owner: bool = True) -> str:
    line = f"#{todo['id']} {todo_status_marker(todo)} {todo['text']}"
    if include_owner:
        line += f" | {todo_owner_label(todo['owner'])}"
    remind_at = todo.get("remind_at")
    if todo.get("status") != "done" and remind_at:
        line += f" | reminder {format_display_datetime(remind_at)}"
    if todo.get("status") == "done" and todo.get("done_at"):
        line += f" | done {format_display_datetime(todo.get('done_at'))}"
    return line


def build_ticket_notes_section(submission: dict, limit: int | None = None) -> str:
    notes = ticket_notes(submission)
    if not notes:
        return "Internal notes\nNone"

    if limit is not None:
        notes = notes[-limit:]

    lines = ["Internal notes"]
    for note in notes:
        lines.extend(
            [
                f"#{note['id']} | {format_display_datetime(note.get('created_at'))}",
                note["text"],
            ]
        )
    return "\n".join(lines)


def build_ticket_todos_section(submission: dict) -> str:
    todos = ticket_todos(submission)
    if not todos:
        return "Checklist\nNone"

    lines = ["Checklist"]
    for todo in todos:
        lines.append(format_todo_line(todo))
    return "\n".join(lines)


def build_user_todos_section(submission: dict) -> str:
    todos = open_ticket_todos(submission, "user")
    if not todos:
        return ""

    lines = ["Open checklist"]
    for todo in todos:
        lines.append(format_todo_line(todo, include_owner=False))
    return "\n".join(lines)


def build_todo_summary_line(submission: dict) -> str:
    open_total = count_open_ticket_todos(submission)
    if open_total == 0:
        return "Checklist: clear"
    return (
        f"Checklist: {open_total} open "
        f"({count_open_ticket_todos(submission, 'admin')} admin, {count_open_ticket_todos(submission, 'user')} user)"
    )


def build_todo_reminder_message(ticket_id: int, submission: dict, todo: dict, owner: str) -> str:
    header = "Admin reminder" if owner == "admin" else "Checklist reminder"
    lines = [
        f"{header} for ticket #{ticket_id}",
        "",
        format_todo_line(todo, include_owner=False),
    ]
    user_todos = open_ticket_todos(submission, owner if owner == "user" else None)
    if owner == "user" and user_todos:
        lines.extend(["", "Current open checklist"])
        for item in user_todos:
            lines.append(format_todo_line(item, include_owner=False))
    elif owner == "admin":
        admin_todos = open_ticket_todos(submission, "admin")
        if admin_todos:
            lines.extend(["", "Open admin checklist"])
            for item in admin_todos:
                lines.append(format_todo_line(item, include_owner=False))
    return "\n".join(lines)


def due_ticket_todos(submission: dict, now: datetime | None = None) -> list[dict]:
    reference_now = now or datetime.now(timezone.utc)
    due: list[dict] = []
    for todo in open_ticket_todos(submission):
        if ticket_is_ended(submission) and todo.get("owner") == "user":
            continue
        remind_at = parse_iso_datetime(todo.get("remind_at"))
        if remind_at is None or remind_at > reference_now:
            continue
        if parse_iso_datetime(todo.get("reminder_sent_at")) is not None:
            continue
        due.append(todo)
    return due


def due_ticket_todo_count(submission: dict, owner: str | None = None) -> int:
    due = due_ticket_todos(submission)
    if owner is not None:
        due = [todo for todo in due if todo.get("owner") == owner]
    return len(due)


def stale_ticket_auto_end_note(submission: dict) -> str:
    if ticket_is_ended(submission):
        return ""

    latest = latest_response(submission)
    now = datetime.now(timezone.utc)
    if latest is None:
        latest_at = parse_iso_datetime(submission.get("updated_at"))
        if latest_at is None:
            return ""
        if submission.get("status") == "answered_private" and now - latest_at >= PRIVATE_TICKET_IDLE_TIMEOUT:
            return "This ticket was ended automatically after 1 day without a reply in the private conversation."
        if submission.get("status") == "answered_public" and now - latest_at >= PUBLIC_TICKET_IDLE_TIMEOUT:
            return "This public ticket was ended automatically after 3 days without a follow-up."
        return ""

    latest_at = parse_iso_datetime(latest.get("created_at")) or parse_iso_datetime(submission.get("updated_at"))
    if latest_at is None:
        return ""

    if latest.get("direction") == "mentor_to_user":
        if now - latest_at >= PRIVATE_TICKET_IDLE_TIMEOUT:
            return "This ticket was ended automatically after 1 day without a reply in the private conversation."
        return ""

    if latest.get("mode") in {"public", "public_manual", "public_discussion", "public_channel"}:
        if private_thread_enabled(submission):
            return ""
        if now - latest_at >= PUBLIC_TICKET_IDLE_TIMEOUT:
            return "This public ticket was ended automatically after 3 days without a follow-up."

    return ""


def classify_queue_state(submission: dict) -> str:
    request = normalize_payload(submission.get("request", {}))
    if ticket_is_ended(submission):
        return "done_closed"
    if has_open_user_todos(submission):
        return "waiting_user"
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


def admin_queue_state_label(state: str) -> str:
    labels = {
        "queue": "Waiting on you",
        "awaiting_private": "Waiting on you (private)",
        "awaiting_public": "Waiting on you (public)",
        "waiting_user": "Waiting on user",
        "done_public": "Answered publicly",
        "done_closed": "Ended",
        "all": "All tickets",
    }
    return labels.get(state, state.replace("_", " ").title())


def admin_queue_state_short_label(state: str) -> str:
    labels = {
        "awaiting_private": "You/private",
        "awaiting_public": "You/public",
        "waiting_user": "User",
        "done_public": "Public done",
        "done_closed": "Ended",
    }
    return labels.get(state, state.replace("_", " ").title())


def latest_activity_value(submission: dict) -> str | None:
    latest = latest_response(submission)
    if latest is not None and latest.get("created_at"):
        return latest.get("created_at")
    return submission.get("updated_at") or submission.get("created_at")


def recent_activity_sort_key(submission: dict) -> tuple[datetime, int]:
    latest_at = parse_iso_datetime(latest_activity_value(submission)) or datetime.min.replace(tzinfo=timezone.utc)
    return latest_at, int(submission.get("id", 0))


def normalize_ticket_list_scope(value: str) -> str | None:
    return TICKET_LIST_SCOPE_ALIASES.get((value or "").strip().lower())


def build_ticket_list_usage() -> str:
    return (
        "Usage: /tickets [queue|private|public|waiting_user|ended|all] [limit]\n"
        "Limit is capped at 25.\n"
        "Examples:\n"
        "/tickets\n"
        "/tickets 20\n"
        "/tickets waiting_user 20\n"
        "/tickets ended 20"
    )


def parse_ticket_list_args(args: list[str]) -> tuple[str | None, int | None]:
    if len(args) > 2:
        return None, None

    scope = "queue"
    limit = DEFAULT_ADMIN_TICKET_LIST_LIMIT

    if not args:
        return scope, limit

    first = (args[0] or "").strip()
    if first.isdigit():
        return scope, max(1, min(int(first), MAX_ADMIN_TICKET_LIST_LIMIT))

    scope = normalize_ticket_list_scope(first)
    if scope is None:
        return None, None

    if len(args) == 2:
        second = (args[1] or "").strip()
        if not second.isdigit():
            return None, None
        limit = max(1, min(int(second), MAX_ADMIN_TICKET_LIST_LIMIT))

    return scope, limit


def select_ticket_list_submissions(submissions: list[dict], scope: str) -> list[dict]:
    if scope == "queue":
        selected = [
            submission
            for submission in submissions
            if classify_queue_state(submission) in {"awaiting_private", "awaiting_public"}
        ]
        return sorted(selected, key=queue_priority_key)

    if scope == "all":
        return sorted(submissions, key=recent_activity_sort_key, reverse=True)

    selected = [
        submission
        for submission in submissions
        if classify_queue_state(submission) == scope
    ]
    if scope in {"awaiting_private", "awaiting_public"}:
        return sorted(selected, key=queue_priority_key)
    return sorted(selected, key=recent_activity_sort_key, reverse=True)


def build_ticket_lookup_message(record: dict) -> str:
    ticket_id = int(record.get("id", 0))
    latest_activity = format_age_short(latest_activity_value(record))
    latest_activity_text = "unknown" if latest_activity == "unknown" else f"{latest_activity} ago"
    response_count = len(record.get("responses", []))
    queue_state = admin_queue_state_label(classify_queue_state(record))

    return (
        "Ticket details\n"
        f"Ticket: #{ticket_id}\n"
        f"Queue state: {queue_state}\n"
        f"Responses: {response_count}\n"
        f"{build_todo_summary_line(record)}\n"
        f"Latest activity: {latest_activity_text}\n\n"
        f"{build_admin_ticket_detail_message(record)}\n\n"
        f"{build_ticket_todos_section(record)}\n\n"
        f"{build_ticket_notes_section(record, MAX_TICKET_NOTES_PREVIEW)}"
    )


def build_ticket_list_message(submissions: list[dict], scope: str, limit: int) -> tuple[str, list[dict]]:
    if not submissions:
        return "No requests have been submitted yet.", []

    selected = select_ticket_list_submissions(submissions, scope)
    scope_label = admin_queue_state_label(scope)
    if not selected:
        return f"Ticket list: {scope_label}\n\nNo tickets match that filter right now.", []

    shown = selected[:limit]
    lines = [
        f"Ticket list: {scope_label}",
        "",
        f"Showing {len(shown)} of {len(selected)}",
        "",
    ]

    for submission in shown:
        request = normalize_payload(submission.get("request", {}))
        quality = assess_request_quality(request)
        state = classify_queue_state(submission)
        latest_activity = format_age_short(latest_activity_value(submission))
        latest_activity_text = "unknown" if latest_activity == "unknown" else f"last {latest_activity}"
        lines.append(
            f"#{submission['id']} | {admin_queue_state_short_label(state)} | {quality['grade']} | "
            f"{short_request_kind_label(request.get('request_kind', 'mentorship'))} | {request['urgency']} | "
            f"{trim_text(request['track'], 16)} | "
            f"{trim_text(request['question'], 56)} | {latest_activity_text} | {count_open_ticket_todos(submission)} tasks"
        )

    lines.extend(
        [
            "",
            "Fast lookup",
            "/ticket <ticket>",
            "/tickets",
            "/tickets waiting_user 20",
            "/tickets ended 20",
            "/todos <ticket>",
        ]
    )
    return "\n".join(lines), shown


def build_ticket_list_markup(submissions: list[dict]) -> InlineKeyboardMarkup | None:
    buttons = [
        build_copy_button(f"#{int(submission.get('id', 0))}", f"/ticket {int(submission.get('id', 0))}")
        for submission in submissions[:12]
    ]
    if not buttons:
        return None
    return InlineKeyboardMarkup(chunk_items(buttons, 4))


def queue_priority_key(submission: dict) -> tuple[int, int, datetime, int]:
    request = normalize_payload(submission.get("request", {}))
    urgency_rank = {"High": 0, "Normal": 1, "Low": 2}.get(request.get("urgency", "Normal"), 1)
    quality = assess_request_quality(request)
    created_at = parse_iso_datetime(submission.get("created_at")) or datetime.max.replace(tzinfo=timezone.utc)
    return urgency_rank, -int(quality["score"]), created_at, int(submission.get("id", 0))


def build_dashboard_message(submissions: list[dict]) -> str:
    availability_text, _ = expand_saved_tags(MENTOR_AVAILABILITY_TEXT)
    if not submissions:
        return (
            "Admin Dashboard\n\n"
            "No tickets yet.\n\n"
            f"Response windows\n{availability_text}"
        )

    waiting_private: list[dict] = []
    waiting_public: list[dict] = []
    waiting_user: list[dict] = []
    ended = 0
    high_priority = 0
    answer_ready = 0
    admin_todos_open = 0
    user_todos_open = 0
    due_admin_reminders = 0
    due_user_reminders = 0

    for submission in submissions:
        state = classify_queue_state(submission)
        request = normalize_payload(submission.get("request", {}))
        quality = assess_request_quality(request)
        admin_todos_open += count_open_ticket_todos(submission, "admin")
        user_todos_open += count_open_ticket_todos(submission, "user")
        due_admin_reminders += due_ticket_todo_count(submission, "admin")
        due_user_reminders += due_ticket_todo_count(submission, "user")
        if state == "awaiting_private":
            waiting_private.append(submission)
            if request.get("urgency") == "High":
                high_priority += 1
            if int(quality["score"]) >= 80:
                answer_ready += 1
        elif state == "awaiting_public":
            waiting_public.append(submission)
            if request.get("urgency") == "High":
                high_priority += 1
            if int(quality["score"]) >= 80:
                answer_ready += 1
        elif state == "waiting_user":
            waiting_user.append(submission)
        elif state == "done_closed":
            ended += 1

    waiting_on_you = sorted(waiting_private + waiting_public, key=queue_priority_key)
    preview_lines = []
    for submission in waiting_on_you[:6]:
        request = normalize_payload(submission.get("request", {}))
        quality = assess_request_quality(request)
        preview_lines.append(
            f"#{submission['id']} | {quality['grade']} | {answer_mode_policy_short(request.get('answer_mode', 'private'))} | "
            f"{short_request_kind_label(request.get('request_kind', 'mentorship'))} | {request['urgency']} | "
            f"{trim_text(request['track'], 18)} | "
            f"{trim_text(request['question'], 52)} | {format_age_short(submission.get('created_at'))}"
        )

    preview_text = "\n".join(preview_lines) if preview_lines else "No tickets currently waiting on you."

    return (
        "Admin Dashboard\n\n"
        f"Total tickets: {len(submissions)}\n"
        f"Waiting on you: {len(waiting_on_you)}\n"
        f"Private queue: {len(waiting_private)}\n"
        f"Public queue: {len(waiting_public)}\n"
        f"Waiting on user: {len(waiting_user)}\n"
        f"Ended tickets: {ended}\n"
        f"High priority waiting: {high_priority}\n\n"
        f"Answer-ready now: {answer_ready}\n\n"
        f"Admin checklist open: {admin_todos_open}\n"
        f"User checklist open: {user_todos_open}\n"
        f"Due reminders now: {due_admin_reminders + due_user_reminders}\n\n"
        f"Response windows\n{availability_text}\n\n"
        f"Next tickets\n{preview_text}\n\n"
        "Fast actions\n"
        "/ticket <ticket>\n"
        "/tickets queue 20\n"
        "/tickets waiting_user 20\n"
        "/todos <ticket>\n"
        "/todo <ticket> user <task>\n"
        "/templates\n"
        "/tags\n"
        "/quickreply <ticket> queue\n"
        "/quickreply <ticket> need_context\n"
        "/quickreply <ticket> queue show"
        + ("\n/sendmeeting <ticket>" if booking_enabled() else "")
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
            "Saved tags like {{website}} and ticket-aware tags like {{meeting_link}} are expanded before sending.",
            "Use the copy buttons below when you are replying to a ticket message.",
        ]
    )
    return "\n".join(lines)


def build_templates_markup() -> InlineKeyboardMarkup:
    buttons = [
        build_copy_button(key, f"/quickreply {key}") for key in FAST_REPLY_TEMPLATES
    ]
    return InlineKeyboardMarkup(chunk_items(buttons, 2))


def build_public_notice(ticket_id: int, link: str, mode: str | None = None) -> str:
    link = normalize_https_url(link)
    posted_at = build_public_posted_at_text(mode, link)
    lines = [f"Update for ticket #{ticket_id}", f"A public answer is now available in {posted_at}."]
    if link:
        lines.append("Use the button below to open it.")
    lines.extend(["", "Use the buttons below if you want to continue this ticket, book a meeting, or close it."])
    return append_user_cta("\n".join(lines), ticket_id)


def build_public_answer_message(ticket_id: int, answer_text: str, link: str, mode: str | None = None) -> str:
    link = normalize_https_url(link)
    posted_at = build_public_posted_at_text(mode, link)
    lines = [f"Update for ticket #{ticket_id}", "", f"A public answer is now available in {posted_at}."]
    if answer_text:
        lines.extend(["", answer_text])
    if link:
        lines.extend(["", "Use the button below to open the published version."])
    lines.extend(["", "Use the buttons below if you want to continue this ticket, book a meeting, or close it."])
    return append_user_cta("\n".join(lines), ticket_id)


def build_public_answer_markup(ticket_id: int, submission: dict, link: str) -> InlineKeyboardMarkup | None:
    return build_user_ticket_markup(submission, link, force_continue=True)


def build_ticket_actions_markup(record: dict) -> InlineKeyboardMarkup:
    request = normalize_payload(record.get("request", {}))
    ticket_id = int(record.get("id", 0))
    buttons = [
        build_copy_button("Details", f"/ticket {ticket_id}"),
        build_copy_button("Reply", f"/reply {ticket_id} "),
        build_copy_button("Status", f"/status {ticket_id}"),
        build_copy_button("Notes", f"/notes {ticket_id}"),
        build_copy_button("Checklist", f"/todos {ticket_id}"),
    ]

    suggested_template = suggest_quick_reply_template(request)
    if suggested_template:
        buttons.append(build_copy_button("Quick reply", f"/quickreply {ticket_id} {suggested_template}"))
    else:
        buttons.append(build_copy_button("Queue reply", f"/quickreply {ticket_id} queue"))
        buttons.append(build_copy_button("Need context", f"/quickreply {ticket_id} need_context"))

    if allows_public_reply(request.get("answer_mode", "private")):
        buttons.append(build_copy_button("Public reply", f"/replypublic {ticket_id} "))
        buttons.append(build_copy_button("Mark public", f"/markpublic {ticket_id} https://"))

    if booking_enabled():
        buttons.append(build_copy_button("Meeting", f"/sendmeeting {ticket_id}"))

    buttons.append(build_copy_button("Add note", f"/note {ticket_id} "))
    buttons.append(build_copy_button("Todo for user", f"/todo {ticket_id} user "))
    buttons.append(build_copy_button("Todo for admin", f"/todo {ticket_id} admin "))
    buttons.append(build_copy_button("End ticket", f"/endticket {ticket_id}"))

    return InlineKeyboardMarkup(chunk_items(buttons, 2))


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
        "request_kind": normalize_request_kind(payload.get("request_kind", "")),
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
        "notes": [],
        "todos": [],
        "responses": [],
    }


def build_admin_ticket_detail_message(record: dict) -> str:
    user = record.get("user", {})
    request = normalize_payload(record.get("request", {}))
    ticket_id = record.get("id", "Unknown")
    contact_visibility = normalize_contact_visibility(request.get("contact_visibility", "shown"))
    public_actions_allowed = allows_public_reply(request.get("answer_mode", "private"))

    if contact_visibility == "hidden":
        contact_lines = (
            "Admin-visible details\n"
            "Private\n"
            "The bot still keeps the delivery route privately so replies can be sent."
        )
    else:
        username = f"@{user['username']}" if user.get("username") else "Not provided"
        contact_lines = (
            "Admin-visible details\n"
            f"Name: {user.get('display_name', 'Unknown user')}\n"
            f"Username: {username}\n"
            f"Telegram ID: {user.get('id', 'Unknown')}"
        )

    suggested_template = suggest_quick_reply_template(request)
    action_text = "Use the copy buttons below for the common ticket actions."
    if suggested_template:
        action_text += f"\nSuggested quick reply: /quickreply {ticket_id} {suggested_template}"
    if not public_actions_allowed:
        action_text += "\nPublic answer is blocked for this ticket."

    lines = [
        f"Request Ticket #{ticket_id}",
        "",
        f"Submitted: {record.get('display_time', 'Unknown')}",
        f"Source: {format_source(record.get('source', 'guided_flow'))}",
        f"Status: {format_status(record.get('status', 'open'))}",
        "",
        "Core request",
        f"Question:\n{request['question']}",
    ]
    if request["goal"] != "Not provided":
        lines.extend(["", f"Goal:\n{request['goal']}"])
    if request["challenge"] != "Not provided":
        lines.extend(["", f"Blocker:\n{request['challenge']}"])
    if request["context"] != "No extra context":
        lines.extend(["", f"Context:\n{request['context']}"])

    detail_lines = [f"Requested reply mode: {format_answer_mode(request['answer_mode'])}", f"Details in admin view: {format_contact_visibility(request['contact_visibility'])}"]
    if request["request_kind"] not in {"mentorship", "other"}:
        detail_lines.insert(0, f"Request type: {format_request_kind(request['request_kind'])}")
    if request["track"] not in {"General", "General / custom"}:
        detail_lines.append(f"Topic: {request['track']}")
    if request["level"] != "Not provided":
        detail_lines.append(f"Stage: {request['level']}")
    if request["urgency"] != "Normal":
        detail_lines.append(f"Urgency: {request['urgency']}")

    lines.extend(
        [
            "",
            build_fast_read_section(request, ticket_id),
            "",
            "Request details",
            *detail_lines,
            "",
            "Reply policy",
            answer_mode_policy_text(request["answer_mode"]),
            "",
            contact_lines,
            "",
            "Public preview",
            record.get("public_request", build_public_prompt(request)),
            "",
            "Private bot thread",
            "Reply to this message to answer privately or continue the private conversation through the bot.",
            "",
            action_text,
        ]
    )
    return "\n".join(lines)


def format_submission(record: dict) -> str:
    request = normalize_payload(record.get("request", {}))
    ticket_id = int(record.get("id", 0))
    lines = [
        f"Ticket #{ticket_id}",
        f"Status: {format_status(record.get('status', 'open'))}",
        f"Reply: {format_answer_mode(request.get('answer_mode', 'private'))}",
    ]
    if request.get("request_kind", "mentorship") not in {"mentorship", "other"}:
        lines.insert(2, f"Type: {format_request_kind(request.get('request_kind', 'other'))}")
    if request.get("urgency", "Normal") != "Normal":
        lines.append(f"Urgency: {request['urgency']}")
    lines.extend(
        [
            "",
            "Question",
            request.get("question", "Not provided"),
            "",
            "Use the Details button below for the full request.",
        ]
    )
    return "\n".join(lines)


def format_discussion_ticket(record: dict) -> str:
    request = normalize_payload(record.get("request", {}))
    public_request = record.get("public_request") or build_public_prompt(request)

    return (
        f"Anonymous Request Ticket #{record['id']}\n\n"
        f"Request type: {format_request_kind(request['request_kind'])}\n"
        f"Topic: {request['track']}\n"
        f"Stage: {request['level']}\n"
        f"Urgency: {request['urgency']}\n\n"
        f"{public_request}\n\n"
        "Reply here with the public answer.\n"
        "The ticket stays active until the mentor ends it."
    )


def build_summary(payload: dict) -> str:
    request = normalize_payload(payload)
    lines = ["Before you send", "", "Question", request["question"]]

    if request["context"] != "No extra context":
        lines.extend(["", "Extra details", request["context"]])
    if request["goal"] != "Not provided":
        lines.extend(["", "Goal", request["goal"]])
    if request["challenge"] != "Not provided":
        lines.extend(["", "Blocker", request["challenge"]])

    meta_lines = [f"Reply: {format_answer_mode(request['answer_mode'])}", f"Details: {format_contact_visibility(request['contact_visibility'])}"]
    if request["request_kind"] not in {"mentorship", "other"}:
        meta_lines.insert(0, f"Type: {format_request_kind(request['request_kind'])}")
    if request["urgency"] != "Normal":
        meta_lines.append(f"Urgency: {request['urgency']}")
    if request["track"] not in {"General", "General / custom"}:
        meta_lines.append(f"Topic: {request['track']}")
    if request["level"] != "Not provided":
        meta_lines.append(f"Stage: {request['level']}")

    lines.extend(["", *meta_lines])
    lines.extend(["", "Use Submit to send, Restart to edit, or Cancel to stop."])
    return "\n".join(lines)


def build_user_status_markup(record: dict) -> InlineKeyboardMarkup | None:
    return build_user_ticket_markup(record)


def build_user_status(record: dict) -> str:
    request = normalize_payload(record.get("request", {}))
    ticket_id = int(record.get("id", 0))
    lines = [
        f"Ticket #{ticket_id}",
        f"Status: {format_status(record.get('status', 'open'))}",
        f"Submitted: {record.get('display_time', 'Unknown')}",
        f"Reply: {format_answer_mode(request.get('answer_mode', 'private'))}",
    ]

    if request.get("request_kind", "mentorship") not in {"mentorship", "other"}:
        lines.insert(3, f"Type: {format_request_kind(request.get('request_kind', 'mentorship'))}")
    lines.extend(["", "Question", request.get("question", "Not provided")])

    public_response = latest_public_response(record)
    if public_response is not None:
        public_link = normalize_https_url(public_response.get("link", ""))
        lines.extend(
            [
                "",
                f"A public answer is available in {build_public_posted_at_text(public_response.get('mode'), public_link)}.",
            ]
        )
        if public_link:
            lines.append("Use the button below to open it.")
    elif record.get("status") == "answered_public":
        lines.extend(["", f"A public answer was posted in {build_public_posted_at_text(None, '')}."])

    discussion = record.get("discussion", {})
    if discussion.get("message_id") and record.get("status") == "open" and not ticket_has_public_answer(record):
        lines.extend(["", "Your anonymous public request is queued in the discussion group."])
    user_todos_section = build_user_todos_section(record)
    if user_todos_section:
        lines.extend(["", user_todos_section])
    if ticket_is_ended(record):
        lines.extend(["", "This ticket is closed."])
    elif user_followup_available(record):
        lines.extend(["", "Use the buttons below to continue this ticket, send a file, book a meeting, or close it."])

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


def build_user_followup_prompt(ticket_id: int, submission: dict) -> str:
    lines = [
        f"Continue ticket #{ticket_id}",
        "",
        "Send your next message now.",
        "You can type normally or attach a file.",
    ]
    if private_thread_enabled(submission):
        lines.append("If you prefer, you can also reply to the earlier ticket thread.")
    return "\n".join(lines)


async def relay_user_message_to_admin(
    context: ContextTypes.DEFAULT_TYPE,
    submission: dict,
    ticket_id: int,
    source_message,
    reply_to_message_id: int | None,
    mode: str,
) -> tuple[bool, str, int | None]:
    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is None:
        return False, "The mentor is not configured yet. Please try again later.", None

    prefix = "Private follow-up" if mode == "private_thread" else "Follow-up"
    reply_markup = build_ticket_actions_markup(submission)
    try:
        if message_has_attachment(source_message):
            copy_kwargs = {
                "chat_id": admin_id,
                "from_chat_id": source_message.chat_id,
                "message_id": source_message.message_id,
                "reply_to_message_id": reply_to_message_id,
                "reply_markup": reply_markup,
            }
            if message_supports_caption(source_message):
                copy_kwargs["caption"] = build_attachment_caption(
                    f"{prefix} for ticket #{ticket_id}",
                    message_body_text(source_message),
                )
            sent_message = await context.bot.copy_message(**copy_kwargs)
            return True, "", sent_message.message_id

        sent_message = await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"{prefix} for ticket #{ticket_id}\n\n"
                f"{message_content_summary(source_message)}\n\n"
                "Reply to this message to answer through the bot."
            ),
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
            link_preview_options=NO_PREVIEW,
        )
    except TelegramError:
        logger.exception("Failed to relay user update for ticket %s", ticket_id)
        return False, "I could not send your update right now. Please try again in a moment.", None

    return True, "", sent_message.message_id


async def copy_private_ticket_message_to_user(
    context: ContextTypes.DEFAULT_TYPE,
    submission: dict,
    ticket_id: int,
    source_message,
    admin_message_id: int | None,
    reply_markup: InlineKeyboardMarkup | None = None,
    caption_text: str | None = None,
) -> tuple[bool, str]:
    if ticket_is_ended(submission):
        return False, ended_ticket_message(ticket_id)

    user_id = submission.get("user", {}).get("id")
    if user_id is None:
        return False, "I could not find the Telegram user for this ticket."

    merged_markup = merge_inline_markups(reply_markup, build_user_ticket_markup(submission, force_continue=True))
    reply_target_message_id = get_latest_private_thread_message_id(submission, "user")
    body = caption_text if caption_text is not None else message_body_text(source_message)
    try:
        copy_kwargs = {
            "chat_id": user_id,
            "from_chat_id": source_message.chat_id,
            "message_id": source_message.message_id,
            "reply_to_message_id": reply_target_message_id,
            "reply_markup": merged_markup,
        }
        if message_supports_caption(source_message):
            copy_kwargs["caption"] = build_attachment_caption(
                f"Reply for ticket #{ticket_id}",
                body,
            )
        sent_message = await context.bot.copy_message(**copy_kwargs)
    except TelegramError:
        logger.exception("Failed to copy private ticket message")
        return False, f"I could not deliver the private message for ticket #{ticket_id}."

    append_response(
        ticket_id,
        "answered_private",
        {
            "mode": "private_thread",
            "direction": "mentor_to_user",
            "text": clean_text(body, message_content_summary(source_message)),
            "admin_message_id": admin_message_id,
            "user_message_id": sent_message.message_id,
        },
    )
    return True, ""


async def send_private_ticket_message(
    context: ContextTypes.DEFAULT_TYPE,
    submission: dict,
    ticket_id: int,
    message_text: str,
    admin_message_id: int | None,
    direction: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> tuple[bool, str]:
    if ticket_is_ended(submission):
        return False, ended_ticket_message(ticket_id)

    user_id = submission.get("user", {}).get("id")
    if user_id is None:
        return False, "I could not find the Telegram user for this ticket."

    request = normalize_payload(submission.get("request", {}))
    if allows_public_reply(request.get("answer_mode", "private")) and not private_thread_enabled(submission):
        message_text = (
            f"{message_text}\n\n"
            "You can reply here, attach a file, or use Continue ticket below if you want to keep going."
        )
    if direction == "mentor_to_user":
        prior_mentor_replies = [
            response
            for response in submission.get("responses", [])
            if response.get("direction") == "mentor_to_user"
        ]
        if not prior_mentor_replies:
            message_text = append_user_cta(message_text, ticket_id, submission)
        reply_markup = merge_inline_markups(reply_markup, build_user_ticket_markup(submission, force_continue=True))

    reply_target_message_id = get_latest_private_thread_message_id(submission, "user")
    try:
        sent_message = await context.bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_to_message_id=reply_target_message_id,
            reply_markup=reply_markup,
            link_preview_options=NO_PREVIEW,
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


def build_user_todo_update_message(ticket_id: int, submission: dict, todo: dict, reason: str) -> str:
    title = "Checklist update" if reason == "created" else "Checklist reminder"
    lines = [
        f"{title} for ticket #{ticket_id}",
        "",
        format_todo_line(todo, include_owner=False),
    ]

    user_todos = open_ticket_todos(submission, "user")
    if user_todos:
        lines.extend(["", "Current open checklist"])
        for item in user_todos:
            lines.append(format_todo_line(item, include_owner=False))

    lines.append("")
    if user_followup_available(submission):
        lines.append("Use the buttons below when you have an update.")
    else:
        lines.append(f"Use /status {ticket_id} any time to review this checklist.")
    return "\n".join(lines)


async def notify_user_todo_update(
    context: ContextTypes.DEFAULT_TYPE,
    submission: dict,
    ticket_id: int,
    todo: dict,
    reason: str,
) -> None:
    user_id = submission.get("user", {}).get("id")
    if user_id is None:
        return

    reply_target = get_latest_private_thread_message_id(submission, "user") if private_thread_enabled(submission) else None
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=build_user_todo_update_message(ticket_id, submission, todo, reason),
            reply_to_message_id=reply_target,
            reply_markup=build_user_ticket_markup(submission),
            link_preview_options=NO_PREVIEW,
        )
    except TelegramError:
        logger.exception("Failed to notify user about checklist update for ticket %s", ticket_id)


async def send_due_todo_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_id = context.application.bot_data.get("admin_id")
    now = datetime.now(timezone.utc)

    for submission in read_submissions():
        ticket_id = int(submission.get("id", 0))
        for todo in due_ticket_todos(submission, now):
            target_chat_id = admin_id if todo.get("owner") == "admin" else submission.get("user", {}).get("id")
            if target_chat_id is None:
                continue

            reply_target = None
            if todo.get("owner") == "admin":
                reply_target = get_latest_private_thread_message_id(submission, "admin")
            elif private_thread_enabled(submission):
                reply_target = get_latest_private_thread_message_id(submission, "user")

            try:
                await context.bot.send_message(
                    chat_id=target_chat_id,
                    text=build_todo_reminder_message(ticket_id, submission, todo, todo.get("owner", "user")),
                    reply_to_message_id=reply_target,
                    reply_markup=build_user_ticket_markup(submission) if todo.get("owner") == "user" else None,
                    link_preview_options=NO_PREVIEW,
                )
            except TelegramError:
                logger.exception("Failed to send checklist reminder for ticket %s todo %s", ticket_id, todo.get("id"))
                continue

            mark_ticket_todo_reminder_sent(ticket_id, int(todo.get("id", 0)), now.isoformat())


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


def resolve_admin_ticket_target(
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
    if submission is not None and thread_context is not None and thread_context.get("side") == "admin":
        return int(submission["id"]), submission, 0

    if is_discussion_group(context, update.effective_chat.id):
        _, _, submission = find_submission_by_discussion_message(
            update.effective_chat.id,
            replied_message.message_id,
        )
        if submission is not None:
            return int(submission["id"]), submission, 0

    return None, None, 0


def resolve_user_ticket_target(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[int | None, dict | None]:
    if update.message is None or update.effective_user is None:
        return None, None

    if context.args:
        ticket_id = parse_ticket_id(context.args[0])
        if ticket_id is not None:
            _, _, submission = find_submission(ticket_id)
            if submission is not None and submission.get("user", {}).get("id") == update.effective_user.id:
                return ticket_id, submission

    replied_message = getattr(update.message, "reply_to_message", None)
    if replied_message is None or update.effective_chat is None:
        return None, None

    _, _, submission, thread_context = find_submission_by_private_message(
        update.effective_chat.id,
        replied_message.message_id,
    )
    if submission is None or thread_context is None or thread_context.get("side") != "user":
        return None, None
    if submission.get("user", {}).get("id") != update.effective_user.id:
        return None, None

    return int(submission["id"]), submission


def add_ticket_note(ticket_id: int, text: str) -> tuple[dict | None, dict | None]:
    note_text = clean_text(text, "")
    if not note_text:
        return None, None

    created_note: dict | None = None

    def mutate(submission: dict, updated_at: str) -> bool:
        nonlocal created_note
        notes = ticket_notes(submission)
        note_record = {
            "id": next_ticket_item_id(notes),
            "text": note_text,
            "created_at": updated_at,
            "author": "admin",
        }
        notes.append(note_record)
        submission["notes"] = notes
        created_note = note_record
        return True

    submission = mutate_submission(ticket_id, mutate)
    return submission, created_note


def add_ticket_todo(ticket_id: int, owner: str, text: str) -> tuple[dict | None, dict | None]:
    todo_text = clean_text(text, "")
    if not todo_text:
        return None, None

    created_todo: dict | None = None

    def mutate(submission: dict, updated_at: str) -> bool:
        nonlocal created_todo
        todos = ticket_todos(submission)
        todo_record = {
            "id": next_ticket_item_id(todos),
            "owner": owner,
            "text": todo_text,
            "status": "open",
            "created_at": updated_at,
            "updated_at": updated_at,
            "done_at": "",
            "remind_at": "",
            "reminder_sent_at": "",
        }
        todos.append(todo_record)
        submission["todos"] = todos
        created_todo = todo_record
        return True

    submission = mutate_submission(ticket_id, mutate)
    return submission, created_todo


def set_ticket_todo_status(ticket_id: int, todo_id: int, done: bool) -> tuple[dict | None, dict | None]:
    updated_todo: dict | None = None

    def mutate(submission: dict, updated_at: str) -> bool:
        nonlocal updated_todo
        todos = ticket_todos(submission)
        changed = False
        for todo in todos:
            if int(todo.get("id", 0)) != todo_id:
                continue
            todo["status"] = "done" if done else "open"
            todo["updated_at"] = updated_at
            todo["done_at"] = updated_at if done else ""
            todo["reminder_sent_at"] = ""
            updated_todo = dict(todo)
            changed = True
            break
        if changed:
            submission["todos"] = todos
        return changed

    submission = mutate_submission(ticket_id, mutate)
    return submission, updated_todo


def set_ticket_todo_reminder(ticket_id: int, todo_id: int, remind_at: str) -> tuple[dict | None, dict | None]:
    updated_todo: dict | None = None

    def mutate(submission: dict, updated_at: str) -> bool:
        nonlocal updated_todo
        todos = ticket_todos(submission)
        changed = False
        for todo in todos:
            if int(todo.get("id", 0)) != todo_id:
                continue
            todo["remind_at"] = remind_at
            todo["reminder_sent_at"] = ""
            todo["updated_at"] = updated_at
            updated_todo = dict(todo)
            changed = True
            break
        if changed:
            submission["todos"] = todos
        return changed

    submission = mutate_submission(ticket_id, mutate)
    return submission, updated_todo


def mark_ticket_todo_reminder_sent(ticket_id: int, todo_id: int, sent_at: str) -> dict | None:
    def mutate(submission: dict, updated_at: str) -> bool:
        todos = ticket_todos(submission)
        changed = False
        for todo in todos:
            if int(todo.get("id", 0)) != todo_id:
                continue
            if todo.get("status") == "done":
                break
            todo["reminder_sent_at"] = sent_at
            todo["updated_at"] = updated_at
            changed = True
            break
        if changed:
            submission["todos"] = todos
        return changed

    return mutate_submission(ticket_id, mutate)


async def post_public_answer(
    context: ContextTypes.DEFAULT_TYPE,
    submission: dict,
    answer_text: str,
) -> tuple[str, str, int | None, int | None]:
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
        return (
            "public_discussion",
            getattr(sent_message, "link", "") or "",
            getattr(sent_message, "chat_id", None),
            getattr(sent_message, "message_id", None),
        )

    if public_channel_id is not None:
        sent_message = await context.bot.send_message(
            chat_id=public_channel_id,
            text=message_text,
        )
        return (
            "public_channel",
            getattr(sent_message, "link", "") or "",
            getattr(sent_message, "chat_id", None),
            getattr(sent_message, "message_id", None),
        )

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
        admin_ticket_message = await context.bot.send_message(
            chat_id=admin_id,
            text=format_submission(record),
            reply_markup=build_ticket_actions_markup(record),
            link_preview_options=NO_PREVIEW,
        )
    except TelegramError:
        logger.exception("Failed to forward request")
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
        append_user_cta(
            (
                f"Request sent\n"
                f"Ticket: #{record['id']}\n"
                + (
                    f"Type: {format_request_kind(record['request']['request_kind'])}\n"
                    if record["request"].get("request_kind") not in {"mentorship", "other"}
                    else ""
                )
                + f"Reply: {format_answer_mode(record['request']['answer_mode'])}"
                f"{public_note}"
            ),
            record["id"],
            record,
        ),
        reply_markup=build_keyboard(MAIN_MENU),
        link_preview_options=NO_PREVIEW,
    )
    record["private_thread"] = {
        "admin_chat_id": admin_id,
        "admin_root_message_id": admin_ticket_message.message_id,
        "user_chat_id": update.effective_user.id,
        "user_root_message_id": user_confirmation_message.message_id,
    }
    save_submission(record)
    return True


async def notify_user_public_answer(
    context: ContextTypes.DEFAULT_TYPE,
    submission: dict,
    notice_text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    source_chat_id: int | None = None,
    source_message_id: int | None = None,
) -> tuple[bool, str]:
    user_id = submission.get("user", {}).get("id")
    ticket_id = int(submission.get("id", 0))
    if user_id is None:
        return False, f"I could not notify the user about the public answer for ticket #{ticket_id}."

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=notice_text,
            reply_markup=reply_markup,
            link_preview_options=NO_PREVIEW,
        )
    except TelegramError:
        logger.exception("Failed to notify the user about the public answer")
        return False, f"I could not notify the user about the public answer for ticket #{ticket_id}."

    if source_chat_id is not None and source_message_id is not None:
        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
                reply_markup=reply_markup,
            )
        except TelegramError:
            logger.exception("Failed to copy the public answer to the user")

    return True, ""


async def remember_private_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat is None or update.effective_chat.type != "private":
        return
    if update.effective_user is None:
        return
    remember_known_user(update.effective_user)


async def mute_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if not feature_channel_updates_enabled():
        await update.message.reply_text(
            "Channel updates are not active here right now.",
            reply_markup=build_keyboard(MAIN_MENU),
        )
        return

    remember_known_user(update.effective_user, updates_enabled=False)
    channel_url = cta_channel_url() or build_public_destination_text()
    await update.message.reply_text(
        "Channel updates are paused.\n"
        f"You can still follow the channel here: {channel_url}\n"
        "Use /resumeupdates whenever you want them back.",
        reply_markup=build_keyboard(MAIN_MENU),
        link_preview_options=NO_PREVIEW,
    )


async def resume_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if not feature_channel_updates_enabled():
        await update.message.reply_text(
            "Channel updates are not active here right now.",
            reply_markup=build_keyboard(MAIN_MENU),
        )
        return

    remember_known_user(update.effective_user, updates_enabled=True)
    await update.message.reply_text(
        "Channel updates are active again.\n"
        "New channel posts can be mirrored here when available.",
        reply_markup=build_keyboard(MAIN_MENU),
        link_preview_options=NO_PREVIEW,
    )


async def broadcast_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return

    public_channel_id = context.application.bot_data.get("public_channel_id")
    if public_channel_id is None or chat.id != public_channel_id:
        return
    if should_skip_channel_broadcast(message):
        return
    if not (getattr(message, "text", None) or getattr(message, "caption", None) or getattr(message, "effective_attachment", None)):
        return

    admin_id = context.application.bot_data.get("admin_id")
    targets = collect_broadcast_targets(admin_id)
    if not targets:
        return

    delivered = 0
    skipped_members = 0
    failed = 0

    for user_id in targets:
        try:
            member = await context.bot.get_chat_member(chat_id=public_channel_id, user_id=user_id)
            if member.status in {"creator", "administrator", "member", "restricted"}:
                skipped_members += 1
                continue
        except TelegramError:
            pass

        try:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=chat.id,
                message_id=message.message_id,
            )
            delivered += 1
        except Forbidden:
            set_user_updates_preference(user_id, False)
            failed += 1
        except TelegramError:
            failed += 1

    logger.info(
        "Broadcasted channel post %s to %s bot users, skipped %s channel members, failed %s deliveries",
        message.message_id,
        delivered,
        skipped_members,
        failed,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if context.application.bot_data.get("admin_id") is None:
        await update.message.reply_text(
            "This request bot is almost ready.\n"
            "If you are the owner, send /claimadmin once from your Telegram account.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text(
            build_dashboard_message(read_submissions()),
            reply_markup=build_keyboard(ADMIN_MENU),
            link_preview_options=NO_PREVIEW,
        )
        return

    await reply_with_optional_logo(
        update.message,
        build_user_start_message(),
        build_keyboard(MAIN_MENU),
        parse_mode="HTML",
    )
    start_brand_markup = build_start_brand_markup()
    if start_brand_markup is not None:
        await update.message.reply_text(
            build_start_brand_message(),
            reply_markup=start_brand_markup,
            parse_mode="HTML",
            link_preview_options=NO_PREVIEW,
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text(
            build_admin_help_message(),
            reply_markup=build_admin_help_markup(),
            parse_mode="HTML",
            link_preview_options=NO_PREVIEW,
        )
        return

    await update.message.reply_text(
        build_user_help_message(),
        reply_markup=build_keyboard(MAIN_MENU),
        parse_mode="HTML",
        link_preview_options=NO_PREVIEW,
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
        "The request bot is ready to receive tickets.\n"
        "Use /setdiscussion and /setchannel from your private admin chat to connect the public destinations.\n"
        "Use /storagestatus to confirm queue persistence, /dashboard to watch the queue and follow-up load, /ticket and /tickets for lookup, /todo and /note for execution tracking, /templates for fast replies, /tags for saved shortcuts, and /meetingstatus to confirm Calendly booking.",
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


async def storage_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("This command is available only to the admin.")
        return

    await update.message.reply_text(
        build_storage_status_message(),
        reply_markup=build_keyboard(ADMIN_MENU),
        link_preview_options=NO_PREVIEW,
    )


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
        await update.message.reply_text("No requests have been submitted yet.")
        return

    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=7)
    recent_count = 0
    track_counter: Counter[str] = Counter()
    request_kind_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    answer_mode_counter: Counter[str] = Counter()

    for submission in submissions:
        request = normalize_payload(submission.get("request", {}))
        track = request.get("track", "Unknown")
        track_counter[track] += 1
        request_kind_counter[format_request_kind(request.get("request_kind", "mentorship"))] += 1
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
    request_type_lines = "\n".join(
        f"- {request_kind}: {count}" for request_kind, count in request_kind_counter.most_common()
    )

    await update.message.reply_text(
        f"Total requests: {len(submissions)}\n"
        f"Last 7 days: {recent_count}\n\n"
        f"Open: {status_counter.get('open', 0)}\n"
        f"Answered privately: {status_counter.get('answered_private', 0)}\n"
        f"Answered publicly: {status_counter.get('answered_public', 0)}\n\n"
        f"Private reply preference: {answer_mode_counter.get('private', 0)}\n"
        f"Public answer preference: {answer_mode_counter.get('public', 0)}\n\n"
        f"Request types:\n{request_type_lines}\n\n"
        f"Top topics:\n{top_tracks}",
        link_preview_options=NO_PREVIEW,
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
        link_preview_options=NO_PREVIEW,
    )


async def ticket_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, _ = resolve_admin_ticket_target(update, context)
    if ticket_id is None:
        await update.message.reply_text(
            "Usage: /ticket <ticket_number>\n"
            "You can also reply to an admin-side ticket message with /ticket."
        )
        return
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    await update.message.reply_text(
        build_ticket_lookup_message(submission),
        reply_markup=build_ticket_actions_markup(submission),
        link_preview_options=NO_PREVIEW,
    )


async def tickets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    scope, limit = parse_ticket_list_args(context.args)
    if scope is None or limit is None:
        await update.message.reply_text(build_ticket_list_usage())
        return

    message_text, shown = build_ticket_list_message(read_submissions(), scope, limit)
    await update.message.reply_text(
        message_text,
        reply_markup=build_ticket_list_markup(shown),
        link_preview_options=NO_PREVIEW,
    )


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, args_offset = resolve_admin_ticket_target(update, context)
    if ticket_id is None:
        await update.message.reply_text(build_notes_usage())
        return
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    note_text = " ".join(context.args[args_offset:]).strip()
    if not note_text:
        await update.message.reply_text(build_notes_usage())
        return

    extra_tags = build_ticket_tags(ticket_id, submission)
    note_text, missing_tags = expand_saved_tags(note_text, extra_tags)
    if missing_tags:
        await update.message.reply_text(
            build_unknown_tags_message(missing_tags),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    updated_submission, created_note = add_ticket_note(ticket_id, note_text)
    if updated_submission is None or created_note is None:
        await update.message.reply_text("I could not save that note.")
        return

    await update.message.reply_text(
        f"Saved note #{created_note['id']} for ticket #{ticket_id}.\n\n{build_ticket_notes_section(updated_submission, MAX_TICKET_NOTES_PREVIEW)}",
        reply_markup=build_ticket_actions_markup(updated_submission),
        link_preview_options=NO_PREVIEW,
    )


async def notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, _ = resolve_admin_ticket_target(update, context)
    if ticket_id is None:
        await update.message.reply_text("Usage: /notes <ticket_number>\nYou can also reply to an admin-side ticket message with /notes.")
        return
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    await update.message.reply_text(
        f"Ticket #{ticket_id}\n\n{build_ticket_notes_section(submission)}",
        reply_markup=build_ticket_actions_markup(submission),
        link_preview_options=NO_PREVIEW,
    )


async def todo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, args_offset = resolve_admin_ticket_target(update, context)
    if ticket_id is None:
        await update.message.reply_text(build_todo_usage())
        return
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    if len(context.args) <= args_offset:
        await update.message.reply_text(build_todo_usage())
        return

    owner = normalize_ticket_owner(context.args[args_offset])
    if owner is None:
        await update.message.reply_text(build_todo_usage())
        return

    todo_text = " ".join(context.args[args_offset + 1 :]).strip()
    if not todo_text:
        await update.message.reply_text(build_todo_usage())
        return

    if owner == "user" and ticket_is_ended(submission):
        await update.message.reply_text("User checklist items cannot be added after a ticket is ended.")
        return

    extra_tags = build_ticket_tags(ticket_id, submission)
    todo_text, missing_tags = expand_saved_tags(todo_text, extra_tags)
    if missing_tags:
        await update.message.reply_text(
            build_unknown_tags_message(missing_tags),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    updated_submission, created_todo = add_ticket_todo(ticket_id, owner, todo_text)
    if updated_submission is None or created_todo is None:
        await update.message.reply_text("I could not save that checklist item.")
        return

    if owner == "user" and not ticket_is_ended(updated_submission):
        await notify_user_todo_update(context, updated_submission, ticket_id, created_todo, "created")

    await update.message.reply_text(
        f"Added checklist item #{created_todo['id']} for ticket #{ticket_id}.\n"
        f"Owner: {todo_owner_label(owner)}\n"
        f"{build_todo_summary_line(updated_submission)}\n\n"
        f"{build_ticket_todos_section(updated_submission)}",
        reply_markup=build_ticket_actions_markup(updated_submission),
        link_preview_options=NO_PREVIEW,
    )


async def todos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, _ = resolve_admin_ticket_target(update, context)
    if ticket_id is None:
        await update.message.reply_text("Usage: /todos <ticket_number>\nYou can also reply to an admin-side ticket message with /todos.")
        return
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    await update.message.reply_text(
        f"Ticket #{ticket_id}\n\n{build_ticket_todos_section(submission)}",
        reply_markup=build_ticket_actions_markup(submission),
        link_preview_options=NO_PREVIEW,
    )


async def tododone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, args_offset = resolve_admin_ticket_target(update, context)
    if ticket_id is None or len(context.args) <= args_offset:
        await update.message.reply_text(
            "Usage: /tododone <ticket_number> <todo_id>\n"
            "Or reply to an admin-side ticket message with /tododone <todo_id>."
        )
        return
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    todo_id = parse_numeric_id(context.args[args_offset])
    if todo_id is None:
        await update.message.reply_text("Checklist item IDs must be numeric.")
        return

    existing_todo = find_ticket_todo(submission, todo_id)
    if existing_todo is None:
        await update.message.reply_text(f"Checklist item #{todo_id} was not found on ticket #{ticket_id}.")
        return
    if existing_todo.get("status") == "done":
        await update.message.reply_text(f"Checklist item #{todo_id} is already done.")
        return

    updated_submission, updated_todo = set_ticket_todo_status(ticket_id, todo_id, done=True)
    if updated_submission is None or updated_todo is None:
        await update.message.reply_text("I could not update that checklist item.")
        return

    await update.message.reply_text(
        f"Checklist item #{todo_id} marked done for ticket #{ticket_id}.\n\n{build_ticket_todos_section(updated_submission)}",
        reply_markup=build_ticket_actions_markup(updated_submission),
        link_preview_options=NO_PREVIEW,
    )


async def todoundo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, args_offset = resolve_admin_ticket_target(update, context)
    if ticket_id is None or len(context.args) <= args_offset:
        await update.message.reply_text(
            "Usage: /todoundo <ticket_number> <todo_id>\n"
            "Or reply to an admin-side ticket message with /todoundo <todo_id>."
        )
        return
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    todo_id = parse_numeric_id(context.args[args_offset])
    if todo_id is None:
        await update.message.reply_text("Checklist item IDs must be numeric.")
        return

    existing_todo = find_ticket_todo(submission, todo_id)
    if existing_todo is None:
        await update.message.reply_text(f"Checklist item #{todo_id} was not found on ticket #{ticket_id}.")
        return
    if existing_todo.get("status") != "done":
        await update.message.reply_text(f"Checklist item #{todo_id} is already open.")
        return

    updated_submission, updated_todo = set_ticket_todo_status(ticket_id, todo_id, done=False)
    if updated_submission is None or updated_todo is None:
        await update.message.reply_text("I could not reopen that checklist item.")
        return

    await update.message.reply_text(
        f"Checklist item #{todo_id} reopened for ticket #{ticket_id}.\n\n{build_ticket_todos_section(updated_submission)}",
        reply_markup=build_ticket_actions_markup(updated_submission),
        link_preview_options=NO_PREVIEW,
    )


async def todoremind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, args_offset = resolve_admin_ticket_target(update, context)
    if ticket_id is None or len(context.args) <= args_offset + 1:
        await update.message.reply_text(build_todo_reminder_usage())
        return
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    todo_id = parse_numeric_id(context.args[args_offset])
    if todo_id is None:
        await update.message.reply_text("Checklist item IDs must be numeric.")
        return

    reminder_value = context.args[args_offset + 1].strip().lower()
    existing_todo = find_ticket_todo(submission, todo_id)
    if existing_todo is None:
        await update.message.reply_text(f"Checklist item #{todo_id} was not found on ticket #{ticket_id}.")
        return
    if existing_todo.get("status") == "done":
        await update.message.reply_text("Reminders can only be set on open checklist items.")
        return

    remind_at = ""
    if reminder_value != "off":
        offset = parse_reminder_offset(reminder_value)
        if offset is None:
            await update.message.reply_text(build_todo_reminder_usage())
            return
        remind_at = (datetime.now(timezone.utc) + offset).isoformat()

    updated_submission, updated_todo = set_ticket_todo_reminder(ticket_id, todo_id, remind_at)
    if updated_submission is None or updated_todo is None:
        await update.message.reply_text("I could not update that reminder.")
        return

    reminder_text = "Reminder cleared." if not remind_at else f"Reminder set for {format_display_datetime(remind_at)}."
    await update.message.reply_text(
        f"Ticket #{ticket_id} checklist item #{todo_id}\n{reminder_text}\n\n{build_ticket_todos_section(updated_submission)}",
        reply_markup=build_ticket_actions_markup(updated_submission),
        link_preview_options=NO_PREVIEW,
    )


async def templates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("This command is available only to the admin.")
        return

    await update.message.reply_text(
        build_templates_message(),
        reply_markup=build_templates_markup(),
        link_preview_options=NO_PREVIEW,
    )


async def availability_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    admin_view = is_admin(context, update.effective_user.id if update.effective_user else None)
    reply_markup = build_keyboard(ADMIN_MENU) if admin_view else build_keyboard(MAIN_MENU)
    message_text = build_availability_message()
    if not admin_view:
        message_text = append_user_cta(message_text)
    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        link_preview_options=NO_PREVIEW,
    )


async def tags_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    if not is_admin(context, update.effective_user.id if update.effective_user else None):
        await update.message.reply_text("This command is available only to the admin.")
        return

    await update.message.reply_text(
        build_tags_message(),
        reply_markup=build_tags_markup(),
        link_preview_options=NO_PREVIEW,
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


def clear_pending_followup(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("followup_ticket_id", None)
    context.user_data.pop("followup_prompt_message_id", None)


def set_pending_followup(context: ContextTypes.DEFAULT_TYPE, ticket_id: int, prompt_message_id: int | None = None) -> None:
    context.user_data["followup_ticket_id"] = ticket_id
    if prompt_message_id is None:
        context.user_data.pop("followup_prompt_message_id", None)
    else:
        context.user_data["followup_prompt_message_id"] = prompt_message_id


def pending_followup_ticket_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    return parse_numeric_id(str(context.user_data.get("followup_ticket_id", "")).strip())


def is_pending_followup_prompt_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    message = update.message
    prompt_message_id = parse_numeric_id(str(context.user_data.get("followup_prompt_message_id", "")).strip())
    if message is None or message.reply_to_message is None or prompt_message_id is None:
        return False
    return message.reply_to_message.message_id == prompt_message_id


async def submit_pending_followup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if update.message is None or update.effective_user is None:
        return False

    ticket_id = pending_followup_ticket_id(context)
    if ticket_id is None:
        return False

    _, _, submission = find_submission(ticket_id)
    if submission is None:
        clear_pending_followup(context)
        await update.message.reply_text(
            "That ticket could not be found anymore.",
            reply_markup=build_keyboard(MAIN_MENU),
        )
        return True

    if submission.get("user", {}).get("id") != update.effective_user.id:
        clear_pending_followup(context)
        await update.message.reply_text("You can only continue your own tickets.")
        return True

    if ticket_is_ended(submission):
        clear_pending_followup(context)
        await update.message.reply_text(ended_ticket_message(ticket_id))
        return True

    mode = "private_thread" if private_thread_enabled(submission) else "public_followup"
    sent, error_message, admin_message_id = await relay_user_message_to_admin(
        context,
        submission,
        ticket_id,
        update.message,
        get_latest_private_thread_message_id(submission, "admin"),
        mode,
    )
    if not sent:
        await update.message.reply_text(error_message)
        return True

    updated_submission = append_response(
        ticket_id,
        "open",
        {
            "mode": mode,
            "direction": "user_to_mentor",
            "text": message_content_summary(update.message),
            "admin_message_id": admin_message_id,
            "user_message_id": update.message.message_id,
        },
    )
    clear_pending_followup(context)
    await update.message.reply_text(
        append_user_cta(
            f"Your update for ticket #{ticket_id} has been sent.",
            ticket_id,
            updated_submission or submission,
        ),
        reply_markup=build_user_ticket_markup(updated_submission or submission),
        link_preview_options=NO_PREVIEW,
    )
    return True


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
    clear_pending_followup(context)
    context.user_data["intake_mode"] = "guided"
    context.user_data["request"] = {
        "request_kind": "mentorship",
        "track": "General / custom",
        "level": "Not provided",
        "goal": "Not provided",
        "challenge": "Not provided",
        "question": "Not provided",
        "context": "No extra context",
        "urgency": "Normal",
    }
    await update.message.reply_text(
        step_text(
            1,
            intake_total_steps("guided"),
            "What would you like help with?",
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    return QUESTION


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
    clear_pending_followup(context)
    context.user_data["intake_mode"] = "quick"
    await update.message.reply_text(
        step_text(
            1,
            intake_total_steps("quick"),
            "Send your mentorship question in one message.\nOne clear question works best.",
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

    if pending_followup_ticket_id(context) is not None:
        await submit_pending_followup(update, context)
        return ConversationHandler.END

    reset_request(context)
    context.user_data["intake_mode"] = "quick"
    context.user_data["request"] = {
        "request_kind": "mentorship",
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
            intake_total_steps("quick"),
            "How should the answer be delivered?\nPrivate keeps it inside the bot. Public hides your identity.",
        ),
        reply_markup=build_keyboard(ANSWER_MODE_MENU),
    )
    return ANSWER_MODE


async def capture_request_kind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return REQUEST_KIND

    request_kind = (update.message.text or "").strip()
    if request_kind not in REQUEST_KIND_CHOICES:
        await update.message.reply_text(
            "Choose the request type that fits best.",
            reply_markup=build_keyboard(REQUEST_KIND_MENU),
        )
        return REQUEST_KIND

    normalized_kind = normalize_request_kind(request_kind)
    context.user_data["request"]["request_kind"] = normalized_kind
    intake_mode = context.user_data.get("intake_mode", "guided")
    if intake_mode == "quick":
        await update.message.reply_text(
            step_text(
                3,
                intake_total_steps("quick"),
                "How should the answer be delivered?\nPrivate keeps it inside the bot. Public hides your identity.",
            ),
            reply_markup=build_keyboard(ANSWER_MODE_MENU),
        )
        return ANSWER_MODE

    await update.message.reply_text(
        step_text(
            4,
            intake_total_steps("guided"),
            "How urgent is this?",
        ),
        reply_markup=build_keyboard(URGENCY_MENU),
    )
    return URGENCY


async def capture_track(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return TRACK

    track = (update.message.text or "").strip()
    if not track:
        await update.message.reply_text(
            "Please write a short topic for this request.",
        )
        return TRACK

    context.user_data["request"]["track"] = track
    await update.message.reply_text(
        step_text(
            3,
            intake_total_steps("guided"),
            "What stage are you at right now?\nA short answer is enough.",
        ),
        reply_markup=ReplyKeyboardRemove(),
    )
    return LEVEL


async def capture_level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message is None:
        return LEVEL

    level = (update.message.text or "").strip()
    if not level:
        await update.message.reply_text(
            "Please share your current stage.",
        )
        return LEVEL

    context.user_data["request"]["level"] = level
    await update.message.reply_text(
        step_text(
            4,
            intake_total_steps("guided"),
            "What outcome do you want from this?\nKeep it concrete.",
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
            5,
            intake_total_steps("guided"),
            "What is the main blocker right now?",
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
            6,
            intake_total_steps("guided"),
            "What is your main question?\nOne direct question works best.",
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
            2,
            intake_total_steps("guided"),
            "Add any helpful detail.\nYou can include context, goal, blocker, stage, or deadline.\nIf not, send Skip.",
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
            3,
            intake_total_steps("guided"),
            "How should the answer be delivered?\nPrivate keeps it in the bot. Public hides your identity.",
        ),
        reply_markup=build_keyboard(ANSWER_MODE_MENU),
    )
    return ANSWER_MODE


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
            5,
            intake_total_steps("guided"),
            "How should the answer be delivered?\nPrivate keeps it in the bot. Public hides your identity.",
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
    total_steps = intake_total_steps(context.user_data.get("intake_mode", "guided"))
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
        "request_kind": "mentorship",
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
            intake_total_steps("quick"),
            "How should the answer be delivered?\nPrivate keeps it inside the bot. Public hides your identity.",
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
    clear_pending_followup(context)
    if update.message is not None:
        await update.message.reply_text(
            "Your current request was cancelled.",
            reply_markup=build_keyboard(MAIN_MENU),
        )
    return ConversationHandler.END


async def handle_pending_followup_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_chat is None:
        return
    if update.effective_chat.type != "private" or update.message.reply_to_message is not None:
        return
    await submit_pending_followup(update, context)


async def user_end_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    ticket_id, submission = resolve_user_ticket_target(update, context)
    if ticket_id is None or submission is None:
        await update.message.reply_text(
            "Usage: /done <ticket_number>\nYou can also reply to one of your ticket messages with /done."
        )
        return

    updated_submission, error_message = await close_ticket_for_user(
        context,
        submission,
        ticket_id,
        update.message.message_id,
    )
    if error_message:
        await update.message.reply_text(error_message)
        return

    clear_pending_followup(context)
    await update.message.reply_text(
        append_user_cta(
            f"Ticket #{ticket_id} is now closed.\nStart a new question any time if you need more help.",
            ticket_id,
            updated_submission or submission,
        ),
        reply_markup=build_user_ticket_markup(updated_submission or submission),
        link_preview_options=NO_PREVIEW,
    )


async def handle_user_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or update.effective_user is None:
        return

    data = query.data or ""
    ticket_id: int | None = None
    action = ""
    if data.startswith(USER_CONTINUE_CALLBACK_PREFIX):
        ticket_id = parse_ticket_id(data.removeprefix(USER_CONTINUE_CALLBACK_PREFIX))
        action = "continue"
    elif data.startswith(USER_CLOSE_CALLBACK_PREFIX):
        ticket_id = parse_ticket_id(data.removeprefix(USER_CLOSE_CALLBACK_PREFIX))
        action = "close"

    if ticket_id is None:
        await query.answer()
        return

    _, _, submission = find_submission(ticket_id)
    if submission is None:
        clear_pending_followup(context)
        await query.answer("Ticket not found.", show_alert=True)
        return

    if submission.get("user", {}).get("id") != update.effective_user.id:
        await query.answer("This action is only available on your own tickets.", show_alert=True)
        return

    if action == "continue":
        if ticket_is_ended(submission):
            clear_pending_followup(context)
            await query.answer("This ticket is already closed.", show_alert=True)
            return

        prompt_message = None
        if query.message is not None:
            prompt_message = await query.message.reply_text(
                build_user_followup_prompt(ticket_id, submission),
                reply_markup=build_user_ticket_markup(submission),
                link_preview_options=NO_PREVIEW,
            )
        set_pending_followup(context, ticket_id, prompt_message.message_id if prompt_message is not None else None)
        await query.answer("Send your next message now.")
        return

    updated_submission, error_message = await close_ticket_for_user(
        context,
        submission,
        ticket_id,
        query.message.message_id if query.message is not None else None,
    )
    if error_message:
        await query.answer(error_message, show_alert=True)
        return

    clear_pending_followup(context)
    await query.answer("Ticket closed.")
    if query.message is not None:
        try:
            await query.edit_message_reply_markup(
                reply_markup=build_user_ticket_markup(updated_submission or submission)
            )
        except TelegramError:
            logger.exception("Failed to refresh closed ticket markup for ticket %s", ticket_id)
        await query.message.reply_text(
            append_user_cta(
                f"Ticket #{ticket_id} is now closed.\nStart a new question any time if you need more help.",
                ticket_id,
                updated_submission or submission,
            ),
            reply_markup=build_user_ticket_markup(updated_submission or submission),
            link_preview_options=NO_PREVIEW,
        )


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

    message_text = build_user_status(submission)
    if is_ticket_owner:
        message_text = append_user_cta(message_text, ticket_id, submission)
    await update.message.reply_text(
        message_text,
        reply_markup=build_user_status_markup(submission),
        link_preview_options=NO_PREVIEW,
    )


async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    admin_view = is_admin(context, update.effective_user.id if update.effective_user else None)
    link = cta_services_url()
    if not link:
        await update.message.reply_text(
            build_services_message(admin_view),
            reply_markup=build_keyboard(ADMIN_MENU if admin_view else MAIN_MENU),
            link_preview_options=NO_PREVIEW,
        )
        return

    await update.message.reply_text(
        build_services_message(admin_view),
        reply_markup=build_services_markup(link),
        link_preview_options=NO_PREVIEW,
    )


async def contact_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    admin_view = is_admin(context, update.effective_user.id if update.effective_user else None)
    reply_markup = build_contact_markup()
    if reply_markup is None:
        reply_markup = build_keyboard(ADMIN_MENU if admin_view else MAIN_MENU)
    await update.message.reply_text(
        build_contact_message(admin_view),
        reply_markup=reply_markup,
        link_preview_options=NO_PREVIEW,
    )


async def website_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    admin_view = is_admin(context, update.effective_user.id if update.effective_user else None)
    reply_markup = build_website_markup()
    if reply_markup is None:
        reply_markup = build_keyboard(ADMIN_MENU if admin_view else MAIN_MENU)
    await update.message.reply_text(
        build_website_message(admin_view),
        reply_markup=reply_markup,
        link_preview_options=NO_PREVIEW,
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return

    admin_view = is_admin(context, update.effective_user.id if update.effective_user else None)
    reply_markup = build_profile_markup()
    if reply_markup is None:
        reply_markup = build_keyboard(ADMIN_MENU if admin_view else MAIN_MENU)
    await update.message.reply_text(
        build_profile_message(admin_view),
        reply_markup=reply_markup,
        link_preview_options=NO_PREVIEW,
    )


async def meeting_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    admin_view = is_admin(context, update.effective_user.id)
    if not booking_enabled():
        await update.message.reply_text(
            build_meeting_message(admin_view=admin_view),
            reply_markup=build_keyboard(ADMIN_MENU if admin_view else MAIN_MENU),
            link_preview_options=NO_PREVIEW,
        )
        return

    ticket_id: int | None = None
    submission: dict | None = None
    if context.args:
        ticket_id = parse_ticket_id(context.args[0])
        if ticket_id is None:
            await update.message.reply_text("Usage: /meeting [ticket_number]")
            return
        _, _, submission = find_submission(ticket_id)
        if submission is None:
            await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
            return
        if not admin_view and submission.get("user", {}).get("id") != update.effective_user.id:
            await update.message.reply_text("You can only open booking links for your own tickets.")
            return

    await update.message.reply_text(
        build_meeting_message(ticket_id, submission, admin_view),
        reply_markup=build_meeting_markup(build_meeting_link(ticket_id, submission), ticket_id, admin_view),
        link_preview_options=NO_PREVIEW,
    )


async def meeting_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    base_url = calendly_url()
    await update.message.reply_text(
        build_meeting_status_message(),
        reply_markup=build_meeting_markup(base_url, admin=True),
        link_preview_options=NO_PREVIEW,
    )


async def send_meeting_invite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    if not booking_enabled():
        await update.message.reply_text(
            "Calendly booking is not configured yet.\n"
            "Set CALENDLY_URL or TAG_BOOKING first."
        )
        return

    ticket_id, submission, args_offset = resolve_admin_ticket_target(update, context)
    if ticket_id is None or submission is None:
        await update.message.reply_text(
            "Usage: /sendmeeting <ticket_number> [optional note]\n"
            "You can also reply to an admin-side ticket message with /sendmeeting [optional note]."
        )
        return
    if ticket_is_ended(submission):
        await update.message.reply_text(ended_ticket_message(ticket_id))
        return

    extra_tags = build_ticket_tags(ticket_id, submission)
    meeting_note = " ".join(context.args[args_offset:]).strip()
    if meeting_note:
        meeting_note, missing_tags = expand_saved_tags(meeting_note, extra_tags)
        if missing_tags:
            await update.message.reply_text(
                build_unknown_tags_message(missing_tags),
                reply_markup=build_keyboard(ADMIN_MENU),
            )
            return

    meeting_link = extra_tags.get("meeting_link", "")
    lines = [f"Meeting for ticket #{ticket_id}", "", CALENDLY_TEXT]
    if meeting_note:
        lines.extend(["", meeting_note])
    lines.extend(["", f"If the booking form has notes, mention ticket #{ticket_id}."])
    message_text = apply_identity_signature("\n".join(lines), default_identity_visibility())

    sent, error_message = await send_private_ticket_message(
        context,
        submission,
        ticket_id,
        message_text,
        update.message.message_id,
        "mentor_to_user",
        build_meeting_markup(meeting_link, ticket_id),
    )
    if not sent:
        await update.message.reply_text(error_message)
        return

    await update.message.reply_text(
        f"Meeting invite sent for ticket #{ticket_id}.",
        reply_markup=build_keyboard(ADMIN_MENU),
    )


async def followup_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /followup <ticket_number> <message>")
        return

    ticket_id = parse_ticket_id(context.args[0])
    if ticket_id is None:
        await update.message.reply_text("Ticket numbers must be numeric.")
        return

    followup_text = " ".join(context.args[1:]).strip()
    if not followup_text:
        await update.message.reply_text("Please include the follow-up message after the ticket number.")
        return

    _, _, submission = find_submission(ticket_id)
    if submission is None:
        await update.message.reply_text(f"Ticket #{ticket_id} was not found.")
        return

    if submission.get("user", {}).get("id") != update.effective_user.id:
        await update.message.reply_text("You can only continue your own tickets.")
        return

    if ticket_is_ended(submission):
        await update.message.reply_text(ended_ticket_message(ticket_id))
        return

    request = normalize_payload(submission.get("request", {}))
    if not allows_public_reply(request.get("answer_mode", "private")):
        await update.message.reply_text(
            "This ticket already uses private replies in the bot.\n"
            "Reply to the private ticket thread instead."
        )
        return

    if private_thread_enabled(submission):
        await update.message.reply_text(
            "This ticket is currently continuing privately in the bot.\n"
            "Reply to the private ticket thread instead."
        )
        return

    if not ticket_has_public_answer(submission):
        await update.message.reply_text(
            f"Ticket #{ticket_id} has not received a public answer yet.\n"
            "Use /status to check it while it is still in queue."
        )
        return

    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is None:
        await update.message.reply_text("The mentor is not configured yet. Please try again later.")
        return

    admin_reply_target = get_latest_private_thread_message_id(submission, "admin")
    try:
        sent_message = await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"Public follow-up for ticket #{ticket_id}\n\n"
                f"{followup_text}\n\n"
                "Reply with /replypublic for another public answer, /reply for a private switch, or /endticket when finished."
            ),
            reply_to_message_id=admin_reply_target,
            reply_markup=build_ticket_actions_markup(submission),
            link_preview_options=NO_PREVIEW,
        )
    except TelegramError:
        logger.exception("Failed to relay user public follow-up")
        await update.message.reply_text(
            "I could not send your follow-up right now. Please try again in a moment."
        )
        return

    append_response(
        ticket_id,
        "open",
        {
            "mode": "public_followup",
            "direction": "user_to_mentor",
            "text": followup_text,
            "admin_message_id": sent_message.message_id,
            "user_message_id": update.message.message_id,
        },
    )
    await update.message.reply_text(
        append_user_cta(
            f"Your follow-up for ticket #{ticket_id} has been sent.\n"
            "You can use the buttons below if you want to continue, book a meeting, or close the ticket later.",
            ticket_id,
            submission,
        ),
        reply_markup=build_user_ticket_markup(submission),
        link_preview_options=NO_PREVIEW,
    )


async def close_ticket_for_user(
    context: ContextTypes.DEFAULT_TYPE,
    submission: dict,
    ticket_id: int,
    user_message_id: int | None = None,
) -> tuple[dict | None, str]:
    if ticket_is_ended(submission):
        return submission, ended_ticket_message(ticket_id)

    admin_message_id = None
    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is not None:
        try:
            sent_admin_message = await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"Ticket #{ticket_id} was closed by the user.\n"
                    "No further replies will be accepted on this ticket."
                ),
                reply_to_message_id=get_latest_private_thread_message_id(submission, "admin"),
                link_preview_options=NO_PREVIEW,
            )
            admin_message_id = sent_admin_message.message_id
        except TelegramError:
            logger.exception("Failed to notify admin about user-closed ticket")

    updated_submission = append_response(
        ticket_id,
        "ended",
        {
            "mode": "ticket_end_user",
            "direction": "user_to_mentor",
            "text": "Closed by user",
            "admin_message_id": admin_message_id,
            "user_message_id": user_message_id,
        },
    )
    if updated_submission is None:
        return None, f"Ticket #{ticket_id} was not found."
    return updated_submission, ""


async def end_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return

    if not is_admin(context, update.effective_user.id):
        await update.message.reply_text("This command is available only to the admin.")
        return

    ticket_id, submission, args_offset = resolve_admin_ticket_target(update, context)
    if ticket_id is None or submission is None:
        await update.message.reply_text(
            "Usage: /endticket <ticket_number> [optional closing note]\n"
            "You can also reply to an admin-side ticket message with /endticket [optional closing note]."
        )
        return

    if ticket_is_ended(submission):
        await update.message.reply_text(f"Ticket #{ticket_id} is already ended.")
        return

    closing_note = " ".join(context.args[args_offset:]).strip()
    if closing_note:
        extra_tags = build_ticket_tags(ticket_id, submission)
        closing_note, missing_tags = expand_saved_tags(
            closing_note,
            extra_tags,
        )
        if missing_tags:
            await update.message.reply_text(
                build_unknown_tags_message(missing_tags),
                reply_markup=build_keyboard(ADMIN_MENU),
            )
            return

    user_id = submission.get("user", {}).get("id")
    user_message_id = None
    notify_error = ""
    if user_id is not None:
        lines = [f"Ticket #{ticket_id} has been ended by the mentor."]
        if closing_note:
            lines.extend(["", closing_note])
        lines.extend(["", "Start a new ticket any time if you want help with a new or continued question."])
        try:
            sent_message = await context.bot.send_message(
                chat_id=user_id,
                text=append_user_cta("\n".join(lines), ticket_id, submission),
                link_preview_options=NO_PREVIEW,
            )
            user_message_id = sent_message.message_id
        except TelegramError:
            logger.exception("Failed to notify user about ended ticket")
            notify_error = " The ticket was ended, but I could not notify the user."

    append_response(
        ticket_id,
        "ended",
        {
            "mode": "ticket_end",
            "direction": "mentor_to_user",
            "text": closing_note,
            "admin_message_id": update.message.message_id,
            "user_message_id": user_message_id,
        },
    )
    await update.message.reply_text(
        f"Ticket #{ticket_id} ended.{notify_error}",
        reply_markup=build_keyboard(ADMIN_MENU),
    )


async def auto_end_ticket_by_inactivity(application: Application, ticket_id: int) -> bool:
    _, _, submission = find_submission(ticket_id)
    if submission is None:
        return False

    closing_note = stale_ticket_auto_end_note(submission)
    if not closing_note:
        return False

    user_id = submission.get("user", {}).get("id")
    user_message_id = None
    admin_message_id = None

    if user_id is not None:
        try:
            sent_message = await application.bot.send_message(
                chat_id=user_id,
                text=append_user_cta(
                    f"Ticket #{ticket_id} was ended automatically.\n\n"
                    f"{closing_note}\n\n"
                    "Start a new ticket any time if you want help with a new or continued question.",
                    ticket_id,
                    submission,
                ),
                link_preview_options=NO_PREVIEW,
            )
            user_message_id = sent_message.message_id
        except TelegramError:
            logger.exception("Failed to notify user about automatic ticket end")

    admin_id = application.bot_data.get("admin_id")
    admin_root_message_id = submission.get("private_thread", {}).get("admin_root_message_id")
    if admin_id is not None:
        try:
            sent_admin_message = await application.bot.send_message(
                chat_id=admin_id,
                text=f"Ticket #{ticket_id} ended automatically.\n{closing_note}",
                reply_to_message_id=admin_root_message_id,
                reply_markup=build_keyboard(ADMIN_MENU),
                link_preview_options=NO_PREVIEW,
            )
            admin_message_id = sent_admin_message.message_id
        except TelegramError:
            logger.exception("Failed to notify admin about automatic ticket end")

    append_response(
        ticket_id,
        "ended",
        {
            "mode": "ticket_end_auto",
            "direction": "system",
            "text": closing_note,
            "admin_message_id": admin_message_id,
            "user_message_id": user_message_id,
        },
    )
    logger.info("Ticket %s ended automatically due to inactivity", ticket_id)
    return True


async def sweep_stale_tickets(application: Application) -> None:
    for submission in read_submissions():
        await auto_end_ticket_by_inactivity(application, int(submission.get("id", 0)))


async def auto_end_stale_tickets(context: ContextTypes.DEFAULT_TYPE) -> None:
    await sweep_stale_tickets(context.application)


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
    if ticket_is_ended(submission):
        await update.message.reply_text(ended_ticket_message(ticket_id))
        return

    extra_tags = build_ticket_tags(ticket_id, submission)
    answer_text, missing_tags = expand_saved_tags(
        answer_text,
        extra_tags,
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
    if ticket_is_ended(submission):
        await update.message.reply_text(ended_ticket_message(ticket_id))
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
    extra_tags = build_ticket_tags(ticket_id, submission)
    reply_text, missing_tags = expand_saved_tags(
        reply_text,
        extra_tags,
    )
    if missing_tags:
        await update.message.reply_text(
            build_unknown_tags_message(missing_tags),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    reply_markup = None
    if template_key == "meeting_invite":
        reply_markup = build_meeting_markup(extra_tags.get("meeting_link", ""), ticket_id)

    sent, error_message = await send_private_ticket_message(
        context,
        submission,
        ticket_id,
        f"Private answer for ticket #{ticket_id}\n\n{reply_text}",
        update.message.message_id,
        "mentor_to_user",
        reply_markup,
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

    if not (message_body_text(update.message) or message_has_attachment(update.message)):
        return

    if is_pending_followup_prompt_reply(update, context):
        await submit_pending_followup(update, context)
        return

    reply_text = message_body_text(update.message)

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
    if ticket_is_ended(submission):
        await update.message.reply_text(ended_ticket_message(ticket_id))
        return

    if thread_context["side"] == "admin":
        caption_text = reply_text
        if caption_text:
            extra_tags = build_ticket_tags(ticket_id, submission)
            caption_text, missing_tags = expand_saved_tags(
                caption_text,
                extra_tags,
            )
            if missing_tags:
                await update.message.reply_text(
                    build_unknown_tags_message(missing_tags),
                    reply_markup=build_keyboard(ADMIN_MENU),
                )
                return

        if message_has_attachment(update.message):
            sent, error_message = await copy_private_ticket_message_to_user(
                context,
                submission,
                ticket_id,
                update.message,
                update.message.message_id,
                caption_text=caption_text,
            )
            if not sent:
                await update.message.reply_text(error_message)
            return

        sent, error_message = await send_private_ticket_message(
            context,
            submission,
            ticket_id,
            f"Private reply for ticket #{ticket_id}\n\n{caption_text}",
            update.message.message_id,
            "mentor_to_user",
        )
        if not sent:
            await update.message.reply_text(error_message)
        return

    admin_id = context.application.bot_data.get("admin_id")
    if admin_id is None or submission.get("user", {}).get("id") != update.effective_user.id:
        return

    sent, error_message, admin_message_id = await relay_user_message_to_admin(
        context,
        submission,
        ticket_id,
        update.message,
        thread_context.get("remote_reply_to_message_id"),
        "private_thread",
    )
    if not sent:
        await update.message.reply_text(error_message)
        return

    updated_submission = append_response(
        ticket_id,
        "open",
        {
            "mode": "private_thread",
            "direction": "user_to_mentor",
            "text": message_content_summary(update.message),
            "admin_message_id": admin_message_id,
            "user_message_id": update.message.message_id,
        },
    )
    if pending_followup_ticket_id(context) == ticket_id:
        clear_pending_followup(context)
    await update.message.reply_text(
        append_user_cta(
            f"Your update for ticket #{ticket_id} has been sent.",
            ticket_id,
            updated_submission or submission,
        ),
        reply_markup=build_user_ticket_markup(updated_submission or submission),
        link_preview_options=NO_PREVIEW,
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
    if ticket_is_ended(submission):
        await update.message.reply_text(ended_ticket_message(ticket_id))
        return

    request = normalize_payload(submission.get("request", {}))
    if not allows_public_reply(request.get("answer_mode", "private")):
        await update.message.reply_text(
            public_reply_block_message(ticket_id),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    extra_tags = build_ticket_tags(ticket_id, submission)
    answer_text, missing_tags = expand_saved_tags(
        answer_text,
        extra_tags,
    )
    if missing_tags:
        await update.message.reply_text(
            build_unknown_tags_message(missing_tags),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    try:
        response_mode, public_link, public_chat_id, public_message_id = await post_public_answer(
            context,
            submission,
            answer_text,
        )
    except TelegramError:
        logger.exception("Failed to publish public answer")
        await update.message.reply_text(
            "I could not publish the public answer. Configure /setdiscussion or /setchannel, or use /markpublic with a manual link."
        )
        return
    public_link = normalize_https_url(public_link)

    user_id = submission.get("user", {}).get("id")
    notice_text = build_public_answer_message(ticket_id, answer_text, public_link, response_mode)
    notice_markup = build_public_answer_markup(ticket_id, submission, public_link)

    notified, error_message = await notify_user_public_answer(
        context,
        submission,
        notice_text,
        notice_markup,
        public_chat_id,
        public_message_id,
    )
    if not notified:
        await update.message.reply_text(
            error_message,
        )
        return

    append_response(
        ticket_id,
        "answered_public",
        {
            "mode": response_mode,
            "text": answer_text,
            "link": public_link,
            "public_chat_id": public_chat_id,
            "public_message_id": public_message_id,
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
    if ticket_is_ended(submission):
        await update.message.reply_text(ended_ticket_message(ticket_id))
        return

    request = normalize_payload(submission.get("request", {}))
    if not allows_public_reply(request.get("answer_mode", "private")):
        await update.message.reply_text(
            public_reply_block_message(ticket_id),
            reply_markup=build_keyboard(ADMIN_MENU),
        )
        return

    notice_text = build_public_notice(ticket_id, public_link, "public_manual")
    notice_markup = build_public_answer_markup(ticket_id, submission, public_link)

    notified, error_message = await notify_user_public_answer(
        context,
        submission,
        notice_text,
        notice_markup,
    )
    if not notified:
        await update.message.reply_text(
            error_message,
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
    if ticket_is_ended(submission):
        await update.message.reply_text(ended_ticket_message(ticket_id))
        return
    request = normalize_payload(submission.get("request", {}))
    if not allows_public_reply(request.get("answer_mode", "private")):
        await update.message.reply_text(public_reply_block_message(ticket_id))
        return

    public_link = getattr(update.message, "link", "") or ""
    public_link = normalize_https_url(public_link)
    notice_text = build_public_answer_message(ticket_id, answer_text, public_link, "public_discussion")
    notice_markup = build_public_answer_markup(ticket_id, submission, public_link)

    notified, error_message = await notify_user_public_answer(
        context,
        submission,
        notice_text,
        notice_markup,
        update.effective_chat.id,
        update.message.message_id,
    )
    if not notified:
        await update.message.reply_text(
            error_message,
        )
        return

    append_response(
        ticket_id,
        "answered_public",
        {
            "mode": "public_discussion",
            "text": answer_text,
            "link": public_link,
            "public_chat_id": update.effective_chat.id,
            "public_message_id": update.message.message_id,
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
    await sweep_stale_tickets(application)
    if application.job_queue is not None:
        application.job_queue.run_repeating(
            auto_end_stale_tickets,
            interval=3600,
            first=3600,
            name="auto_end_stale_tickets",
        )
        application.job_queue.run_repeating(
            send_due_todo_reminders,
            interval=TODO_REMINDER_SWEEP_SECONDS,
            first=TODO_REMINDER_SWEEP_SECONDS,
            name="send_due_todo_reminders",
        )


def main() -> None:
    if not TOKEN:
        raise RuntimeError(
            "TELEGRAM_TOKEN is missing. Set it in Railway Variables for deployment or in the local .env file."
        )

    validate_storage_configuration()
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    quick_question_pattern = rf"^{re.escape(QUICK_QUESTION_LABEL)}$"
    how_it_works_pattern = rf"^{re.escape(HOW_IT_WORKS_LABEL)}$"
    response_times_pattern = rf"^{re.escape(RESPONSE_TIMES_LABEL)}$"
    book_meeting_pattern = rf"^{re.escape(BOOK_MEETING_LABEL)}$"
    services_pattern = rf"^{re.escape(SERVICES_LABEL)}$"
    contact_pattern = rf"^{re.escape(CONTACT_LABEL)}$"
    website_pattern = rf"^{re.escape(WEBSITE_LABEL)}$"
    dashboard_pattern = rf"^{re.escape(DASHBOARD_LABEL)}$"
    templates_pattern = rf"^{re.escape(TEMPLATES_LABEL)}$"
    tags_pattern = rf"^{re.escape(TAGS_LABEL)}$"

    conversation = ConversationHandler(
        entry_points=[
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
                & ~filters.Regex(quick_question_pattern)
                & ~filters.Regex(response_times_pattern)
                & ~filters.Regex(book_meeting_pattern)
                & ~filters.Regex(services_pattern)
                & ~filters.Regex(contact_pattern)
                & ~filters.Regex(website_pattern)
                & ~filters.Regex(dashboard_pattern)
                & ~filters.Regex(templates_pattern)
                & ~filters.Regex(tags_pattern)
                & ~filters.Regex(how_it_works_pattern),
                start_quick_request,
            ),
        ],
        states={
            REQUEST_KIND: [MessageHandler(filters.TEXT & ~filters.COMMAND, capture_request_kind)],
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

    app.add_handler(MessageHandler(filters.ChatType.PRIVATE, remember_private_user), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("meeting", meeting_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("services", services_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("contact", contact_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("website", website_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("profile", profile_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("availability", availability_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("followup", followup_ticket, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("done", user_end_ticket, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("muteupdates", mute_updates, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("resumeupdates", resume_updates, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("claimadmin", claim_admin))
    app.add_handler(CommandHandler("adminstatus", admin_status))
    app.add_handler(CommandHandler("storagestatus", storage_status))
    app.add_handler(CommandHandler("dashboard", dashboard_command))
    app.add_handler(CommandHandler("ticket", ticket_command))
    app.add_handler(CommandHandler("tickets", tickets_command))
    app.add_handler(CommandHandler("note", note_command))
    app.add_handler(CommandHandler("notes", notes_command))
    app.add_handler(CommandHandler("todo", todo_command))
    app.add_handler(CommandHandler("todos", todos_command))
    app.add_handler(CommandHandler("tododone", tododone_command))
    app.add_handler(CommandHandler("todoundo", todoundo_command))
    app.add_handler(CommandHandler("todoremind", todoremind_command))
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
            filters.ChatType.PRIVATE & filters.ATTACHMENT & ~filters.REPLY & ~filters.COMMAND,
            handle_pending_followup_message,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.StatusUpdate.CHAT_SHARED,
            handle_chat_shared,
        )
    )
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, broadcast_channel_post))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("reply", reply_ticket))
    app.add_handler(CommandHandler("sendmeeting", send_meeting_invite))
    app.add_handler(CommandHandler("meetingstatus", meeting_status_command))
    app.add_handler(CommandHandler("quickreply", quick_reply_ticket))
    app.add_handler(CommandHandler("replypublic", reply_public_ticket))
    app.add_handler(CommandHandler("markpublic", mark_public))
    app.add_handler(CommandHandler("endticket", end_ticket))
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
        MessageHandler(filters.Regex(book_meeting_pattern) & ~filters.REPLY, meeting_command)
    )
    app.add_handler(
        MessageHandler(filters.Regex(services_pattern) & ~filters.REPLY, services_command)
    )
    app.add_handler(
        MessageHandler(filters.Regex(contact_pattern) & ~filters.REPLY, contact_command)
    )
    app.add_handler(
        MessageHandler(filters.Regex(website_pattern) & ~filters.REPLY, website_command)
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
        CallbackQueryHandler(handle_user_ticket_callback, pattern=r"^user:")
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.REPLY & (filters.TEXT | filters.ATTACHMENT) & ~filters.COMMAND,
            handle_private_thread_reply,
        )
    )
    app.add_handler(CommandHandler("cancel", cancel_request))

    logger.info("Mentorship bot is starting")
    app.run_polling(allowed_updates=["message", "channel_post", "callback_query"])


if __name__ == "__main__":
    main()
