from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

# Database URL (use SQLite for simplicity, can switch to PostgreSQL later)
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./sentiment.db')

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if 'sqlite' in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class Post(Base):
    """Store analyzed posts from Reddit"""
    __tablename__ = "posts"
    
    id = Column(String, primary_key=True, index=True)
    subreddit = Column(String, index=True)
    title = Column(String)
    text = Column(Text)
    author = Column(String)
    score = Column(Integer)
    num_comments = Column(Integer)
    created_utc = Column(DateTime, index=True)
    url = Column(String)
    
    # Sentiment analysis results
    sentiment = Column(String, index=True)  # positive, negative, neutral
    sentiment_score = Column(Float)
    sentiment_positive = Column(Float)
    sentiment_negative = Column(Float)
    sentiment_neutral = Column(Float)
    
    # Topics
    topics = Column(JSON)  # List of extracted topics
    
    # Metadata
    source = Column(String, default='reddit')
    analyzed_at = Column(DateTime, default=datetime.utcnow)
    

class Comment(Base):
    """Store analyzed comments"""
    __tablename__ = "comments"
    
    id = Column(String, primary_key=True, index=True)
    post_id = Column(String, index=True)
    text = Column(Text)
    author = Column(String)
    score = Column(Integer)
    created_utc = Column(DateTime, index=True)
    
    # Sentiment analysis results
    sentiment = Column(String, index=True)
    sentiment_score = Column(Float)
    
    # Topics
    topics = Column(JSON)
    
    # Metadata
    source = Column(String, default='reddit_comment')
    analyzed_at = Column(DateTime, default=datetime.utcnow)


class DailySummary(Base):
    """Daily aggregated sentiment statistics"""
    __tablename__ = "daily_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, unique=True, index=True)
    
    total_posts = Column(Integer)
    positive_count = Column(Integer)
    negative_count = Column(Integer)
    neutral_count = Column(Integer)
    
    positive_pct = Column(Float)
    negative_pct = Column(Float)
    neutral_pct = Column(Float)
    
    avg_sentiment_score = Column(Float)
    
    # Top topics of the day
    top_topics = Column(JSON)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class Topic(Base):
    """Track topic mentions and sentiment over time"""
    __tablename__ = "topics"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    date = Column(DateTime, index=True)
    
    mention_count = Column(Integer)
    avg_sentiment = Column(Float)
    positive_mentions = Column(Integer)
    negative_mentions = Column(Integer)
    neutral_mentions = Column(Integer)
    
    created_at = Column(DateTime, default=datetime.utcnow)


# Database functions
def get_db():
    """Dependency for FastAPI to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables"""
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully!")


def save_posts(posts_data: list):
    """Save analyzed posts to database"""
    db = SessionLocal()
    
    try:
        saved_count = 0
        skipped_count = 0
        seen_ids = set()  # Track IDs in current batch to avoid duplicates
        
        for post_data in posts_data:
            post_id = post_data['id']
            
            # Skip if we've already seen this ID in the current batch
            if post_id in seen_ids:
                skipped_count += 1
                continue
            
            # Check if post already exists in database
            existing = db.query(Post).filter(Post.id == post_id).first()
            if existing:
                skipped_count += 1
                continue
            
            seen_ids.add(post_id)  # Mark as seen
            
            post = Post(
                id=post_data['id'],
                subreddit=post_data['subreddit'],
                title=post_data['title'],
                text=post_data['text'],
                author=post_data['author'],
                score=post_data['score'],
                num_comments=post_data['num_comments'],
                created_utc=datetime.fromisoformat(post_data['created_utc']),
                url=post_data['url'],
                sentiment=post_data['sentiment'],
                sentiment_score=post_data['sentiment_score'],
                topics=post_data['topics'],
                source=post_data['source']
            )
            
            db.add(post)
            saved_count += 1
        
        db.commit()
        print(f"✅ Saved {saved_count} new items to database")
        if skipped_count > 0:
            print(f"⏭️  Skipped {skipped_count} duplicates")
    
    except Exception as e:
        db.rollback()
        print(f"❌ Error saving posts: {e}")
    
    finally:
        db.close()


def get_sentiment_trend(days: int = 7):
    """Get sentiment trends for the last N days"""
    db = SessionLocal()
    
    try:
        summaries = db.query(DailySummary)\
            .order_by(DailySummary.date.desc())\
            .limit(days)\
            .all()
        
        return summaries
    
    finally:
        db.close()


# Run this to initialize the database
if __name__ == "__main__":
    init_db()