# 🐦 Dobby Tweet Bot

A Discord bot that monitors a specific Twitter account and posts new tweets to a designated Discord channel. It uses the Sentient API with the Dobby model to generate witty, bolded summaries of each tweet.

## ✨ Features

* **Twitter Integration**: Monitors a specified Twitter account for new tweets.
* **AI-Powered Summaries**: Utilizes the  **SENTIENT Dobby** (a Llama 3.1-8B model) to create concise and engaging summaries.
* **Persistent State**: Remembers the last tweet it saw, so you don't miss anything even if the bot restarts.
* **Rate Limit Handling**: Gracefully handles Twitter API rate limits by pausing and retrying.
* **Rich Discord Embeds**: Posts tweets as beautiful Discord embeds, complete with a clickable summary and a native tweet preview.

***

## ⚙️ Setup & Installation

### 1. Clone the Repository

```bash
git clone https://github.com/MAYANK-MAHAUR/DOBBY-TWEET-BOT.git
cd dobby-tweet-bot
```

### 2. Set up Environment Variables

Create a file named `.env` in the root directory and fill it with your credentials. You can use the provided `.env.example` as a guide.

```ini
# Example .env file
DISCORD_TOKEN="..."
DISCORD_CHANNEL_ID="..."
TWITTER_BEARER_TOKEN="..."
TWITTER_USERNAME="..."
API_KEY="..."
```

### 3. Install Dependencies

Make sure you have Python 3.8+ installed, then install the required packages.

```bash
pip install -r requirements.txt
```


### 4. Run the Bot

```bash
python main.py
```

***

## 🤖 How It Works

The bot uses a **task loop** to periodically check for new tweets from the specified user. When a new tweet is found, the bot:

1.  **Feeds the tweet's text to the Dobby via API.**
2.  **The Dobby (Llama 3.1-8B) model**, generates a creative, one-sentence summary.
3.  **Constructs a rich Discord embed** with the AI-generated summary.
4.  **Posts two messages to Discord**:
    * The first message is the custom embed.
    * The second message is the raw tweet link, which Discord automatically embeds for a native look.
5.  **Saves the ID of the latest tweet** to a file (`tweet_tracker_state.json`) to remember its progress.

This setup ensures that every new tweet is instantly and intelligently summarized for your Discord community.

***

## 🤝 Contributing

Feel free to open issues or submit pull requests if you have suggestions for new features or bug fixes.
