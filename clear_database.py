"""
Clear Database Script
Use this to start fresh before running enhanced backfill.

⚠️  WARNING: This deletes ALL posts and comments from the database!

Usage:
    python clear_database.py
"""

from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal, Post, DailySummary, Topic
from datetime import datetime

def clear_database():
    """Clear all data from the database"""
    db = SessionLocal()
    
    try:
        # Count current data
        posts_count = db.query(Post).count()
        summaries_count = db.query(DailySummary).count()
        topics_count = db.query(Topic).count()
        
        print("\n" + "="*60)
        print("🗑️  DATABASE CLEAR")
        print("="*60)
        print(f"\nCurrent database contents:")
        print(f"  📝 Posts/Comments: {posts_count}")
        print(f"  📊 Daily Summaries: {summaries_count}")
        print(f"  🔥 Topics: {topics_count}")
        
        if posts_count == 0:
            print("\n✅ Database is already empty!")
            return
        
        print(f"\n⚠️  WARNING: This will DELETE ALL {posts_count} posts/comments!")
        print("   You'll need to run the backfill script again.\n")
        
        confirm = input("Type 'DELETE' to confirm: ")
        
        if confirm != 'DELETE':
            print("\n❌ Cancelled. No data was deleted.")
            return
        
        print("\n🗑️  Deleting data...")
        
        # Delete all data
        deleted_posts = db.query(Post).delete()
        deleted_summaries = db.query(DailySummary).delete()
        deleted_topics = db.query(Topic).delete()
        
        db.commit()
        
        print(f"\n✅ Database cleared successfully!")
        print(f"   Deleted {deleted_posts} posts/comments")
        print(f"   Deleted {deleted_summaries} daily summaries")
        print(f"   Deleted {deleted_topics} topic entries")
        print(f"\n💡 Now run: python backfill_with_comments.py")
        print(f"   to repopulate with posts + comments\n")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ Error clearing database: {e}")
    
    finally:
        db.close()

if __name__ == "__main__":
    clear_database()




