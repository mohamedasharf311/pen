from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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

# =========================================
# NORMALIZE ARABIC TEXT
# =========================================

def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    
    replacements = {
        'أ': 'ا', 'إ': 'ا', 'آ': 'ا',
        'ة': 'ه',
        'ى': 'ي',
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

SKILL_MAP = {
    "استنتاج": "implicit_reasoning",
    "الاستنتاج": "implicit_reasoning",
    "فكرة رئيسية": "main_idea_detection",
    "الفكرة الرئيسية": "main_idea_detection",
    "بلاغة": "rhetoric_analysis",
    "البلاغة": "rhetoric_analysis",
    "نحو": "grammar",
    "النحو": "grammar",
}

def detect_intent(message: str, chat_id: str = "") -> Intent:
    message_lower = message.lower().strip()
    message_words = message_lower.split()
    
    # هوية البوت
    for phrase in IDENTITY_WORDS:
        if phrase in message_lower:
            return Intent.IDENTITY
    
    # تحية
    for pattern in GREETING_PATTERNS:
        if re.search(pattern, message_lower) and len(message_words) <= 3:
            return Intent.GREETING
    
    # تغيير المستوى
    if message_lower in ["سهل", "متوسط", "صعب"]:
        last = get_last_command(chat_id)
        if last in ["exam", "interactive_exam"]:
            return Intent.LEVEL_CHANGE
    
    # امتحان تفاعلي
    if any(x in message_lower for x in ["اختبرني", "اختبرنى", "اختبريني"]):
        return Intent.INTERACTIVE_EXAM
    
    # امتحان عادي
    if any(x in message_lower for x in ["امتحان", "امتخان", "اختبار"]):
        return Intent.EXAM
    
    # خطة تركيز
    if any(x in message_lower for x in ["خطة", "خطه", "التركيز", "ركز", "تركيز", "مستوايا", "مستوى"]):
        return Intent.FOCUS_PLAN
    
    # شرح درس
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
    
    for topic, questions in QUESTIONS_BY_TOPIC.items():
        if fuzzy_match(clean_message, topic, threshold=0.5) and questions:
            q = questions[0]
            return format_lesson_response(q, clean_message)
    
    for q in ALL_QUESTIONS[:20]:
        question_text = q.get("question", "")
        if fuzzy_match(clean_message, question_text, threshold=0.6):
            return format_lesson_response(q, clean_message)
    
    return f"❌ مش لاقي شرح لـ '{clean_message}'\n\nجرب تكتب:\n• شرح النحو\n• شرح البلاغة"

def format_lesson_response(question: Dict, topic: str) -> str:
    question_text = question.get("question", "")
    if len(question_text) > MAX_QUESTION_LENGTH:
        question_text = question_text[:MAX_QUESTION_LENGTH-3] + "..."
    
    msg = f"📚 *شرح: {topic}*\n"
    msg += "─" * 25 + "\n\n"
    msg += f"📖 *السؤال:*\n{question_text}\n\n"
    
    explanation = question.get("explanation", "")
    if explanation:
        msg += f"📝 *الشرح:*\n{explanation}\n\n"
    
    msg += "💪 *ركز عليه كويس*"
    
    return msg

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
        
        # التحقق من جلسة تفاعلية نشطة
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
            return """👋 *أهلاً بيك في منصة Pen!*

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

# =========================================
# ROOT & HEALTH
# =========================================

@app.get("/")
async def root():
    return {
        "status": "working",
        "version": "pen-v1",
        "questions": len(ALL_QUESTIONS),
        "mcq_questions": len(MCQ_QUESTIONS),
        "endpoints": {
            "webhook": "/api/webhook",
            "health": "/health"
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "questions": len(ALL_QUESTIONS),
        "mcq": len(MCQ_QUESTIONS),
        "active_sessions": len(user_sessions)
    }

# =========================================
# STARTUP
# =========================================

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_sessions())
    print("🚀 Pen Platform started!")
