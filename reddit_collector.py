import praw
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import os
from sentiment_analyzer import ArgentineSentimentAnalyzer

class RedditCollector:
    """Collect political posts and comments from Argentine subreddits"""
    
    def __init__(self, client_id: str = None, client_secret: str = None, user_agent: str = None):
        """
        Initialize Reddit API client
        Get credentials from: https://www.reddit.com/prefs/apps
        """
        self.reddit = praw.Reddit(
            client_id=client_id or os.getenv('REDDIT_CLIENT_ID'),
            client_secret=client_secret or os.getenv('REDDIT_CLIENT_SECRET'),
            user_agent=user_agent or os.getenv('REDDIT_USER_AGENT', 'ArgentineSentiment/1.0')
        )
        
        self.analyzer = ArgentineSentimentAnalyzer()
        
        # Subreddits to monitor
        self.subreddits = [
            'argentina',
            'RepublicaArgentina', 
            'Republica_Argentina',
            'dankgentina',
            'ArgentinaBenderStyle',
            'BuenosAires',
        ]
        # Political keywords to filter (comprehensive list with accent variations)
        self.political_keywords = [
            # Politicians (with and without accents)
            'milei', 'cristina', 'cfk', 'cFK', 'macri', 'massa', 'bullrich', 'kicillof', 'axel',
            'fernandez', 'fernández', 'larreta', 'larreta', 'rodriguez', 'rodríguez',
            'patricia bullrich', 'alberto', 'mauricio', 'nestor', 'néstor',
            'scioli', 'randazzo', 'schiaretti', 'moreno', 'grabois',
            'del caño', 'del cano', 'espert', 'gomez', 'gómez centurión', 'centurion',
            'villarruel', 'santoro', 'tolosa paz', 'manes', 'facundo', 'bregman',
            'stolbizer', 'lousteau', 'martin', 'tetaz', 'vidal',
            
            # Political terms (with accent variations)
            'politica', 'política', 'politico', 'político', 'politicos', 'políticos',
            'elecciones', 'eleccion', 'elección', 'electoral', 'electorales',
            'votar', 'votacion', 'votación', 'voto', 'votos',
            'presidente', 'presidencia', 'presidencial', 'presidenciales',
            'gobierno', 'gobernador', 'gobernadora', 'intendente',
            'congreso', 'senado', 'diputados', 'diputado', 'diputada', 'senador', 'senadora',
            'legislatura', 'legislador', 'legisladora', 'legislativo',
            'ministro', 'ministra', 'ministerio', 'secretario', 'secretaria',
            'funcionario', 'funcionaria', 'dirigente', 'autoridades',
            
            # Parties and movements (with variations)
            'peronismo', 'peronista', 'peron', 'perón', 'justicialista',
            'kirchnerismo', 'kirchnerista', 'k', 'cristinismo',
            'macrismo', 'macrista', 'cambiemos', 'pro',
            'libertarios', 'libertario', 'la libertad avanza', 'lla', 'llaa',
            'juntos por el cambio', 'jxc', 'jpc',
            'frente de todos', 'union por la patria', 'unión por la patria', 'up',
            'ucr', 'radical', 'radicalismo', 'radicales',
            'izquierda', 'fit', 'fitu', 'socialista', 'comunista',
            'fpv', 'frente para la victoria',
            
            # Government terms
            'estado', 'nacional', 'provincial', 'municipal',
            'casa rosada', 'rosada', 'balcarce',
            'camara', 'cámara', 'legislativo', 'ejecutivo', 'judicial',
            'poder ejecutivo', 'poder legislativo', 'poder judicial',
            
            # Political topics (with accent variations)
            'campaña', 'campana', 'propaganda', 'proselitismo',
            'reforma', 'proyecto de ley', 'ley', 'decreto', 'dnu',
            'veto', 'sancion', 'sanción', 'promulgacion', 'promulgación',
            'corrupcion', 'corrupción', 'corrupto', 'coima', 'soborno',
            'juicio politico', 'juicio político', 'impeachment', 'destitución', 'destitucion',
            'condena', 'procesamiento', 'causa', 'fiscal', 'juez',
            
            # Protests and social movements
            'manifestacion', 'manifestación', 'marcha', 'protesta', 'movilizacion', 'movilización',
            'piquete', 'piquetero', 'corte', 'ruta', 'calle',
            'sindical', 'sindicato', 'gremio', 'cgt', 'cta',
            'huelga', 'paro', 'conflicto', 'reclamo',
            
            # Economic/political terms
            'impuesto', 'impuestos', 'tributo', 'tasas',
            'deficit', 'déficit', 'presupuesto', 'deuda',
            'ajuste', 'recorte', 'inflacion', 'inflación',
            'dolar', 'dólar', 'peso', 'economia', 'economía', 'economico', 'económico',
            'subsidio', 'plan', 'planes', 'asignacion', 'asignación',
            
            # Democratic processes
            'democracia', 'democratico', 'democrático',
            'constitucion', 'constitución', 'constitucional',
            'republica', 'república', 'republicano',
            'golpe', 'golpe de estado', 'dictadura', 'autoritario',
            
            # Argentina specific
            'argentina', 'argentino', 'argentinos', 'pais', 'país', 'nacion', 'nación',
            'patria', 'nacional', 'territorio', 'soberania', 'soberanía'
        ]
    
    def is_political(self, text: str) -> bool:
        """Check if text contains political keywords (requires at least 2 matches)"""
        text_lower = text.lower()
        matches = sum(1 for keyword in self.political_keywords if keyword in text_lower)
        return matches >= 2  # Require at least 2 political keywords for higher accuracy
    
    def collect_posts(self, subreddit_name: str, limit: int = 200, time_filter: str = 'week') -> List[Dict]:
        """
        Collect posts from a subreddit using multiple sorting methods for better coverage
        time_filter: 'hour', 'day', 'week', 'month', 'year', 'all'
        """
        subreddit = self.reddit.subreddit(subreddit_name)
        posts = []
        post_ids = set()  # Track IDs to avoid duplicates
        
        def process_submission(submission):
            """Helper function to process a submission"""
            # Skip if already collected
            if submission.id in post_ids:
                return None
            
            # Filter for political content
            if not self.is_political(submission.title + " " + submission.selftext):
                return None
            
            # Analyze sentiment
            full_text = f"{submission.title} {submission.selftext}"
            sentiment = self.analyzer.analyze(full_text)
            topics = self.analyzer.extract_topics(full_text)
            
            post_data = {
                'id': submission.id,
                'subreddit': subreddit_name,
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
            
            post_ids.add(submission.id)
            return post_data
        
        try:
            # Collect from hot posts (current trending content)
            for submission in subreddit.hot(limit=limit//2):
                post_data = process_submission(submission)
                if post_data:
                    posts.append(post_data)
            
            # Also collect from new posts (recent content) - this gets the freshest posts
            for submission in subreddit.new(limit=limit):
                post_data = process_submission(submission)
                if post_data:
                    posts.append(post_data)
            
            # If we didn't get enough posts, try top posts from the week
            if len(posts) < 20:
                print(f"  Only found {len(posts)} posts, fetching top posts as fallback...")
                for submission in subreddit.top(time_filter='week', limit=100):
                    post_data = process_submission(submission)
                    if post_data:
                        posts.append(post_data)
            
            # Additional fallback: if still not enough, try top from the month
            if len(posts) < 20:
                print(f"  Still only {len(posts)} posts, trying monthly top posts...")
                for submission in subreddit.top(time_filter='month', limit=100):
                    post_data = process_submission(submission)
                    if post_data:
                        posts.append(post_data)
        
        except Exception as e:
            print(f"Error collecting from r/{subreddit_name}: {e}")
        
        return posts
    
    def collect_comments(self, post_id: str, limit: int = 50) -> List[Dict]:
        """Collect and analyze comments from a specific post"""
        submission = self.reddit.submission(id=post_id)
        submission.comments.replace_more(limit=0)
        
        comments = []
        
        for comment in submission.comments.list()[:limit]:
            if len(comment.body) < 20:  # Skip very short comments
                continue
            
            sentiment = self.analyzer.analyze(comment.body)
            topics = self.analyzer.extract_topics(comment.body)
            
            comment_data = {
                'id': comment.id,
                'post_id': post_id,
                'text': comment.body,
                'author': str(comment.author),
                'score': comment.score,
                'created_utc': datetime.fromtimestamp(comment.created_utc, tz=timezone.utc).isoformat(),
                'sentiment': sentiment['sentiment'],
                'sentiment_score': sentiment['score'],
                'topics': topics,
                'source': 'reddit_comment'
            }
            
            comments.append(comment_data)
        
        return comments
    
    def collect_all_subreddits(self, limit_per_sub: int = 100) -> List[Dict]:
        """Collect posts from all monitored subreddits (increased default limit for better coverage)"""
        all_posts = []
        
        for subreddit in self.subreddits:
            print(f"Collecting from r/{subreddit}...")
            posts = self.collect_posts(subreddit, limit=limit_per_sub)
            all_posts.extend(posts)
            print(f"Collected {len(posts)} political posts")
        
        return all_posts
    
    def get_sentiment_summary(self, posts: List[Dict]) -> Dict:
        """Generate summary statistics from collected posts"""
        if not posts:
            return {
                'total': 0,
                'positive': 0,
                'negative': 0,
                'neutral': 0
            }
        
        sentiments = [p['sentiment'] for p in posts]
        
        return {
            'total': len(posts),
            'positive': sentiments.count('positive'),
            'negative': sentiments.count('negative'),
            'neutral': sentiments.count('neutral'),
            'positive_pct': sentiments.count('positive') / len(posts),
            'negative_pct': sentiments.count('negative') / len(posts),
            'neutral_pct': sentiments.count('neutral') / len(posts),
            'avg_score': sum(p['sentiment_score'] for p in posts) / len(posts)
        }


# Example usage
if __name__ == "__main__":
    # To use this, you need Reddit API credentials
    # Get them from: https://www.reddit.com/prefs/apps
    
    collector = RedditCollector(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        user_agent="ArgentineSentiment/1.0"
    )
    
    # Collect posts
    posts = collector.collect_all_subreddits(limit_per_sub=20)
    
    # Get summary
    summary = collector.get_sentiment_summary(posts)
    
    print("\n=== Collection Summary ===")
    print(f"Total posts analyzed: {summary['total']}")
    print(f"Positive: {summary['positive']} ({summary['positive_pct']:.1%})")
    print(f"Negative: {summary['negative']} ({summary['negative_pct']:.1%})")
    print(f"Neutral: {summary['neutral']} ({summary['neutral_pct']:.1%})")
    print(f"Average sentiment score: {summary['avg_score']:.3f}")