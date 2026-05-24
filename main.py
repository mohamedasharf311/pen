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
from enum import Enum
import base64
import tempfile
from datetime import datetime
import hashlib

# =========================================
# APP
# =========================================

app = FastAPI(title="Pen Platform - Advanced V5")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================
# COMPLETE SKILL MAPPING
# =========================================

SKILL_ALIASES = {
    "بلاغة": ["rhetoric_analysis", "poetic_imagery_analysis", "rhetorical_device_analysis", "imagery", "rhetoric", "interpretation", "textual_relationship_analysis"],
    "نحو": ["grammar", "parsing", "grammar_rules_application", "morphology", "syntax"],
    "أدب": ["literature", "literary_school_identification", "literary_history"],
    "قراءة": ["reading", "critical_reading", "reading_comprehension", "text_analysis", "idea_identification"],
    "مفردات": ["vocabulary", "vocabulary_context", "definition_extraction", "word_meaning"],
    "استنتاج": ["implicit_reasoning", "inference", "deduction", "synthesis"],
    "فكرة": ["main_idea_detection", "main_idea", "central_idea", "idea_identification"],
    "دليل": ["evidence_extraction", "textual_evidence", "supporting_details"],
    "غرض": ["purpose_identification", "author_purpose", "text_purpose"],
    "تعبير": ["expression", "writing", "composition"],
    "إعراب": ["parsing", "grammar_analysis", "sentence_structure"],
    "صرف": ["morphology", "word_formation", "derivation"],
    "مدارس": ["literary_school_identification", "literary_movements"],
    "صورة": ["poetic_imagery_analysis", "imagery", "figurative_language"],
    "مقارنة": ["compare_and_contrast", "comparison"],
    "تفسير": ["interpretation", "explanation"],
}

SKILL_NAMES_AR = {
    "morphology": "الصرف",
    "parsing": "الإعراب",
    "grammar": "النحو",
    "grammar_rules_application": "تطبيقات نحوية",
    "syntax": "التركيب",
    "grammar_analysis": "التحليل النحوي",
    "sentence_structure": "بنية الجملة",
    "word_formation": "اشتقاق الكلمات",
    "derivation": "الاشتقاق",
    "rhetoric_analysis": "البلاغة",
    "poetic_imagery_analysis": "الصورة البيانية",
    "rhetorical_device_analysis": "المحسنات البديعية",
    "imagery": "التصوير",
    "rhetoric": "البلاغة",
    "figurative_language": "اللغة المجازية",
    "interpretation": "التفسير",
    "explanation": "الشرح",
    "textual_relationship_analysis": "العلاقات النصية",
    "literature": "الأدب",
    "literary_school_identification": "المدارس الأدبية",
    "literary_history": "تاريخ الأدب",
    "literary_movements": "الحركات الأدبية",
    "reading": "القراءة",
    "critical_reading": "القراءة النقدية",
    "reading_comprehension": "الفهم القرائي",
    "text_analysis": "تحليل النص",
    "idea_identification": "تحديد الفكرة",
    "vocabulary": "المفردات",
    "vocabulary_context": "المفردات في السياق",
    "definition_extraction": "استخراج المعنى",
    "word_meaning": "معاني الكلمات",
    "implicit_reasoning": "الاستنتاج الضمني",
    "inference": "الاستدلال",
    "deduction": "الاستنباط",
    "synthesis": "التحليل والتركيب",
    "main_idea_detection": "الفكرة الرئيسية",
    "main_idea": "الفكرة المحورية",
    "central_idea": "المغزى",
    "evidence_extraction": "استخراج الدليل",
    "textual_evidence": "الأدلة النصية",
    "supporting_details": "التفاصيل الداعمة",
    "purpose_identification": "تحديد الغرض",
    "author_purpose": "غرض الكاتب",
    "expression": "التعبير",
    "writing": "الكتابة",
    "composition": "الإنشاء",
    "compare_and_contrast": "المقارنة",
    "comparison": "الموازنة",
    "عام": "عام"
}

# Study recommendations based on skills
SKILL_RECOMMENDATIONS = {
    "poetic_imagery_analysis": ["التشبيه", "الاستعارة المكنية", "الاستعارة التصريحية", "المجاز المرسل", "الكناية"],
    "rhetoric_analysis": ["التشبيه", "الاستعارة", "الكناية", "المجاز", "الجناس", "الطباق", "المقابلة"],
    "rhetorical_device_analysis": ["الجناس", "الطباق", "المقابلة", "السجع", "التورية"],
    "grammar": ["المبتدأ والخبر", "الفاعل", "المفعول به", "الحال", "التمييز", "المضاف والمضاف إليه"],
    "parsing": ["إعراب الفعل المضارع", "إعراب الأسماء الخمسة", "إعراب المثنى والجمع", "الحال وأنواعها", "التمييز"],
    "morphology": ["المجرد والمزيد", "المصادر", "المشتقات", "اسم الفاعل", "اسم المفعول", "صيغ المبالغة"],
    "vocabulary_context": ["المعاني في السياق", "الترادف", "التضاد", "المعنى الحقيقي والمجازي"],
    "definition_extraction": ["استخراج معاني الكلمات", "تعريف المصطلحات", "شرح المفردات"],
    "literary_school_identification": ["المدرسة الكلاسيكية", "المدرسة الرومانسية", "المدرسة الواقعية", "مدرسة الديوان", "مدرسة أبولو"],
    "critical_reading": ["تحليل النص", "استخراج الأفكار", "نقد المحتوى", "التمييز بين الرأي والحقيقة"],
    "implicit_reasoning": ["الاستنتاج", "الاستدلال", "قراءة ما بين السطور", "فهم المعاني الضمنية"],
    "main_idea_detection": ["تحديد الفكرة العامة", "الأفكار الرئيسية والفرعية", "تلخيص النص", "المغزى من النص"],
    "evidence_extraction": ["الشاهد من النص", "الدليل", "القرينة", "البرهان"],
    "synthesis": ["التحليل", "التركيب", "إعادة الصياغة", "الاستخلاص"],
    "interpretation": ["شرح المعنى", "تفسير النص", "توضيح المقصود", "فهم المراد"],
    "textual_relationship_analysis": ["علاقات الجمل", "الربط", "الاستدراك", "التعليل", "النتيجة"],
    "compare_and_contrast": ["أوجه الشبه", "أوجه الاختلاف", "الموازنة", "المفاضلة"],
    "idea_identification": ["استخراج الأفكار", "تصنيف الأفكار", "الأفكار الضمنية", "الأفكار الصريحة"],
    "purpose_identification": ["غرض الكاتب", "هدف النص", "الرسالة", "الغرض من الكتابة"],
    "expression": ["التعبير الكتابي", "الإنشاء", "كتابة المقال", "التلخيص"],
    "grammar_rules_application": ["تطبيق القواعد", "تصحيح الأخطاء", "الضبط النحوي", "علامات الإعراب"],
    "imagery": ["الصور البيانية", "التشبيه", "الاستعارة", "الكناية", "المجاز"],
    "figurative_language": ["اللغة المجازية", "التعبيرات البلاغية", "الصور الفنية", "المحسنات"],
}

def resolve_skills(query: str) -> List[str]:
    """Resolve Arabic skill names to actual skill keys"""
    query_lower = query.lower().strip()
    resolved = []
    
    for arabic_name, skills in SKILL_ALIASES.items():
        if arabic_name in query_lower:
            resolved.extend(skills)
    
    for skill_key, skill_ar in SKILL_NAMES_AR.items():
        if skill_ar in query_lower:
            resolved.append(skill_key)
    
    if not resolved:
        for skill_key in SKILL_NAMES_AR.keys():
            if skill_key.lower() in query_lower:
                resolved.append(skill_key)
    
    return list(set(resolved)) if resolved else []

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
            "total_questions_answered": 0,
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
            if skill not in skill_stats:
                skill_stats[skill] = {"correct": 0, "wrong": 0, "total": 0}
            skill_stats[skill]["total"] += skill_counter.get(skill, 0)
            skill_stats[skill]["wrong"] += wrong_skill_counter.get(skill, 0)
            skill_stats[skill]["correct"] = skill_stats[skill]["total"] - skill_stats[skill]["wrong"]
        
        cls.update_user_data(username, {
            "skill_stats": skill_stats,
            "total_exams": user_data.get("total_exams", 0) + 1,
            "total_score": user_data.get("total_score", 0) + correct,
            "total_questions_answered": user_data.get("total_questions_answered", 0) + total
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

MAX_QUESTION_LENGTH = 600
SESSION_TIMEOUT = 900
RATE_LIMIT_SECONDS = 0.3

# =========================================
# DATA LOADING WITH VALIDATION
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
    """Validate question and return (is_valid, reason)"""
    if not q.get("question") or len(q.get("question", "").strip()) < 5:
        return False, "سؤال قصير جداً"
    
    if not q.get("answer_key"):
        return False, "لا يوجد answer_key"
    
    answer_idx = get_answer_index(q)
    if answer_idx is None:
        return False, f"answer_key غير صالح: {q.get('answer_key')}"
    
    choices = q.get("choices", [])
    if len(choices) < 2:
        return False, "اختيارات أقل من 2"
    
    prompt = q.get("prompt", q.get("question", ""))
    
    if "البيت السابق" in prompt and not q.get("poem") and not q.get("previous_lines") and not q.get("passage"):
        return False, "يحتاج سياق (بيت سابق) غير موجود"
    
    if "النص السابق" in prompt and not q.get("passage") and not q.get("poem"):
        return False, "يحتاج سياق (نص سابق) غير موجود"
    
    if "الأبيات السابقة" in prompt and not q.get("previous_lines") and not q.get("poem"):
        return False, "يحتاج سياق (أبيات سابقة) غير موجود"
    
    return True, "صالح"

def extract_all_questions(data, depth=0, context=None):
    if context is None:
        context = {"passage": "", "section": "", "poem": "", "previous_lines": []}
    
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
        
        new_context = {
            "passage": passage_text or context["passage"],
            "section": section_title or context["section"],
            "poem": poem_text or context["poem"],
            "previous_lines": previous_lines if previous_lines else context["previous_lines"]
        }
        
        if "prompt" in data and "question_id" in data:
            questions.append({
                "question_id": data.get("question_id", ""),
                "prompt": data.get("prompt", ""),
                "question": data.get("prompt", ""),
                "explanation": data.get("explanation", ""),
                "answer_key": data.get("answer_key", ""),
                "choices": data.get("choices", data.get("options", [])),
                "difficulty": data.get("difficulty", "medium"),
                "skill": data.get("skill", "عام"),
                "passage": new_context["passage"],
                "section_title": new_context["section"],
                "poem": new_context["poem"],
                "previous_lines": new_context["previous_lines"],
                "question_type": ""
            })
        elif "question" in data:
            questions.append({
                "question_id": data.get("id", data.get("question_id", "")),
                "prompt": data.get("question", ""),
                "question": data.get("question", ""),
                "explanation": data.get("explanation", data.get("answer", "")),
                "answer_key": data.get("answer_key", data.get("correct", "")),
                "choices": data.get("choices", data.get("options", [])),
                "difficulty": data.get("difficulty", "medium"),
                "skill": data.get("skill", "عام"),
                "passage": new_context["passage"],
                "section_title": new_context["section"],
                "poem": new_context["poem"],
                "previous_lines": new_context["previous_lines"],
                "question_type": ""
            })
        
        for key in ["questions", "sections", "lessons", "items", "exercises", "sub_questions"]:
            if key in data and isinstance(data[key], list):
                for item in data[key]:
                    questions.extend(extract_all_questions(item, depth+1, new_context))
        
        for key, value in data.items():
            if key not in ["questions", "sections", "lessons", "items", "exercises", "sub_questions", "passage", "poem"]:
                if isinstance(value, (dict, list)):
                    questions.extend(extract_all_questions(value, depth+1, new_context))
    
    elif isinstance(data, list):
        for item in data:
            questions.extend(extract_all_questions(item, depth+1, context))
    
    return questions

def load_all_data():
    global ALL_QUESTIONS, MCQ_QUESTIONS, QUESTIONS_BY_DIFFICULTY, QUESTIONS_BY_SKILL, BAD_QUESTIONS, VALIDATION_REPORT
    
    ALL_QUESTIONS = []
    MCQ_QUESTIONS = []
    QUESTIONS_BY_DIFFICULTY = defaultdict(list)
    QUESTIONS_BY_SKILL = defaultdict(list)
    BAD_QUESTIONS = []
    seen = set()
    
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(exist_ok=True)
        return
    
    files = list(DATA_DIR.glob("*.json"))
    print(f"📚 FOUND {len(files)} FILES")
    
    total_extracted = 0
    total_valid = 0
    total_invalid = 0
    invalid_reasons = Counter()
    
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
                        
                        # Validate question
                        is_valid, reason = validate_question(q)
                        
                        if is_valid:
                            q["question_type"] = detect_question_type(q)
                            ALL_QUESTIONS.append(q)
                            total_valid += 1
                            
                            if q["question_type"] == "mcq":
                                MCQ_QUESTIONS.append(q)
                            
                            QUESTIONS_BY_DIFFICULTY[q.get("difficulty", "medium")].append(q)
                            QUESTIONS_BY_SKILL[q.get("skill", "عام")].append(q)
                        else:
                            BAD_QUESTIONS.append({"question": q.get("question", "")[:100], "reason": reason, "file": file.name, "skill": q.get("skill", "عام")})
                            total_invalid += 1
                            invalid_reasons[reason] += 1
                
                print(f"✅ {file.name}: {len(questions)} extracted")
        except Exception as e:
            print(f"❌ ERROR {file.name}: {e}")
    
    VALIDATION_REPORT = {
        "total_extracted": total_extracted,
        "total_valid": total_valid,
        "total_invalid": total_invalid,
        "invalid_reasons": dict(invalid_reasons.most_common()),
        "bad_questions_sample": BAD_QUESTIONS[:20]
    }
    
    print(f"\n📊 VALIDATION REPORT:")
    print(f"   Extracted: {total_extracted}")
    print(f"   ✅ Valid: {total_valid}")
    print(f"   ❌ Invalid: {total_invalid}")
    for reason, count in invalid_reasons.most_common():
        print(f"      - {reason}: {count}")
    
    print(f"\n🔥 FINAL: {len(ALL_QUESTIONS)} questions | {len(MCQ_QUESTIONS)} MCQ")
    print(f"🎯 Skills: {len(QUESTIONS_BY_SKILL)}")

load_all_data()

# =========================================
# SESSION MANAGEMENT
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
    
    def check_answer(self, user_answer: int, username: str = None) -> Dict:
        self.last_activity = time.time()
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

def filter_by_skills(questions: List[Dict], skill_query: str) -> List[Dict]:
    resolved_skills = resolve_skills(skill_query)
    if not resolved_skills: return []
    filtered = []
    for q in questions:
        q_skill = q.get("skill", "").lower()
        for rs in resolved_skills:
            if rs.lower() in q_skill or q_skill in rs.lower():
                filtered.append(q)
                break
    return filtered

def format_context(q: Dict) -> str:
    parts = []
    previous_lines = q.get("previous_lines", [])
    if previous_lines:
        if isinstance(previous_lines, list):
            parts.append("📜 *الأبيات:*\n" + "\n".join(str(l) for l in previous_lines[:5]))
        elif isinstance(previous_lines, str):
            parts.append(f"📜 *النص السابق:*\n{str(previous_lines)[:300]}")
    
    poem = q.get("poem", "")
    if poem:
        parts.append(f"📜 *الأبيات:*\n{str(poem)[:400]}")
    
    passage = q.get("passage", "")
    if passage:
        section = q.get("section_title", "")
        title = f"📖 *{section}*\n" if section else "📖 *النص:*\n"
        parts.append(f"{title}{str(passage)[:600]}")
    
    return "\n\n".join(parts) if parts else ""

def format_question_with_context(q: Dict, index: int, total: int) -> str:
    msg = ""
    context = format_context(q)
    if context:
        msg += f"{context}\n\n{'─' * 25}\n\n"
    
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
    msg += "💡 `تقرير` للإبلاغ عن خطأ"
    return msg

def get_recommendations_text(skills: List[str]) -> str:
    """Get study recommendations based on skills"""
    topics = set()
    for skill in skills:
        recs = get_recommendations(skill)
        for r in recs:
            topics.add(r)
    
    if not topics:
        return ""
    
    return "📚 *راجع الدروس دي:*\n" + "\n".join([f"• {t}" for t in sorted(topics)[:8]])

# =========================================
# RESPONSE GENERATORS
# =========================================

DIFFICULTY_AR = {"easy": "سهل 🟢", "medium": "متوسط 🟡", "hard": "صعب 🔴"}

def generate_exam(level: str = None, skill_query: str = None, count: int = 5, username: str = None) -> str:
    if not ALL_QUESTIONS:
        return "❌ مفيش أسئلة متاحة"
    
    filtered = ALL_QUESTIONS.copy()
    
    if skill_query:
        skill_filtered = filter_by_skills(filtered, skill_query)
        if not skill_filtered:
            available = set()
            for q in ALL_QUESTIONS[:50]:
                available.add(get_skill_arabic(q.get("skill", "عام")))
            return f"❌ مفيش أسئلة لـ '{skill_query}'\n\n🎯 *المهارات المتاحة:*\n" + "\n".join([f"• {s}" for s in sorted(available)[:10]])
        filtered = skill_filtered
    
    if level and level in ["easy", "medium", "hard"]:
        filtered = [q for q in filtered if q.get("difficulty") == level]
    
    if not filtered:
        return "❌ مفيش أسئلة متاحة"
    
    if username:
        selected = get_unasked_questions(filtered, username, count)
    else:
        selected = random.sample(filtered, min(count, len(filtered)))
    
    level_name = DIFFICULTY_AR.get(level, "شامل 📝")
    skill_name = f" | 🎯 {skill_query}" if skill_query else ""
    
    exam = f"📝 *امتحان {level_name}{skill_name}*\n{'─' * 25}\n\n"
    
    for i, q in enumerate(selected, 1):
        context = format_context(q)
        if context:
            exam += f"{context}\n\n"
        
        question_text = str(q.get("prompt", "سؤال"))[:MAX_QUESTION_LENGTH]
        q_type = q.get("question_type", "")
        type_label = "📝" if q_type == "open_text" else "🔤"
        skill_ar = get_skill_arabic(q.get("skill", "عام"))
        
        exam += f"*{i}. {type_label}* [{skill_ar}] {question_text}\n"
        
        if q_type == "mcq" and q.get("choices"):
            for idx, choice in enumerate(q.get("choices", []), 1):
                choice_text = choice.get("text", str(choice)) if isinstance(choice, dict) else str(choice)
                exam += f"   {idx}️⃣ {choice_text}\n"
            exam += "\n"
    
    exam += f"{'─' * 25}\n📝 *عدد الأسئلة: {len(selected)}*\n💪 *ربنا معاك يا بطل*"
    return exam

def start_interactive_exam(chat_id: str, level: str = "medium", skill_query: str = None, username: str = None, review_wrong: bool = False) -> str:
    if review_wrong and username:
        wrong_ids = StudentService.get_wrong_questions(username)
        if not wrong_ids:
            return "✅ *مافيش أخطاء سابقة!*\nكل إجاباتك السابقة صحيحة 🎉\n\n🔄 جرب: `اختبرني` لامتحان جديد"
        
        filtered = [q for q in MCQ_QUESTIONS if q.get("question_id", "") in wrong_ids]
        if not filtered:
            return "✅ *مافيش أخطاء سابقة!*"
        mode = "review"
    elif skill_query:
        filtered = filter_by_skills(MCQ_QUESTIONS if MCQ_QUESTIONS else ALL_QUESTIONS, skill_query)
        if not filtered:
            available = set()
            for q in ALL_QUESTIONS[:50]:
                available.add(get_skill_arabic(q.get("skill", "عام")))
            return f"❌ مفيش أسئلة لـ '{skill_query}'\n\n🎯 *المهارات المتاحة:*\n" + "\n".join([f"• {s}" for s in sorted(available)[:10]])
        mode = "skill"
    else:
        filtered = MCQ_QUESTIONS.copy() if MCQ_QUESTIONS else ALL_QUESTIONS.copy()
        mode = "normal"
    
    if level in ["easy", "medium", "hard"]:
        level_filtered = [q for q in filtered if q.get("difficulty") == level]
        if level_filtered:
            filtered = level_filtered
    
    if not filtered:
        return "❌ عدد الأسئلة غير كافي"
    
    if username and not review_wrong:
        selected = get_unasked_questions(filtered, username, 5)
    else:
        selected = random.sample(filtered, min(5, len(filtered)))
    
    if len(selected) < 2:
        return "❌ عدد الأسئلة غير كافي (محتاج 2 على الأقل)"
    
    session = ExamSession(selected, level, mode)
    user_sessions[chat_id] = session
    
    return format_question_with_context(selected[0], 1, len(selected))

def process_exam_answer(chat_id: str, user_answer: str, username: str = None) -> str:
    session = user_sessions.get(chat_id)
    if not session:
        return "⏰ *الجلسة انتهت*\nاكتب `اختبرني` لبدء امتحان جديد"
    
    if "تقرير" in user_answer or "بلغ" in user_answer:
        idx = max(0, session.current_index - 1)
        if idx < len(session.questions):
            q = session.questions[idx]
            qid = q.get("question_id", "")
            if username and qid:
                StudentService.report_question(qid, username)
                if session.active:
                    next_q = session.questions[session.current_index]
                    return "✅ *تم الإبلاغ*\n\n" + format_question_with_context(next_q, session.current_index + 1, session.total)
                return "✅ *تم الإبلاغ*"
    
    try:
        numbers = re.findall(r'\d+', user_answer)
        if not numbers:
            return "❌ *ابعت رقم الإجابة فقط*\n💡 أو اكتب `تقرير` للإبلاغ عن خطأ"
        answer_num = int(numbers[0])
    except:
        return "❌ *ابعت رقم الإجابة فقط*"
    
    current_q = session.questions[session.current_index]
    max_choices = len(current_q.get("choices", []))
    
    if answer_num < 1 or answer_num > max(4, max_choices):
        return f"❌ *رقم الإجابة يجب أن يكون بين 1 و {max(4, max_choices)}*"
    
    try:
        result = session.check_answer(answer_num, username)
    except Exception as e:
        print(f"❌ Check answer error: {e}")
        del user_sessions[chat_id]
        return f"❌ *حصل خطأ في السؤال*\nتم إلغاء الامتحان.\n\n🔄 جرب: `اختبرني`\n\n💡 استخدم `تقرير` للإبلاغ عن الأسئلة الخاطئة"
    
    response = ""
    
    if result["correct"]:
        response += "✅ *إجابة صحيحة!* 🎉\n\n"
    else:
        response += f"❌ *إجابة خاطئة*\n✅ *الإجابة الصحيحة: {result['correct_answer']}*\n\n"
    
    if result["explanation"] and len(str(result["explanation"])) > 10:
        explanation = str(result["explanation"])
        if len(explanation) > 400:
            explanation = explanation[:397] + "..."
        response += f"📝 *الشرح:*\n{explanation}\n\n"
    else:
        response += f"📝 *الإجابة الصحيحة:* {result['correct_answer']}\n\n"
    
    response += f"📊 *النتيجة: {result['current_score']} / {result['question_number']}*\n\n"
    
    if session.active:
        next_q = session.questions[session.current_index]
        response += format_question_with_context(next_q, session.current_index + 1, session.total)
    else:
        final_score = result["current_score"]
        total = result["total"]
        percentage = int((final_score / total) * 100) if total > 0 else 0
        
        if username:
            StudentService.save_exam_result(username, {
                "correct": final_score,
                "total": total,
                "wrong_questions": session.wrong_questions,
                "wrong_skills": list(set(session.wrong_skills)),
                "all_skills": session.all_skills
            })
        
        emoji = "🏆" if percentage >= 80 else "👍" if percentage >= 60 else "📚" if percentage >= 40 else "💪"
        comment = "ممتاز!" if percentage >= 80 else "جيد" if percentage >= 60 else "محتاج مذاكرة" if percentage >= 40 else "لازم تشد حيلك"
        
        response += f"{emoji} *الامتحان خلص!*\n\n"
        response += f"📊 *النتيجة: {final_score} / {total}*\n"
        response += f"📈 *النسبة: {percentage}%*\n\n"
        response += f"{comment}\n\n"
        
        if session.wrong_skills:
            wrong_counter = Counter(session.wrong_skills)
            response += "🔧 *مهارات تحتاج تركيز:*\n"
            for skill, count in wrong_counter.most_common(5):
                skill_ar = get_skill_arabic(skill)
                response += f"   ⚠️ {skill_ar} ({count} خطأ)\n"
            
            # Add recommendations
            recs = get_recommendations_text(list(wrong_counter.keys()))
            if recs:
                response += f"\n{recs}\n"
            response += "\n"
        
        response += "🔄 *إيه اللي جاي:*\n"
        response += "• `اختبرني` - امتحان جديد\n"
        if session.wrong_questions:
            response += "• `امتحنني في أخطائي` - راجع أخطائك 🔥\n"
        response += "• `مستوايا` - تحليل شامل\n"
        response += "• `خطة التركيز` - خطتك الشخصية"
        
        del user_sessions[chat_id]
    
    return response

def generate_focus_plan(username: str = None) -> str:
    msg = "🎯 *خطة التركيز*\n" + "─" * 25 + "\n\n"
    
    if username:
        user_data = StudentService.get_user_data(username)
        skill_stats = user_data.get("skill_stats", {})
        
        if skill_stats:
            msg += "📊 *تحليل أدائك الشخصي:*\n\n"
            
            skill_scores = {}
            for skill, stats in skill_stats.items():
                total = stats.get("total", 0)
                wrong = stats.get("wrong", 0)
                if total > 0:
                    pct = int(((total - wrong) / total) * 100)
                    skill_scores[skill] = {"percentage": pct, "total": total, "wrong": wrong}
            
            sorted_skills = sorted(skill_scores.items(), key=lambda x: x[1]["percentage"])
            
            if sorted_skills:
                msg += "🔧 *أضعف نقاطك:*\n"
                shown = 0
                for skill, data in sorted_skills:
                    if data["percentage"] < 70 and shown < 5:
                        skill_ar = get_skill_arabic(skill)
                        msg += f"   ⚠️ {skill_ar}: {data['percentage']}% ({data['wrong']} أخطاء)\n"
                        shown += 1
                
                if shown == 0:
                    msg += "   💪 كل مهاراتك فوق 70% - استمر!\n"
                
                msg += "\n💪 *متمكن منه:*\n"
                strong = [s for s in sorted_skills if s[1]["percentage"] >= 80]
                if strong:
                    for skill, data in strong[:3]:
                        skill_ar = get_skill_arabic(skill)
                        msg += f"   ✅ {skill_ar}: {data['percentage']}%\n"
                else:
                    msg += "   استمر في التدريب 💪\n"
                
                # Recommendations for weakest skill
                if sorted_skills and sorted_skills[0][1]["percentage"] < 70:
                    weakest_skill = sorted_skills[0][0]
                    recs = get_recommendations(weakest_skill)
                    if recs:
                        msg += f"\n📚 *ابدأ بمراجعة:*\n"
                        for r in recs[:5]:
                            msg += f"• {r}\n"
                
                msg += "\n"
    
    skill_counter = Counter(q.get("skill", "عام") for q in ALL_QUESTIONS)
    msg += "📌 *أكثر المهارات في الأسئلة:*\n"
    for skill, count in skill_counter.most_common(8):
        if skill and skill != "عام":
            skill_ar = get_skill_arabic(skill)
            msg += f"   ⭐ {skill_ar} ({count} سؤال)\n"
    
    msg += f"\n📊 *الإجمالي:* {len(ALL_QUESTIONS)} سؤال | {len(MCQ_QUESTIONS)} MCQ\n"
    msg += "💪 *ركز على نقاط ضعفك الأول*"
    
    return msg

def get_level_analytics(username: str) -> str:
    user_data = StudentService.get_user_data(username)
    skill_stats = user_data.get("skill_stats", {})
    total_exams = user_data.get("total_exams", 0)
    total_score = user_data.get("total_score", 0)
    total_questions = user_data.get("total_questions_answered", 0)
    
    if total_exams == 0:
        return "📊 *لسه مفيش بيانات*\n\n🎯 ابدأ بـ:\n• `اختبرني` - امتحان تفاعلي\n• `امتحان` - أسئلة متوقعة"
    
    avg_percentage = int((total_score / total_questions) * 100) if total_questions > 0 else 0
    
    msg = f"📊 *تحليل مستواك*\n{'─' * 25}\n\n"
    msg += f"🏆 *المستوى:* {StudentService._calculate_grade(avg_percentage)}\n"
    msg += f"📈 *المتوسط:* {avg_percentage}%\n"
    msg += f"📝 *الامتحانات:* {total_exams} | *أسئلة:* {total_questions} | *صحيح:* {total_score}\n\n"
    
    if skill_stats:
        skill_scores = {}
        for skill, stats in skill_stats.items():
            total = stats.get("total", 0)
            wrong = stats.get("wrong", 0)
            if total > 0:
                pct = int(((total - wrong) / total) * 100)
                skill_scores[skill] = {"percentage": pct, "total": total, "wrong": wrong}
        
        sorted_skills = sorted(skill_scores.items(), key=lambda x: x[1]["percentage"])
        
        weak = [(s, d) for s, d in sorted_skills if d["percentage"] < 70]
        if weak:
            msg += "🔧 *يحتاج تحسين:*\n"
            for skill, data in weak[:5]:
                skill_ar = get_skill_arabic(skill)
                msg += f"   ⚠️ {skill_ar}: {data['percentage']}%\n"
                recs = get_recommendations(skill)
                if recs:
                    msg += f"      📚 راجع: {' - '.join(recs[:3])}\n"
            msg += "\n"
        
        strong = [(s, d) for s, d in sorted_skills if d["percentage"] >= 80]
        if strong:
            msg += "💪 *نقاط القوة:*\n"
            for skill, data in strong[:5]:
                skill_ar = get_skill_arabic(skill)
                msg += f"   ✅ {skill_ar}: {data['percentage']}%\n"
            msg += "\n"
    
    msg += "💡 *نصيحة:*\n"
    if avg_percentage >= 80:
        msg += "🌟 مستوى متقدم - جرب `امتحان صعب`"
    elif avg_percentage >= 60:
        msg += "👍 ركز على `خطة التركيز`"
    else:
        msg += "💪 ابدأ بـ `امتحان سهل`"
    
    return msg

def get_leaderboard_text() -> str:
    leaders = StudentService.get_leaderboard()
    if not leaders:
        return "📊 *الترتيب*\n\nلسه مفيش بيانات\n🎯 خد امتحان وظهر في الترتيب!"
    
    msg = "🏆 *أفضل الطلاب*\n" + "─" * 25 + "\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}."
        msg += f"{medal} *{user['name']}* - {user['avg']}% ({user['exams']} امتحان)\n"
    
    msg += "\n💪 *خد امتحان وظهر في الترتيب!*"
    return msg

def review_wrong_questions(chat_id: str, username: str) -> str:
    return start_interactive_exam(chat_id, "medium", None, username, review_wrong=True)

def get_greeting(username: str = None) -> str:
    name_line = f"\n👤 *{username}*" if username else ""
    return f"""👋 *أهلاً بيك في منصة Pen!*{name_line}

📝 *امتحانات:* `امتحان` - `سهل` `متوسط` `صعب`
🎯 *تفاعلي:* `اختبرني` - `اختبرني في [المهارة]`
📊 *تحليل:* `خطة التركيز` - `مستوايا` - `الترتيب`
📚 *مراجعة:* `امتحنني في أخطائي`
💡 *تقرير:* `تقرير` أثناء الامتحان للإبلاغ

🎯 *المهارات:* البلاغة | النحو | الأدب | المفردات | الاستنتاج | القراءة | الإعراب | الصرف"""

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
                return process_exam_answer(chat_id, body, username)
            else:
                del user_sessions[chat_id]
        
        body_lower = body.lower().strip()
        
        if body_lower in ["الترتيب", "ترتيب", "المتصدرين", "أفضل", "الاوائل"]:
            return get_leaderboard_text()
        
        if any(x in body_lower for x in ["امتحنني في أخطائي", "راجع أخطائي", "أخطائي", "اخطائي"]):
            if username: return review_wrong_questions(chat_id, username)
            return "❌ لازم تسجل دخول الأول"
        
        if any(x in body_lower for x in ["اختبرني", "اختبرنى"]):
            level = "medium"
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower:
                    level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            
            skill_query = None
            for word in body_lower.split():
                if word in ["في", "على", "عن", "لـ", "بـ"]: continue
                if resolve_skills(word):
                    skill_query = word
                    break
            
            return start_interactive_exam(chat_id, level, skill_query, username)
        
        if any(x in body_lower for x in ["امتحان", "اختبار"]):
            level = None
            for l in ["سهل", "متوسط", "صعب"]:
                if l in body_lower:
                    level = {"سهل": "easy", "متوسط": "medium", "صعب": "hard"}[l]
            
            skill_query = None
            for word in body_lower.split():
                if word in ["في", "على", "عن", "لـ", "بـ"]: continue
                if resolve_skills(word):
                    skill_query = word
                    break
            
            return generate_exam(level=level, skill_query=skill_query, username=username)
        
        if body_lower in ["مستوايا", "مستوى", "تحليل", "تحليلي"]:
            if username: return get_level_analytics(username)
            return "📊 *لسه مفيش بيانات*\nجرب: `اختبرني`"
        
        if any(x in body_lower for x in ["خطة", "تركيز", "ركز"]):
            return generate_focus_plan(username)
        
        if any(x in body_lower for x in ["اهلا", "مرحبا", "سلام", "هاي", "هلو", "مساعدة", "help", "اوامر"]):
            return get_greeting(username)
        
        # Check if it's a skill query
        resolved = resolve_skills(body_lower)
        if resolved:
            return start_interactive_exam(chat_id, "medium", body_lower, username)
        
        return get_greeting(username)
    
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return "❌ حصل خطأ، جرب تاني"

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
        if "error" in result: return JSONResponse(result, status_code=400)
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
        if "error" in result: return JSONResponse(result, status_code=401)
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
        
        if not message: return JSONResponse({"reply": ""})
        ACTIVE_USERS[chat_id] = username
        reply = await process_message(chat_id, message, username)
        return JSONResponse({"reply": reply, "ok": True})
    except Exception as e:
        return JSONResponse({"reply": "❌ حصل خطأ", "ok": False})

@app.get("/api/leaderboard")
async def leaderboard():
    return JSONResponse(StudentService.get_leaderboard())

@app.get("/api/validation")
async def validation_report():
    return JSONResponse(VALIDATION_REPORT)

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "v5",
        "questions": len(ALL_QUESTIONS),
        "mcq": len(MCQ_QUESTIONS),
        "bad_questions": len(BAD_QUESTIONS),
        "skills": len(QUESTIONS_BY_SKILL)
    }

# =========================================
# SERVE HTML
# =========================================

@app.get("/", response_class=HTMLResponse)
async def auth_page():
    auth_path = BASE_DIR / "auth.html"
    if auth_path.exists(): return auth_path.read_text(encoding="utf-8")
    return "<h1>auth.html not found</h1>"

@app.get("/app", response_class=HTMLResponse)
async def app_page():
    app_path = BASE_DIR / "app.html"
    if app_path.exists(): return app_path.read_text(encoding="utf-8")
    return "<h1>app.html not found</h1>"

# =========================================
# STARTUP
# =========================================

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_expired_sessions())
    print(f"🚀 Pen Platform V5 started!")
    print(f"📊 {len(ALL_QUESTIONS)} valid | {len(BAD_QUESTIONS)} invalid")
    print(f"🔧 {len(SKILL_NAMES_AR)} skill translations")
    print(f"📚 {len(SKILL_RECOMMENDATIONS)} recommendation mappings")
