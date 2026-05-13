# tweets-bot.py - Discord Twitter Monitor Bot
# Monitors Twitter accounts and sends realtime notifications to Discord channels
import asyncio
import logging
import random
import os
import json
import re
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
from twikit import Client

# Load environment variables from this directory's .env
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    load_dotenv(env_path)
    print(f"[INFO] Loaded .env file from {env_path}")
except ImportError:
    print("[WARNING] python-dotenv not installed")

# ==================== CONFIGURATION ====================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '')

# Twitter tokens - load individual AUTH_TOKEN and CT0 pairs
TWITTER_TOKENS = []

# Dynamically load AUTH_TOKEN{n} and CT0_{n} pairs
token_index = 1
while True:
    auth_token = os.getenv(f'AUTH_TOKEN{token_index}', '').strip()
    ct0 = os.getenv(f'CT0_{token_index}', '').strip()
    if not auth_token and not ct0:
        break
    if auth_token and ct0:
        TWITTER_TOKENS.append({'auth_token': auth_token, 'ct0': ct0})
        print(f"[DEBUG] Loaded token {token_index}: auth_token={auth_token[:20]}...")
    else:
        print(f"[WARNING] Token {token_index} incomplete: auth_token={'set' if auth_token else 'missing'}, ct0={'set' if ct0 else 'missing'}")
    token_index += 1

if not TWITTER_TOKENS:
    print("[ERROR] No Twitter tokens loaded! Add AUTH_TOKEN1/CT0_1 pairs to .env")
else:
    print(f"[INFO] Loaded {len(TWITTER_TOKENS)} Twitter token pair(s)")

# Monitoring settings
CHECK_INTERVAL = 30
DELAY_BETWEEN_ACCOUNTS = 5
TWEET_FETCH_COUNT = 5
RATE_LIMIT_SKIP_CYCLES = 8
USER_CACHE_TTL = 900

# Human-like delay settings
HUMAN_DELAY_MIN = 3
HUMAN_DELAY_MAX = 8
HUMAN_DELAY_OCCASIONAL_MIN = 10
HUMAN_DELAY_OCCASIONAL_MAX = 20
HUMAN_DELAY_OCCASIONAL_CHANCE = 0.15

# Per-account check interval
ACCOUNT_CHECK_INTERVAL_MIN = 17
ACCOUNT_CHECK_INTERVAL_MAX = 76

# Token settings
TOKEN_RATE_LIMIT_COOLDOWN = 1800
TOKEN_REQUEST_DELAY = 3

# Data files
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
MONITORED_FILE = os.path.join(DATA_DIR, "tweets_monitored.json")
LAST_TWEETS_FILE = os.path.join(DATA_DIR, "tweets_last.json")

# ==================== LOGGING ====================
console_format = '%(levelname)s: %(message)s'
file_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

file_handler = logging.FileHandler(os.path.join(DATA_DIR, 'tweets-bot.log'))
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(file_format))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(console_format))

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

# Reduce verbose HTTP logging
for log_name in ['httpx', 'httpcore', 'httpcore.http11', 'httpcore.connection',
                 'aiohttp', 'urllib3', 'urllib3.connectionpool', 'twikit',
                 'twikit.client', 'discord', 'discord.http', 'discord.gateway']:
    logging.getLogger(log_name).setLevel(logging.WARNING)

# ==================== GLOBAL VARIABLES ====================
# Structure: {channel_id_str: {username: {filters, muted, user_data}}}
monitored_accounts = {}
last_tweets = {}

# Cache & tracking
user_cache = {}
rate_limit_tracker = {}
account_check_intervals = {}
token_usage_tracker = {}
current_token_index = 0
token_request_counter = 0
monitoring_cycle_counter = 0

# Twitter client
twitter_client = Client()

# ==================== EMOJI MAPPING ====================
def get_action_emoji(action_type: str) -> str:
    action_emojis = {
        "tweet": "✍️",
        "retweet": "🐦",
        "reply": "💬",
        "quote": "💭",
        "default": "📝"
    }
    return action_emojis.get(action_type, action_emojis["default"])

# ==================== DATA MANAGEMENT ====================
def load_data():
    global monitored_accounts, last_tweets
    try:
        if os.path.exists(MONITORED_FILE):
            with open(MONITORED_FILE, 'r', encoding='utf-8') as f:
                monitored_accounts = json.load(f)
            logger.info(f"📂 Loaded {len(monitored_accounts)} channel(s) with monitored accounts")
        if os.path.exists(LAST_TWEETS_FILE):
            with open(LAST_TWEETS_FILE, 'r', encoding='utf-8') as f:
                last_tweets = json.load(f)
            logger.info(f"📂 Loaded {len(last_tweets)} tweet records")
    except Exception as e:
        logger.error(f"Error loading data: {e}")

def save_data():
    try:
        with open(MONITORED_FILE, 'w', encoding='utf-8') as f:
            json.dump(monitored_accounts, f, indent=2, ensure_ascii=False)
        with open(LAST_TWEETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(last_tweets, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving data: {e}")

# ==================== HELPER FUNCTIONS ====================
def clear_trailing_tco(text: str) -> str:
    # Removes the auto-appended t.co media link at the very end of the tweet
    return re.sub(r'https://t\.co/[a-zA-Z0-9]+\s*$', '', text).strip()

def format_number(num) -> str:
    try:
        num = int(num)
        if num >= 1000000:
            return f"{num/1000000:.2f}M"
        elif num >= 1000:
            return f"{num/1000:.1f}K"
        return str(num)
    except:
        return str(num)

def format_timestamp(created_at) -> str:
    try:
        if isinstance(created_at, str):
            try:
                dt = datetime.strptime(created_at, '%a %b %d %H:%M:%S %z %Y')
            except ValueError:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                except ValueError:
                    dt = datetime.now(timezone.utc)
        elif hasattr(created_at, 'timestamp'):
            dt = created_at
        else:
            dt = datetime.now(timezone.utc)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        wib_tz = timezone(timedelta(hours=7))
        dt_wib = dt.astimezone(wib_tz)
        now = datetime.now(wib_tz)
        diff = now - dt_wib
        total_seconds = int(diff.total_seconds())

        if total_seconds < 0:
            time_ago = "just now"
        elif total_seconds < 60:
            time_ago = f"{total_seconds}s ago"
        elif total_seconds < 3600:
            time_ago = f"{total_seconds // 60}m ago"
        elif total_seconds < 86400:
            time_ago = f"{total_seconds // 3600}h ago"
        else:
            time_ago = f"{total_seconds // 86400}d ago"

        date_str = dt_wib.strftime("%b %d, %y @ %I:%M %p")
        return f"{date_str} ({time_ago})"
    except Exception as e:
        logger.error(f"Error formatting timestamp: {e}")
        return datetime.now().strftime("%b %d, %y @ %I:%M %p")

def detect_tweet_type(tweet) -> str:
    if hasattr(tweet, 'retweeted_tweet') and tweet.retweeted_tweet:
        return 'retweet'
    if hasattr(tweet, 'in_reply_to_screen_name'):
        if tweet.in_reply_to_screen_name and str(tweet.in_reply_to_screen_name).strip():
            return 'reply'
    if hasattr(tweet, 'in_reply_to_status_id'):
        if tweet.in_reply_to_status_id and tweet.in_reply_to_status_id != 0:
            return 'reply'
    if hasattr(tweet, 'in_reply_to_user_id'):
        if tweet.in_reply_to_user_id and tweet.in_reply_to_user_id != 0:
            return 'reply'
    if hasattr(tweet, 'text') and tweet.text:
        if str(tweet.text).strip().startswith('@'):
            return 'reply'
    return 'tweet'

def should_send_notification(channel_id: str, username: str, tweet_type: str) -> bool:
    account = monitored_accounts.get(channel_id, {}).get(username)
    if not account:
        return False
    if account.get('muted', False):
        return False
    filters = account.get('filters', {})
    return filters.get(tweet_type, True)

def get_account_key(channel_id_str: str, username: str) -> str:
    return f"{channel_id_str}_{username}"

# ==================== HUMAN-LIKE DELAYS ====================
def get_human_delay() -> float:
    if random.random() < HUMAN_DELAY_OCCASIONAL_CHANCE:
        return random.uniform(HUMAN_DELAY_OCCASIONAL_MIN, HUMAN_DELAY_OCCASIONAL_MAX)
    return random.uniform(HUMAN_DELAY_MIN, HUMAN_DELAY_MAX)

def get_account_check_interval() -> float:
    return random.uniform(ACCOUNT_CHECK_INTERVAL_MIN, ACCOUNT_CHECK_INTERVAL_MAX)

def is_account_ready_for_check(account_key: str) -> bool:
    current_time = datetime.now().timestamp()
    if account_key not in account_check_intervals:
        interval = get_account_check_interval()
        account_check_intervals[account_key] = {
            'last_check': 0,
            'next_check': current_time + interval,
            'interval': interval
        }
        return True
    return current_time >= account_check_intervals[account_key].get('next_check', 0)

def update_account_check_time(account_key: str):
    current_time = datetime.now().timestamp()
    interval = get_account_check_interval()
    if account_key not in account_check_intervals:
        account_check_intervals[account_key] = {}
    account_check_intervals[account_key]['last_check'] = current_time
    account_check_intervals[account_key]['next_check'] = current_time + interval
    account_check_intervals[account_key]['interval'] = interval

def cleanup_account_tracking(account_key: str):
    if account_key in last_tweets:
        del last_tweets[account_key]
    if account_key in account_check_intervals:
        del account_check_intervals[account_key]

# ==================== TOKEN MANAGEMENT ====================
def get_next_token():
    global current_token_index
    if not TWITTER_TOKENS:
        return None, None
    current_time = datetime.now().timestamp()
    available_tokens = []
    for idx, token in enumerate(TWITTER_TOKENS):
        tracker = token_usage_tracker.get(idx, {})
        if tracker.get('rate_limited', False):
            if current_time - tracker.get('last_limit', 0) < TOKEN_RATE_LIMIT_COOLDOWN:
                continue
        last_used = tracker.get('last_used', 0)
        if current_time - last_used < TOKEN_REQUEST_DELAY:
            continue
        available_tokens.append({
            'index': idx, 'last_used': last_used,
            'request_count': tracker.get('request_count', 0), 'token': token
        })
    if not available_tokens:
        all_tokens = []
        for idx, token in enumerate(TWITTER_TOKENS):
            tracker = token_usage_tracker.get(idx, {})
            all_tokens.append({
                'index': idx, 'last_used': tracker.get('last_used', 0),
                'request_count': tracker.get('request_count', 0), 'token': token
            })
        available_tokens = sorted(all_tokens, key=lambda x: (x['last_used'], x['request_count']))
    selected = min(available_tokens, key=lambda x: (x['last_used'], x['request_count']))
    return selected['token'], selected['index']

def get_token_label(token_idx):
    """Get a readable label for a token (index + auth_token prefix)"""
    if token_idx is not None and 0 <= token_idx < len(TWITTER_TOKENS):
        auth_prefix = TWITTER_TOKENS[token_idx]['auth_token'][:8]
        return f"Token{token_idx + 1}({auth_prefix}...)"
    return f"Token{token_idx + 1}(unknown)"

def is_token_invalid_error(error_str: str) -> bool:
    """Check if an error indicates an invalid/expired token"""
    invalid_indicators = [
        '401', 'unauthorized', 'forbidden', '403',
        'expired', 'invalid', 'bad authentication',
        'could not authenticate', 'not authenticated',
        'authentication required', 'invalid credentials',
        'TwitterException(353',  # suspended/locked
    ]
    error_lower = error_str.lower()
    return any(indicator in error_lower for indicator in invalid_indicators)

def mark_token_rate_limited(token_idx):
    if token_idx not in token_usage_tracker:
        token_usage_tracker[token_idx] = {}
    token_usage_tracker[token_idx]['rate_limited'] = True
    token_usage_tracker[token_idx]['last_limit'] = datetime.now().timestamp()
    token_usage_tracker[token_idx]['error_count'] = token_usage_tracker[token_idx].get('error_count', 0) + 1
    label = get_token_label(token_idx)
    logger.warning(f"⚠️ {label} rate limited (errors: {token_usage_tracker[token_idx]['error_count']})")

def mark_token_invalid(token_idx, error_str: str):
    """Mark a token as invalid/expired with detailed logging"""
    if token_idx not in token_usage_tracker:
        token_usage_tracker[token_idx] = {}
    token_usage_tracker[token_idx]['invalid'] = True
    token_usage_tracker[token_idx]['invalid_since'] = datetime.now().timestamp()
    token_usage_tracker[token_idx]['invalid_error'] = error_str[:200]
    label = get_token_label(token_idx)
    logger.error(f"🚫 {label} INVALID/EXPIRED — {error_str[:150]}")
    
    # Count how many tokens are still valid
    valid_count = sum(1 for i in range(len(TWITTER_TOKENS)) if not token_usage_tracker.get(i, {}).get('invalid', False))
    logger.warning(f"🔑 Valid tokens remaining: {valid_count}/{len(TWITTER_TOKENS)}")
    if valid_count == 0:
        logger.critical(f"❌ ALL TOKENS ARE INVALID! Bot cannot fetch tweets. Please update .env with valid credentials.")

async def switch_twitter_token():
    global twitter_client, current_token_index
    token_data, token_idx = get_next_token()
    if not token_data:
        return False
    try:
        twitter_client.set_cookies({
            'auth_token': token_data['auth_token'],
            'ct0': token_data['ct0']
        })
        current_token_index = token_idx
        if token_idx not in token_usage_tracker:
            token_usage_tracker[token_idx] = {}
        token_usage_tracker[token_idx]['last_used'] = datetime.now().timestamp()
        logger.info(f"🔄 Switched to token {token_idx + 1}/{len(TWITTER_TOKENS)}")
        return True
    except Exception as e:
        logger.error(f"❌ Error switching token: {e}")
        return False

async def rotate_token_proactively():
    global twitter_client, current_token_index, token_request_counter
    if len(TWITTER_TOKENS) <= 1:
        return
    token_request_counter += 1
    token_data, token_idx = get_next_token()
    if not token_data:
        return
    if token_idx != current_token_index:
        try:
            twitter_client.set_cookies({
                'auth_token': token_data['auth_token'],
                'ct0': token_data['ct0']
            })
            current_token_index = token_idx
            if token_idx not in token_usage_tracker:
                token_usage_tracker[token_idx] = {}
            token_usage_tracker[token_idx]['last_used'] = datetime.now().timestamp()
            token_usage_tracker[token_idx]['request_count'] = token_usage_tracker[token_idx].get('request_count', 0) + 1
        except Exception as e:
            logger.error(f"❌ Error rotating token: {e}")
    else:
        if token_idx not in token_usage_tracker:
            token_usage_tracker[token_idx] = {}
        token_usage_tracker[token_idx]['last_used'] = datetime.now().timestamp()
        token_usage_tracker[token_idx]['request_count'] = token_usage_tracker[token_idx].get('request_count', 0) + 1

# ==================== TWITTER AUTH ====================
async def authenticate_twitter():
    try:
        if not TWITTER_TOKENS:
            logger.error("Twitter credentials not set")
            return False
        token_data, token_idx = get_next_token()
        if not token_data:
            return False
        twitter_client.set_cookies({
            'auth_token': token_data['auth_token'],
            'ct0': token_data['ct0']
        })
        if token_idx not in token_usage_tracker:
            token_usage_tracker[token_idx] = {}
        token_usage_tracker[token_idx]['last_used'] = datetime.now().timestamp()
        logger.info(f"✅ Twitter authenticated with token {token_idx + 1}/{len(TWITTER_TOKENS)}")
        return True
    except Exception as e:
        logger.error(f"Twitter auth failed: {e}")
        return False

async def get_user_with_cache(username: str):
    current_time = datetime.now().timestamp()
    if username in user_cache:
        cache_data = user_cache[username]
        if current_time - cache_data['last_updated'] < USER_CACHE_TTL:
            return cache_data['user_obj']

    max_retries = len(TWITTER_TOKENS) if len(TWITTER_TOKENS) > 1 else 1
    last_error = None

    for attempt in range(max_retries):
        try:
            if current_token_index in token_usage_tracker:
                tracker = token_usage_tracker[current_token_index]
                time_since_last = current_time - tracker.get('last_used', 0)
                if time_since_last < TOKEN_REQUEST_DELAY:
                    await asyncio.sleep(TOKEN_REQUEST_DELAY - time_since_last)
                else:
                    await asyncio.sleep(get_human_delay())

            await rotate_token_proactively()
            user = await twitter_client.get_user_by_screen_name(username)
            user_cache[username] = {'user_obj': user, 'last_updated': datetime.now().timestamp()}

            if current_token_index not in token_usage_tracker:
                token_usage_tracker[current_token_index] = {}
            token_usage_tracker[current_token_index]['last_used'] = datetime.now().timestamp()
            token_usage_tracker[current_token_index]['request_count'] = token_usage_tracker[current_token_index].get('request_count', 0) + 1
            return user
        except Exception as e:
            error_str = str(e)
            last_error = e
            label = get_token_label(current_token_index)
            if is_token_invalid_error(error_str):
                mark_token_invalid(current_token_index, error_str)
                if attempt < max_retries - 1 and len(TWITTER_TOKENS) > 1:
                    if await switch_twitter_token():
                        await asyncio.sleep(get_human_delay())
                        continue
            elif "429" in error_str or "rate limit" in error_str.lower():
                mark_token_rate_limited(current_token_index)
                if attempt < max_retries - 1 and len(TWITTER_TOKENS) > 1:
                    if await switch_twitter_token():
                        await asyncio.sleep(get_human_delay() * 2)
                        continue
            else:
                logger.error(f"❌ {label} error fetching user @{username}: {error_str[:150]}")
                break

    if username in user_cache:
        return user_cache[username]['user_obj']
    raise last_error

# ==================== DISCORD EMBED BUILDERS ====================
def build_tweet_embed(username: str, tweet, tweet_type: str, user_data: dict = None) -> discord.Embed:
    """Build a Discord embed for a tweet notification"""
    action_emoji = get_action_emoji(tweet_type)
    real_name = user_data.get('real_name', username) if user_data else username
    created_at = getattr(tweet, 'created_at', datetime.now())
    timestamp_str = format_timestamp(created_at)

    # Color based on tweet type
    colors = {
        'tweet': 0x1DA1F2,    # Twitter blue
        'retweet': 0x17BF63,  # Green
        'reply': 0xFFAD1F,    # Orange
    }
    color = colors.get(tweet_type, 0x1DA1F2)

    # Title based on type
    type_labels = {
        'tweet': 'New Tweet',
        'retweet': 'Retweet',
        'reply': 'Reply',
    }
    type_label = type_labels.get(tweet_type, 'Tweet')

    embed = discord.Embed(color=color)
    embed.set_author(
        name=f"{action_emoji} {real_name} (@{username})",
        url=f"https://x.com/{username}",
        icon_url=f"https://unavatar.io/twitter/{username}"
    )

    # Handle retweet
    if tweet_type == "retweet" and hasattr(tweet, 'retweeted_tweet') and tweet.retweeted_tweet:
        retweeted_tweet = tweet.retweeted_tweet
        original_content = retweeted_tweet.text if hasattr(retweeted_tweet, 'text') else str(retweeted_tweet)
        original_author = "unknown"
        if hasattr(retweeted_tweet, 'user') and retweeted_tweet.user:
            if hasattr(retweeted_tweet.user, 'screen_name'):
                original_author = retweeted_tweet.user.screen_name
        cleaned = clear_trailing_tco(original_content)
        embed.description = f"🔁 **Retweeted from @{original_author}**\n\n{cleaned[:1500]}"
    elif tweet_type == "reply":
        content = tweet.text if hasattr(tweet, 'text') else str(tweet)
        cleaned = clear_trailing_tco(content)
        in_reply_to = getattr(tweet, 'in_reply_to_screen_name', '')
        if in_reply_to:
            embed.description = f"💬 **Replying to @{in_reply_to}**\n\n{cleaned[:1500]}"
        else:
            embed.description = f"{cleaned[:1500]}"
    else:
        content = tweet.text if hasattr(tweet, 'text') else str(tweet)
        cleaned = clear_trailing_tco(content)
        embed.description = f"{cleaned[:1500]}"

    # Add tweet images if available
    try:
        if hasattr(tweet, 'media') and tweet.media:
            for media in tweet.media:
                # twikit 2.x uses `media_url` property
                if hasattr(media, 'media_url') and media.media_url:
                    embed.set_image(url=media.media_url)
                    break
                # fallback for other/older versions
                elif hasattr(media, 'media_url_https') and media.media_url_https:
                    embed.set_image(url=media.media_url_https)
                    break
                # fallback if media is a dictionary
                elif isinstance(media, dict):
                    url = media.get('media_url_https') or media.get('media_url')
                    if url:
                        embed.set_image(url=url)
                        break
    except:
        pass

    embed.set_footer(text=f"{type_label} • {timestamp_str}")

    return embed

def build_account_added_embed(username: str, user_data: dict) -> discord.Embed:
    """Build embed for account added confirmation"""
    real_name = user_data.get('real_name', username)
    followers = format_number(user_data.get('followers', 0))
    following = format_number(user_data.get('following', 0))

    embed = discord.Embed(
        title="✅ Account Added to Monitoring",
        color=0x17BF63,
        description=(
            f"**Account:** [{real_name}](https://x.com/{username}) (@{username})\n"
            f"**Followers:** {followers}\n"
            f"**Following:** {following}"
        )
    )
    embed.set_thumbnail(url=f"https://unavatar.io/twitter/{username}")
    embed.set_footer(text="Twitter Monitor Bot")
    embed.timestamp = datetime.now(timezone.utc)
    return embed

def build_list_embed(channel_id: str) -> discord.Embed:
    """Build embed for monitored accounts list"""
    accounts = monitored_accounts.get(channel_id, {})

    if not accounts:
        embed = discord.Embed(
            title="📋 Monitored Accounts",
            color=0x808080,
            description="No accounts being monitored in this channel.\n\nUse `.tweets @username` to add one."
        )
        embed.set_footer(text="Twitter Monitor Bot")
        return embed

    desc = ""
    for idx, (username, settings) in enumerate(sorted(accounts.items()), 1):
        user_data = settings.get('user_data', {})
        real_name = user_data.get('real_name', username)
        muted = settings.get('muted', False)
        filters = settings.get('filters', {})

        status_icon = "🔕" if muted else "🔔"
        filter_icons = []
        if filters.get('tweet', True):
            filter_icons.append("✍️")
        if filters.get('retweet', True):
            filter_icons.append("🐦")
        if filters.get('reply', True):
            filter_icons.append("💬")

        filter_str = " ".join(filter_icons) if filter_icons else "❌ All off"
        desc += f"`{idx}.` {status_icon} **{real_name}** ([@{username}](https://x.com/{username})) — {filter_str}\n"

    embed = discord.Embed(
        title=f"📋 Monitored Accounts ({len(accounts)})",
        color=0x1DA1F2,
        description=desc
    )
    embed.set_footer(text="Use .tweets @username to add • .untweets @username to remove")
    embed.timestamp = datetime.now(timezone.utc)
    return embed

# ==================== TWEET CHECK LOGIC ====================
async def check_account_tweets(username: str, channel_id: int, bot_client):
    """Check for new tweets and send notifications to Discord channel"""
    channel_id_str = str(channel_id)
    account_key = get_account_key(channel_id_str, username)
    token_label = get_token_label(current_token_index)
    logger.info(f"🔎 @{username} | ch:{channel_id} | using {token_label}")

    # Rate limit skip
    if username in rate_limit_tracker:
        tracker = rate_limit_tracker[username]
        if tracker.get('skip_cycles', 0) > 0:
            remaining = tracker['skip_cycles']
            tracker['skip_cycles'] -= 1
            logger.info(f"⏭️ @{username} | skipped (rate limit cooldown, {remaining} cycles left)")
            return False

    try:
        user = await get_user_with_cache(username)

        # Fetch tweets with token rotation
        tweets = None
        max_token_retries = len(TWITTER_TOKENS) if len(TWITTER_TOKENS) > 1 else 1
        current_time = datetime.now().timestamp()
        used_token_label = get_token_label(current_token_index)

        for tweet_attempt in range(max_token_retries):
            try:
                if current_token_index in token_usage_tracker:
                    tracker = token_usage_tracker[current_token_index]
                    time_since_last = current_time - tracker.get('last_used', 0)
                    if time_since_last < TOKEN_REQUEST_DELAY:
                        await asyncio.sleep(TOKEN_REQUEST_DELAY - time_since_last)
                    else:
                        await asyncio.sleep(get_human_delay())

                await rotate_token_proactively()
                used_token_label = get_token_label(current_token_index)

                try:
                    tweets = await twitter_client.get_user_tweets(user.id, 'TweetsAndReplies', count=TWEET_FETCH_COUNT)
                except:
                    tweets = await twitter_client.get_user_tweets(user.id, 'Tweets', count=TWEET_FETCH_COUNT)

                if current_token_index not in token_usage_tracker:
                    token_usage_tracker[current_token_index] = {}
                token_usage_tracker[current_token_index]['last_used'] = datetime.now().timestamp()
                token_usage_tracker[current_token_index]['request_count'] = token_usage_tracker[current_token_index].get('request_count', 0) + 1
                break
            except Exception as e:
                error_str = str(e)
                if is_token_invalid_error(error_str):
                    mark_token_invalid(current_token_index, error_str)
                    if tweet_attempt < max_token_retries - 1 and len(TWITTER_TOKENS) > 1:
                        if await switch_twitter_token():
                            used_token_label = get_token_label(current_token_index)
                            await asyncio.sleep(get_human_delay())
                            continue
                    raise
                elif "429" in error_str or "rate limit" in error_str.lower():
                    mark_token_rate_limited(current_token_index)
                    if tweet_attempt < max_token_retries - 1 and len(TWITTER_TOKENS) > 1:
                        if await switch_twitter_token():
                            used_token_label = get_token_label(current_token_index)
                            await asyncio.sleep(get_human_delay() * 2)
                            continue
                    raise
                else:
                    raise

        if tweets is None:
            raise Exception("Failed to fetch tweets")

        if not isinstance(tweets, list):
            tweets = list(tweets) if tweets else []

        tweet_count = len(tweets)
        last_id = last_tweets.get(account_key)

        if not last_id:
            if tweets and tweet_count > 0:
                last_tweets[account_key] = str(tweets[0].id)
                save_data()
            logger.info(f"✅ @{username} | fetched {tweet_count} tweets | baseline set | {used_token_label}")
            return True

        new_tweets = []
        for tweet in tweets:
            tweet_id = int(tweet.id)
            if tweet_id <= int(last_id):
                break
            new_tweets.append(tweet)

        if new_tweets:
            last_tweets[account_key] = str(new_tweets[0].id)
            save_data()
            logger.info(f"📬 @{username} | {len(new_tweets)} NEW tweet(s) found | {used_token_label}")

            channel = bot_client.get_channel(channel_id)
            if not channel:
                try:
                    channel = await bot_client.fetch_channel(channel_id)
                except:
                    logger.error(f"Cannot find channel {channel_id}")
                    return False

            for tweet in reversed(new_tweets):
                tweet_type = detect_tweet_type(tweet)
                if should_send_notification(channel_id_str, username, tweet_type):
                    account = monitored_accounts.get(channel_id_str, {}).get(username, {})
                    user_data = account.get('user_data', {})
                    embed = build_tweet_embed(username, tweet, tweet_type, user_data)
                    tweet_url = f"https://x.com/{username}/status/{tweet.id}"
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(label="View on 𝕏", url=tweet_url))

                    try:
                        await channel.send(embed=embed, view=view)
                        logger.info(f"📤 @{username} | sent {tweet_type} → ch:{channel_id}")
                    except Exception as e:
                        logger.error(f"Error sending to channel {channel_id}: {e}")

                    await asyncio.sleep(get_human_delay())
        else:
            logger.info(f"✅ @{username} | fetched {tweet_count} tweets | no new | {used_token_label}")

        if username in rate_limit_tracker:
            if rate_limit_tracker[username].get('skip_cycles', 0) == 0:
                del rate_limit_tracker[username]
        return True

    except Exception as e:
        error_str = str(e)
        token_label = get_token_label(current_token_index)
        if is_token_invalid_error(error_str):
            mark_token_invalid(current_token_index, error_str)
            logger.error(f"🚫 @{username} | {token_label} invalid/expired — {error_str[:150]}")
            if len(TWITTER_TOKENS) > 1:
                await switch_twitter_token()
        elif "429" in error_str or "rate limit" in error_str.lower():
            logger.warning(f"⏸️ @{username} | rate limited | {token_label} | skipping {RATE_LIMIT_SKIP_CYCLES} cycles")
            mark_token_rate_limited(current_token_index)
            if len(TWITTER_TOKENS) > 1:
                await switch_twitter_token()
            if username not in rate_limit_tracker:
                rate_limit_tracker[username] = {
                    'last_limit': datetime.now().timestamp(),
                    'skip_cycles': RATE_LIMIT_SKIP_CYCLES,
                    'consecutive_failures': 0
                }
            else:
                rate_limit_tracker[username]['last_limit'] = datetime.now().timestamp()
                rate_limit_tracker[username]['skip_cycles'] = RATE_LIMIT_SKIP_CYCLES
        else:
            logger.error(f"❌ @{username} | {token_label} | error: {error_str[:150]}")
        return False

# ==================== ADD ACCOUNT WITH RETRY ====================
async def add_account_with_retry(username: str, channel_id_str: str, max_retries=3):
    """Add account with retry and rate limit handling"""
    retry_delays = [30, 60, 120]

    for attempt in range(max_retries):
        try:
            user = await get_user_with_cache(username)

            # Fetch latest tweet
            tweets = None
            max_token_retries = len(TWITTER_TOKENS) if len(TWITTER_TOKENS) > 1 else max_retries
            current_time = datetime.now().timestamp()

            for tweet_attempt in range(max_token_retries):
                try:
                    if current_token_index in token_usage_tracker:
                        tracker = token_usage_tracker[current_token_index]
                        time_since_last = current_time - tracker.get('last_used', 0)
                        if time_since_last < TOKEN_REQUEST_DELAY:
                            await asyncio.sleep(TOKEN_REQUEST_DELAY - time_since_last)
                        else:
                            await asyncio.sleep(get_human_delay())
                    await rotate_token_proactively()
                    tweets = await twitter_client.get_user_tweets(user.id, 'Tweets', count=1)

                    if current_token_index not in token_usage_tracker:
                        token_usage_tracker[current_token_index] = {}
                    token_usage_tracker[current_token_index]['last_used'] = datetime.now().timestamp()
                    token_usage_tracker[current_token_index]['request_count'] = token_usage_tracker[current_token_index].get('request_count', 0) + 1
                    break
                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str or "rate limit" in error_str.lower():
                        mark_token_rate_limited(current_token_index)
                        if tweet_attempt < max_token_retries - 1 and len(TWITTER_TOKENS) > 1:
                            if await switch_twitter_token():
                                await asyncio.sleep(get_human_delay() * 2)
                                continue
                        raise
                    else:
                        raise

            # Set baseline tweet
            account_key = get_account_key(channel_id_str, username)
            if tweets and len(tweets) > 0:
                last_tweets[account_key] = str(tweets[0].id)
                account_check_intervals[account_key] = {
                    'last_check': 0,
                    'next_check': datetime.now().timestamp(),
                    'interval': ACCOUNT_CHECK_INTERVAL_MIN
                }

            user_data = {
                "real_name": getattr(user, 'name', username),
                "followers": getattr(user, 'followers_count', 0),
                "following": getattr(user, 'following_count', 0)
            }

            if channel_id_str not in monitored_accounts:
                monitored_accounts[channel_id_str] = {}

            monitored_accounts[channel_id_str][username] = {
                "filters": {"tweet": True, "retweet": True, "reply": True},
                "muted": False,
                "user_data": user_data
            }

            save_data()
            logger.info(f"✅ Added @{username} for channel {channel_id_str}")

            return {'success': True, 'user_data': user_data, 'user': user}

        except Exception as e:
            error_str = str(e)
            is_rate_limit = "429" in error_str or "rate limit" in error_str.lower()

            if is_rate_limit and attempt < max_retries - 1:
                if len(TWITTER_TOKENS) > 1:
                    mark_token_rate_limited(current_token_index)
                    if await switch_twitter_token():
                        await asyncio.sleep(get_human_delay() * 2)
                        continue
                delay = retry_delays[attempt]
                await asyncio.sleep(delay)
                continue
            else:
                return {
                    'success': False,
                    'error': str(e),
                    'is_rate_limit': is_rate_limit
                }

    return {'success': False, 'error': 'Failed after all retries', 'is_rate_limit': True}

# ==================== TOKEN HEALTH LOGGING ====================
def log_token_health_summary():
    """Log a summary of all token statuses"""
    lines = []
    for idx in range(len(TWITTER_TOKENS)):
        label = get_token_label(idx)
        tracker = token_usage_tracker.get(idx, {})
        status_parts = []
        if tracker.get('invalid', False):
            since = tracker.get('invalid_since', 0)
            ago = int(datetime.now().timestamp() - since) if since else 0
            status_parts.append(f"🚫 INVALID ({ago}s ago)")
            err = tracker.get('invalid_error', 'unknown')
            status_parts.append(f"err: {err[:80]}")
        elif tracker.get('rate_limited', False):
            since = tracker.get('last_limit', 0)
            ago = int(datetime.now().timestamp() - since) if since else 0
            status_parts.append(f"⚠️ RATE LIMITED ({ago}s ago)")
        else:
            status_parts.append("✅ OK")
        reqs = tracker.get('request_count', 0)
        errs = tracker.get('error_count', 0)
        status_parts.append(f"reqs:{reqs} errs:{errs}")
        active = " ← active" if idx == current_token_index else ""
        lines.append(f"  {label}: {' | '.join(status_parts)}{active}")
    logger.info(f"🔑 Token Health Summary:\n" + "\n".join(lines))

# ==================== MONITORING LOOP ====================
async def monitoring_loop(bot_client):
    """Main monitoring loop - checks accounts and sends notifications"""
    global monitoring_cycle_counter
    logger.info(f"🔄 Monitoring started (interval: {ACCOUNT_CHECK_INTERVAL_MIN}-{ACCOUNT_CHECK_INTERVAL_MAX}s per account)")

    base_check_interval = 5
    HEALTH_LOG_INTERVAL = 20  # Log token health every N cycles

    while True:
        try:
            if not monitored_accounts:
                await asyncio.sleep(base_check_interval)
                continue

            monitoring_cycle_counter += 1

            # Periodic token health summary
            if monitoring_cycle_counter % HEALTH_LOG_INTERVAL == 0:
                log_token_health_summary()

            # Get ready accounts
            ready_accounts = []
            for channel_id_str, accounts in monitored_accounts.items():
                for username, settings in accounts.items():
                    if settings.get('muted', False):
                        continue
                    account_key = get_account_key(channel_id_str, username)
                    if is_account_ready_for_check(account_key):
                        ready_accounts.append((channel_id_str, username))

            if not ready_accounts:
                await asyncio.sleep(base_check_interval)
                continue

            if len(TWITTER_TOKENS) > 1:
                await rotate_token_proactively()

            logger.info(f"📋 Cycle #{monitoring_cycle_counter} | {len(ready_accounts)} account(s) ready to check")

            for channel_id_str, username in ready_accounts:
                channel_id = int(channel_id_str)
                account_key = get_account_key(channel_id_str, username)

                await check_account_tweets(username, channel_id, bot_client)
                update_account_check_time(account_key)

                if len(TWITTER_TOKENS) > 1:
                    await rotate_token_proactively()

                await asyncio.sleep(max(get_human_delay(), DELAY_BETWEEN_ACCOUNTS))

            await asyncio.sleep(base_check_interval)

        except Exception as e:
            logger.error(f"Monitoring loop error: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

# ==================== DISCORD BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

@bot.event
async def on_ready():
    logger.info(f"✅ Discord Bot ready! Logged in as {bot.user.tag if hasattr(bot.user, 'tag') else bot.user}")
    logger.info(f"📡 Serving {len(bot.guilds)} guild(s)")
    logger.info(f"🐦 Twitter tokens: {len(TWITTER_TOKENS)}")

    load_data()

    if await authenticate_twitter():
        asyncio.create_task(monitoring_loop(bot))
        logger.info("🔄 Monitoring loop started")
    else:
        logger.warning("⚠️ Running without Twitter auth - monitoring disabled")

@bot.command(name='tweets')
async def cmd_tweets(ctx, username: str = None):
    """Add a Twitter account to monitor in this channel. Usage: .tweets @username"""
    if not username:
        embed = discord.Embed(
            title="❌ Missing Username",
            color=0xFF0000,
            description=(
                "**Usage:** `.tweets @username`\n"
                "**Example:** `.tweets @elonmusk`\n\n"
                "This will monitor the account and send tweet notifications to this channel."
            )
        )
        await ctx.send(embed=embed)
        return

    username = username.replace('@', '').strip().lower()
    if not username:
        await ctx.send("❌ Invalid username")
        return

    channel_id_str = str(ctx.channel.id)

    if channel_id_str not in monitored_accounts:
        monitored_accounts[channel_id_str] = {}

    if username in monitored_accounts[channel_id_str]:
        embed = discord.Embed(
            title="⚠️ Already Monitoring",
            color=0xFFAD1F,
            description=f"**@{username}** is already being monitored in this channel."
        )
        await ctx.send(embed=embed)
        return

    # Send processing message
    processing_embed = discord.Embed(
        title="⏳ Setting up monitoring...",
        color=0x1DA1F2,
        description=f"Fetching account info for **@{username}**...\nPlease wait..."
    )
    processing_msg = await ctx.send(embed=processing_embed)

    # Add account
    result = await add_account_with_retry(username, channel_id_str)

    if result['success']:
        embed = build_account_added_embed(username, result['user_data'])
        await processing_msg.edit(embed=embed)
    else:
        error_msg = result.get('error', 'Unknown error')
        is_rate_limit = result.get('is_rate_limit', False)

        if is_rate_limit:
            embed = discord.Embed(
                title="❌ Rate Limit Exceeded",
                color=0xFF0000,
                description=(
                    f"Could not add **@{username}** due to Twitter API rate limit.\n\n"
                    "**Solution:** Wait 5-10 minutes and try again.\n"
                    "*This is normal when monitoring many accounts.*"
                )
            )
        else:
            embed = discord.Embed(
                title=f"❌ Error Adding @{username}",
                color=0xFF0000,
                description=f"**Error:** {error_msg}\n\nPlease check the username and try again."
            )
        await processing_msg.edit(embed=embed)

@bot.command(name='untweets')
async def cmd_untweets(ctx, username: str = None):
    """Remove a Twitter account from monitoring. Usage: .untweets @username"""
    if not username:
        embed = discord.Embed(
            title="❌ Missing Username",
            color=0xFF0000,
            description=(
                "**Usage:** `.untweets @username`\n"
                "**Example:** `.untweets @elonmusk`\n\n"
                "This will stop monitoring the account in this channel."
            )
        )
        await ctx.send(embed=embed)
        return

    username = username.replace('@', '').strip().lower()
    channel_id_str = str(ctx.channel.id)

    if channel_id_str not in monitored_accounts or username not in monitored_accounts[channel_id_str]:
        embed = discord.Embed(
            title="⚠️ Not Found",
            color=0xFFAD1F,
            description=f"**@{username}** is not being monitored in this channel."
        )
        await ctx.send(embed=embed)
        return

    # Get user data before removing
    account_data = monitored_accounts[channel_id_str][username]
    user_data = account_data.get('user_data', {})
    real_name = user_data.get('real_name', username)

    # Remove
    del monitored_accounts[channel_id_str][username]
    account_key = get_account_key(channel_id_str, username)
    cleanup_account_tracking(account_key)
    save_data()

    remaining = len(monitored_accounts.get(channel_id_str, {}))
    logger.info(f"Removed @{username} from channel {channel_id_str}")

    embed = discord.Embed(
        title="✅ Account Removed",
        color=0xFF6B6B,
        description=(
            f"**{real_name}** (@{username}) has been removed from monitoring.\n\n"
            f"Remaining accounts in this channel: **{remaining}**"
        )
    )
    embed.set_footer(text="Twitter Monitor Bot")
    embed.timestamp = datetime.now(timezone.utc)
    await ctx.send(embed=embed)

@bot.command(name='list')
async def cmd_list(ctx):
    """View all monitored accounts in this channel. Usage: .list"""
    channel_id_str = str(ctx.channel.id)
    embed = build_list_embed(channel_id_str)
    await ctx.send(embed=embed)

@bot.command(name='tweethelp')
async def cmd_tweethelp(ctx):
    """Show help for Twitter monitoring commands"""
    embed = discord.Embed(
        title="❓ Twitter Monitor — Help",
        color=0x1DA1F2,
        description=(
            "Monitor Twitter accounts and get realtime notifications in your Discord channels.\n\n"
            "**Commands:**\n"
            "`.tweets @username` — Add account to monitor\n"
            "`.untweets @username` — Remove from monitoring\n"
            "`.list` — View monitored accounts\n"
            "`.tweethelp` — Show this help\n\n"
            "**Notifications:**\n"
            "✍️ New tweets\n"
            "🐦 Retweets\n"
            "💬 Replies\n\n"
            "**How it works:**\n"
            "When you add an account with `.tweets`, the bot will monitor it and "
            "send notifications **to the channel where you used the command**.\n"
            "Each channel can have its own list of monitored accounts."
        )
    )
    embed.set_footer(text=f"Check interval: {ACCOUNT_CHECK_INTERVAL_MIN}-{ACCOUNT_CHECK_INTERVAL_MAX}s per account")
    embed.timestamp = datetime.now(timezone.utc)
    await ctx.send(embed=embed)

# ==================== MAIN ====================
if __name__ == '__main__':
    if not DISCORD_TOKEN:
        print("[ERROR] DISCORD_TOKEN not set in .env file!")
        exit(1)

    logger.info("🚀 Starting Discord Twitter Monitor Bot...")
    bot.run(DISCORD_TOKEN, log_handler=None)
