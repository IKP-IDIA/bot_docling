from fastapi import FastAPI, HTTPException
import json
import requests
import os

app = FastAPI()

# 🔹 URL ของ Meilisearch
MEILI_URL = "http://10.1.0.150:7700/indexes/documents2/documents"
HEADERS = {
    "Content-Type": "application/json",
    # "Authorization": "Bearer MASTER_KEY"
}

def read_and_send_json(path: str):
    """
    อ่านไฟล์ JSON, ส่งเข้า Meilisearch, และคืนข้อมูล JSON
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"ไม่พบไฟล์: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data_list = [data] if isinstance(data, dict) else data

    try:
        response = requests.post(MEILI_URL, headers=HEADERS, json=data_list)
        if response.status_code in [200, 202]:
            return {"status": "success", "message": f"ส่งไฟล์ {os.path.basename(path)} สำเร็จ!", "json_content": data}
        else:
            return {"status": "error", "message": f"ส่งไม่สำเร็จ ({response.status_code})", "json_content": data}
    except Exception as e:
        return {"status": "error", "message": str(e), "json_content": data}

# 🔹 FastAPI endpoint
@app.get("/send_json")
def send_json(path: str):
    try:
        result = read_and_send_json(path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
