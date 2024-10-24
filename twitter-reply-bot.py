import tweepy
from datetime import datetime, timedelta
import schedule
import time
import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Load your Twitter and Groq API keys
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_ENDPOINT = os.getenv("GROQ_API_ENDPOINT")

# TwitterBot class to help us organize our code and manage shared state
class TwitterBot:
    def __init__(self):
        self.twitter_api = tweepy.Client(
            bearer_token=TWITTER_BEARER_TOKEN,
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
            wait_on_rate_limit=True
        )
        self.twitter_me_id = self.get_me_id()
        self.tweet_response_limit = 35  # How many tweets to respond to each time the program wakes up
        self.mentions_found = 0
        self.mentions_replied = 0
        self.mentions_replied_errors = 0

    # Generate a response using the Groq API
    def generate_response(self, mentioned_conversation_tweet_text):
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "llama3-8b-8192",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an incredibly wise and smart tech mad scientist from Silicon Valley. "
                        "Your goal is to give a concise prediction in response to a piece of text from the user. "
                        "Your response should be serious with a hint of wit and sarcasm, in two or fewer sentences."
                    )
                },
                {
                    "role": "user",
                    "content": mentioned_conversation_tweet_text
                }
            ]
        }

        response = requests.post(GROQ_API_ENDPOINT, headers=headers, json=data)
        response_json = response.json()
        return response_json.get("choices", [{}])[0].get("message", {}).get("content", "")

    def respond_to_mention(self, mention, mentioned_conversation_tweet):
        response_text = self.generate_response(mentioned_conversation_tweet.text)
        try:
            response_tweet = self.twitter_api.create_tweet(
                text=response_text, in_reply_to_tweet_id=mention.id
            )
            self.mentions_replied += 1
            # Log the response details to a text file for debugging
            with open("responses_log.txt", "a") as log_file:
                log_file.write(
                    f"{datetime.utcnow().isoformat()} - Responded to tweet ID: {mention.id} "
                    f"with text: {response_text}\n"
                )
        except Exception as e:
            with open("responses_log.txt", "a") as log_file:
                log_file.write(
                    f"{datetime.utcnow().isoformat()} - Error replying to tweet ID: {mention.id}: {e}\n"
                )
            self.mentions_replied_errors += 1
            return

    def get_me_id(self):
        return self.twitter_api.get_me()[0].id

    def get_mention_conversation_tweet(self, mention):
        if mention.conversation_id is not None:
            conversation_tweet = self.twitter_api.get_tweet(mention.conversation_id).data
            return conversation_tweet
        return None

    def get_mentions(self):
        now = datetime.utcnow()
        start_time = now - timedelta(minutes=20)
        start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.twitter_api.get_users_mentions(
            id=self.twitter_me_id,
            start_time=start_time_str,
            expansions=['referenced_tweets.id'],
            tweet_fields=['created_at', 'conversation_id']
        ).data

    def respond_to_mentions(self):
        mentions = self.get_mentions()

        if not mentions:
            print("No mentions found")
            return

        self.mentions_found = len(mentions)

        for mention in mentions[:self.tweet_response_limit]:
            mentioned_conversation_tweet = self.get_mention_conversation_tweet(mention)
            if (
                mentioned_conversation_tweet.id != mention.id
                and not self.check_already_responded(mentioned_conversation_tweet.id)
            ):
                self.respond_to_mention(mention, mentioned_conversation_tweet)
        return True

    def execute_replies(self):
        with open("responses_log.txt", "a") as log_file:
            log_file.write(f"Starting Job: {datetime.utcnow().isoformat()}\n")
        self.respond_to_mentions()
        with open("responses_log.txt", "a") as log_file:
            log_file.write(
                f"Finished Job: {datetime.utcnow().isoformat()}, Found: {self.mentions_found}, "
                f"Replied: {self.mentions_replied}, Errors: {self.mentions_replied_errors}\n"
            )


def job():
    print(f"Job executed at {datetime.utcnow().isoformat()}")
    bot = TwitterBot()
    bot.execute_replies()


if __name__ == "__main__":
    schedule.every(6).minutes.do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)
