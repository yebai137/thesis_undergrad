#!/usr/bin/env python3
"""Parse v2 AIGC report HTML from Weipu and extract flagged segments."""
import re
import json
import sys
from html.parser import HTMLParser

HTML_PATH = "/home/ywj/elevator_ai/thesis_undergrad/aigc_feedback_v2/report.html"
OUT_PATH = "/home/ywj/elevator_ai/thesis_undergrad/finish/v2_retry_aigc_report_segments.json"

class WzbzParser(HTMLParser):
    """Extract text from wzbz_content section, tracking font_color_purple spans."""
    def __init__(self):
        super().__init__()
        self.in_wzbz = False
        self.in_title = False
        self.in_purple = False
        self.depth = 0
        self.segments = []  # list of (text, is_aigc)
        self.current_text = ""
        self.current_is_aigc = False
        self.titles = []
        self.current_title = ""
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        
        if "wzbz_content" in cls:
            self.in_wzbz = True
            self.depth = 0
            return
            
        if "wzbz_title" in cls:
            self.in_title = True
            self.current_title = ""
            return
            
        if self.in_wzbz:
            if tag == "div":
                self.depth += 1
            if "font_color_purple" in cls:
                # Flush non-AIGC text
                if self.current_text.strip():
                    self.segments.append({
                        "text": self.current_text.strip(),
                        "is_aigc": False
                    })
                    self.current_text = ""
                self.in_purple = True
                self.current_is_aigc = True
                
    def handle_endtag(self, tag):
        if self.in_title and tag == "div":
            self.titles.append(self.current_title.strip())
            self.in_title = False
            return
            
        if self.in_wzbz:
            if tag == "span" and self.in_purple:
                # Flush AIGC text
                if self.current_text.strip():
                    self.segments.append({
                        "text": self.current_text.strip(),
                        "is_aigc": True
                    })
                    self.current_text = ""
                self.in_purple = False
                self.current_is_aigc = False
            if tag == "div":
                self.depth -= 1
                if self.depth < 0:
                    # Flush remaining
                    if self.current_text.strip():
                        self.segments.append({
                            "text": self.current_text.strip(),
                            "is_aigc": self.current_is_aigc
                        })
                        self.current_text = ""
                    self.in_wzbz = False
                    
    def handle_data(self, data):
        if self.in_title:
            self.current_title += data
        if self.in_wzbz:
            self.current_text += data


class PdfbParser(HTMLParser):
    """Extract segments from pdfb (片段分布) section."""
    def __init__(self):
        super().__init__()
        self.in_pdfb = False
        self.in_text_box = False
        self.severity = None
        self.in_main_text = False
        self.segments = []
        self.current_text = ""
        self.depth = 0
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        
        if "pdfb_box" in cls:
            self.in_pdfb = True
            return
            
        if self.in_pdfb:
            if "pdfb_text_box" in cls:
                self.in_text_box = True
                if "severe" in cls:
                    self.severity = "severe"
                elif "moderate" in cls:
                    self.severity = "moderate"
                elif "mild" in cls:
                    self.severity = "mild"
                else:
                    self.severity = "unknown"
                self.current_text = ""
                    
            if "pdfb_main_text" in cls:
                self.in_main_text = True
                self.current_text = ""
                    
    def handle_endtag(self, tag):
        if self.in_main_text and tag == "div":
            if self.current_text.strip():
                self.segments.append({
                    "text": self.current_text.strip(),
                    "severity": self.severity
                })
            self.in_main_text = False
            
        if self.in_text_box and tag == "div" and not self.in_main_text:
            self.in_text_box = False
                    
    def handle_data(self, data):
        if self.in_main_text:
            self.current_text += data


def parse_report(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract overall stats
    aigc_match = re.search(r'(\d+\.?\d*)%.*?全文疑似.*?AIGC.*?生成', content, re.DOTALL)
    aigc_pct = float(aigc_match.group(1)) if aigc_match else None
    
    # Parse wzbz section (full text with AIGC annotations)
    wzbz_parser = WzbzParser()
    wzbz_parser.feed(content)
    
    # Parse pdfb section (fragment distribution)
    pdfb_parser = PdfbParser()
    pdfb_parser.feed(content)
    
    # Also extract from the fake_table sections (疑似片段汇总)
    # Parse the table rows
    table_segments = []
    # Find yspdhz (疑似片段汇总) section
    table_pattern = re.compile(
        r'<div class="fake_table_tr clear">(.*?)</div>\s*</div>',
        re.DOTALL
    )
    
    result = {
        "source": html_path,
        "summary": {
            "aigc_percent": aigc_pct,
        },
        "wzbz_segments": wzbz_parser.segments,
        "wzbz_titles": wzbz_parser.titles,
        "pdfb_segments": pdfb_parser.segments,
    }
    
    return result


if __name__ == "__main__":
    result = parse_report(HTML_PATH)
    
    print(f"AIGC%: {result['summary']['aigc_percent']}")
    print(f"WZBZ segments: {len(result['wzbz_segments'])}")
    print(f"  - AIGC flagged: {sum(1 for s in result['wzbz_segments'] if s.get('is_aigc'))}")
    print(f"  - Clean: {sum(1 for s in result['wzbz_segments'] if not s.get('is_aigc'))}")
    print(f"PDFB segments: {len(result['pdfb_segments'])}")
    print(f"Titles: {result['wzbz_titles']}")
    
    # Show AIGC segments
    print("\n=== AIGC-flagged segments ===")
    for i, seg in enumerate(result['wzbz_segments']):
        if seg.get('is_aigc'):
            text = seg['text'][:120]
            print(f"  [{i}] {text}...")
    
    print(f"\n=== PDFB segments (by severity) ===")
    for seg in result['pdfb_segments']:
        text = seg['text'][:100]
        print(f"  [{seg['severity']}] {text}...")
    
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUT_PATH}")
