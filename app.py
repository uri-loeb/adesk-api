
import os
import secrets
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
import stripe

app = Flask(__name__)
CORS(app)

# Environment variables
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL")   # e.g., https://your-netlify-app.netlify.app
BACKEND_URL = os.getenv("BACKEND_URL")     # e.g., https://your-backend.onrender.com

if not STRIPE_SECRET_KEY or not FRONTEND_URL or not BACKEND_URL:
    raise RuntimeError("Missing environment variables. Set STRIPE_SECRET_KEY, FRONTEND_URL, BACKEND_URL")

stripe.api_key = STRIPE_SECRET_KEY

@app.route("/")
def home():
    return "✅ ADesk Backend Running"

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "ADesk Access"},
                    "unit_amount": 500,  # $5.00
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{BACKEND_URL}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{FRONTEND_URL}/payment-cancelled"
        )
        return jsonify({"id": session.id, "url": session.url})
    except Exception as e:
        return jsonify(error=str(e)), 400

@app.route("/payment-success")
def payment_success():
    # In production, verify session_id and payment status via Stripe API
    token = secrets.token_urlsafe(24)  # one-time token
    return redirect(f"{FRONTEND_URL}?token={token}&backend={BACKEND_URL}")

@app.route("/verify-token")
def verify_token():
    token = request.args.get("token")
    if not token:
        return jsonify({"valid": False}), 400
    return jsonify({"valid": True, "token": token})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
