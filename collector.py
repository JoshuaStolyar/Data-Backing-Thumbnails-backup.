#!/usr/bin/env python3
import csv, json, os, re, statistics, sys, time
import urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CHANNELS = ",".join([
    "@DharMann", "@MSA.official", "@AlanChikinChow", "@tyler.vitelli", "@MrBeast",
    "@dramatizeme", "@sameerbhavnani", "@vidchronicles", "@totally", "@thebeastfamily",
    "@chainsfr", "@Unspeakable", "@Haminations", "@InfamousSwoosh", "@coopergalanis",
    "@jaidenanimations", "@Guad", "@StoryTimeAnimated", "@theodd1sout", "@sockstudios6010",
    "@BugsAnimations", "@MrBallen", "@mrnightmare", "@IMRScaryTales", "@ChillingScares",
    "@scribblejuice", "@DrNoSleep", "@HorrorShortsParty", "@Torec_", "@GameToonsOfficial",
    "@shaneplays2", "@oblivioushd_", "@NickDiGiovanni", "@royaltyfam", "@stokestwins",
    "@ryan", "@soulsnackstudios", "@lifelessonswithluis", "@illumeably", "@storybooth",
    "@domics", "@alanbecker", "@benazelart", "@betasquad", "@dudeperfect", "@airrack",
])
CHANNELS = [c.strip() for c in os.environ.get("CHANNELS", DEFAULT_CHANNELS).split(",") if c.strip()]
VIDEOS_PER_CHANNEL = 600
MIN_LENGTH_SECONDS = 240
MIN_AGE_DAYS = 14
OUTLIER_MIN = float(os.environ.get("OUTLIER_MIN", 2.0))
MAX_VIDEOS = 3000
DB_MIN_VIDEOS = 3
DB_MIN_CHANNELS = 2
EDGE_MIN = 1
PHRASE_MIN = 3

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)
YT_KEY = os.environ.get("YT_API_KEY", "").strip()

STOPWORDS = set("""
a an the of in on at for and or but to from with by is are was were be been being
this that these those my your his her its our their i you he she it we they
what when where who whom why how will would can could should do does did not no
so if than then up out about into over after before again more most some such
only just also very too get got one two three all has have had us me him them s t
re ve ll d new full part video official ft vs episode ep
tell told tells telling make made makes making want wants wanted know knows knew
see sees saw seen give gives gave given take takes took taken come comes came
let lets left find finds found help helps helped leave leaves keep keeps kept
call calls called try tries tried ask asks asked need needs needed feel feels felt
become becomes became show shows showed say says said went gets goes going
finally suddenly literally actually really always never every everyone everything
because while when after before during until unless though although
i'm it's don't can't won't didn't isn't wasn't that's there's he's she's we're
you're they're i've i'll you'll we'll they'll i'd you'd he'd she'd we'd they'd
happens happened next watch watches watching video videos
off away back down around through against upon within without along across
near inside outside underneath beneath above below toward towards apart aside
stories story compilation compilations moments
""".split())

BRAND_WORDS = set()

# named topic categories for color coding. Order is fixed (maps to fixed palette
# slots in the front end) - a keyword is put in the first category whose trigger
# word appears anywhere in it.
CATEGORIES = [
    ("family", "mom mother mama dad father papa daughter son brother sister sibling "
                "siblings parent parents grandma grandpa grandmother grandfather aunt "
                "uncle cousin family wife husband twin twins baby kid kids child children "
                "pregnant pregnancy adopted adoption"),
    ("challenge & stunt", "survive survived survival days hours challenge spent stranded "
                "island world's biggest smallest extreme dangerous escape trapped alone"),
    ("danger & crime", "killer murder caught secret secretly kidnap kidnapped police cop "
                "arrested prison jail gang robbery robbed scam scammed stalker karen "
                "criminal crime serial catfish predator abuse abused evil villain disturbing"),
    ("money & status", "billionaire millionaire rich poor broke money bank cash "
                "inheritance lottery homeless mansion job fired hired boss ceo waitress "
                "employee waiter janitor rags"),
    ("school & youth", "school teacher student teen class classroom bully bullied "
                "principal college prom graduation nerd popular jock"),
    ("romance", "love date dating boyfriend girlfriend crush marry wedding engaged "
                "divorce affair cheat cheating cheated ex proposal"),
    ("people & identity", "girl boy man woman guy lady kid's teenager adult stranger "
                "neighbor bystander influencer youtuber celebrity stranger's famous"),
    ("home & property", "house home room apartment garage basement attic backyard "
                "neighborhood mansion property rooms"),
]
CATEGORY_WORDS = [(name, set(words.split())) for name, words in CATEGORIES]

def categorize(keyword):
    tokens = keyword.split()
    for idx, (name, words) in enumerate(CATEGORY_WORDS):
        if any(t in words for t in tokens):
            return idx
    return -1

def significant_sequence(title):
    raw = re.findall(r"[a-z0-9']+", title.lower())
    sig, pos = [], []
    for i, w in enumerate(raw):
        if w in STOPWORDS or w in BRAND_WORDS or len(w) < 3 or w.isdigit():
            continue
        sig.append(w); pos.append(i)
    return raw, sig, pos

def extract_topics_and_premises(title, phrase_counts):
    raw, sig, pos = significant_sequence(title)
    results, i = [], 0
    while i < len(sig):
        n = 1
        for cand in (3, 2):
            if i + cand <= len(sig):
                phrase = " ".join(sig[i:i + cand])
                if phrase_counts.get(phrase, 0) >= PHRASE_MIN:
                    n = cand
                    break
        topic = " ".join(sig[i:i + n])
        last_raw = pos[i + n - 1]
        extra = [w for w in raw[last_raw + 1:last_raw + 4] if w not in BRAND_WORDS]
        while extra and extra[-1] in STOPWORDS:
            extra.pop()
        premise = topic if not extra else topic + " " + " ".join(extra)
        results.append((topic, premise))
        i += n
    return results

def phrase_frequency(titles):
    counts = {}
    for title in titles:
        _, sig, _ = significant_sequence(title)
        for n in (2, 3):
            for i in range(len(sig) - n + 1):
                phrase = " ".join(sig[i:i + n])
                counts[phrase] = counts.get(phrase, 0) + 1
    return counts

def die(msg):
    print(f"\n[stopped] {msg}\n"); sys.exit(1)

def http_json(url, data=None, headers=None, retries=3):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="ignore")
            if e.code in (429, 500, 502, 503, 529) and attempt < retries - 1:
                time.sleep(5 * (attempt + 1)); continue
            die(f"HTTP {e.code} from {url.split('?')[0]}\n{text[:600]}")
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(3); continue
            die(f"Network error: {e}")

def yt(endpoint, **params):
    params["key"] = YT_KEY
    return http_json(f"https://www.googleapis.com/youtube/v3/{endpoint}?" + urllib.parse.urlencode(params))

def parse_channel(entry):
    m = re.search(r"(UC[\w-]{22})", entry)
    if m: return {"id": m.group(1)}
    m = re.search(r"@([\w.\-]+)", entry)
    if m: return {"forHandle": "@" + m.group(1)}
    return {"forHandle": "@" + entry.strip()}

def get_channel(entry):
    items = yt("channels", part="snippet,contentDetails,statistics", **parse_channel(entry)).get("items") or []
    if not items:
        print(f"  could not find channel: {entry}"); return None
    c = items[0]
    return {"id": c["id"], "name": c["snippet"]["title"], "uploads": c["contentDetails"]["relatedPlaylists"]["uploads"],
            "subs": int(c.get("statistics", {}).get("subscriberCount", 0) or 0),
            "url": f"https://www.youtube.com/channel/{c['id']}"}

def iso_seconds(d):
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m: return 0
    days, h, mi, s = (int(x or 0) for x in m.groups())
    return days*86400 + h*3600 + mi*60 + s

def fetch_channel_videos(ch):
    cf = CACHE / f"videos_{ch['id']}.json"
    if cf.exists(): return json.loads(cf.read_text())
    ids, token = [], None
    while len(ids) < VIDEOS_PER_CHANNEL:
        p = {"part": "contentDetails", "playlistId": ch["uploads"], "maxResults": 50}
        if token: p["pageToken"] = token
        res = yt("playlistItems", **p)
        ids += [i["contentDetails"]["videoId"] for i in res.get("items", [])]
        token = res.get("nextPageToken")
        if not token: break
    ids = ids[:VIDEOS_PER_CHANNEL]
    videos = []
    for i in range(0, len(ids), 50):
        for v in yt("videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i+50])).get("items", []):
            sn, st = v["snippet"], v.get("statistics", {})
            th = sn.get("thumbnails", {})
            thumb = (th.get("maxres") or th.get("high") or th.get("medium") or {}).get("url", "")
            videos.append({"id": v["id"], "title": sn["title"], "channel": ch["name"], "published": sn["publishedAt"],
                "views": int(st.get("viewCount", 0) or 0), "seconds": iso_seconds(v["contentDetails"].get("duration")),
                "thumb": thumb, "url": f"https://www.youtube.com/watch?v={v['id']}"})
    cf.write_text(json.dumps(videos))
    return videos

def score_outliers(videos):
    now = datetime.now(timezone.utc)
    keep = [v for v in videos if v["seconds"] >= MIN_LENGTH_SECONDS and v["views"] > 0 and
            (now - datetime.fromisoformat(v["published"].replace("Z", "+00:00"))).days >= MIN_AGE_DAYS]
    if len(keep) < 5: return []
    avg = statistics.mean(v["views"] for v in keep)
    for v in keep:
        v["channel_avg"] = int(avg); v["outlier"] = round(v["views"] / avg, 2)
    return keep

def pair_counts_from_sequences(video_keyword_sequences):
    counts = {}
    for seq in video_keyword_sequences:
        for i in range(len(seq) - 1):
            pair = tuple(sorted((seq[i], seq[i + 1])))
            if pair[0] == pair[1]: continue
            counts[pair] = counts.get(pair, 0) + 1
    return counts

def build_library(outliers, channel_stats):
    phrase_counts = phrase_frequency([v["title"] for v in outliers])
    rows, video_keyword_sequences = [], []
    for v in outliers:
        seen, seq = set(), []
        for kw, premise in extract_topics_and_premises(v["title"], phrase_counts):
            if kw in seen: continue
            seen.add(kw); seq.append(kw)
            rows.append({**v, "keyword": kw, "premise": premise})
        if seq: video_keyword_sequences.append(seq)
    groups = {}
    for r in rows: groups.setdefault(r["keyword"], []).append(r)
    pair_counts = pair_counts_from_sequences(video_keyword_sequences)
    keywords = []
    for kw, vids in groups.items():
        chans = {v["channel"] for v in vids}
        prem = {}
        for v in vids: prem.setdefault(v["premise"], []).append(v)
        plist = sorted([{"premise": p, "count": len(pv), "median_outlier": round(statistics.median(x["outlier"] for x in pv), 2),
                         "videos": sorted(pv, key=lambda x: -x["outlier"])} for p, pv in prem.items()],
                       key=lambda p: (-p["count"], -p["median_outlier"]))
        med = round(statistics.median(v["outlier"] for v in vids), 2)
        keywords.append({"keyword": kw, "count": len(vids), "channels": len(chans), "median_outlier": med,
            "data_backed": len(vids) >= DB_MIN_VIDEOS and len(chans) >= DB_MIN_CHANNELS,
            "category": categorize(kw),
            "score": round(len(vids) * med * (1 + 0.25 * (len(chans) - 1)), 2), "premises": plist})
    keywords.sort(key=lambda k: -k["score"])
    kw_set = {k["keyword"] for k in keywords}
    edges = [{"a": a, "b": b, "w": w} for (a, b), w in pair_counts.items()
             if w >= EDGE_MIN and a in kw_set and b in kw_set]
    with open(HERE / "library.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["keyword", "premise", "title", "channel", "views", "outlier", "url", "thumbnail"])
        for k in keywords:
            for p in k["premises"]:
                for v in p["videos"]:
                    w.writerow([k["keyword"], p["premise"], v["title"], v["channel"], v["views"], v["outlier"], v["url"], v["thumb"]])
    payload = {"generated": datetime.now().strftime("%b %d, %Y at %I:%M %p"),
               "channels": sorted({v["channel"] for v in outliers}),
               "channel_stats": sorted(channel_stats, key=lambda c: -c["subs"]),
               "outlier_min": OUTLIER_MIN,
               "total": len(outliers), "rule": f"{DB_MIN_VIDEOS}+ outlier videos across {DB_MIN_CHANNELS}+ channels",
               "categories": [name for name, _ in CATEGORIES],
               "keywords": keywords, "edges": edges}
    html = (HERE / "library_template.html").read_text().replace("/*__DATA__*/null", json.dumps(payload).replace("</", "<\\/"))
    (HERE / "library.html").write_text(html)

def main():
    if not YT_KEY: die("Missing YouTube key")
    print("1. Pulling channels")
    outs, channel_stats = [], []
    for entry in CHANNELS:
        ch = get_channel(entry)
        if not ch: continue
        BRAND_WORDS.update(re.findall(r"[a-z0-9']+", ch["name"].lower()))
        vids = fetch_channel_videos(ch)
        scored = score_outliers(vids)
        o = [v for v in scored if v["outlier"] >= OUTLIER_MIN]
        avg_views = scored[0]["channel_avg"] if scored else 0
        print(f"  {ch['name']} ({ch['subs']:,} subs): {len(vids)} uploads, {len(scored)} long form, "
              f"avg {avg_views:,} views, {len(o)} outliers at {OUTLIER_MIN}x+ this channel's own long-form average")
        channel_stats.append({"name": ch["name"], "subs": ch["subs"], "url": ch["url"], "uploads_scanned": len(vids),
                               "long_form": len(scored), "outliers": len(o), "avg_views": avg_views})
        outs += o
    if not outs: die("No outliers found. Add more channels or lower OUTLIER_MIN.")
    outs = sorted(outs, key=lambda v: -v["outlier"])[:MAX_VIDEOS]
    print("\n2. Extracting data backed keywords from titles")
    build_library(outs, channel_stats)
    print(f"  done. Opening {HERE / 'library.html'}")

if __name__ == "__main__":
    main()
