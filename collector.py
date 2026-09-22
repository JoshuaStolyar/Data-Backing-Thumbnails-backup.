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
    "@honeyentertainmentinc", "@illymation", "@llamaarts", "@this-is-naxon", "@heresmystory",
    "@meetmystory", "@mda.mydiaryanimated", "@baileysarian", "@jcs", "@rottenmangopod",
    "@stephaniesoo", "@kendallrae", "@eleanorneale", "@thatchapter", "@christinaarandall",
    "@billyforreal", "@drinsanitycrime", "@ewubodycam", "@LawAndCrime", "@Bodycamlockup",
    "@bodycamfiles", "@PoliceOnScene", "@most_dangerous", "@the.rebelkid",
    "@reddnea", "@joebartolozzi", "@jen_animation",
    "@brew", "@babynojamie", "@snook_yt", "@kallmekris", "@drovenmc", "@redditor",
    "@bloxbustersmovies", "@euina", "@cuterobloxtv", "@shibaberry002", "@honeyberryroblox",
    "@trxsted_stories", "@burdieofficial", "@letmeexplainstudios", "@mjvanimations",
    "@jaicemations", "@thepaintexplainer", "@henryzhangishappy", "@icecreamsandwich", "@sambucha",
    "@plan3", "@hartyt_", "@jahandraws", "@yaurhan", "@onzlemur", "@boog9ner", "@zephfire_16",
    "@udy", "@justpegi", "@unemployedandunfunny", "@dharmannstudiostopvideos",
    "@saildust", "@mrwhosetheboss", "@notexttospeech", "@willtennyson", "@ryoga.training",
    "@vladimirfitness", "@tommynfg", "@matthewbeem", "@alexarivera", "@brentrivera",
    "@irlcaylus", "@foltynofficial", "@terragreen1", "@mackhopkins", "@tylerblanchard",
])
CHANNELS = [c.strip() for c in os.environ.get("CHANNELS", DEFAULT_CHANNELS).split(",") if c.strip()]
VIDEOS_PER_CHANNEL = 600
MIN_LENGTH_SECONDS = 240
MIN_AGE_DAYS = 14
OUTLIER_MIN = float(os.environ.get("OUTLIER_MIN", 2.0))
MAX_AGE_DAYS_FOR_LOW_VIEWS = 4 * 365
MIN_VIEWS_IF_OLD = 3_000_000
MAX_VIDEOS = 3000
DB_MIN_VIDEOS = 3
DB_MIN_CHANNELS = 2
EDGE_MIN = 2
LIFT_MIN = 2.0
PHRASE_MIN = 3
MAX_KEYWORDS = 500

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)
YT_KEY = os.environ.get("YT_API_KEY", "").strip()

STOPWORDS = set("""
a an the of in on at for and or but to from with by is are was were be been being
this that these those my your his her its our their i you he she it we they
when where whom will would can could should do does did not no
so if than then up out about into over again more most some such
only just also very too get got one two three all has have had us me him them s t
re ve ll d new full part video official ft episode ep
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
off away back down around through against upon within along across
near inside outside underneath beneath above below toward towards apart aside
stories story compilation compilations moments
""".split())

BRAND_WORDS = set()

# --- five-slot narrative taxonomy: [WHO] did [ACTION] and [ENDING], with [STAKES] ---
# AMPLIFIER is separate: descriptor/adjective words that intensify or characterize
# without being one of the four narrative-grammar slots themselves.
# Precedence when a keyword's tokens hit more than one slot's word list: WHO, then
# ACTION, ENDING, STAKES (matches the grammar order writers think in), AMPLIFIER last.
SLOTS = ["WHO", "ACTION", "ENDING", "STAKES", "AMPLIFIER"]

def token_in(t, word_set):
    if t in word_set: return True
    if t.endswith("s") and t[:-1] in word_set: return True  # cheap plural match: cops -> cop, girls -> girl
    return False

WHO_RELATIONSHIP = set("""
mom mother mama dad father papa stepmom stepdad stepfather
stepmother wife husband
sister brother daughter son cousin aunt uncle grandma grandpa grandmother
grandfather boyfriend girlfriend fiance fiancee ex nephew niece twin sibling
siblings parent parents
stepson stepdaughter foster adopted spouse widow
widower
""".split())

WHO_IDENTITY = set("""
landlord tenant neighbor boss employee coworker teacher student nerd stranger
waitress waiter janitor cop police karen bully billionaire millionaire
celebrity influencer youtuber teenager teen roommate babysitter principal
doctor nurse bartender manager customer classmate friend colleague employer
girl boy man woman guy lady kid baby toddler teenager adult senior
killer crush victim suspect witness
""".split())

WHO_WORDS = WHO_RELATIONSHIP | WHO_IDENTITY

ACTION_WORDS = set("""
kicked kickedout faked fakes faking cheated cheats cheating fired scammed
scam scams stole steals stealing lied lies lying abandoned
abandons replaced replaces disowned disowns kidnapped kidnaps betrayed
betrays humiliated humiliates embarrassed ruined ruins destroyed
destroys sabotaged sabotages framed blackmailed dumped ghosted evicted
banned rejected insulted mocked bullied robbed threatened manipulated
gaslit canceled forged trespassed assaulted abused neglects neglected
disrespected slapped hit poisoned drugged catfished stalked spied
murder murdered murders build builds built turned turns bought buy
trapped fight fought fights survived survive survives escaped escape
escapes pranked prank pranks
""".split())

ENDING_WORDS = set("""
karma regret regrets regretted walkedaway apologized backfired
learns learned forgiven forgave reunited revenge revenged justice
jailed redemption apologizes sorry lastlaugh shock shocking surprise
instantly ending caught arrested exposed wins won win end ends ended
""".split())

STAKES_WORDS = set("""
inheritance wedding custody house will money business company
reputation marriage family job college scholarship savings home
trustfund estate property career relationship engagement fund
weddingring ring life case cases love
""".split())

# descriptor/adjective words that intensify or characterize the who/situation
# without being a narrative-grammar slot themselves (e.g. "secret", "racist").
AMPLIFIER_WORDS = set("""
secret evil disturbing racist jealous rich poor homeless famous pregnant
extreme crazy insane wild ridiculous outrageous dangerous brutal savage
ruthless cruel toxic obsessed desperate spoiled entitled arrogant selfish
greedy corrupt fake popular unbelievable shameless heartless cold
worst best horrifying dark expensive biggest big bad wrong secretly
""".split())

def assign_slot(keyword):
    tokens = re.split(r"[\s-]+", keyword)
    if any(token_in(t, WHO_WORDS) for t in tokens):
        who_type = "relationship" if any(token_in(t, WHO_RELATIONSHIP) for t in tokens) else "identity"
        return 0, who_type
    if any(token_in(t, ACTION_WORDS) for t in tokens):
        return 1, None
    if any(token_in(t, ENDING_WORDS) for t in tokens):
        return 2, None
    if any(token_in(t, STAKES_WORDS) for t in tokens):
        return 3, None
    if any(token_in(t, AMPLIFIER_WORDS) for t in tokens):
        return 4, None
    return -1, None

def grade_for(outlier, data_backed):
    # tied directly to the two things that actually matter here: is it proven
    # across multiple channels (data_backed), and how strong is the outlier.
    # never a vague composite - always traceable back to those two numbers.
    if data_backed and outlier >= 4: return "A"
    if data_backed and outlier >= 2.5: return "B"
    if data_backed: return "C"
    if outlier >= 3: return "D"
    return "F"

HISTORY_FILE = HERE / "keyword_history.json"
HISTORY_KEEP = 10
TREND_THRESHOLD = 0.15

def load_history():
    if HISTORY_FILE.exists():
        try: return json.loads(HISTORY_FILE.read_text())
        except Exception: return []
    return []

def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history[-HISTORY_KEEP:]))

def trend_for(keyword, score, prev_snapshot):
    # only trust a trend when the channel roster is unchanged since the last run -
    # otherwise a score swing is just "we added channels," not a real trend, and
    # calling that "rising" or "cooling" would be actively misleading.
    if prev_snapshot is None: return "new"
    prev_scores = prev_snapshot.get("scores", {})
    if keyword not in prev_scores: return "new"
    prev_score = prev_scores[keyword]
    if prev_score <= 0: return "new"
    change = (score - prev_score) / prev_score
    if change >= TREND_THRESHOLD: return "rising"
    if change <= -TREND_THRESHOLD: return "cooling"
    return "steady"

ALIASES_FILE = HERE / "keyword_aliases.json"

def load_aliases():
    if ALIASES_FILE.exists():
        return json.loads(ALIASES_FILE.read_text())
    return {}

def save_aliases(aliases):
    ALIASES_FILE.write_text(json.dumps(aliases, indent=1, sort_keys=True))

def merge_keyword(frm, to):
    aliases = load_aliases()
    frm, to = frm.strip().lower(), to.strip().lower()
    while to in aliases and aliases[to] != to:
        to = aliases[to]
    if frm == to:
        print(f"'{frm}' already equals '{to}', nothing to do."); return
    aliases[frm] = to
    for k, v in list(aliases.items()):
        if v == frm: aliases[k] = to
    save_aliases(aliases)
    print(f"Merged '{frm}' -> '{to}' (saved to {ALIASES_FILE.name}).")
    print("Re-run 'python3 collector.py' with no arguments to regenerate the library with this applied.")

def significant_sequence(title):
    raw = re.findall(r"[a-z0-9']+", title.lower())
    sig, pos = [], []
    for i, w in enumerate(raw):
        if w in STOPWORDS or w in BRAND_WORDS or len(w) < 3 or w.isdigit():
            continue
        sig.append(w); pos.append(i)
    return raw, sig, pos

def _premise_for(raw, pos, sig, start, n, topic):
    last_raw = pos[start + n - 1]
    extra = [w for w in raw[last_raw + 1:last_raw + 4] if w not in BRAND_WORDS]
    while extra and extra[-1] in STOPWORDS:
        extra.pop()
    return topic if not extra else topic + " " + " ".join(extra)

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
        # a merged phrase is always an ADDITION, never a replacement - every
        # individual word still gets registered so it can't get swallowed by a
        # compound that later turns out too rare to make the keyword cutoff.
        for j in range(i, i + n):
            word = sig[j]
            results.append((word, _premise_for(raw, pos, sig, j, 1, word)))
        if n > 1:
            phrase = " ".join(sig[i:i + n])
            results.append((phrase, _premise_for(raw, pos, sig, i, n, phrase)))
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

SUPABASE_URL = "https://gjksyrsfmszhewtwtdej.supabase.co"
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

def push_snapshot_to_supabase(payload):
    if not SUPABASE_SERVICE_KEY:
        print("  (skipping Supabase snapshot push - no SUPABASE_SERVICE_KEY set in env)")
        return
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
               "Content-Type": "application/json"}
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/library_snapshots",
            data=json.dumps({"payload": payload}).encode(),
            headers={**headers, "Prefer": "return=minimal"},
            method="POST")
        urllib.request.urlopen(req, timeout=180).read()
        print("  pushed live snapshot to Supabase")
        prune_old_snapshots(headers)
    except Exception as e:
        # non-fatal: library.html was already written locally with this data, so a failed
        # live-sync here shouldn't abort the run - the page just keeps serving that baked-in copy
        print(f"  warning: could not push snapshot to Supabase ({e})")

def prune_old_snapshots(headers, keep=5):
    # keeps a short rollback history in Supabase - if a future scrape ever pushes a corrupt
    # snapshot, the page's own sanity check falls back to the newest surviving good one
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/library_snapshots?select=id&order=id.desc&offset={keep}",
            headers=headers, method="GET")
        old_ids = [r["id"] for r in json.loads(urllib.request.urlopen(req, timeout=30).read())]
        if not old_ids: return
        id_list = ",".join(str(i) for i in old_ids)
        del_req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/library_snapshots?id=in.({id_list})", headers=headers, method="DELETE")
        urllib.request.urlopen(del_req, timeout=30).read()
        print(f"  pruned {len(old_ids)} old snapshot(s), keeping last {keep}")
    except Exception as e:
        print(f"  warning: could not prune old snapshots ({e})")

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

def video_age_days(v):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(v["published"].replace("Z", "+00:00"))).days

def score_outliers(videos, subs):
    now = datetime.now(timezone.utc)
    keep = [v for v in videos if v["seconds"] >= MIN_LENGTH_SECONDS and v["views"] > 0 and
            (now - datetime.fromisoformat(v["published"].replace("Z", "+00:00"))).days >= MIN_AGE_DAYS]
    # a channel needs 5+ long-form videos before its average is a reliable baseline for
    # the outlier/keyword pipeline - but that's no reason to drop the channel from
    # "Search anything" entirely, so all_scored is built regardless of that threshold.
    reliable = len(keep) >= 5
    avg = statistics.mean(v["views"] for v in keep) if reliable else None
    all_scored = []
    for v in videos:
        if v["views"] <= 0: continue
        v["channel_avg"] = int(avg) if avg else 0
        v["outlier"] = round(v["views"] / avg, 2) if avg else 0
        v["runner"] = round(v["views"] / subs, 2) if subs else 0
        all_scored.append(v)
    return (keep if reliable else []), all_scored

def pair_counts_from_sequences(video_keyword_pairs):
    counts, examples = {}, {}
    for v, seq in video_keyword_pairs:
        for i in range(len(seq) - 1):
            pair = tuple(sorted((seq[i], seq[i + 1])))
            if pair[0] == pair[1]: continue
            counts[pair] = counts.get(pair, 0) + 1
            if pair not in examples or v["outlier"] > examples[pair]["outlier"]:
                examples[pair] = v
    return counts, examples

def channel_weighted_median(vids, field="outlier"):
    by_chan = {}
    for v in vids: by_chan.setdefault(v["channel"], []).append(v[field])
    chan_avgs = [statistics.mean(vals) for vals in by_chan.values()]
    return round(statistics.median(chan_avgs), 2)

def build_library(outliers, channel_stats, all_long_form):
    aliases = load_aliases()
    history = load_history()
    prev_snapshot = history[-1] if history else None
    comparable = prev_snapshot is not None and prev_snapshot.get("channel_count") == len(channel_stats)
    phrase_counts = phrase_frequency([v["title"] for v in outliers])
    rows, video_keyword_pairs = [], []
    for v in outliers:
        seen, seq = set(), []
        for kw, premise in extract_topics_and_premises(v["title"], phrase_counts):
            kw = aliases.get(kw, kw)
            if kw in seen: continue
            seen.add(kw); seq.append(kw)
            rows.append({**v, "keyword": kw, "premise": premise})
        if seq: video_keyword_pairs.append((v, seq))
    groups = {}
    for r in rows: groups.setdefault(r["keyword"], []).append(r)
    pair_counts, pair_examples = pair_counts_from_sequences(video_keyword_pairs)
    keywords = []
    for kw, vids in groups.items():
        chans = {v["channel"] for v in vids}
        prem = {}
        for v in vids: prem.setdefault(v["premise"], []).append(v)
        # "one channel, one vote": a channel's own average counts once, regardless of
        # how many qualifying videos it contributed, so a prolific channel can't
        # dominate a keyword's stats.
        plist = sorted([{"premise": p, "count": len(pv), "median_outlier": channel_weighted_median(pv),
                         "videos": sorted(pv, key=lambda x: -x["outlier"])} for p, pv in prem.items()],
                       key=lambda p: (-p["count"], -p["median_outlier"]))
        med = channel_weighted_median(vids)
        med_runner = channel_weighted_median(vids, "runner")
        slot, who_type = assign_slot(kw)
        data_backed = len(vids) >= DB_MIN_VIDEOS and len(chans) >= DB_MIN_CHANNELS
        score = round(len(vids) * med * (1 + 0.25 * (len(chans) - 1)), 2)
        keywords.append({"keyword": kw, "count": len(vids), "channels": len(chans), "median_outlier": med,
            "median_runner": med_runner, "data_backed": data_backed, "grade": grade_for(med, data_backed),
            "trend": trend_for(kw, score, prev_snapshot) if comparable else "new",
            "slot": slot, "slot_name": SLOTS[slot] if slot >= 0 else "unclassified", "who_type": who_type,
            "score": score, "premises": plist})
    keywords.sort(key=lambda k: -k["score"])
    keywords = keywords[:MAX_KEYWORDS]
    history.append({"channel_count": len(channel_stats), "generated": datetime.now().isoformat(),
                     "scores": {k["keyword"]: k["score"] for k in keywords}})
    save_history(history)
    kw_set = {k["keyword"] for k in keywords}
    counts_by_kw = {k["keyword"]: k["count"] for k in keywords}
    n_corpus = len(outliers)
    edges = []
    for (a, b), w in pair_counts.items():
        if w < EDGE_MIN or a not in kw_set or b not in kw_set: continue
        na, nb = counts_by_kw[a], counts_by_kw[b]
        lift = round((w * n_corpus) / (na * nb), 2)
        if lift < LIFT_MIN: continue
        ex = pair_examples.get((a, b))
        example = None
        if ex:
            example = {"title": ex["title"], "url": ex["url"], "thumb": ex["thumb"],
                       "channel": ex["channel"], "outlier": ex["outlier"], "runner": ex["runner"]}
        edges.append({"a": a, "b": b, "w": w, "lift": lift, "example": example})
    with open(HERE / "library.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["grade", "trend", "slot", "who_type", "keyword", "premise", "title", "channel",
                    "views", "outlier", "runner", "url", "thumbnail"])
        for k in keywords:
            for p in k["premises"]:
                for v in p["videos"]:
                    w.writerow([k["grade"], k["trend"], k["slot_name"], k["who_type"] or "", k["keyword"], p["premise"],
                                v["title"], v["channel"], v["views"], v["outlier"], v["runner"], v["url"], v["thumb"]])
    # "Search anything" searches every long-form video pulled, not just outliers, so a
    # miss is a real "not in the data" rather than an artifact of the outlier filter.
    all_videos = [{"title": v["title"], "url": v["url"], "thumb": v["thumb"], "channel": v["channel"],
                   "outlier": v["outlier"], "runner": v["runner"], "views": v["views"]}
                  for v in sorted(all_long_form, key=lambda x: -x["outlier"])]
    payload = {"generated": datetime.now().strftime("%b %d, %Y at %I:%M %p"),
               "channels": sorted({v["channel"] for v in outliers}),
               "channel_stats": sorted(channel_stats, key=lambda c: -c["subs"]),
               "outlier_min": OUTLIER_MIN,
               "total": len(outliers), "rule": f"{DB_MIN_VIDEOS}+ outlier videos across {DB_MIN_CHANNELS}+ channels",
               "slots": SLOTS,
               "keywords": keywords, "edges": edges, "all_videos": all_videos}
    html = (HERE / "library_template.html").read_text().replace("/*__DATA__*/null", json.dumps(payload).replace("</", "<\\/"))
    (HERE / "library.html").write_text(html)
    push_snapshot_to_supabase(payload)

    counts = {}
    for k in keywords: counts[k["slot_name"]] = counts.get(k["slot_name"], 0) + 1
    print("  slot breakdown: " + ", ".join(f"{name} {counts.get(name, 0)}" for name in SLOTS + ["unclassified"]))

def main():
    if not YT_KEY: die("Missing YouTube key")
    print("1. Pulling channels")
    outs, all_long_form, channel_stats = [], [], []
    for entry in CHANNELS:
        ch = get_channel(entry)
        if not ch: continue
        BRAND_WORDS.update(re.findall(r"[a-z0-9']+", ch["name"].lower()))
        vids = fetch_channel_videos(ch)
        scored, all_scored = score_outliers(vids, ch["subs"])
        # an old video with weak absolute views is stale evidence even if it beat its channel's
        # average at the time - require a real view floor once a video is 4+ years old
        o = [v for v in scored if v["outlier"] >= OUTLIER_MIN and
             not (video_age_days(v) > MAX_AGE_DAYS_FOR_LOW_VIEWS and v["views"] < MIN_VIEWS_IF_OLD)]
        avg_views = scored[0]["channel_avg"] if scored else 0
        print(f"  {ch['name']} ({ch['subs']:,} subs): {len(vids)} uploads, {len(scored)} long form, "
              f"avg {avg_views:,} views, {len(o)} outliers at {OUTLIER_MIN}x+ this channel's own long-form average")
        channel_stats.append({"name": ch["name"], "subs": ch["subs"], "url": ch["url"], "uploads_scanned": len(vids),
                               "long_form": len(scored), "outliers": len(o), "avg_views": avg_views})
        outs += o
        all_long_form += all_scored  # every video with views (Shorts + recent too) - feeds "Search anything" only
    if not outs: die("No outliers found. Add more channels or lower OUTLIER_MIN.")
    outs = sorted(outs, key=lambda v: -v["outlier"])[:MAX_VIDEOS]
    print("\n2. Extracting data backed keywords from titles")
    build_library(outs, channel_stats, all_long_form)
    print(f"  done. Opening {HERE / 'library.html'}")

if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "merge":
        merge_keyword(sys.argv[2], sys.argv[3])
    elif len(sys.argv) > 1:
        die("Usage: python3 collector.py            (normal run)\n"
            "       python3 collector.py merge \"from\" \"to\"   (fold one keyword into another)")
    else:
        main()
