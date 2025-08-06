from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route("/api/generate", methods=["POST"])
def generate_ads():
    data = request.get_json()
    product = data.get("product", "Product")
    dimensions = data.get("dimensions", "500x500")

    ads = []
    for i in range(3):
        ad = {
            "image": f"https://via.placeholder.com/{dimensions}?text=Ad+{i+1}+for+{product.replace(' ', '+')}",
            "text": f"This is ad variation {i+1} for {product}. Eye-catching and engaging content here!"
        }
        ads.append(ad)

    return jsonify(ads)

if __name__ == "__main__":
    app.run(debug=True)
