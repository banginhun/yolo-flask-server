from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return '서버 잘 돌아감!'

