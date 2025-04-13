import os
import re
import logging
import requests
import feedparser
import numpy as np
from urllib.parse import urlparse, urljoin
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import openai
from newspaper import Article, Config
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Load environment variables
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("❌ Missing API key. Set the OPENAI_API_KEY environment variable.")

# OpenAI API Client
openai_client = openai.OpenAI(api_key=api_key)

# Configure Flask App
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)

# Configure Logging
logging.basicConfig(level=logging.DEBUG)

# Trusted News Sources Database
TRUSTED_SOURCES = {
    "indianexpress.com": "High",
    "timesofindia.indiatimes.com": "High",
    "thehindu.com": "High",
    "hindustantimes.com": "High",
    "ndtv.com": "Medium",
    "reuters.com": "High",
    "bbc.com": "High",
    "aljazeera.com": "Medium"
}

COMPARISON_SOURCES = [
    "timesofindia.indiatimes.com",
    "hindustantimes.com",
    "thehindu.com",
    "ndtv.com",
    "indianexpress.com"
]

def extract_domain(url):
    try:
        parsed_url = urlparse(url)
        domain_parts = parsed_url.netloc.replace("www.", "").split('.')
        return ".".join(domain_parts[-2:])
    except Exception as e:
        logging.error(f"❌ Error extracting domain from URL: {str(e)}")
        return "Unknown"

def extract_number(text):
    try:
        match = re.search(r"\d+(?:\.\d+)?", text)
        return float(match.group()) if match else None
    except Exception as e:
        logging.error(f"❌ Error extracting number: {str(e)}")
        return None 

def fetch_article_from_url(url):
    try:
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36'
        config.request_timeout = 10
        
        article = Article(url, config=config)
        article.download()
        article.parse()
        
        if not article.text or len(article.text) < 100:
            raise ValueError("Article text too short or empty")
            
        return article.title, article.text, article.publish_date
    except Exception as e:
        logging.error(f"❌ Error fetching article from URL: {str(e)}")
        return None, None, None

def analyze_article_content(text, title, date):
    try:
        if not text or len(text) < 100:
            raise ValueError("Text too short for analysis")

        # Get Bias Score
        bias_result = analyze_with_gpt3(
            text,
            "Analyze the bias in this news article and return ONLY a number between 0 and 100 where 0 is completely neutral and 100 is extremely biased. Just return the number, nothing else.",
            temperature=0
        )
        bias_score = extract_number(bias_result) if bias_result else None

        # Get Rewritten Text
        rewritten_text = analyze_with_gpt3(
            text,
            "Rewrite this news article in a completely neutral way, removing any emotionally charged language, bias, or subjective language. Maintain all factual information and keep the same length.",
            temperature=0.2
        )

        # Get Redlined Text
        redlined_text = analyze_with_gpt3(
            text,
            """Identify biased words or phrases in this text and suggest neutral alternatives. 
            Return ONLY in this exact format:
            Biased words: [word1, word2, word3]
            Neutral alternatives: [alternative1, alternative2, alternative3]""",
            temperature=0
        )
        redlined_result = parse_redlined_text(redlined_text) if redlined_text else {"biased_words": [], "neutral_alternatives": []}

        return {
            "title": title or "Untitled Article",
            "date": date.strftime("%Y-%m-%d") if date else "Unknown date",
            "bias_score": round(float(bias_score), 2) if bias_score is not None else None,
            "rewritten": rewritten_text or "Could not generate neutral version",
            "redlined_text": redlined_result,
            "original_text": text
        }
    except Exception as e:
        logging.error(f"❌ Error analyzing article content: {str(e)}")
        return None

def extract_keywords(text, n=5):
    """Extract top n keywords from text using TF-IDF"""
    try:
        vectorizer = TfidfVectorizer(stop_words='english', max_features=n)
        vectorizer.fit([text])
        return vectorizer.get_feature_names_out()
    except Exception as e:
        logging.error(f"Error extracting keywords: {str(e)}")
        return []

def get_similar_articles(main_title, main_text, main_date, exclude_domain, max_articles=3):
    """Find truly similar articles about the same event"""
    try:
        # Extract key entities and locations using NLP
        key_terms = extract_key_terms(main_title + " " + main_text)
        
        # Build a focused search query
        search_query = " ".join([
            "India Pakistan",
            "LoC",
            "ceasefire",
            "border",
            main_date.strftime("%Y-%m-%d")
        ] + list(key_terms))
        
        # Search specific Indian news sites
        articles = []
        for source in ["thehindu.com", "hindustantimes.com", "ndtv.com"]:
            if source != exclude_domain:
                try:
                    # Use site-specific search with date filter
                    search_url = f"https://www.{source}/search/?q={search_query}"
                    articles += scrape_articles_from_search(search_url, source)
                except Exception as e:
                    logging.error(f"Error searching {source}: {str(e)}")
        
        # Calculate content similarity
        if articles:
            vectorizer = TfidfVectorizer(stop_words='english')
            main_content = f"{main_title}\n\n{main_text}"
            comparison_texts = [f"{a['title']}\n\n{a['text']}" for a in articles]
            
            tfidf_matrix = vectorizer.fit_transform([main_content] + comparison_texts)
            cosine_similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
            
            # Add scores and filter by similarity threshold
            for i, score in enumerate(cosine_similarities):
                articles[i]['similarity'] = score
                
            articles = [a for a in articles if a.get('similarity', 0) > 0.3]  # Minimum 30% similarity
            
            # Sort by similarity and date
            articles.sort(key=lambda x: (-x.get('similarity', 0), 
                                       abs((x.get('date', main_date) - main_date).total_seconds())))
        
        return articles[:max_articles]
        
    except Exception as e:
        logging.error(f"Error in get_similar_articles: {str(e)}")
        return []

def parse_redlined_text(text):
    try:
        if not text:
            return {"biased_words": [], "neutral_alternatives": []}

        biased_words = []
        neutral_alternatives = []

        biased_match = re.search(r"Biased words:\s*\[([^\]]*)\]", text, re.IGNORECASE)
        if biased_match:
            biased_words = [word.strip().strip("'\"") for word in biased_match.group(1).split(",")]

        neutral_match = re.search(r"Neutral alternatives:\s*\[([^\]]*)\]", text, re.IGNORECASE)
        if neutral_match:
            neutral_alternatives = [word.strip().strip("'\"") for word in neutral_match.group(1).split(",")]

        return {
            "biased_words": biased_words if biased_words else [],
            "neutral_alternatives": neutral_alternatives if neutral_alternatives else []
        }
    except Exception as e:
        logging.error(f"❌ Error parsing redlined text: {str(e)}")
        return {"biased_words": [], "neutral_alternatives": []}

def scrape_articles_from_search(search_url, source):
    """Scrape articles from a news site search results page"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(search_url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    articles = []
    
    # Site-specific selectors
    if source == "thehindu.com":
        results = soup.select(".story-card")
        for item in results[:5]:  # Limit to top 5
            try:
                url = item.find('a')['href']
                if not url.startswith('http'):
                    url = f"https://www.{source}{url}"
                
                title = item.find('h3').get_text(strip=True)
                date = datetime.now()  # Temporary - would parse from item
                
                # Fetch full article
                article_text = fetch_article_text(url)
                if article_text:
                    articles.append({
                        'title': title,
                        'text': article_text,
                        'url': url,
                        'source': source,
                        'date': date
                    })
            except Exception as e:
                continue
                
    # Similar blocks for other news sites...
    
    return articles

def analyze_with_gpt3(text, instructions, temperature=0):
    try:
        messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": text}
        ]

        response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=temperature
        )

        if response and response.choices and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        return None

    except Exception as e:
        logging.error(f"❌ Error in GPT-3.5 Analysis: {str(e)}")
        return None

@app.route('/api/analyze-url', methods=['POST'])
def analyze_news_from_url():
    try:
        if not request.is_json:
            return jsonify({"error": "Invalid request format. Expected JSON"}), 400

        data = request.get_json()
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"error": "No URL provided"}), 400

        title, article_text, publish_date = fetch_article_from_url(url)
        if not article_text:
            return jsonify({"error": "Could not extract article text from URL"}), 400

        analysis_result = analyze_article_content(article_text, title, publish_date)
        if not analysis_result:
            return jsonify({"error": "Could not analyze article content"}), 400

        domain = extract_domain(url)
        credibility = TRUSTED_SOURCES.get(domain, "Unknown")
        
        response = {
            **analysis_result,
            "source": domain,
            "credibility": credibility,
            "original_url": url
        }

        return jsonify(response)

    except Exception as e:
        logging.error(f"❌ Error in /api/analyze-url: {str(e)}")
        return jsonify({"error": "Internal Server Error"}), 500

@app.route('/api/compare-news', methods=['POST'])
def compare_news():
    try:
        if not request.is_json:
            return jsonify({"error": "Invalid request format. Expected JSON"}), 400

        data = request.get_json()
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"error": "No URL provided"}), 400

        # Get and analyze original article
        title, article_text, publish_date = fetch_article_from_url(url)
        if not article_text:
            return jsonify({"error": "Could not extract article text from URL"}), 400

        original_analysis = analyze_article_content(article_text, title, publish_date)
        if not original_analysis:
            return jsonify({"error": "Could not analyze article content"}), 400

        domain = extract_domain(url)
        publish_date = publish_date or datetime.now()
        
        # Get comparison articles using improved method
        comparison_articles = []
        similar_articles = get_similar_articles(title, article_text, publish_date, domain)
        
        for article in similar_articles:
            analyzed = analyze_article_content(
                article['text'],
                article['title'],
                article['date']
            )
            if analyzed:
                comparison_articles.append({
                    **analyzed,
                    "source": article['source'],
                    "credibility": TRUSTED_SOURCES.get(article['source'], "Unknown"),
                    "original_url": article['url'],
                    "timestamp": article['date'].isoformat() if article.get('date') else datetime.now().isoformat(),
                    "similarity_score": round(article.get('similarity', 0) * 100, 1)
                })

        response = {
            "status": "success",
            "main_topic": title or "Unknown Topic",
            "comparison_date": datetime.now().strftime("%Y-%m-%d"),
            "original_article": {
                **original_analysis,
                "source": domain,
                "credibility": TRUSTED_SOURCES.get(domain, "Unknown"),
                "original_url": url,
                "timestamp": datetime.now().isoformat()
            },
            "comparison_articles": comparison_articles,
            "message": f"Found {len(comparison_articles)} comparison articles"
        }

        return jsonify(response)

    except Exception as e:
        logging.error(f"❌ Error in /api/compare-news: {str(e)}")
        return jsonify({
            "status": "error",
            "error": "Internal Server Error",
            "message": "Please try again later"
        }), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_text():
    try:
        if not request.is_json:
            return jsonify({"error": "Invalid request format. Expected JSON"}), 400

        data = request.get_json()
        text = data.get("text", "").strip()
        if not text or len(text) < 50:
            return jsonify({"error": "Text too short for analysis (minimum 50 characters)"}), 400

        analysis_result = analyze_article_content(text, "Custom Text Analysis", datetime.now())
        if not analysis_result:
            return jsonify({"error": "Could not analyze text"}), 400

        response = {
            **analysis_result,
            "source": "User-provided text",
            "credibility": "N/A"
        }

        return jsonify(response)

    except Exception as e:
        logging.error(f"❌ Error in /api/analyze: {str(e)}")
        return jsonify({"error": "Internal Server Error"}), 500

@app.route('/api/source-check', methods=['POST'])
def check_source():
    try:
        if not request.is_json:
            return jsonify({"error": "Invalid request format. Expected JSON"}), 400

        data = request.get_json()
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"error": "No URL provided"}), 400

        domain = extract_domain(url)
        credibility = TRUSTED_SOURCES.get(domain, "Unknown")

        return jsonify({
            "source": domain,
            "credibility": credibility,
            "status": "success"
        })

    except Exception as e:
        logging.error(f"❌ Error in /api/source-check: {str(e)}")
        return jsonify({"error": "Internal Server Error"}), 500

@app.route('/')
def home():
    return render_template('index.html')

if __name__ == '__main__':
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(debug=debug_mode, host="0.0.0.0", port=5000)




























