from dotenv import load_dotenv
import os

load_dotenv()

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from reddit_collector import RedditCollector
from database import save_posts, SessionLocal, DailySummary, Post, Topic
from collections import Counter
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataCollectionScheduler:
    """Automated data collection and aggregation"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.collector = RedditCollector()
        
    def collect_and_store(self):
        """Collect new posts and store them"""
        try:
            logger.info("Starting data collection...")
            posts = self.collector.collect_all_subreddits(limit_per_sub=30)
            
            if posts:
                save_posts(posts)
                logger.info(f"Successfully collected and stored {len(posts)} posts")
            else:
                logger.warning("No posts collected")
        
        except Exception as e:
            logger.error(f"Error in data collection: {e}")
    
    def generate_daily_summary(self):
        """Generate daily sentiment summary"""
        try:
            db = SessionLocal()
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday = today - timedelta(days=1)
            
            # Check if summary already exists
            existing = db.query(DailySummary).filter(DailySummary.date == yesterday).first()
            if existing:
                logger.info("Daily summary already exists")
                return
            
            # Get posts from yesterday
            posts = db.query(Post).filter(
                Post.created_utc >= yesterday,
                Post.created_utc < today
            ).all()
            
            if not posts:
                logger.warning("No posts to summarize")
                return
            
            # Calculate statistics
            total = len(posts)
            positive = sum(1 for p in posts if p.sentiment == 'positive')
            negative = sum(1 for p in posts if p.sentiment == 'negative')
            neutral = sum(1 for p in posts if p.sentiment == 'neutral')
            
            avg_score = sum(p.sentiment_score for p in posts) / total
            
            # Get top topics
            all_topics = []
            for post in posts:
                if post.topics:
                    all_topics.extend(post.topics)
            
            topic_counts = Counter(all_topics)
            top_topics = [
                {'topic': topic, 'count': count}
                for topic, count in topic_counts.most_common(10)
            ]
            
            # Create summary
            summary = DailySummary(
                date=yesterday,
                total_posts=total,
                positive_count=positive,
                negative_count=negative,
                neutral_count=neutral,
                positive_pct=positive / total,
                negative_pct=negative / total,
                neutral_pct=neutral / total,
                avg_sentiment_score=avg_score,
                top_topics=top_topics
            )
            
            db.add(summary)
            db.commit()
            
            logger.info(f"Generated daily summary for {yesterday.date()}")
        
        except Exception as e:
            db.rollback()
            logger.error(f"Error generating daily summary: {e}")
        
        finally:
            db.close()
    
    def update_topic_trends(self):
        """Update topic mention counts and sentiment"""
        try:
            db = SessionLocal()
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get today's posts
            posts = db.query(Post).filter(
                Post.created_utc >= today
            ).all()
            
            if not posts:
                return
            
            # Collect topic data
            topic_data = {}
            
            for post in posts:
                if not post.topics:
                    continue
                
                for topic in post.topics:
                    if topic not in topic_data:
                        topic_data[topic] = {
                            'count': 0,
                            'scores': [],
                            'positive': 0,
                            'negative': 0,
                            'neutral': 0
                        }
                    
                    topic_data[topic]['count'] += 1
                    topic_data[topic]['scores'].append(post.sentiment_score)
                    topic_data[topic][post.sentiment] += 1
            
            # Save topic data
            for topic_name, data in topic_data.items():
                topic = Topic(
                    name=topic_name,
                    date=today,
                    mention_count=data['count'],
                    avg_sentiment=sum(data['scores']) / len(data['scores']),
                    positive_mentions=data['positive'],
                    negative_mentions=data['negative'],
                    neutral_mentions=data['neutral']
                )
                
                db.add(topic)
            
            db.commit()
            logger.info(f"Updated trends for {len(topic_data)} topics")
        
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating topic trends: {e}")
        
        finally:
            db.close()
    
    def start(self):
        """Start the scheduler with all jobs"""
        
        # Collect data every 2 hours
        self.scheduler.add_job(
            self.collect_and_store,
            CronTrigger(hour='*/2'),  # Every 2 hours
            id='collect_data',
            name='Collect Reddit data',
            replace_existing=True
        )
        
        # Generate daily summary at 1 AM
        self.scheduler.add_job(
            self.generate_daily_summary,
            CronTrigger(hour=1, minute=0),
            id='daily_summary',
            name='Generate daily summary',
            replace_existing=True
        )
        
        # Update topic trends every 6 hours
        self.scheduler.add_job(
            self.update_topic_trends,
            CronTrigger(hour='*/6'),
            id='update_topics',
            name='Update topic trends',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Scheduler started successfully")
        logger.info("Jobs scheduled:")
        for job in self.scheduler.get_jobs():
            logger.info(f"  - {job.name}: {job.trigger}")
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")


# Integration with FastAPI
if __name__ == "__main__":
    scheduler = DataCollectionScheduler()
    
    # Run initial collection
    logger.info("Running initial data collection...")
    scheduler.collect_and_store()
    
    # Start scheduler
    scheduler.start()
    
    # Keep running
    try:
        import time
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()