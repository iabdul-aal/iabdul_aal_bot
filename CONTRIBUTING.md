# Contributing

Thanks for contributing to `telegram-mentorship-bot`.

## Project overview

This repository contains a Telegram request bot with:

- Private request intake
- Request-type routing across mentorship, technical services, collaboration, and speaking
- Optional Calendly booking flow
- Flexible topic and stage intake
- Optional hiding of Telegram contact details in admin view
- Anonymous public answer support
- Ticket tracking
- Website, contact, and profile hubs driven from the configured website/tag links
- Private-thread reply routing through the bot
- Public-ticket follow-ups by ticket ID until the ticket is ended
- Admin dashboard and ready-reply templates
- Internal ticket notes and checklist reminders
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
CALENDLY_URL=
CALENDLY_LABEL=Book a meeting
CALENDLY_TEXT=Use this when a live meeting is the fastest way to move the case forward.
CTA_CHANNEL_URL=
CTA_WEBSITE_URL=
CTA_SERVICES_URL=
CTA_EXTRA_TEXT=
TAG_WEBSITE=
TAG_BOOKING=
TAG_CONTACT=
TAG_CV=
TAG_EMAIL=
TAG_LINKEDIN=
TAG_WHATSAPP=
TAG_GITHUB=
TAG_ORCID=
TAG_SCHOLAR=
PUBLIC_CHANNEL_URL=
DISCUSSION_GROUP_URL=
DISCUSSION_GROUP_ID=
PUBLIC_CHANNEL_ID=
DATA_DIR=./data
```

If `PUBLIC_CHANNEL_URL` or `DISCUSSION_GROUP_URL` are set, use public `https://...` links.
`MENTOR_IDENTITY_TEXT`, `MENTOR_AVAILABILITY_TEXT`, `CALENDLY_TEXT`, and `CTA_EXTRA_TEXT` support `\n` for line breaks in `.env`.
`CALENDLY_URL` is the main booking setting. `TAG_BOOKING` can still be used as a fallback booking link.
`CTA_WEBSITE_URL` or `TAG_WEBSITE` powers `/website`, `/profile`, and derived page routes like `/contact`, `/services`, `/publications`, and `/talks`.
`CTA_SERVICES_URL` is optional. If it stays empty, the bot derives the services page from `CTA_WEBSITE_URL` or `TAG_WEBSITE` and appends `/services`.
Optional tags like `TAG_CONTACT`, `TAG_CV`, `TAG_EMAIL`, `TAG_LINKEDIN`, `TAG_WHATSAPP`, `TAG_GITHUB`, `TAG_ORCID`, and `TAG_SCHOLAR` let the bot expose direct contact and profile links without extra code changes.
`REQUIRE_PERSISTENT_STORAGE` is optional. Leave it empty or `false` to allow Railway ephemeral storage with a warning, or set it to `true` to require a mounted volume at startup.

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
5. Submit a private ticket and confirm the request-type step appears before topic selection.
6. Submit a public ticket and confirm the request type is visible in the admin queue.
7. Test `/dashboard`, `/templates`, `/tags`, `/quickreply`, `/reply`, `/replypublic`, `/markpublic`, and `/status`.
8. Test `/ticket <ticket_number>` and `/tickets queue 20` from the admin chat.
9. Test `/note <ticket_number>`, `/notes <ticket_number>`, `/todo <ticket_number> user <task>`, `/tododone`, and `/todoremind`.
10. Confirm a user-assigned checklist item appears in `/status <ticket_number>` and reminder messages are delivered after the configured delay.
11. Run `/storagestatus` and confirm Railway shows `railway_volume` before trusting queue persistence across deploys.
12. Confirm a private-mode ticket cannot be closed publicly through `/replypublic`, `/markpublic`, or a discussion reply.
13. Confirm a public-mode ticket can still receive a private reply and continue through bot-thread replies.
14. Confirm new tickets show a readiness grade and fast-read section for the admin.
15. Confirm template and tag screens expose Telegram copy buttons for quick reuse.
16. Save a tag with `/savetag website https://your-site.example` and confirm `{{website}}` expands in admin replies.
17. Post in the configured public channel and confirm bot users who are not channel members receive the mirrored update.
18. Run `/muteupdates`, post again, and confirm that user no longer receives mirrored channel updates until `/resumeupdates`.
19. If discussion support is enabled, reply to a mirrored public ticket in the discussion group and confirm the user is notified.
20. Send `/followup <ticket_number> <message>` after a public answer and confirm the follow-up returns to the admin on the same ticket.
21. End a ticket with `/endticket` and confirm later replies are blocked.
22. Leave a private ticket waiting on the user for 1 day, and a public answered ticket for 3 days, then confirm both auto-end.
23. Confirm `/replypublic` and discussion replies send the user both the public-answer notice and a copied version of the actual public post when the bot has that source message.
24. Configure `CALENDLY_URL`, test `/meeting`, `/meeting <ticket_number>`, `/meetingstatus`, and `/sendmeeting <ticket_number>`.
25. Confirm `{{meeting_link}}` expands correctly in `/quickreply` and other admin reply paths.
26. Confirm `/services` and the `Get other services` button open the correct website services page.
27. Confirm `/contact` opens the expected contact page and any configured direct channels.
28. Confirm `/website` opens the main website sections without duplicate or broken links.
29. Confirm `/profile` opens the public profile snapshot and key public links.

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
