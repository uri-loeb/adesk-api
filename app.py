import os, re, time, base64, io, uuid, zipfile
from flask import Flask, request, jsonify, redirect, send_file, make_response
from flask_cors import CORS
import stripe

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

stripe.api_key = STRIPE_SECRET_KEY

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [FRONTEND_URL]}}, supports_credentials=True)

WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")
FORBIDDEN = re.compile(r"(logo|logos|trademark|™|®|©|brand name|nike|adidas|coca|pepsi|apple|google|microsoft|starbucks|netflix|disney|marvel|bmw|mercedes|audi|tesla)", re.I)

JOBS = {}

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
    if len(words) < 50:
        words += ["impact"] * (50 - len(words))
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
        fs = max(24, min(width, height)//16)
        svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}'>"
               "<rect width='100%' height='100%' fill='#e3edff'/>"
               "<text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' "
               "font-family='Arial' font-size='{fs}' fill='#141c26'>{text}</text>"
               "</svg>").format(w=width, h=height, fs=fs, text=text)
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
            success_url=f"{FRONTEND_URL}/?sid={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/?canceled=1",
        )
        return jsonify({"url": checkout_session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.get("/api/claim")
def api_claim():
    sid = request.args.get("sid", "")
    if not sid:
        return jsonify({"ok": False, "error": "missing_sid"}), 400
    try:
        sess = stripe.checkout.Session.retrieve(sid, expand=["payment_intent"])
        if sess.get("payment_status") != "paid":
            return jsonify({"ok": False, "error": "payment_not_completed"}), 402
    except Exception as e:
        return jsonify({"ok": False, "error": "invalid_sid"}), 400

    resp = make_response(jsonify({"ok": True}))
    max_age = 24*3600
    resp.set_cookie("paid", "1", max_age=max_age, path="/", secure=True, httponly=True, samesite="None")
    resp.set_cookie("attempts", "0", max_age=max_age, path="/", secure=True, httponly=True, samesite="None")
    return resp

@app.get("/api/attempts")
def api_attempts():
    paid = request.cookies.get("paid")
    if not paid:
        return jsonify({"error": "not_paid"}), 401
    try:
        attempts = int(request.cookies.get("attempts", "0"))
    except ValueError:
        attempts = 0
    left = max(0, 3 - attempts)
    return jsonify({"attempts_left": left})

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
    paid = request.cookies.get("paid")
    if not paid:
        return jsonify({"ok": False, "error": "not_paid"}), 401
    try:
        attempts = int(request.cookies.get("attempts", "0"))
    except ValueError:
        attempts = 0
    if attempts >= 3:
        return jsonify({"ok": False, "error": "attempts_exhausted"}), 429

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

    resp = make_response(jsonify({"ok": True, "job_id": job_id, "dimensions": f"{w}x{h}", "variations": variations}))
    attempts += 1
    max_age = 24*3600
    resp.set_cookie("attempts", str(attempts), max_age=max_age, path="/", secure=True, httponly=True, samesite="None")
    return resp

@app.get("/api/download")
def api_download():
    paid = request.cookies.get("paid")
    if not paid:
        return jsonify({"ok": False, "error": "not_paid"}), 401
    job = request.args.get("job", "")
    data = JOBS.get(job)
    if not data: return jsonify({"ok": False, "error": "job_not_found"}), 404

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as z:
        for i, b in enumerate(data["images"], start=1):
            z.writestr(f"ad_{i}.jpg", b)
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
                for line in tw.wrap(txt, width=90): c.drawString(72, y, line); y -= 14
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
