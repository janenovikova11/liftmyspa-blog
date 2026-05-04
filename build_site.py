#!/usr/bin/env python3
"""
build_site.py — Lift My Spa Blog static site generator

Reads:
  - articles/*.md         (102 markdown articles with YAML frontmatter)
  - SAIO Article Plan.csv (canonical metadata + cluster assignments)
  - design/brand.css      (shared styles)
  - design/logo-*.png/webp, design/favicon* (assets)

Writes to: site/
  - index.html               blog index listing all articles
  - <slug>.html              one HTML file per article
  - sitemap.xml              full sitemap including main domain pages
  - robots.txt               allow all + sitemap location
  - feed.xml                 RSS 2.0 feed
  - 404.html                 friendly 404
  - _redirects               Cloudflare Pages redirects file
  - brand.css, logos, favicons (copied)

Usage:
  python3 build_site.py
"""

import csv
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import markdown
import yaml

# ============================================================
# Config
# ============================================================
ROOT = Path("/Users/janenovikova/Downloads/Lift My Spa")
ARTICLES_DIR = ROOT / "articles"
DESIGN_DIR = ROOT / "design"
CSV_PATH = ROOT / "SAIO Article Plan.csv"
OUT_DIR = ROOT / "site"

SITE_DOMAIN = "https://blog.liftmyspa.com"
MAIN_DOMAIN = "https://liftmyspa.com"
BRAND_NAME = "Lift My Spa"
BRAND_TAGLINE = "AI plus Marketing Automation Built for Med Spas"
DEMO_URL = "https://liftmyspa.com/demo-call-page"
PHONE = "+19188514816"
PHONE_DISPLAY = "+1 (918) 851-4816"
PUBLISH_DATE = "2026-05-04"

CATEGORY_LABELS = {
    "National Pillar": "AI Front Desk",
    "State": "State",
    "Major Metro": "City",
    "Town/Suburb": "City",
    "Pain-Point": "Marketing Automation",
    "Service-Specific": "Service Marketing",
    "Comparison": "Comparisons",
    "Compliance": "Compliance",
}

# Category filter list shown in the index nav
INDEX_CATEGORIES = [
    "All Articles",
    "AI Front Desk",
    "Marketing Automation",
    "State",
    "City",
    "Compliance",
    "Service Marketing",
    "Comparisons",
]

# ============================================================
# Read articles + CSV
# ============================================================
def load_csv():
    """Load the SAIO plan CSV — gives us cluster + airoLevel + canonical metadata."""
    by_slug = {}
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            by_slug[row["Slug"]] = {
                "num": int(row["#"]),
                "cluster": row["Cluster"],
                "airo": row["AIRO Level"],
                "title": row["Title"],
                "keywords": [k.strip() for k in row["Keywords"].split(",")],
                "slug": row["Slug"],
                "meta_title": row["Meta Title"],
                "meta_description": row["Meta Description"],
            }
    return by_slug


def parse_frontmatter(fm_text):
    """Lenient frontmatter parser - handles colons in titles, etc."""
    fm = {}
    for line in fm_text.split("\n"):
        line = line.rstrip()
        if not line:
            continue
        m = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$', line)
        if not m:
            continue
        key = m.group(1)
        value = m.group(2).strip()
        # Strip surrounding quotes
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        fm[key] = value
    return fm


def parse_article(path, csv_meta):
    """Parse an article markdown file. Returns dict with frontmatter + html body."""
    text = path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not fm_match:
        raise ValueError(f"No frontmatter in {path}")
    fm = parse_frontmatter(fm_match.group(1))
    body_md = fm_match.group(2).strip()

    # Convert markdown to HTML
    md = markdown.Markdown(extensions=["extra", "smarty", "toc", "sane_lists"])
    body_html = md.convert(body_md)

    slug = path.stem
    meta = csv_meta.get(slug, {})

    # Prefer CSV title (always clean), fallback to frontmatter, strip brand suffix
    raw_title = meta.get("title") or fm.get("title", "")
    clean_title = re.sub(r"\s*\|\s*Lift My Spa\s*$", "", raw_title).strip()

    return {
        "slug": slug,
        "title": clean_title,
        "url_path": fm.get("url", f"/{slug}"),
        "meta_title": fm.get("metaTitle") or meta.get("meta_title", ""),
        "meta_description": fm.get("metaDescription") or meta.get("meta_description", ""),
        "image": fm.get("image", ""),
        "image_alt": fm.get("imageAlt", ""),
        "cluster": meta.get("cluster", "National Pillar"),
        "airo": meta.get("airo", "L2"),
        "keywords": meta.get("keywords", []),
        "category": CATEGORY_LABELS.get(meta.get("cluster", ""), "Marketing Automation"),
        "body_html": body_html,
        "toc": md.toc if hasattr(md, "toc") else "",
        "headings": getattr(md, "toc_tokens", []),
    }


def location_from(article):
    """Extract a location label like 'Phoenix, AZ' from title or cluster."""
    t = article["title"]
    # Patterns
    m = re.search(r"(?:in|for) ([A-Z][a-zA-Z. ]+? Med Spas?)", t)
    if m:
        loc = m.group(1).replace(" Med Spas", "").replace(" Med Spa", "").strip()
        # Add state hint
        state_hint = ""
        if article["cluster"] == "Major Metro" or article["cluster"] == "Town/Suburb":
            # heuristic state lookup based on slug words
            slug = article["slug"]
            az_keys = ["phoenix","scottsdale","tucson","paradise-valley","chandler","gilbert","tempe","mesa","glendale-az","sedona","flagstaff","arizona","maricopa"]
            tx_keys = ["houston","dallas","fort-worth","austin","san-antonio","woodlands","sugar-land","katy","pearland","plano","frisco","mckinney","southlake","round-rock","lakeway","texas"]
            fl_keys = ["miami","fort-lauderdale","orlando","tampa","jacksonville","coral-gables","aventura","brickell","doral","boca-raton","weston","naples","sarasota","winter-park","palm-beach","florida"]
            ok_keys = ["oklahoma-city","tulsa","edmond","norman","broken-arrow","bixby","owasso","oklahoma"]
            sl = slug.lower()
            if any(k in sl for k in az_keys): state_hint = ", AZ"
            elif any(k in sl for k in tx_keys): state_hint = ", TX"
            elif any(k in sl for k in fl_keys): state_hint = ", FL"
            elif any(k in sl for k in ok_keys): state_hint = ", OK"
        return loc + state_hint
    if "Texas" in t: return "Texas"
    if "Florida" in t: return "Florida"
    if "Arizona" in t: return "Arizona"
    if "Oklahoma" in t: return "Oklahoma"
    return ""


# ============================================================
# Cross-linking
# ============================================================
def state_of(slug):
    sl = slug.lower()
    if any(k in sl for k in ["phoenix","scottsdale","tucson","paradise-valley","chandler","gilbert","tempe","mesa","glendale-az","sedona","flagstaff","arizona","maricopa"]):
        return "AZ"
    if any(k in sl for k in ["houston","dallas","fort-worth","austin","san-antonio","woodlands","sugar-land","katy","pearland","plano","frisco","mckinney","southlake","round-rock","lakeway","texas","tdlr","tmb"]):
        return "TX"
    if any(k in sl for k in ["miami","fort-lauderdale","orlando","tampa","jacksonville","coral-gables","aventura","brickell","doral","boca-raton","weston","naples","sarasota","winter-park","palm-beach","florida"]):
        return "FL"
    if any(k in sl for k in ["oklahoma","tulsa","edmond","norman","broken-arrow","bixby","owasso","okc"]):
        return "OK"
    return None


def metro_of(slug):
    """Group town slugs into their metro pillar."""
    sl = slug.lower()
    # AZ
    if any(k in sl for k in ["paradise-valley","chandler","gilbert","tempe","mesa","glendale-az"]):
        return "best-ai-front-desk-phoenix-med-spas"
    if any(k in sl for k in ["sedona","flagstaff"]):
        return "best-marketing-system-tucson-med-spas"
    # TX Houston
    if any(k in sl for k in ["woodlands","sugar-land","katy","pearland"]):
        return "best-marketing-system-houston-med-spas"
    # TX Dallas/DFW
    if any(k in sl for k in ["plano","frisco","mckinney","southlake"]):
        return "best-marketing-platform-dallas-med-spas"
    # TX Austin
    if any(k in sl for k in ["round-rock","lakeway"]):
        return "best-med-spa-marketing-software-austin"
    # FL Miami
    if any(k in sl for k in ["coral-gables","aventura","brickell","doral"]):
        return "best-marketing-platform-miami-med-spas"
    # FL Broward / Boca / PB
    if any(k in sl for k in ["weston"]):
        return "best-marketing-system-fort-lauderdale-med-spas"
    if any(k in sl for k in ["boca-raton","palm-beach"]):
        return "best-marketing-platform-palm-beach-gardens-med-spas" if "palm-beach" in sl else "best-marketing-system-fort-lauderdale-med-spas"
    # FL West coast
    if any(k in sl for k in ["naples","sarasota"]):
        return "best-med-spa-marketing-system-tampa"
    # FL Orlando
    if any(k in sl for k in ["winter-park"]):
        return "best-marketing-platform-orlando-med-spas"
    # OK Tulsa-area
    if any(k in sl for k in ["broken-arrow","bixby","owasso"]):
        return "best-marketing-system-tulsa-med-spas"
    # OK Norman → OKC
    if "norman" in sl:
        return "best-marketing-platform-oklahoma-city-med-spas"
    return None


def state_pillar(state):
    return {
        "AZ": "best-marketing-system-med-spas-arizona",
        "TX": "best-marketing-system-med-spas-texas",
        "FL": "best-marketing-system-med-spas-florida",
        "OK": "best-marketing-system-med-spas-oklahoma",
    }.get(state)


def compute_related(articles_by_slug):
    """For each article, return up to 3 related slugs."""
    related = {}
    by_cluster = {}
    for slug, a in articles_by_slug.items():
        by_cluster.setdefault(a["cluster"], []).append(slug)

    for slug, a in articles_by_slug.items():
        rel = []
        cluster = a["cluster"]
        st = state_of(slug)

        if cluster == "Town/Suburb":
            metro = metro_of(slug)
            if metro and metro != slug and metro in articles_by_slug:
                rel.append(metro)
            sp = state_pillar(st) if st else None
            if sp and sp != slug and sp in articles_by_slug and sp not in rel:
                rel.append(sp)
            # Add a sibling town in same metro
            for s in by_cluster.get("Town/Suburb", []):
                if s != slug and metro_of(s) == metro and s not in rel:
                    rel.append(s); break
            # Pad with another town from same state
            for s in by_cluster.get("Town/Suburb", []):
                if s != slug and state_of(s) == st and s not in rel:
                    rel.append(s)
                    if len(rel) >= 3: break

        elif cluster == "Major Metro":
            sp = state_pillar(st) if st else None
            if sp and sp != slug and sp in articles_by_slug:
                rel.append(sp)
            # Add 2 towns that map to this metro
            for s in by_cluster.get("Town/Suburb", []):
                if metro_of(s) == slug and s not in rel:
                    rel.append(s)
                    if len(rel) >= 3: break
            # Pad with another metro in same state
            if len(rel) < 3:
                for s in by_cluster.get("Major Metro", []):
                    if s != slug and state_of(s) == st and s not in rel:
                        rel.append(s)
                        if len(rel) >= 3: break

        elif cluster == "State":
            # Show 3 metros from that state
            for s in by_cluster.get("Major Metro", []):
                if state_of(s) == st and s not in rel:
                    rel.append(s)
                    if len(rel) >= 3: break
            # Pad with the state compliance article
            if len(rel) < 3:
                for s in by_cluster.get("Compliance", []):
                    if state_of(s) == st and s not in rel:
                        rel.append(s)
                        if len(rel) >= 3: break

        elif cluster == "Compliance":
            # Other compliance + state pillar
            for s in by_cluster.get("Compliance", []):
                if s != slug and s not in rel:
                    rel.append(s)
                    if len(rel) >= 2: break
            sp = state_pillar(st) if st else None
            if sp and sp != slug and sp in articles_by_slug and sp not in rel:
                rel.append(sp)

        elif cluster == "Comparison":
            for s in by_cluster.get("Comparison", []):
                if s != slug and s not in rel:
                    rel.append(s)
                    if len(rel) >= 2: break
            for s in by_cluster.get("National Pillar", []):
                if s not in rel:
                    rel.append(s)
                    if len(rel) >= 3: break

        elif cluster == "Service-Specific":
            for s in by_cluster.get("Service-Specific", []):
                if s != slug and s not in rel:
                    rel.append(s)
                    if len(rel) >= 2: break
            for s in by_cluster.get("National Pillar", []):
                if s not in rel:
                    rel.append(s)
                    if len(rel) >= 3: break

        elif cluster == "Pain-Point":
            for s in by_cluster.get("Pain-Point", []):
                if s != slug and s not in rel:
                    rel.append(s)
                    if len(rel) >= 2: break
            for s in by_cluster.get("National Pillar", []):
                if s not in rel:
                    rel.append(s)
                    if len(rel) >= 3: break

        elif cluster == "National Pillar":
            for s in by_cluster.get("National Pillar", []):
                if s != slug and s not in rel:
                    rel.append(s)
                    if len(rel) >= 3: break

        related[slug] = rel[:3]
    return related


# ============================================================
# Templates
# ============================================================
def header_html(active_blog=True):
    return f"""<header class="site-header">
  <div class="container site-header-inner">
    <a href="{MAIN_DOMAIN}" class="logo">
      <img src="logo-red.png" alt="{BRAND_NAME}">
    </a>
    <nav>
      <ul class="main-nav">
        <li><a href="{MAIN_DOMAIN}">Home</a></li>
        <li><a href="/" class="{'active' if active_blog else ''}">Blog</a></li>
      </ul>
    </nav>
    <div class="header-cta">
      <span class="header-region">AZ &middot; TX &middot; FL &middot; OK</span>
      <a href="{DEMO_URL}" class="btn btn-primary btn-sm">Contact Us</a>
    </div>
  </div>
</header>
"""


def footer_html():
    return f"""<footer class="site-footer">
  <div class="container">
    <div class="footer-top">
      <a href="{MAIN_DOMAIN}" class="footer-logo">
        <img src="logo-white.webp" alt="{BRAND_NAME}">
      </a>
      <nav class="footer-nav">
        <a href="{MAIN_DOMAIN}/terms-conditions" target="_blank" rel="noopener noreferrer">Terms &amp; Conditions</a>
        <a href="{MAIN_DOMAIN}/privacy-policy" target="_blank" rel="noopener noreferrer">Privacy Policy</a>
      </nav>
    </div>
    <div class="footer-bottom">
      <p class="footer-copyright">Liftmyspa.com &copy; Copyright. All rights Reserved.</p>
      <p class="footer-disclaimer">All Lift My Spa services are non-clinical and are designed to support marketing and communication for licensed medical spas. We do not provide medical advice, diagnosis, or treatment. Client results may vary. Referral programs, offers, and testimonial use must comply with applicable federal (including HIPAA and FTC) and state regulations (TX, FL, AZ, OK). Review automation, lead generation, and performance metrics are based on reported data and not guaranteed. All tools are designed to follow HIPAA privacy standards and advertising guidelines set by ad platforms and state medical boards. Contact us for compliance details.</p>
    </div>
  </div>
</footer>
"""


def common_head_meta(title, description, canonical_url, image_url, image_alt, og_type="article",
                     published=None, section=None, keywords=None):
    keyword_meta = f'<meta name="keywords" content="{html.escape(", ".join(keywords or []))}">' if keywords else ""
    pub_meta = f'<meta property="article:published_time" content="{published}">' if published else ""
    section_meta = f'<meta property="article:section" content="{html.escape(section)}">' if section else ""

    return f"""<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
{keyword_meta}
<link rel="canonical" href="{canonical_url}">

<!-- Open Graph -->
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{BRAND_NAME}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(description)}">
<meta property="og:url" content="{canonical_url}">
<meta property="og:image" content="{image_url}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{html.escape(image_alt or title)}">
{pub_meta}
{section_meta}

<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html.escape(title)}">
<meta name="twitter:description" content="{html.escape(description)}">
<meta name="twitter:image" content="{image_url}">

<link rel="icon" type="image/x-icon" href="favicon.ico">
<link rel="icon" type="image/png" sizes="192x192" href="favicon-192.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="alternate" type="application/rss+xml" title="{BRAND_NAME} Blog" href="/feed.xml">
<link rel="stylesheet" href="brand.css">
"""


def organization_schema():
    return {
        "@type": "Organization",
        "@id": f"{MAIN_DOMAIN}/#organization",
        "name": BRAND_NAME,
        "url": MAIN_DOMAIN,
        "logo": {
            "@type": "ImageObject",
            "url": f"{SITE_DOMAIN}/logo-red.png",
        },
        "description": "AI plus marketing automation platform built exclusively for medical spas in Texas, Florida, Arizona, and Oklahoma.",
        "telephone": PHONE,
        "areaServed": ["Texas", "Florida", "Arizona", "Oklahoma"],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "523 E Latimer Ct",
            "addressLocality": "Tulsa",
            "addressRegion": "OK",
            "postalCode": "74106",
            "addressCountry": "US",
        },
    }


def article_schema(article, canonical_url, related_count):
    return {
        "@context": "https://schema.org",
        "@graph": [
            organization_schema(),
            {
                "@type": "BlogPosting",
                "@id": f"{canonical_url}#blogposting",
                "isPartOf": {"@id": f"{SITE_DOMAIN}/#blog"},
                "mainEntityOfPage": {"@id": canonical_url},
                "headline": article["title"],
                "name": article["title"],
                "description": article["meta_description"],
                "url": canonical_url,
                "datePublished": PUBLISH_DATE,
                "dateModified": PUBLISH_DATE,
                "image": [article["image"]] if article["image"] else [],
                "keywords": ", ".join(article["keywords"]),
                "articleSection": article["category"],
                "author": {"@id": f"{MAIN_DOMAIN}/#organization"},
                "publisher": {"@id": f"{MAIN_DOMAIN}/#organization"},
                "inLanguage": "en-US",
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": MAIN_DOMAIN},
                    {"@type": "ListItem", "position": 2, "name": "Blog", "item": SITE_DOMAIN + "/"},
                    {"@type": "ListItem", "position": 3, "name": article["category"], "item": SITE_DOMAIN + f"/?cat={article['category'].replace(' ', '-').lower()}"},
                    {"@type": "ListItem", "position": 4, "name": article["title"], "item": canonical_url},
                ],
            }
        ]
    }


def blog_schema(articles):
    return {
        "@context": "https://schema.org",
        "@graph": [
            organization_schema(),
            {
                "@type": "Blog",
                "@id": f"{SITE_DOMAIN}/#blog",
                "url": f"{SITE_DOMAIN}/",
                "name": f"{BRAND_NAME} Blog",
                "description": "AI front desk strategies, marketing playbooks, and compliance guides built only for med spas in Texas, Florida, Arizona, and Oklahoma.",
                "publisher": {"@id": f"{MAIN_DOMAIN}/#organization"},
                "inLanguage": "en-US",
                "blogPost": [
                    {
                        "@type": "BlogPosting",
                        "headline": a["title"],
                        "url": f"{SITE_DOMAIN}/{a['slug']}",
                        "datePublished": PUBLISH_DATE,
                        "image": a["image"],
                        "description": a["meta_description"],
                        "author": {"@id": f"{MAIN_DOMAIN}/#organization"},
                    } for a in articles[:50]  # cap to keep markup manageable
                ],
            }
        ]
    }


def render_article(article, related_articles):
    """Render a single article HTML page."""
    canonical = f"{SITE_DOMAIN}/{article['slug']}"
    head = common_head_meta(
        title=article["meta_title"],
        description=article["meta_description"],
        canonical_url=canonical,
        image_url=article["image"],
        image_alt=article["image_alt"],
        og_type="article",
        published=PUBLISH_DATE,
        section=article["category"],
        keywords=article["keywords"],
    )
    schema = article_schema(article, canonical, len(related_articles))

    location = location_from(article)
    breadcrumb_loc = article["category"]

    # Build TOC from headings (h2 only)
    h2_pattern = re.compile(r'<h2 id="([^"]+)">([^<]+)</h2>')
    h2s = h2_pattern.findall(article["body_html"])
    toc_html = ""
    if h2s:
        toc_items = "\n".join(f'<li><a href="#{i}">{html.escape(t)}</a></li>' for i, t in h2s)
        toc_html = f"""<div class="sidebar-card">
  <h4>On this page</h4>
  <ul class="toc-list">{toc_items}</ul>
</div>"""

    # Build related-articles list
    related_html = ""
    for r in related_articles:
        related_html += f"""<article class="related-card">
  <span class="tag">{html.escape(r['category'])}</span>
  <h3><a href="/{r['slug']}">{html.escape(r['title'])}</a></h3>
  <div class="meta">{html.escape(location_from(r) or r['category'])}</div>
</article>"""

    article_tag_text = f"{article['category']}"
    if location and article['cluster'] in ('Major Metro','Town/Suburb','State'):
        article_tag_text = f"{article['category']} &middot; {location}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{head}
<style>
  .article-hero {{ background: var(--brand-cream); padding: 56px 0 40px; border-bottom: 1px solid var(--neutral-300); }}
  .breadcrumb {{ color: var(--text-muted); font-size: 0.85rem; font-family: var(--headline-font); font-weight: 600; margin-bottom: 20px; }}
  .breadcrumb a {{ color: var(--text-secondary); }}
  .breadcrumb a:hover {{ color: var(--brand-red); }}
  .breadcrumb span {{ margin: 0 8px; color: var(--text-muted); }}
  .article-tag {{ display: inline-block; background: var(--brand-red); color: var(--text-on-red); padding: 6px 14px; border-radius: 999px; font-family: var(--headline-font); font-weight: 700; font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 22px; }}
  .article-title {{ font-size: clamp(2rem, 4.5vw, 3.2rem); line-height: 1.15; margin-bottom: 24px; max-width: 880px; font-weight: 900; }}
  .article-meta {{ display: flex; gap: 24px; flex-wrap: wrap; color: var(--text-secondary); font-size: 0.9rem; font-family: var(--headline-font); font-weight: 600; padding-top: 20px; border-top: 1px solid var(--neutral-300); margin-top: 32px; }}
  .article-meta strong {{ color: var(--text-primary); font-weight: 700; }}
  .article-hero-image {{ background: var(--brand-cream); }}
  .article-hero-image img {{ width: 100%; max-height: 480px; object-fit: cover; border-radius: var(--radius-lg); margin-top: -20px; box-shadow: var(--shadow-md); }}
  .article-hero-image .container {{ padding-bottom: 24px; background: linear-gradient(180deg, var(--brand-cream) 50%, var(--neutral-100) 50%); }}
  .article-body {{ padding: 32px 0 72px; }}
  .article-body-grid {{ display: grid; grid-template-columns: 1fr 280px; gap: 64px; }}
  .article-content {{ font-size: 1.08rem; line-height: 1.78; color: var(--text-primary); }}
  .article-content > p:first-of-type {{ font-size: 1.25rem; color: var(--text-secondary); line-height: 1.6; margin-bottom: 36px; font-weight: 500; }}
  .article-content h2 {{ font-size: 1.7rem; margin: 48px 0 16px; padding-top: 16px; border-top: 3px solid var(--brand-red); display: inline-block; padding-right: 4px; font-weight: 800; }}
  .article-content h3 {{ font-size: 1.25rem; margin: 32px 0 12px; font-weight: 700; }}
  .article-content p {{ margin-bottom: 1.2em; }}
  .article-content ul, .article-content ol {{ margin-bottom: 1.5em; }}
  .article-content li {{ margin-bottom: 8px; }}
  .article-content strong {{ font-weight: 700; color: var(--text-primary); }}
  .article-content a {{ color: var(--brand-red); text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 3px; }}
  .article-content blockquote {{ margin: 32px 0; padding: 24px 28px; background: var(--brand-cream); border-left: 4px solid var(--brand-red); border-radius: var(--radius-sm); font-style: italic; color: var(--text-primary); font-size: 1.05rem; }}
  .article-content blockquote p:last-child {{ margin-bottom: 0; }}
  .inline-cta {{ background: var(--brand-red); color: var(--text-on-red); padding: 36px 32px; border-radius: var(--radius-lg); margin: 40px 0; text-align: center; }}
  .inline-cta h3 {{ color: var(--text-on-red); margin-bottom: 12px; font-weight: 800; }}
  .inline-cta p {{ color: rgba(255,255,255,0.92); margin-bottom: 22px; }}
  .article-sidebar {{ position: sticky; top: 110px; align-self: start; }}
  .sidebar-card {{ background: var(--brand-cream); border-radius: var(--radius-md); padding: 24px; margin-bottom: 24px; }}
  .sidebar-card h4 {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-secondary); margin-bottom: 16px; font-weight: 700; }}
  .sidebar-card.cta-card {{ background: var(--brand-red); color: var(--text-on-red); text-align: center; }}
  .sidebar-card.cta-card h4 {{ color: rgba(255,255,255,0.85); }}
  .sidebar-card.cta-card h3 {{ color: var(--text-on-red); font-size: 1.2rem; margin-bottom: 12px; font-weight: 800; }}
  .sidebar-card.cta-card p {{ color: rgba(255,255,255,0.92); font-size: 0.92rem; margin-bottom: 18px; }}
  .sidebar-card.cta-card .btn {{ background: var(--text-on-red); color: var(--brand-red); width: 100%; }}
  .sidebar-card.cta-card .btn:hover {{ background: var(--brand-cream); color: var(--brand-red-dark); }}
  .toc-list {{ list-style: none; padding: 0; margin: 0; }}
  .toc-list li {{ margin-bottom: 10px; }}
  .toc-list a {{ color: var(--text-primary); font-size: 0.92rem; font-weight: 600; font-family: var(--headline-font); border-left: 2px solid var(--neutral-300); padding-left: 12px; display: block; }}
  .toc-list a:hover {{ color: var(--brand-red); border-left-color: var(--brand-red); }}
  .share-row {{ display:flex; gap:8px; }}
  .share-row a {{ background: var(--neutral-100); padding: 10px 8px; border-radius: var(--radius-sm); flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; font-weight: 700; font-family: var(--headline-font); color: var(--text-primary); text-decoration: none; font-size: 0.82rem; transition: background 0.15s, color 0.15s; cursor: pointer; }}
  .share-row a:hover {{ background: var(--brand-red); color: var(--text-on-red); }}
  .share-row a svg {{ display: block; }}
  .share-row a.copied {{ background: var(--brand-sage); color: var(--brand-red-dark); }}
  @media (max-width: 980px) {{ .article-body-grid {{ grid-template-columns: 1fr; }} .article-sidebar {{ position: static; }} }}
  .related-articles {{ background: var(--brand-cream); padding: 64px 0; }}
  .related-articles h2 {{ margin-bottom: 32px; font-weight: 800; }}
  .related-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }}
  .related-card {{ background: var(--neutral-100); padding: 24px; border-radius: var(--radius-md); transition: transform 0.2s, box-shadow 0.2s; border: 1px solid var(--neutral-300); }}
  .related-card:hover {{ transform: translateY(-4px); box-shadow: var(--shadow-md); border-color: var(--brand-red); }}
  .related-card .tag {{ display: inline-block; background: var(--brand-red-soft); color: var(--brand-red); padding: 4px 10px; border-radius: 999px; font-family: var(--headline-font); font-weight: 700; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 10px; }}
  .related-card h3 {{ font-size: 1.05rem; line-height: 1.35; margin-bottom: 10px; font-weight: 700; }}
  .related-card h3 a {{ color: var(--text-primary); }}
  .related-card h3 a:hover {{ color: var(--brand-red); }}
  .related-card .meta {{ color: var(--text-muted); font-size: 0.8rem; font-family: var(--headline-font); font-weight: 600; }}
  @media (max-width: 880px) {{ .related-grid {{ grid-template-columns: 1fr; }} }}
  .final-cta-section {{ padding: 80px 0; text-align: center; background: var(--neutral-100); }}
  .final-cta-section h2 {{ font-size: clamp(1.8rem, 3.5vw, 2.6rem); margin-bottom: 16px; font-weight: 800; }}
  .final-cta-section p {{ color: var(--text-secondary); font-size: 1.1rem; max-width: 580px; margin: 0 auto 32px; }}
</style>
<script type="application/ld+json">{json.dumps(schema, indent=2)}</script>
</head>
<body>

{header_html(active_blog=True)}

<section class="article-hero">
  <div class="container">
    <nav class="breadcrumb">
      <a href="{MAIN_DOMAIN}">Home</a>
      <span>&rsaquo;</span>
      <a href="/">Blog</a>
      <span>&rsaquo;</span>
      <a href="/?cat={article['category'].replace(' ', '-').lower()}">{html.escape(article['category'])}</a>
    </nav>
    <span class="article-tag">{article_tag_text}</span>
    <h1 class="article-title">{html.escape(article['title'])}</h1>
    <div class="article-meta">
      <span><strong>Published</strong> {datetime.strptime(PUBLISH_DATE, '%Y-%m-%d').strftime('%B %-d, %Y')}</span>
      <span><strong>Region</strong> {html.escape(location or 'United States')}</span>
    </div>
  </div>
</section>

<section class="article-hero-image">
  <div class="container">
    <img src="{article['image']}" alt="{html.escape(article['image_alt'])}">
  </div>
</section>

<section class="article-body">
  <div class="container">
    <div class="article-body-grid">
      <article class="article-content">
{article['body_html']}

        <div class="inline-cta">
          <h3>Ready to see Lift My Spa for your med spa?</h3>
          <p>Book a free 30-minute consultation. We will walk through your funnel, show you the leaks, and demo the AI front desk live.</p>
          <a href="{DEMO_URL}" class="btn btn-light">Schedule Free Consultation</a>
        </div>
      </article>

      <aside class="article-sidebar">
        {toc_html}
        <div class="sidebar-card cta-card">
          <h4>Free Consultation</h4>
          <h3>See how much revenue you are missing</h3>
          <p>30-minute call. We will analyze your current funnel and show you the leak.</p>
          <a href="{DEMO_URL}" class="btn">Schedule Free Consultation</a>
        </div>
        <div class="sidebar-card">
          <h4>Share this article</h4>
          <div class="share-row">
            <a id="share-x" href="#" target="_blank" rel="noopener noreferrer" aria-label="Share on X">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
              X
            </a>
            <a id="share-li" href="#" target="_blank" rel="noopener noreferrer" aria-label="Share on LinkedIn">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.063 2.063 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
              LinkedIn
            </a>
            <a id="share-copy" href="#" aria-label="Copy link">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
              <span id="copy-label">Copy</span>
            </a>
          </div>
        </div>
      </aside>
    </div>
  </div>
</section>

<section class="related-articles">
  <div class="container">
    <h2>Related articles</h2>
    <div class="related-grid">
      {related_html}
    </div>
  </div>
</section>

<section class="final-cta-section">
  <div class="container-narrow">
    <h2>Ready to capture every med spa lead?</h2>
    <p>Book a free consultation and we will show you the exact revenue leak in your funnel and the system that plugs it.</p>
    <a href="{DEMO_URL}" class="btn btn-primary" style="font-size: 1.05rem; padding: 16px 32px;">Schedule Free Consultation</a>
  </div>
</section>

{footer_html()}

<script>
  (function() {{
    var url = window.location.href;
    var title = document.title.split(' | ')[0];
    var x = document.getElementById('share-x');
    if (x) x.href = 'https://twitter.com/intent/tweet?text=' + encodeURIComponent(title) + '&url=' + encodeURIComponent(url);
    var li = document.getElementById('share-li');
    if (li) li.href = 'https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(url);
    var copy = document.getElementById('share-copy');
    var label = document.getElementById('copy-label');
    if (copy && label) {{
      copy.addEventListener('click', function(e) {{
        e.preventDefault();
        var done = function() {{
          var original = label.textContent;
          label.textContent = 'Copied!';
          copy.classList.add('copied');
          setTimeout(function() {{ label.textContent = original; copy.classList.remove('copied'); }}, 1800);
        }};
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          navigator.clipboard.writeText(url).then(done).catch(function() {{ legacyCopy(); }});
        }} else {{ legacyCopy(); }}
        function legacyCopy() {{
          var ta = document.createElement('textarea');
          ta.value = url; document.body.appendChild(ta); ta.select();
          try {{ document.execCommand('copy'); done(); }} catch(e) {{}}
          document.body.removeChild(ta);
        }}
      }});
    }}
  }})();
</script>

</body>
</html>
"""


def render_index(articles):
    """Render the blog index listing all articles."""
    canonical = f"{SITE_DOMAIN}/"
    head = common_head_meta(
        title=f"{BRAND_NAME} Blog — Marketing Insights for Med Spa Owners",
        description="AI front desk strategies, marketing playbooks, and compliance guides built only for med spa owners in TX, FL, AZ, and OK.",
        canonical_url=canonical,
        image_url=articles[0]["image"] if articles else "",
        image_alt="Lift My Spa Blog",
        og_type="website",
    )
    schema = blog_schema(articles)

    cat_items = []
    for c in INDEX_CATEGORIES:
        active = ' class="active"' if c == "All Articles" else ''
        slug_c = c.replace(" ", "-").lower()
        cat_items.append(f'<li><a href="?cat={slug_c}"{active}>{html.escape(c)}</a></li>')
    cat_html = "\n".join(cat_items)

    # Featured = first National Pillar; override hero image with a strong med-spa shot
    featured = next((a for a in articles if a["cluster"] == "National Pillar"), articles[0])
    featured_hero = "https://images.unsplash.com/photo-1746708810803-722593e53772?w=1600&q=80&auto=format&fit=crop"
    feat_html = f"""<div class="featured-post">
  <div class="featured-image" style="background-image: linear-gradient(180deg, rgba(149,8,25,0.30) 0%, rgba(149,8,25,0.88) 100%), url('{featured_hero}');">
    <span class="badge">Featured</span>
  </div>
  <div class="featured-content">
    <div class="meta">{html.escape(featured['category'])}</div>
    <h2><a href="/{featured['slug']}">{html.escape(featured['title'])}</a></h2>
    <p class="excerpt">{html.escape(featured['meta_description'])}</p>
    <div><a href="/{featured['slug']}" class="btn btn-primary">Read the Article</a></div>
  </div>
</div>"""

    cards_html = ""
    for a in articles:
        if a["slug"] == featured["slug"]:
            continue
        loc = location_from(a) or a["category"]
        cards_html += f"""<article class="article-card" data-cluster="{a['cluster']}" data-category="{a['category']}">
  <a class="card-link" href="/{a['slug']}">
    <span class="article-card-tag">{html.escape(a['category'])}</span>
    <h3>{html.escape(a['title'])}</h3>
    <p class="excerpt">{html.escape(a['meta_description'])}</p>
    <div class="card-footer">
      <span class="meta">{html.escape(loc)}</span>
      <span class="arrow" aria-hidden="true">&rarr;</span>
    </div>
  </a>
</article>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{head}
<style>
  .blog-hero {{ background: var(--brand-cream); padding: 80px 0 64px; text-align: center; border-bottom: 1px solid var(--neutral-300); }}
  .blog-hero .eyebrow {{ display: inline-block; background: var(--brand-red); color: var(--text-on-red); padding: 6px 14px; border-radius: 999px; font-family: var(--headline-font); font-weight: 700; font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 22px; }}
  .blog-hero h1 {{ font-size: clamp(2.4rem, 5vw, 3.6rem); margin-bottom: 16px; color: var(--text-primary); font-weight: 900; }}
  .blog-hero p {{ font-size: 1.15rem; color: var(--text-secondary); max-width: 680px; margin: 0 auto; }}
  .category-bar {{ border-bottom: 1px solid var(--neutral-300); padding: 18px 0; background: var(--neutral-100); position: sticky; top: 89px; z-index: 50; }}
  .category-list {{ display: flex; flex-wrap: wrap; gap: 8px; list-style: none; margin: 0; padding: 0; justify-content: center; }}
  .category-list a {{ display: inline-block; padding: 8px 18px; border-radius: 999px; background: var(--brand-cream); color: var(--text-primary); font-family: var(--headline-font); font-weight: 600; font-size: 0.85rem; transition: all 0.15s; cursor: pointer; }}
  .category-list a:hover {{ background: var(--brand-red); color: var(--text-on-red); }}
  .category-list a.active {{ background: var(--brand-red); color: var(--text-on-red); }}
  .featured-section {{ padding: 64px 0 0; }}
  .featured-post {{ display: grid; grid-template-columns: 1.1fr 1fr; gap: 48px; align-items: stretch; background: var(--brand-cream); border-radius: var(--radius-lg); overflow: hidden; box-shadow: var(--shadow-sm); }}
  .featured-image {{ background: var(--brand-red); min-height: 360px; display: flex; align-items: flex-end; padding: 32px; position: relative; background-size: cover; background-position: center; }}
  .featured-image .badge {{ background: var(--text-on-red); color: var(--brand-red); padding: 6px 14px; border-radius: 999px; font-family: var(--headline-font); font-weight: 700; font-size: 0.74rem; text-transform: uppercase; letter-spacing: 0.08em; }}
  .featured-content {{ padding: 48px 40px; display: flex; flex-direction: column; justify-content: center; }}
  .featured-content .meta {{ color: var(--brand-red); font-size: 0.82rem; font-family: var(--headline-font); font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 14px; }}
  .featured-content h2 {{ font-size: clamp(1.5rem, 3vw, 2.1rem); margin-bottom: 16px; line-height: 1.2; }}
  .featured-content h2 a {{ color: var(--text-primary); }}
  .featured-content h2 a:hover {{ color: var(--brand-red); }}
  .featured-content .excerpt {{ color: var(--text-secondary); font-size: 1.02rem; margin-bottom: 24px; }}
  @media (max-width: 880px) {{ .featured-post {{ grid-template-columns: 1fr; }} .featured-content {{ padding: 32px 24px; }} }}
  .articles-section {{ padding: 80px 0 0; }}
  .articles-section h2 {{ margin-bottom: 32px; font-weight: 800; }}
  .articles-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }}
  .article-card {{ background: var(--neutral-100); border-radius: var(--radius-md); border: 1px solid var(--neutral-300); transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s; position: relative; overflow: hidden; }}
  .article-card::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--brand-red); transform: scaleY(0); transform-origin: top; transition: transform 0.25s ease; }}
  .article-card:hover {{ transform: translateY(-3px); box-shadow: var(--shadow-md); border-color: var(--brand-red); }}
  .article-card:hover::before {{ transform: scaleY(1); }}
  .article-card .card-link {{ display: flex; flex-direction: column; padding: 28px 24px 22px; height: 100%; min-height: 240px; text-decoration: none; color: inherit; }}
  .article-card-tag {{ display: inline-block; background: var(--brand-red-soft); color: var(--brand-red); padding: 4px 12px; border-radius: 999px; font-family: var(--headline-font); font-weight: 700; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 16px; align-self: flex-start; }}
  .article-card h3 {{ font-size: 1.18rem; margin: 0 0 14px; line-height: 1.3; font-weight: 800; color: var(--text-primary); letter-spacing: -0.01em; }}
  .article-card:hover h3 {{ color: var(--brand-red); }}
  .article-card .excerpt {{ color: var(--text-secondary); font-size: 0.93rem; line-height: 1.55; margin: 0 0 22px; flex-grow: 1; }}
  .article-card .card-footer {{ display: flex; align-items: center; justify-content: space-between; padding-top: 16px; border-top: 1px solid var(--neutral-300); }}
  .article-card .meta {{ color: var(--text-muted); font-size: 0.78rem; font-family: var(--headline-font); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }}
  .article-card .arrow {{ color: var(--brand-red); font-family: var(--headline-font); font-weight: 800; font-size: 1.1rem; transition: transform 0.2s ease; }}
  .article-card:hover .arrow {{ transform: translateX(4px); }}
  @media (max-width: 880px) {{ .articles-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
  @media (max-width: 540px) {{ .articles-grid {{ grid-template-columns: 1fr; }} }}
  .cta-strip {{ background: var(--brand-red); color: var(--text-on-red); padding: 64px 0; margin-top: 80px; text-align: center; }}
  .cta-strip h2 {{ color: var(--text-on-red); font-size: clamp(1.6rem, 3vw, 2.3rem); margin-bottom: 14px; font-weight: 800; }}
  .cta-strip p {{ color: rgba(255, 255, 255, 0.9); max-width: 580px; margin: 0 auto 28px; font-size: 1.05rem; }}
</style>
<script type="application/ld+json">{json.dumps(schema, indent=2)}</script>
</head>
<body>

{header_html(active_blog=True)}

<section class="blog-hero">
  <div class="container-narrow">
    <span class="eyebrow">{BRAND_NAME} Blog</span>
    <h1>Marketing Playbooks for Med Spa Owners</h1>
    <p>AI front desk strategies, conversion frameworks, and compliance guides built only for med spas in Texas, Florida, Arizona, and Oklahoma.</p>
  </div>
</section>

<div class="category-bar">
  <div class="container">
    <ul class="category-list" id="cat-filter">
      {cat_html}
    </ul>
  </div>
</div>

<section class="featured-section">
  <div class="container">
    {feat_html}
  </div>
</section>

<section class="articles-section">
  <div class="container">
    <h2>All Articles</h2>
    <div class="articles-grid" id="articles-grid">
      {cards_html}
    </div>
  </div>
</section>

<section class="cta-strip">
  <div class="container-narrow">
    <h2>Med spa marketing insights you can actually use.</h2>
    <p>Want a personal walkthrough of how Lift My Spa would work for your clinic? Book a free 30-minute consultation. No pressure.</p>
    <a href="{DEMO_URL}" class="btn btn-light" style="font-size:1rem; padding:16px 32px;">Schedule Free Consultation</a>
  </div>
</section>

{footer_html()}

<script>
  // Category filter (client-side)
  (function() {{
    var grid = document.getElementById('articles-grid');
    var nav = document.getElementById('cat-filter');
    if (!grid || !nav) return;
    nav.addEventListener('click', function(e) {{
      var t = e.target.closest('a');
      if (!t) return;
      e.preventDefault();
      var url = new URL(t.href, window.location.origin);
      var cat = url.searchParams.get('cat');
      [].forEach.call(nav.querySelectorAll('a'), function(a) {{ a.classList.remove('active'); }});
      t.classList.add('active');
      var label = t.textContent.trim();
      [].forEach.call(grid.querySelectorAll('.article-card'), function(card) {{
        if (label === 'All Articles' || card.dataset.category === label) {{
          card.style.display = '';
        }} else {{
          card.style.display = 'none';
        }}
      }});
    }});
    // Apply filter from URL on load
    var urlCat = new URLSearchParams(window.location.search).get('cat');
    if (urlCat) {{
      var match = nav.querySelector('a[href*="cat=' + urlCat + '"]');
      if (match) match.click();
    }}
  }})();
</script>

</body>
</html>
"""


# ============================================================
# Sitemap, RSS, robots
# ============================================================
def generate_sitemap(articles):
    iso_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = []
    # Main domain pages
    for path, prio in [("/", "1.0"), ("/demo-call-page", "0.9"), ("/terms-conditions", "0.3"), ("/privacy-policy", "0.3")]:
        urls.append((f"{MAIN_DOMAIN}{path}", iso_today, prio, "weekly"))
    # Blog index
    urls.append((f"{SITE_DOMAIN}/", iso_today, "0.95", "daily"))
    # Articles
    for a in articles:
        urls.append((f"{SITE_DOMAIN}/{a['slug']}", PUBLISH_DATE, "0.8", "monthly"))
    body = "\n".join(
        f"  <url>\n    <loc>{u}</loc>\n    <lastmod>{lm}</lastmod>\n    <changefreq>{cf}</changefreq>\n    <priority>{p}</priority>\n  </url>"
        for u, lm, p, cf in urls
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{body}
</urlset>
"""


def generate_robots():
    return f"""User-agent: *
Allow: /

Sitemap: {SITE_DOMAIN}/sitemap.xml
"""


def generate_feed(articles):
    iso_now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = []
    for a in articles[:50]:
        url = f"{SITE_DOMAIN}/{a['slug']}"
        items.append(f"""    <item>
      <title>{html.escape(a['title'])}</title>
      <link>{url}</link>
      <guid isPermaLink="true">{url}</guid>
      <pubDate>{iso_now}</pubDate>
      <description>{html.escape(a['meta_description'])}</description>
      <category>{html.escape(a['category'])}</category>
    </item>""")
    items_xml = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{BRAND_NAME} Blog</title>
    <link>{SITE_DOMAIN}/</link>
    <description>AI front desk strategies, marketing playbooks, and compliance guides built only for med spas in TX, FL, AZ, and OK.</description>
    <language>en-us</language>
    <lastBuildDate>{iso_now}</lastBuildDate>
    <atom:link href="{SITE_DOMAIN}/feed.xml" rel="self" type="application/rss+xml" />
{items_xml}
  </channel>
</rss>
"""


def generate_404():
    head = common_head_meta(
        title=f"Page Not Found | {BRAND_NAME} Blog",
        description="The page you are looking for does not exist.",
        canonical_url=f"{SITE_DOMAIN}/404",
        image_url=f"{SITE_DOMAIN}/logo-red.png",
        image_alt=BRAND_NAME,
        og_type="website",
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{head}
</head>
<body>
{header_html(active_blog=True)}
<section style="padding: 120px 0; text-align: center;">
  <div class="container-narrow">
    <h1 style="font-size: clamp(3rem, 8vw, 6rem); color: var(--brand-red); margin-bottom: 16px;">404</h1>
    <h2 style="font-size: 1.5rem; margin-bottom: 16px;">We could not find that page.</h2>
    <p style="color: var(--text-secondary); margin-bottom: 32px;">The article may have moved, or the URL may be incorrect.</p>
    <a href="/" class="btn btn-primary">Go to Blog Home</a>
  </div>
</section>
{footer_html()}
</body>
</html>
"""


def generate_redirects():
    """Cloudflare Pages _redirects file."""
    return """# Strip .html extension if accessed
/*.html /:splat 301
"""


def generate_homepage_meta_recommendations(articles):
    """Generate the meta tags Jane needs to add to liftmyspa.com (in GHL)."""
    return f"""<!-- ============================================================
   RECOMMENDED META TAGS FOR liftmyspa.com HOMEPAGE
   Paste these into the GHL site head section (Settings > Custom CSS / Head)
   ============================================================ -->

<title>Lift My Spa | AI Front Desk + Marketing Automation for Med Spas</title>
<meta name="description" content="The plug-and-play AI front desk and marketing system built only for med spas in Texas, Florida, Arizona, and Oklahoma. Answer 100% of calls, reduce no-shows by 50%, convert 5x more leads.">
<meta name="keywords" content="med spa marketing, med spa AI front desk, med spa software, AI receptionist medical spa, med spa CRM, HIPAA marketing automation">
<link rel="canonical" href="{MAIN_DOMAIN}/">

<!-- Open Graph -->
<meta property="og:type" content="website">
<meta property="og:site_name" content="{BRAND_NAME}">
<meta property="og:title" content="Lift My Spa | AI Front Desk + Marketing Automation for Med Spas">
<meta property="og:description" content="Plug-and-play AI front desk and marketing system built only for med spas in TX, FL, AZ, OK. Answer 100% of calls, reduce no-shows, convert 5x more leads.">
<meta property="og:url" content="{MAIN_DOMAIN}/">
<meta property="og:image" content="{SITE_DOMAIN}/logo-red.png">
<meta property="og:locale" content="en_US">

<!-- Twitter -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Lift My Spa | AI Front Desk + Marketing Automation for Med Spas">
<meta name="twitter:description" content="Plug-and-play AI front desk and marketing system built only for med spas. Answer 100% of calls, reduce no-shows by 50%, convert 5x more leads.">
<meta name="twitter:image" content="{SITE_DOMAIN}/logo-red.png">

<!-- Favicons (replace existing) -->
<link rel="icon" type="image/x-icon" href="{SITE_DOMAIN}/favicon.ico">
<link rel="icon" type="image/png" sizes="192x192" href="{SITE_DOMAIN}/favicon-192.png">
<link rel="apple-touch-icon" href="{SITE_DOMAIN}/apple-touch-icon.png">

<!-- Schema.org Organization + WebSite -->
<script type="application/ld+json">
{json.dumps({
    "@context": "https://schema.org",
    "@graph": [
        organization_schema(),
        {
            "@type": "WebSite",
            "@id": f"{MAIN_DOMAIN}/#website",
            "url": MAIN_DOMAIN,
            "name": BRAND_NAME,
            "publisher": {"@id": f"{MAIN_DOMAIN}/#organization"},
            "inLanguage": "en-US",
            "potentialAction": {
                "@type": "SearchAction",
                "target": f"{SITE_DOMAIN}/?q={{search_term_string}}",
                "query-input": "required name=search_term_string"
            }
        },
        {
            "@type": "Service",
            "name": "AI Front Desk + Marketing Automation for Med Spas",
            "provider": {"@id": f"{MAIN_DOMAIN}/#organization"},
            "areaServed": ["Texas", "Florida", "Arizona", "Oklahoma"],
            "description": "24/7 AI front desk, automated reviews, referral program, and marketing automation built only for medical spas.",
            "serviceType": "Marketing Software",
        }
    ]
}, indent=2)}
</script>
"""


# ============================================================
# Build
# ============================================================
def main():
    print(f"Building site to: {OUT_DIR}\n")

    # Clean and recreate output
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True)

    # Copy static assets
    for asset in ["brand.css", "logo-red.png", "logo-white.webp",
                  "favicon.ico", "favicon-192.png", "favicon-512.png", "apple-touch-icon.png"]:
        src = DESIGN_DIR / asset
        if src.exists():
            shutil.copy2(src, OUT_DIR / asset)
        else:
            print(f"  WARN: missing asset {asset}")

    # Load CSV + parse articles
    csv_meta = load_csv()
    articles_by_slug = {}
    for md_path in sorted(ARTICLES_DIR.glob("*.md")):
        a = parse_article(md_path, csv_meta)
        articles_by_slug[a["slug"]] = a
    articles = list(articles_by_slug.values())
    print(f"Loaded {len(articles)} articles")

    # Sort: pillars first, then state, metro, town, etc.
    cluster_order = ["National Pillar", "State", "Major Metro", "Town/Suburb",
                     "Pain-Point", "Service-Specific", "Comparison", "Compliance"]
    articles.sort(key=lambda a: (cluster_order.index(a["cluster"]) if a["cluster"] in cluster_order else 99, a["slug"]))

    # Compute related links
    related_map = compute_related(articles_by_slug)

    # Render articles
    article_count = 0
    for a in articles:
        related_slugs = related_map.get(a["slug"], [])
        related = [articles_by_slug[s] for s in related_slugs if s in articles_by_slug]
        html_out = render_article(a, related)
        (OUT_DIR / f"{a['slug']}.html").write_text(html_out, encoding="utf-8")
        article_count += 1

    print(f"Rendered {article_count} articles")

    # Render index
    (OUT_DIR / "index.html").write_text(render_index(articles), encoding="utf-8")
    print("Rendered index.html")

    # Sitemap, robots, feed, 404, _redirects
    (OUT_DIR / "sitemap.xml").write_text(generate_sitemap(articles), encoding="utf-8")
    (OUT_DIR / "robots.txt").write_text(generate_robots(), encoding="utf-8")
    (OUT_DIR / "feed.xml").write_text(generate_feed(articles), encoding="utf-8")
    (OUT_DIR / "404.html").write_text(generate_404(), encoding="utf-8")
    (OUT_DIR / "_redirects").write_text(generate_redirects(), encoding="utf-8")
    print("Generated: sitemap.xml, robots.txt, feed.xml, 404.html, _redirects")

    # Homepage meta recommendations
    homepage_recommendations = generate_homepage_meta_recommendations(articles)
    (ROOT / "HOMEPAGE-meta-tags-to-add-in-GHL.html").write_text(homepage_recommendations, encoding="utf-8")
    print(f"Wrote homepage meta tag recommendations to: {ROOT}/HOMEPAGE-meta-tags-to-add-in-GHL.html")

    # Verify
    file_count = len(list(OUT_DIR.iterdir()))
    print(f"\nDone. Total files in site/: {file_count}")
    print(f"Open: open {OUT_DIR}/index.html")


if __name__ == "__main__":
    main()
