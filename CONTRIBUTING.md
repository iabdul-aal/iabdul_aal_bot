# Contributing

Thanks for contributing to `telegram-mentorship-bot`.

## Project overview

This repository contains a Telegram mentorship bot with:

- Private mentorship requests
- Flexible topic and stage intake
- Optional hiding of Telegram contact details in mentor view
- Anonymous public answer support
- Ticket tracking
- Private-thread reply routing through the bot
- Admin dashboard and ready-reply templates
- Saved tags for reusable links and text shortcuts
- Discussion-group and channel publishing

## Before you start

Make sure you have:

- Python 3.12 or newer
- A Telegram bot token from BotFather
- Access to the target Telegram bot and admin account

## Local setup

1. Create a local `.env` file.
2. Add the required variables:

```env
TELEGRAM_TOKEN=your_bot_token
ADMIN_ID=
MENTOR_LABEL=your mentor
MENTOR_IDENTITY_TEXT=
MENTOR_IDENTITY_DEFAULT=hidden
MENTOR_AVAILABILITY_TEXT=Replies are handled in planned batches.
TAG_WEBSITE=
TAG_BOOKING=
PUBLIC_CHANNEL_URL=
DISCUSSION_GROUP_URL=
DISCUSSION_GROUP_ID=
PUBLIC_CHANNEL_ID=
DATA_DIR=./data
```

If `PUBLIC_CHANNEL_URL` or `DISCUSSION_GROUP_URL` are set, use public `https://...` links.

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the bot:

```bash
python bot.py
```

## Development guidelines

- Do not commit real secrets or tokens.
- Keep `.env` local only.
- Keep changes focused and easy to review.
- Preserve ticket history compatibility when editing stored submission data.
- Test the bot flow after changing command handling, ticket logic, or public-routing logic.

## Suggested test flow

1. Start the bot locally.
2. Send `/claimadmin` from the admin account.
3. Run `/setdiscussion` in the private admin chat and choose the linked discussion group if discussion replies are used.
4. Run `/setchannel` in the private admin chat and choose the public channel if channel replies are used.
5. Submit a private mentorship ticket.
6. Submit a public mentorship ticket.
7. Test `/dashboard`, `/templates`, `/tags`, `/quickreply`, `/reply`, `/replypublic`, `/markpublic`, and `/status`.
8. Reply to a private ticket from both sides and confirm the thread continues through bot replies.
9. Save a tag with `/savetag website https://your-site.example` and confirm `{{website}}` expands in admin replies.
10. If discussion support is enabled, reply to a mirrored public ticket in the discussion group and confirm the user is notified.

## Git workflow

1. Create a branch for your change.
2. Make your edits.
3. Run:

```bash
python -m py_compile bot.py
```

4. Commit with a clear message.
5. Open a pull request with:

- What changed
- Why it changed
- Any setup or testing notes

## Security

- Rotate the bot token immediately if it is exposed.
- Never paste production secrets into issues or pull requests.
- Be careful when changing admin-only command handling or public-answer routing.
