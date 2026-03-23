# telegram-mentorship-bot

Telegram request bot for mentorship, services, collaboration, and speaking workflows with private intake, anonymous public answers, ticket tracking, flexible topics, and discussion or channel publishing.

## What it does

- Guided and quick question flows
- Request-type routing across mentorship, technical services, collaboration, and speaking
- Optional Calendly booking flow for live meetings
- Flexible topic and stage capture with custom entries
- Private request intake and replies inside Telegram
- Optional hiding of Telegram contact details in the admin view
- Anonymous public replies through a linked discussion group or channel
- Ticket tracking with `/status`
- Website, contact, and profile hubs driven from the configured website/tag links
- Private tickets can continue through replies inside the bot
- Public tickets can continue with `/followup <ticket>` after a public answer until they are ended
- Channel posts can be mirrored to bot users who are not already in the public channel
- Admin dashboard, request grading, ticket notes, checklist reminders, copy-ready templates/tags, identity controls, and public/private reply tools

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

If you set `PUBLIC_CHANNEL_URL` or `DISCUSSION_GROUP_URL`, use the public `https://...` link form. The bot normalizes these to HTTPS.
`MENTOR_IDENTITY_TEXT`, `MENTOR_AVAILABILITY_TEXT`, `CALENDLY_TEXT`, and `CTA_EXTRA_TEXT` support `\n` for line breaks in `.env`.
`CALENDLY_URL` is the main booking setting. If you already use `TAG_BOOKING`, the bot can also fall back to that link.
`CTA_WEBSITE_URL` or `TAG_WEBSITE` powers `/website`, `/profile`, and derived page routes like `/contact`, `/services`, `/publications`, and `/talks`.
`CTA_SERVICES_URL` is optional. If you leave it empty, the bot uses `CTA_WEBSITE_URL` or `TAG_WEBSITE` and opens the `/services` path on that site.
Optional tags like `TAG_CONTACT`, `TAG_CV`, `TAG_EMAIL`, `TAG_LINKEDIN`, `TAG_WHATSAPP`, `TAG_GITHUB`, `TAG_ORCID`, and `TAG_SCHOLAR` let the bot expose direct contact and profile links without extra code changes.

`ADMIN_ID` can stay empty at first. After the bot is running, open it in Telegram and send `/claimadmin` from the admin account.

If you use a linked discussion group for public answers, leave `DISCUSSION_GROUP_ID` empty and run `/setdiscussion` in your private admin chat with the bot, then choose the group from Telegram's picker.

If you use a channel for public answers, leave `PUBLIC_CHANNEL_ID` empty and run `/setchannel` in your private admin chat with the bot, then choose the channel from Telegram's picker.

The bot must be an admin in any discussion group or channel it should post to.
The configured admin account must also be an admin there so Telegram can offer that chat in the picker.

On Railway, queue persistence requires a Railway Volume mounted to `/app/data` if you keep the default relative `./data` storage path.
By default the bot now starts even if the deployment is using ephemeral Railway storage, but it logs a warning because ticket data can reset on redeploy or restart.
If you want startup to fail until persistence is configured correctly, set `REQUIRE_PERSISTENT_STORAGE=true`.

## Public and private behavior

- Private reply keeps the request and answer inside the bot.
- If a user chooses private reply, the admin cannot switch that ticket to public later.
- For private tickets, both sides can continue the same conversation by replying in the bot thread.
- After the latest private mentor reply, a private ticket ends automatically after 1 day without a reply.
- The bot receives the user's Telegram display name, username, and routing ID to deliver replies.
- Before submission, the user can choose whether those Telegram details stay visible in the admin view.
- Public answer keeps the user identity private and publishes only a minimal anonymous version of the request. The admin can still answer privately if that is more useful.
- After a public answer, the user can continue the same ticket with `/followup <ticket_number> <message>` until the mentor ends it.
- After the latest public answer, a public ticket ends automatically after 3 days without a follow-up.
- User-assigned checklist items appear in `/status`, and optional reminders can be sent later through the bot.
- If Calendly is configured, users can open `/meeting` or `/meeting <ticket_number>` to book a live session.
- If the website is configured, users can open `/services`, `/contact`, `/website`, or `/profile` to reach the public site and direct contact routes.
- `/replypublic` lets the bot post the public answer directly to the linked discussion group or channel.
- When the bot knows the public message, the user also receives a copied version of that public post in the bot together with the direct message link.
- `/markpublic` is still available if the public answer was posted manually somewhere else, and manual links are normalized to HTTPS.
- If a public channel is configured, normal channel posts from that channel are mirrored to bot users who are not already members there.
- Users can stop or resume mirrored channel updates with `/muteupdates` and `/resumeupdates`.

## Admin workflow

- `/storagestatus` shows whether the queue is on persistent storage and how many tickets are currently on disk.
- `/dashboard` shows what is waiting on you, what is waiting on the user, and your current response-window message.
- `/ticket <ticket_number>` reloads one ticket by ID and also works when you reply to an admin-side ticket message with `/ticket`.
- `/tickets [queue|private|public|waiting_user|ended|all] [limit]` shows compact ticket lists for high-volume queue scanning.
- `/stats` shows request volume, reply-mode mix, and request-type mix.
- `/note <ticket_number> <text>` and `/notes <ticket_number>` keep internal ticket context without mixing it into replies.
- `/todo <ticket_number> <admin|user> <task>`, `/todos <ticket_number>`, `/tododone`, `/todoundo`, and `/todoremind` add structured follow-up tracking with reminders.
- New tickets include a fast-read section with the main ask, outcome, blocker, readiness grade, and the fastest suggested reply path.
- `/templates` lists concise ready replies for common situations.
- Ticket actions, template shortcuts, and tag placeholders use Telegram copy buttons for faster reuse.
- `/tags` lists reusable placeholders like `{{website}}`.
- `/savetag` and `/deletetag` let you manage saved shortcuts without redeploying.
- `/meetingstatus` shows whether Calendly booking is configured.
- `/sendmeeting` sends a ticket-specific meeting invite with a tracked Calendly link.
- `/quickreply` sends a reusable private answer template and can optionally show or hide mentor identity.
- `/endticket` ends a ticket manually and stops future replies on that ticket.
- `MENTOR_IDENTITY_TEXT` lets you define the identity/signature text used when you choose to show it.
- `MENTOR_LOGO_URL` lets `/start` use a brand image when Telegram can fetch it.
- `MENTOR_AVAILABILITY_TEXT` lets you publish fixed or variable response slots without changing code.
- `CALENDLY_URL`, `CALENDLY_LABEL`, and `CALENDLY_TEXT` configure the user and admin meeting flow.
- `CTA_CHANNEL_URL`, `CTA_WEBSITE_URL`, `CTA_SERVICES_URL`, and `CTA_EXTRA_TEXT` add a light footer to user-facing ticket messages.
- The website, contact, and profile commands reuse the same website/tag sources instead of duplicating URLs in code.
- Any `TAG_<NAME>` variable in `.env` becomes `{{name}}` in admin replies. Example: `TAG_WEBSITE=https://your-site.example`.
- Saved tags expand in `/reply`, `/replypublic`, `/quickreply`, and admin private-thread replies.
- Built-in tags also include `{{identity}}`, `{{logo}}`, `{{calendly}}`, `{{meeting_link}}`, `{{cta_channel}}`, `{{cta_website}}`, and `{{cta_services}}` when configured.

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
