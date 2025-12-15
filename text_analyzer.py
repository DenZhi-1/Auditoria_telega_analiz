import logging
import re
import nltk
from typing import Dict, List, Any, Tuple
from collections import Counter
import asyncio

logger = logging.getLogger(__name__)

try:
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
except:
    pass

from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.corpus import stopwords
import string

class TextAnalyzer:
    """AI-анализатор текстового контента"""
    
    def __init__(self):
        self.russian_stopwords = set(stopwords.words('russian'))
        
        # Словари для анализа тональности
        self.positive_words = {
            'хороший', 'отличный', 'прекрасный', 'замечательный', 'лучший',
            'удобный', 'качественный', 'простой', 'интересный', 'полезный',
            'важный', 'необходимый', 'успешный', 'эффективный', 'популярный',
            'любимый', 'дружелюбный', 'профессиональный', 'современный',
            'инновационный', 'креативный', 'яркий', 'красивый', 'стильный'
        }
        
        self.negative_words = {
            'плохой', 'ужасный', 'скучный', 'сложный', 'трудный',
            'дорогой', 'дешевый', 'старый', 'медленный', 'проблемный',
            'слабый', 'опасный', 'рискованный', 'неудобный', 'непонятный',
            'глупый', 'бесполезный', 'ненужный', 'устаревший', 'сломанный',
            'ошибка', 'проблема', 'недостаток', 'минус', 'негативный'
        }
        
        # Категории для классификации текста
        self.text_categories = {
            'технический': ['программирование', 'разработка', 'код', 'алгоритм', 'база данных'],
            'образовательный': ['обучение', 'курс', 'лекция', 'урок', 'знание', 'наука'],
            'коммерческий': ['продажа', 'покупка', 'цена', 'скидка', 'акция', 'магазин'],
            'развлекательный': ['развлечение', 'игра', 'юмор', 'прикол', 'мем', 'смешно'],
            'новостной': ['новость', 'событие', 'обновление', 'информация', 'анонс'],
            'социальный': ['сообщество', 'группа', 'друзья', 'общение', 'дискуссия'],
            'личный': ['опыт', 'история', 'рассказ', 'мнение', 'совет', 'рекомендация']
        }
        
        # Эмоциональные словари
        self.emotion_words = {
            'радость': {'рад', 'счастлив', 'доволен', 'восторг', 'ура', 'успех'},
            'грусть': {'грустно', 'печаль', 'тоска', 'разочарование', 'жаль'},
            'гнев': {'злой', 'сердит', 'раздражен', 'возмущен', 'бесит'},
            'страх': {'боюсь', 'страшно', 'опасно', 'тревога', 'переживаю'},
            'удивление': {'удивлен', 'неожиданно', 'интересно', 'любопытно', 'вау'},
            'доверие': {'доверяю', 'надежный', 'проверенный', 'гарантия', 'безопасно'}
        }
    
    def preprocess_text(self, text: str) -> List[str]:
        """Предобработка текста"""
        if not text:
            return []
        
        # Приводим к нижнему регистру
        text_lower = text.lower()
        
        # Удаляем пунктуацию и цифры
        text_clean = re.sub(r'[^\w\s]', ' ', text_lower)
        text_clean = re.sub(r'\d+', ' ', text_clean)
        
        # Токенизация
        tokens = word_tokenize(text_clean, language='russian')
        
        # Удаляем стоп-слова и короткие слова
        filtered_tokens = [
            token for token in tokens 
            if token not in self.russian_stopwords 
            and len(token) > 2
            and token not in string.punctuation
        ]
        
        return filtered_tokens
    
    def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Анализирует тональность текста"""
        tokens = self.preprocess_text(text)
        
        if not tokens:
            return {'score': 0, 'label': 'neutral', 'confidence': 0}
        
        positive_count = 0
        negative_count = 0
        
        for token in tokens:
            if token in self.positive_words:
                positive_count += 1
            elif token in self.negative_words:
                negative_count += 1
        
        total_words = len(tokens)
        
        if total_words == 0:
            return {'score': 0, 'label': 'neutral', 'confidence': 0}
        
        # Вычисляем оценку тональности от -1 до 1
        sentiment_score = (positive_count - negative_count) / total_words
        
        # Определяем метку
        if sentiment_score > 0.1:
            label = 'positive'
            confidence = min(1.0, sentiment_score)
        elif sentiment_score < -0.1:
            label = 'negative'
            confidence = min(1.0, -sentiment_score)
        else:
            label = 'neutral'
            confidence = 1.0 - min(abs(sentiment_score), 1.0)
        
        return {
            'score': round(sentiment_score, 3),
            'label': label,
            'confidence': round(confidence, 3),
            'positive_words': positive_count,
            'negative_words': negative_count,
            'total_words': total_words
        }
    
    def extract_keywords(self, text: str, top_n: int = 20) -> List[Dict]:
        """Извлекает ключевые слова из текста"""
        tokens = self.preprocess_text(text)
        
        if not tokens:
            return []
        
        # Подсчет частоты слов
        word_freq = Counter(tokens)
        
        # Исключаем слишком частые, но неинформативные слова
        common_words = {'этот', 'такой', 'какой', 'который', 'очень', 'можно'}
        
        # Формируем список ключевых слов
        keywords = []
        for word, count in word_freq.most_common(top_n * 2):
            if word not in common_words and count > 1:
                keywords.append({
                    'word': word,
                    'count': count,
                    'frequency': count / len(tokens)
                })
                
                if len(keywords) >= top_n:
                    break
        
        return keywords
    
    def categorize_text(self, text: str) -> List[Dict]:
        """Определяет категории текста"""
        tokens = self.preprocess_text(text)
        tokens_set = set(tokens)
        
        categories = []
        
        for category, keywords in self.text_categories.items():
            matches = 0
            for keyword in keywords:
                if keyword in tokens_set:
                    matches += 1
            
            if matches > 0:
                score = matches / len(keywords)
                categories.append({
                    'name': category,
                    'score': round(score, 3),
                    'matches': matches
                })
        
        # Сортируем по убыванию score
        categories.sort(key=lambda x: x['score'], reverse=True)
        
        return categories[:5]
    
    def analyze_emotions(self, text: str) -> Dict[str, float]:
        """Анализирует эмоциональную окраску текста"""
        tokens = self.preprocess_text(text)
        tokens_set = set(tokens)
        
        emotions = {}
        
        for emotion, words in self.emotion_words.items():
            matches = len([word for word in words if word in tokens_set])
            
            if matches > 0:
                score = matches / len(words)
                emotions[emotion] = round(score, 3)
        
        return emotions
    
    def calculate_readability(self, text: str) -> float:
        """Вычисляет оценку читаемости текста (0-100)"""
        if not text:
            return 0.0
        
        sentences = sent_tokenize(text, language='russian')
        words = self.preprocess_text(text)
        
        if not sentences or not words:
            return 0.0
        
        # Средняя длина предложения в словах
        avg_sentence_length = len(words) / len(sentences)
        
        # Средняя длина слова в символах
        avg_word_length = sum(len(word) for word in words) / len(words)
        
        # Оценка читаемости (простая формула)
        # Чем короче предложения и слова, тем выше читаемость
        readability = 100 - (avg_sentence_length * 2 + avg_word_length * 5)
        
        return max(0, min(100, readability))
    
    def generate_recommendations(self, analysis: Dict) -> List[str]:
        """Генерирует рекомендации на основе анализа текста"""
        recommendations = []
        
        sentiment = analysis.get('sentiment', {})
        readability = analysis.get('readability_score', 0)
        keywords = analysis.get('keywords', [])
        
        # Рекомендации по тональности
        if sentiment.get('label') == 'negative':
            if sentiment.get('score', 0) < -0.3:
                recommendations.append("📉 Текст имеет сильную негативную окраску. "
                                      "Рекомендуется добавить позитивных формулировок.")
            else:
                recommendations.append("⚠️ Текст имеет легкую негативную окраску. "
                                      "Проверьте формулировки на предмет критичности.")
        
        elif sentiment.get('label') == 'positive':
            if sentiment.get('score', 0) > 0.3:
                recommendations.append("📈 Отличная позитивная тональность! "
                                      "Такие тексты хорошо воспринимаются аудиторией.")
            else:
                recommendations.append("👍 Текст имеет позитивную окраску. "
                                      "Можно добавить больше эмоциональных слов.")
        
        # Рекомендации по читаемости
        if readability < 40:
            recommendations.append("🔍 Низкая читаемость текста. "
                                  "Рекомендуется разбить длинные предложения на более короткие.")
        elif readability < 60:
            recommendations.append("📖 Средняя читаемость. "
                                  "Можно упростить некоторые предложения для лучшего восприятия.")
        else:
            recommendations.append("✅ Отличная читаемость! Текст легко воспринимается.")
        
        # Рекомендации по ключевым словам
        if keywords:
            top_keywords = [k['word'] for k in keywords[:5]]
            recommendations.append(f"🎯 Используйте ключевые слова в заголовках: {', '.join(top_keywords)}")
        
        # Рекомендации по длине текста
        text_length = analysis.get('text_length', 0)
        if text_length < 500:
            recommendations.append("📝 Текст довольно короткий. "
                                  "Добавьте больше деталей и примеров для лучшего раскрытия темы.")
        elif text_length > 3000:
            recommendations.append("📚 Текст очень длинный. "
                                  "Рассмотрите возможность разбить его на несколько частей.")
        
        return recommendations[:5]
    
    async def analyze_text(self, text: str) -> Dict[str, Any]:
        """Основной метод анализа текста"""
        if not text:
            return {'error': 'Текст пустой'}
        
        logger.info(f"Начинаю анализ текста (длина: {len(text)} символов)")
        
        # Выполняем все анализы параллельно
        tasks = [
            asyncio.to_thread(self.analyze_sentiment, text),
            asyncio.to_thread(self.extract_keywords, text, 15),
            asyncio.to_thread(self.categorize_text, text),
            asyncio.to_thread(self.analyze_emotions, text),
            asyncio.to_thread(self.calculate_readability, text)
        ]
        
        results = await asyncio.gather(*tasks)
        
        analysis = {
            'text_length': len(text),
            'unique_words': len(set(self.preprocess_text(text))),
            'avg_sentence_length': len(self.preprocess_text(text)) / 
                                  max(1, len(sent_tokenize(text, language='russian'))),
            'sentiment': results[0],
            'keywords': results[1],
            'topics': results[2],
            'emotions': results[3],
            'readability_score': round(results[4], 1)
        }
        
        # Генерация рекомендаций
        analysis['recommendations'] = self.generate_recommendations(analysis)
        
        logger.info(f"Анализ текста завершен. Тональность: {analysis['sentiment']['label']}")
        
        return analysis
    
    def generate_text_report(self, analysis: Dict) -> str:
        """Генерирует текстовый отчет по анализу"""
        report_lines = [
            "🧠 ОТЧЕТ ПО AI-АНАЛИЗУ ТЕКСТА",
            "=" * 50,
            f"Длина текста: {analysis.get('text_length', 0):,} символов",
            f"Уникальных слов: {analysis.get('unique_words', 0)}",
            f"Читаемость: {analysis.get('readability_score', 0)}/100",
            ""
        ]
        
        # Тональность
        sentiment = analysis.get('sentiment', {})
        if sentiment:
            sentiment_label = {
                'positive': 'Позитивная',
                'negative': 'Негативная', 
                'neutral': 'Нейтральная'
            }.get(sentiment.get('label', 'neutral'), 'Нейтральная')
            
            report_lines.append(f"ТОНАЛЬНОСТЬ: {sentiment_label}")
            report_lines.append(f"Оценка: {sentiment.get('score', 0):.3f}")
            report_lines.append(f"Уверенность: {sentiment.get('confidence', 0):.1%}")
            report_lines.append("")
        
        # Ключевые слова
        keywords = analysis.get('keywords', [])
        if keywords:
            report_lines.append("КЛЮЧЕВЫЕ СЛОВА (топ-10):")
            for i, kw in enumerate(keywords[:10], 1):
                report_lines.append(f"{i}. {kw['word']} ({kw['count']} раз)")
            report_lines.append("")
        
        # Темы
        topics = analysis.get('topics', [])
        if topics:
            report_lines.append("ОСНОВНЫЕ ТЕМЫ:")
            for topic in topics[:5]:
                report_lines.append(f"• {topic['name']}: {topic['score']:.1%}")
            report_lines.append("")
        
        # Эмоции
        emotions = analysis.get('emotions', {})
        if emotions:
            report_lines.append("ЭМОЦИОНАЛЬНАЯ ОКРАСКА:")
            for emotion, score in emotions.items():
                if score > 0.1:
                    report_lines.append(f"• {emotion}: {score:.1%}")
            report_lines.append("")
        
        # Рекомендации
        recommendations = analysis.get('recommendations', [])
        if recommendations:
            report_lines.append("РЕКОМЕНДАЦИИ:")
            for i, rec in enumerate(recommendations, 1):
                report_lines.append(f"{i}. {rec}")
        
        return "\n".join(report_lines)
