import os
import openai
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

openai.api_key = os.environ["OPENAI_API_KEY"]

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
        # 1. Generate marketing copy
        copy_prompt = f"Write a creative, engaging ad for the following product in exactly 50 words. Product: {product}"
        gpt_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a creative marketing copywriter."},
                {"role": "user", "content": copy_prompt}
            ]
        )
        full_text = gpt_response.choices[0].message.content.strip()

        # 2. Generate short headline for image
        headline_prompt = f"Generate a short, punchy advertising headline (4-6 words) for this product: {product}"
        headline_response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You write short, catchy ad headlines."},
                {"role": "user", "content": headline_prompt}
            ]
        )
        headline = headline_response.choices[0].message.content.strip().replace('"', '')

        # 3. Generate image from headline
        image_response = openai.Image.create(
            prompt=f"Advertising image for: {headline}. Show the headline text in the image. Marketing style. Realistic composition.",
            size=dalle_size,
            n=1,
            response_format="url"
        )
        image_url = image_response["data"][0]["url"]

        ads.append({
            "image": image_url,
            "text": full_text,
            "dimensions": dimensions
        })

    return jsonify(ads)

if __name__ == "__main__":
    app.run(debug=True)
