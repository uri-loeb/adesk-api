
import os
import uuid
import time
from flask import Flask, request, jsonify, redirect, send_from_directory, abort
from flask_cors import CORS
import stripe

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_replace_me")
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_replace_me")

YOUR_DOMAIN = os.getenv("PUBLIC_DOMAIN", "http://localhost:5000")

valid_tokens = {}

@app.route("/")
def home():
    return send_from_directory(".", "stripe.html")

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "ADesk Access (24h)"},
                    "unit_amount": 100,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{YOUR_DOMAIN}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{YOUR_DOMAIN}/cancel",
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
    except Exception:
        pass

    token = str(uuid.uuid4())
    valid_tokens[token] = time.time()
    return redirect(f"/iframe?token={token}", code=302)

@app.route("/cancel")
def cancel():
    return "<h2>Payment canceled.</h2>"

@app.route("/iframe")
def iframe_entry():
    token = request.args.get("token", "")
    if token not in valid_tokens:
        return "Invalid token", 403
    if time.time() - valid_tokens[token] > 86400:
        return "Token expired", 403
    return send_from_directory("iframe_demo", "index.html")

@app.route("/iframe_demo/<path:filename>")
def iframe_assets(filename):
    token = request.args.get("token", "")
    if token not in valid_tokens or time.time() - valid_tokens[token] > 86400:
        return abort(403)
    return send_from_directory("iframe_demo", filename)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
