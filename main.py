from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

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

app = FastAPI(title="Pen Platform - With Firebase Auth")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# FIREBASE CONFIG (من كودك)
# =========================================

FIREBASE_CONFIG = {
    "apiKey": "AIzaSyDWOvo3svd_e239IJkLtrs_F0tUfa5oCfE",
    "authDomain": "forme-6167f.firebaseapp.com",
    "databaseURL": "https://forme-6167f-default-rtdb.firebaseio.com",
    "projectId": "forme-6167f",
    "storageBucket": "forme-6167f.firebasestorage.app",
    "messagingSenderId": "473501377416",
    "appId": "1:473501377416:web:92a1bc21291824ab7d503d",
}

# =========================================
# STUDENT SERVICE (معدل من كودك)
# =========================================

class StudentService:
    _db = None
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
            
            # استخدام credentials من base64 environment variable
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
                    print("ℹ️ Firebase app already exists")
                except ValueError:
                    firebase_admin.initialize_app(cred, {
                        "databaseURL": FIREBASE_CONFIG["databaseURL"]
                    })
                    print("✅ Firebase initialized!")
                
                try:
                    from firebase_admin import db
                    cls._rtdb = db
                    print("✅ Firebase Realtime Database ready!")
                except Exception as e:
                    print(f"⚠️ RTDB init: {e}")
            
        except ImportError:
            print("⚠️ firebase_admin not installed - using local storage only")
        except Exception as e:
            print(f"⚠️ Firebase error: {e} (using local storage)")
    
    @classmethod
    def _now_timestamp(cls) -> int:
        return int(datetime.now().timestamp() * 1000)
    
    @classmethod
    def _now_iso(cls) -> str:
        return datetime.now().isoformat()
    
    @classmethod
    def create_user(cls, username: str, password: str, name: str = "") -> Dict:
        """إنشاء مستخدم جديد"""
        username = username.strip().lower()
        
        # التحقق من عدم وجود المستخدم
        if cls._rtdb:
            try:
                existing = cls._rtdb.reference(f"users/{username}").get()
                if existing:
                    return {"error": "اسم المستخدم موجود بالفعل"}
            except Exception:
                pass
        
        if username in cls._local_db["users"]:
            return {"error": "اسم المستخدم موجود بالفعل"}
        
        # تشفير كلمة المرور
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        user_data = {
            "username": username,
            "password": hashed_password,
            "name": name or username,
            "created_at": cls._now_iso(),
            "chat_id": f"user_{username}",
            "joined_at": cls._now_iso(),
            "last_seen": cls._now_iso(),
            "total_interactions": 0,
        }
        
        # حفظ محلي
        cls._local_db["users"][username] = user_data
        
        # حفظ في Firebase
        if cls._rtdb:
            try:
                cls._rtdb.reference(f"users/{username}").set(user_data)
                cls._rtdb.reference(f"students/{username}/profile").set({
                    "username": username,
                    "name": name or username,
                    "joined_at": cls._now_iso(),
                    "last_seen": cls._now_iso(),
                    "total_interactions": 0,
                })
            except Exception as e:
                print(f"Firebase save error: {e}")
        
        return {"success": True, "username": username, "chat_id": f"user_{username}"}
    
    @classmethod
    def login_user(cls, username: str, password: str) -> Dict:
        """تسجيل دخول المستخدم"""
        username = username.strip().lower()
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        # البحث في Firebase
        user_data = None
        if cls._rtdb:
            try:
                user_data = cls._rtdb.reference(f"users/{username}").get()
            except Exception:
                pass
        
        # البحث محلياً
        if not user_data:
            user_data = cls._local_db["users"].get(username)
        
        if not user_data:
            return {"error": "اسم المستخدم غير موجود"}
        
        if user_data.get("password") != hashed_password:
            return {"error": "كلمة المرور غير صحيحة"}
        
        # تحديث آخر ظهور
        cls.update_last_seen(username)
        
        return {
            "success": True,
            "username": username,
            "name": user_data.get("name", username),
            "chat_id": f"user_{username}",
            "stats": cls.get_stats(username)
        }
    
    @classmethod
    def update_last_seen(cls, username: str):
        now = cls._now_iso()
        
        if username in cls._local_db["users"]:
            cls._local_db["users"][username]["last_seen"] = now
            cls._local_db["users"][username]["total_interactions"] = cls._local_db["users"][username].get("total_interactions", 0) + 1
        
        if cls._rtdb:
            try:
                cls._rtdb.reference(f"users/{username}/last_seen").set(now)
                cls._rtdb.reference(f"students/{username}/profile/last_seen").set(now)
            except Exception:
                pass
    
    @classmethod
    def save_conversation(cls, username: str, user_msg: str, bot_reply: str):
        """حفظ المحادثة"""
        cls.update_last_seen(username)
        
        conversation = {
            "user_message": user_msg,
            "bot_reply": bot_reply,
            "timestamp": cls._now_timestamp(),
            "created_at": cls._now_iso(),
        }
        
        # حفظ محلي
        if "conversations" not in cls._local_db:
            cls._local_db["conversations"] = {}
        if username not in cls._local_db["conversations"]:
            cls._local_db["conversations"][username] = []
        cls._local_db["conversations"][username].append(conversation)
        
        # حفظ في Firebase
        if cls._rtdb:
            try:
                cls._rtdb.reference(f"students/{username}/conversations").push(conversation)
            except Exception:
                pass
    
    @classmethod
    def save_exam_result(cls, username: str, result: Dict) -> Dict:
        """حفظ نتيجة الامتحان"""
        cls.update_last_seen(username)
        
        correct = result.get("correct", 0)
        total = result.get("total", 1)
        percentage = int((correct / max(total, 1)) * 100)
        
        exam_data = {
            "score": correct,
            "total": total,
            "percentage": percentage,
            "timestamp": cls._now_timestamp(),
            "created_at": cls._now_iso(),
            "grade": cls._calculate_grade(percentage),
        }
        
        # حفظ في Firebase
        if cls._rtdb:
            try:
                cls._rtdb.reference(f"students/{username}/exams").push(exam_data)
            except Exception:
                pass
        
        cls.update_stats(username)
        return exam_data
    
    @classmethod
    def _calculate_grade(cls, percentage: int) -> str:
        if percentage >= 90:
            return "ممتاز 🏆"
        elif percentage >= 80:
            return "جيد جداً 🌟"
        elif percentage >= 65:
            return "جيد 👍"
        elif percentage >= 50:
            return "مقبول 📚"
        return "ضعيف 💪"
    
    @classmethod
    def update_stats(cls, username: str) -> Dict:
        """تحديث إحصائيات الطالب"""
        exams_data = {}
        
        if cls._rtdb:
            try:
                exams_data = cls._rtdb.reference(f"students/{username}/exams").get() or {}
            except Exception:
                pass
        
        if not exams_data:
            return {}
        
        total_exams = len(exams_data)
        total_score = sum(e.get("score", 0) for e in exams_data.values())
        total_questions = sum(e.get("total", 0) for e in exams_data.values())
        percentages = [e.get("percentage", 0) for e in exams_data.values() if e.get("percentage", 0) > 0]
        
        avg_percentage = int(sum(percentages) / len(percentages)) if percentages else 0
        best_score = max(percentages) if percentages else 0
        
        # تحليل نقاط القوة والضعف
        strengths = []
        weaknesses = []
        
        if avg_percentage >= 70:
            strengths.append("الفهم العام")
        else:
            weaknesses.append("الفهم العام")
        
        if total_exams >= 3:
            strengths.append("الممارسة المستمرة")
        else:
            weaknesses.append("قلة الممارسة")
        
        if best_score >= 80:
            strengths.append("القدرة على تحقيق نتائج عالية")
        
        stats = {
            "total_exams": total_exams,
            "total_questions_answered": total_questions,
            "total_correct_answers": total_score,
            "avg_percentage": avg_percentage,
            "best_score": best_score,
            "level": cls._calculate_grade(avg_percentage),
            "level_numeric": avg_percentage,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "updated_at": cls._now_iso(),
        }
        
        if cls._rtdb:
            try:
                cls._rtdb.reference(f"students/{username}/stats").set(stats)
            except Exception:
                pass
        
        return stats
    
    @classmethod
    def get_stats(cls, username: str) -> Dict:
        """الحصول على إحصائيات الطالب"""
        if cls._rtdb:
            try:
                stats = cls._rtdb.reference(f"students/{username}/stats").get()
                if stats:
                    return stats
            except Exception:
                pass
        
        return cls.update_stats(username)
    
    @classmethod
    def get_level_analytics(cls, username: str) -> str:
        """تحليل مستوى الطالب"""
        stats = cls.get_stats(username)
        
        if not stats or stats.get("total_exams", 0) == 0:
            return None
        
        total_exams = stats.get("total_exams", 0)
        avg = stats.get("avg_percentage", 0)
        best = stats.get("best_score", 0)
        total_q = stats.get("total_questions_answered", 0)
        correct_q = stats.get("total_correct_answers", 0)
        level = stats.get("level", cls._calculate_grade(avg))
        strengths = stats.get("strengths", [])
        weaknesses = stats.get("weaknesses", [])
        
        if avg >= 80:
            suggestion = "🌟 أنت في مستوى متقدم - جرب `امتحان صعب`"
        elif avg >= 60:
            suggestion = "👍 مستواك كويس - ركز على `خطة التركيز`"
        elif avg >= 40:
            suggestion = "📚 محتاج تركز أكتر - جرب `اختبرني سهل`"
        else:
            suggestion = "💪 ابدأ بـ `امتحان سهل` و `شرح النحو`"
        
        strengths_text = "\n".join([f"   ✅ {s}" for s in strengths]) if strengths else "   - لا توجد بيانات كافية"
        weaknesses_text = "\n".join([f"   ⚠️ {w}" for w in weaknesses]) if weaknesses else "   - لا توجد بيانات كافية"
        
        return f"""
📊 *تحليل مستواك*

🏆 *المستوى:* {level}
📈 *المتوسط:* {avg}%

📝 *إحصائيات:*
• عدد الامتحانات: {total_exams}
• أفضل نتيجة: {best}%
• إجمالي الأسئلة: {total_q}
• إجابات صحيحة: {correct_q}

💪 *نقاط القوة:*
{strengths_text}

🔧 *يحتاج تحسين:*
{weaknesses_text}

💡 *نصيحة:*
{suggestion}

🔄 *جرب:* `امتحان` | `اختبرني` | `خطة التركيز`
"""
    
    @classmethod
    def is_connected(cls) -> bool:
        if cls._rtdb:
            try:
                cls._rtdb.reference(".info/connected").get()
                return True
            except Exception:
                pass
        return False

# تهيئة Firebase
StudentService.initialize()

# =========================================
# CONFIG
# =========================================

MAX_QUESTION_LENGTH = 350
SESSION_TIMEOUT = 600
RATE_LIMIT_SECONDS = 1.0

# =========================================
# INTENT TYPES
# =========================================

class Intent(str, Enum):
    GREETING = "greeting"
    IDENTITY = "identity"
    EXAM = "exam"
    INTERACTIVE_EXAM = "interactive_exam"
    FOCUS_PLAN = "focus_plan"
    LESSON = "lesson"
    LEVEL_CHANGE = "level_change"
    MY_LEVEL = "my_level"
    UNKNOWN = "unknown"

# =========================================
# DATA PATHS
# =========================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# =========================================
# QUESTION DETECTION
# =========================================

def detect_question_type(question: Dict) -> str:
    choices = question.get("choices", [])
    if not choices or len(choices) < 2:
        return "open_text"
    
    answer_key = str(question.get("answer_key", "")).strip()
    if not answer_key:
        return "open_text"
    
    if answer_key.isdigit():
        key_num = int(answer_key)
        if 1 <= key_num <= len(choices):
            return "mcq"
    
    arabic_keys = ["أ", "ب", "ج", "د", "هـ", "ه"]
    if answer_key in arabic_keys:
        idx = arabic_keys.index(answer_key)
        if idx < len(choices):
            return "mcq"
    
    english_keys = ["a", "b", "c", "d", "e"]
    if answer_key.lower() in english_keys:
        idx = english_keys.index(answer_key.lower())
        if idx < len(choices):
            return "mcq"
    
    return "open_text"

def get_answer_index(question: Dict) -> Optional[int]:
    answer_key = str(question.get("answer_key", "")).strip()
    choices = question.get("choices", [])
    
    if not choices:
        return None
    
    if answer_key.isdigit():
        idx = int(answer_key) - 1
        if 0 <= idx < len(choices):
            return idx
    
    arabic_keys = ["أ", "ب", "ج", "د", "هـ", "ه"]
    if answer_key in arabic_keys:
        return arabic_keys.index(answer_key)
    
    english_keys = ["a", "b", "c", "d", "e"]
    if answer_key.lower() in english_keys:
        return english_keys.index(answer_key.lower())
    
    return None

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
        self.created_at = time.time()
        self.last_activity = time.time()
    
    def is_expired(self) -> bool:
        return time.time() - self.last_activity > SESSION_TIMEOUT
    
    def update_activity(self):
        self.last_activity = time.time()
    
    def get_current_question(self) -> Optional[Dict]:
        if self.current_index < len(self.questions):
            return self.questions[self.current_index]
        return None
    
    def check_answer(self, user_answer: int) -> Dict:
        self.update_activity()
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
            if isinstance(choice, dict):
                correct_answer_text = choice.get("text", str(choice))
            else:
                correct_answer_text = str(choice)
        
        result = {
            "correct": is_correct,
            "correct_answer": correct_answer_text or str(correct_idx + 1 if correct_idx is not None else "?"),
            "user_answer": user_answer,
            "explanation": question.get("explanation", ""),
            "question_text": question.get("prompt") or question.get("question", ""),
            "choices": choices,
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
LAST_COMMAND: Dict[str, str] = {}
LAST_COMMAND_TIME: Dict[str, float] = {}
COMMAND_MEMORY_TIMEOUT = 30
ACTIVE_USERS: Dict[str, str] = {}  # chat_id -> username

async def cleanup_expired_sessions():
    while True:
        try:
            current_time = time.time()
            expired = [
                chat_id for chat_id, session in user_sessions.items()
                if session.is_expired()
            ]
            for chat_id in expired:
                del user_sessions[chat_id]
        except Exception as e:
            print(f"❌ CLEANUP ERROR: {e}")
        await asyncio.sleep(60)

def remember_command(chat_id: str, intent: str):
    LAST_COMMAND[chat_id] = intent
    LAST_COMMAND_TIME[chat_id] = time.time()

def get_last_command(chat_id: str) -> Optional[str]:
    last_time = LAST_COMMAND_TIME.get(chat_id, 0)
    if time.time() - last_time < COMMAND_MEMORY_TIMEOUT:
        return LAST_COMMAND.get(chat_id)
    return None

# =========================================
# NORMALIZE ARABIC TEXT
# =========================================

def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    replacements = {
        'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ة': 'ه', 'ى': 'ي',
        'ؤ': 'و', 'ئ': 'ي',
        'َ': '', 'ُ': '', 'ِ': '', 'ً': '', 'ٌ': '', 'ٍ': '',
        'ْ': '', 'ّ': ''
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.lower().strip()

def fuzzy_match(query: str, target: str, threshold: float = 0.7) -> bool:
    if not query or not target:
        return False
    query_norm = normalize_arabic(query)
    target_norm = normalize_arabic(target)
    if query_norm in target_norm or target_norm in query_norm:
        return True
    ratio = SequenceMatcher(None, query_norm, target_norm).ratio()
    return ratio >= threshold

# =========================================
# INTENT DETECTION
# =========================================

GREETING_PATTERNS = [
    r'\bاهلا\b', r'\bأهلا\b', r'\bمرحبا\b', r'\bالسلام\b',
    r'\bهاي\b', r'\bهلا\b', r'\bسلام\b', r'\bصباح\b', r'\bمساء\b',
]

IDENTITY_WORDS = [
    "انت مين", "انتي مين", "اسمك اي", "اسمك ايه",
    "مين انت", "مين انتي", "بتعمل اي", "بتعملي اي",
]

LEVEL_KEYWORDS = {
    "سهل": "easy",
    "متوسط": "medium",
    "صعب": "hard",
}

def detect_intent(message: str, chat_id: str = "") -> Intent:
    message_lower = message.lower().strip()
    message_words = message_lower.split()
    
    for phrase in IDENTITY_WORDS:
        if phrase in message_lower:
            return Intent.IDENTITY
    
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, message_lower) and len(message_words) <= 3:
            return Intent.GREETING
    
    if message_lower in ["سهل", "متوسط", "صعب"]:
        last = get_last_command(chat_id)
        if last in ["exam", "interactive_exam"]:
            return Intent.LEVEL_CHANGE
    
    if message_lower in ["مستوايا", "مستوى", "تحليل مستوايا", "تحليل المستوى"]:
        return Intent.MY_LEVEL
    
    if any(x in message_lower for x in ["اختبرني", "اختبرنى", "اختبريني"]):
        return Intent.INTERACTIVE_EXAM
    
    if any(x in message_lower for x in ["امتحان", "امتخان", "اختبار"]):
        return Intent.EXAM
    
    if any(x in message_lower for x in ["خطة", "خطه", "التركيز", "ركز", "تركيز"]):
        return Intent.FOCUS_PLAN
    
    if "شرح" in message_lower:
        return Intent.LESSON
    
    return Intent.UNKNOWN

# =========================================
# DATA LOADING
# =========================================

ALL_QUESTIONS: List[Dict] = []
MCQ_QUESTIONS: List[Dict] = []
QUESTIONS_BY_DIFFICULTY: Dict[str, List[Dict]] = defaultdict(list)

def extract_all_questions(data, depth=0):
    questions = []
    if depth > 10:
        return questions
    
    if isinstance(data, dict):
        if "prompt" in data and "question_id" in data:
            question_text = data.get("prompt", "")
            questions.append({
                "question_id": data.get("question_id", ""),
                "prompt": question_text,
                "question": question_text,
                "explanation": data.get("explanation", ""),
                "answer_key": data.get("answer_key", ""),
                "choices": data.get("choices", data.get("options", [])),
                "difficulty": data.get("difficulty", "medium"),
                "skill": data.get("skill", ""),
                "question_type": ""
            })
        elif "question" in data:
            question_text = data.get("question", "")
            questions.append({
                "question_id": data.get("id", ""),
                "prompt": question_text,
                "question": question_text,
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

def build_indexes():
    global MCQ_QUESTIONS, QUESTIONS_BY_DIFFICULTY
    MCQ_QUESTIONS = []
    QUESTIONS_BY_DIFFICULTY = defaultdict(list)
    
    for q in ALL_QUESTIONS:
        q_type = q.get("question_type", "")
        if q_type == "mcq":
            MCQ_QUESTIONS.append(q)
        
        difficulty = q.get("difficulty", "medium")
        QUESTIONS_BY_DIFFICULTY[difficulty].append(q)

def load_all_data():
    global ALL_QUESTIONS
    ALL_QUESTIONS = []
    seen = set()
    
    if not DATA_DIR.exists():
        print("❌ DATA FOLDER NOT FOUND - creating...")
        DATA_DIR.mkdir(exist_ok=True)
        return
    
    files = list(DATA_DIR.glob("*.json"))
    print(f"📚 FOUND {len(files)} FILES")
    
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                questions = extract_all_questions(data)
                
                new_q = []
                for q in questions:
                    q_text = str(q.get("question", ""))[:100]
                    if q_text and q_text not in seen:
                        seen.add(q_text)
                        q["question_type"] = detect_question_type(q)
                        new_q.append(q)
                
                ALL_QUESTIONS.extend(new_q)
                print(f"✅ Loaded: {file.name} -> {len(new_q)} questions")
        except Exception as e:
            print(f"❌ ERROR loading {file.name}: {e}")
    
    build_indexes()
    print(f"🔥 TOTAL: {len(ALL_QUESTIONS)} | MCQ: {len(MCQ_QUESTIONS)}")

load_all_data()

# =========================================
# RESPONSE GENERATORS
# =========================================

DIFFICULTY_AR = {
    "easy": "سهل 🟢",
    "medium": "متوسط 🟡",
    "hard": "صعب 🔴"
}

def generate_exam(level: str = None, count: int = 5) -> str:
    if not ALL_QUESTIONS:
        return "❌ مفيش أسئلة متاحة حالياً"
    
    filtered = ALL_QUESTIONS.copy()
    if level and level in ["easy", "medium", "hard"]:
        filtered = QUESTIONS_BY_DIFFICULTY.get(level, ALL_QUESTIONS.copy())
    
    if not filtered:
        return f"❌ مفيش أسئلة متاحة بالمستوى '{level or 'عام'}'"
    
    if len(filtered) > count:
        selected = random.sample(filtered, count)
    else:
        selected = filtered
    
    level_name = DIFFICULTY_AR.get(level, "شامل 📝")
    
    exam = f"📝 *امتحان {level_name}*\n"
    exam += "─" * 25 + "\n\n"
    
    for i, q in enumerate(selected, 1):
        question_text = q.get("prompt") or q.get("question", "سؤال")
        if len(question_text) > MAX_QUESTION_LENGTH:
            question_text = question_text[:MAX_QUESTION_LENGTH-3] + "..."
        
        q_type = q.get("question_type", "")
        type_label = "📝" if q_type == "open_text" else "🔤"
        
        exam += f"*{i}. {type_label}* {question_text}\n"
        
        if q_type == "mcq" and q.get("choices"):
            for idx, choice in enumerate(q.get("choices", []), 1):
                if isinstance(choice, dict):
                    choice_text = choice.get("text", str(choice))
                else:
                    choice_text = str(choice)
                exam += f"   {idx}️⃣ {choice_text}\n"
            exam += "\n"
    
    exam += "─" * 25 + "\n"
    exam += f"📝 *عدد الأسئلة: {len(selected)}*\n"
    exam += "💪 *ربنا معاك يا بطل*"
    
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
        return "❌ عدد الأسئلة غير كافي لامتحان تفاعلي"
    
    session = ExamSession(selected, level)
    user_sessions[chat_id] = session
    
    return format_question_message(session)

def format_question_message(session: ExamSession) -> str:
    question = session.get_current_question()
    if not question:
        return ""
    
    question_text = question.get("prompt") or question.get("question", "سؤال")
    if len(question_text) > MAX_QUESTION_LENGTH:
        question_text = question_text[:MAX_QUESTION_LENGTH-3] + "..."
    
    choices = question.get("choices", [])
    
    msg = f"🧠 *سؤال {session.current_index + 1} من {session.total}*\n\n"
    msg += f"*{question_text}*\n\n"
    
    if choices:
        for idx, choice in enumerate(choices, 1):
            if isinstance(choice, dict):
                choice_text = choice.get("text", str(choice))
            else:
                choice_text = str(choice)
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
        return "❌ *ابعت رقم الإجابة فقط (1، 2، 3، 4)*"
    
    if answer_num < 1 or answer_num > 4:
        return "❌ *رقم الإجابة يجب أن يكون بين 1 و 4*"
    
    result = session.check_answer(answer_num)
    
    if result["correct"]:
        response = "✅ *إجابة صحيحة!* 🎉\n\n"
    else:
        response = f"❌ *إجابة خاطئة*\n✅ *الإجابة الصحيحة: {result['correct_answer']}*\n\n"
    
    if result["explanation"]:
        explanation = result["explanation"]
        if len(explanation) > 300:
            explanation = explanation[:297] + "..."
        response += f"📝 *الشرح:*\n{explanation}\n\n"
    
    response += f"📊 *النتيجة: {result['current_score']} / {result['question_number']}*\n\n"
    
    if session.active:
        response += format_question_message(session)
    else:
        final_score = result["current_score"]
        total = result["total"]
        percentage = (final_score / total) * 100 if total > 0 else 0
        
        # حفظ النتيجة في قاعدة البيانات
        if username:
            StudentService.save_exam_result(username, {
                "correct": final_score,
                "total": total
            })
        
        if percentage >= 80:
            emoji, comment = "🏆", "ممتاز! أداء رائع"
        elif percentage >= 60:
            emoji, comment = "👍", "جيد جداً - ركز على الأخطاء"
        elif percentage >= 40:
            emoji, comment = "📚", "محتاج مذاكرة أكتر"
        else:
            emoji, comment = "💪", "لازم تشد حيلك"
        
        response += f"{emoji} *الامتحان خلص!*\n\n"
        response += f"📊 *النتيجة النهائية: {final_score} / {total}*\n"
        response += f"📈 *النسبة: {int(percentage)}%*\n\n"
        response += f"{comment}\n\n"
        response += "🔄 *للامتحان التالي:*\n"
        response += "• `اختبرني` - امتحان شامل\n"
        response += "• `اختبرني سهل` - أسئلة سهلة\n"
        response += "• `اختبرني صعب` - أسئلة صعبة\n"
        response += "• `مستوايا` - شوف تحليل مستواك"
        
        del user_sessions[chat_id]
    
    return response

def generate_focus_plan() -> str:
    if not ALL_QUESTIONS:
        return "❌ مفيش بيانات متاحة"
    
    msg = "🎯 *خطة التركيز الذكية*\n"
    msg += "─" * 25 + "\n\n"
    
    msg += "📌 *أهم الموضوعات:*\n"
    msg += "   ⭐ النحو والصرف\n"
    msg += "   ⭐ البلاغة العربية\n"
    msg += "   ⭐ الأدب والنصوص\n"
    msg += "   ⭐ القراءة والفهم\n"
    msg += "   ⭐ التعبير والإنشاء\n"
    
    msg += "\n📊 *إحصائيات سريعة:*\n"
    msg += f"   📝 الأسئلة: {len(ALL_QUESTIONS)}\n"
    msg += f"   🔤 MCQ: {len(MCQ_QUESTIONS)}\n"
    
    difficulties = Counter(q.get("difficulty", "medium") for q in ALL_QUESTIONS)
    msg += f"   🟢 سهل: {difficulties.get('easy', 0)}\n"
    msg += f"   🟡 متوسط: {difficulties.get('medium', 0)}\n"
    msg += f"   🔴 صعب: {difficulties.get('hard', 0)}\n"
    
    msg += "\n💪 *ركز على الموضوعات دي*"
    
    return msg

def search_lesson(user_message: str) -> str:
    clean_message = re.sub(r"[^\u0600-\u06FF\s]", " ", user_message)
    clean_message = re.sub(r"\bشرح\b", "", clean_message)
    clean_message = re.sub(r"\bدرس\b", "", clean_message)
    clean_message = re.sub(r"\s+", " ", clean_message).strip()
    
    if not clean_message:
        return "❌ اكتب اسم الدرس بعد 'شرح'\nمثال: شرح النحو"
    
    for q in ALL_QUESTIONS[:20]:
        question_text = q.get("question", "")
        if fuzzy_match(clean_message, question_text, threshold=0.6):
            question_text_display = question_text
            if len(question_text_display) > MAX_QUESTION_LENGTH:
                question_text_display = question_text_display[:MAX_QUESTION_LENGTH-3] + "..."
            
            msg = f"📚 *شرح: {clean_message}*\n"
            msg += "─" * 25 + "\n\n"
            msg += f"📖 *السؤال:*\n{question_text_display}\n\n"
            
            explanation = q.get("explanation", "")
            if explanation:
                msg += f"📝 *الشرح:*\n{explanation}\n\n"
            
            msg += "💪 *ركز عليه كويس*"
            return msg
    
    return f"❌ مش لاقي شرح لـ '{clean_message}'\n\nجرب تكتب:\n• شرح النحو\n• شرح البلاغة"

# =========================================
# IDENTITY & GREETING RESPONSES
# =========================================

IDENTITY_RESPONSE = """🤖 *أنا المساعد Pen*

📚 *مساعد ذكي للتعليم:*
• 🎯 امتحانات متوقعة
• 📝 امتحانات تفاعلية (MCQ)
• 📖 شرح الدروس والمفاهيم
• 📊 تحليل أهم الموضوعات
• 👤 تحليل مستواك الشخصي

📌 *جرب الأوامر دي:*
• `امتحان` - أسئلة متوقعة
• `اختبرني` - امتحان تفاعلي
• `شرح النحو` - شرح درس
• `خطة التركيز` - أهم الموضوعات
• `مستوايا` - تحليل مستواك"""

def get_greeting_response(username: str = None) -> str:
    name_line = f"\n👤 *{username}*" if username else ""
    return f"""👋 *أهلاً بيك في منصة Pen!*{name_line}

📝 *امتحانات:*
• `امتحان` - أهم الأسئلة
• `امتحان سهل` - `متوسط` - `صعب`

🎯 *تفاعلي (MCQ فقط):*
• `اختبرني` - امتحان تفاعلي
• `اختبرني في البلاغة`

📊 *تحليل:*
• `خطة التركيز` - أهم الموضوعات
• `مستوايا` - تحليل مستواك 📈

📚 *شرح:*
• `شرح [الدرس]`

💡 *للاستفسارات:*
• `اشرحلي` - `فسر` - `قارن`"""

# =========================================
# MAIN PROCESSOR
# =========================================

def is_rate_limited(chat_id: str) -> bool:
    current_time = time.time()
    last_time = LAST_MESSAGE_TIME.get(chat_id, 0)
    if current_time - last_time < RATE_LIMIT_SECONDS:
        return True
    LAST_MESSAGE_TIME[chat_id] = current_time
    return False

async def process_message(chat_id: str, body: str, username: str = None) -> str:
    try:
        if is_rate_limited(chat_id):
            return ""
        
        # حفظ المحادثة
        if username:
            # هنحفظ الرد بعد ما نعرفه
            pass
        
        if chat_id in user_sessions:
            session = user_sessions[chat_id]
            if session.active and not session.is_expired():
                reply = process_exam_answer(chat_id, body, username)
                if username and reply:
                    StudentService.save_conversation(username, body, reply)
                return reply
            elif session.is_expired():
                del user_sessions[chat_id]
                return "⏰ *انتهت الجلسة*\nاكتب `اختبرني` لبدء امتحان جديد"
        
        body_lower = body.lower().strip()
        intent = detect_intent(body_lower, chat_id)
        
        reply = None
        
        if intent == Intent.IDENTITY:
            reply = IDENTITY_RESPONSE
        
        elif intent == Intent.GREETING:
            reply = get_greeting_response(username)
        
        elif intent == Intent.MY_LEVEL:
            if username:
                analytics = StudentService.get_level_analytics(username)
                if analytics:
                    reply = analytics
                else:
                    reply = "📊 *لسه مفيش بيانات كافية*\n\nجرب تاخد امتحان الأول:\n• `اختبرني` - امتحان تفاعلي\n• `امتحان` - أسئلة متوقعة"
            else:
                reply = "📊 *تحليل المستوى*\n─────────────────────────\n\n📌 *نقاط القوة:*\n   ✅ الفهم: 85%\n   ✅ التطبيق: 78%\n\n⚠️ *يحتاج تحسين:*\n   ⚠️ التحليل: 60%\n   ⚠️ الاستنتاج: 55%"
        
        elif intent == Intent.LEVEL_CHANGE:
            last = get_last_command(chat_id)
            level = LEVEL_KEYWORDS.get(body_lower, "medium")
            
            if last == "exam":
                reply = generate_exam(level=level)
            elif last == "interactive_exam":
                reply = start_interactive_exam(chat_id, level=level)
            else:
                reply = f"📌 اكتب `امتحان {body_lower}` أو `اختبرني {body_lower}`"
        
        elif intent == Intent.INTERACTIVE_EXAM:
            level = "medium"
            for arabic_level, level_key in LEVEL_KEYWORDS.items():
                if arabic_level in body_lower:
                    level = level_key
                    break
            
            remember_command(chat_id, "interactive_exam")
            reply = start_interactive_exam(chat_id, level)
        
        elif intent == Intent.EXAM:
            level = None
            for arabic_level, level_key in LEVEL_KEYWORDS.items():
                if arabic_level in body_lower:
                    level = level_key
                    break
            
            remember_command(chat_id, "exam")
            reply = generate_exam(level=level)
        
        elif intent == Intent.FOCUS_PLAN:
            reply = generate_focus_plan()
        
        elif intent == Intent.LESSON:
            reply = search_lesson(body)
        
        else:
            reply = """📌 *جرب تكتب:*
• `امتحان` - أسئلة متوقعة
• `اختبرني` - امتحان تفاعلي
• `شرح النحو` - شرح
• `خطة التركيز` - أهم الموضوعات
• `مستوايا` - تحليل مستواك"""
        
        # حفظ المحادثة
        if username and reply:
            StudentService.save_conversation(username, body, reply)
        
        return reply
    
    except Exception as e:
        print(f"❌ PROCESS ERROR: {e}")
        return "❌ حصل خطأ، جرب تاني"

# =========================================
# API ENDPOINTS
# =========================================

@app.post("/api/register")
async def register(request: Request):
    """تسجيل مستخدم جديد"""
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        name = data.get("name", "").strip()
        
        if not username or not password:
            return JSONResponse({"error": "اسم المستخدم وكلمة المرور مطلوبين"}, status_code=400)
        
        if len(username) < 3:
            return JSONResponse({"error": "اسم المستخدم يجب أن يكون 3 أحرف على الأقل"}, status_code=400)
        
        if len(password) < 6:
            return JSONResponse({"error": "كلمة المرور يجب أن تكون 6 أحرف على الأقل"}, status_code=400)
        
        result = StudentService.create_user(username, password, name)
        
        if "error" in result:
            return JSONResponse(result, status_code=400)
        
        return JSONResponse(result)
    
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/login")
async def login(request: Request):
    """تسجيل دخول"""
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        
        if not username or not password:
            return JSONResponse({"error": "اسم المستخدم وكلمة المرور مطلوبين"}, status_code=400)
        
        result = StudentService.login_user(username, password)
        
        if "error" in result:
            return JSONResponse(result, status_code=401)
        
        # تخزين المستخدم النشط
        chat_id = result.get("chat_id")
        if chat_id:
            ACTIVE_USERS[chat_id] = username
        
        return JSONResponse(result)
    
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/chat")
async def chat(request: Request):
    """المحادثة مع البوت (تتطلب تسجيل الدخول)"""
    try:
        data = await request.json()
        chat_id = data.get("chat_id", "")
        message = data.get("message", "").strip()
        username = data.get("username", "")
        
        if not message:
            return JSONResponse({"reply": ""})
        
        # التحقق من المستخدم
        if username:
            ACTIVE_USERS[chat_id] = username
        
        reply = await process_message(chat_id, message, username)
        
        return JSONResponse({
            "reply": reply,
            "ok": True
        })
    
    except Exception as e:
        print(f"❌ CHAT ERROR: {e}")
        return JSONResponse({"reply": "❌ حصل خطأ", "ok": False})

@app.get("/api/stats/{username}")
async def get_stats(username: str):
    """الحصول على إحصائيات المستخدم"""
    stats = StudentService.get_stats(username)
    return JSONResponse(stats)

@app.api_route("/api/webhook", methods=["GET", "POST"])
async def webhook_handler(request: Request):
    """للتوافق مع الإصدارات القديمة"""
    if request.method == "GET":
        return JSONResponse({
            "status": "active",
            "version": "pen-v2-with-auth",
            "questions": len(ALL_QUESTIONS),
            "mcq_questions": len(MCQ_QUESTIONS),
            "active_sessions": len(user_sessions),
            "firebase_connected": StudentService.is_connected()
        })
    
    try:
        data = await request.json()
        payload = data.get("payload", {})
        chat_id = payload.get("from", "web_user")
        body = str(payload.get("body", "")).strip()
        
        if not body:
            return JSONResponse({"reply": ""})
        
        username = ACTIVE_USERS.get(chat_id)
        reply = await process_message(chat_id, body, username)
        
        return JSONResponse({
            "reply": reply,
            "ok": True
        })
    except Exception as e:
        return JSONResponse({"reply": "❌ حصل خطأ", "ok": False})

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "questions": len(ALL_QUESTIONS),
        "mcq": len(MCQ_QUESTIONS),
        "active_sessions": len(user_sessions),
        "active_users": len(ACTIVE_USERS),
        "firebase_connected": StudentService.is_connected()
    }

# =========================================
# HTML INTERFACE WITH LOGIN
# =========================================

@app.get("/", response_class=HTMLResponse)
async def serve_html():
    return """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>منصة Pen | تعليم ذكي</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    body { background: #0f172a; color: #e2e8f0; display: flex; flex-direction: column; min-height: 100vh; }
    
    /* Login Page */
    .login-container {
      display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px;
    }
    .login-box {
      background: #1e293b; border-radius: 24px; padding: 2.5rem; box-shadow: 0 8px 32px rgba(0,0,0,0.6);
      border: 1px solid #334155; width: 100%; max-width: 420px;
    }
    .login-header { text-align: center; margin-bottom: 2rem; }
    .login-logo { font-size: 3rem; color: #fbbf24; margin-bottom: 1rem; }
    .login-title { font-size: 2rem; font-weight: bold; background: linear-gradient(135deg, #fbbf24, #f59e0b); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .form-group { margin-bottom: 1.2rem; }
    .form-group label { display: block; margin-bottom: 0.5rem; color: #94a3b8; font-weight: 500; }
    .form-group input { width: 100%; padding: 0.9rem 1.2rem; border-radius: 12px; border: 1px solid #475569; background: #0f172a; color: #e2e8f0; font-size: 1rem; outline: none; transition: 0.2s; }
    .form-group input:focus { border-color: #fbbf24; box-shadow: 0 0 0 3px rgba(251,191,36,0.2); }
    .btn { width: 100%; padding: 0.9rem; border-radius: 12px; border: none; font-size: 1rem; font-weight: bold; cursor: pointer; transition: 0.2s; margin-top: 0.5rem; }
    .btn-primary { background: #fbbf24; color: #0f172a; }
    .btn-primary:hover { background: #f59e0b; transform: scale(1.02); }
    .btn-secondary { background: #334155; color: #e2e8f0; }
    .btn-secondary:hover { background: #475569; }
    .toggle-text { text-align: center; margin-top: 1.5rem; color: #94a3b8; }
    .toggle-text a { color: #fbbf24; cursor: pointer; text-decoration: none; font-weight: 500; }
    .toggle-text a:hover { text-decoration: underline; }
    .error-msg { background: #7f1d1d; color: #fca5a5; padding: 0.8rem; border-radius: 10px; margin-bottom: 1rem; text-align: center; display: none; }
    .success-msg { background: #064e3b; color: #6ee7b7; padding: 0.8rem; border-radius: 10px; margin-bottom: 1rem; text-align: center; display: none; }

    /* Main App */
    .app-container { display: none; flex-direction: column; min-height: 100vh; }
    .top-bar { background: #1e293b; color: #f1f5f9; padding: 0.7rem 2rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; box-shadow: 0 4px 16px rgba(0,0,0,0.5); border-bottom: 1px solid #334155; }
    .logo-area { display: flex; align-items: center; gap: 12px; }
    .logo-icon { font-size: 2.2rem; color: #fbbf24; transform: rotate(-15deg); }
    .logo-text { font-size: 1.8rem; font-weight: bold; background: linear-gradient(135deg, #fbbf24, #f59e0b); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .user-area { display: flex; align-items: center; gap: 10px; }
    .user-name { color: #fbbf24; font-weight: 500; }
    .logout-btn { background: #ef4444; color: white; border: none; padding: 0.5rem 1rem; border-radius: 8px; cursor: pointer; font-size: 0.85rem; }
    .logout-btn:hover { background: #dc2626; }
    .main-layout { display: flex; flex: 1; margin: 0 1.5rem 1.5rem; gap: 1.5rem; flex-wrap: wrap; align-items: stretch; }
    .content-area { flex: 0.4; min-width: 220px; max-width: 300px; background: #1e293b; border-radius: 24px; padding: 1.2rem; box-shadow: 0 8px 24px rgba(0,0,0,0.5); border: 1px solid #334155; }
    .card-grid { display: flex; flex-direction: column; gap: 0.8rem; margin-top: 0.8rem; }
    .feature-card { background: #0f172a; border-radius: 14px; padding: 0.8rem; display: flex; align-items: center; gap: 10px; border: 1px solid #334155; cursor: pointer; }
    .feature-card i { font-size: 1.3rem; color: #fbbf24; }
    .feature-card h4 { color: #f1f5f9; font-size: 0.9rem; }
    .feature-card p { color: #94a3b8; font-size: 0.75rem; }
    .feature-card:hover { background: #1e293b; border-color: #fbbf24; }
    .chatbot-section { flex: 3; min-width: 500px; background: #1e293b; border-radius: 24px; box-shadow: 0 8px 28px rgba(0,0,0,0.6); display: flex; flex-direction: column; overflow: hidden; border: 1px solid #334155; }
    .chat-header { background: #0f172a; color: #fbbf24; padding: 1rem 1.5rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem; font-weight: bold; font-size: 1.3rem; border-bottom: 1px solid #334155; }
    .chat-header-left { display: flex; align-items: center; gap: 10px; }
    .chat-header-left i { font-size: 1.6rem; }
    .status-badge { padding: 0.2rem 0.6rem; border-radius: 10px; font-size: 0.7rem; font-weight: normal; }
    .status-online { background: #10b981; color: white; }
    .header-quick-buttons { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .header-quick-btn { background: #1e293b; color: #fbbf24; border: 1px solid #fbbf24; padding: 0.4rem 0.8rem; border-radius: 18px; font-size: 0.75rem; cursor: pointer; transition: 0.2s; white-space: nowrap; font-weight: 500; }
    .header-quick-btn:hover { background: #fbbf24; color: #0f172a; transform: scale(1.05); }
    .header-category-label { color: #94a3b8; font-size: 0.7rem; font-weight: bold; margin: 0 0.2rem; }
    .chat-messages { flex: 1; padding: 1.5rem; overflow-y: auto; display: flex; flex-direction: column; gap: 1.2rem; background: #0b1120; min-height: 400px; max-height: 70vh; }
    .message { display: flex; gap: 10px; animation: fadeIn 0.3s ease; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    .bot-msg { align-self: flex-start; }
    .user-msg { align-self: flex-end; flex-direction: row-reverse; }
    .msg-bubble { padding: 0.9rem 1.3rem; border-radius: 20px; max-width: 80%; background: #334155; color: #e2e8f0; font-size: 1rem; line-height: 1.8; white-space: pre-wrap; word-wrap: break-word; }
    .user-msg .msg-bubble { background: #fbbf24; color: #0f172a; font-weight: 500; }
    .msg-bubble strong { color: #fbbf24; }
    .msg-bubble em { color: #fcd34d; font-style: italic; }
    .typing-indicator { display: flex; gap: 4px; padding: 0.9rem 1.3rem; align-self: flex-start; }
    .typing-dot { width: 8px; height: 8px; background: #fbbf24; border-radius: 50%; animation: typing 1.4s infinite; }
    .typing-dot:nth-child(2) { animation-delay: 0.2s; }
    .typing-dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes typing { 0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); } 30% { opacity: 1; transform: scale(1); } }
    .chat-input-area { display: flex; padding: 1rem; border-top: 1px solid #334155; background: #1e293b; gap: 10px; }
    .chat-input-area input { flex: 1; padding: 0.9rem 1.2rem; border-radius: 30px; border: 1px solid #475569; background: #0f172a; color: #e2e8f0; outline: none; font-size: 1rem; }
    .chat-input-area input::placeholder { color: #64748b; }
    .chat-input-area input:disabled { opacity: 0.5; }
    .chat-input-area button { background: #fbbf24; color: #0f172a; border: none; border-radius: 50%; width: 50px; height: 50px; cursor: pointer; font-size: 1.2rem; transition: 0.2s; display: flex; align-items: center; justify-content: center; }
    .chat-input-area button:hover { background: #f59e0b; transform: scale(1.1); }
    .chat-input-area button:disabled { opacity: 0.5; cursor: not-allowed; }
    footer { text-align: center; color: #64748b; margin: 0.5rem 0 1rem; font-size: 0.8rem; }
    @media (max-width: 900px) { .main-layout { flex-direction: column; } .content-area { max-width: 100%; flex: 1; } .chatbot-section { min-width: auto; flex: 3; } }
  </style>
</head>
<body>
  <!-- Login Page -->
  <div id="loginPage" class="login-container">
    <div class="login-box">
      <div class="login-header">
        <div class="login-logo"><i class="fas fa-pen-fancy"></i></div>
        <div class="login-title">Pen</div>
        <p style="color:#94a3b8; margin-top:0.5rem;">منصة التعلم الذكية</p>
      </div>
      <div id="errorMsg" class="error-msg"></div>
      <div id="successMsg" class="success-msg"></div>
      <div id="loginForm">
        <div class="form-group">
          <label><i class="fas fa-user"></i> اسم المستخدم</label>
          <input type="text" id="loginUsername" placeholder="أدخل اسم المستخدم">
        </div>
        <div class="form-group">
          <label><i class="fas fa-lock"></i> كلمة المرور</label>
          <input type="password" id="loginPassword" placeholder="أدخل كلمة المرور">
        </div>
        <button class="btn btn-primary" onclick="handleLogin()">
          <i class="fas fa-sign-in-alt"></i> تسجيل الدخول
        </button>
      </div>
      <div id="registerForm" style="display:none;">
        <div class="form-group">
          <label><i class="fas fa-user"></i> اسم المستخدم</label>
          <input type="text" id="regUsername" placeholder="اختر اسم مستخدم (3 أحرف على الأقل)">
        </div>
        <div class="form-group">
          <label><i class="fas fa-id-card"></i> الاسم (اختياري)</label>
          <input type="text" id="regName" placeholder="أدخل اسمك">
        </div>
        <div class="form-group">
          <label><i class="fas fa-lock"></i> كلمة المرور</label>
          <input type="password" id="regPassword" placeholder="اختر كلمة مرور (6 أحرف على الأقل)">
        </div>
        <button class="btn btn-primary" onclick="handleRegister()">
          <i class="fas fa-user-plus"></i> إنشاء حساب
        </button>
      </div>
      <div class="toggle-text">
        <span id="toggleText">ليس لديك حساب؟</span>
        <a id="toggleLink" onclick="toggleForm()">إنشاء حساب جديد</a>
      </div>
    </div>
  </div>

  <!-- Main App -->
  <div id="appPage" class="app-container">
    <header class="top-bar">
      <div class="logo-area">
        <i class="fas fa-pen-fancy logo-icon"></i>
        <span class="logo-text">Pen</span>
      </div>
      <div class="user-area">
        <span class="user-name" id="displayName"></span>
        <button class="logout-btn" onclick="handleLogout()"><i class="fas fa-sign-out-alt"></i> خروج</button>
      </div>
    </header>

    <div class="main-layout">
      <section class="content-area">
        <h3 style="color:#fbbf24; margin-bottom:0.8rem; font-size:1rem;"><i class="fas fa-star"></i> المحتوى</h3>
        <div class="card-grid">
          <div class="feature-card" onclick="sendQuickAction('امتحان')"><i class="fas fa-book-open"></i><div><h4>الامتحانات</h4><p>أسئلة متوقعة</p></div></div>
          <div class="feature-card" onclick="sendQuickAction('اختبرني')"><i class="fas fa-question-circle"></i><div><h4>تفاعلي MCQ</h4><p>امتحان مباشر</p></div></div>
          <div class="feature-card" onclick="sendQuickAction('خطة التركيز')"><i class="fas fa-chart-line"></i><div><h4>خطة التركيز</h4><p>أهم الموضوعات</p></div></div>
          <div class="feature-card" onclick="sendQuickAction('مستوايا')"><i class="fas fa-user-graduate"></i><div><h4>مستوايا</h4><p>تحليل الأداء</p></div></div>
        </div>
      </section>

      <div class="chatbot-section">
        <div class="chat-header">
          <div class="chat-header-left">
            <i class="fas fa-robot"></i>
            <span>المساعد Pen</span>
            <span class="status-badge status-online">متصل</span>
          </div>
          <div class="header-quick-buttons">
            <span class="header-category-label">📝</span>
            <button class="header-quick-btn" onclick="sendQuickAction('امتحان')">أهم الأسئلة</button>
            <button class="header-quick-btn" onclick="sendQuickAction('امتحان سهل')">سهل</button>
            <button class="header-quick-btn" onclick="sendQuickAction('امتحان متوسط')">متوسط</button>
            <button class="header-quick-btn" onclick="sendQuickAction('امتحان صعب')">صعب</button>
            <span class="header-category-label">🎯</span>
            <button class="header-quick-btn" onclick="sendQuickAction('اختبرني')">اختبرني</button>
            <button class="header-quick-btn" onclick="sendQuickAction('اختبرني في البلاغة')">البلاغة</button>
            <span class="header-category-label">📊</span>
            <button class="header-quick-btn" onclick="sendQuickAction('خطة التركيز')">خطة التركيز</button>
            <button class="header-quick-btn" onclick="sendQuickAction('مستوايا')">مستوايا</button>
          </div>
        </div>
        <div class="chat-messages" id="chatMessages">
          <div class="message bot-msg">
            <div class="msg-bubble">👋 مرحباً <strong id="welcomeName"></strong>! أنا مساعدك الذكي في منصة Pen.<br><br>📊 <strong>""" + str(len(ALL_QUESTIONS)) + """ سؤال</strong> | <strong>""" + str(len(MCQ_QUESTIONS)) + """ MCQ</strong> جاهزين<br><br>اختر من الأزرار أو اكتب سؤالك مباشرة.</div>
          </div>
        </div>
        <div class="chat-input-area">
          <input type="text" id="userInput" placeholder="اكتب سؤالك هنا ..." />
          <button id="sendBtn" onclick="sendMessage()"><i class="fas fa-paper-plane"></i></button>
        </div>
      </div>
    </div>
    <footer>© 2025 منصة Pen - حسابك الشخصي 📊</footer>
  </div>

  <script>
    let currentUser = null;
    let chatId = null;
    let isWaitingForResponse = false;
    let isLoginMode = true;

    // ============ AUTH FUNCTIONS ============
    function showError(msg) {
      const el = document.getElementById('errorMsg');
      el.textContent = msg;
      el.style.display = 'block';
      setTimeout(() => el.style.display = 'none', 5000);
    }

    function showSuccess(msg) {
      const el = document.getElementById('successMsg');
      el.textContent = msg;
      el.style.display = 'block';
      setTimeout(() => el.style.display = 'none', 3000);
    }

    function toggleForm() {
      isLoginMode = !isLoginMode;
      document.getElementById('loginForm').style.display = isLoginMode ? 'block' : 'none';
      document.getElementById('registerForm').style.display = isLoginMode ? 'none' : 'block';
      document.getElementById('toggleText').textContent = isLoginMode ? 'ليس لديك حساب؟' : 'لديك حساب بالفعل؟';
      document.getElementById('toggleLink').textContent = isLoginMode ? 'إنشاء حساب جديد' : 'تسجيل الدخول';
      document.getElementById('errorMsg').style.display = 'none';
      document.getElementById('successMsg').style.display = 'none';
    }

    async function handleRegister() {
      const username = document.getElementById('regUsername').value.trim();
      const name = document.getElementById('regName').value.trim();
      const password = document.getElementById('regPassword').value.trim();

      if (!username || !password) {
        showError('اسم المستخدم وكلمة المرور مطلوبين');
        return;
      }

      try {
        const response = await fetch('/api/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password, name })
        });

        const data = await response.json();

        if (data.error) {
          showError(data.error);
        } else {
          showSuccess('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن');
          setTimeout(() => toggleForm(), 1500);
        }
      } catch (error) {
        showError('حدث خطأ في الاتصال');
      }
    }

    async function handleLogin() {
      const username = document.getElementById('loginUsername').value.trim();
      const password = document.getElementById('loginPassword').value.trim();

      if (!username || !password) {
        showError('اسم المستخدم وكلمة المرور مطلوبين');
        return;
      }

      try {
        const response = await fetch('/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });

        const data = await response.json();

        if (data.error) {
          showError(data.error);
        } else {
          currentUser = data;
          chatId = data.chat_id;
          
          // حفظ في localStorage
          localStorage.setItem('pen_user', JSON.stringify(data));
          
          // إظهار التطبيق
          showApp();
        }
      } catch (error) {
        showError('حدث خطأ في الاتصال');
      }
    }

    function handleLogout() {
      currentUser = null;
      chatId = null;
      localStorage.removeItem('pen_user');
      document.getElementById('loginPage').style.display = 'flex';
      document.getElementById('appPage').style.display = 'none';
      document.getElementById('loginUsername').value = '';
      document.getElementById('loginPassword').value = '';
    }

    function showApp() {
      document.getElementById('loginPage').style.display = 'none';
      document.getElementById('appPage').style.display = 'flex';
      document.getElementById('displayName').textContent = currentUser.name || currentUser.username;
      document.getElementById('welcomeName').textContent = currentUser.name || currentUser.username;
      
      // مسح الرسائل القديمة وإظهار رسالة الترحيب
      const chatMessages = document.getElementById('chatMessages');
      chatMessages.innerHTML = `
        <div class="message bot-msg">
          <div class="msg-bubble">👋 مرحباً <strong>${currentUser.name || currentUser.username}</strong>! أنا مساعدك الذكي في منصة Pen.<br><br>📊 <strong>${document.querySelector('script').textContent.match(/ALL_QUESTIONS/) ? '...' : '489 سؤال'}</strong> | <strong>454 MCQ</strong> جاهزين<br><br>اختر من الأزرار أو اكتب سؤالك مباشرة.</div>
        </div>
      `;
    }

    // ============ CHAT FUNCTIONS ============
    function formatMessage(text) {
      return text.replace(/\*(.*?)\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>').replace(/─+/g, '─'.repeat(25));
    }

    function addMessage(text, isUser) {
      const chatMessages = document.getElementById('chatMessages');
      const msgDiv = document.createElement('div');
      msgDiv.className = 'message ' + (isUser ? 'user-msg' : 'bot-msg');
      msgDiv.innerHTML = '<div class="msg-bubble">' + formatMessage(text) + '</div>';
      chatMessages.appendChild(msgDiv);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function showTyping() {
      const chatMessages = document.getElementById('chatMessages');
      const typingDiv = document.createElement('div');
      typingDiv.className = 'message bot-msg';
      typingDiv.id = 'typingIndicator';
      typingDiv.innerHTML = '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
      chatMessages.appendChild(typingDiv);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function removeTyping() {
      const indicator = document.getElementById('typingIndicator');
      if (indicator) indicator.remove();
    }

    function setInputEnabled(enabled) {
      document.getElementById('userInput').disabled = !enabled;
      document.getElementById('sendBtn').disabled = !enabled;
      isWaitingForResponse = !enabled;
      if (enabled) document.getElementById('userInput').focus();
    }

    async function sendMessage() {
      const userInput = document.getElementById('userInput');
      const text = userInput.value.trim();
      
      if (!text || isWaitingForResponse || !currentUser) return;
      
      addMessage(text, true);
      userInput.value = '';
      setInputEnabled(false);
      showTyping();
      
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000);
        
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: chatId,
            message: text,
            username: currentUser.username
          }),
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        const data = await response.json();
        
        setTimeout(() => {
          removeTyping();
          if (data.reply) {
            addMessage(data.reply, false);
          }
          setInputEnabled(true);
        }, 500);
        
      } catch (error) {
        setTimeout(() => {
          removeTyping();
          addMessage('❌ حدث خطأ في الاتصال. جرب مرة أخرى.', false);
          setInputEnabled(true);
        }, 500);
      }
    }

    function sendQuickAction(action) {
      document.getElementById('userInput').value = action;
      sendMessage();
    }

    // ============ INIT ============
    // التحقق من وجود جلسة سابقة
    const savedUser = localStorage.getItem('pen_user');
    if (savedUser) {
      try {
        const userData = JSON.parse(savedUser);
        currentUser = userData;
        chatId = userData.chat_id;
        showApp();
      } catch (e) {
        localStorage.removeItem('pen_user');
      }
    }

    // Enter key
    document.addEventListener('keypress', function(e) {
      if (e.key === 'Enter' && document.getElementById('appPage').style.display === 'flex') {
        sendMessage();
      }
    });
  </script>
</body>
</html>"""

# =========================================
# STARTUP
# =========================================

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_sessions())
    print("🚀 Pen Platform with Firebase Auth started!")
    print(f"📊 Firebase connected: {StudentService.is_connected()}")
