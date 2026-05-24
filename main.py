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
from typing import List, Dict, Optional, Set, Tuple
import base64
import tempfile
from datetime import datetime
import hashlib

# =========================================
# APP
# =========================================

app = FastAPI(title="Pen Platform - V6 Fixed")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# SKILL ALIASES - EXACT MATCHING
# =========================================

SKILL_ALIASES = {
    "بلاغة": ["الصورة البيانية", "الأساليب", "المحسنات البديعية", "البلاغة", "التصوير", "اللغة المجازية", "التشبيه", "الاستعارة", "الكناية", "المجاز", "الجناس", "الطباق", "المقابلة", "السجع", "التورية"],
    "نحو": ["الإعراب", "الصرف", "النحو", "تطبيقات نحوية", "التركيب", "التحليل النحوي", "بنية الجملة", "اشتقاق الكلمات", "الاشتقاق", "المجرد والمزيد", "المصادر", "المشتقات", "اسم الفاعل", "اسم المفعول", "صيغ المبالغة", "المبتدأ والخبر", "الفاعل", "المفعول به", "الحال", "التمييز", "المضاف والمضاف إليه"],
    "أدب": ["المدارس الأدبية", "تاريخ الأدب", "الحركات الأدبية", "المدرسة الكلاسيكية", "المدرسة الرومانسية", "المدرسة الواقعية", "مدرسة الديوان", "مدرسة أبولو"],
    "قراءة": ["القراءة النقدية", "الفهم القرائي", "تحليل النص", "تحديد الفكرة", "استخراج الدليل", "الأدلة النصية", "التفاصيل الداعمة"],
    "مفردات": ["استخراج المعنى", "معاني الكلمات", "المفردات في السياق", "الترادف", "التضاد", "المعنى الحقيقي والمجازي"],
    "استنتاج": ["الاستنتاج الضمني", "الاستدلال", "الاستنباط", "التحليل والتركيب", "قراءة ما بين السطور", "فهم المعاني الضمنية"],
    "إعراب": ["الإعراب", "التحليل النحوي", "إعراب الفعل المضارع", "إعراب الأسماء الخمسة", "إعراب المثنى والجمع"],
    "صرف": ["الصرف", "اشتقاق الكلمات", "المجرد والمزيد", "المصادر", "المشتقات"],
    "مدارس": ["المدارس الأدبية", "المدرسة الكلاسيكية", "المدرسة الرومانسية", "المدرسة الواقعية"],
    "صورة": ["الصورة البيانية", "التصوير", "اللغة المجازية", "التشبيه", "الاستعارة", "الكناية", "المجاز"],
    "تفسير": ["شرح المعنى", "تفسير النص", "توضيح المقصود", "فهم المراد"],
    "مقارنة": ["المقارنة", "الموازنة", "أوجه الشبه", "أوجه الاختلاف", "المفاضلة"],
    "فكرة": ["تحديد الفكرة", "الفكرة الرئيسية", "الفكرة المحورية", "المغزى", "استخراج الأفكار", "تصنيف الأفكار"],
    "دليل": ["استخراج الدليل", "الأدلة النصية", "الشاهد من النص", "القرينة", "البرهان"],
    "غرض": ["تحديد الغرض", "غرض الكاتب", "هدف النص", "الرسالة"],
}

SKILL_NAMES_AR = {
    "الصورة البيانية": "الصورة البيانية",
    "الأساليب": "الأساليب",
    "المحسنات البديعية": "المحسنات البديعية",
    "البلاغة": "البلاغة",
    "التصوير": "التصوير",
    "اللغة المجازية": "اللغة المجازية",
    "التشبيه": "التشبيه",
    "الاستعارة": "الاستعارة",
    "الكناية": "الكناية",
    "المجاز": "المجاز",
    "الجناس": "الجناس",
    "الطباق": "الطباق",
    "المقابلة": "المقابلة",
    "السجع": "السجع",
    "التورية": "التورية",
    "الإعراب": "الإعراب",
    "الصرف": "الصرف",
    "النحو": "النحو",
    "تطبيقات نحوية": "تطبيقات نحوية",
    "التركيب": "التركيب",
    "التحليل النحوي": "التحليل النحوي",
    "بنية الجملة": "بنية الجملة",
    "المدارس الأدبية": "المدارس الأدبية",
    "تاريخ الأدب": "تاريخ الأدب",
    "الحركات الأدبية": "الحركات الأدبية",
    "القراءة النقدية": "القراءة النقدية",
    "الفهم القرائي": "الفهم القرائي",
    "تحليل النص": "تحليل النص",
    "تحديد الفكرة": "تحديد الفكرة",
    "استخراج الدليل": "استخراج الدليل",
    "استخراج المعنى": "استخراج المعنى",
    "معاني الكلمات": "معاني الكلمات",
    "المفردات في السياق": "المفردات في السياق",
    "الاستنتاج الضمني": "الاستنتاج الضمني",
    "الاستدلال": "الاستدلال",
    "الاستنباط": "الاستنباط",
    "التحليل والتركيب": "التحليل والتركيب",
    "الفكرة الرئيسية": "الفكرة الرئيسية",
    "المغزى": "المغزى",
    "تحديد الغرض": "تحديد الغرض",
    "غرض الكاتب": "غرض الكاتب",
    "المقارنة": "المقارنة",
    "الموازنة": "الموازنة",
    "شرح المعنى": "شرح المعنى",
    "تفسير النص": "تفسير النص",
    "اشتقاق الكلمات": "اشتقاق الكلمات",
    "المصادر": "المصادر",
    "المشتقات": "المشتقات",
    "اسم الفاعل": "اسم الفاعل",
    "اسم المفعول": "اسم المفعول",
    "صيغ المبالغة": "صيغ المبالغة",
    "العلاقات النصية": "العلاقات النصية",
    "التعبير": "التعبير",
    "الكتابة": "الكتابة",
    "الإنشاء": "الإنشاء",
    "عام": "عام",
}

SKILL_RECOMMENDATIONS = {
    "الصورة البيانية": ["التشبيه", "الاستعارة المكنية", "الاستعارة التصريحية", "المجاز المرسل", "الكناية"],
    "البلاغة": ["التشبيه", "الاستعارة", "الكناية", "المجاز", "الجناس", "الطباق", "المقابلة"],
    "المحسنات البديعية": ["الجناس", "الطباق", "المقابلة", "السجع", "التورية"],
    "النحو": ["المبتدأ والخبر", "الفاعل", "المفعول به", "الحال", "التمييز"],
    "الإعراب": ["إعراب الفعل المضارع", "إعراب الأسماء الخمسة", "إعراب المثنى والجمع", "الحال وأنواعها"],
    "الصرف": ["المجرد والمزيد", "المصادر", "المشتقات", "اسم الفاعل", "اسم المفعول", "صيغ المبالغة"],
    "المفردات في السياق": ["المعاني في السياق", "الترادف", "التضاد", "المعنى الحقيقي والمجازي"],
    "استخراج المعنى": ["استخراج معاني الكلمات", "تعريف المصطلحات", "شرح المفردات"],
    "المدارس الأدبية": ["المدرسة الكلاسيكية", "المدرسة الرومانسية", "المدرسة الواقعية", "مدرسة الديوان", "مدرسة أبولو"],
    "القراءة النقدية": ["تحليل النص", "استخراج الأفكار", "نقد المحتوى", "التمييز بين الرأي والحقيقة"],
    "الاستنتاج الضمني": ["الاستنتاج", "الاستدلال", "قراءة ما بين السطور", "فهم المعاني الضمنية"],
    "تحديد الفكرة": ["تحديد الفكرة العامة", "الأفكار الرئيسية والفرعية", "تلخيص النص", "المغزى من النص"],
    "استخراج الدليل": ["الشاهد من النص", "الدليل", "القرينة", "البرهان"],
    "التحليل والتركيب": ["التحليل", "التركيب", "إعادة الصياغة", "الاستخلاص"],
    "شرح المعنى": ["شرح المعنى", "تفسير النص", "توضيح المقصود", "فهم المراد"],
    "العلاقات النصية": ["علاقات الجمل", "الربط", "الاستدراك", "التعليل", "النتيجة"],
    "المقارنة": ["أوجه الشبه", "أوجه الاختلاف", "الموازنة", "المفاضلة"],
    "تحديد الغرض": ["غرض الكاتب", "هدف النص", "الرسالة", "الغرض من الكتابة"],
    "التعبير": ["التعبير الكتابي", "الإنشاء", "كتابة المقال", "التلخيص"],
}

def resolve_skills(query: str) -> List[str]:
    """Resolve Arabic skill names to actual skill keys"""
    query_lower = query.lower().strip()
    
    # Check aliases first
    for arabic_name, skills in SKILL_ALIASES.items():
        if arabic_name in query_lower:
            return skills
    
    # Check individual skill names
    for skill_name in SKILL_NAMES_AR.keys():
        if skill_name in query_lower:
            return [skill_name]
    
    return []

def get_skill_arabic(skill_key: str) -> str:
    return SKILL_NAMES_AR.get(skill_key, skill_key)

def get_recommendations(skill_key: str) -> List[str]:
    return SKILL_RECOMMENDATIONS.get(skill_key, [])

# =========================================
# STUDENT SERVICE
# =========================================

class StudentService:
    _rtdb = None
    _local_db: Dict = {"users": {}, "reported_questions": []}
    _initialized = False
    
    @classmethod
    def initialize(cls):
        if cls._initialized: return
        cls._initialized = True
        try:
            import firebase_admin
            from firebase_admin import credentials
            b64 = os.getenv("FIREBASE_CREDENTIALS_BASE64", "")
            if b64:
                decoded = base64.b64decode(b64).decode("utf-8")
                with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                    f.write(decoded)
                    temp_path = f.name
                cred = credentials.Certificate(temp_path)
                os.unlink(temp_path)
                try: firebase_admin.get_app()
                except ValueError: firebase_admin.initialize_app(cred, {"databaseURL": "https://forme-6167f-default-rtdb.firebaseio.com"})
                from firebase_admin import db
                cls._rtdb = db
                print("✅ Firebase ready!")
        except ImportError: print("⚠️ firebase_admin not installed")
        except Exception as e: print(f"⚠️ Firebase error: {e}")
    
    @classmethod
    def _now_iso(cls) -> str: return datetime.now().isoformat()
    @classmethod
    def _now_ts(cls) -> int: return int(datetime.now().timestamp() * 1000)
    
    @classmethod
    def create_user(cls, username: str, password: str, name: str = "") -> Dict:
        username = username.strip().lower()
        if cls._rtdb:
            try:
                if cls._rtdb.reference(f"users/{username}").get(): return {"error": "اسم المستخدم موجود بالفعل"}
            except: pass
        if username in cls._local_db["users"]: return {"error": "اسم المستخدم موجود بالفعل"}
        
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        user_data = {"username": username, "password": hashed_password, "name": name or username, "created_at": cls._now_iso(), "chat_id": f"user_{username}", "asked_questions": [], "total_score": 0, "total_exams": 0, "total_questions_answered": 0, "skill_stats": {}, "recent_exams": []}
        cls._local_db["users"][username] = user_data
        if cls._rtdb:
            try: cls._rtdb.reference(f"users/{username}").set(user_data)
            except: pass
        return {"success": True, "username": username, "chat_id": f"user_{username}"}
    
    @classmethod
    def login_user(cls, username: str, password: str) -> Dict:
        username = username.strip().lower()
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        user_data = None
        if cls._rtdb:
            try: user_data = cls._rtdb.reference(f"users/{username}").get()
            except: pass
        if not user_data: user_data = cls._local_db["users"].get(username)
        if not user_data: return {"error": "اسم المستخدم غير موجود"}
        if user_data.get("password") != hashed_password: return {"error": "كلمة المرور غير صحيحة"}
        return {"success": True, "username": username, "name": user_data.get("name", username), "chat_id": f"user_{username}"}
    
    @classmethod
    def get_user_data(cls, username: str) -> Dict:
        if cls._rtdb:
            try:
                data = cls._rtdb.reference(f"users/{username}").get()
                if data: return data
            except: pass
        return cls._local_db["users"].get(username, {})
    
    @classmethod
    def update_user_data(cls, username: str, updates: Dict):
        user_data = cls.get_user_data(username)
        user_data.update(updates)
        cls._local_db["users"][username] = user_data
        if cls._rtdb:
            try: cls._rtdb.reference(f"users/{username}").update(updates)
            except: pass
    
    @classmethod
    def add_asked_question(cls, username: str, question_id: str):
        user_data = cls.get_user_data(username)
        asked = user_data.get("asked_questions", [])
        if question_id not in asked:
            asked.append(question_id)
            if len(asked) > 500: asked = asked[-500:]
            cls.update_user_data(username, {"asked_questions": asked})
    
    @classmethod
    def save_exam_result(cls, username: str, result: Dict):
        correct = result.get("correct", 0)
        total = result.get("total", 1)
        percentage = int((correct / max(total, 1)) * 100)
        wrong_questions = result.get("wrong_questions", [])
        wrong_skills = result.get("wrong_skills", [])
        all_skills = result.get("all_skills", [])
        
        user_data = cls.get_user_data(username)
        skill_stats = user_data.get("skill_stats", {})
        skill_counter = Counter(all_skills)
        wrong_skill_counter = Counter(wrong_skills)
        
        for skill in set(all_skills + wrong_skills):
            if skill not in skill_stats: skill_stats[skill] = {"correct": 0, "wrong": 0, "total": 0}
            skill_stats[skill]["total"] += skill_counter.get(skill, 0)
            skill_stats[skill]["wrong"] += wrong_skill_counter.get(skill, 0)
            skill_stats[skill]["correct"] = skill_stats[skill]["total"] - skill_stats[skill]["wrong"]
        
        # Save recent exams (last 10)
        recent_exams = user_data.get("recent_exams", [])
        recent_exams.append({"correct": correct, "total": total, "percentage": percentage, "wrong_skills": wrong_skills, "wrong_questions": wrong_questions, "timestamp": cls._now_ts()})
        if len(recent_exams) > 10: recent_exams = recent_exams[-10:]
        
        cls.update_user_data(username, {
            "skill_stats": skill_stats,
            "total_exams": user_data.get("total_exams", 0) + 1,
            "total_score": user_data.get("total_score", 0) + correct,
            "total_questions_answered": user_data.get("total_questions_answered", 0) + total,
            "recent_exams": recent_exams
        })
        
        if cls._rtdb:
            try: cls._rtdb.reference(f"students/{username}/exams").push({"score": correct, "total": total, "percentage": percentage, "wrong_questions": wrong_questions, "wrong_skills": wrong_skills, "timestamp": cls._now_ts()})
            except: pass
    
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
        user_data = cls.get_user_data(username)
        recent_exams = user_data.get("recent_exams", [])
        for exam in recent_exams:
            wrong_qs.extend(exam.get("wrong_questions", []))
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
        source = cls._local_db["users"]
        if cls._rtdb:
            try: source = cls._rtdb.reference("users").get() or {}
            except: pass
        for uid, data in source.items():
            if "password" in data:
                total_exams = data.get("total_exams", 0)
                total_score = data.get("total_score", 0)
                total_questions = data.get("total_questions_answered", 0)
                if total_exams > 0 and total_questions > 0:
                    users.append({"name": data.get("name", uid), "avg": int((total_score / total_questions) * 100), "exams": total_exams})
        users.sort(key=lambda x: (x["avg"], x["exams"]), reverse=True)
        return users[:10]
    
    @classmethod
    def report_question(cls, question_id: str, username: str, reason: str = "wrong_answer"):
        report = {"question_id": question_id, "reported_by": username, "reason": reason, "timestamp": cls._now_ts()}
        cls._local_db["reported_questions"].append(report)
        if cls._rtdb:
            try: cls._rtdb.reference(f"reported_questions/{question_id}").push(report)
            except: pass
        return {"success": True}

StudentService.initialize()

# =========================================
# CONFIG
# =========================================

MAX_QUESTION_LENGTH = 400
MAX_PASSAGE_LENGTH = 500
SESSION_TIMEOUT = 900
RATE_LIMIT_SECONDS = 0.3

# =========================================
# DATA LOADING
# =========================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

ALL_QUESTIONS: List[Dict] = []
MCQ_QUESTIONS: List[Dict] = []
QUESTIONS_BY_DIFFICULTY: Dict[str, List[Dict]] = defaultdict(list)
QUESTIONS_BY_SKILL: Dict[str, List[Dict]] = defaultdict(list)
BAD_QUESTIONS: List[Dict] = []
VALIDATION_REPORT: Dict = {}

def detect_question_type(question: Dict) -> str:
    choices = question.get("choices", [])
    if not choices or len(choices) < 2: return "open_text"
    answer_key = str(question.get("answer_key", "")).strip()
    if not answer_key: return "open_text"
    if answer_key.isdigit(): return "mcq"
    if answer_key in ["أ", "ب", "ج", "د"]: return "mcq"
    if answer_key.lower() in ["a", "b", "c", "d"]: return "mcq"
    return "open_text"

def get_answer_index(question: Dict) -> Optional[int]:
    answer_key = str(question.get("answer_key", "")).strip()
    choices = question.get("choices", [])
    if not choices: return None
    if answer_key.isdigit():
        idx = int(answer_key) - 1
        return idx if 0 <= idx < len(choices) else None
    if answer_key in ["أ", "ب", "ج", "د"]: return ["أ", "ب", "ج", "د"].index(answer_key)
    if answer_key.lower() in ["a", "b", "c", "d"]: return ["a", "b", "c", "d"].index(answer_key.lower())
    return None

def validate_question(q: Dict) -> Tuple[bool, str]:
    if not q.get("question") or len(q.get("question", "").strip()) < 5: return False, "سؤال قصير جداً"
    if not q.get("answer_key"): return False, "لا يوجد answer_key"
    answer_idx = get_answer_index(q)
    if answer_idx is None: return False, f"answer_key غير صالح: {q.get('answer_key')}"
    choices = q.get("choices", [])
    if len(choices) < 2: return False, "اختيارات أقل من 2"
    prompt = q.get("prompt", q.get("question", ""))
    if "البيت السابق" in prompt and not q.get("poem") and not q.get("previous_lines") and not q.get("passage"): return False, "يحتاج سياق (بيت سابق)"
    if "النص السابق" in prompt and not q.get("passage") and not q.get("poem"): return False, "يحتاج سياق (نص سابق)"
    if "الأبيات السابقة" in prompt and not q.get("previous_lines") and not q.get("poem"): return False, "يحتاج سياق (أبيات سابقة)"
    return True, "صالح"

def extract_all_questions(data, depth=0, context=None):
    if context is None: context = {"passage": "", "section": "", "poem": "", "previous_lines": []}
    questions = []
    if depth > 15: return questions
    
    if isinstance(data, dict):
        passage_text = ""
        if "passage" in data:
            passage = data["passage"]
            if isinstance(passage, dict): passage_text = passage.get("text", "")
            elif isinstance(passage, str): passage_text = passage
        
        section_title = data.get("section_title", data.get("title", ""))
        poem_text = data.get("poem", data.get("poem_text", ""))
        previous_lines = data.get("previous_lines", data.get("context_lines", []))
        
        new_context = {"passage": passage_text or context["passage"], "section": section_title or context["section"], "poem": poem_text or context["poem"], "previous_lines": previous_lines if previous_lines else context["previous_lines"]}
        
        if "prompt" in data and "question_id" in data:
            questions.append({"question_id": data.get("question_id", ""), "prompt": data.get("prompt", ""), "question": data.get("prompt", ""), "explanation": data.get("explanation", ""), "answer_key": data.get("answer_key", ""), "choices": data.get("choices", data.get("options", [])), "difficulty": data.get("difficulty", "medium"), "skill": data.get("skill", "عام"), "passage": new_context["passage"], "section_title": new_context["section"], "poem": new_context["poem"], "previous_lines": new_context["previous_lines"], "question_type": ""})
        elif "question" in data:
            questions.append({"question_id": data.get("id", data.get("question_id", "")), "prompt": data.get("question", ""), "question": data.get("question", ""), "explanation": data.get("explanation", data.get("answer", "")), "answer_key": data.get("answer_key", data.get("correct", "")), "choices": data.get("choices", data.get("options", [])), "difficulty": data.get("difficulty", "medium"), "skill": data.get("skill", "عام"), "passage": new_context["passage"], "section_title": new_context["section"], "poem": new_context["poem"], "previous_lines": new_context["previous_lines"], "question_type": ""})
        
        for key in ["questions", "sections", "lessons", "items", "exercises", "sub_questions"]:
            if key in data and isinstance(data[key], list):
                for item in data[key]: questions.extend(extract_all_questions(item, depth+1, new_context))
        for key, value in data.items():
            if key not in ["questions", "sections", "lessons", "items", "exercises", "sub_questions", "passage", "poem"]:
                if isinstance(value, (dict, list)): questions.extend(extract_all_questions(value, depth+1, new_context))
    elif isinstance(data, list):
        for item in data: questions.extend(extract_all_questions(item, depth+1, context))
    return questions

def load_all_data():
    global ALL_QUESTIONS, MCQ_QUESTIONS, QUESTIONS_BY_DIFFICULTY, QUESTIONS_BY_SKILL, BAD_QUESTIONS, VALIDATION_REPORT
    ALL_QUESTIONS = []; MCQ_QUESTIONS = []; QUESTIONS_BY_DIFFICULTY = defaultdict(list); QUESTIONS_BY_SKILL = defaultdict(list); BAD_QUESTIONS = []
    seen = set()
    
    if not DATA_DIR.exists(): DATA_DIR.mkdir(exist_ok=True); return
    
    files = list(DATA_DIR.glob("*.json"))
    print(f"📚 {len(files)} files")
    total_extracted = 0; total_valid = 0; total_invalid = 0; invalid_reasons = Counter()
    
    for file in files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                questions = extract_all_questions(data)
                total_extracted += len(questions)
                for q in questions:
                    q_text = str(q.get("question", ""))[:100]
                    if q_text and q_text not in seen:
                        seen.add(q_text)
                        is_valid, reason = validate_question(q)
                        if is_valid:
                            q["question_type"] = detect_question_type(q)
                            # Normalize skill name
                            skill = q.get("skill", "عام")
                            if skill not in SKILL_NAMES_AR:
                                # Try to find matching skill
                                for known_skill in SKILL_NAMES_AR.keys():
                                    if known_skill.lower() in skill.lower() or skill.lower() in known_skill.lower():
                                        q["skill"] = known_skill
                                        break
                            ALL_QUESTIONS.append(q); total_valid += 1
                            if q["question_type"] == "mcq": MCQ_QUESTIONS.append(q)
                            QUESTIONS_BY_DIFFICULTY[q.get("difficulty", "medium")].append(q)
                            QUESTIONS_BY_SKILL[q.get("skill", "عام")].append(q)
                        else:
                            BAD_QUESTIONS.append({"question": q.get("question", "")[:100], "reason": reason, "file": file.name, "skill": q.get("skill", "عام")}); total_invalid += 1; invalid_reasons[reason] += 1
        except Exception as e: print(f"❌ {file.name}: {e}")
    
    VALIDATION_REPORT = {"total_extracted": total_extracted, "total_valid": total_valid, "total_invalid": total_invalid, "invalid_reasons": dict(invalid_reasons.most_common())}
    print(f"\n📊 Valid: {total_valid} | Invalid: {total_invalid}")
    for reason, count in invalid_reasons.most_common(5): print(f"   - {reason}: {count}")
    print(f"🔥 Final: {len(ALL_QUESTIONS)} questions | {len(MCQ_QUESTIONS)} MCQ | {len(QUESTIONS_BY_SKILL)} skills")

load_all_data()

# =========================================
# SESSION MANAGEMENT (FIXED)
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
    
    def is_expired(self) -> bool:
        return time.time() - self.last_activity > SESSION_TIMEOUT
    
    def has_next(self) -> bool:
        return self.current_index < len(self.questions)
    
    def get_current_question(self) -> Optional[Dict]:
        if self.has_next():
            return self.questions[self.current_index]
        return None
    
    def check_answer(self, user_answer: int, username: str = None) -> Dict:
        """Check answer and advance. Returns result dict."""
        self.last_activity = time.time()
        
        if not self.has_next():
            return {"error": "no_more_questions"}
        
        question = self.questions[self.current_index]
        correct_idx = get_answer_index(question)
        user_idx = user_answer - 1
        is_correct = (correct_idx is not None and correct_idx == user_idx)
        
        if is_correct:
            self.score += 1
        else:
            qid = question.get("question_id", "")
            if qid: self.wrong_questions.append(qid)
            self.wrong_skills.append(question.get("skill", "عام"))
        
        self.all_skills.append(question.get("skill", "عام"))
        
        choices = question.get("choices", [])
        correct_answer_text = ""
        if correct_idx is not None and 0 <= correct_idx < len(choices):
            choice = choices[correct_idx]
            correct_answer_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
        
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
            "poem": question.get("poem", ""),
            "previous_lines": question.get("previous_lines", []),
            "skill": question.get("skill", "عام"),
            "question_id": question.get("question_id", ""),
        }
        
        # Advance to next question
        self.current_index += 1
        
        # Check if exam is finished
        if not self.has_next():
            self.active = False
        
        return result

user_sessions: Dict[str, ExamSession] = {}
LAST_MESSAGE_TIME: Dict[str, float] = {}
ACTIVE_USERS: Dict[str, str] = {}

async def cleanup_expired_sessions():
    while True:
        try:
            expired = [cid for cid, s in user_sessions.items() if s.is_expired()]
            for cid in expired: del user_sessions[cid]
        except: pass
        await asyncio.sleep(60)

# =========================================
# HELPERS
# =========================================

def get_unasked_questions(questions: List[Dict], username: str, count: int) -> List[Dict]:
    user_data = StudentService.get_user_data(username)
    asked = set(user_data.get("asked_questions", []))
    unasked = [q for q in questions if q.get("question_id", "") not in asked]
    if len(unasked) >= count: return random.sample(unasked, count)
    elif unasked: return unasked[:count]
    return random.sample(questions, min(count, len(questions)))

def filter_by_skills_exact(questions: List[Dict], skill_query: str) -> List[Dict]:
    """Filter questions by exact skill matching"""
    resolved_skills = resolve_skills(skill_query)
    if not resolved_skills: return []
    
    # Make lowercase set for matching
    resolved_lower = set(s.lower() for s in resolved_skills)
    
    filtered = []
    for q in questions:
        q_skill = q.get("skill", "عام").lower()
        # Exact match or substring match
        for rs in resolved_lower:
            if rs in q_skill or q_skill in rs:
                filtered.append(q)
                break
    
    return filtered

def format_context(q: Dict) -> str:
    parts = []
    previous_lines = q.get("previous_lines", [])
    if previous_lines:
        if isinstance(previous_lines, list):
            lines_text = "\n".join(str(l) for l in previous_lines[:3])
            if len(lines_text) > MAX_PASSAGE_LENGTH: lines_text = lines_text[:MAX_PASSAGE_LENGTH-3] + "..."
            parts.append(f"📜 *الأبيات:*\n{lines_text}")
        elif isinstance(previous_lines, str):
            text = str(previous_lines)[:MAX_PASSAGE_LENGTH]
            parts.append(f"📜 *النص السابق:*\n{text}")
    
    poem = q.get("poem", "")
    if poem:
        poem_text = str(poem)[:MAX_PASSAGE_LENGTH]
        if len(str(poem)) > MAX_PASSAGE_LENGTH: poem_text += "\n..."
        parts.append(f"📜 *الأبيات:*\n{poem_text}")
    
    passage = q.get("passage", "")
    if passage:
        section = q.get("section_title", "")
        title = f"📖 *{section}*\n" if section else "📖 *النص:*\n"
        passage_text = str(passage)[:MAX_PASSAGE_LENGTH]
        if len(str(passage)) > MAX_PASSAGE_LENGTH: passage_text += "\n..."
        parts.append(f"{title}{passage_text}")
    
    return "\n\n".join(parts) if parts else ""

def format_question_with_context(q: Dict, index: int, total: int) -> str:
    msg = ""
    context = format_context(q)
    if context: msg += f"{context}\n\n{'─' * 25}\n\n"
    
    question_text = str(q.get("prompt", q.get("question", "سؤال")))[:MAX_QUESTION_LENGTH]
    choices = q.get("choices", [])
    skill_ar = get_skill_arabic(q.get("skill", "عام"))
    difficulty = q.get("difficulty", "medium")
    diff_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(difficulty, "🟡")
    
    msg += f"🧠 *سؤال {index} من {total}* | {diff_emoji} | 🎯 {skill_ar}\n\n"
    msg += f"*{question_text}*\n\n"
    
    if choices:
        for idx, choice in enumerate(choices, 1):
            choice_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
            msg += f"{idx}️⃣ {choice_text}\n"
    
    msg += "\n📝 *ابعت رقم الإجابة* 👇\n"
    msg += "🚨 `تقرير` للإبلاغ عن خطأ"
    return msg

def get_recommendations_text(skills: List[str]) -> str:
    topics = set()
    for skill in skills:
        recs = get_recommendations(skill)
        for r in recs: topics.add(r)
    if not topics: return ""
    return "📚 *راجع:*\n" + "\n".join([f"• {t}" for t in sorted(topics)[:8]])

def get_last_wrong_summary(username: str) -> str:
    """Show summary of last wrong questions"""
    user_data = StudentService.get_user_data(username)
    recent_exams = user_data.get("recent_exams", [])
    
    if not recent_exams:
        return "📝 *لسه مفيش أخطاء سابقة*\n\n🎯 جرب: `اختبرني`"
    
    # Get wrong questions from last exam
    last_exam = recent_exams[-1]
    wrong_qs = last_exam.get("wrong_questions", [])
    wrong_skills = last_exam.get("wrong_skills", [])
    
    if not wrong_qs:
        return "✅ *آخر امتحان كان كله صح!* 🎉\n\n🔄 جرب: `اختبرني صعب`"
    
    msg = f"📝 *آخر أخطائك* ({last_exam.get('correct', 0)}/{last_exam.get('total', 0)})\n{'─' * 25}\n\n"
    
    # Group by skill
    skill_counts = Counter(wrong_skills)
    for i, (skill, count) in enumerate(skill_counts.most_common(5), 1):
        skill_ar = get_skill_arabic(skill)
        msg += f"{i}. {skill_ar} ({count} خطأ)\n"
    
    msg += f"\n📚 *راجع أخطائك:* `امتحنني في أخطائي`"
    return msg

# =========================================
# RESPONSE GENERATORS
# =========================================

DIFFICULTY_AR = {"easy": "سهل 🟢", "medium": "متوسط 🟡", "hard": "صعب 🔴"}

def generate_exam(level: str = None, skill_query: str = None, count: int = 5, username: str = None) -> str:
    if not ALL_QUESTIONS: return "❌ مفيش أسئلة متاحة"
    
    filtered = ALL_QUESTIONS.copy()
    if skill_query:
        skill_filtered = filter_by_skills_exact(filtered, skill_query)
        if not skill_filtered:
            available = set()
            for q in ALL_QUESTIONS[:50]: available.add(q.get("skill", "عام"))
            return f"❌ مفيش أسئلة لـ '{skill_query}'\n\n🎯 *المهارات:*\n" + "\n".join([f"• {s}" for s in sorted(available)[:10]])
        filtered = skill_filtered
    
    if level and level in ["easy", "medium", "hard"]:
        filtered = [q for q in filtered if q.get("difficulty") == level]
    if not filtered: return "❌ مفيش أسئلة متاحة"
    
    selected = get_unasked_questions(filtered, username, count) if username else random.sample(filtered, min(count, len(filtered)))
    level_name = DIFFICULTY_AR.get(level, "شامل 📝")
    skill_name = f" | 🎯 {skill_query}" if skill_query else ""
    
    exam = f"📝 *امتحان {level_name}{skill_name}*\n{'─' * 25}\n\n"
    for i, q in enumerate(selected, 1):
        context = format_context(q)
        if context: exam += f"{context}\n\n"
        question_text = str(q.get("prompt", "سؤال"))[:MAX_QUESTION_LENGTH]
        q_type = q.get("question_type", "")
        type_label = "📝" if q_type == "open_text" else "🔤"
        difficulty = q.get("difficulty", "medium")
        diff_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(difficulty, "🟡")
        skill_ar = get_skill_arabic(q.get("skill", "عام"))
        exam += f"*{i}. {type_label}* {diff_emoji} [{skill_ar}] {question_text}\n"
        if q_type == "mcq" and q.get("choices"):
            for idx, choice in enumerate(q.get("choices", []), 1):
                choice_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
                exam += f"   {idx}️⃣ {choice_text}\n"
            exam += "\n"
    exam += f"{'─' * 25}\n📝 *{len(selected)} سؤال*\n💪 *ربنا معاك يا بطل*"
    return exam

def start_interactive_exam(chat_id: str, level: str = "medium", skill_query: str = None, username: str = None, review_wrong: bool = False) -> str:
    if review_wrong and username:
        wrong_ids = StudentService.get_wrong_questions(username)
        if not wrong_ids: return "✅ *مافيش أخطاء سابقة!*\nكل إجاباتك صحيحة 🎉\n\n🔄 جرب: `اختبرني`"
        filtered = [q for q in MCQ_QUESTIONS if q.get("question_id", "") in wrong_ids]
        if not filtered: return "✅ *مافيش أخطاء!*"
        mode = "review"
    elif skill_query:
        filtered = filter_by_skills_exact(MCQ_QUESTIONS if MCQ_QUESTIONS else ALL_QUESTIONS, skill_query)
        if not filtered:
            available = set()
            for q in ALL_QUESTIONS[:50]: available.add(q.get("skill", "عام"))
            return f"❌ مفيش أسئلة لـ '{skill_query}'\n\n🎯 *المهارات:*\n" + "\n".join([f"• {s}" for s in sorted(available)[:10]])
        mode = "skill"
    else:
        filtered = MCQ_QUESTIONS.copy() if MCQ_QUESTIONS else ALL_QUESTIONS.copy()
        mode = "normal"
    
    if level in ["easy", "medium", "hard"]:
        level_filtered = [q for q in filtered if q.get("difficulty") == level]
        if level_filtered: filtered = level_filtered
    if not filtered: return "❌ عدد الأسئلة غير كافي"
    
    selected = get_unasked_questions(filtered, username, 5) if username and not review_wrong else random.sample(filtered, min(5, len(filtered)))
    if len(selected) < 2: return "❌ عدد الأسئلة غير كافي"
    
    session = ExamSession(selected, level, mode)
    user_sessions[chat_id] = session
    return format_question_with_context(selected[0], 1, len(selected))

def process_exam_answer(chat_id: str, user_answer: str, username: str = None) -> str:
    session = user_sessions.get(chat_id)
    if not session: return "⏰ *الجلسة انتهت*\nاكتب `اختبرني` لبدء امتحان جديد"
    
    # Handle report
    if "تقرير" in user_answer or "بلغ" in user_answer:
        current_q = session.questions[min(session.current_index, len(session.questions)-1)]
        qid = current_q.get("question_id", "")
        if username and qid:
            StudentService.report_question(qid, username)
        if session.has_next():
            return "✅ *تم الإبلاغ*\n\n" + format_question_with_context(session.questions[session.current_index], session.current_index + 1, session.total)
        return "✅ *تم الإبلاغ*"
    
    try:
        numbers = re.findall(r'\d+', user_answer)
        if not numbers: return "❌ *ابعت رقم الإجابة*\n🚨 `تقرير` للإبلاغ عن خطأ"
        answer_num = int(numbers[0])
    except:
        return "❌ *ابعت رقم الإجابة فقط*"
    
    current_q = session.questions[session.current_index]
    max_choices = len(current_q.get("choices", []))
    if answer_num < 1 or answer_num > max(4, max_choices):
        return f"❌ *من 1 إلى {max(4, max_choices)}*"
    
    try:
        result = session.check_answer(answer_num, username)
    except Exception as e:
        print(f"❌ Check error: {e}")
        del user_sessions[chat_id]
        return f"❌ *حصل خطأ*\nتم إلغاء الامتحان\n\n🔄 `اختبرني`"
    
    if "error" in result:
        del user_sessions[chat_id]
        return "❌ *انتهى الامتحان*\n\n🔄 `اختبرني`"
    
    response = ""
    if result["correct"]: response += "✅ *صحيح!* 🎉\n\n"
    else: response += f"❌ *خطأ*\n✅ *الصحيحة: {result['correct_answer']}*\n\n"
    
    if result["explanation"] and len(str(result["explanation"])) > 10:
        explanation = str(result["explanation"])[:400]
        response += f"📝 *الشرح:*\n{explanation}\n\n"
    else:
        response += f"📝 *الإجابة:* {result['correct_answer']}\n\n"
    
    response += f"📊 *{result['current_score']} / {result['question_number']}*\n\n"
    
    # Check if exam continues
    if session.active and session.has_next():
        next_q = session.questions[session.current_index]
        response += format_question_with_context(next_q, session.current_index + 1, session.total)
    else:
        # Exam finished
        final_score = result["current_score"]
        total = result["total"]
        percentage = int((final_score / total) * 100) if total > 0 else 0
        
        if username:
            StudentService.save_exam_result(username, {"correct": final_score, "total": total, "wrong_questions": session.wrong_questions, "wrong_skills": list(set(session.wrong_skills)), "all_skills": session.all_skills})
        
        emoji = "🏆" if percentage >= 80 else "👍" if percentage >= 60 else "📚" if percentage >= 40 else "💪"
        comment = "ممتاز!" if percentage >= 80 else "جيد" if percentage >= 60 else "محتاج مذاكرة" if percentage >= 40 else "لازم تشد حيلك"
        
        response += f"{emoji} *الامتحان خلص!*\n\n📊 *{final_score} / {total}* | 📈 *{percentage}%*\n\n{comment}\n\n"
        
        if session.wrong_skills:
            wrong_counter = Counter(session.wrong_skills)
            response += "🔧 *مهارات تحتاج تركيز:*\n"
            for skill, count in wrong_counter.most_common(5):
                skill_ar = get_skill_arabic(skill)
                response += f"   ⚠️ {skill_ar} ({count} خطأ)\n"
            recs = get_recommendations_text(list(wrong_counter.keys()))
            if recs: response += f"\n{recs}\n"
            response += "\n"
        
        response += "🔄 *جرب:*\n"
        response += "• `اختبرني` - امتحان جديد\n"
        if session.wrong_questions:
            response += "• `امتحنني في أخطائي` 🔥\n"
            response += "• `راجع أخطائي` 📝\n"
        response += "• `مستوايا` - تحليلك\n"
        response += "• `خطة التركيز` - خطتك"
        
        del user_sessions[chat_id]
    
    return response

def generate_focus_plan(username: str = None) -> str:
    msg = "🎯 *خطة التركيز*\n" + "─" * 25 + "\n\n"
    
    if username:
        user_data = StudentService.get_user_data(username)
        recent_exams = user_data.get("recent_exams", [])
        
        if recent_exams:
            # Use recent exams only (last 10 or last 50 questions)
            all_wrong_skills = []
            all_skills = []
            total_recent = 0
            total_correct = 0
            
            for exam in recent_exams:
                total_recent += exam.get("total", 0)
                total_correct += exam.get("correct", 0)
                all_wrong_skills.extend(exam.get("wrong_skills", []))
            
            recent_avg = int((total_correct / max(total_recent, 1)) * 100)
            
            msg += f"📊 *آخر {total_recent} سؤال:*\n"
            msg += f"   📈 المتوسط: {recent_avg}%\n\n"
            
            if all_wrong_skills:
                wrong_counter = Counter(all_wrong_skills)
                msg += "🔧 *أضعف نقاطك (من الأخطاء الأخيرة):*\n"
                for skill, count in wrong_counter.most_common(5):
                    skill_ar = get_skill_arabic(skill)
                    pct = int((count / max(total_recent, 1)) * 100)
                    msg += f"   ⚠️ {skill_ar}: {pct}% خطأ\n"
                    recs = get_recommendations(skill)
                    if recs:
                        msg += f"      📚 {' - '.join(recs[:2])}\n"
                msg += "\n"
    
    # General skill frequency
    skill_counter = Counter(q.get("skill", "عام") for q in ALL_QUESTIONS)
    msg += "📌 *أكثر المهارات في الأسئلة:*\n"
    for skill, count in skill_counter.most_common(6):
        if skill and skill != "عام":
            skill_ar = get_skill_arabic(skill)
            msg += f"   ⭐ {skill_ar} ({count})\n"
    
    msg += f"\n💪 *ابدأ بأضعف نقطة عندك*"
    return msg

def get_level_analytics(username: str) -> str:
    user_data = StudentService.get_user_data(username)
    recent_exams = user_data.get("recent_exams", [])
    total_exams = user_data.get("total_exams", 0)
    total_questions = user_data.get("total_questions_answered", 0)
    total_score = user_data.get("total_score", 0)
    
    if total_exams == 0:
        return "📊 *لسه مفيش بيانات*\n🎯 ابدأ بـ: `اختبرني`"
    
    # Recent average (last 50 questions)
    recent_correct = 0
    recent_total = 0
    recent_wrong_skills = []
    for exam in recent_exams:
        recent_correct += exam.get("correct", 0)
        recent_total += exam.get("total", 0)
        recent_wrong_skills.extend(exam.get("wrong_skills", []))
    
    recent_avg = int((recent_correct / max(recent_total, 1)) * 100)
    overall_avg = int((total_score / max(total_questions, 1)) * 100)
    
    msg = f"📊 *تحليل مستواك*\n{'─' * 25}\n\n"
    msg += f"🏆 *المستوى:* {StudentService._calculate_grade(recent_avg)}\n"
    msg += f"📈 *آخر {recent_total} سؤال:* {recent_avg}%\n"
    msg += f"📊 *المتوسط الكلي:* {overall_avg}%\n"
    msg += f"📝 *الامتحانات:* {total_exams} | *الأسئلة:* {total_questions}\n\n"
    
    if recent_wrong_skills:
        wrong_counter = Counter(recent_wrong_skills)
        msg += "🔧 *يحتاج تحسين (آخر النتائج):*\n"
        for skill, count in wrong_counter.most_common(5):
            skill_ar = get_skill_arabic(skill)
            pct = int((count / max(recent_total, 1)) * 100)
            msg += f"   ⚠️ {skill_ar}: {pct}% خطأ\n"
            recs = get_recommendations(skill)
            if recs: msg += f"      📚 {' - '.join(recs[:3])}\n"
        msg += "\n"
    
    msg += "💡 *نصيحة:*\n"
    if recent_avg >= 80: msg += "🌟 مستوى متقدم - جرب `امتحان صعب`"
    elif recent_avg >= 60: msg += "👍 ركز على `خطة التركيز`"
    else: msg += "💪 ابدأ بـ `امتحان سهل`"
    
    return msg

def get_leaderboard_text() -> str:
    leaders = StudentService.get_leaderboard()
    if not leaders: return "📊 *الترتيب*\n\nلسه مفيش بيانات\n🎯 خد امتحان!"
    msg = "🏆 *أفضل الطلاب*\n" + "─" * 25 + "\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}."
        msg += f"{medal} *{user['name']}* - {user['avg']}% ({user['exams']} امتحان)\n"
    msg += "\n💪 *خد امتحان وظهر!*"
    return msg

def review_wrong_questions(chat_id: str, username: str) -> str:
    return start_interactive_exam(chat_id, "medium", None, username, review_wrong=True)

def get_greeting(username: str = None) -> str:
    name_line = f"\n👤 *{username}*" if username else ""
    return f"""👋 *أهلاً بيك في Pen!*{name_line}

📝 *امتحانات:* `امتحان` `سهل` `متوسط` `صعب`
🎯 *تفاعلي:* `اختبرني` `اختبرني في [المهارة]`
📊 *تحليل:* `خطة التركيز` `مستوايا` `الترتيب`
📚 *مراجعة:* `امتحنني في أخطائي` `راجع أخطائي`
🚨 *تقرير:* `تقرير` أثناء الامتحان

🎯 *المهارات:* البلاغة | النحو | الأدب | المفردات | الاستنتاج | الإعراب | الصرف"""

# =========================================
# MAIN PROCESSOR
# =========================================

def is_rate_limited(chat_id: str) -> bool:
    current_time = time.time()
    if current_time - LAST_MESSAGE_TIME.get(chat_id, 0) < RATE_LIMIT_SECONDS: return True
    LAST_MESSAGE_TIME[chat_id] = current_time
    return False

async def process_message(chat_id: str, body: str, username: str = None) -> str:
    try:
        if is_rate_limited(chat_id): return ""
        
        # Active exam session
        if chat_id in user_sessions:
            session = user_sessions[chat_id]
            if session.active and not session.is_expired():
                return process_exam_answer(chat_id, body, username)
            else:
                del user_sessions[chat_id]
        
        body_lower = body.lower().strip()
        
        if body_lower in ["الترتيب", "ترتيب", "المتصدرين", "أفضل"]: return get_leaderboard_text()
        
        if any(x in body_lower for x in ["راجع أخطائي", "اخر اخطائي", "آخر أخطائي"]):
            if username: return get_last_wrong_summary(username)
            return "❌ سجل دخول الأول"
        
        if any(x in body_lower for x in ["امتحنني في أخطائي", "أخطائي", "اخطائي"]):
            if username: return review_wrong_questions(chat_id, username)
            return "❌ سجل دخول الأول"
        
        if any(x in body_lower for x in ["اختبرني", "اختبرنى"]):
            level = "medium"
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower: level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            skill_query = None
            for word in body_lower.split():
                if word in ["في", "على", "عن", "لـ", "بـ"]: continue
                if resolve_skills(word): skill_query = word; break
            return start_interactive_exam(chat_id, level, skill_query, username)
        
        if any(x in body_lower for x in ["امتحان", "اختبار"]):
            level = None
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower: level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            skill_query = None
            for word in body_lower.split():
                if word in ["في", "على", "عن", "لـ", "بـ"]: continue
                if resolve_skills(word): skill_query = word; break
            return generate_exam(level=level, skill_query=skill_query, username=username)
        
        if body_lower in ["مستوايا", "مستوى", "تحليل", "تحليلي"]:
            if username: return get_level_analytics(username)
            return "📊 *لسه مفيش بيانات*\nجرب: `اختبرني`"
        
        if any(x in body_lower for x in ["خطة", "تركيز", "ركز"]): return generate_focus_plan(username)
        
        if any(x in body_lower for x in ["اهلا", "مرحبا", "سلام", "هاي", "مساعدة", "help"]): return get_greeting(username)
        
        resolved = resolve_skills(body_lower)
        if resolved: return start_interactive_exam(chat_id, "medium", body_lower, username)
        
        return get_greeting(username)
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback; traceback.print_exc()
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
        if not username or not password: return JSONResponse({"error": "مطلوب"}, status_code=400)
        if len(username) < 3: return JSONResponse({"error": "3 أحرف"}, status_code=400)
        if len(password) < 6: return JSONResponse({"error": "6 أحرف"}, status_code=400)
        result = StudentService.create_user(username, password, name)
        if "error" in result: return JSONResponse(result, status_code=400)
        return JSONResponse(result)
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/login")
async def login(request: Request):
    try:
        data = await request.json()
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        if not username or not password: return JSONResponse({"error": "مطلوب"}, status_code=400)
        result = StudentService.login_user(username, password)
        if "error" in result: return JSONResponse(result, status_code=401)
        ACTIVE_USERS[result["chat_id"]] = username
        return JSONResponse(result)
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        chat_id = data.get("chat_id", "")
        message = data.get("message", "").strip()
        username = data.get("username", "")
        if not message: return JSONResponse({"reply": ""})
        ACTIVE_USERS[chat_id] = username
        reply = await process_message(chat_id, message, username)
        return JSONResponse({"reply": reply, "ok": True})
    except Exception as e: return JSONResponse({"reply": "❌ خطأ", "ok": False})

@app.get("/api/leaderboard")
async def leaderboard(): return JSONResponse(StudentService.get_leaderboard())

@app.get("/api/validation")
async def validation(): return JSONResponse(VALIDATION_REPORT)

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "v6", "questions": len(ALL_QUESTIONS), "mcq": len(MCQ_QUESTIONS), "bad": len(BAD_QUESTIONS), "skills": len(QUESTIONS_BY_SKILL)}

@app.get("/", response_class=HTMLResponse)
async def auth_page():
    auth_path = BASE_DIR / "auth.html"
    return auth_path.read_text(encoding="utf-8") if auth_path.exists() else "<h1>not found</h1>"

@app.get("/app", response_class=HTMLResponse)
async def app_page():
    app_path = BASE_DIR / "app.html"
    return app_path.read_text(encoding="utf-8") if app_path.exists() else "<h1>not found</h1>"

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_sessions())
    print(f"🚀 Pen V6 | {len(ALL_QUESTIONS)} valid | {len(BAD_QUESTIONS)} invalid | {len(SKILL_ALIASES)} aliases")
