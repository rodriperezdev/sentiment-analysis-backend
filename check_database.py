"""
Quick script to check what data is currently in your database
"""

from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal, Post
from datetime import datetime
from collections import Counter

def check_database():
    db = SessionLocal()
    
    print("\n" + "="*60)
    print("DATABASE OVERVIEW")
    print("="*60)
    
    # Total posts
    total_posts = db.query(Post).count()
    print(f"\n[OK] Total posts in database: {total_posts}")
    
    if total_posts == 0:
        print("\n[WARNING] Database is empty!")
        print("   Run 'python backfill_historical_data.py' to populate it.")
        db.close()
        return
    
    # Date range
    oldest = db.query(Post).order_by(Post.created_utc.asc()).first()
    newest = db.query(Post).order_by(Post.created_utc.desc()).first()
    
    print(f"\nDate Range:")
    print(f"   Oldest: {oldest.created_utc.strftime('%Y-%m-%d %H:%M')}")
    print(f"   Newest: {newest.created_utc.strftime('%Y-%m-%d %H:%M')}")
    
    days_span = (newest.created_utc - oldest.created_utc).days
    print(f"   Span: {days_span} days ({days_span/365:.1f} years)")
    
    # Post density
    avg_per_day = total_posts / max(days_span, 1)
    print(f"\nPost Density: {avg_per_day:.2f} posts/day")
    
    if avg_per_day < 0.5:
        print(f"   [WARNING] Low density - yearly chart may have gaps")
        print(f"   [NOTE] Run backfill script to add more historical data")
    elif avg_per_day < 1:
        print(f"   [WARNING] Moderate density - yearly chart will work but be sparse")
    else:
        print(f"   [OK] Good density for yearly analysis!")
    
    # Sentiment breakdown
    all_posts = db.query(Post).all()
    sentiments = [p.sentiment for p in all_posts]
    
    positive = sentiments.count('positive')
    negative = sentiments.count('negative')
    neutral = sentiments.count('neutral')
    
    print(f"\nSentiment Distribution:")
    print(f"   Positive: {positive} ({positive/total_posts*100:.1f}%)")
    print(f"   Negative: {negative} ({negative/total_posts*100:.1f}%)")
    print(f"   Neutral: {neutral} ({neutral/total_posts*100:.1f}%)")
    
    # Subreddit breakdown
    subreddits = [p.subreddit for p in all_posts]
    subreddit_counts = Counter(subreddits)
    
    print(f"\nPosts by Subreddit:")
    for sub, count in subreddit_counts.most_common():
        print(f"   r/{sub}: {count} posts ({count/total_posts*100:.1f}%)")
    
    # Posts per month (for recent data)
    from datetime import datetime, timedelta
    
    now = datetime.now()
    one_month_ago = now - timedelta(days=30)
    recent_posts = db.query(Post).filter(Post.created_utc >= one_month_ago).count()
    
    print(f"\nRecent Activity:")
    print(f"   Last 30 days: {recent_posts} posts")
    
    # Check for data gaps
    print(f"\nData Quality Check:")
    
    # Check if we have data for different time periods
    one_week_ago = now - timedelta(days=7)
    six_months_ago = now - timedelta(days=180)
    one_year_ago = now - timedelta(days=365)
    
    posts_last_week = db.query(Post).filter(Post.created_utc >= one_week_ago).count()
    posts_last_6m = db.query(Post).filter(Post.created_utc >= six_months_ago).count()
    posts_last_year = db.query(Post).filter(Post.created_utc >= one_year_ago).count()
    
    print(f"   Last 7 days: {posts_last_week} posts " + ("[OK]" if posts_last_week >= 10 else "[WARNING] (need more)"))
    print(f"   Last 6 months: {posts_last_6m} posts " + ("[OK]" if posts_last_6m >= 100 else "[WARNING] (need more)"))
    print(f"   Last year: {posts_last_year} posts " + ("[OK]" if posts_last_year >= 200 else "[WARNING] (need more)"))
    
    print(f"\n[NOTE] Recommendations:")
    if total_posts < 200:
        print(f"   - Run backfill script to collect more historical data")
    if avg_per_day < 1:
        print(f"   - Post density is low; consider more frequent collection")
    if posts_last_week < 10:
        print(f"   - Recent data is sparse; run refresh button or backfill")
    if posts_last_year < 200:
        print(f"   - Not enough data for yearly analysis; run backfill")
    
    if total_posts >= 200 and avg_per_day >= 1 and posts_last_year >= 200:
        print(f"   [OK] Your database looks good for all time ranges!")
    
    print("\n" + "="*60 + "\n")
    
    db.close()

if __name__ == "__main__":
    check_database()







