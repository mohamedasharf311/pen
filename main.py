from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

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

# =========================================
# APP
# =========================================

app = FastAPI(title="Pen Platform - Exam Focus Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    
    if any(x in message_lower for x in ["اختبرني", "اختبرنى", "اختبريني"]):
        return Intent.INTERACTIVE_EXAM
    
    if any(x in message_lower for x in ["امتحان", "امتخان", "اختبار"]):
        return Intent.EXAM
    
    if any(x in message_lower for x in ["خطة", "خطه", "التركيز", "ركز", "تركيز", "مستوايا", "مستوى"]):
        return Intent.FOCUS_PLAN
    
    if "شرح" in message_lower:
        return Intent.LESSON
    
    return Intent.UNKNOWN

# =========================================
# DATA LOADING
# =========================================

ALL_QUESTIONS: List[Dict] = []
MCQ_QUESTIONS: List[Dict] = []
QUESTIONS_BY_TOPIC: Dict[str, List[Dict]] = defaultdict(list)
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
                "exam_signal": data.get("exam_signal", {}),
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
                "exam_signal": data.get("exam_signal", {}),
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
    global MCQ_QUESTIONS, QUESTIONS_BY_TOPIC, QUESTIONS_BY_DIFFICULTY
    MCQ_QUESTIONS = []
    QUESTIONS_BY_TOPIC = defaultdict(list)
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

def process_exam_answer(chat_id: str, user_answer: str) -> str:
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
        response += "• `اختبرني صعب` - أسئلة صعبة"
        
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
# IDENTITY RESPONSE
# =========================================

IDENTITY_RESPONSE = """🤖 *أنا المساعد Pen*

📚 *مساعد ذكي للتعليم:*
• 🎯 امتحانات متوقعة
• 📝 امتحانات تفاعلية (MCQ)
• 📖 شرح الدروس والمفاهيم
• 📊 تحليل أهم الموضوعات

📌 *جرب الأوامر دي:*
• `امتحان` - أسئلة متوقعة
• `اختبرني` - امتحان تفاعلي
• `شرح النحو` - شرح درس
• `خطة التركيز` - أهم الموضوعات"""

GREETING_RESPONSE = """👋 *أهلاً بيك في منصة Pen!*

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

async def process_message(chat_id: str, body: str) -> str:
    try:
        if is_rate_limited(chat_id):
            return ""
        
        if chat_id in user_sessions:
            session = user_sessions[chat_id]
            if session.active and not session.is_expired():
                return process_exam_answer(chat_id, body)
            elif session.is_expired():
                del user_sessions[chat_id]
                return "⏰ *انتهت الجلسة*\nاكتب `اختبرني` لبدء امتحان جديد"
        
        body_lower = body.lower().strip()
        intent = detect_intent(body_lower, chat_id)
        
        if intent == Intent.IDENTITY:
            return IDENTITY_RESPONSE
        
        elif intent == Intent.GREETING:
            return GREETING_RESPONSE
        
        elif intent == Intent.LEVEL_CHANGE:
            last = get_last_command(chat_id)
            level = LEVEL_KEYWORDS.get(body_lower, "medium")
            
            if last == "exam":
                return generate_exam(level=level)
            elif last == "interactive_exam":
                return start_interactive_exam(chat_id, level=level)
            else:
                return f"📌 اكتب `امتحان {body_lower}` أو `اختبرني {body_lower}`"
        
        elif intent == Intent.INTERACTIVE_EXAM:
            level = "medium"
            for arabic_level, level_key in LEVEL_KEYWORDS.items():
                if arabic_level in body_lower:
                    level = level_key
                    break
            
            remember_command(chat_id, "interactive_exam")
            return start_interactive_exam(chat_id, level)
        
        elif intent == Intent.EXAM:
            level = None
            for arabic_level, level_key in LEVEL_KEYWORDS.items():
                if arabic_level in body_lower:
                    level = level_key
                    break
            
            remember_command(chat_id, "exam")
            return generate_exam(level=level)
        
        elif intent == Intent.FOCUS_PLAN:
            return generate_focus_plan()
        
        elif intent == Intent.LESSON:
            return search_lesson(body)
        
        else:
            return """📌 *جرب تكتب:*
• `امتحان` - أسئلة متوقعة
• `اختبرني` - امتحان تفاعلي
• `شرح النحو` - شرح
• `خطة التركيز` - أهم الموضوعات"""
    
    except Exception as e:
        print(f"❌ PROCESS ERROR: {e}")
        return "❌ حصل خطأ، جرب تاني"

# =========================================
# API ENDPOINT
# =========================================

@app.api_route("/api/webhook", methods=["GET", "POST"])
async def webhook_handler(request: Request):
    if request.method == "GET":
        return JSONResponse({
            "status": "active",
            "version": "pen-v1",
            "questions": len(ALL_QUESTIONS),
            "mcq_questions": len(MCQ_QUESTIONS),
            "active_sessions": len(user_sessions)
        })
    
    try:
        data = await request.json()
        payload = data.get("payload", {})
        chat_id = payload.get("from", "web_user")
        body = str(payload.get("body", "")).strip()
        
        if not body:
            return JSONResponse({"reply": ""})
        
        reply = await process_message(chat_id, body)
        
        return JSONResponse({
            "reply": reply,
            "ok": True
        })
    except Exception as e:
        print(f"❌ WEBHOOK ERROR: {e}")
        return JSONResponse({"reply": "❌ حصل خطأ", "ok": False})

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "questions": len(ALL_QUESTIONS),
        "mcq": len(MCQ_QUESTIONS),
        "active_sessions": len(user_sessions)
    }

# =========================================
# HTML INTERFACE
# =========================================

@app.get("/", response_class=HTMLResponse)
async def serve_html():
    return """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=yes">
  <title>منصة Pen | تعليم ذكي</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    body { background: #0f172a; color: #e2e8f0; display: flex; flex-direction: column; min-height: 100vh; }
    .top-bar { background: #1e293b; color: #f1f5f9; padding: 0.7rem 2rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; box-shadow: 0 4px 16px rgba(0,0,0,0.5); border-bottom: 1px solid #334155; }
    .logo-area { display: flex; align-items: center; gap: 12px; }
    .logo-icon { font-size: 2.2rem; color: #fbbf24; transform: rotate(-15deg); text-shadow: 0 0 10px rgba(251,191,36,0.5); }
    .logo-text { font-size: 1.8rem; font-weight: bold; letter-spacing: 1px; background: linear-gradient(135deg, #fbbf24, #f59e0b); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
    .nav-links { display: flex; gap: 1.8rem; flex-wrap: wrap; align-items: center; }
    .nav-links a { color: #cbd5e1; text-decoration: none; font-weight: 500; padding: 0.5rem 0.9rem; border-radius: 10px; transition: 0.2s; display: flex; align-items: center; gap: 6px; }
    .nav-links a:hover { background: #334155; color: white; }
    .active-link { background: #fbbf24 !important; color: #0f172a !important; font-weight: bold; }
    .main-layout { display: flex; flex: 1; margin: 0 1.5rem 1.5rem; gap: 1.5rem; flex-wrap: wrap; align-items: stretch; }
    .content-area { flex: 0.4; min-width: 220px; max-width: 300px; background: #1e293b; border-radius: 24px; padding: 1.2rem; box-shadow: 0 8px 24px rgba(0,0,0,0.5); border: 1px solid #334155; display: flex; flex-direction: column; }
    .card-grid { display: flex; flex-direction: column; gap: 0.8rem; margin-top: 0.8rem; overflow-y: auto; }
    .feature-card { background: #0f172a; border-radius: 14px; padding: 0.8rem; display: flex; align-items: center; gap: 10px; transition: 0.2s; border: 1px solid #334155; cursor: pointer; }
    .feature-card i { font-size: 1.3rem; color: #fbbf24; }
    .feature-card h4 { color: #f1f5f9; margin-bottom: 0.1rem; font-size: 0.9rem; }
    .feature-card p { color: #94a3b8; font-size: 0.75rem; }
    .feature-card:hover { background: #1e293b; border-color: #fbbf24; }
    .chatbot-section { flex: 3; min-width: 500px; background: #1e293b; border-radius: 24px; box-shadow: 0 8px 28px rgba(0,0,0,0.6); display: flex; flex-direction: column; overflow: hidden; border: 1px solid #334155; }
    .chat-header { background: #0f172a; color: #fbbf24; padding: 1rem 1.5rem; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem; font-weight: bold; font-size: 1.3rem; border-bottom: 1px solid #334155; }
    .chat-header-left { display: flex; align-items: center; gap: 10px; }
    .chat-header-left i { font-size: 1.6rem; }
    .status-badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 10px; font-size: 0.7rem; font-weight: normal; }
    .status-online { background: #10b981; color: white; }
    .header-quick-buttons { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
    .header-quick-btn { background: #1e293b; color: #fbbf24; border: 1px solid #fbbf24; padding: 0.4rem 0.8rem; border-radius: 18px; font-size: 0.75rem; cursor: pointer; transition: 0.2s; white-space: nowrap; font-weight: 500; }
    .header-quick-btn:hover { background: #fbbf24; color: #0f172a; font-weight: bold; transform: scale(1.05); }
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
    .chat-input-area input::placeholder { color: #64748b; font-size: 0.95rem; }
    .chat-input-area input:disabled { opacity: 0.5; }
    .chat-input-area button { background: #fbbf24; color: #0f172a; border: none; border-radius: 50%; width: 50px; height: 50px; cursor: pointer; font-size: 1.2rem; transition: 0.2s; display: flex; align-items: center; justify-content: center; }
    .chat-input-area button:hover { background: #f59e0b; transform: scale(1.1); }
    .chat-input-area button:disabled { opacity: 0.5; cursor: not-allowed; }
    footer { text-align: center; color: #64748b; margin: 0.5rem 0 1rem; font-size: 0.8rem; }
    @media (max-width: 900px) { .main-layout { flex-direction: column; } .content-area { max-width: 100%; flex: 1; } .chatbot-section { min-width: auto; flex: 3; } .chat-header { flex-direction: column; align-items: flex-start; } }
  </style>
</head>
<body>
  <header class="top-bar">
    <div class="logo-area">
      <i class="fas fa-pen-fancy logo-icon"></i>
      <span class="logo-text">Pen</span>
    </div>
    <div class="nav-links">
      <a href="#" id="navCourses" class="active-link"><i class="fas fa-book-open"></i> الكورسات</a>
      <a href="#" id="navMinistry"><i class="fas fa-university"></i> وزارة التربية والتعليم</a>
    </div>
  </header>

  <div class="main-layout">
    <section class="content-area" id="contentDisplay">
      <h3 style="color:#fbbf24; margin-bottom:0.8rem; font-size:1rem;"><i class="fas fa-star"></i> المحتوى</h3>
      <div id="dynamicCards" class="card-grid">
        <div class="feature-card"><i class="fas fa-book-open"></i><div><h4>أساسيات البرمجة</h4><p>كورس بايثون للمبتدئين</p></div></div>
        <div class="feature-card"><i class="fas fa-calculator"></i><div><h4>الرياضيات المتقدمة</h4><p>تفاضل وتكامل</p></div></div>
        <div class="feature-card"><i class="fas fa-language"></i><div><h4>اللغة الإنجليزية</h4><p>محادثة وقواعد</p></div></div>
        <div class="feature-card"><i class="fas fa-atom"></i><div><h4>الفيزياء الحديثة</h4><p>الكهرباء والمغناطيسية</p></div></div>
        <div class="feature-card"><i class="fas fa-landmark"></i><div><h4>التاريخ العالمي</h4><p>الحضارات القديمة</p></div></div>
      </div>
    </section>

    <div class="chatbot-section">
      <div class="chat-header">
        <div class="chat-header-left">
          <i class="fas fa-robot"></i>
          <span>المساعد Pen</span>
          <span id="apiStatus" class="status-badge status-online">متصل</span>
        </div>
        <div class="header-quick-buttons" id="headerQuickButtons">
          <span class="header-category-label">📝</span>
          <button class="header-quick-btn" data-action="امتحان">أهم الأسئلة</button>
          <button class="header-quick-btn" data-action="امتحان سهل">سهل</button>
          <button class="header-quick-btn" data-action="امتحان متوسط">متوسط</button>
          <button class="header-quick-btn" data-action="امتحان صعب">صعب</button>
          
          <span class="header-category-label">🎯</span>
          <button class="header-quick-btn" data-action="اختبرني">اختبرني</button>
          <button class="header-quick-btn" data-action="اختبرني في البلاغة">البلاغة</button>
          
          <span class="header-category-label">📊</span>
          <button class="header-quick-btn" data-action="خطة التركيز">خطة التركيز</button>
          <button class="header-quick-btn" data-action="مستوايا">مستوايا</button>
          
          <span class="header-category-label">📚</span>
          <button class="header-quick-btn" data-action="شرح">شرح</button>
          
          <span class="header-category-label">💡</span>
          <button class="header-quick-btn" data-action="اشرحلي">اشرحلي</button>
          <button class="header-quick-btn" data-action="فسر">فسر</button>
          <button class="header-quick-btn" data-action="قارن">قارن</button>
        </div>
      </div>
      <div class="chat-messages" id="chatMessages">
        <div class="message bot-msg">
          <div class="msg-bubble">👋 مرحباً! أنا مساعدك الذكي في منصة Pen.<br><br>📊 <strong>""" + str(len(ALL_QUESTIONS)) + """ سؤال</strong> | <strong>""" + str(len(MCQ_QUESTIONS)) + """ MCQ</strong> جاهزين<br><br>اختر من الأزرار في الأعلى أو اكتب سؤالك مباشرة.</div>
        </div>
      </div>
      <div class="chat-input-area">
        <input type="text" id="userInput" placeholder="اكتب سؤالك هنا ..." />
        <button id="sendBtn"><i class="fas fa-paper-plane"></i></button>
      </div>
    </div>
  </div>
  <footer>© 2025 منصة Pen - شغال على Render 🚀</footer>

  <script>
    const API_URL = '/api/webhook';
    const CHAT_ID = 'web_user_' + Math.random().toString(36).substr(2, 9);
    
    const chatMessages = document.getElementById('chatMessages');
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const apiStatus = document.getElementById('apiStatus');
    let isWaitingForResponse = false;

    function formatMessage(text) {
      return text.replace(/\\*(.*?)\\*/g, '<strong>$1</strong>').replace(/\\n/g, '<br>').replace(/─+/g, '─'.repeat(25));
    }

    function addMessage(text, isUser) {
      const msgDiv = document.createElement('div');
      msgDiv.className = 'message ' + (isUser ? 'user-msg' : 'bot-msg');
      msgDiv.innerHTML = '<div class="msg-bubble">' + formatMessage(text) + '</div>';
      chatMessages.appendChild(msgDiv);
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function showTyping() {
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
      userInput.disabled = !enabled;
      sendBtn.disabled = !enabled;
      isWaitingForResponse = !enabled;
      if (enabled) userInput.focus();
    }

    function getLocalResponse(message) {
      const msg = message.toLowerCase().trim();
      if (/^(اهلا|أهلا|مرحبا|السلام|هاي|هلا|سلام)/.test(msg)) {
        return "👋 *أهلاً بيك في منصة Pen!*\\n\\n📝 *الامتحانات:*\\n• امتحان - أهم الأسئلة\\n• امتحان سهل - متوسط - صعب\\n\\n🎯 *تفاعلي:*\\n• اختبرني - امتحان تفاعلي\\n• اختبرني في البلاغة\\n\\n📊 *تحليل:*\\n• خطة التركيز\\n• مستوايا";
      }
      if (msg.includes('امتحان') && msg.includes('سهل')) return "📝 *امتحان سهل 🟢*\\n─────────────────────────\\n\\n*1.* ما هو تعريف المصطلح الأساسي؟\\n*2.* أكمل الفراغ\\n*3.* اختر الإجابة الصحيحة\\n\\n🟢 المستوى: *سهل*\\n💪 *ربنا معاك يا بطل*";
      if (msg.includes('امتحان') && msg.includes('متوسط')) return "📝 *امتحان متوسط 🟡*\\n─────────────────────────\\n\\n*1.* قارن بين المفهومين\\n*2.* اشرح العبارة التالية\\n*3.* حلل النص\\n\\n🟡 المستوى: *متوسط*\\n💪 *ركز كويس*";
      if (msg.includes('امتحان') && msg.includes('صعب')) return "📝 *امتحان صعب 🔴*\\n─────────────────────────\\n\\n*1.* ناقش بالتفصيل\\n*2.* استنتج العلاقة\\n*3.* حل المسألة المعقدة\\n\\n🔴 المستوى: *صعب*\\n💪 *للمتميزين فقط*";
      if (msg.includes('امتحان')) return "📝 *أهم الأسئلة المتوقعة*\\n─────────────────────────\\n\\n*1.* 📝 سؤال عن المفاهيم الأساسية\\n*2.* 🔤 سؤال اختيار من متعدد\\n*3.* ✍️ سؤال مقالي تحليلي\\n\\n💪 *ربنا معاك يا بطل*";
      if (msg.includes('اختبرني')) return "🧠 *سؤال 1 من 5*\\n\\n*س1:* أي من الخيارات التالية يمثل الخاصية الأساسية للنص الأدبي؟\\n\\n1️⃣ الوضوح المباشر\\n2️⃣ التعبير عن المشاعر\\n3️⃣ استخدام الأرقام\\n4️⃣ الحياد التام\\n\\n📝 *ابعت رقم الإجابة (1-4)* 👇";
      if (msg.includes('خطة') || msg.includes('تركيز') || msg.includes('مستوايا') || msg.includes('مستوى')) return "📊 *تحليل المستوى*\\n─────────────────────────\\n\\n📌 *نقاط القوة:*\\n   ✅ الفهم: 85%\\n   ✅ التطبيق: 78%\\n\\n⚠️ *يحتاج تحسين:*\\n   ⚠️ التحليل: 60%\\n   ⚠️ الاستنتاج: 55%";
      return "📌 *جرب تكتب:*\\n• `امتحان` - أسئلة متوقعة\\n• `اختبرني` - امتحان تفاعلي\\n• `شرح [الدرس]` - شرح\\n• `خطة التركيز` - أهم الموضوعات";
    }

    async function sendMessage(text) {
      if (!text || isWaitingForResponse) return;
      addMessage(text, true);
      userInput.value = '';
      setInputEnabled(false);
      showTyping();
      
      let reply = null;
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);
        const response = await fetch(API_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ payload: { from: CHAT_ID, body: text } }),
          signal: controller.signal
        });
        clearTimeout(timeoutId);
        const data = await response.json();
        if (data.ok && data.reply) reply = data.reply;
      } catch (error) {
        console.log('API offline, using local');
      }
      
      if (!reply) reply = getLocalResponse(text);
      
      setTimeout(() => {
        removeTyping();
        addMessage(reply, false);
        setInputEnabled(true);
      }, 600);
    }

    sendBtn.addEventListener('click', () => sendMessage(userInput.value.trim()));
    userInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendMessage(userInput.value.trim());
    });

    document.querySelectorAll('.header-quick-btn').forEach(btn => {
      btn.addEventListener('click', () => sendMessage(btn.dataset.action));
    });

    document.getElementById('navCourses').addEventListener('click', function(e) {
      e.preventDefault();
      this.classList.add('active-link');
      document.getElementById('navMinistry').classList.remove('active-link');
    });

    document.getElementById('navMinistry').addEventListener('click', function(e) {
      e.preventDefault();
      this.classList.add('active-link');
      document.getElementById('navCourses').classList.remove('active-link');
    });

    userInput.focus();
    console.log('🚀 منصة Pen جاهزة | """ + str(len(ALL_QUESTIONS)) + """ سؤال | """ + str(len(MCQ_QUESTIONS)) + """ MCQ');
  </script>
</body>
</html>"""

# =========================================
# STARTUP
# =========================================

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_sessions())
    print("🚀 Pen Platform started!")
