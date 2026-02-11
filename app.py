from flask import Flask, render_template, request, jsonify
import trafilatura
from bs4 import BeautifulSoup
import requests
import re

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

        # Step 1: Download raw HTML using trafilatura (handles SSL/encoding well)
        raw_html = trafilatura.fetch_url(url)
        if not raw_html:
            return jsonify({'error': 'Could not fetch URL. Please check if the URL is accessible.'}), 400

        # Step 2: Quick regex-based lazy-load fix (fast, no full HTML parsing)
        # Replace data-src="..." with src="..." for images that only have data-src
        fixed_html = re.sub(
            r'<img([^>]*?)data-src="([^"]+)"',
            r'<img\1src="\2"',
            raw_html
        )
        # Also handle data-original
        fixed_html = re.sub(
            r'<img([^>]*?)data-original="([^"]+)"',
            r'<img\1src="\2"',
            fixed_html
        )

        # Step 3: Extract metadata
        title = "No Title Found"
        try:
            metadata = trafilatura.extract_metadata(fixed_html)
            if metadata and metadata.title:
                title = metadata.title
        except Exception as e:
            print(f"Metadata extraction failed: {e}")

        # Step 4: Try trafilatura extraction first
        html_content = trafilatura.extract(
            fixed_html,
            include_images=True,
            include_links=True,
            include_formatting=True,
            output_format='html'
        )

        # Step 5: Check if trafilatura got images
        has_images = html_content and '<img' in html_content
        
        if not has_images:
            print(f"Trafilatura {'returned no content' if not html_content else 'stripped images'}. Using BeautifulSoup fallback.")
            fallback_content = extract_with_fallback(fixed_html, url)
            if fallback_content:
                html_content = fallback_content

        if not html_content:
            return jsonify({
                'error': 'Could not extract content from this page. The page might be empty or protected.'
            }), 400

        # Step 6: Post-process cleanup
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove empty tags (but keep images and their parents)
            for tag in soup.find_all():
                if tag.name in ['img', 'br', 'hr', 'figure']:
                    continue
                if len(tag.get_text(strip=True)) == 0 and not tag.find('img'):
                    tag.decompose()

            final_html = str(soup)
        except Exception as e:
            print(f"HTML cleanup failed: {e}")
            final_html = html_content

        return jsonify({
            'title': title if title else "No Title Found",
            'content': final_html if final_html else "<p>No content extracted</p>"
        })

    except Exception as e:
        print(f"Crawl error: {e}")
        return jsonify({
            'error': f'An error occurred while crawling: {str(e)}'
        }), 500


def extract_with_fallback(html, url):
    """
    Fallback extraction using BeautifulSoup when trafilatura fails to get images.
    Targets the main content container of the page.
    """
    try:
        soup = BeautifulSoup(html, 'lxml')

        # Find the main content container
        # Order matters: more specific selectors first
        selectors = [
            '.fck_detail',           # VnExpress
            '.detail-content',       # TheThaoVanHoa, Soha
            '[data-role="content"]',  # Generic data-role
            'article .entry-content',# WordPress
            '.post-content',         # Generic blog
            '.entry-content',        # WordPress
            '.content-detail',       # Some VN sites
            '#content',              # Generic
            'article',               # Semantic
        ]

        content_node = None
        for selector in selectors:
            content_node = soup.select_one(selector)
            if content_node:
                print(f"Fallback: Found content with selector '{selector}'")
                break

        if not content_node:
            print("Fallback: No content container found")
            return None

        # --- Site-specific image handling ---

        # VnExpress: slide shows with data-src
        for slide in content_node.select('.item_slide_show'):
            img_tag = slide.find('img')
            if img_tag:
                src = img_tag.get('data-src') or img_tag.get('src')
                if src and src.startswith('http'):
                    new_img = soup.new_tag('img', src=src)
                    caption = slide.select_one('.desc_cation')
                    if caption:
                        slide.replace_with(new_img)
                        new_img.insert_after(caption)
                    else:
                        slide.replace_with(new_img)

        # VnExpress: figure.tplCaption with meta itemprop="url"
        for figure in content_node.select('figure.tplCaption, figure[itemprop="associatedMedia"]'):
            meta_url = figure.find('meta', itemprop='url')
            if meta_url and meta_url.get('content'):
                img_url = meta_url.get('content')
                if img_url.startswith('http'):
                    new_img = soup.new_tag('img', src=img_url)
                    caption = figure.find('figcaption')
                    if caption:
                        figure.replace_with(new_img)
                        new_img.insert_after(caption)
                    else:
                        figure.replace_with(new_img)

        # --- General cleanup ---
        
        # Remove unwanted elements
        for tag in content_node.select('script, style, iframe, .hidden, .ads, .advertisement, .social-share, .related-news, .box-tinlienquan'):
            tag.decompose()

        # Remove empty paragraphs (but keep ones with images)
        for tag in content_node.find_all('p'):
            if not tag.get_text(strip=True) and not tag.find('img'):
                tag.decompose()

        result = str(content_node)
        
        # Verify we got images
        if '<img' in result:
            print(f"Fallback: Successfully extracted content with images")
        else:
            print(f"Fallback: Content extracted but still no images")
            
        return result

    except Exception as e:
        print(f"Fallback extraction failed: {e}")
        return None


if __name__ == '__main__':
    app.run(debug=True, port=8000)
