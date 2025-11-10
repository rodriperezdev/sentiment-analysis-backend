"""
Enhanced Historical Backfill - Includes Comments for Richer Sentiment Analysis
This collects both posts AND their top comments for more comprehensive analysis.

⚠️ Warning: This takes 3-5x longer than post-only collection due to Reddit API limits.

Usage:
    python backfill_with_comments.py
"""

from dotenv import load_dotenv
load_dotenv()

from reddit_collector import RedditCollector
from database import save_posts, SessionLocal, Post
from datetime import datetime, timedelta
import time

def backfill_with_comments(comments_per_post: int = 10):
    """
    Collect historical posts AND their top comments for richer sentiment data.
    
    Args:
        comments_per_post: Number of top comments to collect per post (default: 10)
    """
    collector = RedditCollector()
    db = SessionLocal()
    
    oldest_post = db.query(Post).order_by(Post.created_utc.asc()).first()
    if oldest_post:
        print(f"📊 Current oldest post: {oldest_post.created_utc}")
    
    db.close()
    
    print("\n" + "="*60)
    print("🔄 ENHANCED BACKFILL - POSTS + COMMENTS")
    print("="*60)
    print(f"Will collect posts AND top {comments_per_post} comments from each post")
    print(f"⚠️  This takes longer but gives MUCH richer sentiment data!\n")
    
    print(f"📍 Monitoring subreddits: {', '.join(['r/'+s for s in collector.subreddits])}\n")
    
    all_collected_items = []  # Both posts and comments
    successful_subreddits = set()
    posts_collected = 0
    comments_collected = 0
    
    time_periods = [
        ('month', 150, 'Top posts from the past month'),
        ('year', 200, 'Top posts from the past year'),
        ('all', 150, 'Top posts of all time')
    ]
    
    for time_filter, limit, description in time_periods:
        print(f"\n📅 {description}")
        print("-" * 60)
        
        for subreddit in collector.subreddits:
            try:
                print(f"  📍 r/{subreddit} ({time_filter})...")
                
                reddit_sub = collector.reddit.subreddit(subreddit)
                post_ids = set()
                checked = 0
                sub_posts = 0
                sub_comments = 0
                
                for submission in reddit_sub.top(time_filter=time_filter, limit=limit):
                    checked += 1
                    
                    if submission.id in post_ids:
                        continue
                    
                    # Filter for political content
                    full_text = f"{submission.title} {submission.selftext}".lower()
                    matches = sum(1 for keyword in collector.political_keywords if keyword in full_text)
                    
                    if matches < 1:
                        continue
                    
                    # Analyze the POST
                    full_text = f"{submission.title} {submission.selftext}"
                    sentiment = collector.analyzer.analyze(full_text)
                    topics = collector.analyzer.extract_topics(full_text)
                    
                    post_data = {
                        'id': submission.id,
                        'subreddit': subreddit,
                        'title': submission.title,
                        'text': submission.selftext,
                        'author': str(submission.author),
                        'score': submission.score,
                        'num_comments': submission.num_comments,
                        'created_utc': datetime.fromtimestamp(submission.created_utc).isoformat(),
                        'url': submission.url,
                        'sentiment': sentiment['sentiment'],
                        'sentiment_score': sentiment['score'],
                        'topics': topics,
                        'source': 'reddit'
                    }
                    
                    all_collected_items.append(post_data)
                    post_ids.add(submission.id)
                    sub_posts += 1
                    
                    # Now collect TOP COMMENTS from this post
                    try:
                        submission.comments.replace_more(limit=0)  # Remove "load more" comments
                        
                        # Get top comments sorted by score
                        top_comments = sorted(
                            submission.comments.list(), 
                            key=lambda c: c.score, 
                            reverse=True
                        )[:comments_per_post]
                        
                        for comment in top_comments:
                            # Skip short or deleted comments
                            if not hasattr(comment, 'body') or len(comment.body) < 20:
                                continue
                            
                            # Check if comment is also political (optional, keeps quality high)
                            comment_lower = comment.body.lower()
                            comment_matches = sum(1 for kw in collector.political_keywords if kw in comment_lower)
                            
                            # Only analyze if comment is political OR post has 2+ matches (context)
                            if comment_matches >= 1 or matches >= 2:
                                comment_sentiment = collector.analyzer.analyze(comment.body)
                                comment_topics = collector.analyzer.extract_topics(comment.body)
                                
                                comment_data = {
                                    'id': f"{submission.id}_{comment.id}",  # Unique ID
                                    'subreddit': subreddit,
                                    'title': f"Comment on: {submission.title[:50]}...",
                                    'text': comment.body,
                                    'author': str(comment.author),
                                    'score': comment.score,
                                    'num_comments': 0,
                                    'created_utc': datetime.fromtimestamp(comment.created_utc).isoformat(),
                                    'url': f"https://reddit.com{comment.permalink}",
                                    'sentiment': comment_sentiment['sentiment'],
                                    'sentiment_score': comment_sentiment['score'],
                                    'topics': comment_topics,
                                    'source': 'reddit_comment'
                                }
                                
                                all_collected_items.append(comment_data)
                                sub_comments += 1
                        
                    except Exception as comment_error:
                        # Don't fail entire collection if comments fail
                        pass
                    
                    # Progress update
                    if sub_posts % 10 == 0:
                        print(f"    ✓ {sub_posts} posts, {sub_comments} comments (checked {checked})...")
                    
                    # Small delay to respect rate limits
                    time.sleep(0.5)
                
                print(f"  ✅ r/{subreddit}: {sub_posts} posts + {sub_comments} comments")
                posts_collected += sub_posts
                comments_collected += sub_comments
                successful_subreddits.add(subreddit)
                
                # Longer delay between subreddits
                time.sleep(2)
                
            except Exception as e:
                print(f"  ❌ Error: {e}")
                print(f"  ⏭️  Skipping r/{subreddit}...")
                continue
    
    # Save everything to database
    print(f"\n💾 Saving {len(all_collected_items)} items to database...")
    save_posts(all_collected_items)
    
    if all_collected_items:
        dates = [datetime.fromisoformat(item['created_utc']) for item in all_collected_items]
        oldest = min(dates)
        newest = max(dates)
        
        print(f"\n📊 ENHANCED BACKFILL COMPLETE!")
        print("="*60)
        print(f"✅ Total items: {len(all_collected_items)}")
        print(f"   📝 Posts: {posts_collected}")
        print(f"   💬 Comments: {comments_collected}")
        print(f"   📊 Ratio: {comments_collected/max(posts_collected,1):.1f} comments per post")
        print(f"📍 Successful subreddits: {', '.join(['r/'+s for s in sorted(successful_subreddits)])}")
        print(f"📅 Date range: {oldest.strftime('%Y-%m-%d')} to {newest.strftime('%Y-%m-%d')}")
        
        days = (newest - oldest).days
        print(f"⏱️  Span: {days} days ({days/365:.1f} years)")
        print(f"📊 Density: {len(all_collected_items)/max(days,1):.2f} items/day")
        
        # Sentiment breakdown
        sentiments = [item['sentiment'] for item in all_collected_items]
        pos = sentiments.count('positive')
        neg = sentiments.count('negative')
        neu = sentiments.count('neutral')
        
        print(f"\n📈 Overall Sentiment:")
        print(f"   😊 Positive: {pos} ({pos/len(all_collected_items)*100:.1f}%)")
        print(f"   😠 Negative: {neg} ({neg/len(all_collected_items)*100:.1f}%)")
        print(f"   😐 Neutral: {neu} ({neu/len(all_collected_items)*100:.1f}%)")
        
        print(f"\n✨ Your dashboard now has MUCH richer sentiment data!")
        print(f"   Comments often reveal more nuanced opinions than posts!\n")
    else:
        print("\n⚠️  No items collected.\n")

if __name__ == "__main__":
    print("\n🚀 Enhanced Historical Backfill - Posts + Comments")
    print("\n⚠️  Important Notes:")
    print("   - This collects BOTH posts and their top comments")
    print("   - Takes 3-5x longer than post-only collection")
    print("   - Provides much richer sentiment analysis")
    print("   - Respects Reddit API rate limits\n")
    
    response = input("Start enhanced backfill? (10-20 minutes) (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        comments_per_post = 10  # Collect top 10 comments per post
        print(f"\nCollecting top {comments_per_post} comments per post...\n")
        
        start = time.time()
        backfill_with_comments(comments_per_post)
        elapsed = (time.time() - start) / 60
        print(f"⏱️  Total time: {elapsed:.1f} minutes")
    else:
        print("Cancelled.")






