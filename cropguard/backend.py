"""
CropGuard AI -- Flask Backend
Calls the Roboflow Hosted Inference API directly via HTTP
(no SDK needed — avoids API-key validation quirks).
"""

import os
import io
import re
import base64
import sqlite3
import tempfile
import requests as http_requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# -- Roboflow Hosted API configuration --------------------------------------
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY")
ROBOFLOW_DETECT_URL = "https://detect.roboflow.com/rice-leaf-wfax3-vnwpd/1"

# Create uploads folder inside workspace for saving leaf photos
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Colour palette for bounding boxes
BOX_COLORS = [
    "#ef4444", "#f59e0b", "#a78bfa", "#60a5fa", "#f472b6",
    "#34d399", "#fb923c", "#38bdf8", "#e879f9", "#fbbf24",
]

# -- SQLite Database Setup -----------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "cropguard_users.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            state TEXT,
            crop TEXT,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            original_image TEXT NOT NULL,
            annotated_image TEXT NOT NULL,
            diseases_detected TEXT NOT NULL,
            total_detections INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()
    print("[+] Database and tables ready")

init_db()
print("[+] CropGuard AI backend ready (Roboflow Hosted API mode)")



# -- Serve the frontend ------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# -- Health-check -------------------------------------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# -- Authentication endpoints --------------------------------------------------
@app.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(force=True)
    name     = data.get("name", "").strip()
    phone    = data.get("phone", "").strip()
    email    = data.get("email", "").strip()
    state    = data.get("state", "").strip()
    crop     = data.get("crop", "").strip()
    password = data.get("password", "")

    # Validation
    if not name:
        return jsonify({"error": "Full name is required."}), 400
    if not phone and not email:
        return jsonify({"error": "Phone or email is required."}), 400
    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters."}), 400

    # Check if user already exists
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if phone:
        c.execute("SELECT id FROM users WHERE phone = ?", (phone,))
        if c.fetchone():
            conn.close()
            return jsonify({"error": "This phone number is already registered."}), 409
    if email:
        c.execute("SELECT id FROM users WHERE email = ?", (email,))
        if c.fetchone():
            conn.close()
            return jsonify({"error": "This email is already registered."}), 409

    # Create user
    password_hash = generate_password_hash(password)
    c.execute(
        "INSERT INTO users (name, phone, email, state, crop, password_hash) VALUES (?, ?, ?, ?, ?, ?)",
        (name, phone or None, email or None, state or None, crop or None, password_hash)
    )
    conn.commit()
    user_id = c.lastrowid
    conn.close()

    print(f"[+] New user registered: {name} (ID: {user_id})")
    return jsonify({"success": True, "user": {"id": user_id, "name": name}})


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    identifier = data.get("identifier", "").strip()  # phone or email
    password   = data.get("password", "")

    if not identifier:
        return jsonify({"error": "Phone or email is required."}), 400
    if not password:
        return jsonify({"error": "Password is required."}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Try matching by phone or email
    c.execute("SELECT id, name, password_hash FROM users WHERE phone = ? OR email = ?",
              (identifier, identifier))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "No account found with this phone/email."}), 401

    user_id, name, password_hash = row
    if not check_password_hash(password_hash, password):
        return jsonify({"error": "Incorrect password."}), 401

    print(f"[+] User logged in: {name} (ID: {user_id})")
    return jsonify({"success": True, "user": {"id": user_id, "name": name}})


# -- Serve physical upload images --------------------------------------------
@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# -- Profile endpoint --------------------------------------------------------
@app.route("/profile", methods=["POST"])
def profile():
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required."}), 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, phone, email, state, crop, created_at FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "User not found."}), 404

    u_id, name, phone, email, state, crop, created_at = row
    return jsonify({
        "success": True,
        "user": {
            "id": u_id,
            "name": name,
            "phone": phone,
            "email": email,
            "state": state,
            "crop": crop,
            "created_at": created_at
        }
    })


# -- History endpoint --------------------------------------------------------
@app.route("/history", methods=["GET"])
def history():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "User ID is required."}), 400

    try:
        import json
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT id, original_image, annotated_image, diseases_detected, total_detections, created_at FROM scans WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = c.fetchall()
        conn.close()

        scans = []
        for row in rows:
            scan_id, orig_img, anno_img, diseases_str, total_det, created_at = row
            scans.append({
                "id": scan_id,
                "original_image": orig_img,
                "annotated_image": anno_img,
                "diseases": json.loads(diseases_str),
                "total_detections": total_det,
                "created_at": created_at
            })
        return jsonify({"success": True, "scans": scans})
    except Exception as e:
        print(f"[!] History fetching error: {e}")
        return jsonify({"error": str(e)}), 500


# -- Detection endpoint -------------------------------------------------------
@app.route("/detect", methods=["POST"])
def detect():
    if "image" not in request.files:
        return jsonify({"error": "No image uploaded."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "Empty filename."}), 400

    user_id = request.form.get("user_id")

    try:
        # Read uploaded image
        img_bytes = file.read()
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        orig_w, orig_h = img.size

        # Generate unique filenames for server disk storage
        import uuid
        file_uuid = str(uuid.uuid4())
        orig_filename = f"{file_uuid}_orig.jpg"
        anno_filename = f"{file_uuid}_anno.jpg"
        orig_filepath = os.path.join(UPLOAD_FOLDER, orig_filename)
        anno_filepath = os.path.join(UPLOAD_FOLDER, anno_filename)

        # Save physical original image to disk
        img.save(orig_filepath, format="JPEG", quality=95)

        # Encode image as base64 for the Roboflow Hosted API
        buf_upload = io.BytesIO()
        img.save(buf_upload, format="JPEG", quality=95)
        img_b64 = base64.b64encode(buf_upload.getvalue()).decode("utf-8")

        # Call Roboflow Hosted Inference API
        print(f"[*] Sending image ({orig_w}x{orig_h}) to Roboflow ...")
        resp = http_requests.post(
            ROBOFLOW_DETECT_URL,
            params={"api_key": ROBOFLOW_API_KEY},
            data=img_b64,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )

        if resp.status_code != 200:
            error_msg = resp.text[:300]
            print(f"[!] Roboflow API error {resp.status_code}: {error_msg}")
            return jsonify({"error": f"Roboflow API error ({resp.status_code}): {error_msg}"}), 502

        result = resp.json()
        predictions = result.get("predictions", [])
        print(f"[+] Got {len(predictions)} prediction(s)")

        # Build colour map per class
        class_names_seen = []
        for p in predictions:
            if p["class"] not in class_names_seen:
                class_names_seen.append(p["class"])
        color_map = {
            name: BOX_COLORS[i % len(BOX_COLORS)]
            for i, name in enumerate(class_names_seen)
        }

        # -- Draw bounding boxes on the image --------------------------------
        draw = ImageDraw.Draw(img)
        try:
            font_size = max(16, int(min(orig_w, orig_h) * 0.028))
            font = ImageFont.truetype("arial.ttf", font_size)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18
                )
            except (OSError, IOError):
                font = ImageFont.load_default()

        diseases = []
        for pred in predictions:
            cls  = pred["class"]
            conf = round(pred["confidence"] * 100, 1)
            cx, cy = pred["x"], pred["y"]
            pw, ph = pred["width"], pred["height"]
            x1 = int(cx - pw / 2)
            y1 = int(cy - ph / 2)
            x2 = int(cx + pw / 2)
            y2 = int(cy + ph / 2)

            color  = color_map[cls]
            line_w = max(2, int(min(orig_w, orig_h) * 0.004))

            for i in range(line_w):
                draw.rectangle([x1 - i, y1 - i, x2 + i, y2 + i], outline=color)

            label = f"{cls} {conf}%"
            bbox  = draw.textbbox((x1, y1), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.rectangle([x1, y1 - th - 8, x1 + tw + 10, y1], fill=color)
            draw.text((x1 + 5, y1 - th - 5), label, fill="white", font=font)

            diseases.append({
                "name": cls,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],
            })

        # Save physical annotated image to disk
        img.save(anno_filepath, format="JPEG", quality=92)

        # -- Encode annotated image to base64 --------------------------------
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        annotated_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        # -- Log scan in database --------------------------------------------
        if user_id:
            try:
                import json
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute(
                    "INSERT INTO scans (user_id, original_image, annotated_image, diseases_detected, total_detections) VALUES (?, ?, ?, ?, ?)",
                    (
                        int(user_id),
                        f"/uploads/{orig_filename}",
                        f"/uploads/{anno_filename}",
                        json.dumps(diseases),
                        len(diseases)
                    )
                )
                conn.commit()
                conn.close()
                print(f"[+] Scan record logged for user_id={user_id}")
            except Exception as dberr:
                print(f"[!] SQLite scan log failed: {dberr}")

        return jsonify({
            "diseases": diseases,
            "total_detections": len(diseases),
            "annotated_image": f"data:image/jpeg;base64,{annotated_b64}",
            "original_image_url": f"/uploads/{orig_filename}",
            "annotated_image_url": f"/uploads/{anno_filename}",
        })

    except http_requests.exceptions.Timeout:
        return jsonify({"error": "Roboflow API timed out. Try again."}), 504
    except http_requests.exceptions.ConnectionError:
        return jsonify({"error": "Cannot reach Roboflow API. Check your internet."}), 503
    except Exception as e:
        print(f"[!] Detection error: {e}")
        return jsonify({"error": f"Detection error: {str(e)}"}), 500


# -- AI Chat Configuration ----------------------------------------------------
# OPTION 1 (Recommended): Groq — FREE, fast, generous limits
# -- LLaMA Chatbot integration (via Groq) --------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# OPTION 2: Google Gemini — FREE but has quota limits
# Get key at: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAt-aYn_ITxlUnc09zlBT4znzguC2AGq0M")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


# Store conversation history per session (simple in-memory)
chat_histories = {}

SYSTEM_PROMPTS = {
    "en": (
        "You are FarmDoc AI, a brilliant and friendly agricultural expert and general-purpose AI assistant. "
        "You specialize in crop diseases, treatments, pesticides, organic farming, and Indian agriculture — "
        "but you can also answer ANY question on ANY topic (science, math, coding, general knowledge, etc.) "
        "just like ChatGPT or Claude would.\n\n"
        "Guidelines:\n"
        "- Be concise but thorough (under 200 words unless the topic needs more)\n"
        "- Use bullet points and bold for key info\n"
        "- Be practical and farmer-friendly when discussing agriculture\n"
        "- For non-agriculture questions, answer accurately and helpfully\n"
        "- Always be polite and encouraging\n"
        "- Answer in English"
    ),
    "hi": (
        "You are FarmDoc AI, a brilliant agricultural expert and general-purpose AI assistant. "
        "You specialize in crop diseases and Indian agriculture, but can answer ANY question on ANY topic. "
        "IMPORTANT: Always respond in simple Hindi (Devanagari script) that Indian farmers can easily understand. "
        "Be concise (under 200 words), practical, and use bullet points."
    ),
    "kn": (
        "You are FarmDoc AI, a brilliant agricultural expert and general-purpose AI assistant. "
        "You specialize in crop diseases and Indian agriculture, but can answer ANY question on ANY topic. "
        "IMPORTANT: Always respond in simple Kannada (Kannada script) that Karnataka farmers can easily understand. "
        "Be concise (under 200 words), practical, and use bullet points."
    ),
}


# -- Chat endpoint (AI powered) -----------------------------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    message  = data.get("message", "").strip()
    language = data.get("language", "en")
    context  = data.get("detection_context", "No detection yet")
    session  = data.get("session_id", "default")

    if not message:
        return jsonify({"error": "Empty message."}), 400

    # Try Groq first (fast + generous free tier)
    if GROQ_API_KEY and GROQ_API_KEY != "PASTE_YOUR_GROQ_KEY_HERE":
        reply = _ask_groq(message, context, language, session)
        if reply:
            return jsonify({"reply": reply})

    # Try Gemini as backup
    if GEMINI_API_KEY and GEMINI_API_KEY != "PASTE_YOUR_GEMINI_KEY_HERE":
        reply = _ask_gemini(message, context, language, session)
        if reply:
            return jsonify({"reply": reply})

    # Fallback: rule-based
    reply = _rule_based_reply(message, context, language)
    return jsonify({"reply": reply})


def _build_system_prompt(lang: str, context: str) -> str:
    """Build the system prompt with optional detection context."""
    prompt = SYSTEM_PROMPTS.get(lang, SYSTEM_PROMPTS["en"])
    if context and context != "No detection yet":
        prompt += f"\n\nCrop scan context: The farmer's crop was analyzed and shows: {context}. Use this info when relevant."
    return prompt


def _get_history(session: str) -> list:
    """Get or create conversation history for a session."""
    if session not in chat_histories:
        chat_histories[session] = []
    return chat_histories[session]


def _save_history(session: str, user_msg: str, bot_reply: str):
    """Save exchange to history, trim if too long."""
    history = _get_history(session)
    history.append({"role": "user", "text": user_msg})
    history.append({"role": "assistant", "text": bot_reply})
    if len(history) > 20:
        chat_histories[session] = history[-20:]


def _ask_groq(message: str, context: str, lang: str, session: str) -> str:
    """Call Groq API (Llama 3.3 70B) — free and fast."""
    try:
        system_prompt = _build_system_prompt(lang, context)
        history = _get_history(session)

        # Build messages array
        messages = [{"role": "system", "content": system_prompt}]
        for h in history[-10:]:
            messages.append({"role": h["role"], "content": h["text"]})
        messages.append({"role": "user", "content": message})

        resp = http_requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "max_tokens": 1024,
                "temperature": 0.7,
            },
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )

        if resp.status_code != 200:
            print(f"[!] Groq API error {resp.status_code}: {resp.text[:200]}")
            return None

        reply = resp.json()["choices"][0]["message"]["content"]
        _save_history(session, message, reply)
        return reply

    except Exception as e:
        print(f"[!] Groq error: {e}")
        return None


def _ask_gemini(message: str, context: str, lang: str, session: str) -> str:
    """Call Google Gemini API with conversation history."""
    try:
        system_prompt = _build_system_prompt(lang, context)
        history = _get_history(session)

        # Build contents array (Gemini uses "user"/"model" roles)
        contents = []
        for h in history[-10:]:
            role = "model" if h["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": h["text"]}]})
        contents.append({"role": "user", "parts": [{"text": message}]})

        resp = http_requests.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
            },
            headers={"Content-Type": "application/json"},
            timeout=15,
        )

        if resp.status_code != 200:
            print(f"[!] Gemini API error {resp.status_code}: {resp.text[:200]}")
            return None

        reply = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        _save_history(session, message, reply)
        return reply

    except Exception as e:
        print(f"[!] Gemini error: {e}")
        return None


def _rule_based_reply(message: str, context: str, lang: str) -> str:
    """Fallback rule-based replies when Gemini is not available."""
    msg = message.lower()
    ctx = context.lower()

    diseases_mentioned = []
    known = [
        "bacterial_leaf_blight", "brown_spot", "leaf_blast",
        "leaf_scald", "narrow_brown_spot", "neck_blast",
        "rice_hispa", "sheath_blight", "tungro",
        "bacterial leaf blight", "brown spot", "leaf blast",
        "leaf scald", "narrow brown spot", "neck blast",
        "rice hispa", "sheath blight",
    ]
    for d in known:
        if d in ctx or d in msg:
            diseases_mentioned.append(d.replace("_", " ").title())

    disease_str = ", ".join(set(diseases_mentioned)) if diseases_mentioned else None

    if "treat" in msg or "cure" in msg:
        base = f"For **{disease_str}**:\n\n" if disease_str else ""
        return base + (
            "1. **Remove** affected leaves and burn them.\n"
            "2. **Apply** fungicide (Mancozeb 75 WP @ 2g/L or Carbendazim 50 WP @ 1g/L).\n"
            "3. **Ensure** proper spacing for air circulation.\n"
            "4. **Avoid** excess nitrogen fertiliser.\n"
            "5. **Drain** excess water from the field."
        )

    if "pesticide" in msg or "fungicide" in msg:
        return (
            "**Recommended pesticides/fungicides:**\n\n"
            "- **Mancozeb 75 WP** -- 2g per litre\n"
            "- **Carbendazim 50 WP** -- 1g per litre\n"
            "- **Tricyclazole 75 WP** -- 0.6g per litre (for blast)\n"
            "- **Propiconazole 25 EC** -- 1ml per litre"
        )

    if "organic" in msg or "natural" in msg:
        return (
            "**Organic treatments:**\n\n"
            "- **Neem oil** -- 5ml/litre + soap solution\n"
            "- **Trichoderma viride** -- 2.5 kg/hectare\n"
            "- **Pseudomonas fluorescens** -- seed treatment 10g/kg"
        )

    if disease_str:
        return (
            f"I detected **{disease_str}** in your crop.\n\n"
            "Ask me: How to **treat** it? Which **pesticide**? "
            "Will it **spread**? **Organic** remedies?"
        )

    return (
        "I'm FarmDoc AI! I'm currently in basic mode.\n\n"
        "To unlock full AI chat (like ChatGPT), add a free **Gemini API key** in backend.py.\n"
        "Get one at: https://aistudio.google.com/app/apikey"
    )


# -- Run -----------------------------------------------------------------------
if __name__ == "__main__":
    print("\n  [CropGuard AI Backend]")
    print(f"  Roboflow API: {ROBOFLOW_DETECT_URL}")
    print("  Open http://127.0.0.1:5000 in your browser\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
