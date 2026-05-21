from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import os
import json
import random
import time
import asyncio
from pathlib import Path
import re
from difflib import SequenceMatcher
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Set
from enum import Enum
import base64
import tempfile
from datetime import datetime
import hashlib

# =========================================
# APP
# =========================================

app = FastAPI(title="Pen Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# STUDENT SERVICE
# =========================================

class StudentService:
    _rtdb = None
    _local_db: Dict = {"users": {}, "students": {}}
    _initialized = False
    
    @classmethod
    def initialize(cls):
        if cls._initialized:
            return
        cls._initialized = True
        
        try:
            import firebase_admin
            from firebase_admin import credentials
            
            cred = None
            b64 = os.getenv("FIREBASE_CREDENTIALS_BASE64", "")
            if b64:
                try:
                    decoded = base64.b64decode(b64).decode("utf-8")
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                        f.write(decoded)
                        temp_path = f.name
                    cred = credentials.Certificate(temp_path)
                    print("✅ Firebase Auth: using env var")
                    os.unlink(temp_path)
                except Exception as e:
                    print(f"❌ Base64 decode failed: {e}")
            
            if cred:
                try:
                    firebase_admin.get_app()
                except ValueError:
                    firebase_admin.initialize_app(cred, {
                        "databaseURL": "https://forme-6167f-default-rtdb.firebaseio.com"
                    })
                    print("✅ Firebase initialized!")
                
                try:
                    from firebase_admin import db
                    cls._rtdb = db
                    print("✅ Firebase RTDB ready!")
                except Exception as e:
                    print(f"⚠️ RTDB error: {e}")
        except ImportError:
            print("⚠️ firebase_admin not installed")
        except Exception as e:
            print(f"⚠️ Firebase error: {e}")
    
    @classmethod
    def _now_iso(cls) -> str:
        return datetime.now().isoformat()
    
    @classmethod
    def create_user(cls, username: str, password: str, name: str = "") -> Dict:
        username = username.strip().lower()
        
        if cls._rtdb:
            try:
                if cls._rtdb.reference(f"users/{username}").get():
                    return {"error": "اسم المستخدم موجود بالفعل"}
            except: pass
        
        if username in cls._local_db["users"]:
            return {"error": "اسم المستخدم موجود بالفعل"}
        
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        user_data = {
            "username": username,
            "password": hashed_password,
            "name": name or username,
            "created_at": cls._now_iso(),
            "chat_id": f"user_{username}",
        }
        
        cls._local_db["users"][username] = user_data
        
        if cls._rtdb:
            try:
                cls._rtdb.reference(f"users/{username}").set(user_data)
            except: pass
        
        return {"success": True, "username": username, "chat_id": f"user_{username}"}
    
    @classmethod
    def login_user(cls, username: str, password: str) -> Dict:
        username = username.strip().lower()
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        user_data = None
        if cls._rtdb:
            try:
                user_data = cls._rtdb.reference(f"users/{username}").get()
            except: pass
        
        if not user_data:
            user_data = cls._local_db["users"].get(username)
        
        if not user_data:
            return {"error": "اسم المستخدم غير موجود"}
        
        if user_data.get("password") != hashed_password:
            return {"error": "كلمة المرور غير صحيحة"}
        
        return {
            "success": True,
            "username": username,
            "name": user_data.get("name", username),
            "chat_id": f"user_{username}"
        }
    
    @classmethod
    def save_conversation(cls, username: str, user_msg: str, bot_reply: str):
        conversation = {
            "user_message": user_msg,
            "bot_reply": bot_reply,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }
        
        if "conversations" not in cls._local_db:
            cls._local_db["conversations"] = {}
        if username not in cls._local_db["conversations"]:
            cls._local_db["conversations"][username] = []
        cls._local_db["conversations"][username].append(conversation)
        
        if cls._rtdb:
            try:
                cls._rtdb.reference(f"students/{username}/conversations").push(conversation)
            except: pass
    
    @classmethod
    def save_exam_result(cls, username: str, result: Dict) -> Dict:
        correct = result.get("correct", 0)
        total = result.get("total", 1)
        percentage = int((correct / max(total, 1)) * 100)
        
        exam_data = {
            "score": correct,
            "total": total,
            "percentage": percentage,
            "timestamp": int(datetime.now().timestamp() * 1000),
            "grade": cls._calculate_grade(percentage),
        }
        
        if cls._rtdb:
            try:
                cls._rtdb.reference(f"students/{username}/exams").push(exam_data)
            except: pass
        
        return exam_data
    
    @classmethod
    def _calculate_grade(cls, percentage: int) -> str:
        if percentage >= 90: return "ممتاز 🏆"
        elif percentage >= 80: return "جيد جداً 🌟"
        elif percentage >= 65: return "جيد 👍"
        elif percentage >= 50: return "مقبول 📚"
        return "ضعيف 💪"
    
    @classmethod
    def get_level_analytics(cls, username: str) -> Optional[str]:
        exams_data = {}
        
        if cls._rtdb:
            try:
                exams_data = cls._rtdb.reference(f"students/{username}/exams").get() or {}
            except: pass
        
        if not exams_data:
            return None
        
        total_exams = len(exams_data)
        total_score = sum(e.get("score", 0) for e in exams_data.values())
        total_questions = sum(e.get("total", 0) for e in exams_data.values())
        percentages = [e.get("percentage", 0) for e in exams_data.values()]
        
        avg_percentage = int(sum(percentages) / len(percentages)) if percentages else 0
        best_score = max(percentages) if percentages else 0
        
        if avg_percentage >= 80:
            suggestion = "🌟 أنت في مستوى متقدم - جرب `امتحان صعب`"
        elif avg_percentage >= 60:
            suggestion = "👍 مستواك كويس - ركز على `خطة التركيز`"
        else:
            suggestion = "💪 ابدأ بـ `امتحان سهل` و `شرح النحو`"
        
        return f"""
📊 *تحليل مستواك*

🏆 *المستوى:* {cls._calculate_grade(avg_percentage)}
📈 *المتوسط:* {avg_percentage}%

📝 *إحصائيات:*
• عدد الامتحانات: {total_exams}
• أفضل نتيجة: {best_score}%
• إجمالي الأسئلة: {total_questions}
• إجابات صحيحة: {total_score}

💡 *نصيحة:*
{suggestion}

🔄 *جرب:* `امتحان` | `اختبرني` | `خطة التركيز`
"""

StudentService.initialize()

# =========================================
# CONFIG
# =========================================

MAX_QUESTION_LENGTH = 350
SESSION_TIMEOUT = 600
RATE_LIMIT_SECONDS = 1.0

# =========================================
# DATA LOADING
# =========================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

ALL_QUESTIONS: List[Dict] = []
MCQ_QUESTIONS: List[Dict] = []
QUESTIONS_BY_DIFFICULTY: Dict[str, List[Dict]] = defaultdict(list)

def detect_question_type(question: Dict) -> str:
    choices = question.get("choices", [])
    if not choices or len(choices) < 2:
        return "open_text"
    
    answer_key = str(question.get("answer_key", "")).strip()
    if not answer_key:
        return "open_text"
    
    if answer_key.isdigit():
        return "mcq"
    
    if answer_key in ["أ", "ب", "ج", "د"]:
        return "mcq"
    
    if answer_key.lower() in ["a", "b", "c", "d"]:
        return "mcq"
    
    return "open_text"

def get_answer_index(question: Dict) -> Optional[int]:
    answer_key = str(question.get("answer_key", "")).strip()
    choices = question.get("choices", [])
    
    if not choices:
        return None
    
    if answer_key.isdigit():
        idx = int(answer_key) - 1
        return idx if 0 <= idx < len(choices) else None
    
    arabic_keys = ["أ", "ب", "ج", "د"]
    if answer_key in arabic_keys:
        return arabic_keys.index(answer_key)
    
    english_keys = ["a", "b", "c", "d"]
    if answer_key.lower() in english_keys:
        return english_keys.index(answer_key.lower())
    
    return None

def extract_all_questions(data, depth=0):
    questions = []
    if depth > 10:
        return questions
    
    if isinstance(data, dict):
        if "prompt" in data and "question_id" in data:
            questions.append({
                "question_id": data.get("question_id", ""),
                "prompt": data.get("prompt", ""),
                "question": data.get("prompt", ""),
                "explanation": data.get("explanation", ""),
                "answer_key": data.get("answer_key", ""),
                "choices": data.get("choices", data.get("options", [])),
                "difficulty": data.get("difficulty", "medium"),
                "skill": data.get("skill", ""),
                "question_type": ""
            })
        elif "question" in data:
            questions.append({
                "question_id": data.get("id", ""),
                "prompt": data.get("question", ""),
                "question": data.get("question", ""),
                "explanation": data.get("explanation", data.get("answer", "")),
                "answer_key": data.get("answer_key", data.get("correct", "")),
                "choices": data.get("choices", data.get("options", [])),
                "difficulty": data.get("difficulty", "medium"),
                "skill": data.get("skill", ""),
                "question_type": ""
            })
        
        for key in ["questions", "sections", "lessons", "items", "exercises"]:
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    questions.extend(extract_all_questions(item, depth+1))
        
        for key, value in data.items():
            if key not in ["questions", "sections", "lessons", "items", "exercises"]:
                if isinstance(value, (dict, list)):
                    questions.extend(extract_all_questions(value, depth+1))
    
    elif isinstance(data, list):
        for item in data:
            questions.extend(extract_all_questions(item, depth+1))
    
    return questions

def load_all_data():
    global ALL_QUESTIONS, MCQ_QUESTIONS, QUESTIONS_BY_DIFFICULTY
    ALL_QUESTIONS = []
    MCQ_QUESTIONS = []
    QUESTIONS_BY_DIFFICULTY = defaultdict(list)
    seen = set()
    
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(exist_ok=True)
        return
    
    files = list(DATA_DIR.glob("*.json"))
    print(f"📚 FOUND {len(files)} FILES")
    
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                questions = extract_all_questions(data)
                
                for q in questions:
                    q_text = str(q.get("question", ""))[:100]
                    if q_text and q_text not in seen:
                        seen.add(q_text)
                        q["question_type"] = detect_question_type(q)
                        ALL_QUESTIONS.append(q)
                        
                        if q["question_type"] == "mcq":
                            MCQ_QUESTIONS.append(q)
                        
                        QUESTIONS_BY_DIFFICULTY[q.get("difficulty", "medium")].append(q)
                
                print(f"✅ Loaded: {file.name}")
        except Exception as e:
            print(f"❌ ERROR: {file.name}: {e}")
    
    print(f"🔥 TOTAL: {len(ALL_QUESTIONS)} | MCQ: {len(MCQ_QUESTIONS)}")

load_all_data()

# =========================================
# SESSION MANAGEMENT
# =========================================

class ExamSession:
    def __init__(self, questions: List[Dict], level: str = "medium"):
        self.questions = questions
        self.current_index = 0
        self.score = 0
        self.total = len(questions)
        self.level = level
        self.active = True
        self.last_activity = time.time()
    
    def is_expired(self) -> bool:
        return time.time() - self.last_activity > SESSION_TIMEOUT
    
    def check_answer(self, user_answer: int) -> Dict:
        self.last_activity = time.time()
        question = self.questions[self.current_index]
        
        correct_idx = get_answer_index(question)
        user_idx = user_answer - 1
        
        is_correct = (correct_idx is not None and correct_idx == user_idx)
        if is_correct:
            self.score += 1
        
        choices = question.get("choices", [])
        correct_answer_text = ""
        if correct_idx is not None and 0 <= correct_idx < len(choices):
            choice = choices[correct_idx]
            correct_answer_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
        
        result = {
            "correct": is_correct,
            "correct_answer": correct_answer_text,
            "explanation": question.get("explanation", ""),
            "current_score": self.score,
            "question_number": self.current_index + 1,
            "total": self.total
        }
        
        self.current_index += 1
        if self.current_index >= self.total:
            self.active = False
        
        return result

user_sessions: Dict[str, ExamSession] = {}
LAST_MESSAGE_TIME: Dict[str, float] = {}
ACTIVE_USERS: Dict[str, str] = {}

async def cleanup_expired_sessions():
    while True:
        try:
            expired = [cid for cid, s in user_sessions.items() if s.is_expired()]
            for cid in expired:
                del user_sessions[cid]
        except: pass
        await asyncio.sleep(60)

# =========================================
# RESPONSE GENERATORS
# =========================================

DIFFICULTY_AR = {"easy": "سهل 🟢", "medium": "متوسط 🟡", "hard": "صعب 🔴"}

def generate_exam(level: str = None, count: int = 5) -> str:
    if not ALL_QUESTIONS:
        return "❌ مفيش أسئلة متاحة حالياً"
    
    filtered = QUESTIONS_BY_DIFFICULTY.get(level, ALL_QUESTIONS.copy()) if level else ALL_QUESTIONS.copy()
    
    if not filtered:
        return f"❌ مفيش أسئلة متاحة بالمستوى '{level or 'عام'}'"
    
    selected = random.sample(filtered, min(count, len(filtered)))
    level_name = DIFFICULTY_AR.get(level, "شامل 📝")
    
    exam = f"📝 *امتحان {level_name}*\n{'─' * 25}\n\n"
    
    for i, q in enumerate(selected, 1):
        question_text = q.get("prompt", "سؤال")[:MAX_QUESTION_LENGTH]
        q_type = q.get("question_type", "")
        type_label = "📝" if q_type == "open_text" else "🔤"
        
        exam += f"*{i}. {type_label}* {question_text}\n"
        
        if q_type == "mcq" and q.get("choices"):
            for idx, choice in enumerate(q.get("choices", []), 1):
                choice_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
                exam += f"   {idx}️⃣ {choice_text}\n"
            exam += "\n"
    
    exam += f"{'─' * 25}\n📝 *عدد الأسئلة: {len(selected)}*\n💪 *ربنا معاك يا بطل*"
    return exam

def start_interactive_exam(chat_id: str, level: str = "medium") -> str:
    filtered = MCQ_QUESTIONS.copy() if MCQ_QUESTIONS else ALL_QUESTIONS.copy()
    
    if level in ["easy", "medium", "hard"]:
        level_filtered = [q for q in filtered if q.get("difficulty") == level]
        if level_filtered:
            filtered = level_filtered
    
    if len(filtered) >= 5:
        selected = random.sample(filtered, 5)
    elif len(filtered) >= 2:
        selected = filtered[:5]
    else:
        return "❌ عدد الأسئلة غير كافي"
    
    session = ExamSession(selected, level)
    user_sessions[chat_id] = session
    
    question = selected[0]
    question_text = question.get("prompt", "سؤال")[:MAX_QUESTION_LENGTH]
    choices = question.get("choices", [])
    
    msg = f"🧠 *سؤال 1 من {len(selected)}*\n\n*{question_text}*\n\n"
    
    if choices:
        for idx, choice in enumerate(choices, 1):
            choice_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
            msg += f"{idx}️⃣ {choice_text}\n"
    
    msg += "\n📝 *ابعت رقم الإجابة* 👇"
    return msg

def process_exam_answer(chat_id: str, user_answer: str, username: str = None) -> str:
    session = user_sessions.get(chat_id)
    if not session:
        return ""
    
    try:
        numbers = re.findall(r'\d+', user_answer)
        if not numbers:
            return "❌ *ابعت رقم الإجابة فقط (1، 2، 3، 4)*"
        answer_num = int(numbers[0])
    except:
        return "❌ *ابعت رقم الإجابة فقط*"
    
    if answer_num < 1 or answer_num > 4:
        return "❌ *رقم الإجابة يجب أن يكون بين 1 و 4*"
    
    result = session.check_answer(answer_num)
    
    response = "✅ *إجابة صحيحة!* 🎉\n\n" if result["correct"] else f"❌ *إجابة خاطئة*\n✅ *الصحيحة: {result['correct_answer']}*\n\n"
    
    if result["explanation"]:
        response += f"📝 *الشرح:*\n{result['explanation'][:300]}\n\n"
    
    response += f"📊 *النتيجة: {result['current_score']} / {result['question_number']}*\n\n"
    
    if session.active:
        question = session.questions[session.current_index]
        question_text = question.get("prompt", "سؤال")[:MAX_QUESTION_LENGTH]
        choices = question.get("choices", [])
        
        response += f"🧠 *سؤال {session.current_index + 1} من {session.total}*\n\n*{question_text}*\n\n"
        
        if choices:
            for idx, choice in enumerate(choices, 1):
                choice_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
                response += f"{idx}️⃣ {choice_text}\n"
        
        response += "\n📝 *ابعت رقم الإجابة* 👇"
    else:
        final_score = result["current_score"]
        total = result["total"]
        percentage = int((final_score / total) * 100) if total > 0 else 0
        
        if username:
            StudentService.save_exam_result(username, {"correct": final_score, "total": total})
        
        emoji = "🏆" if percentage >= 80 else "👍" if percentage >= 60 else "📚"
        comment = "ممتاز!" if percentage >= 80 else "جيد - ركز على الأخطاء" if percentage >= 60 else "محتاج مذاكرة أكتر"
        
        response += f"{emoji} *الامتحان خلص!*\n\n📊 *النتيجة: {final_score} / {total}*\n📈 *النسبة: {percentage}%*\n\n{comment}\n\n🔄 *جرب:* `اختبرني` | `مستوايا`"
        
        del user_sessions[chat_id]
    
    return response

def generate_focus_plan() -> str:
    if not ALL_QUESTIONS:
        return "❌ مفيش بيانات"
    
    msg = "🎯 *خطة التركيز الذكية*\n" + "─" * 25 + "\n\n"
    msg += "📌 *أهم الموضوعات:*\n   ⭐ النحو والصرف\n   ⭐ البلاغة\n   ⭐ الأدب والنصوص\n\n"
    msg += f"📊 *إحصائيات:*\n   📝 الأسئلة: {len(ALL_QUESTIONS)}\n   🔤 MCQ: {len(MCQ_QUESTIONS)}\n"
    
    difficulties = Counter(q.get("difficulty", "medium") for q in ALL_QUESTIONS)
    msg += f"   🟢 سهل: {difficulties.get('easy', 0)}\n   🟡 متوسط: {difficulties.get('medium', 0)}\n   🔴 صعب: {difficulties.get('hard', 0)}\n"
    
    msg += "\n💪 *ركز على الموضوعات دي*"
    return msg

def get_greeting(username: str = None) -> str:
    name_line = f"\n👤 *{username}*" if username else ""
    return f"""👋 *أهلاً بيك في منصة Pen!*{name_line}

📝 *امتحانات:* `امتحان` - `امتحان سهل` - `متوسط` - `صعب`
🎯 *تفاعلي:* `اختبرني` - `اختبرني في البلاغة`
📊 *تحليل:* `خطة التركيز` - `مستوايا`
📚 *شرح:* `شرح [الدرس]`
💡 *استفسارات:* `اشرحلي` - `فسر` - `قارن`"""

# =========================================
# MAIN PROCESSOR
# =========================================

def is_rate_limited(chat_id: str) -> bool:
    current_time = time.time()
    if current_time - LAST_MESSAGE_TIME.get(chat_id, 0) < RATE_LIMIT_SECONDS:
        return True
    LAST_MESSAGE_TIME[chat_id] = current_time
    return False

async def process_message(chat_id: str, body: str, username: str = None) -> str:
    try:
        if is_rate_limited(chat_id):
            return ""
        
        if chat_id in user_sessions:
            session = user_sessions[chat_id]
            if session.active and not session.is_expired():
                reply = process_exam_answer(chat_id, body, username)
                if username and reply:
                    StudentService.save_conversation(username, body, reply)
                return reply
            else:
                del user_sessions[chat_id]
        
        body_lower = body.lower().strip()
        
        # امتحان تفاعلي
        if any(x in body_lower for x in ["اختبرني", "اختبرنى"]):
            level = "medium"
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower:
                    level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            return start_interactive_exam(chat_id, level)
        
        # امتحان عادي
        if any(x in body_lower for x in ["امتحان", "اختبار"]):
            level = None
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower:
                    level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            return generate_exam(level=level)
        
        # تحليل المستوى
        if body_lower in ["مستوايا", "مستوى", "تحليل"]:
            if username:
                analytics = StudentService.get_level_analytics(username)
                if analytics:
                    return analytics
            return "📊 *لسه مفيش بيانات*\nجرب تاخد امتحان: `اختبرني`"
        
        # خطة التركيز
        if any(x in body_lower for x in ["خطة", "تركيز", "ركز"]):
            return generate_focus_plan()
        
        # ترحيب
        if any(x in body_lower for x in ["اهلا", "مرحبا", "سلام", "هاي"]):
            return get_greeting(username)
        
        # شرح
        if "شرح" in body_lower:
            return "📚 *شرح*\n\nاكتب اسم الدرس بالتفصيل بعد كلمة شرح\nمثال: `شرح النحو`"
        
        reply = get_greeting(username)
        
        if username and reply:
            StudentService.save_conversation(username, body, reply)
        
        return reply
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return "❌ حصل خطأ"

# =========================================
# API ENDPOINTS
# =========================================

@app.post("/api/register")
async def register(request: Request):
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        name = data.get("name", "").strip()
        
        if not username or not password:
            return JSONResponse({"error": "اسم المستخدم وكلمة المرور مطلوبين"}, status_code=400)
        if len(username) < 3:
            return JSONResponse({"error": "اسم المستخدم 3 أحرف على الأقل"}, status_code=400)
        if len(password) < 6:
            return JSONResponse({"error": "كلمة المرور 6 أحرف على الأقل"}, status_code=400)
        
        result = StudentService.create_user(username, password, name)
        if "error" in result:
            return JSONResponse(result, status_code=400)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/login")
async def login(request: Request):
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        
        if not username or not password:
            return JSONResponse({"error": "مطلوب اسم المستخدم وكلمة المرور"}, status_code=400)
        
        result = StudentService.login_user(username, password)
        if "error" in result:
            return JSONResponse(result, status_code=401)
        
        ACTIVE_USERS[result["chat_id"]] = username
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        chat_id = data.get("chat_id", "")
        message = data.get("message", "").strip()
        username = data.get("username", "")
        
        if not message:
            return JSONResponse({"reply": ""})
        
        ACTIVE_USERS[chat_id] = username
        reply = await process_message(chat_id, message, username)
        
        return JSONResponse({"reply": reply, "ok": True})
    except Exception as e:
        return JSONResponse({"reply": "❌ حصل خطأ", "ok": False})

@app.get("/health")
async def health():
    return {"status": "healthy", "questions": len(ALL_QUESTIONS), "mcq": len(MCQ_QUESTIONS)}

# =========================================
# SERVE HTML FILES
# =========================================

@app.get("/", response_class=HTMLResponse)
async def auth_page():
    auth_path = BASE_DIR / "auth.html"
    if auth_path.exists():
        return auth_path.read_text(encoding="utf-8")
    return """<h1>auth.html not found</h1>"""

@app.get("/app", response_class=HTMLResponse)
async def app_page():
    app_path = BASE_DIR / "app.html"
    if app_path.exists():
        return app_path.read_text(encoding="utf-8")
    return """<h1>app.html not found</h1>"""

# =========================================
# STARTUP
# =========================================

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_sessions())
    print("🚀 Pen Platform started!")
    print(f"📊 {len(ALL_QUESTIONS)} questions loaded")
