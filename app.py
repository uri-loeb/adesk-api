
import os, io, time, uuid, zipfile, requests, re
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
import stripe

try:
    import openai
    OPENAI_OK = True
except Exception:
    OPENAI_OK = False

app = Flask(__name__)
CORS(app)

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_replace_me")
stripe.api_key = STRIPE_SECRET_KEY
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://your-netlify-site.netlify.app")
PUBLIC_DOMAIN = os.getenv("PUBLIC_DOMAIN", "http://localhost:5000")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
if OPENAI_OK and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

TOKENS = {}
RESULTS = {}

BANNED_TERMS = {
    "logo","trademark","®","©","™",
    "coca-cola","coke","pepsi","starbucks","nike","adidas","apple","facebook","instagram","google","mcdonald",
    "heineken","kellogg","netflix","disney","pixar","marvel","dc","barbie","lego"
}

def violates_policy(s: str) -> bool:
    s = (s or "").lower()
    return any(t in s for t in BANNED_TERMS)

_word_re = re.compile(r"\s+")
def clean_input(text: str) -> str:
    # Keep only English letters, digits, space, dot, hyphen
    allowed = re.sub(r"[^A-Za-z0-9\-\.\s]", "", text or "")
    # Normalize spaces
    allowed = _word_re.sub(" ", allowed).strip()
    if not allowed:
        return ""
    # Cap to 15 words
    words = [w for w in allowed.split(" ") if w]
    if len(words) > 15:
        words = words[:15]
    return " ".join(words)

@app.route("/")
def landing():
    html = f"""<!DOCTYPE html>
<html lang='en'><head><meta charset='UTF-8'/><meta name='viewport' content='width=device-width,initial-scale=1.0'/>
<title>ADesk – Create Ads with AI</title>
<style>
:root{{--bg1:#e6f2ff;--bg2:#f7fbff;--ink:#123;--muted:#567;--p:#0066cc;--pd:#004c99}}
*{{box-sizing:border-box}} body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;color:var(--ink);
background:radial-gradient(1200px 600px at 20% 10%,var(--bg1),var(--bg2))}}
.hero{{max-width:1100px;margin:0 auto;padding:56px 20px 24px;display:grid;gap:18px}}
h1{{margin:0;font-size:2rem;}} .sub{{margin:0;color:var(--muted)}}
.cta{{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px}}
.cta a,.cta button{{background:var(--p);color:#fff;border:0;border-radius:12px;padding:12px 16px;font-weight:700;cursor:pointer;text-decoration:none}}
.cta a:hover,.cta button:hover{{background:var(--pd)}}
.demo{{max-width:1100px;margin:10px auto 24px;padding:0 20px;display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.card{{background:#fff;border-radius:16px;box-shadow:0 12px 34px rgba(0,0,0,.08);overflow:hidden}}
.img{{height:200px;background:linear-gradient(135deg,#cfe8ff,#eaf5ff)}} .body{{padding:12px 14px}}
.body h3{{margin:0 0 6px;font-size:1.05rem}} .body p{{margin:0;color:var(--muted)}}
.features{{max-width:1100px;margin:0 auto 24px;padding:0 20px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px}}
.feat{{background:#fff;border-radius:14px;padding:14px;border:1px solid #e6f1ff}}
#checkout{{max-width:900px;margin:12px auto 40px;background:#fff;border-radius:18px;box-shadow:0 16px 48px rgba(0,0,0,.08);padding:22px 24px}}
#note{{color:#456;font-size:.9rem;margin-top:8px}}
@media (max-width:900px){{.demo,.features{{grid-template-columns:1fr 1fr}}}}
@media (max-width:640px){{.demo,.features{{grid-template-columns:1fr}}}}
</style></head><body>
<section class='hero'>
  <h1>Turn a product name into 3 ad variations</h1>
  <p class='sub'>Images + copy in seconds. No logos, trademarks or copyrighted packaging. Download ZIP (JPG + PDF text).</p>
  <div class='cta'><a href='#checkout'>Start now</a></div>
</section>
<section class='demo'>
  <div class='card'><div class='img'></div><div class='body'><h3>Clean & crisp</h3><p>Minimal, brand‑agnostic visuals that focus on value.</p></div></div>
  <div class='card'><div class='img'></div><div class='body'><h3>Chill the noise</h3><p>Clear headline, zero clutter, strong CTA.</p></div></div>
  <div class='card'><div class='img'></div><div class='body'><h3>Bold by design</h3><p>Modern composition that converts across channels.</p></div></div>
</section>
<section class='features'>
  <div class='feat'>🔐 24‑hour secure access via token</div>
  <div class='feat'>🧠 GPT copy + DALL·E images</div>
  <div class='feat'>⬇️ ZIP download (JPG + PDF text)</div>
</section>
<section id='checkout'>
  <h2>Get 24‑hour access</h2>
  <p>Test mode: use Stripe demo card <b>4242 4242 4242 4242</b>, any future date, any CVC.</p>
  <button id='payBtn'>Pay $1.00 (Test)</button>
  <div id='note'></div>
</section>
<script>
document.getElementById('payBtn').addEventListener('click', async () => {
  const res = await fetch('/create-checkout-session', { method: 'POST' });
  const data = await res.json();
  if(data.url) window.location.href = data.url;
  else document.getElementById('note').textContent = data.error || 'Failed to start checkout.';
});
</script></body></html>"""
    return html

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "ADesk 24-hour access"},
                    "unit_amount": 100,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{PUBLIC_DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{PUBLIC_DOMAIN}/#checkout",
        )
        return jsonify({"url": checkout_session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/success")
def success():
    session_id = request.args.get("session_id")
    if not session_id:
        return "Missing session_id", 400
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.get("payment_status") != "paid":
            return "Payment not completed", 402
    except Exception as e:
        return f"Stripe error: {e}", 400

    token = str(uuid.uuid4())
    TOKENS[token] = time.time() + 24*3600
    # Redirect with backend param so frontend knows our base URL
    frontend = FRONTEND_URL
    backend = PUBLIC_DOMAIN
    return (f"<script>location.href='{frontend}?token={token}&backend='+encodeURIComponent('{backend}')</script>", 200)

@app.route("/api/generate", methods=["POST"])
def generate_ads():
    token = request.args.get("token", "") or (request.json or {}).get("token", "")
    if token not in TOKENS or TOKENS[token] < time.time():
        return jsonify({"error": "Invalid or expired token"}), 403

    data = request.get_json(force=True)
    raw_product = (data.get("product") or "").strip()
    dimensions = (data.get("dimensions") or "").strip()

    # Sanitize to English-only and cap to 15 words
    product = clean_input(raw_product)
    if not product:
        return jsonify({"error": "Input must be English-only (letters/numbers/space/dot/hyphen) and up to 15 words."}), 400

    if violates_policy(product):
        return jsonify({"error": "Logos/trademarks/brand packaging/copyrighted posters are not allowed."}), 400

    size_map = {"1080x1080":"1024x1024","1080x1350":"1024x1024","1080x1920":"1024x1024","1200x628":"1024x1024"}
    dalle_size = size_map.get(dimensions, "1024x1024")

    results = []
    fallback = False

    SYSTEM_INSTRUCT = (
        "You are an ad copywriter. Create concise, original marketing copy. "
        "Do NOT mention or use any logos, trademarks, existing brand names, existing packaging or copyrighted posters. "
        "Output must be safe for commercial use and generic."
    )

    for _ in range(3):
        headline = f"{product}: Fresh & Original Ad"
        marketing = f"A safe, generic ~50-word marketing description for {product}. No logos/trademarks/packaging/posters. Clear benefits, value proposition, strong CTA."
        image_url = None

        if OPENAI_OK and OPENAI_API_KEY:
            try:
                completion = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": SYSTEM_INSTRUCT},
                        {"role": "user", "content": f"Product: {product}. Create a catchy headline and a 50-word ad text in English. No trademarks or logos."}
                    ],
                    temperature=0.9,
                )
                text_out = completion["choices"][0]["message"]["content"]
                lines = [ln.strip() for ln in text_out.splitlines() if ln.strip()]
                if lines:
                    headline = lines[0][:120]
                    body = " ".join(lines[1:]).strip()
                    if len(body.split()) < 30:
                        body = text_out
                    marketing = body[:700]
            except Exception:
                fallback = True

            try:
                prompt = (
                    f"Minimalist advertising photo for a generic product named '{product}'. "
                    "No logos, no brand packaging, no copyrighted posters, no text overlays. "
                    "Contemporary studio look, soft lighting, abstract shapes."
                )
                img = openai.Image.create(prompt=prompt, n=1, size=dalle_size)
                image_url = img["data"][0]["url"]
            except Exception:
                fallback = True

        results.append({"headline": headline, "text": marketing, "image_url": image_url, "size": dalle_size})

    RESULTS[token] = results
    return jsonify({"ok": True, "results": results, "fallback": fallback})

def _ensure_result(token, idx):
    if token not in RESULTS:
        abort(404)
    try:
        idx = int(idx)
    except:
        abort(400)
    if idx < 0 or idx >= len(RESULTS[token]):
        abort(404)
    return RESULTS[token][idx]

@app.route("/api/download/bundle/<token>/<idx>")
def download_bundle(token, idx):
    if token not in TOKENS or TOKENS[token] < time.time():
        return abort(403)

    item = _ensure_result(token, idx)
    image_url = item.get("image_url")
    text = item.get("text") or ""
    headline = item.get("headline") or "Ad Headline"

    buff = io.BytesIO()
    with zipfile.ZipFile(buff, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # PDF text only
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import Paragraph, SimpleDocTemplate
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm

            pdf_bytes = io.BytesIO()
            doc = SimpleDocTemplate(pdf_bytes, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
            styles = getSampleStyleSheet()
            story = []
            story.append(Paragraph(f"<b>{headline}</b>", styles["Heading2"]))
            story.append(Paragraph(text.replace("\n","<br/>"), styles["BodyText"]))
            doc.build(story)
            zf.writestr("text.pdf", pdf_bytes.getvalue())
        except Exception:
            zf.writestr("text.pdf", f"{headline}\n\n{text}".encode("utf-8"))

        if image_url:
            try:
                r = requests.get(image_url, timeout=25)
                if r.status_code == 200:
                    zf.writestr("image.jpg", r.content)
            except Exception:
                pass

    buff.seek(0)
    return send_file(buff, mimetype="application/zip", as_attachment=True, download_name="ad_variation.zip")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
