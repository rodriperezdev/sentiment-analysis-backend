"""
DEBUG version of backfill - shows exactly what's happening
"""

from dotenv import load_dotenv
load_dotenv()

from reddit_collector import RedditCollector
from database import save_posts, SessionLocal, Post, init_db
from datetime import datetime
import time

def debug_backfill():
    print("\n" + "="*60)
    print("🐛 DEBUG BACKFILL")
    print("="*60)
    
    # Step 1: Initialize database
    print("\n1️⃣ Initializing database...")
    init_db()
    print("   ✅ Database initialized")
    
    # Step 2: Check current count
    db = SessionLocal()
    current_count = db.query(Post).count()
    db.close()
    print(f"\n2️⃣ Current posts in database: {current_count}")
    
    # Step 3: Initialize collector
    print("\n3️⃣ Initializing Reddit collector...")
    collector = RedditCollector()
    print(f"   ✅ Monitoring: {', '.join(['r/'+s for s in collector.subreddits])}")
    print(f"   ✅ Political keywords: {len(collector.political_keywords)} keywords")
    
    # Step 4: Try to collect just from ONE subreddit
    print("\n4️⃣ Testing collection from r/argentina (top 50 from month)...")
    try:
        reddit_sub = collector.reddit.subreddit('argentina')
        test_items = []
        checked = 0
        
        for submission in reddit_sub.top(time_filter='month', limit=50):
            checked += 1
            
            # Check if political
            full_text = f"{submission.title} {submission.selftext}".lower()
            matches = sum(1 for kw in collector.political_keywords if kw in full_text)
            
            if matches >= 1:
                # Just save post info (no comments for this test)
                sentiment = collector.analyzer.analyze(f"{submission.title} {submission.selftext}")
                
                test_items.append({
                    'id': submission.id,
                    'subreddit': 'argentina',
                    'title': submission.title,
                    'text': submission.selftext,
                    'author': str(submission.author),
                    'score': submission.score,
                    'num_comments': submission.num_comments,
                    'created_utc': datetime.fromtimestamp(submission.created_utc).isoformat(),
                    'url': submission.url,
                    'sentiment': sentiment['sentiment'],
                    'sentiment_score': sentiment['score'],
                    'topics': [],
                    'source': 'reddit'
                })
                
                print(f"   ✓ Found political post: {submission.title[:50]}...")
        
        print(f"\n   ✅ Checked {checked} posts, found {len(test_items)} political posts")
        
        if len(test_items) == 0:
            print("\n❌ NO POLITICAL POSTS FOUND!")
            print("   The filter might be too strict or subreddit has no political content.")
            return
        
        # Step 5: Try to save them
        print(f"\n5️⃣ Attempting to save {len(test_items)} posts to database...")
        
        try:
            save_posts(test_items)
            print("   ✅ Save function completed")
        except Exception as save_error:
            print(f"   ❌ Save failed: {save_error}")
            return
        
        # Step 6: Verify they're actually in the database
        print(f"\n6️⃣ Verifying posts were saved...")
        db = SessionLocal()
        new_count = db.query(Post).count()
        
        # Try to find one of the posts we just saved
        first_post_id = test_items[0]['id']
        found_post = db.query(Post).filter(Post.id == first_post_id).first()
        
        db.close()
        
        print(f"   Database count: {current_count} → {new_count}")
        print(f"   Expected increase: {len(test_items)}")
        print(f"   Actual increase: {new_count - current_count}")
        
        if found_post:
            print(f"   ✅ Found test post in database: {found_post.title[:50]}...")
        else:
            print(f"   ❌ Test post NOT found in database!")
            print(f"   Looking for ID: {first_post_id}")
        
        if new_count > current_count:
            print(f"\n✅ SUCCESS! Database was updated.")
            print(f"   You can now run the full backfill.")
        else:
            print(f"\n❌ PROBLEM! Database was NOT updated.")
            print(f"   Posts were collected but not saved to database.")
            
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_backfill()
    print("\n" + "="*60 + "\n")



