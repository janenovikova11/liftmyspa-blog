# Lift My Spa Blog

The blog for [Lift My Spa](https://liftmyspa.com), the AI plus marketing automation platform built exclusively for medical spas in Texas, Florida, Arizona, and Oklahoma.

Blog deploys to **`blog.liftmyspa.com`** via Cloudflare Pages.

## Repo structure

```
.
├── articles/           102 markdown articles with YAML frontmatter (source content)
├── design/             Shared design assets (CSS, logos, favicons) and HTML mockups
├── site/               Generated static HTML output (deployed to Cloudflare Pages)
├── build_site.py       Python build script (markdown -> HTML)
├── SAIO Article Plan.csv   Canonical content plan with metadata + cluster assignments
└── README.md           This file
```

## How it builds

The build script reads:
- All `articles/*.md` files (frontmatter + markdown body)
- `SAIO Article Plan.csv` (cluster, AIRO level, keywords, meta titles, slugs)
- `design/brand.css`, `design/logo-*`, `design/favicon-*`

And writes to `site/`:
- `index.html` — blog index with category filter
- `[slug].html` — one HTML file per article (102 total)
- `sitemap.xml` — full sitemap incl. main domain pages
- `robots.txt` — allow all + sitemap location
- `feed.xml` — RSS 2.0
- `404.html` — friendly 404
- `_redirects` — Cloudflare Pages redirect rules
- copies of all static assets (CSS, logos, favicons)

Each article page includes:
- `<title>`, `<meta description>`, canonical URL
- Open Graph tags (og:title, og:description, og:image, og:url, og:type)
- Twitter Card tags
- JSON-LD schema (Organization + BlogPosting + BreadcrumbList)
- Hero image, table of contents, related articles, share buttons (X, LinkedIn, Copy)

## Build locally

```bash
pip3 install --user markdown pyyaml
python3 build_site.py
open site/index.html
```

## Deploy on Cloudflare Pages

1. Push this repo to GitHub.
2. In Cloudflare dashboard: **Pages > Connect to Git** -> select this repo.
3. Build settings:
   - **Build command**: `python3 build_site.py`
   - **Build output directory**: `site`
   - **Root directory**: `/`
   - **Environment variables**: none
4. Add custom domain: `blog.liftmyspa.com` (CNAME to the Cloudflare Pages domain).

Or, if you prefer no build step (since `site/` is committed):
- **Build command**: leave blank
- **Build output directory**: `site`

## Brand reference

- Primary deep red: `#950819`
- Cream background: `#F3F0EC`
- Sage accent: `#BBCAA1`
- Blush accent: `#F8D6D2`
- Headline font: Manrope
- Body font: Inter

## Article taxonomy (8 clusters, 102 articles)

| Cluster | Count | AIRO level |
|---|---|---|
| National Pillar | 12 | mix L1/L2/L3 |
| State | 8 | L2/L1 mix |
| Major Metro (City) | 16 | L2 |
| Town/Suburb (City) | 32 | L2 |
| Pain-Point | 10 | L1 |
| Service-Specific | 10 | L1 + 1 L3 |
| Comparison | 8 | L2 |
| Compliance | 6 | L1 |

## Cross-linking

Each article has 3 related articles, computed by cluster:
- **Town** -> metro pillar + state pillar + sibling town
- **Metro** -> state pillar + 2 towns from same metro
- **State** -> 3 metros from that state
- **Pillar / Service / Pain-Point / Comparison / Compliance** -> 2 cluster siblings + 1 pillar
