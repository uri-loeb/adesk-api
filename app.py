import os, re, time, base64
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import stripe
from itsdangerous import URLSafeSerializer, BadSignature

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000").rstrip("/")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
SIGNING_SECRET = os.getenv("TOKEN_SIGNING_SECRET", "change-me")

stripe.api_key = STRIPE_SECRET_KEY
serializer = URLSafeSerializer(SIGNING_SECRET, salt="adv-agency")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [FRONTEND_URL]}})

WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")
FORBIDDEN = re.compile(r"(logo|logos|trademark|™|®|©|brand name|nike|adidas|coca|pepsi|apple|google|microsoft|starbucks|netflix|disney|marvel|bmw|mercedes|audi|tesla)", re.I)

def make_token(user_ref: str, ttl_seconds: int = 24*3600) -> str:
    payload = {"u": user_ref, "exp": int(time.time()) + ttl_seconds}
    return serializer.dumps(payload)

def verify_signed_token(token: str) -> bool:
    try:
        data = serializer.loads(token)
        return data.get("exp", 0) >= int(time.time())
    except BadSignature:
        return False

def parse_dimensions(dim_str: str):
    try:
        w, h = dim_str.lower().split("x")
        return int(w), int(h)
    except Exception:
        return 1080, 1080

def make_svg_data_url(width: int, height: int, text: str) -> str:
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>
      <defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0%' stop-color='#eaf1ff'/><stop offset='100%' stop-color='#cfe4ff'/></linearGradient></defs>
      <rect width='100%' height='100%' fill='url(#g)' rx='24' ry='24'/>
      <text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' font-family='Inter, Arial, sans-serif' font-size='{max(24, min(width, height)//16)}' fill='#0f172a'>{text}</text></svg>"""
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

def enforce_input_rules(product: str):
    if not product or any(ord(c) > 127 for c in product):
        return False, "English only (ASCII)."
    words = WORD_RE.findall(product)
    if len(words) == 0:
        return False, "Please enter a short English description."
    if len(words) > 15:
        return False, "Max 15 words."
    if FORBIDDEN.search(product):
        return False, "Avoid brand names, logos or trademarks."
    return True, ""

@app.get("/health")
def health(): return jsonify({"status": "ok"})

@app.post("/create-checkout-session")
def create_checkout():
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price_data": {"currency": "usd", "product_data": {"name": "Advertising Agency Access"}, "unit_amount": 500}, "quantity": 1}],
            mode="payment",
            success_url=f"{BACKEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/?canceled=1",
        )
        return jsonify({"url": checkout_session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.get("/payment/success")
def payment_success():
    session_id = request.args.get("session_id")
    if not session_id: return jsonify({"ok": False, "error": "missing session_id"}), 400
    sess = stripe.checkout.Session.retrieve(session_id, expand=["customer_details", "payment_intent"])
    if sess.get("payment_status") != "paid": return jsonify({"ok": False, "error": "payment not completed"}), 402
    buyer = (sess.get("customer_details") or {}).get("email") or "guest"
    token = make_token(buyer)
    return redirect(f"{FRONTEND_URL}/?token={token}", code=302)

@app.get("/verify-token")
def verify_token():
    token = request.args.get("token")
    if not token or not verify_signed_token(token): return jsonify({"valid": False}), 401
    return jsonify({"valid": True})

@app.post("/api/generate")
def api_generate():
    token = request.args.get("token") or request.headers.get("X-ADesk-Token", "")
    if not token or not verify_signed_token(token): return jsonify({"ok": False, "error": "invalid_or_expired_token"}), 401
    data = request.get_json(silent=True) or {}
    product = (data.get("product") or "").strip()
    ok, msg = enforce_input_rules(product)
    if not ok: return jsonify({"ok": False, "error": msg}), 400
    dim = (data.get("dimensions") or "1080x1080").strip()
    w, h = parse_dimensions(dim)
    variations = []
    for i in range(1, 4):
        headline = f"Clean & crisp • {product}"
        img_url = make_svg_data_url(w, h, f"Ad {i}: {product}")
        copy50 = " ".join(("Impactful clean ad copy focusing on value clarity benefits and call to action without any brand or trademark references placeholder text for preview only").split()[:50])
        variations.append({"idx": i, "headline": headline, "image_url": img_url, "marketing_copy_50": copy50})
    return jsonify({"ok": True, "dimensions": f"{w}x{h}", "variations": variations})

@app.post("/webhook")
def webhook():
    wh_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not wh_secret: return "webhook not configured", 200
    sig = request.headers.get("Stripe-Signature", "")
    try: stripe.Webhook.construct_event(request.data, sig, wh_secret)
    except Exception: return "invalid", 400
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
