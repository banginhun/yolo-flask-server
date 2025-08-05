from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/ping', methods=['GET'])
def ping():
    return "pong"

@app.route('/receive', methods=['POST'])
def receive():
    if 'image' not in request.files:
        return jsonify({'error': 'No image uploaded'}), 400
    print("📷 이미지 수신 완료")
    return jsonify({'status': 'received'}), 200

if __name__ == '__main__':
    app.run()
