# ✅ 서버 상단에 전역 변수 추가
last_uploaded_filename = None

@app.route('/')
def index():
    return render_template('index.html', last_image=last_uploaded_filename)

@app.route('/predict', methods=['POST'])
def predict():
    global last_uploaded_filename
    if 'image' not in request.files:
        return "No file part"
    file = request.files['image']
    if file.filename == '':
        return "No selected file"

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    # ✅ 마지막 업로드 파일 기억
    last_uploaded_filename = file.filename

    result = "YOLO 모델 결과: (예시 라벨)"
    return render_template('result.html', result=result, image_url=filepath)
