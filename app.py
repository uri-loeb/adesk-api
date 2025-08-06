import os
import openai
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.environ.get("OPENAI_API_KEY", "")

DALLE_SIZES = {
    "1080x1080": "1024x1024",
    "1080x1350": "1024x1792",
    "1080x566": "1792x1024",
    "1080x1920": "1024x1792",
    "1200x628": "1792x1024",
    "1640x856": "1792x1024"
}

@app.route("/api/generate", methods=["POST"])
def generate_ads():
    data = request.get_json()
    product = data.get("product", "")
    dimensions = data.get("dimensions", "1080x1080")
    dalle_size = DALLE_SIZES.get(dimensions, "1024x1024")

    ads = []

    for i in range(3):
        # טקסט שיווקי
        try:
            copy_prompt = f"Write a creative, engaging ad for the following product in exactly 50 words. Product: {product}"
            gpt_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a creative marketing copywriter."},
                    {"role": "user", "content": copy_prompt}
                ]
            )
            full_text = gpt_response.choices[0].message.content.strip()
        except Exception as e:
            print("⚠️ Text fallback:", e)
            full_text = f"This is a sample ad for {product}. Upgrade your account to see real AI-generated copy."

        # כותרת
        try:
            headline_prompt = f"Generate a short, punchy advertising headline (4-6 words) for this product: {product}"
            headline_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You write short, catchy ad headlines."},
                    {"role": "user", "content": headline_prompt}
                ]
            )
            headline = headline_response.choices[0].message.content.strip().replace('"', '')
        except Exception as e:
            print("⚠️ Headline fallback:", e)
            headline = f"Sample Headline {i+1}"

        # תמונה
        try:
    image_response = openai.Image.create(
        prompt=f"...",
        size=dalle_size,
        n=1,
        response_format="url"
    )
    image_url = image_response["data"][0]["url"]
except Exception as e:
    print("⚠️ Image fallback:", e)
    image_url = f"https://via.placeholder.com/{dimensions}?text=Ad+{i+1}+for+{product.replace(' ', '+')}"


        ads.append({
            "image": image_url,
            "text": full_text,
            "dimensions": dimensions
        })

    return jsonify(ads)

if __name__ == "__main__":
    app.run(debug=True)
