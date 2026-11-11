#!/usr/bin/env python3
"""네이버 블로그 글 목록을 모아 GitHub Pages 허브(아카이브) 페이지와 sitemap.xml을 만든다.

사용법
  python scripts/update.py              # RSS로 새 글만 추가 (6시간마다 자동 실행)
  python scripts/update.py --backfill   # 블로그 전체 글을 처음부터 모두 수집 (최초 1회)
  python scripts/update.py --build-only # 수집 없이 페이지만 다시 생성
"""
import argparse
import datetime as dt
import email.utils
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BLOG_ID = CONFIG["blog_id"]
DATA_FILE = ROOT / "data" / "posts.json"
KST = dt.timezone(dt.timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


# ---------------------------------------------------------------- 수집
def fetch(url, referer=None):
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def load_posts():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {"categories": {}, "posts": {}}


def save_posts(data):
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch_categories():
    """카테고리 번호 -> 이름. 실패해도 계속 진행한다."""
    try:
        raw = fetch(f"https://m.blog.naver.com/api/blogs/{BLOG_ID}/category-list",
                    referer=f"https://m.blog.naver.com/{BLOG_ID}")
        items = json.loads(raw)["result"]["mylogCategoryList"]
        return {str(c["categoryNo"]): c["categoryName"] for c in items}
    except Exception as e:  # noqa: BLE001
        print(f"[경고] 카테고리 이름을 가져오지 못했습니다: {e}", file=sys.stderr)
        return {}


def parse_add_date(text):
    """'2026. 11. 7.' 형식 또는 '17분 전' 같은 상대 표기를 YYYY-MM-DD로."""
    m = re.match(r"(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", text or "")
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    return dt.datetime.now(KST).strftime("%Y-%m-%d")


def backfill(data):
    """블로그 전체 글 목록을 페이지 단위로 수집."""
    cats = fetch_categories()
    data["categories"].update(cats)
    page, per_page, added = 1, 30, 0
    while True:
        url = ("https://blog.naver.com/PostTitleListAsync.naver"
               f"?blogId={BLOG_ID}&viewdate=&currentPage={page}"
               f"&categoryNo=0&parentCategoryNo=0&countPerPage={per_page}")
        raw = fetch(url, referer=f"https://blog.naver.com/{BLOG_ID}")
        raw = raw.replace("\\'", "'")  # 네이버 응답의 잘못된 이스케이프 보정
        js = json.loads(raw)
        items = js.get("postList") or []
        if not items:
            break
        for it in items:
            log_no = str(it["logNo"])
            if log_no not in data["posts"]:
                added += 1
            data["posts"][log_no] = {
                "title": urllib.parse.unquote_plus(it.get("title", "")).strip(),
                "category_no": str(it.get("categoryNo", "0")),
                "date": parse_add_date(urllib.parse.unquote_plus(it.get("addDate", ""))),
            }
        total = int(js.get("totalCount", 0) or 0)
        print(f"  {page}페이지 수집 완료 ({len(data['posts'])}/{total})")
        if page * per_page >= total:
            break
        page += 1
        time.sleep(0.5)
    print(f"전체 수집: 새 글 {added}개 추가, 총 {len(data['posts'])}개")


def update_from_rss(data):
    """RSS 피드에서 최신 글을 추가."""
    raw = fetch(f"https://rss.blog.naver.com/{BLOG_ID}.xml")
    root = ET.fromstring(raw)
    name_to_no = {v: k for k, v in data["categories"].items()}
    added = 0
    for item in root.iter("item"):
        link = item.findtext("link", "")
        m = re.search(r"/(\d{9,})", link)
        if not m:
            continue
        log_no = m[1]
        cat_name = (item.findtext("category") or "기타").strip()
        cat_no = name_to_no.get(cat_name)
        if cat_no is None:  # 처음 보는 카테고리는 이름 자체를 키로 저장
            cat_no = "rss:" + cat_name
            data["categories"][cat_no] = cat_name
            name_to_no[cat_name] = cat_no
        try:
            date = email.utils.parsedate_to_datetime(item.findtext("pubDate", "")) \
                .astimezone(KST).strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            date = dt.datetime.now(KST).strftime("%Y-%m-%d")
        if log_no not in data["posts"]:
            added += 1
            data["posts"][log_no] = {
                "title": (item.findtext("title") or "").strip(),
                "category_no": cat_no,
                "date": date,
            }
    print(f"RSS 업데이트: 새 글 {added}개 추가, 총 {len(data['posts'])}개")
    return added


# ---------------------------------------------------------------- 페이지 생성
def mobile_url(log_no):
    return f"https://m.blog.naver.com/{BLOG_ID}/{log_no}"


def slug(cat_no):
    return re.sub(r"[^0-9A-Za-z]+", "-", cat_no).strip("-") or "etc"


CSS = """
:root{--bg:#fafaf7;--fg:#222;--muted:#777;--accent:#03a94d;--line:#e6e4dd}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:860px;margin:0 auto;padding:32px 20px 64px}
h1{font-size:1.7rem;margin:0 0 4px}h2{font-size:1.2rem;margin:36px 0 10px}
.desc{color:var(--muted);margin:0 0 20px}a{color:inherit}
.cats{display:flex;flex-wrap:wrap;gap:8px;padding:0;list-style:none}
.cats a{display:inline-block;padding:6px 12px;border:1px solid var(--line);border-radius:999px;
text-decoration:none;background:#fff}.cats a:hover{border-color:var(--accent);color:var(--accent)}
.cats small{color:var(--muted)}
ol.posts{list-style:none;padding:0;margin:0;border-top:1px solid var(--line)}
ol.posts li{display:flex;justify-content:space-between;gap:16px;padding:10px 2px;border-bottom:1px solid var(--line)}
ol.posts a{text-decoration:none}ol.posts a:hover{color:var(--accent);text-decoration:underline}
time{color:var(--muted);font-size:.85rem;white-space:nowrap}
input[type=search]{width:100%;padding:10px 14px;border:1px solid var(--line);border-radius:8px;font-size:1rem;margin:8px 0 4px}
footer{margin-top:48px;color:var(--muted);font-size:.85rem}
"""

SEARCH_JS = """<script>
if(!/Mobi|Android|iPhone|iPad/i.test(navigator.userAgent))document.querySelectorAll('a[href^="https://m.blog.naver.com/"]').forEach(a=>a.href=a.href.replace('://m.blog','://blog'));
const q=document.getElementById('q');q&&q.addEventListener('input',()=>{const v=q.value.trim().toLowerCase();
document.querySelectorAll('ol.posts li').forEach(li=>{li.style.display=!v||li.textContent.toLowerCase().includes(v)?'':'none'})});
</script>"""


def page(title, body, canonical):
    verify = CONFIG.get("google_site_verification", "").strip()
    meta = f'<meta name="google-site-verification" content="{html.escape(verify)}">' if verify else ""
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(CONFIG['site_description'])}">
<link rel="canonical" href="{html.escape(canonical)}">{meta}
<style>{CSS}</style></head>
<body><main>{body}
<footer>원문: <a href="https://m.blog.naver.com/{BLOG_ID}">m.blog.naver.com/{BLOG_ID}</a> ·
마지막 업데이트 {dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M')} (KST)</footer>
</main>{SEARCH_JS}</body></html>
"""


def post_list(items):
    rows = [f'<li><a href="{mobile_url(n)}">{html.escape(p["title"] or "(제목 없음)")}</a>'
            f'<time datetime="{p["date"]}">{p["date"]}</time></li>' for n, p in items]
    return '<ol class="posts">' + "".join(rows) + "</ol>"


def build(data):
    base = CONFIG["site_url"].rstrip("/")
    posts = sorted(data["posts"].items(), key=lambda kv: (kv[1]["date"], int(re.sub(r"\D", "", kv[0]) or 0)),
                   reverse=True)
    by_cat = {}
    for n, p in posts:
        by_cat.setdefault(p["category_no"], []).append((n, p))

    def cat_name(no):
        return data["categories"].get(no) or (f"카테고리 {no}" if no not in ("0", "") else "미분류")

    (ROOT / "category").mkdir(exist_ok=True)
    for old in (ROOT / "category").glob("*.html"):
        old.unlink()
    urls = [f"{base}/"]
    for no, items in by_cat.items():
        name = cat_name(no)
        path = f"category/{slug(no)}.html"
        body = (f'<p><a href="../">← 전체 카테고리</a></p><h1>{html.escape(name)}</h1>'
                f'<p class="desc">글 {len(items)}개</p>'
                f'<input id="q" type="search" placeholder="이 카테고리에서 제목 검색">' + post_list(items))
        (ROOT / path).write_text(page(f"{name} - {CONFIG['site_title']}", body, f"{base}/{path}"),
                                 encoding="utf-8")
        urls.append(f"{base}/{path}")

    cats_sorted = sorted(by_cat.items(), key=lambda kv: -len(kv[1]))
    cat_links = "".join(f'<li><a href="category/{slug(no)}.html">{html.escape(cat_name(no))} '
                        f'<small>{len(items)}</small></a></li>' for no, items in cats_sorted)
    body = (f"<h1>{html.escape(CONFIG['site_title'])}</h1>"
            f'<p class="desc">{html.escape(CONFIG["site_description"])} 전체 글 {len(posts)}개</p>'
            f'<h2>카테고리</h2><ul class="cats">{cat_links}</ul>'
            f'<h2>최근 글</h2><input id="q" type="search" placeholder="최근 글에서 제목 검색">'
            + post_list(posts[:100]))
    (ROOT / "index.html").write_text(page(CONFIG["site_title"], body, f"{base}/"), encoding="utf-8")

    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{html.escape(u)}</loc><lastmod>{today}</lastmod></url>" for u in urls]
    sm.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    print(f"페이지 생성: 카테고리 {len(by_cat)}개, 글 {len(posts)}개")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="전체 글 수집")
    ap.add_argument("--build-only", action="store_true", help="수집 없이 페이지만 생성")
    args = ap.parse_args()
    data = load_posts()
    if args.backfill:
        backfill(data)
    elif not args.build_only:
        if not data["categories"]:
            data["categories"].update(fetch_categories())
        update_from_rss(data)
    save_posts(data)
    build(data)


if __name__ == "__main__":
    main()
