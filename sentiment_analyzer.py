from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import re
from typing import Dict, List

class ArgentineSentimentAnalyzer:
    """Sentiment analyzer optimized for Argentine Spanish political content"""
    
    def __init__(self):
        self.analyzer = SentimentIntensityAnalyzer()
        
        # Custom lexicon for Argentine political terms
        self.custom_lexicon = {
            # Positive terms
            'crecimiento': 2.0,
            'inversión': 1.5,
            'desarrollo': 1.8,
            'progreso': 2.0,
            'mejora': 1.5,
            'éxito': 2.2,
            
            # Negative terms
            'inflación': -2.5,
            'crisis': -2.8,
            'corrupción': -3.0,
            'pobreza': -2.5,
            'inseguridad': -2.3,
            'desempleo': -2.4,
            'ajuste': -1.8,
            'recesión': -2.6,
            
            # Political figures and movements (neutral, let context decide)
            'milei': 0.0,
            'cristina': 0.0,
            'macri': 0.0,
            'massa': 0.0,
            'peronismo': 0.0,
            'kirchnerismo': 0.0,
        }
        
        # Update VADER lexicon with custom terms
        self.analyzer.lexicon.update(self.custom_lexicon)
        
    def preprocess_text(self, text: str) -> str:
        """Clean and prepare text for analysis"""
        # Remove URLs
        text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
        # Remove mentions
        text = re.sub(r'@\w+', '', text)
        # Remove hashtags (but keep the word)
        text = re.sub(r'#', '', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text.lower()
    
    def analyze(self, text: str) -> Dict:
        """
        Analyze sentiment of text
        Returns: dict with sentiment scores and classification
        """
        # Preprocess
        clean_text = self.preprocess_text(text)
        
        # Get VADER scores
        scores = self.analyzer.polarity_scores(clean_text)
        
        # Classify sentiment
        compound = scores['compound']
        if compound >= 0.05:
            sentiment = 'positive'
        elif compound <= -0.05:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        return {
            'sentiment': sentiment,
            'score': compound,
            'positive': scores['pos'],
            'negative': scores['neg'],
            'neutral': scores['neu'],
            'confidence': max(scores['pos'], scores['neg'], scores['neu'])
        }
    
    def batch_analyze(self, texts: List[str]) -> List[Dict]:
        """Analyze multiple texts at once"""
        return [self.analyze(text) for text in texts]
    
    def extract_topics(self, text: str) -> List[str]:
        """Extract political topics/keywords from text"""
        text_lower = text.lower()
        
        topics = []
        keywords = [
            'economía', 'inflación', 'dólar', 'peso',
            'milei', 'cristina', 'macri', 'massa',
            'peronismo', 'kirchnerismo', 'libertarios',
            'educación', 'salud', 'seguridad', 'trabajo',
            'corrupción', 'justicia', 'política',
            'congreso', 'senado', 'diputados',
            'provincias', 'caba', 'buenos aires'
        ]
        
        for keyword in keywords:
            if keyword in text_lower:
                topics.append(keyword)
        
        return topics


# Example usage
if __name__ == "__main__":
    analyzer = ArgentineSentimentAnalyzer()
    
    test_texts = [
        "La inflación en Argentina está destruyendo el poder adquisitivo de las familias",
        "Excelente noticia: el dólar se mantiene estable y hay inversiones llegando",
        "Otro caso de corrupción en el gobierno, esto no puede seguir así",
        "Milei anunció reformas económicas importantes para el país"
    ]
    
    print("=== Argentine Political Sentiment Analysis ===\n")
    for text in test_texts:
        result = analyzer.analyze(text)
        topics = analyzer.extract_topics(text)
        
        print(f"Text: {text}")
        print(f"Sentiment: {result['sentiment']} (score: {result['score']:.3f})")
        print(f"Topics: {', '.join(topics) if topics else 'None detected'}")
        print("-" * 80)