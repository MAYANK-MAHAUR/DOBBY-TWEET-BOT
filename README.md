# 🐦 Dobby Tweet Bot

A Discord bot that monitors a specific Twitter account and posts new tweets to a designated Discord channel. It uses the **Sentient** Dobby model to generate witty, bolded summaries of each tweet.

## ✨ Features

- **Twitter Integration**: Monitors a specified Twitter account for new tweets.
- **AI-Powered Summaries**: Utilizes the Sentient API and Dobby (a Llama 3.1-70B model) to create concise and engaging summaries.
- **Persistent State**: Remembers the last tweet it saw, so you don't miss anything even if the bot restarts.
- **Rate Limit Handling**: Gracefully handles Twitter API rate limits by pausing and retrying.
- **Rich Discord Embeds**: Posts tweets as beautiful Discord embeds, complete with a clickable summary and a native tweet preview.

## ⚙️ Setup & Installation

### 1. Clone the Repository
```bash
git clone 
cd dobby-tweet-bot