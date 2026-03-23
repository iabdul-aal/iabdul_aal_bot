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
- Public-ticket follow-ups by ticket ID until the ticket is ended
- Admin dashboard and ready-reply templates
- Request grading and copy-ready admin shortcuts
- Saved tags for reusable links and text shortcuts
- Discussion-group and channel publishing
- Channel-post mirroring to bot users who are not in the public channel

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

If `PUBLIC_CHANNEL_URL` or `DISCUSSION_GROUP_URL` are set, use public `https://...` links.
`MENTOR_IDENTITY_TEXT`, `MENTOR_AVAILABILITY_TEXT`, and `CTA_EXTRA_TEXT` support `\n` for line breaks in `.env`.

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
8. Run `/storagestatus` and confirm Railway shows `railway_volume` before trusting queue persistence across deploys.
9. Confirm a private-mode ticket cannot be closed publicly through `/replypublic`, `/markpublic`, or a discussion reply.
10. Confirm a public-mode ticket can still receive a private reply and continue through bot-thread replies.
11. Confirm new tickets show a readiness grade and fast-read section for the admin.
12. Confirm template and tag screens expose Telegram copy buttons for quick reuse.
13. Save a tag with `/savetag website https://your-site.example` and confirm `{{website}}` expands in admin replies.
14. Post in the configured public channel and confirm bot users who are not channel members receive the mirrored update.
15. Run `/muteupdates`, post again, and confirm that user no longer receives mirrored channel updates until `/resumeupdates`.
16. If discussion support is enabled, reply to a mirrored public ticket in the discussion group and confirm the user is notified.
17. Send `/followup <ticket_number> <message>` after a public answer and confirm the follow-up returns to the admin on the same ticket.
18. End a ticket with `/endticket` and confirm later replies are blocked.
19. Leave a private ticket waiting on the user for 1 day, and a public answered ticket for 3 days, then confirm both auto-end.

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
