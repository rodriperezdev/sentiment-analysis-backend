"""
Quick test to see if we can save to the database
"""

from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal, Post, init_db
from datetime import datetime

def test_save():
    # Initialize database
    init_db()
    
    db = SessionLocal()
    
    try:
        # Try to save a test post
        test_post = Post(
            id='test_123',
            subreddit='test',
            title='Test Post',
            text='Testing database',
            author='test_user',
            score=1,
            num_comments=0,
            created_utc=datetime.now(),
            url='https://reddit.com/test',
            sentiment='neutral',
            sentiment_score=0.0,
            topics=[],
            source='test'
        )
        
        db.add(test_post)
        db.commit()
        
        # Check if it saved
        saved = db.query(Post).filter(Post.id == 'test_123').first()
        
        if saved:
            print("✅ Database write test: SUCCESS")
            print(f"   Saved test post: {saved.title}")
            
            # Clean up test post
            db.delete(saved)
            db.commit()
            print("✅ Cleaned up test post")
        else:
            print("❌ Database write test: FAILED - Post not found after save")
        
    except Exception as e:
        print(f"❌ Database write test: FAILED")
        print(f"   Error: {e}")
        db.rollback()
    
    finally:
        db.close()

if __name__ == "__main__":
    print("\n🧪 Testing database write capability...\n")
    test_save()
    print()






