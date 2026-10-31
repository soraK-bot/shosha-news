#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
商社就活ニュース 取得エンジン
--------------------------------
各社ごとに Google ニュースの検索RSSを取得し、
重複除去 → 自動タグ付け（ハッシュタグ）→ AI要約 を行って
data/news.json に書き出す。

GitHub Actions 上で定期実行される想定。
ローカルや手元PCでも `python collect.py` で動く。

AI要約は環境変数 ANTHROPIC_API_KEY があるときだけ有効。
無ければ記事の説明文をそのまま要約として使う（無料・キー不要でも動く）。
"""

import os
import re
import json
import html
import time
import hashlib
import urllib.parse
from datetime import datetime, timezone

import requests
import feedparser

# ----------------------------------------------------------------------
# 設定
# ----------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data", "news.json")

# 1記事あたり保持する最大件数（古いものから捨てる）
MAX_ARTICLES = 600
# 1社あたり1回の取得で見る件数
PER_COMPANY_LIMIT = 25

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5").strip()

# 対象企業（id は英字、name は表示名、query はニュース検索語）
# category: "総合"（7大総合商社）/ "専門"
COMPANIES = [
    # ---- 7大総合商社 ----
    {"id": "mitsubishi",   "name": "三菱商事",         "category": "総合", "query": "三菱商事"},
    {"id": "mitsui",       "name": "三井物産",         "category": "総合", "query": "三井物産"},
    {"id": "itochu",       "name": "伊藤忠商事",       "category": "総合", "query": "伊藤忠商事"},
    {"id": "sumitomo",     "name": "住友商事",         "category": "総合", "query": "住友商事"},
    {"id": "marubeni",     "name": "丸紅",             "category": "総合", "query": "丸紅"},
    {"id": "toyotatsusho", "name": "豊田通商",         "category": "総合", "query": "豊田通商"},
    {"id": "sojitz",       "name": "双日",             "category": "総合", "query": "双日 商社"},
    # ---- 専門商社（指定分）----
    {"id": "kanematsu",    "name": "兼松",             "category": "専門", "query": "兼松 商社"},
    {"id": "benichu",      "name": "伊藤忠丸紅鉄鋼",   "category": "専門", "query": "伊藤忠丸紅鉄鋼"},
    {"id": "nagase",       "name": "長瀬産業",         "category": "専門", "query": "長瀬産業"},
    {"id": "metalone",     "name": "メタルワン",       "category": "専門", "query": "メタルワン"},
    {"id": "jfeshoji",     "name": "JFE商事",          "category": "専門", "query": "JFE商事"},
]

# 自動タグ付けルール：タグ名 -> そのタグを付けるキーワード群
# （タイトル・要約のどちらかに含まれれば付与。複数該当すれば複数付く）
TAG_RULES = {
    "決算":     ["決算", "純利益", "営業利益", "最終益", "最終利益", "増益", "減益", "四半期", "通期", "営業益"],
    "業績予想": ["業績予想", "上方修正", "下方修正", "見通し", "予想を", "最高益"],
    "株主還元": ["配当", "増配", "自社株買い", "株主還元", "自己株式"],
    "投資":     ["出資", "投資", "取得", "権益", "参画"],
    "M&A":      ["買収", "子会社化", "合併", "TOB", "売却", "株式譲渡", "完全子会社"],
    "提携":     ["提携", "協業", "合弁", "パートナー", "共同", "協定", "連携"],
    "資源":     ["石炭", "原油", "LNG", "天然ガス", "鉄鉱石", "銅", "ニッケル", "リチウム", "鉱山", "資源", "権益", "原料"],
    "脱炭素":   ["脱炭素", "再エネ", "再生可能", "水素", "アンモニア", "カーボン", "CO2", "洋上風力", "太陽光", "SAF", "e-メタン", "GX"],
    "DX":       ["DX", "デジタル", "AI", "生成AI", "データセンター", "半導体", "システム"],
    "新規事業": ["新規事業", "新会社", "事業化", "新事業", "参入", "立ち上げ"],
    "海外":     ["米国", "欧州", "アジア", "インド", "ブラジル", "中国", "海外", "現地", "豪州", "東南アジア", "中東", "アフリカ"],
    "食料":     ["食料", "食品", "農業", "穀物", "水産", "飼料", "コンビニ", "ローソン"],
    "人事":     ["社長", "会長", "人事", "役員", "就任", "退任", "CEO", "トップ人事"],
    "サステナ": ["サステナ", "ESG", "人権", "環境", "生物多様性"],
    "就活":     ["採用", "新卒", "初任給", "インターン", "内定", "就活", "年収"],
}

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={q}&hl=ja&gl=JP&ceid=JP:ja"
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; ShoshaNewsBot/1.0; personal use)"
)


# ----------------------------------------------------------------------
# ユーティリティ
# ----------------------------------------------------------------------

def strip_html(text: str) -> str:
    """HTMLタグを除去し、実体参照をほどく。"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def split_source(title: str):
    """Google ニュースのタイトル『本文 - メディア名』を分ける。"""
    if " - " in title:
        head, _, tail = title.rpartition(" - ")
        if head and tail and len(tail) <= 30:
            return head.strip(), tail.strip()
    return title.strip(), ""


def normalize_key(title: str) -> str:
    """重複判定用のキー。記号・空白をならして小文字化。"""
    t = re.sub(r"[\s　\-|｜<>「」【】\[\]（）()、。,.!?！？:：/・]", "", title)
    return t.lower()


def make_id(url: str, title: str) -> str:
    # 同じニュースが複数メディアから出ても1件にまとめたいので、
    # URLではなく「正規化したタイトル」だけでIDを作る（最初に拾った1件を残す）。
    base = normalize_key(title)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def to_iso(entry) -> str:
    """RSSの日付を ISO8601(UTC) に。取れなければ現在時刻。"""
    tm = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if tm:
        try:
            return datetime(*tm[:6], tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def auto_tags(text: str):
    """タイトル＋要約からハッシュタグ対象のタグ名リストを返す。"""
    found = []
    for tag, keywords in TAG_RULES.items():
        for kw in keywords:
            if kw.lower() in text.lower():
                found.append(tag)
                break
    return found


def detect_extra_companies(text: str, primary_id: str):
    """本文に他社名が出ていれば、その会社idも関連付ける。"""
    ids = []
    for c in COMPANIES:
        if c["id"] == primary_id:
            continue
        if c["name"] in text:
            ids.append(c["id"])
    return ids


# ----------------------------------------------------------------------
# AI要約
# ----------------------------------------------------------------------

def ai_summarize(title: str, desc: str) -> str:
    """ANTHROPIC_API_KEY があれば AI で1〜2文要約。無ければ説明文を返す。"""
    fallback = desc if desc else title
    fallback = fallback[:140]
    if not ANTHROPIC_API_KEY:
        return fallback

    prompt = (
        "あなたは就活生向けニュースアプリの編集者です。"
        "次の商社関連ニュースの見出しと説明から、就活で押さえるべき要点を"
        "日本語で1〜2文（最大80字程度）に要約してください。"
        "誇張せず事実のみ。前置きや記号は不要で要約本文だけを返す。\n\n"
        f"見出し: {title}\n説明: {desc}"
    )
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            parts = data.get("content", [])
            out = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
            out = out.strip()
            if out:
                return out
        else:
            print(f"  [AI要約] HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        print(f"  [AI要約] 失敗: {e}")
    return fallback


# ----------------------------------------------------------------------
# 取得
# ----------------------------------------------------------------------

def fetch_company(company: dict):
    """1社分のRSSを取得して記事dictのリストを返す。"""
    q = urllib.parse.quote(company["query"])
    url = GOOGLE_NEWS_RSS.format(q=q)
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        feed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"  [取得失敗] {company['name']}: {e}")
        return []

    out = []
    for entry in feed.entries[:PER_COMPANY_LIMIT]:
        raw_title = getattr(entry, "title", "")
        title, source = split_source(raw_title)
        if not getattr(entry, "source", None) is None:
            source = source or getattr(entry.source, "title", "")
        desc = strip_html(getattr(entry, "summary", ""))
        link = getattr(entry, "link", "")
        out.append({
            "title": title,
            "url": link,
            "source": source,
            "published": to_iso(entry),
            "primary": company["id"],
            "desc": desc,
        })
    return out


def load_existing():
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"updated_at": None, "companies": [], "articles": []}


def build():
    existing = load_existing()
    by_id = {a["id"]: a for a in existing.get("articles", [])}

    new_count = 0
    summarized = 0
    # この回の取得で、各ニュース(aid)を何社のメディアが報じたかを数える
    run_sources = {}

    for c in COMPANIES:
        print(f"取得中: {c['name']}")
        for item in fetch_company(c):
            aid = make_id(item["url"], item["title"])
            text = item["title"] + " " + item["desc"]
            tags = auto_tags(text)
            companies_ids = [item["primary"]] + detect_extra_companies(text, item["primary"])

            src = (item.get("source") or "").strip()
            if src:
                run_sources.setdefault(aid, set()).add(src)

            if aid in by_id:
                # 既存：会社の関連付けとタグだけ更新（要約は再生成しない=コスト節約）
                a = by_id[aid]
                a["company_ids"] = sorted(set(a.get("company_ids", []) + companies_ids))
                a["tags"] = sorted(set(a.get("tags", []) + tags))
            else:
                summary = ai_summarize(item["title"], item["desc"])
                if ANTHROPIC_API_KEY:
                    summarized += 1
                    time.sleep(0.2)  # レート配慮
                by_id[aid] = {
                    "id": aid,
                    "title": item["title"],
                    "url": item["url"],
                    "source": item["source"],
                    "published": item["published"],
                    "company_ids": sorted(set(companies_ids)),
                    "tags": sorted(set(tags)),
                    "summary": summary,
                    "source_count": 1,
                }
                new_count += 1

    # この回で報じたメディア数を各記事に反映（週次ダイジェストの重要度に使う）
    for aid, srcs in run_sources.items():
        if aid in by_id:
            prev = by_id[aid].get("source_count", 1) or 1
            by_id[aid]["source_count"] = max(len(srcs), prev)

    # 並べ替え（新しい順）＆上限
    articles = sorted(by_id.values(), key=lambda a: a["published"], reverse=True)
    articles = articles[:MAX_ARTICLES]

    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "companies": COMPANIES,
        "tags": list(TAG_RULES.keys()),
        "articles": articles,
    }

    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n完了: 新規 {new_count} 件 / 合計 {len(articles)} 件 / AI要約 {summarized} 件")
    print(f"書き出し: {DATA_PATH}")


if __name__ == "__main__":
    build()
