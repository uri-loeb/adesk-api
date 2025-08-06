
import os
import openai
from flask import Flask, request, jsonify
from flask_cors import CORS

# הגדרת המפתח מתוך משתני סביבה
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app)

# המרה בין מימדים שנשלחים ל־DALL·E
dalle_size_map = {
    "1080x1080": "1024x1024",
    "1080x1350": "1024x1024",
    "1080x566": "1024x576",
    "1080x1920": "1024x1792",
    "1200x628": "1024x512",
    "1640x856": "1024x512"
}

@app.route("/api/generate", methods=["POST"])
def generate_ads():
    try:
        data = request.get_json()
        product = data.get("product", "").strip()
        dimensions = data.get("dimensions", "1080x1080")

        if not product:
            return jsonify({"error": "Missing product input"}), 400

        dalle_size = dalle_size_map.get(dimensions, "1024x1024")
        ads = []

        for i in range(3):
            # 1. יצירת כותרת
            headline_prompt = f"Create a short, punchy headline for an ad promoting: {product}. One short sentence only."
            headline = gpt_text(headline_prompt)

            # 2. יצירת טקסט שיווקי
            text_prompt = f"Write a short, creative marketing text (exactly 50 words) for a social media ad promoting: {product}. Do not repeat the headline. Focus on engagement and clarity."
            full_text = gpt_text(text_prompt)

            # 3. יצירת תמונה עם הכותרת בלבד
            image_prompt = f"Advertising image for: {headline}. Show the headline text in the image. Marketing style. Realistic composition. No other text. No extra branding."
            image_url = generate_image(image_prompt, dalle_size)

            ads.append({
                "image": image_url,
                "text": full_text,
                "dimensions": dimensions
            })

        return jsonify({"ads": ads})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def gpt_text(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8
        )
        return response["choices"][0]["message"]["content"].strip()
    except Exception:
        # fallback
        return "This is a fallback marketing message with no GPT available."


def generate_image(prompt, size):
    try:
        response = openai.Image.create(
            prompt=prompt,
            size=size,
            n=1,
            response_format="url"
        )
        return response["data"][0]["url"]
    except Exception:
        # fallback
        return "https://via.placeholder.com/1024x1024.png?text=Image+Unavailable"


if __name__ == "__main__":
    app.run(debug=True)
