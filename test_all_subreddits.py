from reddit_collector import RedditCollector
from database import save_posts
import os
from dotenv import load_dotenv

load_dotenv()

print("=== Testing ALL Subreddits ===\n")

collector = RedditCollector()

# This will check ALL 4 subreddits in the list
posts = collector.collect_all_subreddits(limit_per_sub=30)

print(f"\n{'='*60}")
print(f"TOTAL COLLECTED: {len(posts)} posts")
print(f"{'='*60}")

if posts:
    # Show breakdown by subreddit
    from collections import Counter
    subreddit_counts = Counter(p['subreddit'] for p in posts)
    
    print("\nBreakdown by subreddit:")
    for sub, count in subreddit_counts.items():
        print(f"  r/{sub}: {count} posts")
    
    # Show sentiment breakdown
    sentiment_counts = Counter(p['sentiment'] for p in posts)
    print("\nSentiment breakdown:")
    for sent, count in sentiment_counts.items():
        print(f"  {sent}: {count} posts")
    
    # Show sample posts
    print(f"\nSample posts (first 5):")
    for i, post in enumerate(posts[:5], 1):
        print(f"\n{i}. [{post['subreddit']}] {post['title'][:70]}")
        print(f"   Sentiment: {post['sentiment']} ({post['sentiment_score']:.2f})")
        print(f"   Topics: {', '.join(post['topics'][:3]) if post['topics'] else 'None'}")
    
    # Save to database
    save_posts(posts)
    print(f"\n[OK] Saved {len(posts)} posts to database!")
else:
    print("\n[WARNING] No posts collected from any subreddit")
    print("\nThis could mean:")
    print("  1. Very quiet day politically")
    print("  2. Keywords might be too restrictive")
    print("  3. Subreddits might be private/restricted")