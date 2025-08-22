import os, re, time, base64, io, uuid, zipfile
from flask import Flask, request, jsonify, redirect, send_file
from flask_cors import CORS
import stripe
from itsdangerous import URLSafeSerializer, BadSignature

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = ImageDraw = ImageFont = None
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
except Exception:
    canvas = None
    A4 = None

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

JOBS = {}

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

def make_copy_50_words(product: str, variant: int) -> str:
    base = (f"{product} – clean, simple, built for results. "
            f"Three crisp variations with clear headline and CTA. "
            f"No brands or trademarks. Variation {variant} highlights value, benefits, and action.")
    words = base.split()
    if len(words) < 50: words += ["impact"] * (50 - len(words))
    return " ".join(words[:50])

def render_image_bytes(width, height, text):
    if Image is not None:
        img = Image.new("RGB", (width, height), (227, 237, 255))
        draw = ImageDraw.Draw(img)
        for y in range(height):
            c = 227 + int((255-227) * (y/height))
            draw.line([(0,y),(width,y)], fill=(c, c, 255))
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", max(18, min(width, height)//16))
        except Exception:
            font = ImageFont.load_default()
        tw, th = draw.textsize(text, font=font)
        draw.text(((width-tw)//2, (height-th)//2), text, fill=(20,28,38), font=font)
        bio = io.BytesIO(); img.save(bio, format="JPEG", quality=90)
        return bio.getvalue()
    else:
        svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>
        <rect width='100%' height='100%' fill='#e3edff'/>
        <text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle'
              font-family='Arial' font-size='{max(24, min(width,height)//16)}' fill='#141c26'>{text}</text>
        </svg>"""
        return svg.encode()

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

def enforce_input_rules(product: str):
    if not product or any(ord(c) > 127 for c in product):
        return False, "English only (ASCII)."
    words = WORD_RE.findall(product)
    if len(words) == 0: return False, "Please enter a short English description."
    if len(words) > 15: return False, "Max 15 words."
    if FORBIDDEN.search(product): return False, "Avoid brand names, logos or trademarks."
    return True, ""

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

    job_id = str(uuid.uuid4())[:8]
    images = []; variations = []
    for i in range(1, 4):
        title = f"Ad {i}: {product}"
        img_bytes = render_image_bytes(w, h, title)
        images.append(img_bytes)
        variations.append({
            "idx": i,
            "headline": f"Clean & crisp • {product}",
            "image_url": "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode(),
            "marketing_copy_50": make_copy_50_words(product, i)
        })
    JOBS[job_id] = {"product": product, "dimensions": f"{w}x{h}", "images": images, "copies": [v["marketing_copy_50"] for v in variations]}
    return jsonify({"ok": True, "job_id": job_id, "dimensions": f"{w}x{h}", "variations": variations})

@app.get("/api/download")
def api_download():
    token = request.args.get("token") or request.headers.get("X-ADesk-Token", "")
    job = request.args.get("job", "")
    if not token or not verify_signed_token(token): return jsonify({"ok": False, "error": "invalid_or_expired_token"}), 401
    data = JOBS.get(job)
    if not data: return jsonify({"ok": False, "error": "job_not_found"}), 404

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for i, b in enumerate(data["images"], start=1):
            z.writestr(f"ad_{i}.jpg", b)
        # PDF fallback to .txt if reportlab missing
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            pdf_buf = io.BytesIO()
            c = canvas.Canvas(pdf_buf, pagesize=A4)
            width, height = A4; y = height - 72
            c.setFont("Helvetica-Bold", 14)
            c.drawString(72, y, f"Advertising Agency – {data['product']}  ({data['dimensions']})")
            y -= 24; c.setFont("Helvetica", 11)
            import textwrap as tw
            for i, txt in enumerate(data["copies"], start=1):
                c.drawString(72, y, f"Ad {i} copy (50 words):"); y -= 18
                for line in tw.wrap(txt, width=90):
                    c.drawString(72, y, line); y -= 14
                y -= 10
                if y < 100: c.showPage(); y = height - 72; c.setFont("Helvetica", 11)
            c.save()
            z.writestr("copy.pdf", pdf_buf.getvalue())
        except Exception:
            txt = [f"Product: {data['product']} ({data['dimensions']})", ""]
            for i, t in enumerate(data["copies"], start=1):
                txt.append(f"Ad {i} – copy (50 words):"); txt.append(t); txt.append("")
            z.writestr("copy.txt", "\n".join(txt).encode())

    mem.seek(0)
    return send_file(mem, mimetype="application/zip", as_attachment=True, download_name=f"ads_{job}.zip")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
