import asyncio
import re
from crawl4ai import *
import os

def sanitize_filename(text):
   
    text = re.sub(r"\*+", "", text)
    text = text.strip().replace(" ", "_")
    text = re.sub(r"[\[\]\(\)]+", "", text)
    text = re.sub(r"[\u2013\u2014]", "-", text) 
    swedish_map = {'å':'a','ä':'a','ö':'o','Å':'A','Ä':'A','Ö':'O'}
    text = re.sub(r"[\u00e5\u00e4\u00f6\u00c5\u00c4\u00d6]", lambda m: swedish_map[m.group(0)], text)
    text = re.sub(r"[^\w\-]", "", text)
    return text

async def main():
    
    with open("lagen-hompage.md", encoding="utf-8") as f:
        content = f.read()
   
    links = re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", content)
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    async with AsyncWebCrawler() as crawler:
        for link_text, url in links:
            filename = sanitize_filename(link_text) + ".md"
            filepath = os.path.join(output_dir, filename)
            print(f"Scraping {url} -> {filepath}")
            try:
                result = await crawler.arun(url=url)
                with open(filepath, "w", encoding="utf-8") as outf:
                    outf.write(result.markdown)
            except Exception as e:
                print(f"Failed to scrape {url}: {e}")

if __name__ == "__main__":
    asyncio.run(main())