# Discord Tweets Bot

A Discord bot that monitors selected Twitter/X accounts and posts realtime notifications into the Discord channel where the account was added.

## Features

- Monitor tweets, retweets, and replies
- Per-channel monitored account lists
- Multiple Twitter auth token pairs for rotation
- Persistent local state for monitored accounts and last seen tweets
- Discord commands for add, remove, list, and help

## Commands

- `.tweets @username` - add an account to monitor in the current channel
- `.untweets @username` - stop monitoring an account in the current channel
- `.list` - show monitored accounts for the current channel
- `.tweethelp` - show command help

## Requirements

- Python 3.10+
- A Discord bot token
- Twitter/X auth cookie pairs for Twikit:
  - `AUTH_TOKEN1` + `CT0_1`
  - `AUTH_TOKEN2` + `CT0_2`
  - and so on

## Setup

### 1. Clone and enter the project

```bash
git clone https://github.com/aldyrza/discord-tweets.git
cd discord-tweets
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your environment file

```bash
cp .env.example .env
nano .env
```

Fill in your Discord token and Twitter cookie pairs.

### 5. Run the bot

```bash
python3 bot.py
```

## Environment variables

See `.env.example` for the template.

Required:

- `DISCORD_TOKEN`
- At least one valid Twitter pair:
  - `AUTH_TOKEN1`
  - `CT0_1`

Optional:

- Additional pairs for rotation:
  - `AUTH_TOKEN2` + `CT0_2`
  - `AUTH_TOKEN3` + `CT0_3`
  - etc.

## Local files

These files are created locally and should not be committed:

- `.env`
- `venv/`
- `tweets-bot.log`
- `tweets_last.json`
- `tweets_monitored.json`

## systemd service

A sample service file is included at `discord-tweets.service`.

Typical install flow:

```bash
sudo cp discord-tweets.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now discord-tweets
sudo systemctl status discord-tweets
```

If your project path or Python virtualenv path differs, edit the service file first.

## Logs

View service logs with:

```bash
journalctl -u discord-tweets -f
```

The bot also writes a local file log:

```bash
tweets-bot.log
```

## Notes

- This project depends on Twitter/X session cookies, which can expire.
- If monitoring starts failing, refresh the auth values in `.env`.
- Keep this repo private unless you are sure no operational details inside are sensitive.
