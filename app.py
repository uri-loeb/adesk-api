from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route('/api/generate', methods=['POST'])
def generate_ads():
    data = request.json
    product = data.get("product", "")
    dimensions = data.get("dimensions", "")

    variations = [
        {
            "image": f"https://via.placeholder.com/500x500?text=Ad+1+for+{product.replace(' ', '+')}",
            "text": f"Discover the power of {product}. Perfectly tailored to {dimensions} – version 1."
        },
        {
            "image": f"https://via.placeholder.com/500x500?text=Ad+2+for+{product.replace(' ', '+')}",
            "text": f"{product} just got smarter. A fresh perspective at {dimensions} – version 2."
        },
        {
            "image": f"https://via.placeholder.com/500x500?text=Ad+3+for+{product.replace(' ', '+')}",
            "text": f"Ready for impact? {product} meets design at {dimensions} – version 3."
        }
    ]

    return jsonify(variations)

if __name__ == '__main__':
    app.run()
