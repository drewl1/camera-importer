import os
import shutil
import hashlib
import json
from flask import Flask, jsonify, request, Response, render_template

app = Flask(__name__)

DATA_FILE = "/mnt/stor2/camera_import_db.json"

DESTINATIONS = {
    "gopro": "/mnt/stor2/gopro_uploads",
    "r100": "/mnt/stor2/canonR100_uploads",
    "xs": "/mnt/stor2/canonXS_uploads"
}

def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_db(db):
    with open(DATA_FILE, "w") as f:
        json.dump(db, f, indent=2)

def hash_file(path):
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def find_camera():
    media_root = "/media"
    for device in os.listdir(media_root):
        dcim_path = os.path.join(media_root, device, "DCIM")
        if os.path.exists(dcim_path):
            return device, dcim_path
    return None, None

def detect_camera_type(device_name):
    name = device_name.lower()
    if "gopro" in name:
        return "gopro"
    if "canon" in name and "r100" in name:
        return "r100"
    if "canon" in name:
        return "xs"
    return "gopro"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan")
def scan():
    device, dcim = find_camera()
    if not dcim:
        return jsonify({"device": None, "new_files": 0, "already_imported": 0})

    camera_type = detect_camera_type(device)
    db = load_db()
    db.setdefault(camera_type, {"files": [], "hashes": []})

    new_files = 0
    existing = 0

    for root, _, files in os.walk(dcim):
        for f in files:
            path = os.path.join(root, f)
            if path in db[camera_type]["files"]:
                existing += 1
            else:
                new_files += 1

    return jsonify({
        "device": device,
        "camera_type": camera_type,
        "new_files": new_files,
        "already_imported": existing
    })

@app.route("/import", methods=["POST"])
def import_files():
    data = request.json
    destination_key = data["destination"]

    dest_path = DESTINATIONS[destination_key]
    device, dcim = find_camera()

    if not dcim:
        return "No camera found"

    db = load_db()
    db.setdefault(destination_key, {"files": [], "hashes": []})

    def generate():
        total = sum(len(files) for _, _, files in os.walk(dcim))
        count = 0

        for root, _, files in os.walk(dcim):
            for f in files:
                src = os.path.join(root, f)
                file_hash = hash_file(src)

                if src in db[destination_key]["files"] or file_hash in db[destination_key]["hashes"]:
                    yield f"Skipping (duplicate): {f}\n"
                    continue

                dest = os.path.join(dest_path, f)

                i = 1
                base, ext = os.path.splitext(f)
                while os.path.exists(dest):
                    dest = os.path.join(dest_path, f"{base}_{i}{ext}")
                    i += 1

                shutil.copy2(src, dest)

                db[destination_key]["files"].append(src)
                db[destination_key]["hashes"].append(file_hash)

                count += 1
                yield f"{count}/{total} imported: {f}\n"

        save_db(db)
        yield "DONE\n"

    return Response(generate(), mimetype='text/plain')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)