# =============================================================
# briefing.py
# settings.json 의 모든 RSS 에서 기사를 모아 최대 5개를 고르고,
# Gemini 로 세 줄 요약을 만든 뒤 news.json 과 index.html 로 저장합니다.
#
# 고르는 순서
#   1) 키워드마다 가장 최신 기사를 최소 1개씩 고름
#   2) 남은 자리는 키워드가 들어간 다른 기사로 채움 (최신순)
#   3) 그래도 5개가 안 되면 나머지 기사 중 최신 기사로 채움
#
# 키워드는 제목이나 소개문에 들어 있는지 검사합니다.
#
# 기사 본문은 가져오지 않습니다. RSS 에 들어 있는 내용만 씁니다.
# 그래서 요약도 제목과 소개문만 보고 만듭니다.
#
# .env 파일에 GEMINI_API_KEY=키값 형식으로 키를 적어 두어야 요약이 만들어집니다.
# 키가 없거나 요약에 실패해도 index.html 은 만들어집니다.
#
# 실행 방법: 터미널에서 python briefing.py
# =============================================================

# ----- 1. 도구 불러오기 ---------------------------------------
import html  # &nbsp; 같은 HTML 특수 표기를 원래 글자로 바꿉니다.
import json  # JSON 글자를 만들고 파일로 저장합니다.
import re  # 글자의 패턴을 찾아 바꿔 줍니다.
import sys  # 화면 출력 설정을 바꾸고, 프로그램을 끝낼 때 씁니다.
import time  # 다시 시도하기 전에 잠시 기다릴 때 씁니다.
import urllib.error  # 인터넷 접속 오류의 종류를 알려 줍니다.
import urllib.request  # Gemini 에 요청을 보냅니다.
import xml.etree.ElementTree as ET  # RSS(XML 형식)를 읽습니다.
from datetime import datetime, timezone  # 날짜와 시간을 다룹니다.

# fetch_news.py 에 이미 만들어 둔 함수를 가져와서 다시 씁니다.
# 그래서 이 파일은 fetch_news.py 와 같은 폴더에 있어야 합니다.
from fetch_news import KOREA_TIME, download, load_settings, parse_date

# ----- 2. 바꿔 쓸 수 있는 값 -----------------------------------
OUTPUT_FILE = "news.json"  # 결과를 저장할 파일 이름
PAGE_FILE = "index.html"  # 브리핑 페이지 파일 이름
PAGE_TITLE = "증시,부동산 아침 브리핑"  # 페이지 제목
MAX_ARTICLES = 5  # 저장할 기사의 최대 개수

ENV_FILE = ".env"  # API 키가 적힌 파일 이름
GEMINI_MODEL = "gemini-flash-lite-latest"  # 사용할 Gemini 모델
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + GEMINI_MODEL
    + ":generateContent"
)
GEMINI_TIMEOUT_SECONDS = 60  # Gemini 응답을 기다리는 최대 시간
GEMINI_MAX_TRIES = 3  # 일시적인 오류가 나면 최대 몇 번까지 시도할지
RETRY_WAIT_SECONDS = 5  # 다시 시도하기 전에 기다리는 시간
RETRY_STATUS_CODES = (429, 500, 503)  # 잠시 뒤 다시 하면 될 수 있는 오류
KEY_ERROR_CODES = (400, 401, 403)  # 키나 요청이 잘못되어 다시 해도 안 되는 오류

# 요약을 만들 때 Gemini 에 보내는 지시문입니다.
SUMMARY_PROMPT = """아래 기사 정보만 보고 한국어로 세 줄 요약을 써 줘.
- 각 줄은 한 문장, 줄 앞에 "- " 를 붙인다
- 기사 정보에 없는 내용, 숫자, 이름은 절대 쓰지 않는다
- 정보가 부족하면 마지막 줄에 "- 자세한 내용은 원문 확인 필요" 라고 쓴다

[기사 정보]
제목: {title}
언론사: {source}
날짜: {date}
소개문: {summary}
"""

# 페이지의 모양을 정하는 CSS 입니다.
# 화면 설정이 어두운 모드이면 어두운 색으로 바뀝니다.
PAGE_STYLE = """
:root {
  --bg: #f6f5f1; --card: #ffffff; --text: #22242a; --muted: #686c76;
  --line: #e2e0d9; --accent: #1f5fbf; --notice: #fff4d6; --notice-text: #6b4e00;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #17181c; --card: #212329; --text: #eceef2; --muted: #a2a6b0;
    --line: #363943; --accent: #8db8ff; --notice: #3b3216; --notice-text: #f3dd9b;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text); line-height: 1.65;
  font-family: "Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
}
.wrap { max-width: 720px; margin: 0 auto; padding: 32px 16px 40px; }
h1 { margin: 0; font-size: 1.75rem; line-height: 1.3; }
.time { margin: 6px 0 24px; color: var(--muted); font-size: 0.9rem; }
.notice {
  margin: 0 0 16px; padding: 10px 14px; border-radius: 8px;
  background: var(--notice); color: var(--notice-text); font-size: 0.9rem;
}
article {
  margin-bottom: 14px; padding: 18px 20px; border-radius: 10px;
  background: var(--card); border: 1px solid var(--line);
}
h2 { margin: 0 0 10px; font-size: 1.1rem; line-height: 1.45; overflow-wrap: anywhere; }
article ul { margin: 0 0 12px; padding-left: 20px; }
.no-summary { margin: 0 0 12px; color: var(--muted); }
.meta { margin: 0; color: var(--muted); font-size: 0.875rem; }
.meta a { color: var(--accent); }
footer {
  margin-top: 24px; padding-top: 14px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 0.875rem;
}
"""


class GeminiKeyError(Exception):
    """키가 잘못되어 다시 시도해도 소용없을 때 쓰는 오류입니다."""


# ----- 3. 함수 만들기 -----------------------------------------


def clean_text(text):
    """소개문에서 HTML 태그를 지우고 글자만 남깁니다."""
    # 구글 뉴스의 소개문에는 <a href="주소"> 같은 태그가 들어 있습니다.
    # 태그를 지우지 않으면 주소 속 영어까지 검사하게 되어,
    # 우연히 들어 있는 "AI" 때문에 엉뚱한 기사가 걸립니다.
    without_tags = re.sub(r"<[^>]+>", " ", text or "")
    return html.unescape(without_tags).strip()


def has_keyword(keyword, text):
    """글(text) 안에 키워드가 들어 있으면 True 를 돌려줍니다."""
    if keyword.isascii():
        # AI 같은 영어 키워드는 앞뒤에 영어나 숫자가 붙으면 다른 단어입니다.
        # 예: "AI로"는 찾지만 "KAIST", "EMAIL"은 찾지 않습니다.
        pattern = r"(?<![A-Za-z0-9])" + re.escape(keyword) + r"(?![A-Za-z0-9])"
        return re.search(pattern, text, re.IGNORECASE) is not None
    # 한글 키워드는 "증시가", "증시는"도 찾도록 단순히 포함 여부만 봅니다.
    return keyword in text


def find_keywords(article, keywords):
    """기사의 제목이나 소개문에 들어 있는 키워드만 모아 돌려줍니다."""
    text = article["title"] + " " + article["summary"]
    # 빈 키워드("")는 건너뜁니다. 그대로 두면 모든 기사가 걸립니다.
    return [word for word in keywords if word.strip() and has_keyword(word, text)]


def fetch_articles(feed):
    """RSS 주소 하나에서 기사를 모두 읽어 목록으로 돌려줍니다."""
    root = ET.fromstring(download(feed["url"]))

    articles = []
    for item in root.findall("./channel/item"):
        # 언론사 이름은 구글 뉴스는 <source>, 매일경제는 <author> 에 있습니다.
        source = (item.findtext("source") or item.findtext("author") or "").strip()
        title = (item.findtext("title") or "").strip()
        # 구글 뉴스 제목 끝의 " - 한겨레" 같은 언론사 이름은 따로 보여 주므로 지웁니다.
        if source:
            title = title.removesuffix(" - " + source).strip()

        article = {
            "title": title,
            "link": (item.findtext("link") or "").strip(),
            "summary": clean_text(item.findtext("description")),  # 소개문
            "date": parse_date(item.findtext("pubDate")),
            "feed": feed["name"],
            "source": source or feed["name"],  # 없으면 피드 이름을 씁니다.
        }
        # 제목이나 링크가 없는 기사는 쓸 수 없으니 넣지 않습니다.
        if article["title"] and article["link"]:
            articles.append(article)
    return articles


def sort_newest_first(articles):
    """기사를 최신순으로 정렬합니다. 날짜가 없는 기사는 맨 뒤로 갑니다."""
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    articles.sort(key=lambda article: article["date"] or oldest, reverse=True)


def remove_duplicates(articles):
    """링크나 제목이 같은 기사는 하나만 남깁니다."""
    # 같은 기사가 증권과 경제 피드에 모두 실리는 경우를 대비합니다.
    # set 은 "이미 본 것"을 빠르게 확인할 수 있는 묶음입니다.
    seen_links = set()
    seen_titles = set()
    unique = []
    for article in articles:
        if article["link"] in seen_links or article["title"] in seen_titles:
            continue  # 이미 본 기사이므로 건너뜁니다.
        seen_links.add(article["link"])
        seen_titles.add(article["title"])
        unique.append(article)
    return unique


def pick_one_per_keyword(matched, keywords):
    """키워드마다 기사가 최소 1개씩 들어가도록 기사를 고릅니다."""
    # matched 는 최신순이므로, 앞에서 찾은 기사가 그 키워드의 최신 기사입니다.
    picked = []
    for keyword in keywords:
        # 이미 고른 기사에 이 키워드가 있으면 하나 더 고를 필요가 없습니다.
        if any(keyword in article["matched_keywords"] for article in picked):
            continue
        for article in matched:
            if keyword in article["matched_keywords"]:
                picked.append(article)
                break  # 하나 찾았으니 다음 키워드로 넘어갑니다.
    return picked


def select_articles(articles, keywords):
    """키워드가 걸린 기사를 먼저, 모자라면 최신 기사로 채워 고릅니다."""
    # 다른 곳에 있는 목록을 바꾸지 않도록 복사본을 정렬합니다.
    articles = list(articles)
    sort_newest_first(articles)

    matched = []  # 키워드가 걸린 기사
    others = []  # 걸리지 않은 기사
    for article in articles:
        article["matched_keywords"] = find_keywords(article, keywords)
        if article["matched_keywords"]:
            matched.append(article)
        else:
            others.append(article)

    # 키워드별로 1개씩 먼저 고르고, 남은 자리를 다른 키워드 기사로 채웁니다.
    picked = pick_one_per_keyword(matched, keywords)[:MAX_ARTICLES]
    for article in matched:
        if len(picked) >= MAX_ARTICLES:
            break  # 자리가 다 찼으니 그만 고릅니다.
        if article not in picked:
            picked.append(article)

    # 보기 좋게 최신순으로 다시 정렬합니다.
    sort_newest_first(picked)

    # 키워드 기사 뒤에 나머지 기사를 붙이고 앞에서부터 자릅니다.
    # 그래서 모자란 만큼만 최신 기사가 들어옵니다.
    return (picked + others)[:MAX_ARTICLES]


def load_api_key():
    """.env 파일에서 GEMINI_API_KEY 값을 찾습니다. 없으면 빈 글자를 돌려줍니다."""
    # 키는 비밀번호와 같습니다. 화면이나 파일에 출력하지 않습니다.
    try:
        # utf-8-sig 는 메모장이 파일 맨 앞에 넣는 표시(BOM)까지 처리해 줍니다.
        with open(ENV_FILE, encoding="utf-8-sig") as file:
            for line in file:
                name, _, value = line.partition("=")
                if name.strip() == "GEMINI_API_KEY":
                    return value.strip().strip("\"'")
    except OSError:
        pass  # 파일이 없으면 키가 없는 것으로 처리합니다.
    return ""


def ask_gemini(prompt, api_key):
    """Gemini 에 글을 보내고 답을 글자로 돌려줍니다."""
    # Gemini 가 정해 둔 형식에 맞춰 보낼 내용을 만듭니다.
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
    # 키를 주소에 넣으면 오류 메시지에 노출될 수 있어서 헤더로 보냅니다.
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    request = urllib.request.Request(GEMINI_URL, data=body, headers=headers)

    for attempt in range(1, GEMINI_MAX_TRIES + 1):
        try:
            with urllib.request.urlopen(
                request, timeout=GEMINI_TIMEOUT_SECONDS
            ) as response:
                data = json.load(response)
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except urllib.error.HTTPError as error:
            if error.code in KEY_ERROR_CODES:
                raise GeminiKeyError(f"HTTP {error.code}")
            if error.code not in RETRY_STATUS_CODES or attempt == GEMINI_MAX_TRIES:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == GEMINI_MAX_TRIES:
                raise
        # 여기까지 오면 일시적인 오류이므로 조금 기다렸다가 다시 시도합니다.
        time.sleep(RETRY_WAIT_SECONDS * attempt)


def parse_summary(text):
    """Gemini 의 답에서 "- " 로 시작하는 줄만 최대 3줄 꺼냅니다."""
    lines = [line.strip() for line in text.splitlines()]
    return [line for line in lines if line.startswith("- ")][:3]


def summarize_articles(articles, api_key):
    """기사마다 세 줄 요약을 만들어 넣고, 알릴 내용이 있으면 글자로 돌려줍니다."""
    for article in articles:
        article["ai_summary"] = []  # 실패해도 페이지를 만들 수 있게 빈 목록을 넣습니다.

    if not api_key:
        return "API 키가 없어 AI 요약 없이 기사 목록만 보여 드립니다."

    failed = 0
    for article in articles:
        prompt = SUMMARY_PROMPT.format(
            title=article["title"],
            source=article["source"],
            date=format_date(article["date"]),
            summary=article["summary"] or "(소개문 없음)",
        )
        try:
            article["ai_summary"] = parse_summary(ask_gemini(prompt, api_key))
        except GeminiKeyError as error:
            print(f"Gemini 요청을 거절당해 요약을 멈춥니다: {error}")
            return "API 키에 문제가 있어 AI 요약 없이 기사 목록만 보여 드립니다."
        except Exception as error:
            # 기사 하나가 실패해도 나머지 기사는 계속 요약합니다.
            print(f"요약 실패: {article['title']} ({error})")

        if not article["ai_summary"]:
            failed += 1

    if failed:
        return f"기사 {failed}개는 AI 요약을 만들지 못했습니다."
    return ""


def format_date(date):
    """날짜 값을 한국시간 글자로 바꿉니다. 날짜가 없으면 빈 글자를 돌려줍니다."""
    if date is None:
        return ""
    return date.astimezone(KOREA_TIME).strftime("%Y-%m-%d %H:%M")


def format_article(article):
    """저장할 항목만 골라 정리합니다. 소개문(summary)은 저장하지 않습니다."""
    return {
        "title": article["title"],
        "link": article["link"],
        "date": format_date(article["date"]),
        "feed": article["feed"],
        "source": article["source"],
        "matched_keywords": article["matched_keywords"],  # 없으면 빈 목록 []
        "ai_summary": article["ai_summary"],  # 실패하면 빈 목록 []
    }


def article_to_html(article):
    """기사 하나를 HTML 조각으로 만듭니다."""
    # html.escape 는 < 같은 글자를 안전한 표기로 바꿉니다.
    # 기사 제목이나 AI 답에 태그가 섞여 있어도 글자로만 보이게 하는 장치입니다.
    title = html.escape(article["title"])
    source = html.escape(article["source"])

    if article["ai_summary"]:
        # 앞의 "- " 두 글자는 떼어 내고 목록 점으로 보여 줍니다.
        items = "".join(
            f"<li>{html.escape(line[2:])}</li>" for line in article["ai_summary"]
        )
        summary = f"<ul>{items}</ul>"
    else:
        summary = '<p class="no-summary">요약 없음</p>'

    # http 나 https 로 시작하는 주소만 링크로 만듭니다.
    link = "원문 링크 없음"
    if article["link"].startswith(("http://", "https://")):
        url = html.escape(article["link"], quote=True)
        link = f'<a href="{url}" target="_blank" rel="noopener noreferrer">원문 보기</a>'

    return (
        f"<article><h2>{title}</h2>{summary}"
        f'<p class="meta">{source} · {link}</p></article>'
    )


def build_page(collected_at, articles, notices):
    """브리핑 페이지 전체의 HTML 을 만듭니다."""
    title = html.escape(PAGE_TITLE)
    notice_html = "".join(
        f'<p class="notice">{html.escape(notice)}</p>' for notice in notices
    )
    article_html = "\n".join(article_to_html(article) for article in articles)
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{PAGE_STYLE}</style>
</head>
<body>
<div class="wrap">
<header>
<h1>{title}</h1>
<p class="time">수집 시각: {html.escape(collected_at)}</p>
</header>
<main>
{notice_html}
{article_html}
</main>
<footer>AI 요약은 틀릴 수 있음</footer>
</div>
</body>
</html>
"""


def save_page(collected_at, articles, notices):
    """브리핑 페이지를 파일로 저장합니다."""
    with open(PAGE_FILE, "w", encoding="utf-8") as file:
        file.write(build_page(collected_at, articles, notices))


def main():
    """프로그램의 전체 순서를 담당합니다."""
    sys.stdout.reconfigure(encoding="utf-8")

    settings = load_settings()
    keywords = settings["keywords"]
    collected_at = datetime.now(KOREA_TIME).strftime("%Y-%m-%d %H:%M")

    articles = []
    errors = []
    for feed in settings["feeds"]:
        try:
            articles.extend(fetch_articles(feed))
        except Exception as error:
            # 주소 하나가 실패해도 나머지는 계속 가져옵니다.
            errors.append({"feed": feed["name"], "error": str(error)})

    # 기사를 하나도 못 가져오면, 예전 news.json 을 빈 파일로 덮어쓰지 않습니다.
    # 페이지는 항상 만들어지도록, 안내 문구만 있는 index.html 을 저장합니다.
    if not articles:
        save_page(collected_at, [], ["기사를 하나도 가져오지 못했습니다."])
        print("기사를 하나도 가져오지 못했습니다. news.json 을 바꾸지 않았습니다.")
        print(json.dumps(errors, ensure_ascii=False, indent=2))
        sys.exit(1)  # 1 은 "실패로 끝났다"는 표시입니다.

    # 최신 기사가 남도록 정렬한 다음 중복을 지웁니다.
    sort_newest_first(articles)
    selected = select_articles(remove_duplicates(articles), keywords)

    # 요약을 만들고, 페이지에 보여 줄 안내 문구를 모읍니다.
    notices = []
    summary_notice = summarize_articles(selected, load_api_key())
    if summary_notice:
        notices.append(summary_notice)
    if errors:
        failed_feeds = ", ".join(error["feed"] for error in errors)
        notices.append(f"가져오지 못한 피드: {failed_feeds}")

    result = {
        "generated_at": collected_at,
        "keywords": keywords,
        "articles": [format_article(article) for article in selected],
        "errors": errors,  # 실패한 피드가 없으면 빈 목록 []
    }

    # "w" 는 쓰기 모드입니다. 파일이 있으면 새 내용으로 바꿉니다.
    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)

    save_page(collected_at, selected, notices)

    print(f"기사 {len(result['articles'])}개를 {OUTPUT_FILE} 에 저장했습니다.")
    print(f"브리핑 페이지를 {PAGE_FILE} 에 저장했습니다.")
    for notice in notices:
        print(f"알림: {notice}")


# ----- 4. 프로그램 시작 ---------------------------------------
if __name__ == "__main__":
    main()
