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

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
TWITTER_USERNAME = os.getenv("TWITTER_USERNAME")
API_KEY = os.getenv("API_KEY")
DOBBY_MODEL = os.getenv("DOBBY_MODEL") 
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL", 900)) 

STATE_FILE = "tweet_tracker_state.json"
FIREWORKS_API_URL = "https://api.fireworks.ai/inference/v1/chat/completions"

class TwitterBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.http_session = None

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        await self.add_cog(TwitterCog(self))

    async def on_ready(self):
        logging.info(f"✅ Logged in as {self.user}")

class TwitterCog(commands.Cog):
    def __init__(self, bot: TwitterBot):
        self.bot = bot
        self.twitter_client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN)
        self.twitter_user_id = None
        self.last_tweet_id = None

    async def cog_load(self):
        max_retries = 4
        for attempt in range(max_retries):
            self.twitter_user_id = await self.get_twitter_user_id()
            if self.twitter_user_id:
                self.last_tweet_id = await self.load_last_tweet_id()
                logging.info(f"📌 Watching @{TWITTER_USERNAME} for new tweets. Last seen ID: {self.last_tweet_id}")
                self.check_tweets.start()
                return 
            wait_time = 2 ** attempt * 60  
            logging.warning(f"Attempt {attempt + 1}/{max_retries} failed to get Twitter user ID. Retrying in {wait_time // 60} minute(s)...")
            await asyncio.sleep(wait_time)
        logging.error(f"🚨 Halting operations: Could not find Twitter user ID for {TWITTER_USERNAME} after {max_retries} attempts.")
        if self.bot.http_session and not self.bot.http_session.closed:
            await self.bot.http_session.close()
        await self.bot.close() 

    async def cog_unload(self):
        await self.bot.http_session.close() 
        self.check_tweets.cancel()

    async def get_twitter_user_id(self):
        user_resp = await self.bot.loop.run_in_executor(
            None, lambda: self.twitter_client.get_user(username=TWITTER_USERNAME)
        )
        if user_resp.data:
            return user_resp.data.id
        return None

    async def load_last_tweet_id(self):
        if not os.path.exists(STATE_FILE):
            return None
        async with aiofiles.open(STATE_FILE, "r") as f:
            content = await f.read()
            data = json.loads(content)
            return data.get("last_tweet_id")

    async def save_last_tweet_id(self, tweet_id: int):
        async with aiofiles.open(STATE_FILE, "w") as f:
            await f.write(json.dumps({"last_tweet_id": tweet_id}))
        self.last_tweet_id = tweet_id

    async def summarize_tweet(self, text: str):
        headers = {
            "Authorization": f"Bearer {API_KEY}",
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
        async with self.bot.http_session.post(FIREWORKS_API_URL, json=payload, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data["choices"][0]["message"]["content"].strip()
            else:
                return None
            
    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def check_tweets(self):
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
            logging.warning(
                "Twitter API rate limit hit (429 Too Many Requests). "
                "Pausing the task for 15 minutes before retrying."
            )
            self.check_tweets.change_interval(minutes=15)
            return
        except Exception as e:
            logging.error(f"An unexpected error occurred fetching tweets: {e}")
            return
        
        if not new_tweets:
            logging.info("No new tweets found.")
            return

        logging.info(f"Found {len(new_tweets)} new tweet(s).")
        for tweet in new_tweets:
            summary = await self.summarize_tweet(tweet.text)
            
            
            embed = discord.Embed(
                description=summary or tweet.text,
                color=discord.Color.blue()
            )
            
            
            tweet_url = f"https://twitter.com/{TWITTER_USERNAME}/status/{tweet.id}"

            embed.set_author(
                name=f"New Tweet from @{TWITTER_USERNAME}",
                url=tweet_url,
                icon_url="https://abs.twimg.com/icons/apple-touch-icon-192x192.png"
            )
            embed.set_footer(text="Powered by Fireworks AI & Dobby")
            
            await channel.send(embed=embed)
            await channel.send(f"@everyone {tweet_url}")

            await self.save_last_tweet_id(tweet.id)
            await asyncio.sleep(1)

if __name__ == "__main__":
    if not all([DISCORD_TOKEN, TWITTER_BEARER_TOKEN, API_KEY, TWITTER_USERNAME]):
        logging.critical("Missing one or more critical environment variables. Exiting.")
    else:
        bot = TwitterBot()

bot.run(DISCORD_TOKEN)