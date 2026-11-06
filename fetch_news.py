# =============================================================
# fetch_news.py
# settings.json 에 적힌 RSS 주소마다 최신 글 3개를 가져와서
# 제목, 링크, 날짜를 JSON 형식으로 화면에 보여 주는 프로그램입니다.
#
# 실행 방법: 터미널에서 python fetch_news.py
# =============================================================

# ----- 1. 도구 불러오기 ---------------------------------------
# import 는 "Python 에 들어 있는 도구를 꺼내 쓰겠다"는 뜻입니다.
# 아래는 모두 Python 기본 기능이라 따로 설치할 것이 없습니다.
import json  # JSON 파일을 읽고, JSON 글자로 만들어 줍니다.
import re  # 글자의 패턴을 찾아 바꿔 줍니다.
import sys  # 화면 출력 설정을 바꿀 때 씁니다.
import urllib.request  # 인터넷 주소에 접속합니다.
import xml.etree.ElementTree as ET  # RSS(XML 형식)를 읽습니다.
from datetime import datetime, timedelta, timezone  # 날짜와 시간을 다룹니다.
from email.utils import parsedate_to_datetime  # RSS 날짜 글자를 날짜로 바꿉니다.

# ----- 2. 바꿔 쓸 수 있는 값 -----------------------------------
# 이름을 대문자로 쓰면 "프로그램 내내 바뀌지 않는 값"이라는 표시입니다.
SETTINGS_FILE = "settings.json"  # 설정 파일 이름
ITEMS_PER_FEED = 3  # 주소 하나에서 가져올 글 개수
TIMEOUT_SECONDS = 15  # 이 시간 안에 응답이 없으면 포기합니다.
KOREA_TIME = timezone(timedelta(hours=9))  # 한국시간은 세계 표준시 + 9시간


# ----- 3. 함수 만들기 -----------------------------------------
# def 는 여러 줄의 작업에 이름을 붙이는 것입니다.
# 여기서는 만들어 두기만 하고, 맨 아래에서 실제로 실행합니다.


def load_settings():
    """settings.json 파일을 읽어서 Python 데이터로 돌려줍니다."""
    # 한글이 깨지지 않도록 encoding="utf-8" 을 지정합니다.
    with open(SETTINGS_FILE, encoding="utf-8") as file:
        return json.load(file)


def download(url):
    """인터넷 주소의 내용을 내려받아 돌려줍니다."""
    # User-Agent 는 "어떤 프로그램이 접속했는지" 알려 주는 이름표입니다.
    # 이름표가 없으면 접속을 막는 사이트도 있어서 넣어 줍니다.
    request = urllib.request.Request(url, headers={"User-Agent": "NewsBriefing/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read()


def parse_date(text):
    """RSS 날짜 글자를 날짜 값으로 바꿉니다. 실패하면 None 을 돌려줍니다."""
    # None 은 "값이 없음"을 뜻합니다.
    if not text:
        return None

    # 매일경제는 끝이 "+09:00", 구글 뉴스는 "GMT" 입니다.
    # Python 은 "+09:00" 의 콜론(:)을 제대로 읽지 못해서 "+0900" 으로 고칩니다.
    # 콜론을 그대로 두면 시간대 정보가 사라집니다.
    text = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", text.strip())

    # try / except 는 "해 보고, 오류가 나면 멈추지 말고 이렇게 하라"는 뜻입니다.
    try:
        date = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None

    # 시간대가 안 적힌 날짜는 한국시간으로 간주합니다.
    if date.tzinfo is None:
        date = date.replace(tzinfo=KOREA_TIME)
    return date


def get_latest_items(url):
    """RSS 주소에서 최신 글을 골라 목록으로 돌려줍니다."""
    # 내려받은 내용을 나무 모양의 구조로 읽습니다.
    root = ET.fromstring(download(url))

    items = []
    # RSS 에서 글 하나는 <channel> 안의 <item> 하나입니다.
    for item in root.findall("./channel/item"):
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "date": parse_date(item.findtext("pubDate")),
            }
        )

    # 피드의 순서를 믿지 않고, 날짜를 직접 비교해 최신순으로 정렬합니다.
    # 날짜가 없는 글은 가장 오래된 날짜로 쳐서 맨 뒤로 보냅니다.
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    items.sort(key=lambda item: item["date"] or oldest, reverse=True)

    # [:3] 처럼 쓰면 앞에서부터 3개만 잘라 옵니다.
    latest = items[:ITEMS_PER_FEED]

    # 날짜 값은 JSON 에 그대로 넣을 수 없어서, 한국시간 글자로 바꿉니다.
    for item in latest:
        if item["date"] is None:
            item["date"] = ""
        else:
            item["date"] = item["date"].astimezone(KOREA_TIME).strftime("%Y-%m-%d %H:%M")
    return latest


def main():
    """프로그램의 전체 순서를 담당합니다."""
    # 윈도우 터미널에서 한글이 깨지지 않도록 출력 방식을 정합니다.
    sys.stdout.reconfigure(encoding="utf-8")

    settings = load_settings()
    results = []

    # settings.json 의 주소를 하나씩 꺼내서 처리합니다.
    for feed in settings["feeds"]:
        result = {"feed": feed["name"], "items": []}
        try:
            result["items"] = get_latest_items(feed["url"])
        except Exception as error:
            # 주소 하나가 실패해도 나머지는 계속 가져오도록, 오류만 기록합니다.
            result["error"] = str(error)
        results.append(result)

    # ensure_ascii=False: 한글을 그대로 보여 줍니다.
    # indent=2: 줄을 바꾸고 들여 써서 읽기 좋게 합니다.
    print(json.dumps(results, ensure_ascii=False, indent=2))


# ----- 4. 프로그램 시작 ---------------------------------------
# 이 파일을 직접 실행했을 때만 main() 을 부릅니다.
if __name__ == "__main__":
    main()
