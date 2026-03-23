# telegram-mentorship-bot

Telegram mentorship bot for student-facing guidance with private intake, anonymous public answers, ticket tracking, flexible topics, and discussion or channel publishing.

## What it does

- Guided and quick question flows
- Flexible topic and stage capture with custom entries
- Private replies inside Telegram
- Optional hiding of Telegram contact details in the mentor view
- Anonymous public replies through a linked discussion group or channel
- Ticket tracking with `/status`
- Private tickets can continue through replies inside the bot
- Public tickets can continue with `/followup <ticket>` after a public answer until they are ended
- Channel posts can be mirrored to bot users who are not already in the public channel
- Admin dashboard, request grading, copy-ready templates/tags, identity controls, and public/private reply tools

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
MENTOR_IDENTITY_TEXT=
MENTOR_LOGO_URL=
MENTOR_IDENTITY_DEFAULT=hidden
REQUIRE_PERSISTENT_STORAGE=
MENTOR_AVAILABILITY_TEXT=Replies are handled in planned batches.
CTA_CHANNEL_URL=
CTA_WEBSITE_URL=
CTA_EXTRA_TEXT=
TAG_WEBSITE=
TAG_BOOKING=
PUBLIC_CHANNEL_URL=
DISCUSSION_GROUP_URL=
DISCUSSION_GROUP_ID=
PUBLIC_CHANNEL_ID=
DATA_DIR=./data
```

If you set `PUBLIC_CHANNEL_URL` or `DISCUSSION_GROUP_URL`, use the public `https://...` link form. The bot normalizes these to HTTPS.
`MENTOR_IDENTITY_TEXT`, `MENTOR_AVAILABILITY_TEXT`, and `CTA_EXTRA_TEXT` support `\n` for line breaks in `.env`.

`ADMIN_ID` can stay empty at first. After the bot is running, open it in Telegram and send `/claimadmin` from the admin account.

If you use a linked discussion group for public answers, leave `DISCUSSION_GROUP_ID` empty and run `/setdiscussion` in your private admin chat with the bot, then choose the group from Telegram's picker.

If you use a channel for public answers, leave `PUBLIC_CHANNEL_ID` empty and run `/setchannel` in your private admin chat with the bot, then choose the channel from Telegram's picker.

The bot must be an admin in any discussion group or channel it should post to.
The configured admin account must also be an admin there so Telegram can offer that chat in the picker.

On Railway, queue persistence requires a Railway Volume mounted to `/app/data` if you keep the default relative `./data` storage path.
The bot now refuses to start on Railway if persistent storage is required but no mounted volume is detected.
If you intentionally want disposable storage for a temporary environment, set `REQUIRE_PERSISTENT_STORAGE=false`.

## Public and private behavior

- Private reply keeps the request and answer inside the bot.
- If a user chooses private reply, the admin cannot switch that ticket to public later.
- For private tickets, both sides can continue the same conversation by replying in the bot thread.
- After the latest private mentor reply, a private ticket ends automatically after 1 day without a reply.
- The bot receives the user's Telegram display name, username, and routing ID to deliver replies.
- Before submission, the user can choose whether those Telegram details stay visible in the mentor view.
- Public answer keeps the user identity private and publishes only a minimal anonymous version of the request. The admin can still answer privately if that is more useful.
- After a public answer, the user can continue the same ticket with `/followup <ticket_number> <message>` until the mentor ends it.
- After the latest public answer, a public ticket ends automatically after 3 days without a follow-up.
- `/replypublic` lets the bot post the public answer directly to the linked discussion group or channel.
- When the bot knows the public message, the user also receives a copied version of that public post in the bot together with the direct message link.
- `/markpublic` is still available if the public answer was posted manually somewhere else, and manual links are normalized to HTTPS.
- If a public channel is configured, normal channel posts from that channel are mirrored to bot users who are not already members there.
- Users can stop or resume mirrored channel updates with `/muteupdates` and `/resumeupdates`.

## Admin workflow

- `/storagestatus` shows whether the queue is on persistent storage and how many tickets are currently on disk.
- `/dashboard` shows what is waiting on you, what is waiting on the user, and your current response-window message.
- New tickets include a fast-read section with the main ask, outcome, blocker, readiness grade, and the fastest suggested reply path.
- `/templates` lists concise ready replies for common situations.
- Ticket actions, template shortcuts, and tag placeholders use Telegram copy buttons for faster reuse.
- `/tags` lists reusable placeholders like `{{website}}`.
- `/savetag` and `/deletetag` let you manage saved shortcuts without redeploying.
- `/quickreply` sends a reusable private answer template and can optionally show or hide mentor identity.
- `/endticket` ends a ticket manually and stops future replies on that ticket.
- `MENTOR_IDENTITY_TEXT` lets you define the identity/signature text used when you choose to show it.
- `MENTOR_LOGO_URL` lets `/start` use a brand image when Telegram can fetch it.
- `MENTOR_AVAILABILITY_TEXT` lets you publish fixed or variable response slots without changing code.
- `CTA_CHANNEL_URL`, `CTA_WEBSITE_URL`, and `CTA_EXTRA_TEXT` add a light footer to user-facing ticket messages.
- Any `TAG_<NAME>` variable in `.env` becomes `{{name}}` in admin replies. Example: `TAG_WEBSITE=https://your-site.example`.
- Saved tags expand in `/reply`, `/replypublic`, `/quickreply`, and admin private-thread replies.
- Built-in tags also include `{{identity}}`, `{{logo}}`, `{{cta_channel}}`, and `{{cta_website}}` when configured.

## Railway deployment

This project is prepared for Railway using the root `Dockerfile` and `railway.toml`.

Create a Railway volume and mount it to:

```text
/app/data
```

This keeps ticket history and admin state across restarts.

After deploy, run `/storagestatus` from the admin chat.
You should see `Storage mode: railway_volume` before relying on the queue across commits and redeploys.

## Verification

Run:

```bash
python -m py_compile bot.py
```

## License

Creative Commons Attribution 4.0 International (`CC BY 4.0`).
