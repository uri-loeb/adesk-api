import os, io, zipfile
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import stripe
from PIL import Image, ImageDraw, ImageFont

FRONTEND_URL = os.getenv('FRONTEND_URL', '*')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
PRICE_USD_CENTS = int(os.getenv('PRICE_USD_CENTS', '500'))
CHECKOUT_SUCCESS_URL = os.getenv('CHECKOUT_SUCCESS_URL', f'{FRONTEND_URL}/builder.html?sid={{CHECKOUT_SESSION_ID}}')
CHECKOUT_CANCEL_URL  = os.getenv('CHECKOUT_CANCEL_URL',  f'{FRONTEND_URL}/?canceled=1')

app = Flask(__name__)
CORS(app, origins=[FRONTEND_URL] if FRONTEND_URL!='*' else '*', supports_credentials=True)

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

@app.after_request
def add_cors(resp):
    if FRONTEND_URL != '*':
        resp.headers['Access-Control-Allow-Origin'] = FRONTEND_URL
    resp.headers['Access-Control-Allow-Credentials'] = 'true'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return resp

@app.route('/health')
def health():
    return jsonify(status='ok')

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    if not STRIPE_SECRET_KEY:
        return jsonify(error='Stripe not configured'), 500
    try:
        session = stripe.checkout.Session.create(
            mode='payment',
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': 'Advertising Agency access'},
                    'unit_amount': PRICE_USD_CENTS,
                },
                'quantity': 1,
            }],
            success_url=CHECKOUT_SUCCESS_URL,
            cancel_url=CHECKOUT_CANCEL_URL,
        )
        return jsonify(url=session.url)
    except Exception as e:
        return jsonify(error=str(e)), 500

def make_card(text, w, h):
    img = Image.new('RGB', (w, h), (243, 248, 255))
    drw = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype('DejaVuSans-Bold.ttf', 42)
    except:
        f = ImageFont.load_default()
    drw.rounded_rectangle((24,24,w-24,h-24), radius=18, outline=(160,178,210), width=3)
    drw.text((40, h//2 - 20), text, fill=(26, 43, 87), font=f)
    return img

@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json(force=True) or {}
    desc = (data.get('description') or '').strip()
    dims = (data.get('dimensions') or '1080x1350').strip()
    try:
        w, h = [int(x) for x in dims.lower().split('x')]
    except:
        w, h = 1080, 1350

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for i in range(1,4):
            img = make_card(f'Ad {i}: {desc}', w, h)
            ib = io.BytesIO()
            img.save(ib, format='JPEG', quality=92, optimize=True)
            z.writestr(f'ad_{i}.jpg', ib.getvalue())
        z.writestr('copy.txt', (desc + '\n\nCTA: Learn more →').encode('utf-8'))
        z.writestr('readme.txt', b'Advertising Agency - demo ZIP.')

    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True, download_name='ads.zip')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '10000')), debug=False)
