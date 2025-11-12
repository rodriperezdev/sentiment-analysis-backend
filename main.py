from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from contextlib import asynccontextmanager
import uvicorn

from database import get_db, Post, DailySummary, Topic, init_db, save_posts
from sentiment_analyzer import ArgentineSentimentAnalyzer
from scheduler import DataCollectionScheduler
from reddit_collector import RedditCollector

# Initialize analyzer and collector
analyzer = ArgentineSentimentAnalyzer()
collector = RedditCollector()

# Initialize scheduler (will run in background)
scheduler = None

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
            "POST /collect/refresh": "Trigger manual data collection from Reddit"
        },
        "data_sources": ["r/argentina", "r/RepublicaArgentina", "r/ArgentinaPolitica"],
        "github": "Link to your repo"
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)