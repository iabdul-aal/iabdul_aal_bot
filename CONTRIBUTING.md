# Contributing

Thanks for contributing to `iabdul_aal_bot`.

## Project overview

This repository contains a Telegram mentorship bot for Islam I. Abdulaal. The bot supports:

- Private mentorship requests
- Public or private answer preference
- Ticket tracking
- Discussion-group support for public answers

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
PUBLIC_CHANNEL_URL=
DISCUSSION_GROUP_ID=
DATA_DIR=./data
```

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
- Test the bot flow after changing command handling, ticket logic, or discussion-group logic.

## Suggested test flow

1. Start the bot locally.
2. Send `/claimadmin` from the admin account.
3. Send `/setdiscussion` inside the linked discussion group if public discussion answers are used.
4. Submit a private mentorship ticket.
5. Submit a public mentorship ticket.
6. Test `/reply`, `/markpublic`, and `/status`.
7. If discussion-group support is enabled, reply to a mirrored public ticket in the discussion group and confirm the user is notified.

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

## Deployment notes

The repository is prepared for GitHub-based deployment to Railway.

- `Dockerfile` defines the runtime image
- `railway.toml` defines deployment settings
- Persistent bot data should be mounted at `/app/data`

## Security

- Rotate the bot token immediately if it is exposed.
- Never paste production secrets into issues or pull requests.
- Be careful when changing admin-only command handling.

## Questions

If a change affects ticket behavior, public-answer routing, or data storage, describe the expected user flow clearly in the pull request.
