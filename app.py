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

        # Download content
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
             return jsonify({'error': 'Could not fetch URL. Please check if the URL is accessible.'}), 400
        
        # Pre-process to fix lazy loading BEFORE trafilatura runs
        # This is crucial because trafilatura might strip images without src attributes
        try:
            soup_pre = BeautifulSoup(downloaded, 'html.parser')
            for img in soup_pre.find_all('img'):
                lazy_attrs = ['data-src', 'data-original', 'data-lazy-src', 'data-url', 'data-src-large', 'data-src-medium']
                for attr in lazy_attrs:
                    val = img.get(attr)
                    if val:
                        img['src'] = val
                        # Remove the lazy attribute to avoid confusion
                        del img[attr]
                        break
            downloaded = str(soup_pre)
        except Exception as e:
            print(f"Pre-processing failed: {e}")

        # Extract metadata
        title = "No Title Found"
        try:
            metadata = trafilatura.extract_metadata(downloaded)
            if metadata and metadata.title:
                title = metadata.title
        except Exception as e:
            print(f"Metadata extraction failed: {e}")
        
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

        # Post-process cleanup
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
