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
        try:
            soup_pre = BeautifulSoup(downloaded, 'html.parser')
            
            # 1. Remove scripts and styles first to clean up
            for script in soup_pre(["script", "style"]):
                script.extract()

            # 2. Aggressively fix images
            for img in soup_pre.find_all('img'):
                # List of attributes to check for real image URL
                # Order matters: check most likely candidates first
                candidates = ['data-src', 'data-original', 'data-lazy-src', 'data-url', 'data-src-large', 'data-src-medium', 'src']
                
                real_src = None
                for attr in candidates:
                    val = img.get(attr)
                    if val and val.startswith('http') and 'gif' not in val: # Simple filter for placeholders
                        real_src = val
                        break
                
                if real_src:
                    img['src'] = real_src
                    # Clean up other attributes to avoid confusion
                    for attr in candidates:
                        if attr != 'src' and img.has_attr(attr):
                            del img[attr]
            
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
        # include_images=True is critical
        html_content = trafilatura.extract(
            downloaded, 
            include_images=True, 
            include_links=True,
            include_formatting=True, # Preserve bold, italic, etc.
            output_format='html'
        )
        
        # Validation: Check if trafilatura did a good job
        # If no content or (no images found BUT we know there are images), try fallback
        use_fallback = False
        if not html_content:
            use_fallback = True
        elif '<img' not in html_content and len(soup_pre.find_all('img')) > 0:
            # Trafilatura stripped all images? Suspicious for a news site.
            # Check specifically for VnExpress-like structures
            if 'vnexpress.net' in url or 'fck_detail' in downloaded:
                use_fallback = True

        if use_fallback:
            print("Trafilatura failed or stripped images. Using BeautifulSoup fallback.")
            try:
                soup = BeautifulSoup(downloaded, 'html.parser')
                
                # Try to find the main content container
                # Common candidates: article, .fck_detail (VnExpress), .content, #content
                content_node = None
                selectors = ['article', '.fck_detail', '.content-detail', '#content', '.post-content', '.entry-content']
                
                for selector in selectors:
                    content_node = soup.select_one(selector)
                    if content_node:
                        break
                
                if content_node:
                    # VnExpress-specific: Convert slide show divs to img tags
                    if 'vnexpress.net' in url:
                        # Type 1: item_slide_show with img data-src
                        for slide in content_node.select('.item_slide_show'):
                            # Find img tags with data-src inside the slide
                            img_tag = slide.find('img')
                            if img_tag:
                                src = img_tag.get('data-src') or img_tag.get('src')
                                if src and src.startswith('http'):
                                    # Create a clean img tag
                                    new_img = soup.new_tag('img', src=src)
                                    # Get caption if exists
                                    caption = slide.select_one('.desc_cation')
                                    if caption:
                                        # Replace the slide with img + caption
                                        slide.replace_with(new_img)
                                        new_img.insert_after(caption)
                                    else:
                                        slide.replace_with(new_img)
                        
                        # Type 2: figure.tplCaption with meta tag containing URL
                        for figure in content_node.select('figure.tplCaption'):
                            # Look for meta itemprop="url" inside
                            meta_url = figure.find('meta', itemprop='url')
                            if meta_url and meta_url.get('content'):
                                img_url = meta_url.get('content')
                                if img_url.startswith('http'):
                                    # Create new img tag
                                    new_img = soup.new_tag('img', src=img_url)
                                    # Get caption (figcaption)
                                    caption = figure.find('figcaption')
                                    if caption:
                                        # Replace figure with img + caption
                                        figure.replace_with(new_img)
                                        new_img.insert_after(caption)
                                    else:
                                        figure.replace_with(new_img)
                    
                    # Clean up the fallback content
                    # Remove hidden elements, scripts, styles
                    for tag in content_node.select('script, style, .hidden, [style*="display: none"]'):
                        tag.decompose()
                        
                    # Remove empty paragraphs
                    for tag in content_node.find_all('p'):
                        if not tag.get_text(strip=True) and not tag.find('img'):
                            tag.decompose()
                            
                    html_content = str(content_node)
            except Exception as e:
                print(f"Fallback extraction failed: {e}")
                # If fallback fails, revert to whatever trafilatura found (if anything)
                if not html_content and not use_fallback: 
                     # If we were forcing fallback but it failed, and trafilatura had something, use it.
                     # But here 'html_content' is already from trafilatura (or None).
                     pass

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
