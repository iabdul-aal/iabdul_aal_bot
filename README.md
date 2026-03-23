# iabdul_aal_bot

Telegram mentorship bot for Islam I. Abdulaal.

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

## Railway deployment

This project is prepared for Railway using the root `Dockerfile` and `railway.toml`.

### Required variables

Set these in Railway:

```env
TELEGRAM_TOKEN=your_rotated_bot_token
ADMIN_ID=
PUBLIC_CHANNEL_URL=https://t.me/your_channel
```

`ADMIN_ID` can stay empty at first. After deployment, open the bot in Telegram and send `/claimadmin` from your own account.

### Persistent storage

Create a Railway volume and mount it to:

```text
/app/data
```

This keeps ticket history and admin state across restarts. Railway automatically provides the mount path to the service, so you do not need to set `DATA_DIR` manually in Railway when a volume is attached.

### Deploy from GitHub

1. Push this project to a GitHub repository.
2. In Railway, create a new project.
3. Choose `Deploy from GitHub repo`.
4. Select this repository.
5. Add the environment variables above.
6. Add a volume mounted at `/app/data`.
7. Deploy.

### Deploy from the Railway CLI

1. Install the Railway CLI.
2. Log in.
3. Link or create a Railway project from this folder.
4. Run:

```bash
railway up
```

5. In the Railway dashboard, add the variables and mount a volume at `/app/data`.
6. Redeploy or restart the service.

### Recommended production settings

- Rotate the Telegram token before deploying because the current token was exposed.
- Use a paid Railway plan if you want stronger 24/7 behavior. Free and Trial plans are more limited.
- If you upgrade to a paid plan, set restart policy to `Always` in Railway.

### Free plan notes

- Railway Free is `$0/month` and includes one service with `0.5 GB` RAM and `0.5 GB` volume storage.
- On the Free plan, `Always` restart is not available. `On Failure` is limited to 10 restarts.
- This is still the best free path for this bot because free Render services spin down on idle and free Render web services cannot attach persistent disk storage.

## License

Creative Commons Attribution 4.0 International (`CC BY 4.0`).
