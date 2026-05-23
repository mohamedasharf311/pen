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

app = FastAPI(title="Pen Platform - Advanced V3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# STUDENT SERVICE (Enhanced)
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
            
            b64 = os.getenv("FIREBASE_CREDENTIALS_BASE64", "")
            if b64:
                try:
                    decoded = base64.b64decode(b64).decode("utf-8")
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                        f.write(decoded)
                        temp_path = f.name
                    cred = credentials.Certificate(temp_path)
                    os.unlink(temp_path)
                    
                    try:
                        firebase_admin.get_app()
                    except ValueError:
                        firebase_admin.initialize_app(cred, {
                            "databaseURL": "https://forme-6167f-default-rtdb.firebaseio.com"
                        })
                    
                    from firebase_admin import db
                    cls._rtdb = db
                    print("✅ Firebase RTDB ready!")
                except Exception as e:
                    print(f"⚠️ Firebase error: {e}")
        except ImportError:
            print("⚠️ firebase_admin not installed")
    
    @classmethod
    def _now_iso(cls) -> str:
        return datetime.now().isoformat()
    
    @classmethod
    def _now_ts(cls) -> int:
        return int(datetime.now().timestamp() * 1000)
    
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
            "asked_questions": [],
            "total_score": 0,
            "total_exams": 0,
            "skill_stats": {}
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
    def get_user_data(cls, username: str) -> Dict:
        if cls._rtdb:
            try:
                data = cls._rtdb.reference(f"users/{username}").get()
                if data:
                    return data
            except: pass
        return cls._local_db["users"].get(username, {})
    
    @classmethod
    def update_user_data(cls, username: str, updates: Dict):
        user_data = cls.get_user_data(username)
        user_data.update(updates)
        cls._local_db["users"][username] = user_data
        
        if cls._rtdb:
            try:
                cls._rtdb.reference(f"users/{username}").update(updates)
            except: pass
    
    @classmethod
    def add_asked_question(cls, username: str, question_id: str):
        user_data = cls.get_user_data(username)
        asked = user_data.get("asked_questions", [])
        if question_id not in asked:
            asked.append(question_id)
            cls.update_user_data(username, {"asked_questions": asked})
    
    @classmethod
    def save_exam_result(cls, username: str, result: Dict):
        correct = result.get("correct", 0)
        total = result.get("total", 1)
        percentage = int((correct / max(total, 1)) * 100)
        wrong_questions = result.get("wrong_questions", [])
        wrong_skills = result.get("wrong_skills", [])
        questions_ids = result.get("questions_ids", [])
        
        exam_data = {
            "score": correct,
            "total": total,
            "percentage": percentage,
            "wrong_questions": wrong_questions,
            "wrong_skills": wrong_skills,
            "questions_ids": questions_ids,
            "timestamp": cls._now_ts(),
            "grade": cls._calculate_grade(percentage),
        }
        
        # Update skill stats
        user_data = cls.get_user_data(username)
        skill_stats = user_data.get("skill_stats", {})
        
        for skill in wrong_skills:
            if skill not in skill_stats:
                skill_stats[skill] = {"correct": 0, "wrong": 0}
            skill_stats[skill]["wrong"] += 1
        
        # Add correct skills (questions not in wrong)
        all_skills = result.get("all_skills", [])
        for skill in all_skills:
            if skill not in wrong_skills:
                if skill not in skill_stats:
                    skill_stats[skill] = {"correct": 0, "wrong": 0}
                skill_stats[skill]["correct"] += 1
        
        updates = {
            "skill_stats": skill_stats,
            "total_exams": user_data.get("total_exams", 0) + 1,
            "total_score": user_data.get("total_score", 0) + correct
        }
        cls.update_user_data(username, updates)
        
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
    def get_wrong_questions(cls, username: str) -> List[str]:
        wrong_qs = []
        if cls._rtdb:
            try:
                exams = cls._rtdb.reference(f"students/{username}/exams").get() or {}
                for exam in exams.values():
                    wrong_qs.extend(exam.get("wrong_questions", []))
            except: pass
        return list(set(wrong_qs))
    
    @classmethod
    def get_leaderboard(cls) -> List[Dict]:
        users = []
        if cls._rtdb:
            try:
                all_users = cls._rtdb.reference("users").get() or {}
                for uid, data in all_users.items():
                    total_exams = data.get("total_exams", 0)
                    total_score = data.get("total_score", 0)
                    if total_exams > 0:
                        avg = int((total_score / (total_exams * 5)) * 100) if total_exams > 0 else 0
                        users.append({
                            "name": data.get("name", uid),
                            "avg": avg,
                            "exams": total_exams
                        })
            except: pass
        
        users.sort(key=lambda x: x["avg"], reverse=True)
        return users[:10]

StudentService.initialize()

# =========================================
# CONFIG
# =========================================

MAX_QUESTION_LENGTH = 500
SESSION_TIMEOUT = 600
RATE_LIMIT_SECONDS = 0.5

# =========================================
# DATA LOADING (Enhanced with passages)
# =========================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

ALL_QUESTIONS: List[Dict] = []
MCQ_QUESTIONS: List[Dict] = []
QUESTIONS_BY_DIFFICULTY: Dict[str, List[Dict]] = defaultdict(list)
QUESTIONS_BY_SKILL: Dict[str, List[Dict]] = defaultdict(list)

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

def extract_all_questions(data, depth=0, parent_passage="", parent_section=""):
    """Enhanced extraction with passage and section tracking"""
    questions = []
    if depth > 10:
        return questions
    
    if isinstance(data, dict):
        # Get passage from parent context
        passage_text = data.get("passage", {})
        if isinstance(passage_text, dict):
            passage_text = passage_text.get("text", "")
        elif isinstance(passage_text, str):
            passage_text = passage_text
        else:
            passage_text = parent_passage
        
        section_title = data.get("section_title", data.get("title", parent_section))
        
        if "prompt" in data and "question_id" in data:
            q_data = {
                "question_id": data.get("question_id", ""),
                "prompt": data.get("prompt", ""),
                "question": data.get("prompt", ""),
                "explanation": data.get("explanation", ""),
                "answer_key": data.get("answer_key", ""),
                "choices": data.get("choices", data.get("options", [])),
                "difficulty": data.get("difficulty", "medium"),
                "skill": data.get("skill", "عام"),
                "passage": passage_text or data.get("passage_text", ""),
                "section_title": section_title,
                "question_type": ""
            }
            questions.append(q_data)
        
        elif "question" in data:
            q_data = {
                "question_id": data.get("id", data.get("question_id", "")),
                "prompt": data.get("question", ""),
                "question": data.get("question", ""),
                "explanation": data.get("explanation", data.get("answer", "")),
                "answer_key": data.get("answer_key", data.get("correct", "")),
                "choices": data.get("choices", data.get("options", [])),
                "difficulty": data.get("difficulty", "medium"),
                "skill": data.get("skill", "عام"),
                "passage": passage_text or data.get("passage_text", ""),
                "section_title": section_title,
                "question_type": ""
            }
            questions.append(q_data)
        
        # Get passage for children
        child_passage = passage_text if passage_text else parent_passage
        child_section = section_title if section_title else parent_section
        
        for key in ["questions", "sections", "lessons", "items", "exercises"]:
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    questions.extend(extract_all_questions(item, depth+1, child_passage, child_section))
        
        for key, value in data.items():
            if key not in ["questions", "sections", "lessons", "items", "exercises", "passage"]:
                if isinstance(value, (dict, list)):
                    questions.extend(extract_all_questions(value, depth+1, child_passage, child_section))
    
    elif isinstance(data, list):
        for item in data:
            questions.extend(extract_all_questions(item, depth+1, parent_passage, parent_section))
    
    return questions

def load_all_data():
    global ALL_QUESTIONS, MCQ_QUESTIONS, QUESTIONS_BY_DIFFICULTY, QUESTIONS_BY_SKILL
    ALL_QUESTIONS = []
    MCQ_QUESTIONS = []
    QUESTIONS_BY_DIFFICULTY = defaultdict(list)
    QUESTIONS_BY_SKILL = defaultdict(list)
    seen = set()
    
    if not DATA_DIR.exists():
        print(f"❌ DATA FOLDER NOT FOUND at {DATA_DIR}")
        DATA_DIR.mkdir(exist_ok=True)
        return
    
    files = list(DATA_DIR.glob("*.json"))
    print(f"📚 FOUND {len(files)} FILES in {DATA_DIR}")
    
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
                        QUESTIONS_BY_SKILL[q.get("skill", "عام")].append(q)
                
                print(f"✅ Loaded: {file.name} -> {len(questions)} questions")
        except Exception as e:
            print(f"❌ ERROR loading {file.name}: {e}")
    
    print(f"🔥 TOTAL: {len(ALL_QUESTIONS)} | MCQ: {len(MCQ_QUESTIONS)}")
    print(f"🎯 SKILLS: {dict(Counter(q.get('skill', 'عام') for q in ALL_QUESTIONS))}")

load_all_data()

# =========================================
# SESSION MANAGEMENT (Enhanced)
# =========================================

class ExamSession:
    def __init__(self, questions: List[Dict], level: str = "medium", mode: str = "normal"):
        self.questions = questions
        self.current_index = 0
        self.score = 0
        self.total = len(questions)
        self.level = level
        self.active = True
        self.mode = mode
        self.last_activity = time.time()
        self.wrong_questions = []
        self.wrong_skills = []
        self.all_skills = []
        self.questions_ids = [q.get("question_id", "") for q in questions]
    
    def is_expired(self) -> bool:
        return time.time() - self.last_activity > SESSION_TIMEOUT
    
    def check_answer(self, user_answer: int, username: str = None) -> Dict:
        self.last_activity = time.time()
        question = self.questions[self.current_index]
        
        correct_idx = get_answer_index(question)
        user_idx = user_answer - 1
        
        is_correct = (correct_idx is not None and correct_idx == user_idx)
        if is_correct:
            self.score += 1
        else:
            self.wrong_questions.append(question.get("question_id", ""))
            skill = question.get("skill", "عام")
            self.wrong_skills.append(skill)
        
        self.all_skills.append(question.get("skill", "عام"))
        
        choices = question.get("choices", [])
        correct_answer_text = ""
        if correct_idx is not None and 0 <= correct_idx < len(choices):
            choice = choices[correct_idx]
            correct_answer_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
        
        # Track asked question
        if username:
            StudentService.add_asked_question(username, question.get("question_id", ""))
        
        result = {
            "correct": is_correct,
            "correct_answer": correct_answer_text,
            "explanation": question.get("explanation", ""),
            "current_score": self.score,
            "question_number": self.current_index + 1,
            "total": self.total,
            "passage": question.get("passage", ""),
            "section_title": question.get("section_title", ""),
            "skill": question.get("skill", "عام"),
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
# HELPER: Get not-asked questions
# =========================================

def get_unasked_questions(questions: List[Dict], username: str, count: int) -> List[Dict]:
    """Get questions not previously asked to user"""
    user_data = StudentService.get_user_data(username)
    asked = set(user_data.get("asked_questions", []))
    
    unasked = [q for q in questions if q.get("question_id", "") not in asked]
    
    if len(unasked) >= count:
        return random.sample(unasked, count)
    elif unasked:
        return unasked[:count]
    else:
        # If all questions asked, reset and sample
        return random.sample(questions, min(count, len(questions)))

# =========================================
# RESPONSE GENERATORS (Enhanced)
# =========================================

DIFFICULTY_AR = {"easy": "سهل 🟢", "medium": "متوسط 🟡", "hard": "صعب 🔴"}

SKILL_NAMES_AR = {
    "implicit_reasoning": "الاستنتاج الضمني",
    "main_idea_detection": "الفكرة الرئيسية",
    "evidence_extraction": "استخراج الدليل",
    "rhetoric_analysis": "البلاغة",
    "grammar": "النحو",
    "vocabulary_context": "المفردات",
    "purpose_identification": "تحديد الغرض",
    "critical_reading": "القراءة النقدية",
    "عام": "عام"
}

def format_question_with_passage(q: Dict, index: int, total: int) -> str:
    """Format question with passage if available"""
    msg = ""
    
    passage = q.get("passage", "")
    section = q.get("section_title", "")
    
    if passage:
        msg += f"📖 *{section or 'النص'}*\n{passage[:500]}\n\n{'─' * 25}\n\n"
    
    question_text = q.get("prompt", q.get("question", "سؤال"))[:MAX_QUESTION_LENGTH]
    choices = q.get("choices", [])
    skill = q.get("skill", "عام")
    skill_ar = SKILL_NAMES_AR.get(skill, skill)
    
    msg += f"🧠 *سؤال {index} من {total}* | 🎯 {skill_ar}\n\n"
    msg += f"*{question_text}*\n\n"
    
    if choices:
        for idx, choice in enumerate(choices, 1):
            choice_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
            msg += f"{idx}️⃣ {choice_text}\n"
    
    msg += "\n📝 *ابعت رقم الإجابة* 👇"
    return msg

def generate_exam(level: str = None, skill: str = None, count: int = 5, username: str = None) -> str:
    if not ALL_QUESTIONS:
        return "❌ مفيش أسئلة متاحة"
    
    # Filter by skill first, then level
    if skill:
        filtered = QUESTIONS_BY_SKILL.get(skill, [])
        if not filtered:
            skill_ar = SKILL_NAMES_AR.get(skill, skill)
            return f"❌ مفيش أسئلة لمهارة '{skill_ar}'"
    else:
        filtered = ALL_QUESTIONS.copy()
    
    if level and level in ["easy", "medium", "hard"]:
        filtered = [q for q in filtered if q.get("difficulty") == level]
    
    if not filtered:
        return f"❌ مفيش أسئلة متاحة"
    
    # Avoid repetition
    if username:
        selected = get_unasked_questions(filtered, username, count)
    else:
        selected = random.sample(filtered, min(count, len(filtered)))
    
    level_name = DIFFICULTY_AR.get(level, "شامل 📝")
    skill_name = f" | 🎯 {SKILL_NAMES_AR.get(skill, skill)}" if skill else ""
    
    exam = f"📝 *امتحان {level_name}{skill_name}*\n{'─' * 25}\n\n"
    
    for i, q in enumerate(selected, 1):
        passage = q.get("passage", "")
        if passage:
            exam += f"📖 *{q.get('section_title', 'النص')}*\n{passage[:300]}\n\n"
        
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

def start_interactive_exam(chat_id: str, level: str = "medium", skill: str = None, username: str = None, review_wrong: bool = False) -> str:
    """Start interactive MCQ exam"""
    # Select questions based on mode
    if review_wrong and username:
        wrong_ids = StudentService.get_wrong_questions(username)
        filtered = [q for q in MCQ_QUESTIONS if q.get("question_id", "") in wrong_ids]
        if not filtered:
            return "✅ *مافيش أخطاء سابقة!*\nكل إجاباتك السابقة صحيحة 🎉"
    elif skill:
        filtered = [q for q in MCQ_QUESTIONS if q.get("skill") == skill]
        if not filtered:
            skill_ar = SKILL_NAMES_AR.get(skill, skill)
            return f"❌ مفيش أسئلة MCQ لمهارة '{skill_ar}'"
    else:
        filtered = MCQ_QUESTIONS.copy() if MCQ_QUESTIONS else ALL_QUESTIONS.copy()
    
    if level in ["easy", "medium", "hard"]:
        level_filtered = [q for q in filtered if q.get("difficulty") == level]
        if level_filtered:
            filtered = level_filtered
    
    if not filtered:
        return "❌ عدد الأسئلة غير كافي"
    
    # Avoid repetition
    if username:
        selected = get_unasked_questions(filtered, username, 5)
    else:
        selected = random.sample(filtered, min(5, len(filtered)))
    
    if len(selected) < 2:
        return "❌ عدد الأسئلة غير كافي (محتاج 2 على الأقل)"
    
    mode = "review" if review_wrong else ("skill" if skill else "normal")
    session = ExamSession(selected, level, mode)
    user_sessions[chat_id] = session
    
    return format_question_with_passage(selected[0], 1, len(selected))

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
    
    max_choices = len(session.questions[session.current_index].get("choices", []))
    if answer_num < 1 or answer_num > max_choices:
        return f"❌ *رقم الإجابة يجب أن يكون بين 1 و {max_choices}*"
    
    result = session.check_answer(answer_num, username)
    
    # Build response
    response = ""
    
    if result["correct"]:
        response += "✅ *إجابة صحيحة!* 🎉\n\n"
    else:
        response += f"❌ *إجابة خاطئة*\n✅ *الإجابة الصحيحة: {result['correct_answer']}*\n\n"
    
    # Show explanation
    if result["explanation"]:
        explanation = result["explanation"]
        if len(explanation) > 400:
            explanation = explanation[:397] + "..."
        response += f"📝 *الشرح:*\n{explanation}\n\n"
    else:
        response += f"📝 *الإجابة الصحيحة:* {result['correct_answer']}\n\n"
    
    response += f"📊 *النتيجة: {result['current_score']} / {result['question_number']}*\n\n"
    
    if session.active:
        next_q = session.questions[session.current_index]
        response += format_question_with_passage(next_q, session.current_index + 1, session.total)
    else:
        # Exam finished
        final_score = result["current_score"]
        total = result["total"]
        percentage = int((final_score / total) * 100) if total > 0 else 0
        
        if username:
            StudentService.save_exam_result(username, {
                "correct": final_score,
                "total": total,
                "wrong_questions": session.wrong_questions,
                "wrong_skills": list(set(session.wrong_skills)),
                "all_skills": session.all_skills,
                "questions_ids": session.questions_ids
            })
        
        # Grade and feedback
        emoji = "🏆" if percentage >= 80 else "👍" if percentage >= 60 else "📚"
        comment = "ممتاز! أداء رائع" if percentage >= 80 else "جيد - ركز على الأخطاء" if percentage >= 60 else "محتاج مذاكرة أكتر"
        
        response += f"{emoji} *الامتحان خلص!*\n\n"
        response += f"📊 *النتيجة: {final_score} / {total}*\n"
        response += f"📈 *النسبة: {percentage}%*\n\n"
        response += f"{comment}\n\n"
        
        # Show wrong skills
        if session.wrong_skills:
            wrong_skills_counter = Counter(session.wrong_skills)
            response += "🔧 *المهارات اللي محتاجة تركيز:*\n"
            for skill, count in wrong_skills_counter.most_common(5):
                skill_ar = SKILL_NAMES_AR.get(skill, skill)
                response += f"   ⚠️ {skill_ar} ({count} خطأ)\n"
        
        response += "\n🔄 *جرب:*\n"
        response += "• `اختبرني` - امتحان جديد\n"
        if session.wrong_questions:
            response += "• `امتحنني في أخطائي` - راجع أخطائك\n"
        response += "• `مستوايا` - تحليل شامل"
        
        del user_sessions[chat_id]
    
    return response

def generate_focus_plan() -> str:
    """Smart focus plan based on skill frequency"""
    if not ALL_QUESTIONS:
        return "❌ مفيش بيانات"
    
    skill_counter = Counter(q.get("skill", "عام") for q in ALL_QUESTIONS)
    
    msg = "🎯 *خطة التركيز الذكية*\n" + "─" * 25 + "\n\n"
    msg += "📌 *أهم المهارات:*\n"
    
    for skill, count in skill_counter.most_common(8):
        if skill and skill != "عام":
            skill_ar = SKILL_NAMES_AR.get(skill, skill)
            msg += f"   ⭐ {skill_ar} ({count} سؤال)\n"
    
    msg += f"\n📊 *إحصائيات:*\n"
    msg += f"   📝 الأسئلة: {len(ALL_QUESTIONS)}\n"
    msg += f"   🔤 MCQ: {len(MCQ_QUESTIONS)}\n"
    
    difficulties = Counter(q.get("difficulty", "medium") for q in ALL_QUESTIONS)
    msg += f"   🟢 سهل: {difficulties.get('easy', 0)}\n"
    msg += f"   🟡 متوسط: {difficulties.get('medium', 0)}\n"
    msg += f"   🔴 صعب: {difficulties.get('hard', 0)}\n"
    
    msg += "\n💪 *ركز على المهارات دي*"
    return msg

def get_level_analytics(username: str) -> str:
    """Real level analytics with skill breakdown"""
    user_data = StudentService.get_user_data(username)
    skill_stats = user_data.get("skill_stats", {})
    total_exams = user_data.get("total_exams", 0)
    total_score = user_data.get("total_score", 0)
    
    if total_exams == 0:
        return "📊 *لسه مفيش بيانات*\nجرب تاخد امتحان: `اختبرني`"
    
    avg_percentage = int((total_score / (total_exams * 5)) * 100) if total_exams > 0 else 0
    
    msg = f"📊 *تحليل مستواك*\n{'─' * 25}\n\n"
    msg += f"🏆 *المستوى:* {StudentService._calculate_grade(avg_percentage)}\n"
    msg += f"📈 *المتوسط:* {avg_percentage}%\n"
    msg += f"📝 *عدد الامتحانات:* {total_exams}\n\n"
    
    if skill_stats:
        # Strengths and weaknesses
        strengths = []
        weaknesses = []
        
        for skill, stats in skill_stats.items():
            skill_ar = SKILL_NAMES_AR.get(skill, skill)
            correct = stats.get("correct", 0)
            wrong = stats.get("wrong", 0)
            total = correct + wrong
            
            if total > 0:
                pct = int((correct / total) * 100)
                if pct >= 70:
                    strengths.append((skill_ar, pct))
                else:
                    weaknesses.append((skill_ar, pct))
        
        if strengths:
            msg += "💪 *نقاط القوة:*\n"
            for skill, pct in sorted(strengths, key=lambda x: x[1], reverse=True)[:5]:
                msg += f"   ✅ {skill}: {pct}%\n"
            msg += "\n"
        
        if weaknesses:
            msg += "🔧 *يحتاج تحسين:*\n"
            for skill, pct in sorted(weaknesses, key=lambda x: x[1])[:5]:
                msg += f"   ⚠️ {skill}: {pct}%\n"
                # Suggest practice
                msg += f"      ↳ جرب: `اختبرني في {skill}`\n"
            msg += "\n"
    
    msg += "💡 *نصيحة:*\n"
    if avg_percentage >= 80:
        msg += "🌟 أنت في مستوى متقدم - جرب `امتحان صعب`"
    elif avg_percentage >= 60:
        msg += "👍 مستواك كويس - ركز على المهارات الضعيفة"
    else:
        msg += "💪 ابدأ بـ `امتحان سهل` وركز على `خطة التركيز`"
    
    return msg

def get_leaderboard_text() -> str:
    """Leaderboard display"""
    leaders = StudentService.get_leaderboard()
    
    if not leaders:
        return "📊 *الترتيب*\n\nلسه مفيش بيانات كافية"
    
    msg = "🏆 *أفضل الطلاب*\n" + "─" * 25 + "\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}."
        msg += f"{medal} *{user['name']}* - {user['avg']}% ({user['exams']} امتحان)\n"
    
    return msg

def review_wrong_questions(chat_id: str, username: str) -> str:
    """Start exam with previously wrong questions"""
    return start_interactive_exam(chat_id, "medium", None, username, review_wrong=True)

def get_greeting(username: str = None) -> str:
    name_line = f"\n👤 *{username}*" if username else ""
    return f"""👋 *أهلاً بيك في منصة Pen!*{name_line}

📝 *امتحانات:* `امتحان` - `امتحان سهل` - `متوسط` - `صعب`
🎯 *تفاعلي:* `اختبرني` - `اختبرني في [المهارة]`
📊 *تحليل:* `خطة التركيز` - `مستوايا` - `الترتيب`
📚 *مراجعة:* `امتحنني في أخطائي` - `راجع أخطائي`
💡 *استفسارات:* `اشرحلي` - `فسر` - `قارن`

🎯 *المهارات المتاحة:*
`الاستنتاج` | `البلاغة` | `النحو` | `المفردات` | `القراءة النقدية`"""

# =========================================
# MAIN PROCESSOR
# =========================================

def is_rate_limited(chat_id: str) -> bool:
    current_time = time.time()
    if current_time - LAST_MESSAGE_TIME.get(chat_id, 0) < RATE_LIMIT_SECONDS:
        return True
    LAST_MESSAGE_TIME[chat_id] = current_time
    return False

# Skill detection keywords
SKILL_KEYWORDS = {
    "الاستنتاج": "implicit_reasoning",
    "استنتاج": "implicit_reasoning",
    "البلاغة": "rhetoric_analysis",
    "بلاغة": "rhetoric_analysis",
    "النحو": "grammar",
    "نحو": "grammar",
    "المفردات": "vocabulary_context",
    "مفردات": "vocabulary_context",
    "القراءة": "critical_reading",
    "قراءة": "critical_reading",
    "الفكرة": "main_idea_detection",
    "الدليل": "evidence_extraction",
    "الغرض": "purpose_identification",
}

def extract_skill_from_message(message: str) -> Optional[str]:
    """Extract skill from message"""
    for keyword, skill in SKILL_KEYWORDS.items():
        if keyword in message:
            return skill
    return None

async def process_message(chat_id: str, body: str, username: str = None) -> str:
    try:
        if is_rate_limited(chat_id):
            return ""
        
        # Handle active exam session
        if chat_id in user_sessions:
            session = user_sessions[chat_id]
            if session.active and not session.is_expired():
                return process_exam_answer(chat_id, body, username)
            else:
                del user_sessions[chat_id]
        
        body_lower = body.lower().strip()
        
        # Leaderboard
        if body_lower in ["الترتيب", "ترتيب", "المتصدرين", "أفضل"]:
            return get_leaderboard_text()
        
        # Review wrong questions
        if any(x in body_lower for x in ["امتحنني في أخطائي", "راجع أخطائي", "أخطائي"]):
            if username:
                return review_wrong_questions(chat_id, username)
            return "❌ لازم تسجل دخول الأول"
        
        # Interactive exam with skill
        if any(x in body_lower for x in ["اختبرني", "اختبرنى"]):
            level = "medium"
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower:
                    level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            
            skill = extract_skill_from_message(body_lower)
            return start_interactive_exam(chat_id, level, skill, username)
        
        # Regular exam
        if any(x in body_lower for x in ["امتحان", "اختبار"]):
            level = None
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower:
                    level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            
            skill = extract_skill_from_message(body_lower)
            return generate_exam(level=level, skill=skill, username=username)
        
        # Level analytics
        if body_lower in ["مستوايا", "مستوى", "تحليل"]:
            if username:
                return get_level_analytics(username)
            return "📊 *لسه مفيش بيانات*\nجرب تاخد امتحان: `اختبرني`"
        
        # Focus plan
        if any(x in body_lower for x in ["خطة", "تركيز", "ركز"]):
            return generate_focus_plan()
        
        # Greeting
        if any(x in body_lower for x in ["اهلا", "مرحبا", "سلام", "هاي"]):
            return get_greeting(username)
        
        # Default
        return get_greeting(username)
    
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

@app.get("/api/leaderboard")
async def leaderboard():
    return JSONResponse(StudentService.get_leaderboard())

@app.get("/health")
async def health():
    skills = Counter(q.get("skill", "عام") for q in ALL_QUESTIONS)
    return {
        "status": "healthy",
        "questions": len(ALL_QUESTIONS),
        "mcq": len(MCQ_QUESTIONS),
        "skills": dict(skills.most_common(10))
    }

# =========================================
# SERVE HTML FILES
# =========================================

@app.get("/", response_class=HTMLResponse)
async def auth_page():
    auth_path = BASE_DIR / "auth.html"
    if auth_path.exists():
        return auth_path.read_text(encoding="utf-8")
    return "<h1>auth.html not found</h1>"

@app.get("/app", response_class=HTMLResponse)
async def app_page():
    app_path = BASE_DIR / "app.html"
    if app_path.exists():
        return app_path.read_text(encoding="utf-8")
    return "<h1>app.html not found</h1>"

# =========================================
# STARTUP
# =========================================

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_sessions())
    print("🚀 Pen Platform Advanced V3 started!")
    print(f"📊 {len(ALL_QUESTIONS)} questions | {len(MCQ_QUESTIONS)} MCQ")
    print(f"🎯 Skills: {len(QUESTIONS_BY_SKILL)}")
