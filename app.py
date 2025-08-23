import os, io, base64, secrets, json, time, re
from flask import Flask, request, jsonify, make_response, send_file
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# -------- Config --------
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "3"))
FRONTEND_URL = os.environ.get("FRONTEND_URL", "").rstrip("/")
CHECKOUT_SUCCESS_URL = os.environ.get("CHECKOUT_SUCCESS_URL", "")
CHECKOUT_CANCEL_URL  = os.environ.get("CHECKOUT_CANCEL_URL", "")
STRIPE_SECRET_KEY    = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("stripe_secret_key") or ""
ENTITLEMENT_MODE     = os.environ.get("ENTITLEMENT_MODE", "SID_ONLY").upper()
ENTITLEMENT_TTL_HOURS= int(os.environ.get("ENTITLEMENT_TTL_HOURS", "0"))

try:
    import stripe
    if STRIPE_SECRET_KEY:
        stripe.api_key = STRIPE_SECRET_KEY
    else:
        stripe = None  # type: ignore
except Exception:
    stripe = None  # type: ignore

# In-memory stores
JOBS = {}             # job_id -> list[variation]
SID_STATE = {}        # sid -> {"paid":bool, "attempts":int, "exp":ts}

def allowed_origin():
    origin = request.headers.get("Origin", "")
    if FRONTEND_URL and origin == FRONTEND_URL: return origin
    return FRONTEND_URL or origin or "*"

def with_cors(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    ao = allowed_origin()
    resp.headers["Access-Control-Allow-Origin"] = ao if ao != "*" else "*"
    resp.headers["Vary"] = "Origin"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-SID"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return resp

def now(): return int(time.time())
def sid_get(): return request.headers.get("X-SID") or request.args.get("sid") or ""
def sid_ok(s): 
    x = SID_STATE.get(s); 
    return bool(x and x.get("paid") and (not x.get("exp") or now() <= x["exp"]))

@app.route("/health")
def health():
    return with_cors(jsonify(ok=True, ts=now(), mode=ENTITLEMENT_MODE))

@app.route("/api/debug")
def debug():
    info = {"env_frontend": FRONTEND_URL, "env_success": CHECKOUT_SUCCESS_URL, "env_cancel": CHECKOUT_CANCEL_URL,
            "has_stripe_key": bool(STRIPE_SECRET_KEY), "entitlement_mode": ENTITLEMENT_MODE,
            "entitlement_ttl_h": ENTITLEMENT_TTL_HOURS, "origin": request.headers.get("Origin"),
            "cookies": {k:v for k,v in request.cookies.items()}, "x_sid": request.headers.get("X-SID")}
    return with_cors(jsonify(info))

@app.route("/api/attempts", methods=["GET","OPTIONS"])
def attempts():
    if request.method == "OPTIONS": return with_cors(make_response("",204))
    sid = sid_get()
    if ENTITLEMENT_MODE == "SID_ONLY":
        if not sid_ok(sid): return with_cors(make_response(jsonify(error="not_paid"), 401))
        used = SID_STATE[sid]["attempts"]
        return with_cors(jsonify(attempts_used=used, attempts_left=max(0, MAX_ATTEMPTS-used)))
    if request.cookies.get("paid") != "1":
        return with_cors(make_response(jsonify(error="not_paid"), 401))
    used = int(request.cookies.get("attempts", "0") or 0)
    return with_cors(jsonify(attempts_used=used, attempts_left=max(0, MAX_ATTEMPTS-used)))

@app.route("/api/claim", methods=["GET","OPTIONS"])
def claim():
    if request.method == "OPTIONS": return with_cors(make_response("",204))
    sid = request.args.get("sid") or request.args.get("session_id")
    if not sid: return with_cors(make_response(jsonify(ok=False, error="missing_sid"), 400))
    ok = False
    if stripe and STRIPE_SECRET_KEY and sid.startswith("cs_"):
        try:
            sess = stripe.checkout.Session.retrieve(sid)  # type: ignore
            ok = (sess and sess.get("payment_status") in ("paid","no_payment_required"))
        except Exception:
            ok = False
    else:
        if sid.startswith("cs_test_") or sid == "SIMULATED": ok = True
    if not ok: return with_cors(make_response(jsonify(ok=False, error="invalid_sid"), 400))
    SID_STATE[sid] = {"paid": True, "attempts": 0, "exp": now() + ENTITLEMENT_TTL_HOURS*3600 if ENTITLEMENT_TTL_HOURS>0 else 0}
    return with_cors(jsonify(ok=True))

def parse_dim(dim):
    m = re.match(r"^(\d+)x(\d+)$", str(dim or "").strip())
    return (max(100,int(m.group(1))), max(100,int(m.group(2)))) if m else (1080,1080)

def make_image(text, w, h, variant_idx=1):
    img = Image.new("RGB", (w, h), (240,247,255)); d = ImageDraw.Draw(img)
    for i in range(0, max(w,h), 32):
        color = (224,236,255) if (i//32 + variant_idx) % 2 == 0 else (206,228,255)
        d.rectangle([(0,i),(w,i+16)], fill=color)
    try: font = ImageFont.truetype("DejaVuSans-Bold.ttf", size=max(18, min(w,h)//20))
    except Exception: font = ImageFont.load_default()
    tw, th = d.textsize(text[:60], font=font)
    d.text(((w-tw)//2, (h-th)//2), text[:60], fill=(20,40,80), font=font)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

def build_copy(product_name, description, variant_idx=1):
    base = product_name.strip()
    headline = {1:f"{base} — Try it today", 2:f"{base} — Clear results", 3:f"{base} — Simple. Effective."}.get(variant_idx, f"{base} — Take action")
    desc = (description or "").strip() or "Fast setup • No clutter • Real impact in days"
    return headline, desc

@app.route("/api/generate", methods=["POST","OPTIONS"])
def generate():
    if request.method == "OPTIONS": return with_cors(make_response("",204))
    sid = sid_get() if ENTITLEMENT_MODE == "SID_ONLY" else None
    if ENTITLEMENT_MODE == "SID_ONLY":
        if not sid_ok(sid): return with_cors(make_response(jsonify(error="not_paid"), 401))
        used = SID_STATE[sid]["attempts"]
    else:
        if request.cookies.get("paid") != "1": return with_cors(make_response(jsonify(error="not_paid"), 401))
        used = int(request.cookies.get("attempts", "0") or 0)
    if used >= MAX_ATTEMPTS: return with_cors(make_response(jsonify(error="attempts_exhausted"), 429))

    data = request.get_json(silent=True) or {}
    product_name = (data.get("product_name") or "").strip()
    description  = (data.get("description") or "").strip()
    dim = data.get("dimensions") or "1080x1080"
    job_id = (data.get("job_id") or request.cookies.get("job") or secrets.token_hex(8))

    # Validation
    if not product_name: return with_cors(make_response(jsonify(error="empty_name"), 400))
    if re.search(r"[^\x00-\x7F]", product_name) or re.search(r"[^\x00-\x7F]", description): return with_cors(make_response(jsonify(error="english_only"), 400))
    if len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", product_name)) > 15: return with_cors(make_response(jsonify(error="name_too_long"), 400))
    if len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", description)) > 40: return with_cors(make_response(jsonify(error="desc_too_long"), 400))
    if re.search(r"(logo|logos|trademark|tm|brand|nike|adidas|apple|google|microsoft|disney|bmw|tesla)", product_name + " " + description, re.I): 
        return with_cors(make_response(jsonify(error="no_brands"), 400))

    width, height = parse_dim(dim); variant_idx = used + 1
    headline, blurb = build_copy(product_name, description, variant_idx)
    img_url = make_image(headline, width, height, variant_idx)

    JOBS.setdefault(job_id, [])
    variation = {"idx":variant_idx,"headline":headline,"marketing_copy_50":blurb,"image_url":img_url,"dimensions":f"{width}x{height}"}
    if len(JOBS[job_id]) < variant_idx: JOBS[job_id].append(variation)
    else: JOBS[job_id][variant_idx-1] = variation

    new_used = used + 1
    if ENTITLEMENT_MODE == "SID_ONLY":
        SID_STATE[sid]["attempts"] = new_used
        return with_cors(jsonify(ok=True, job_id=job_id, variation=variation, attempts_used=new_used, attempts_left=max(0, MAX_ATTEMPTS-new_used)))
    # COOKIE mode increment (not used in your setup)
    resp = make_response(jsonify(ok=True, job_id=job_id, variation=variation, attempts_used=new_used, attempts_left=max(0, MAX_ATTEMPTS-new_used)))
    resp.set_cookie("attempts", str(new_used), max_age=ENTITLEMENT_TTL_HOURS*3600 if ENTITLEMENT_TTL_HOURS>0 else None, path="/", secure=True, samesite="None")
    if not request.cookies.get("job"): resp.set_cookie("job", job_id, max_age=ENTITLEMENT_TTL_HOURS*3600 if ENTITLEMENT_TTL_HOURS>0 else None, path="/", secure=True, samesite="None")
    return with_cors(resp)

@app.route("/api/download", methods=["GET","OPTIONS"])
def download():
    if request.method == "OPTIONS": return with_cors(make_response("",204))
    job_id = request.args.get("job") or request.cookies.get("job")
    if not job_id or job_id not in JOBS: return with_cors(make_response(jsonify(error="job_not_found"), 404))
    out = io.BytesIO(); import zipfile
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        txt = []
        for v in JOBS[job_id]: txt.append(f"Variation {v['idx']}: {v['headline']}\n{v['marketing_copy_50']}\n")
        z.writestr("copy.txt", "\n".join(txt))
        for v in JOBS[job_id]:
            pref = "data:image/png;base64,"
            if v["image_url"].startswith(pref):
                z.writestr(f"ad_{v['idx']}.png", base64.b64decode(v["image_url"][len(pref):]))
    out.seek(0); return with_cors(send_file(out, mimetype="application/zip", as_attachment=True, download_name=f"ads_{job_id}.zip"))

@app.route("/create-checkout-session", methods=["POST","OPTIONS"])
def create_checkout():
    if request.method == "OPTIONS": return with_cors(make_response("",204))
    success = CHECKOUT_SUCCESS_URL or (FRONTEND_URL + "/?sid={CHECKOUT_SESSION_ID}" if FRONTEND_URL else None)
    cancel  = CHECKOUT_CANCEL_URL  or (FRONTEND_URL + "/?canceled=1" if FRONTEND_URL else None)
    url = (success or "/").replace("{CHECKOUT_SESSION_ID}", "SIMULATED")
    if stripe and STRIPE_SECRET_KEY and success and cancel:
        try:
            sess = stripe.checkout.Session.create(  # type: ignore
                mode="payment",
                line_items=[{"price_data": {"currency":"usd","unit_amount":1000,"product_data":{"name":"Advertising Agency — 3 ad variations"}}, "quantity":1}],
                success_url=success, cancel_url=cancel,
            ); url = sess.url
        except Exception: pass
    return with_cors(jsonify(url=url))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","8000")))
