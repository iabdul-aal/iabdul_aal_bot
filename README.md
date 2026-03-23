# telegram-mentorship-bot

Telegram mentorship bot with private intake, anonymous public answers, ticket tracking, and discussion or channel publishing.

## What it does

- Guided and quick question flows
- Private replies inside Telegram
- Anonymous public replies through a linked discussion group or channel
- Ticket tracking with `/status`
- Admin tools for private replies, public replies, and manual public marking

## Local run

1. Create or update `.env`.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the bot:

```bash
python bot.py
```

## Environment variables

```env
TELEGRAM_TOKEN=your_bot_token
ADMIN_ID=
MENTOR_LABEL=your mentor
PUBLIC_CHANNEL_URL=
DISCUSSION_GROUP_URL=
DISCUSSION_GROUP_ID=
PUBLIC_CHANNEL_ID=
DATA_DIR=./data
```

`ADMIN_ID` can stay empty at first. After the bot is running, open it in Telegram and send `/claimadmin` from the admin account.

If you use a linked discussion group for public answers, leave `DISCUSSION_GROUP_ID` empty and run `/setdiscussion` in your private admin chat with the bot, then choose the group from Telegram's picker.

If you use a channel for public answers, leave `PUBLIC_CHANNEL_ID` empty and run `/setchannel` in your private admin chat with the bot, then choose the channel from Telegram's picker.

The bot must be an admin in any discussion group or channel it should post to.
The configured admin account must also be an admin there so Telegram can offer that chat in the picker.

## Public and private behavior

- Private reply keeps the request and answer inside the bot.
- Public answer keeps the user identity private and publishes only a minimal anonymous version of the request.
- `/replypublic` lets the bot post the public answer directly to the linked discussion group or channel.
- `/markpublic` is still available if the public answer was posted manually somewhere else.

## Railway deployment

This project is prepared for Railway using the root `Dockerfile` and `railway.toml`.

Create a Railway volume and mount it to:

```text
/app/data
```

This keeps ticket history and admin state across restarts.

## Verification

Run:

```bash
python -m py_compile bot.py
```

## License

Creative Commons Attribution 4.0 International (`CC BY 4.0`).
