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
             return jsonify({'error': 'Could not fetch URL'}), 400
        
        # Extract metadata and main content with trafilatura
        # include_images=True to keep image placeholders, formatted=True keeps some structure
        content = trafilatura.extract(downloaded, include_images=True, include_formatting=True, output_format='xml')
        
        if not content:
             return jsonify({'error': 'Could not extract content'}), 400

        # Post-process with BeautifulSoup to fine-tune HTML for WordPress
        # Trafilatura returns XML, we want to parse it and output clean HTML
        soup = BeautifulSoup(content, 'xml') # Input is XML from trafilatura
        
        # Create a new clean HTML container
        clean_html = BeautifulSoup("<div></div>", "html.parser")
        
        # We can also get the title
        title = ""
        # Trafilatura extract() doesn't return title separately easily if we ask for XML content directly, 
        # but we can do a lighter extract for metadata if needed, 
        # or just rely on what trafilatura gives in the XML root.
        # Let's try to extract metadata separately to be sure.
        metadata = trafilatura.extract_metadata(downloaded)
        if metadata:
            title = metadata.title

        # Convert trafilatura XML tags to standard HTML tags if needed or just use the body
        # Trafilatura XML output structure: <doc> <main> ... </main> </doc>
        # Inside main: <p>, <head rend="h1">, <graphic src="...">, etc.
        
        # Let's write a converter/cleaner
        # Actually trafilatura `output_format='html'` might be easier but sometimes it strips too much or is weird.
        # Let's try output_format='html' first, it's usually decent.
        
        html_content = trafilatura.extract(downloaded, include_images=True, output_format='html')
        
        if not html_content:
             return jsonify({'error': 'Could not extract HTML content'}), 400

        # Now clean up with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Improve formatting for WordPress
        # 1. Ensure images have src
        # 2. Ensure headings look right
        
        # Remove empty tags
        for tag in soup.find_all():
            if len(tag.get_text(strip=True)) == 0 and tag.name not in ['img', 'br', 'hr']:
                tag.decompose()
                
        # Return the cleaned HTML
        final_html = str(soup)
        
        return jsonify({
            'title': title,
            'content': final_html
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)
