import os
import asyncio
import json
import logging
import aiohttp
import aiofiles
from discord.ext import commands, tasks
import tweepy
import discord
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()

# --- Logging Setup ---
# Sets up logging to show timestamps, log level, and message.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- Constants ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
TWITTER_USERNAME = os.getenv("TWITTER_USERNAME")
SENTIENT_API_KEY = os.getenv("SENTIENT_API_KEY")
DOBBY_MODEL = os.getenv("DOBBY_MODEL", "accounts/fireworks/models/llama-v3p1-8b-instruct") # Sensible default
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL", 300)) # Default 5 minutes

STATE_FILE = "tweet_tracker_state.json"
FIREWORKS_API_URL = "https://api.fireworks.ai/inference/v1/chat/completions"

# --- Main Bot Class ---
class TwitterBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        # Create a single session for all HTTP requests to reuse connections
        self.http_session = None

    async def setup_hook(self):
        """This is called once the bot is ready, before on_ready."""
        self.http_session = aiohttp.ClientSession()
        await self.add_cog(TwitterCog(self))

    async def on_ready(self):
        logging.info(f"✅ Logged in as {self.user}")

# --- Bot Logic Cog ---
class TwitterCog(commands.Cog):
    def __init__(self, bot: TwitterBot):
        self.bot = bot
        self.twitter_client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN)
        self.twitter_user_id = None
        self.last_tweet_id = None

    async def cog_load(self):
        """Async setup for the cog with retry logic for fetching the user ID."""
        max_retries = 4
        for attempt in range(max_retries):
            self.twitter_user_id = await self._get_twitter_user_id()
            if self.twitter_user_id:
                # Success!
                self.last_tweet_id = await self._load_last_tweet_id()
                logging.info(f"📌 Watching @{TWITTER_USERNAME} for new tweets. Last seen ID: {self.last_tweet_id}")
                self.check_tweets.start()
                return # Exit the function on success

            # Failure, wait and retry
            wait_time = 2 ** attempt * 60  # Wait for 1, 2, 4, 8 minutes
            logging.warning(f"Attempt {attempt + 1}/{max_retries} failed to get Twitter user ID. Retrying in {wait_time // 60} minute(s)...")
            await asyncio.sleep(wait_time)

        # If all retries fail
        logging.error(f"🚨 Halting operations: Could not find Twitter user ID for {TWITTER_USERNAME} after {max_retries} attempts.")
        # Gracefully close the session before exiting
        if self.bot.http_session and not self.bot.http_session.closed:
            await self.bot.http_session.close()
        await self.bot.close() # Stop the bot if the target user isn't found

    async def cog_unload(self):
        """Cleanup when the cog is unloaded."""
        await self.bot.http_session.close() # Close the aiohttp session
        self.check_tweets.cancel()

    async def _get_twitter_user_id(self):
        """Fetches the Twitter user ID from a username once on startup."""
        try:
            user_resp = await self.bot.loop.run_in_executor(
                None, lambda: self.twitter_client.get_user(username=TWITTER_USERNAME)
            )
            if user_resp.data:
                return user_resp.data.id
        except Exception as e:
            logging.error(f"Failed to fetch Twitter user ID: {e}")
        return None

    async def _load_last_tweet_id(self):
        """Asynchronously loads the last seen tweet ID from a file."""
        if not os.path.exists(STATE_FILE):
            return None
        try:
            async with aiofiles.open(STATE_FILE, "r") as f:
                content = await f.read()
                data = json.loads(content)
                return data.get("last_tweet_id")
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Error loading state from {STATE_FILE}: {e}")
            return None

    async def _save_last_tweet_id(self, tweet_id: int):
        """Asynchronously saves the last seen tweet ID to a file."""
        try:
            async with aiofiles.open(STATE_FILE, "w") as f:
                await f.write(json.dumps({"last_tweet_id": tweet_id}))
            self.last_tweet_id = tweet_id
        except IOError as e:
            logging.error(f"Error saving state to {STATE_FILE}: {e}")

    async def _summarize_tweet(self, text: str):
        """Asynchronously summarizes a tweet using the Fireworks AI API."""
        headers = {
            "Authorization": f"Bearer {SENTIENT_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": DOBBY_MODEL,
            "messages": [
                {"role": "user", "content": f"Summarize this tweet in one witty, bolded sentence and format it:\n\n{text}"}
            ],
            "max_tokens": 80,
            "temperature": 0.6,
        }
        try:
            async with self.bot.http_session.post(FIREWORKS_API_URL, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    logging.error(f"Fireworks API error {response.status}: {await response.text()}")
                    return None
        except aiohttp.ClientError as e:
            logging.error(f"HTTP request to summarizer failed: {e}")
            return None

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def check_tweets(self):
        """The main task loop to check for and post new tweets."""
        channel = self.bot.get_channel(DISCORD_CHANNEL_ID)
        if not channel:
            logging.warning("Discord channel not found. Skipping check.")
            return

        try:
            tweets_resp = await self.bot.loop.run_in_executor(
                None,
                lambda: self.twitter_client.get_users_tweets(
                    id=self.twitter_user_id,
                    since_id=self.last_tweet_id,
                    max_results=5,
                    tweet_fields=["created_at", "text", "id"],
                    exclude=["retweets", "replies"]
                )
            )
            new_tweets = sorted(tweets_resp.data, key=lambda t: t.id) if tweets_resp.data else []
        except tweepy.errors.TooManyRequests:
            logging.warning("Twitter rate limit hit. Pausing for 15 minutes.")
            self.check_tweets.change_interval(minutes=15)
            await asyncio.sleep(1) # a small sleep to allow interval change
            self.check_tweets.change_interval(seconds=CHECK_INTERVAL_SECONDS)
            return
        except Exception as e:
            logging.error(f"An unexpected error occurred fetching tweets: {e}")
            return

        if not new_tweets:
            logging.info("No new tweets found.")
            return

        logging.info(f"Found {len(new_tweets)} new tweet(s).")
        for tweet in new_tweets:
            summary = await self._summarize_tweet(tweet.text)
            
            # --- MODIFIED SECTION ---
            # Construct the Discord message embed
            embed = discord.Embed(
                description=summary or tweet.text,
                color=discord.Color.blue()
            )
            
            # Create the full URL for the tweet
            tweet_url = f"https://twitter.com/{TWITTER_USERNAME}/status/{tweet.id}"

            embed.set_author(
                name=f"New Tweet from @{TWITTER_USERNAME}",
                url=tweet_url,  # The link in the author name is still good to have
                icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png" # Twitter Icon
            )
            embed.set_footer(text="Powered by Sentient & Dobby")
            
            # 1. Send the custom embed first
            await channel.send(embed=embed)
            
            # 2. Then, send the raw tweet URL as a second message
            # This will create Discord's native embed for the tweet below the first message.
            await channel.send(tweet_url)

            # --- END OF MODIFIED SECTION ---
            
            await self._save_last_tweet_id(tweet.id)
            await asyncio.sleep(1) # Small delay to avoid Discord rate limits

# ... (rest of the code is the same) ...
# --- Run Bot ---
if __name__ == "__main__":
    if not all([DISCORD_TOKEN, TWITTER_BEARER_TOKEN, SENTIENT_API_KEY, TWITTER_USERNAME]):
        logging.critical("🚨 Missing one or more critical environment variables. Exiting.")
    else:
        bot = TwitterBot()
        bot.run(DISCORD_TOKEN)