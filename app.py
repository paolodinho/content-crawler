from flask import Flask, render_template, request, jsonify
import trafilatura
from bs4 import BeautifulSoup
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/crawl', methods=['POST'])
def crawl():
    try:
        data = request.json
        url = data.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400

        # Download and extract content using trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
             return jsonify({'error': 'Could not fetch URL. Please check if the URL is accessible.'}), 400
        
        # Extract metadata first
        title = "No Title Found"
        try:
            metadata = trafilatura.extract_metadata(downloaded)
            if metadata and metadata.title:
                title = metadata.title
        except Exception as e:
            print(f"Metadata extraction failed: {e}")
            # Continue anyway, we'll just use default title
        
        # Extract main content with trafilatura
        html_content = trafilatura.extract(
            downloaded, 
            include_images=True, 
            include_links=True,
            output_format='html'
        )
        
        if not html_content:
             return jsonify({
                 'error': 'Could not extract content from this page. The page might be empty or protected.'
             }), 400

        # Clean up with BeautifulSoup
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove empty tags
            for tag in soup.find_all():
                if len(tag.get_text(strip=True)) == 0 and tag.name not in ['img', 'br', 'hr']:
                    tag.decompose()
                    
            # Return the cleaned HTML
            final_html = str(soup)
        except Exception as e:
            print(f"HTML cleanup failed: {e}")
            # If cleanup fails, just use the raw extracted HTML
            final_html = html_content
        
        return jsonify({
            'title': title if title else "No Title Found",
            'content': final_html if final_html else "<p>No content extracted</p>"
        })

    except Exception as e:
        # Always return JSON, even on error
        print(f"Crawl error: {e}")
        return jsonify({
            'error': f'An error occurred while crawling: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)
