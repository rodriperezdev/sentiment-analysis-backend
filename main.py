from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from contextlib import asynccontextmanager
import uvicorn
import threading
import time
import signal

from database import get_db, Post, DailySummary, Topic, init_db, save_posts, SessionLocal
from sentiment_analyzer import ArgentineSentimentAnalyzer
from scheduler import DataCollectionScheduler
from reddit_collector import RedditCollector

# Initialize analyzer and collector
analyzer = ArgentineSentimentAnalyzer()
collector = RedditCollector()

# Initialize scheduler (will run in background)
scheduler = None

# Track if backfill is in progress
backfill_status = {
    "in_progress": False,
    "completed": False,
    "posts_collected": 0,
    "started_at": None,
    "completed_at": None,
    "error": None
}

def run_historical_backfill():
    """
    Run historical data backfill in background thread.
    This populates the database with historical posts without blocking startup.
    """
    global backfill_status
    
    try:
        backfill_status["in_progress"] = True
        backfill_status["started_at"] = datetime.now().isoformat()
        print("\n" + "="*60)
        print("STARTING HISTORICAL BACKFILL (Background)")
        print("="*60)
        print("This will collect historical political posts from Reddit...")
        print("The API is ready to use while this runs in the background.\n")
        
        all_collected_items = []
        
        # Collect from multiple time periods
        time_periods = [
            ('month', 100, 'Past month'),
            ('year', 150, 'Past year'),
            ('all', 100, 'All time top posts')
        ]
        
        for time_filter, limit, description in time_periods:
            print(f"\nCollecting: {description}")
            print("-" * 60)
            
            for subreddit in collector.subreddits:
                try:
                    print(f"  r/{subreddit} ({time_filter})...")
                    
                    reddit_sub = collector.reddit.subreddit(subreddit)
                    post_ids = set()
                    checked = 0
                    collected = 0
                    
                    # Add timeout protection for the iterator
                    def timeout_handler(signum, frame):
                        raise TimeoutError(f"Reddit API request timed out for r/{subreddit}")
                    
                    # Set a timeout for the entire subreddit collection (5 minutes max)
                    try:
                        # Only use signal on Unix-like systems (Render supports it)
                        timeout_set = False
                        if hasattr(signal, 'SIGALRM'):
                            signal.signal(signal.SIGALRM, timeout_handler)
                            signal.alarm(300)  # 5 minutes timeout
                            timeout_set = True
                        else:
                            print(f"    [WARNING] Timeout protection not available on this system")
                        
                        for submission in reddit_sub.top(time_filter=time_filter, limit=limit):
                            checked += 1
                            
                            if submission.id in post_ids:
                                continue
                            
                            # Filter for political content
                            full_text = f"{submission.title} {submission.selftext}".lower()
                            matches = sum(1 for keyword in collector.political_keywords if keyword in full_text)
                            
                            if matches < 1:
                                continue
                            
                            # Analyze the post
                            full_text = f"{submission.title} {submission.selftext}"
                            sentiment = analyzer.analyze(full_text)
                            topics = analyzer.extract_topics(full_text)
                            
                            post_data = {
                                'id': submission.id,
                                'subreddit': subreddit,
                                'title': submission.title,
                                'text': submission.selftext,
                                'author': str(submission.author),
                                'score': submission.score,
                                'num_comments': submission.num_comments,
                                'created_utc': datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat(),
                                'url': submission.url,
                                'sentiment': sentiment['sentiment'],
                                'sentiment_score': sentiment['score'],
                                'topics': topics,
                                'source': 'reddit'
                            }
                            
                            all_collected_items.append(post_data)
                            post_ids.add(submission.id)
                            collected += 1
                            
                            # Progress update
                            if collected % 25 == 0:
                                print(f"    ✓ {collected} posts collected (checked {checked})...")
                            
                            # Small delay to respect rate limits
                            time.sleep(0.3)
                    
                    finally:
                        # Cancel the alarm
                        if hasattr(signal, 'SIGALRM'):
                            signal.alarm(0)
                    
                    print(f"  [OK] r/{subreddit}: {collected} posts")
                    
                    # Longer delay between subreddits
                    time.sleep(2)
                    
                except TimeoutError:
                    print(f"  [TIMEOUT] r/{subreddit} took too long, skipping...")
                    # Cancel alarm and continue
                    if hasattr(signal, 'SIGALRM'):
                        signal.alarm(0)
                    continue
                except Exception as e:
                    print(f"  [ERROR] Error with r/{subreddit}: {str(e)[:100]}")
                    # Cancel alarm if set
                    if hasattr(signal, 'SIGALRM'):
                        signal.alarm(0)
                    continue
        
        # Save all collected items to database
        if all_collected_items:
            print(f"\n\nSaving {len(all_collected_items)} posts to database...")
            save_posts(all_collected_items)
            
            backfill_status["posts_collected"] = len(all_collected_items)
            backfill_status["completed"] = True
            backfill_status["completed_at"] = datetime.now().isoformat()
            
            # Calculate date range
            dates = [datetime.fromisoformat(item['created_utc']) for item in all_collected_items]
            oldest = min(dates)
            newest = max(dates)
            
            print("\n" + "="*60)
            print("HISTORICAL BACKFILL COMPLETE!")
            print("="*60)
            print(f"[OK] Total posts collected: {len(all_collected_items)}")
            print(f"[OK] Date range: {oldest.strftime('%Y-%m-%d')} to {newest.strftime('%Y-%m-%d')}")
            print(f"[OK] Span: {(newest - oldest).days} days")
            print("="*60 + "\n")
        else:
            print("\n[WARNING] No posts collected during backfill.\n")
            backfill_status["completed"] = True
            backfill_status["error"] = "No posts collected"
        
    except Exception as e:
        print(f"\n[ERROR] Backfill failed: {e}\n")
        backfill_status["error"] = str(e)
        backfill_status["completed"] = True
    
    finally:
        backfill_status["in_progress"] = False

def check_and_start_backfill():
    """
    Check if historical data exists, and start backfill if needed.
    This runs in a background thread to avoid blocking deployment.
    """
    db = SessionLocal()
    
    try:
        # Check if we have enough historical data
        total_posts = db.query(func.count(Post.id)).scalar()
        
        # Check date range
        if total_posts > 0:
            oldest_post = db.query(Post).order_by(Post.created_utc.asc()).first()
            newest_post = db.query(Post).order_by(Post.created_utc.desc()).first()
            days_span = (newest_post.created_utc - oldest_post.created_utc).days
            
            print(f"\n[INFO] Current database status:")
            print(f"   Total posts: {total_posts}")
            print(f"   Date range: {oldest_post.created_utc.strftime('%Y-%m-%d')} to {newest_post.created_utc.strftime('%Y-%m-%d')}")
            print(f"   Span: {days_span} days\n")
            
            # Check for invalid future dates (data corruption)
            now = datetime.now(timezone.utc)
            if newest_post.created_utc > now + timedelta(days=1):
                print(f"\n[WARNING] Database contains future dates!")
                print(f"[WARNING] Newest post date: {newest_post.created_utc.strftime('%Y-%m-%d')}")
                print(f"[WARNING] Current date: {now.strftime('%Y-%m-%d')}")
                print(f"[WARNING] This indicates a timezone/date parsing issue.")
                print(f"[WARNING] Please call POST /clear-database to reset and re-collect.\n")
                backfill_status["error"] = "Database contains invalid future dates"
                backfill_status["completed"] = True
                return
            
            # If we have good data (more than 200 posts and spanning at least 30 days), skip backfill
            if total_posts >= 200 and days_span >= 30:
                print("[OK] Historical data already exists. Skipping backfill.\n")
                backfill_status["completed"] = True
                return
        
        print(f"[INFO] Limited historical data found ({total_posts} posts).")
        print("[INFO] Starting background backfill to populate historical data...")
        print("[INFO] This will run in the background without blocking the API.\n")
        
        # Start backfill in a separate thread
        backfill_thread = threading.Thread(target=run_historical_backfill, daemon=True)
        backfill_thread.start()
        
    except Exception as e:
        print(f"[ERROR] Error checking database: {e}")
    
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown"""
    # Startup
    init_db()
    
    global scheduler
    scheduler = DataCollectionScheduler()
    scheduler.start()
    print("✓ Database initialized")
    print("✓ Scheduler started")
    
    # Check if we need to run historical backfill (non-blocking)
    check_and_start_backfill()
    
    yield
    
    # Shutdown
    if scheduler:
        scheduler.stop()
    print("✓ Scheduler stopped")

app = FastAPI(
    title="Argentine Election Sentiment API",
    description="Real-time sentiment analysis of Argentine political discussions",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://perezrodri.vercel.app",  # Production frontend
        "http://localhost:3000",  # Local development
        "http://localhost:3001",  # Alternative local port
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Response models
class SentimentData(BaseModel):
    date: str
    positive: float
    negative: float
    neutral: float
    total_posts: int

class TopicData(BaseModel):
    topic: str
    mentions: int
    avg_sentiment: float

class PostData(BaseModel):
    id: str
    title: str
    text: str
    sentiment: str
    score: float
    created_at: str
    subreddit: str
    topics: List[str]

class AnalyzeRequest(BaseModel):
    text: str

# Routes
@app.get("/")
def read_root():
    return {
        "message": "Argentine Election Sentiment Analysis API",
        "version": "1.0.0",
        "description": "Real-time sentiment analysis of Argentine political discussions from Reddit",
        "endpoints": {
            "GET /sentiment/trend": "Get sentiment trends over time",
            "GET /sentiment/current": "Get current sentiment snapshot",
            "GET /topics/trending": "Get trending political topics",
            "GET /posts/recent": "Get recent analyzed posts",
            "POST /analyze/text": "Manually analyze any text",
            "GET /stats": "Get overall statistics",
            "GET /status": "Get API status and backfill progress",
            "POST /collect/refresh": "Trigger manual data collection from Reddit",
            "POST /clear-database": "[TEMPORARY] Clear all data and restart backfill"
        },
        "data_sources": ["r/argentina", "r/RepublicaArgentina", "r/ArgentinaPolitica"],
        "features": [
            "Automatic historical data backfill on first deployment",
            "Real-time data collection every 2 hours",
            "VADER sentiment analysis",
            "Topic extraction and trending analysis"
        ],
        "github": "https://github.com/rodriperezdev/sentiment-analysis-backend"
    }

@app.get("/sentiment/trend", response_model=List[SentimentData])
def get_sentiment_trend(days: int = 7, db: Session = Depends(get_db)):
    """Get sentiment trends for the last N days"""
    end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)
    
    summaries = db.query(DailySummary).filter(
        DailySummary.date >= start_date,
        DailySummary.date < end_date
    ).order_by(DailySummary.date).all()
    
    # If no daily summaries, calculate from posts directly
    if not summaries:
        # Get all posts in the date range (both start and end boundaries)
        posts = db.query(Post).filter(
            Post.created_utc >= start_date,
            Post.created_utc < end_date
        ).all()
        
        # If no posts in the requested range, try to get the most recent data available
        if not posts:
            # Get the most recent posts and work backwards
            newest_post = db.query(Post).order_by(Post.created_utc.desc()).first()
            if not newest_post:
                return []  # Database is completely empty
            
            # Use the newest post's date as end_date and calculate backwards
            end_date = newest_post.created_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            start_date = end_date - timedelta(days=days)
            
            posts = db.query(Post).filter(
                Post.created_utc >= start_date,
                Post.created_utc < end_date
            ).all()
            
            if not posts:
                return []
        
        # Group posts by day
        daily_data = {}
        for post in posts:
            day_key = post.created_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            if day_key not in daily_data:
                daily_data[day_key] = {'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0}
            
            daily_data[day_key][post.sentiment] += 1
            daily_data[day_key]['total'] += 1
        
        # Filter out days with too few posts (reduces noise)
        min_posts_threshold = 5 if days <= 30 else 10  # Higher threshold for longer periods
        daily_data = {k: v for k, v in daily_data.items() if v['total'] >= min_posts_threshold}
        
        # Convert to response format
        result = []
        for date_key in sorted(daily_data.keys()):
            data = daily_data[date_key]
            total = data['total']
            
            # Calculate percentages and ensure they sum to 1.0
            pos_pct = data['positive'] / total
            neg_pct = data['negative'] / total
            neu_pct = data['neutral'] / total
            
            # Normalize to ensure sum is exactly 1.0 (handle floating point errors)
            sum_pct = pos_pct + neg_pct + neu_pct
            if sum_pct > 0:
                pos_pct /= sum_pct
                neg_pct /= sum_pct
                neu_pct /= sum_pct
            
            result.append(SentimentData(
                date=date_key.strftime("%Y-%m-%d"),
                positive=pos_pct,
                negative=neg_pct,
                neutral=neu_pct,
                total_posts=total
            ))
        
        return result
    
    return [
        SentimentData(
            date=s.date.strftime("%Y-%m-%d"),
            positive=s.positive_pct,
            negative=s.negative_pct,
            neutral=s.neutral_pct,
            total_posts=s.total_posts
        )
        for s in summaries
    ]

@app.get("/sentiment/current")
def get_current_sentiment(db: Session = Depends(get_db)):
    """Get current sentiment snapshot (last 24 hours)"""
    yesterday = datetime.now() - timedelta(days=1)
    
    posts = db.query(Post).filter(Post.created_utc >= yesterday).all()
    
    if not posts:
        return {
            "timestamp": datetime.now().isoformat(),
            "sentiment": {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 0.0
            },
            "total_analyzed": 0,
            "message": "No recent data. Collection in progress..."
        }
    
    total = len(posts)
    positive = sum(1 for p in posts if p.sentiment == 'positive')
    negative = sum(1 for p in posts if p.sentiment == 'negative')
    neutral = sum(1 for p in posts if p.sentiment == 'neutral')
    
    return {
        "timestamp": datetime.now().isoformat(),
        "sentiment": {
            "positive": positive / total,
            "negative": negative / total,
            "neutral": neutral / total
        },
        "total_analyzed": total,
        "avg_score": sum(p.sentiment_score for p in posts) / total,
        "last_updated": max(p.analyzed_at for p in posts).isoformat()
    }

@app.get("/topics/trending", response_model=List[TopicData])
def get_trending_topics(limit: int = 10, days: int = 7, db: Session = Depends(get_db)):
    """Get trending political topics"""
    start_date = datetime.now() - timedelta(days=days)
    
    # Query topics from the last N days
    topics = db.query(
        Topic.name,
        func.sum(Topic.mention_count).label('total_mentions'),
        func.avg(Topic.avg_sentiment).label('avg_sent')
    ).filter(
        Topic.date >= start_date
    ).group_by(Topic.name).order_by(desc('total_mentions')).limit(limit).all()
    
    if not topics:
        # Return sample topics if no data
        return [
            TopicData(topic="economía", mentions=450, avg_sentiment=-0.3),
            TopicData(topic="inflación", mentions=380, avg_sentiment=-0.6),
            TopicData(topic="milei", mentions=520, avg_sentiment=0.1),
            TopicData(topic="dólar", mentions=410, avg_sentiment=-0.4),
        ]
    
    return [
        TopicData(
            topic=t.name,
            mentions=int(t.total_mentions),
            avg_sentiment=float(t.avg_sent)
        )
        for t in topics
    ]

@app.get("/posts/recent", response_model=List[PostData])
def get_recent_posts(limit: int = 20, db: Session = Depends(get_db)):
    """Get recent analyzed posts"""
    posts = db.query(Post).order_by(Post.created_utc.desc()).limit(limit).all()
    
    if not posts:
        return []
    
    return [
        PostData(
            id=p.id,
            title=p.title,
            text=p.text[:200] + "..." if len(p.text) > 200 else p.text,
            sentiment=p.sentiment,
            score=p.sentiment_score,
            created_at=p.created_utc.isoformat(),
            subreddit=p.subreddit,
            topics=p.topics or []
        )
        for p in posts
    ]

@app.post("/analyze/text")
def analyze_text(request: AnalyzeRequest):
    """Manually analyze any text for sentiment"""
    result = analyzer.analyze(request.text)
    topics = analyzer.extract_topics(request.text)
    
    return {
        "text": request.text,
        "sentiment": result['sentiment'],
        "score": result['score'],
        "details": {
            "positive": result['positive'],
            "negative": result['negative'],
            "neutral": result['neutral']
        },
        "topics": topics,
        "confidence": result['confidence']
    }

@app.get("/stats")
def get_overall_stats(db: Session = Depends(get_db)):
    """Get overall statistics"""
    total_posts = db.query(func.count(Post.id)).scalar()
    total_days = db.query(func.count(DailySummary.id)).scalar()
    
    if total_posts == 0:
        return {
            "total_posts_analyzed": 0,
            "total_days_tracked": 0,
            "message": "Data collection in progress. Check back soon!"
        }
    
    avg_daily_posts = total_posts / max(total_days, 1)
    
    # Get most mentioned topics
    top_topics = db.query(
        Topic.name,
        func.sum(Topic.mention_count).label('total')
    ).group_by(Topic.name).order_by(desc('total')).limit(5).all()
    
    return {
        "total_posts_analyzed": total_posts,
        "total_days_tracked": total_days,
        "avg_daily_posts": round(avg_daily_posts, 1),
        "top_topics": [{"topic": t.name, "mentions": int(t.total)} for t in top_topics],
        "data_collection": "Active - updates every 2 hours"
    }

@app.get("/status")
def get_status(db: Session = Depends(get_db)):
    """Get API and backfill status"""
    total_posts = db.query(func.count(Post.id)).scalar()
    
    # Get date range if data exists
    date_range = None
    if total_posts > 0:
        oldest_post = db.query(Post).order_by(Post.created_utc.asc()).first()
        newest_post = db.query(Post).order_by(Post.created_utc.desc()).first()
        date_range = {
            "oldest": oldest_post.created_utc.isoformat(),
            "newest": newest_post.created_utc.isoformat(),
            "days_span": (newest_post.created_utc - oldest_post.created_utc).days
        }
    
    return {
        "api_status": "online",
        "total_posts": total_posts,
        "date_range": date_range,
        "backfill": {
            "in_progress": backfill_status["in_progress"],
            "completed": backfill_status["completed"],
            "posts_collected": backfill_status["posts_collected"],
            "started_at": backfill_status["started_at"],
            "completed_at": backfill_status["completed_at"],
            "error": backfill_status["error"]
        },
        "scheduler_active": scheduler is not None and scheduler.scheduler.running if scheduler else False
    }

@app.post("/collect/refresh")
def trigger_collection():
    """Manually trigger data collection from Reddit"""
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Manual data collection triggered via API")
        
        # Collect posts from all subreddits
        posts = collector.collect_all_subreddits(limit_per_sub=100)
        
        if not posts:
            return {
                "status": "warning",
                "message": "No new political posts found",
                "posts_collected": 0,
                "timestamp": datetime.now().isoformat()
            }
        
        # Save posts to database
        save_posts(posts)
        
        return {
            "status": "success",
            "message": f"Successfully collected and stored {len(posts)} new posts",
            "posts_collected": len(posts),
            "timestamp": datetime.now().isoformat(),
            "subreddits_checked": ["argentina", "RepublicaArgentina", "ArgentinaPolitica"]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during collection: {str(e)}")

@app.post("/clear-database")
def clear_database():
    """
    TEMPORARY ENDPOINT: Clear all data from database to allow fresh backfill.
    Remove this endpoint after fixing the database.
    """
    try:
        db = SessionLocal()
        
        # Get stats before clearing
        post_count = db.query(func.count(Post.id)).scalar()
        summary_count = db.query(func.count(DailySummary.id)).scalar()
        topic_count = db.query(func.count(Topic.id)).scalar()
        
        # Clear all tables
        db.query(Post).delete()
        db.query(DailySummary).delete()
        db.query(Topic).delete()
        db.commit()
        
        print("\n[INFO] Database cleared successfully")
        print(f"   Deleted {post_count} posts")
        print(f"   Deleted {summary_count} daily summaries")
        print(f"   Deleted {topic_count} topics\n")
        
        # Reset backfill status to trigger new backfill
        global backfill_status
        backfill_status = {
            "in_progress": False,
            "completed": False,
            "posts_collected": 0,
            "started_at": None,
            "completed_at": None,
            "error": None
        }
        
        # Trigger new backfill in background
        check_and_start_backfill()
        
        return {
            "status": "success",
            "message": "Database cleared successfully. Backfill will start automatically.",
            "deleted": {
                "posts": post_count,
                "daily_summaries": summary_count,
                "topics": topic_count
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error clearing database: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)