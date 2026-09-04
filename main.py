import os
import datetime
from typing import List, Optional
import jwt
import bcrypt
from fastapi import FastAPI, Depends, HTTPException, status, Request, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text, and_, or_, func
from sqlalchemy.exc import IntegrityError

import json
from database import engine, SessionLocal, init_db, User, Customer, Product, Document, DocumentItem, Expense, Branch, VideoCourse, AuditLog

# Initialize database safely
try:
    init_db()
except Exception:
    pass

# Secret configurations for JWT
IS_PRODUCTION = bool(os.getenv("VERCEL") or os.getenv("ENVIRONMENT") == "production")
JWT_SECRET_ENV = os.getenv("JWT_SECRET_KEY")

if IS_PRODUCTION:
    if not JWT_SECRET_ENV or not JWT_SECRET_ENV.strip():
        raise RuntimeError(
            "CRITICAL CONFIGURATION ERROR: JWT_SECRET_KEY environment variable is required in production! "
            "Please configure JWT_SECRET_KEY in your environment/Vercel settings."
        )
    SECRET_KEY = JWT_SECRET_ENV.strip()
else:
    SECRET_KEY = JWT_SECRET_ENV.strip() if (JWT_SECRET_ENV and JWT_SECRET_ENV.strip()) else "guasa_house_dev_secret_key_2026_local_only"

ALGORITHM = "HS256"

app = FastAPI(title="Guasha House Billing System")

# Base directory for reliable relative path resolution in Vercel/serverless environments
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Ensure upload directories exist safely
for path in [
    os.path.join(STATIC_DIR, "uploads", "slips"),
    os.path.join(STATIC_DIR, "uploads", "branches"),
    os.path.join(STATIC_DIR, "uploads", "products")
]:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass

# Mount static files and templates using absolute paths
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Helper function to get DB Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Password hashing utilities
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

# Security Audit Logging System
def create_audit_log(
    db: Session,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    result: str = "success",
    details: Optional[str] = None,
    user: Optional[User] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    role: Optional[str] = None,
    request: Optional[Request] = None
):
    """
    Safely creates an immutable audit trail entry for important system operations.
    Strictly sanitizes details to NEVER record passwords, tokens, or secret keys.
    """
    try:
        ip_addr = None
        user_agent_str = None
        if request:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                ip_addr = forwarded.split(",")[0].strip()
            elif request.headers.get("X-Real-IP"):
                ip_addr = request.headers.get("X-Real-IP").strip()
            elif request.client:
                ip_addr = request.client.host
            user_agent_str = request.headers.get("User-Agent", "")[:255]

        uid = user.id if user else user_id
        uname = user.username if user else username
        urole = user.role if user else role

        clean_details = str(details) if details else None
        if clean_details:
            import re
            # Redact passwords, tokens, secrets from audit details
            for sensitive in ["password", "token", "secret", "hashed_password", "access_token", "cookie"]:
                clean_details = re.sub(rf'(?i)("{sensitive}"\s*:\s*")[^"]*(")', r'\1[REDACTED]\2', clean_details)

        log_entry = AuditLog(
            timestamp=datetime.datetime.utcnow(),
            user_id=uid,
            username=uname,
            role=urole or "anonymous",
            action=action.upper(),
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            ip_address=ip_addr,
            user_agent=user_agent_str,
            result=result,
            details=clean_details
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"Audit log exception: {e}")

# In-memory Login Rate Limiter / Brute-force Protection
FAILED_LOGIN_ATTEMPTS = {}
LOCKOUT_DURATION_SECONDS = 300 # 5 minutes
MAX_FAILED_LOGIN_ATTEMPTS = 5

def check_login_rate_limit(client_ip: str, username: str) -> None:
    now = datetime.datetime.utcnow()
    keys = [f"ip:{client_ip}", f"user:{username.strip().lower()}"]
    for k in keys:
        attempts = FAILED_LOGIN_ATTEMPTS.get(k, [])
        valid_attempts = [t for t in attempts if (now - t).total_seconds() < LOCKOUT_DURATION_SECONDS]
        FAILED_LOGIN_ATTEMPTS[k] = valid_attempts
        if len(valid_attempts) >= MAX_FAILED_LOGIN_ATTEMPTS:
            oldest = valid_attempts[0]
            remaining = int(LOCKOUT_DURATION_SECONDS - (now - oldest).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"คุณป้อนรหัสผ่านผิดเกินกำหนด ({MAX_FAILED_LOGIN_ATTEMPTS} ครั้ง) กรุณารอ {max(remaining, 1)} วินาทีก่อนลองใหม่"
            )

def record_failed_login(client_ip: str, username: str) -> None:
    now = datetime.datetime.utcnow()
    for k in [f"ip:{client_ip}", f"user:{username.strip().lower()}"]:
        if k not in FAILED_LOGIN_ATTEMPTS:
            FAILED_LOGIN_ATTEMPTS[k] = []
        FAILED_LOGIN_ATTEMPTS[k].append(now)

def reset_failed_login(client_ip: str, username: str) -> None:
    for k in [f"ip:{client_ip}", f"user:{username.strip().lower()}"]:
        FAILED_LOGIN_ATTEMPTS.pop(k, None)

# Thai Baht wording converter
def bahttext(number: float) -> str:
    try:
        number = round(float(number), 2)
    except (ValueError, TypeError):
        return "ศูนย์บาทถ้วน"
        
    if number == 0:
        return "ศูนย์บาทถ้วน"
        
    parts = str(number).split('.')
    baht_part = int(parts[0])
    satang_part = int(parts[1]) if len(parts) > 1 else 0
    
    if len(parts) > 1 and len(parts[1]) == 1:
        satang_part = satang_part * 10

    thai_numbers = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
    thai_positions = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]

    def convert_integer(n: int) -> str:
        if n == 0:
            return ""
        s = str(n)
        length = len(s)
        result = ""
        
        if length > 6:
            million_part = int(s[:-6])
            rem_part = int(s[-6:])
            return convert_integer(million_part) + "ล้าน" + convert_integer(rem_part)

        for i, digit in enumerate(s):
            digit_val = int(digit)
            pos = length - 1 - i
            
            if digit_val == 0:
                continue
            
            if pos == 0 and digit_val == 1 and length > 1:
                result += "เอ็ด"
            elif pos == 1:
                if digit_val == 1:
                    result += "สิบ"
                elif digit_val == 2:
                    result += "ยี่สิบ"
                else:
                    result += thai_numbers[digit_val] + "สิบ"
            else:
                result += thai_numbers[digit_val] + thai_positions[pos]
                
        return result

    baht_text = convert_integer(baht_part)
    satang_text = convert_integer(satang_part)

    result = ""
    if baht_text:
        result += baht_text + "บาท"
    if satang_text:
        result += satang_text + "สตางค์"
    else:
        if baht_text:
            result += "ถ้วน"
            
    return result

# Seeding database with initial data if empty
def seed_database():
    db = SessionLocal()
    try:
        # Check if users table is empty
        user_count = db.query(User).count()
        if user_count == 0:
            user1 = User(
                username="user1",
                hashed_password=hash_password("password123"),
                fullname="Account 1",
                role="staff"
            )
            user2 = User(
                username="user2",
                hashed_password=hash_password("password123"),
                fullname="Account 2",
                role="staff"
            )
            db.add_all([user1, user2])
            db.commit()
            print("Database seeded with default users: user1, user2")

        # Check if customers table is empty
        customer_count = db.query(Customer).count()
        if customer_count == 0:
            cust1 = Customer(
                name="บริษัท ก้าวหน้า ดีไซน์ จำกัด",
                address="123/45 ถนนพัฒนาการ แขวงสวนหลวง เขตสวนหลวง กรุงเทพฯ 10250",
                tax_id="0105561001234",
                phone="02-123-4567",
                email="contact@kaona.co.th",
                notes="ลูกค้าประจำ สั่งหินกัวซาล็อตใหญ่ทุกไตรมาส"
            )
            cust2 = Customer(
                name="บริษัท สุขใจ เฮลท์แคร์ จำกัด",
                address="88/8 ซอยลาดพร้าว 101 แขวงคลองจั่น เขตบางกะปิ กรุงเทพฯ 10240",
                tax_id="0105564009876",
                phone="089-765-4321",
                email="info@sukjai.com",
                notes="ใช้บริการคอร์สนวดตัวเป็นของขวัญให้พนักงาน"
            )
            db.add_all([cust1, cust2])
            db.commit()
            print("Database seeded with default customers")

        # Check if products table is empty
        product_count = db.query(Product).count()
        if product_count == 0:
            prod1 = Product(
                code="GS-001",
                name="คอร์สนวดหน้ากัวซายกกระชับ (Facial Guasha Lifting Course)",
                description="คอร์สนวดหน้ากัวซายกกระชับผิวหน้า 60 นาที ด้วยหินหยกและน้ำมันธรรมชาติบำรุงลึก",
                unit_price=1500.00,
                is_service=True,
                stock_quantity=0,
                image_url="https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?auto=format&fit=crop&w=600&q=80"
            )
            prod2 = Product(
                code="GS-002",
                name="คอร์สนวดตัวกัวซาขับสารพิษ (Body Detox Guasha Course)",
                description="คอร์สขูดกัวซาแผ่นหลังและไหล่เพื่อกระตุ้นการไหลเวียนของโลหิตและขับพิษ 90 นาที",
                unit_price=1800.00,
                is_service=True,
                stock_quantity=0,
                image_url="https://images.unsplash.com/photo-1519699047748-de8e457a634e?auto=format&fit=crop&w=600&q=80"
            )
            prod3 = Product(
                code="GS-003",
                name="หินกัวซาหินคริสตัลพิงค์ควอตซ์ (Pink Quartz Guasha Stone)",
                description="หินกัวซาพิงค์ควอตซ์แท้รูปหัวใจ สำหรับนวดใบหน้าและลำคอ",
                unit_price=590.00,
                is_service=False,
                stock_quantity=50,
                image_url="https://images.unsplash.com/photo-1608248597279-f99d160bfcbc?auto=format&fit=crop&w=600&q=80"
            )
            prod4 = Product(
                code="GS-004",
                name="น้ำมันมะพร้าวสกัดเย็นสูตรบำรุงผิว (Extra Virgin Coconut Oil 250ml)",
                description="น้ำมันมะพร้าวบริสุทธิ์ 100% สำหรับการนวดตัวและบำรุงผิวพรรณ",
                unit_price=320.00,
                is_service=False,
                stock_quantity=80,
                image_url="https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&w=600&q=80"
            )
            db.add_all([prod1, prod2, prod3, prod4])
            db.commit()
            print("Database seeded with default products")
            
        # Check if branches table is empty
        from database import Branch
        branch_count = db.query(Branch).count()
        if branch_count == 0:
            br1 = Branch(
                name="สาขากรุงเทพกรีฑา (สำนักงานใหญ่)",
                region="กรุงเทพฯ",
                address="199/4 ถนนกรุงเทพกรีฑา แขวงหัวหมาก เขตบางกะปิ กรุงเทพฯ 10240",
                phone="061-496-6361",
                map_pin="https://maps.google.com/?q=Guasha+House",
                image_url="https://images.unsplash.com/photo-1600334129128-685c5582fd35?auto=format&fit=crop&w=600&q=80"
            )
            br2 = Branch(
                name="สาขาเชียงใหม่ (นิมมาน)",
                region="ภาคเหนือ",
                address="12 ซอยนิมมานเหมินท์ 9 ต.สุเทพ อ.เมือง จ.เชียงใหม่ 50200",
                phone="053-123-456",
                map_pin="https://maps.google.com",
                image_url="https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=600&q=80"
            )
            br3 = Branch(
                name="สาขาหาดใหญ่",
                region="ภาคใต้",
                address="45 ถนนเสน่หานุสรณ์ ต.หาดใหญ่ อ.หาดใหญ่ จ.สงขลา 90110",
                phone="074-987-654",
                map_pin="https://maps.google.com",
                image_url="https://images.unsplash.com/photo-1519699047748-de8e457a634e?auto=format&fit=crop&w=600&q=80"
            )
            db.add_all([br1, br2, br3])
            db.commit()
            print("Database seeded with default branches")

        # Check if video_courses table is empty
        video_count = db.query(VideoCourse).count()
        if video_count == 0:
            v1 = VideoCourse(
                title="เทคนิคการนวดกัวซายกกระชับใบหน้า (Facial Guasha Lifting)",
                category="กัวซาใบหน้า",
                video_url="https://www.youtube.com/watch?v=5qap5aO4i9A",
                embed_url="https://www.youtube.com/embed/5qap5aO4i9A",
                description="คอร์สสอนเทคนิคการใช้แผ่นกัวซาหินธรรมชาติขูดกระตุ้นคอลลาเจน ยกกระชับกรอบหน้า ลดถุงใต้ตา และขับน้ำเหลืองเสียอย่างถูกต้อง",
                instructor="อ.กัวซา เฮ้าส์",
                duration="12:45 นาที"
            )
            v2 = VideoCourse(
                title="ขั้นตอนการใช้น้ำมันมะพร้าวสกัดเย็นบริสุทธิ์ร่วมกับหินกัวซา",
                category="เทคนิคการใช้ผลิตภัณฑ์",
                video_url="https://www.youtube.com/watch?v=5qap5aO4i9A",
                embed_url="https://www.youtube.com/embed/5qap5aO4i9A",
                description="แนะนำวิธีการใช้น้ำมันมะพร้าวสกัดเย็น 100% ควบคู่กับการนวดหินกัวซาพิงค์ควอตซ์ เพื่อลดการเสียดสี บำรุงผิวล้ำลึก และป้องกันผิวช้ำ",
                instructor="ผู้เชี่ยวชาญกัวซา",
                duration="08:30 นาที"
            )
            v3 = VideoCourse(
                title="เทคนิคนวดขูดกัวซาแผ่นหลังเพื่อรีดสารพิษและคลายกล้ามเนื้อ",
                category="กัวซาร่างกาย",
                video_url="https://www.youtube.com/watch?v=5qap5aO4i9A",
                embed_url="https://www.youtube.com/embed/5qap5aO4i9A",
                description="สอนทักษะการลงน้ำหนัก การสไลด์แผ่นกัวซาตามแนวเส้นลมปราณแผ่นหลัง เพื่อระบายพิษสะสม และลดอาการออฟฟิศซินโดรม",
                instructor="อ.กัวซา เฮ้าส์",
                duration="18:20 นาที"
            )
            db.add_all([v1, v2, v3])
            db.commit()
            print("Database seeded with default video courses")
            
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
    finally:
        db.close()


from sqlalchemy import inspect

_migration_done = False

def migrate_database():
    global _migration_done
    if _migration_done:
        return
    db = SessionLocal()
    try:
        inspector = inspect(engine)
        if inspector.has_table("documents"):
            doc_cols = [c['name'] for c in inspector.get_columns("documents")]
            for col in ["received_by", "received_date", "shipping_name", "shipping_address", "payment_slip"]:
                if col not in doc_cols:
                    db.execute(text(f"ALTER TABLE documents ADD COLUMN {col} VARCHAR"))
        
        if inspector.has_table("products"):
            prod_cols = [c['name'] for c in inspector.get_columns("products")]
            if "stock_quantity" not in prod_cols:
                db.execute(text("ALTER TABLE products ADD COLUMN stock_quantity INTEGER DEFAULT 0"))
            if "is_service" not in prod_cols:
                db.execute(text("ALTER TABLE products ADD COLUMN is_service BOOLEAN DEFAULT 0"))
            if "image_url" not in prod_cols:
                db.execute(text("ALTER TABLE products ADD COLUMN image_url VARCHAR"))

        if inspector.has_table("branches"):
            branch_cols = [c['name'] for c in inspector.get_columns("branches")]
            if "image_url" not in branch_cols:
                db.execute(text("ALTER TABLE branches ADD COLUMN image_url VARCHAR"))
            
        db.commit()
        _migration_done = True
    except Exception as e:
        db.rollback()
        print(f"Database migration notice: {e}")
    finally:
        db.close()

migrate_database()
seed_database()

# Authentication Helpers
def get_current_user(access_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="กรุณาเข้าสู่ระบบก่อนทำรายการ",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        token_version: int = payload.get("token_version", 1)
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ข้อมูลสิทธิ์การเข้าใช้งานไม่ถูกต้อง")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session หมดอายุ กรุณาเข้าสู่ระบบใหม่")
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="ไม่พบบัญชีผู้ใช้งานในระบบ")
        
    # Session Invalidation Check: Validate token version against DB
    user_token_ver = getattr(user, "token_version", 1)
    if user_token_ver != token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session ถูกยกเลิกเนื่องจากมีการเปลี่ยนรหัสผ่านหรือออกจากระบบ กรุณาเข้าสู่ระบบใหม่"
        )
        
    return user

def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ["admin", "developer"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="เฉพาะผู้ดูแลระบบ (Admin) หรือ Developer เท่านั้นที่มีสิทธิ์ดำเนินการในส่วนนี้"
        )
    return current_user

def get_current_user_from_cookie(access_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)) -> Optional[User]:
    if not access_token:
        return None
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        token_version: int = payload.get("token_version", 1)
        if not username:
            return None
        user = db.query(User).filter(User.username == username).first()
        if user and getattr(user, "token_version", 1) == token_version:
            return user
        return None
    except jwt.PyJWTError:
        return None

# UI Routing endpoints
@app.get("/", response_class=HTMLResponse)
def get_home_page(request: Request):
    return templates.TemplateResponse(request=request, name="home.html")

@app.get("/admin", response_class=HTMLResponse)
def get_admin_page(request: Request, access_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(access_token, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="index.html", context={"user": user})

@app.get("/login", response_class=HTMLResponse)
def get_login_page(request: Request, access_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(access_token, db)
    if user:
        return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/api/auth/login")
def login_api(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    client_ip = "127.0.0.1"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.headers.get("X-Real-IP"):
        client_ip = request.headers.get("X-Real-IP").strip()
    elif request.client:
        client_ip = request.client.host
        
    # 1. Check Rate Limit / Brute Force
    check_login_rate_limit(client_ip, username)
    
    # 2. Verify User and Password Hash (bcrypt)
    user = db.query(User).filter(User.username == username.strip()).first()
    if not user or not verify_password(password, user.hashed_password):
        record_failed_login(client_ip, username)
        create_audit_log(
            db=db,
            action="LOGIN_FAILED",
            target_type="auth",
            target_id=username.strip(),
            result="failed",
            details=json.dumps({"reason": "Invalid credentials", "attempted_username": username.strip()}),
            username=username.strip(),
            request=request
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"}
        )
    
    # 3. Successful Login
    reset_failed_login(client_ip, username)
    user_token_ver = getattr(user, "token_version", 1)
    token_data = {
        "sub": user.username,
        "token_version": user_token_ver,
        "role": user.role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    create_audit_log(
        db=db,
        action="LOGIN",
        target_type="auth",
        target_id=str(user.id),
        result="success",
        details=json.dumps({"role": user.role, "fullname": user.fullname}),
        user=user,
        request=request
    )
    
    response = JSONResponse(content={"success": True, "message": "เข้าสู่ระบบสำเร็จ"})
    response.set_cookie(
        key="access_token", 
        value=token, 
        httponly=True, 
        max_age=7 * 24 * 3600, 
        samesite="lax",
        secure=False
    )
    return response

@app.get("/api/auth/logout")
def logout_api(request: Request, access_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    user = get_current_user_from_cookie(access_token, db)
    if user:
        create_audit_log(
            db=db,
            action="LOGOUT",
            target_type="auth",
            target_id=str(user.id),
            result="success",
            user=user,
            request=request
        )
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="access_token")
    return response

@app.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "fullname": current_user.fullname,
        "role": current_user.role
    }

class ChangePasswordSchema(BaseModel):
    old_password: str
    new_password: str

@app.post("/api/auth/change-password")
def change_password_api(
    data: ChangePasswordSchema,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(data.old_password, current_user.hashed_password):
        create_audit_log(
            db=db,
            action="CHANGE_PASSWORD",
            target_type="user",
            target_id=str(current_user.id),
            result="failed",
            details=json.dumps({"reason": "Incorrect old password"}),
            user=current_user,
            request=request
        )
        raise HTTPException(status_code=400, detail="รหัสผ่านเดิมไม่ถูกต้อง")
        
    if len(data.new_password.strip()) < 4:
        raise HTTPException(status_code=400, detail="รหัสผ่านใหม่ต้องมีความยาวอย่างน้อย 4 ตัวอักษร")
        
    # Securely hash new password with bcrypt
    current_user.hashed_password = hash_password(data.new_password.strip())
    # Session Invalidation: increment token version to invalidate all other active tokens
    current_user.token_version = getattr(current_user, "token_version", 1) + 1
    db.commit()
    
    create_audit_log(
        db=db,
        action="CHANGE_PASSWORD",
        target_type="user",
        target_id=str(current_user.id),
        result="success",
        details=json.dumps({"info": "Password changed successfully; other sessions invalidated"}),
        user=current_user,
        request=request
    )
    
    # Issue fresh token for current user
    token_data = {
        "sub": current_user.username,
        "token_version": current_user.token_version,
        "role": current_user.role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    new_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    response = JSONResponse(content={"success": True, "message": "เปลี่ยนรหัสผ่านสำเร็จ และยกเลิก Session เก่าทั้งหมดแล้ว"})
    response.set_cookie(
        key="access_token",
        value=new_token,
        httponly=True,
        max_age=7 * 24 * 3600,
        samesite="lax",
        secure=False
    )
    return response

class ChangeUsernameSchema(BaseModel):
    new_username: str

@app.post("/api/auth/change-username")
def change_username_api(
    data: ChangeUsernameSchema,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    clean_username = data.new_username.strip()
    if not clean_username or len(clean_username) < 3:
        raise HTTPException(status_code=400, detail="ชื่อผู้ใช้งานต้องมีความยาวอย่างน้อย 3 ตัวอักษร")
        
    if clean_username != current_user.username:
        existing = db.query(User).filter(User.username == clean_username).first()
        if existing:
            raise HTTPException(status_code=400, detail="ชื่อผู้ใช้งาน (Username) นี้ถูกใช้งานแล้ว")
            
        old_username = current_user.username
        current_user.username = clean_username
        current_user.token_version = getattr(current_user, "token_version", 1) + 1
        db.commit()
        
        create_audit_log(
            db=db,
            action="CHANGE_USERNAME",
            target_type="user",
            target_id=str(current_user.id),
            result="success",
            details=json.dumps({"old_username": old_username, "new_username": clean_username}),
            user=current_user,
            request=request
        )
        
        token_data = {
            "sub": current_user.username,
            "token_version": current_user.token_version,
            "role": current_user.role,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
        }
        new_token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        
        response = JSONResponse(content={"success": True, "message": "เปลี่ยนชื่อผู้ใช้งานสำเร็จ"})
        response.set_cookie(
            key="access_token",
            value=new_token,
            httponly=True,
            max_age=7 * 24 * 3600,
            samesite="lax",
            secure=False
        )
        return response
        
    return {"success": True, "message": "ชื่อผู้ใช้งานตรงกับปัจจุบัน"}

@app.get("/api/audit-logs")
def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    action: Optional[str] = None,
    username: Optional[str] = None,
    target_type: Optional[str] = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    query = db.query(AuditLog)
    if action and action.strip():
        query = query.filter(AuditLog.action == action.strip().upper())
    if username and username.strip():
        query = query.filter(AuditLog.username.ilike(f"%{username.strip()}%"))
    if target_type and target_type.strip():
        query = query.filter(AuditLog.target_type == target_type.strip().lower())
        
    total = query.count()
    logs = query.order_by(AuditLog.id.desc()).offset(offset).limit(min(limit, 500)).all()
    
    return {
        "total": total,
        "items": [
            {
                "id": l.id,
                "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S") if l.timestamp else "",
                "user_id": l.user_id,
                "username": l.username,
                "role": l.role,
                "action": l.action,
                "target_type": l.target_type,
                "target_id": l.target_id,
                "ip_address": l.ip_address,
                "user_agent": l.user_agent,
                "result": l.result,
                "details": l.details
            }
            for l in logs
        ]
    }

# ----------------- USER MANAGEMENT API (Admin Only) -----------------
class UserCreateSchema(BaseModel):
    username: str
    fullname: str
    password: str
    role: Optional[str] = "staff"

class UserUpdateSchema(BaseModel):
    username: str
    fullname: str
    password: Optional[str] = ""
    role: Optional[str] = "staff"

@app.get("/api/users")
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "fullname": u.fullname,
            "role": u.role or "staff",
            "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S") if u.created_at else ""
        }
        for u in users
    ]

@app.post("/api/users")
def create_user(user: UserCreateSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    if not user.username or not user.password or not user.fullname:
        raise HTTPException(status_code=400, detail="กรุณากรอกข้อมูลให้ครบถ้วน")
        
    existing = db.query(User).filter(User.username == user.username.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="ชื่อผู้ใช้งาน (Username) นี้ถูกใช้งานแล้ว")
        
    role_val = user.role if user.role in ["admin", "developer", "staff"] else "staff"
    new_user = User(
        username=user.username.strip(),
        fullname=user.fullname.strip(),
        hashed_password=hash_password(user.password),
        role=role_val,
        token_version=1
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    create_audit_log(
        db=db,
        action="CREATE_USER",
        target_type="user",
        target_id=str(new_user.id),
        result="success",
        details=json.dumps({"username": new_user.username, "fullname": new_user.fullname, "role": new_user.role}),
        user=current_user,
        request=request
    )
    
    return {"success": True, "message": "เพิ่มผู้ใช้งานสำเร็จ", "id": new_user.id}

@app.put("/api/users/{user_id}")
def update_user(user_id: int, user: UserUpdateSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลผู้ใช้งาน")
        
    if user.username.strip() != u.username:
        existing = db.query(User).filter(User.username == user.username.strip()).first()
        if existing:
            raise HTTPException(status_code=400, detail="ชื่อผู้ใช้งาน (Username) นี้ถูกใช้งานแล้ว")
            
    old_role = u.role
    old_username = u.username
    u.username = user.username.strip()
    u.fullname = user.fullname.strip()
    if user.role in ["admin", "developer", "staff"]:
        u.role = user.role
    
    password_changed = False
    if user.password and user.password.strip():
        if len(user.password.strip()) < 4:
            raise HTTPException(status_code=400, detail="รหัสผ่านต้องมีความยาวอย่างน้อย 4 ตัวอักษร")
        u.hashed_password = hash_password(user.password.strip())
        u.token_version = getattr(u, "token_version", 1) + 1
        password_changed = True
        
    db.commit()
    
    audit_action = "UPDATE_USER"
    if old_role != u.role:
        audit_action = "ROLE_CHANGE"
        
    create_audit_log(
        db=db,
        action=audit_action,
        target_type="user",
        target_id=str(u.id),
        result="success",
        details=json.dumps({
            "old_username": old_username,
            "new_username": u.username,
            "old_role": old_role,
            "new_role": u.role,
            "password_changed": password_changed
        }),
        user=current_user,
        request=request
    )
    
    return {"success": True, "message": "แก้ไขข้อมูลผู้ใช้งานสำเร็จ"}

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin)):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="ไม่สามารถลบบัญชีผู้ใช้ที่กำลังเข้าสู่ระบบอยู่ได้")
        
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลผู้ใช้งาน")
        
    # Check if user has created documents (protect data integrity)
    has_docs = db.query(Document).filter(Document.created_by_user_id == user_id).count() > 0
    if has_docs:
        raise HTTPException(
            status_code=400,
            detail="ไม่สามารถลบผู้ใช้งานนี้ได้ เนื่องจากมีประวัติการสร้างเอกสารในระบบ"
        )
        
    deleted_username = u.username
    deleted_role = u.role
    try:
        db.delete(u)
        db.commit()
        
        create_audit_log(
            db=db,
            action="DELETE_USER",
            target_type="user",
            target_id=str(user_id),
            result="success",
            details=json.dumps({"deleted_username": deleted_username, "deleted_role": deleted_role}),
            user=current_user,
            request=request
        )
        
        return {"success": True, "message": "ลบผู้ใช้งานสำเร็จ"}
    except Exception as e:
        db.rollback()
        print(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการลบผู้ใช้งาน กรุณาลองใหม่อีกครั้ง")

# ----------------- CUSTOMER API -----------------
class CustomerSchema(BaseModel):
    name: str
    address: str
    tax_id: str
    phone: Optional[str] = ""
    email: Optional[str] = ""
    notes: Optional[str] = ""

@app.get("/api/customers")
def list_customers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Customer).order_by(Customer.name.asc()).all()

@app.post("/api/customers")
def create_customer(customer: CustomerSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check if duplicate name
    existing = db.query(Customer).filter(Customer.name == customer.name.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="มีลูกค้าชื่อนี้อยู่ในระบบแล้ว")
    
    new_cust = Customer(
        name=customer.name.strip(),
        address=customer.address.strip(),
        tax_id=customer.tax_id.strip(),
        phone=customer.phone,
        email=customer.email,
        notes=customer.notes
    )
    db.add(new_cust)
    db.commit()
    db.refresh(new_cust)
    
    create_audit_log(
        db=db,
        action="CREATE_CUSTOMER",
        target_type="customer",
        target_id=str(new_cust.id),
        result="success",
        details=json.dumps({"name": new_cust.name, "tax_id": new_cust.tax_id}),
        user=current_user,
        request=request
    )
    
    return new_cust

@app.put("/api/customers/{customer_id}")
def update_customer(customer_id: int, customer: CustomerSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลลูกค้า")
        
    cust.name = customer.name.strip()
    cust.address = customer.address.strip()
    cust.tax_id = customer.tax_id.strip()
    cust.phone = customer.phone
    cust.email = customer.email
    cust.notes = customer.notes
    db.commit()
    db.refresh(cust)
    
    create_audit_log(
        db=db,
        action="UPDATE_CUSTOMER",
        target_type="customer",
        target_id=str(cust.id),
        result="success",
        details=json.dumps({"name": cust.name, "tax_id": cust.tax_id}),
        user=current_user,
        request=request
    )
    
    return cust

@app.delete("/api/customers/{customer_id}")
def delete_customer(customer_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลลูกค้า")
        
    # Check if customer has documents (protect data integrity)
    has_docs = db.query(Document).filter(Document.customer_id == customer_id).count() > 0
    if has_docs:
        raise HTTPException(
            status_code=400,
            detail="ไม่สามารถลบลูกค้ารายนี้ได้ เนื่องจากมีประวัติเอกสารใบกำกับภาษีในระบบ"
        )
        
    deleted_name = cust.name
    try:
        db.delete(cust)
        db.commit()
        
        create_audit_log(
            db=db,
            action="DELETE_CUSTOMER",
            target_type="customer",
            target_id=str(customer_id),
            result="success",
            details=json.dumps({"deleted_name": deleted_name}),
            user=current_user,
            request=request
        )
        
        return {"success": True, "message": "ลบข้อมูลลูกค้าสำเร็จ"}
    except Exception as e:
        db.rollback()
        print(f"Error deleting customer: {e}")
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการลบข้อมูลลูกค้า")

# ----------------- PRODUCT API -----------------
class ProductSchema(BaseModel):
    code: Optional[str] = ""
    name: str
    description: Optional[str] = ""
    unit_price: float
    stock_quantity: Optional[int] = 0
    is_service: Optional[bool] = False
    image_url: Optional[str] = ""

@app.get("/api/products")
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).order_by(Product.code.asc()).all()

@app.post("/api/products")
def create_product(product: ProductSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if product.code:
        existing = db.query(Product).filter(Product.code == product.code).first()
        if existing:
            raise HTTPException(status_code=404, detail="รหัสสินค้านี้ซ้ำในระบบ")
            
    new_prod = Product(
        code=product.code or None,
        name=product.name,
        description=product.description,
        unit_price=product.unit_price,
        stock_quantity=product.stock_quantity or 0,
        is_service=product.is_service or False,
        image_url=product.image_url
    )
    db.add(new_prod)
    db.commit()
    db.refresh(new_prod)
    
    create_audit_log(
        db=db,
        action="CREATE_PRODUCT",
        target_type="product",
        target_id=str(new_prod.id),
        result="success",
        details=json.dumps({"name": new_prod.name, "code": new_prod.code, "unit_price": new_prod.unit_price}),
        user=current_user,
        request=request
    )
    
    return new_prod

@app.put("/api/products/{product_id}")
def update_product(product_id: int, product: ProductSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลสินค้า")
        
    if product.code and product.code != prod.code:
        existing = db.query(Product).filter(Product.code == product.code).first()
        if existing:
            raise HTTPException(status_code=404, detail="รหัสสินค้านี้ซ้ำในระบบ")
            
    prod.code = product.code or None
    prod.name = product.name
    prod.description = product.description
    prod.unit_price = product.unit_price
    prod.stock_quantity = product.stock_quantity or 0
    prod.is_service = product.is_service or False
    prod.image_url = product.image_url
    db.commit()
    db.refresh(prod)
    
    create_audit_log(
        db=db,
        action="UPDATE_PRODUCT",
        target_type="product",
        target_id=str(prod.id),
        result="success",
        details=json.dumps({"name": prod.name, "code": prod.code, "unit_price": prod.unit_price}),
        user=current_user,
        request=request
    )
    
    return prod

@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลสินค้า")
    deleted_name = prod.name
    db.delete(prod)
    db.commit()
    
    create_audit_log(
        db=db,
        action="DELETE_PRODUCT",
        target_type="product",
        target_id=str(product_id),
        result="success",
        details=json.dumps({"deleted_name": deleted_name}),
        user=current_user,
        request=request
    )
    
    return {"success": True, "message": "ลบข้อมูลสินค้าสำเร็จ"}

# ----------------- DOCUMENT API -----------------
class DocumentItemSchema(BaseModel):
    description: str
    quantity: float
    unit_price: float

class DocumentCreateSchema(BaseModel):
    date: str
    customer_id: Optional[int] = None
    customer_name: str
    customer_address: str
    customer_tax_id: str
    customer_phone: Optional[str] = ""
    customer_email: Optional[str] = ""
    payment_method: str # CASH / CHEQUE
    cheque_bank: Optional[str] = ""
    cheque_number: Optional[str] = ""
    cheque_date: Optional[str] = ""
    cheque_branch: Optional[str] = ""
    received_by: Optional[str] = ""
    received_date: Optional[str] = ""
    shipping_name: Optional[str] = ""
    shipping_address: Optional[str] = ""
    payment_slip: Optional[str] = ""
    total_amount_before_vat: float
    vat_amount: float
    total_amount_after_vat: float
    items: List[DocumentItemSchema]

def generate_invoice_number(db: Session, year: str) -> str:
    # Run immediate transaction queries to find max document number for this year.
    prefix = f"INV-{year}-"
    # Find the document with the maximum invoice number for the year.
    result = db.execute(
        text("SELECT document_number FROM documents WHERE document_number LIKE :prefix ORDER BY document_number DESC LIMIT 1"),
        {"prefix": f"{prefix}%"}
    ).fetchone()
    
    if result:
        last_num = result[0]
        try:
            serial_part = last_num.split('-')[-1]
            next_serial = int(serial_part) + 1
        except (ValueError, IndexError):
            next_serial = 1
    else:
        next_serial = 1
        
    return f"INV-{year}-{next_serial:04d}"

@app.post("/api/documents")
def create_document(doc_data: DocumentCreateSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 1. Validation for empty items or missing fields
    if not doc_data.items or len(doc_data.items) == 0:
        raise HTTPException(status_code=400, detail="กรุณาระบุรายการสินค้าอย่างน้อย 1 รายการ")
    
    # 2. Re-calculate all amounts on Backend (Never trust client calculations directly)
    validated_items = []
    subtotal = 0.0
    for idx, item in enumerate(doc_data.items, 1):
        desc = (item.description or "").strip()
        if not desc:
            raise HTTPException(status_code=400, detail=f"กรุณาระบุชื่อรายการสินค้าลำดับที่ {idx}")
        qty = float(item.quantity)
        if qty <= 0:
            raise HTTPException(status_code=400, detail=f"จำนวนสินค้าในรายการลำดับที่ {idx} ต้องมากกว่า 0")
        price = float(item.unit_price)
        if price < 0:
            raise HTTPException(status_code=400, detail=f"ราคาสินค้าในรายการลำดับที่ {idx} ต้องไม่ติดลบ")
        
        item_amt = round(qty * price, 2)
        subtotal += item_amt
        validated_items.append({
            "item_index": idx,
            "description": desc,
            "quantity": qty,
            "unit_price": price,
            "amount": item_amt
        })

    subtotal = round(subtotal, 2)
    vat_amount = round(subtotal * 0.07, 2)
    total_after_vat = round(subtotal + vat_amount, 2)
    total_text = bahttext(total_after_vat)

    max_attempts = 10
    doc_year = "2026"
    if doc_data.date and len(doc_data.date) >= 4:
        doc_year = doc_data.date[:4]
        
    for attempt in range(max_attempts):
        try:
            with db.begin_nested():
                doc_num = generate_invoice_number(db, doc_year)
                
                existing = db.query(Document).filter(Document.document_number == doc_num).first()
                if existing:
                    raise IntegrityError("Collision detected", params=None, orig=None)
                
                new_doc = Document(
                    document_number=doc_num,
                    date=doc_data.date,
                    customer_id=doc_data.customer_id,
                    customer_name=doc_data.customer_name.strip(),
                    customer_address=doc_data.customer_address.strip(),
                    customer_tax_id=doc_data.customer_tax_id.strip(),
                    customer_phone=doc_data.customer_phone,
                    customer_email=doc_data.customer_email,
                    total_amount_before_vat=subtotal,
                    vat_amount=vat_amount,
                    total_amount_after_vat=total_after_vat,
                    total_amount_text=total_text,
                    payment_method=doc_data.payment_method,
                    cheque_bank=doc_data.cheque_bank if doc_data.payment_method == "CHEQUE" else None,
                    cheque_number=doc_data.cheque_number if doc_data.payment_method == "CHEQUE" else None,
                    cheque_date=doc_data.cheque_date if doc_data.payment_method == "CHEQUE" else None,
                    cheque_branch=doc_data.cheque_branch if doc_data.payment_method == "CHEQUE" else None,
                    received_by=doc_data.received_by,
                    received_date=doc_data.received_date,
                    shipping_name=doc_data.shipping_name,
                    shipping_address=doc_data.shipping_address,
                    payment_slip=doc_data.payment_slip,
                    created_by_user_id=current_user.id,
                    created_by_username=current_user.fullname,
                    status="issued"
                )
                
                db.add(new_doc)
                db.flush()
                
                for v_item in validated_items:
                    new_item = DocumentItem(
                         document_id=new_doc.id,
                         item_index=v_item["item_index"],
                         description=v_item["description"],
                         quantity=v_item["quantity"],
                         unit_price=v_item["unit_price"],
                         amount=v_item["amount"]
                    )
                    db.add(new_item)
                    
                    # Stock deduction logic
                    prod = db.query(Product).filter(Product.name == v_item["description"]).first()
                    if prod and not prod.is_service:
                        prod.stock_quantity = max(0, (prod.stock_quantity or 0) - int(v_item["quantity"]))
                
            db.commit()
            create_audit_log(
                db=db,
                action="CREATE_DOCUMENT",
                target_type="document",
                target_id=doc_num,
                result="success",
                details=json.dumps({"total": total_after_vat, "customer": new_doc.customer_name}),
                user=current_user,
                request=request
            )
            return {"success": True, "document_id": new_doc.id, "document_number": doc_num}
        except IntegrityError:
            db.rollback()
            if attempt == max_attempts - 1:
                raise HTTPException(status_code=500, detail="ไม่สามารถสร้างเลขที่เอกสารแบบไม่ซ้ำกันได้เนื่องจากการใช้งานที่หนาแน่น กรุณาลองใหม่อีกครั้ง")
            continue
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            print(f"Error creating document: {e}")
            raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการบันทึกเอกสาร กรุณาลองใหม่อีกครั้ง")

@app.get("/api/documents")
def list_documents(
    query: Optional[str] = None,
    date: Optional[str] = None,
    month: Optional[str] = None,
    year: Optional[str] = None,
    customer_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    q = db.query(Document)
    
    if query:
        search_filter = or_(
            Document.document_number.like(f"%{query}%"),
            Document.customer_name.like(f"%{query}%")
        )
        q = q.filter(search_filter)
        
    if date:
        q = q.filter(Document.date == date)
        
    if month:
        q = q.filter(Document.date.like(f"%-{month}-%"))
        
    if year:
        q = q.filter(Document.date.like(f"{year}-%"))
        
    if customer_id:
        q = q.filter(Document.customer_id == customer_id)
        
    if payment_method:
        q = q.filter(Document.payment_method == payment_method)
        
    return q.order_by(Document.document_number.desc()).all()

@app.get("/api/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสาร")
    
    items_out = []
    for item in sorted(doc.items, key=lambda x: x.item_index):
        items_out.append({
            "description": item.description,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "amount": item.amount
        })
        
    return {
        "id": doc.id,
        "document_number": doc.document_number,
        "date": doc.date,
        "customer_id": doc.customer_id,
        "customer_name": doc.customer_name,
        "customer_address": doc.customer_address,
        "customer_tax_id": doc.customer_tax_id,
        "customer_phone": doc.customer_phone,
        "customer_email": doc.customer_email,
        "total_amount_before_vat": doc.total_amount_before_vat,
        "vat_amount": doc.vat_amount,
        "total_amount_after_vat": doc.total_amount_after_vat,
        "total_amount_text": doc.total_amount_text,
        "payment_method": doc.payment_method,
        "cheque_bank": doc.cheque_bank,
        "cheque_number": doc.cheque_number,
        "cheque_date": doc.cheque_date,
        "cheque_branch": doc.cheque_branch,
        "received_by": doc.received_by,
        "received_date": doc.received_date,
        "shipping_name": doc.shipping_name,
        "shipping_address": doc.shipping_address,
        "payment_slip": doc.payment_slip,
        "created_by_user_id": doc.created_by_user_id,
        "created_by_username": doc.created_by_username,
        "status": doc.status,
        "items": items_out
    }

@app.put("/api/documents/{doc_id}")
def update_document(doc_id: int, doc_data: DocumentCreateSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสาร")
        
    if not doc_data.items or len(doc_data.items) == 0:
        raise HTTPException(status_code=400, detail="กรุณาระบุรายการสินค้าอย่างน้อย 1 รายการ")
        
    # Re-calculate on backend
    validated_items = []
    subtotal = 0.0
    for idx, item in enumerate(doc_data.items, 1):
        desc = (item.description or "").strip()
        if not desc:
            raise HTTPException(status_code=400, detail=f"กรุณาระบุชื่อรายการสินค้าลำดับที่ {idx}")
        qty = float(item.quantity)
        if qty <= 0:
            raise HTTPException(status_code=400, detail=f"จำนวนสินค้าในรายการลำดับที่ {idx} ต้องมากกว่า 0")
        price = float(item.unit_price)
        if price < 0:
            raise HTTPException(status_code=400, detail=f"ราคาสินค้าในรายการลำดับที่ {idx} ต้องไม่ติดลบ")
        
        item_amt = round(qty * price, 2)
        subtotal += item_amt
        validated_items.append({
            "item_index": idx,
            "description": desc,
            "quantity": qty,
            "unit_price": price,
            "amount": item_amt
        })

    subtotal = round(subtotal, 2)
    vat_amount = round(subtotal * 0.07, 2)
    total_after_vat = round(subtotal + vat_amount, 2)
    total_text = bahttext(total_after_vat)

    try:
        with db.begin_nested():
            # Update main record fields
            doc.date = doc_data.date
            doc.customer_id = doc_data.customer_id
            doc.customer_name = doc_data.customer_name.strip()
            doc.customer_address = doc_data.customer_address.strip()
            doc.customer_tax_id = doc_data.customer_tax_id.strip()
            doc.customer_phone = doc_data.customer_phone
            doc.customer_email = doc_data.customer_email
            
            doc.total_amount_before_vat = subtotal
            doc.vat_amount = vat_amount
            doc.total_amount_after_vat = total_after_vat
            doc.total_amount_text = total_text
            
            doc.payment_method = doc_data.payment_method
            doc.cheque_bank = doc_data.cheque_bank if doc_data.payment_method == "CHEQUE" else None
            doc.cheque_number = doc_data.cheque_number if doc_data.payment_method == "CHEQUE" else None
            doc.cheque_date = doc_data.cheque_date if doc_data.payment_method == "CHEQUE" else None
            doc.cheque_branch = doc_data.cheque_branch if doc_data.payment_method == "CHEQUE" else None
            
            doc.received_by = doc_data.received_by
            doc.received_date = doc_data.received_date
            doc.shipping_name = doc_data.shipping_name
            doc.shipping_address = doc_data.shipping_address
            doc.payment_slip = doc_data.payment_slip
            
            # Restore stock from old items before deleting
            old_items = db.query(DocumentItem).filter(DocumentItem.document_id == doc.id).all()
            for old_item in old_items:
                if old_item.description:
                    prod = db.query(Product).filter(Product.name == old_item.description.strip()).first()
                    if prod and not prod.is_service:
                        prod.stock_quantity = (prod.stock_quantity or 0) + int(old_item.quantity)
            
            # Clear old items
            db.query(DocumentItem).filter(DocumentItem.document_id == doc.id).delete()
            
            # Add updated items
            for v_item in validated_items:
                new_item = DocumentItem(
                    document_id=doc.id,
                    item_index=v_item["item_index"],
                    description=v_item["description"],
                    quantity=v_item["quantity"],
                    unit_price=v_item["unit_price"],
                    amount=v_item["amount"]
                )
                db.add(new_item)
                
                # Deduct stock for new items
                prod = db.query(Product).filter(Product.name == v_item["description"]).first()
                if prod and not prod.is_service:
                    prod.stock_quantity = max(0, (prod.stock_quantity or 0) - int(v_item["quantity"]))
                
        db.commit()
        
        create_audit_log(
            db=db,
            action="UPDATE_DOCUMENT",
            target_type="document",
            target_id=doc.document_number,
            result="success",
            details=json.dumps({"total": total_after_vat, "customer": doc.customer_name}),
            user=current_user,
            request=request
        )
        
        return {"success": True, "document_id": doc.id, "document_number": doc.document_number}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error updating document: {e}")
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการแก้ไขเอกสาร กรุณาลองใหม่อีกครั้ง")

@app.post("/api/documents/{doc_id}/duplicate")
def duplicate_document(doc_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    old_doc = db.query(Document).filter(Document.id == doc_id).first()
    if not old_doc:
        raise HTTPException(status_code=404, detail="ไม่พบต้นฉบับเอกสาร")
        
    items_list = []
    for item in old_doc.items:
        items_list.append(DocumentItemSchema(
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price
        ))
        
    doc_create_data = DocumentCreateSchema(
        date=datetime.date.today().isoformat(),
        customer_id=old_doc.customer_id,
        customer_name=old_doc.customer_name,
        customer_address=old_doc.customer_address,
        customer_tax_id=old_doc.customer_tax_id,
        customer_phone=old_doc.customer_phone,
        customer_email=old_doc.customer_email,
        payment_method=old_doc.payment_method,
        cheque_bank=old_doc.cheque_bank,
        cheque_number=old_doc.cheque_number,
        cheque_date=old_doc.cheque_date,
        cheque_branch=old_doc.cheque_branch,
        received_by=old_doc.received_by,
        received_date=old_doc.received_date,
        shipping_name=old_doc.shipping_name,
        shipping_address=old_doc.shipping_address,
        payment_slip=old_doc.payment_slip,
        total_amount_before_vat=old_doc.total_amount_before_vat,
        vat_amount=old_doc.vat_amount,
        total_amount_after_vat=old_doc.total_amount_after_vat,
        items=items_list
    )
    
    return create_document(doc_create_data, request, db, current_user)

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสาร")
    
    doc_num = doc.document_number
    try:
        with db.begin_nested():
            # Restore inventory stock for non-service items
            for item in doc.items:
                if item.description:
                    prod = db.query(Product).filter(Product.name == item.description.strip()).first()
                    if prod and not prod.is_service:
                        prod.stock_quantity = (prod.stock_quantity or 0) + int(item.quantity)
            
            db.delete(doc)
        db.commit()
        
        create_audit_log(
            db=db,
            action="DELETE_DOCUMENT",
            target_type="document",
            target_id=doc_num,
            result="success",
            details=json.dumps({"document_number": doc_num}),
            user=current_user,
            request=request
        )
        
        return {"success": True, "message": "ลบเอกสารและคืนสต็อกสินค้าสำเร็จ"}
    except Exception as e:
        db.rollback()
        print(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการลบเอกสาร กรุณาลองใหม่อีกครั้ง")

# ----------------- DASHBOARD API -----------------
@app.get("/api/dashboard/stats")
def get_dashboard_stats(
    year: Optional[str] = None,
    month: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    from database import Expense
    import datetime
    
    now = datetime.date.today()
    target_year = int(year) if (year and year.isdigit()) else now.year
    
    # Base queries according to year & month filter
    doc_query = db.query(Document)
    exp_query = db.query(Expense)
    
    if month and month != "ALL" and month.isdigit():
        m_int = int(month)
        pattern = f"{target_year}-{m_int:02d}-%"
        doc_query = doc_query.filter(Document.date.like(pattern))
        exp_query = exp_query.filter(Expense.date.like(pattern))
    elif year and year != "ALL":
        pattern = f"{target_year}-%"
        doc_query = doc_query.filter(Document.date.like(pattern))
        exp_query = exp_query.filter(Expense.date.like(pattern))
        
    sales_sum = doc_query.with_entities(func.sum(Document.total_amount_after_vat)).scalar()
    total_sales = float(sales_sum) if sales_sum else 0.0
    
    exp_sum = exp_query.with_entities(func.sum(Expense.amount)).scalar()
    total_expenses = float(exp_sum) if exp_sum else 0.0
    
    net_profit = total_sales - total_expenses
    
    total_docs = doc_query.count()
    total_cust = db.query(Customer).count()
    
    # 12 Months breakdown for Dashboard Chart for target_year (Bulk 2-query aggregation for fast response)
    year_pattern = f"{target_year}-%"
    year_docs = db.query(Document.date, Document.total_amount_after_vat).filter(
        Document.date.like(year_pattern)
    ).all()
    
    year_exps = db.query(Expense.date, Expense.amount).filter(
        Expense.date.like(year_pattern)
    ).all()
    
    sales_by_month = {m: 0.0 for m in range(1, 13)}
    expenses_by_month = {m: 0.0 for m in range(1, 13)}
    
    for doc_date, amount in year_docs:
        if doc_date and len(doc_date) >= 7:
            try:
                m = int(doc_date.split("-")[1])
                if 1 <= m <= 12:
                    sales_by_month[m] += float(amount or 0.0)
            except Exception:
                pass
                
    for exp_date, amount in year_exps:
        if exp_date and len(exp_date) >= 7:
            try:
                m = int(exp_date.split("-")[1])
                if 1 <= m <= 12:
                    expenses_by_month[m] += float(amount or 0.0)
            except Exception:
                pass

    months_chart_data = []
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    for m in range(1, 13):
        s_val = sales_by_month[m]
        e_val = expenses_by_month[m]
        months_chart_data.append({
            "month_num": m,
            "month_name": months_th[m-1],
            "sales": s_val,
            "expenses": e_val,
            "profit": s_val - e_val
        })

    # Recent documents (5)
    recent_docs = db.query(Document).order_by(Document.id.desc()).limit(5).all()
    recent_list = []
    for doc in recent_docs:
        recent_list.append({
            "id": doc.id,
            "document_number": doc.document_number,
            "date": doc.date,
            "customer_name": doc.customer_name,
            "total_amount": doc.total_amount_after_vat,
            "created_by": doc.created_by_username,
            "status": doc.status
        })
        
    return {
        "total_documents": total_docs,
        "monthly_documents": total_docs,
        "total_sales": total_sales,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
        "total_customers": total_cust,
        "monthly_sales": total_sales,
        "monthly_expenses": total_expenses,
        "net_profit_month": net_profit,
        "months_chart_data": months_chart_data,
        "recent_documents": recent_list
    }

# ----------------- REPORTS API -----------------
@app.get("/api/reports/summary")
def get_reports_summary(year: Optional[str] = None, month: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not year:
        year = str(datetime.date.today().year)
        
    # Generate data for months Jan-Dec using 1 bulk query
    year_pattern = f"{year}-%"
    year_docs = db.query(Document.date, Document.total_amount_after_vat, Document.vat_amount).filter(
        Document.date.like(year_pattern)
    ).all()
    
    monthly_stats = {m: {"sales": 0.0, "vat": 0.0, "count": 0} for m in range(1, 13)}
    for doc_date, sales, vat in year_docs:
        if doc_date and len(doc_date) >= 7:
            try:
                m = int(doc_date.split("-")[1])
                if 1 <= m <= 12:
                    monthly_stats[m]["sales"] += float(sales or 0.0)
                    monthly_stats[m]["vat"] += float(vat or 0.0)
                    monthly_stats[m]["count"] += 1
            except Exception:
                pass

    months_data = []
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    for m in range(1, 13):
        months_data.append({
            "month_num": m,
            "month_name": months_th[m-1],
            "sales": monthly_stats[m]["sales"],
            "vat": monthly_stats[m]["vat"],
            "count": monthly_stats[m]["count"]
        })
        
    # Determine date pattern for filtered breakdown (year only or specific month)
    if month and month != "ALL" and month != "":
        try:
            m_int = int(month)
            date_filter_pattern = f"{year}-{m_int:02d}-%"
        except ValueError:
            date_filter_pattern = f"{year}-%"
    else:
        date_filter_pattern = f"{year}-%"

    # Get payment methods breakdown for the selected period
    cash_sum = db.query(func.sum(Document.total_amount_after_vat)).filter(
        and_(Document.date.like(date_filter_pattern), Document.payment_method == "CASH")
    ).scalar()
    cash_sum = float(cash_sum) if cash_sum else 0.0
    
    cheque_sum = db.query(func.sum(Document.total_amount_after_vat)).filter(
        and_(Document.date.like(date_filter_pattern), Document.payment_method == "CHEQUE")
    ).scalar()
    cheque_sum = float(cheque_sum) if cheque_sum else 0.0

    # Total sales in selected period
    period_sales_sum = db.query(func.sum(Document.total_amount_after_vat)).filter(
        Document.date.like(date_filter_pattern)
    ).scalar()
    period_sales = float(period_sales_sum) if period_sales_sum else 0.0
    
    # Get expenses breakdown for the selected period by category
    from database import Expense
    expense_data = db.query(
        Expense.category,
        func.sum(Expense.amount)
    ).filter(
        Expense.date.like(date_filter_pattern)
    ).group_by(
        Expense.category
    ).all()
    
    expenses_breakdown = []
    total_expenses = 0.0
    for cat, amt in expense_data:
        amt_val = float(amt) if amt else 0.0
        expenses_breakdown.append({
            "category": cat,
            "amount": amt_val
        })
        total_expenses += amt_val

    # ----------------- PRODUCT SALES BREAKDOWN -----------------
    # Query DocumentItem quantities and amounts for the selected period
    all_products = db.query(Product).order_by(Product.code.asc()).all()
    
    item_sales_query = db.query(
        DocumentItem.description,
        func.sum(DocumentItem.quantity).label("total_qty"),
        func.sum(DocumentItem.amount).label("total_amount")
    ).join(Document, DocumentItem.document_id == Document.id).filter(
        Document.date.like(date_filter_pattern)
    ).group_by(DocumentItem.description).all()
    
    product_sales_dict = {}
    
    # Initialize all catalog products with 0 sales
    for p in all_products:
        product_sales_dict[p.name.strip()] = {
            "id": p.id,
            "code": p.code or "",
            "name": p.name,
            "description": p.description or "",
            "unit_price": p.unit_price,
            "stock_quantity": p.stock_quantity,
            "is_service": p.is_service,
            "image_url": p.image_url or "",
            "sold_qty": 0,
            "total_amount": 0.0
        }
        
    # Populate sales from documents
    for desc, qty, amt in item_sales_query:
        desc_clean = desc.strip() if desc else ""
        qty_val = int(qty) if qty else 0
        amt_val = float(amt) if amt else 0.0
        
        # Check if matched an existing product in dict
        matched = False
        for p_name in list(product_sales_dict.keys()):
            if desc_clean == p_name or desc_clean.startswith(p_name) or p_name.startswith(desc_clean):
                product_sales_dict[p_name]["sold_qty"] += qty_val
                product_sales_dict[p_name]["total_amount"] += amt_val
                matched = True
                break
                
        if not matched and desc_clean:
            # Custom/ad-hoc item
            product_sales_dict[desc_clean] = {
                "id": None,
                "code": "CUSTOM",
                "name": desc_clean,
                "description": "-",
                "unit_price": amt_val / (qty_val or 1),
                "stock_quantity": 0,
                "is_service": False,
                "image_url": "",
                "sold_qty": qty_val,
                "total_amount": amt_val
            }
            
    product_sales = list(product_sales_dict.values())
    # Sort by sold_qty descending, then total_amount descending
    product_sales.sort(key=lambda x: (x["sold_qty"], x["total_amount"]), reverse=True)
    
    total_items_sold = sum(p["sold_qty"] for p in product_sales)
        
    return {
        "year": year,
        "month": month or "ALL",
        "months_data": months_data,
        "cash_sales": cash_sum,
        "cheque_sales": cheque_sum,
        "total_sales": period_sales,
        "expenses_breakdown": expenses_breakdown,
        "total_expenses": total_expenses,
        "product_sales": product_sales,
        "total_items_sold": total_items_sold
    }

# ----------------- NEW SCHEMA DEFINITIONS -----------------
class BranchCreateSchema(BaseModel):
    name: str
    region: str
    address: str
    phone: Optional[str] = ""
    map_pin: Optional[str] = ""
    image_url: Optional[str] = ""

class ExpenseCreateSchema(BaseModel):
    voucher_number: Optional[str] = ""
    date: str
    category: str
    pay_to: Optional[str] = ""
    address: Optional[str] = ""
    tax_id: Optional[str] = ""
    description: Optional[str] = ""
    items_json: Optional[str] = "[]"
    subtotal: Optional[float] = 0.0
    withholding_tax_percent: Optional[float] = 0.0
    withholding_tax_amount: Optional[float] = 0.0
    amount: float
    net_amount: Optional[float] = 0.0
    note: Optional[str] = ""

# ----------------- BRANCHES API -----------------
@app.get("/api/branches")
def get_branches(db: Session = Depends(get_db)):
    from database import Branch
    return db.query(Branch).order_by(Branch.region, Branch.name).all()

@app.post("/api/branches")
def create_branch(branch_data: BranchCreateSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Branch
    new_br = Branch(
        name=branch_data.name,
        region=branch_data.region,
        address=branch_data.address,
        phone=branch_data.phone,
        map_pin=branch_data.map_pin,
        image_url=branch_data.image_url
    )
    db.add(new_br)
    db.commit()
    return {"success": True, "message": "เพิ่มข้อมูลสาขาสำเร็จ", "branch_id": new_br.id}

@app.put("/api/branches/{branch_id}")
def update_branch(branch_id: int, branch_data: BranchCreateSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Branch
    br = db.query(Branch).filter(Branch.id == branch_id).first()
    if not br:
        raise HTTPException(status_code=404, detail="ไม่พบสาขา")
    br.name = branch_data.name
    br.region = branch_data.region
    br.address = branch_data.address
    br.phone = branch_data.phone
    br.map_pin = branch_data.map_pin
    br.image_url = branch_data.image_url
    db.commit()
    return {"success": True, "message": "แก้ไขข้อมูลสาขาสำเร็จ"}

@app.delete("/api/branches/{branch_id}")
def delete_branch(branch_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Branch
    br = db.query(Branch).filter(Branch.id == branch_id).first()
    if not br:
        raise HTTPException(status_code=404, detail="ไม่พบสาขา")
    db.delete(br)
    db.commit()
    return {"success": True, "message": "ลบข้อมูลสาขาสำเร็จ"}

# ----------------- EXPENSES API -----------------
@app.get("/api/expenses/categories")
def get_expense_categories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    distinct_cats = db.query(Expense.category).distinct().all()
    cats = [c[0] for c in distinct_cats if c[0]]
    defaults = ["ค่าสินค้า/วัตถุดิบ", "ค่าเช่า/สถานที่", "ค่าเงินเดือน/ค่าแรง", "ค่าการตลาด/โฆษณา", "ค่าน้ำ/ค่าไฟ/สาธารณูปโภค", "ค่าใช้จ่ายทั่วไป"]
    
    # Mapping legacy names to clean official names
    legacy_map = {
        "ค่าน้ำ-ค่าไฟ": "ค่าน้ำ/ค่าไฟ/สาธารณูปโภค",
        "ค่าเช่าสถานที่": "ค่าเช่า/สถานที่",
        "ค่าแรง/จ้างงาน": "ค่าเงินเดือน/ค่าแรง",
        "ซื้อสินค้าเข้าสต็อก": "ค่าสินค้า/วัตถุดิบ",
        "อื่นๆ": "ค่าใช้จ่ายทั่วไป"
    }
    
    result = list(defaults)
    for c in cats:
        clean_c = legacy_map.get(c, c)
        if clean_c not in result:
            result.append(clean_c)
            
    return result

@app.get("/api/expenses")
def get_expenses(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    return db.query(Expense).order_by(Expense.date.desc()).all()

@app.post("/api/expenses")
def create_expense(exp_data: ExpenseCreateSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    
    v_num = exp_data.voucher_number
    if not v_num or not v_num.strip():
        count = db.query(Expense).count() + 1
        year_str = datetime.date.today().year
        v_num = f"PV-{year_str}-{count:04d}"
        
    sub_amt = exp_data.subtotal if (exp_data.subtotal and exp_data.subtotal > 0) else exp_data.amount
    net_amt = exp_data.net_amount if (exp_data.net_amount and exp_data.net_amount > 0) else exp_data.amount
    wht_amt = exp_data.withholding_tax_amount or 0.0

    new_exp = Expense()
    new_exp.date = exp_data.date
    new_exp.category = exp_data.category
    new_exp.amount = net_amt
    new_exp.description = exp_data.description or exp_data.pay_to or exp_data.category
    
    # Safe assignments for newly added Payment Voucher columns
    for attr, val in [
        ("voucher_number", v_num),
        ("pay_to", exp_data.pay_to),
        ("address", exp_data.address),
        ("tax_id", exp_data.tax_id),
        ("items_json", exp_data.items_json),
        ("subtotal", sub_amt),
        ("withholding_tax_percent", exp_data.withholding_tax_percent or 0.0),
        ("withholding_tax_amount", wht_amt),
        ("net_amount", net_amt),
        ("note", exp_data.note)
    ]:
        try:
            setattr(new_exp, attr, val)
        except Exception:
            pass

    db.add(new_exp)
    db.commit()
    
    res_v_num = getattr(new_exp, "voucher_number", None) or f"PV-{new_exp.id:04d}"
    
    create_audit_log(
        db=db,
        action="CREATE_EXPENSE",
        target_type="expense",
        target_id=str(new_exp.id),
        result="success",
        details=json.dumps({"voucher_number": res_v_num, "category": new_exp.category, "net_amount": net_amt, "pay_to": getattr(new_exp, 'pay_to', '')}),
        user=current_user,
        request=request
    )
    
    return {"success": True, "message": "บันทึกใบสำคัญจ่ายสำเร็จ", "expense_id": new_exp.id, "voucher_number": res_v_num}

@app.delete("/api/expenses/{exp_id}")
def delete_expense(exp_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    exp = db.query(Expense).filter(Expense.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="ไม่พบรายการรายจ่าย")
    v_num = getattr(exp, "voucher_number", None) or f"PV-{exp.id}"
    cat = exp.category
    amt = exp.amount
    db.delete(exp)
    db.commit()
    
    create_audit_log(
        db=db,
        action="DELETE_EXPENSE",
        target_type="expense",
        target_id=str(exp_id),
        result="success",
        details=json.dumps({"voucher_number": v_num, "category": cat, "amount": amt}),
        user=current_user,
        request=request
    )
    
    return {"success": True, "message": "ลบรายการรายจ่ายสำเร็จ"}

# ----------------- INVENTORY UPGRADE & RESTOCK -----------------
class RestockSchema(BaseModel):
    product_id: int
    quantity: int
    cost_amount: float
    date: str

@app.post("/api/products/restock")
def restock_product(restock_data: RestockSchema, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    prod = db.query(Product).filter(Product.id == restock_data.product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    
    # Update stock quantity
    old_stock = prod.stock_quantity or 0
    prod.stock_quantity = old_stock + restock_data.quantity
    
    # Register as expense
    new_exp = Expense(
        date=restock_data.date,
        category="ซื้อสินค้าเข้าสต็อก",
        amount=restock_data.cost_amount,
        description=f"เพิ่มสต็อก {prod.name} จำนวน {restock_data.quantity} ชิ้น (ราคารวม {restock_data.cost_amount:.2f} บาท)"
    )
    db.add(new_exp)
    db.commit()
    
    create_audit_log(
        db=db,
        action="UPDATE_STOCK",
        target_type="product",
        target_id=str(prod.id),
        result="success",
        details=json.dumps({
            "product_name": prod.name,
            "added_quantity": restock_data.quantity,
            "new_stock": prod.stock_quantity,
            "cost_amount": restock_data.cost_amount
        }),
        user=current_user,
        request=request
    )
    
    return {
        "success": True, 
        "message": f"เพิ่มสต็อก {prod.name} จำนวน {restock_data.quantity} ชิ้น เรียบร้อยแล้ว",
        "new_stock": prod.stock_quantity
    }

# ----------------- PAYMENT SLIP & IMAGE UPLOAD -----------------
from fastapi import File, UploadFile
import shutil
import uuid
import os
import base64

@app.post("/api/documents/upload-slip")
def upload_payment_slip(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads", "slips")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".pdf"]:
        raise HTTPException(status_code=400, detail="รูปแบบไฟล์ไม่รองรับ (รองรับเฉพาะ JPG, PNG, WEBP, PDF)")
        
    filename = f"slip_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"success": True, "filename": filename, "url": f"/static/uploads/slips/{filename}"}
    except Exception:
        try:
            file.file.seek(0)
            content = file.file.read()
            mime_ext = ext.replace(".", "")
            mime = "application/pdf" if mime_ext == "pdf" else f"image/{'jpeg' if mime_ext == 'jpg' else mime_ext}"
            b64_str = base64.b64encode(content).decode("utf-8")
            data_url = f"data:{mime};base64,{b64_str}"
            return {"success": True, "filename": data_url, "url": data_url}
        except Exception as err:
            raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการประมวลผลสลิป: {err}")

@app.post("/api/branches/upload-image")
def upload_branch_image(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads", "branches")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="รูปแบบไฟล์ไม่รองรับ (รองรับเฉพาะ JPG, PNG, WEBP)")
        
    filename = f"branch_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"success": True, "filename": filename, "url": f"/static/uploads/branches/{filename}"}
    except Exception:
        try:
            file.file.seek(0)
            content = file.file.read()
            mime_ext = ext.replace(".", "")
            if mime_ext == "jpg":
                mime_ext = "jpeg"
            b64_str = base64.b64encode(content).decode("utf-8")
            data_url = f"data:image/{mime_ext};base64,{b64_str}"
            return {"success": True, "filename": data_url, "url": data_url}
        except Exception as err:
            raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการประมวลผลรูปภาพ: {err}")

@app.post("/api/products/upload-image")
def upload_product_image(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads", "products")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="รูปแบบไฟล์ไม่รองรับ (รองรับเฉพาะ JPG, PNG, WEBP)")
        
    filename = f"product_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"success": True, "filename": filename, "url": f"/static/uploads/products/{filename}"}
    except Exception:
        try:
            file.file.seek(0)
            content = file.file.read()
            mime_ext = ext.replace(".", "")
            if mime_ext == "jpg":
                mime_ext = "jpeg"
            b64_str = base64.b64encode(content).decode("utf-8")
            data_url = f"data:image/{mime_ext};base64,{b64_str}"
            return {"success": True, "filename": data_url, "url": data_url}
        except Exception as err:
            raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการประมวลผลรูปภาพสินค้า: {err}")

# ----------------- SHARE ROUTE -----------------
@app.get("/share/invoice/{doc_id}", response_class=HTMLResponse)
def share_invoice(doc_id: int, request: Request, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสาร")
    
    items = sorted(doc.items, key=lambda x: x.item_index)
    display_items = []
    for item in items:
        display_items.append(item)
        
    padding_count = max(0, 8 - len(display_items))
    padding_rows = range(padding_count)
    
    return templates.TemplateResponse(
        request=request,
        name="print.html",
        context={
            "doc": doc,
            "items": display_items,
            "padding_rows": padding_rows,
            "share_mode": True
        }
    )

# ----------------- PRINT ROUTE -----------------
@app.get("/print/summary/list", response_class=HTMLResponse)
def print_documents_summary_list(
    request: Request,
    query: Optional[str] = None,
    year: Optional[str] = None,
    month: Optional[str] = None,
    payment_method: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    try:
        stmt = db.query(Document)
        
        if year and year.strip():
            if month and month.strip() and month != "ALL":
                try:
                    pattern = f"{year.strip()}-{int(month.strip()):02d}-%"
                except ValueError:
                    pattern = f"{year.strip()}-%"
            else:
                pattern = f"{year.strip()}-%"
            stmt = stmt.filter(Document.date.like(pattern))
            
        if payment_method and payment_method.strip():
            stmt = stmt.filter(Document.payment_method == payment_method.strip())
            
        raw_documents = stmt.order_by(Document.date.desc(), Document.id.desc()).all()
        
        # Filter by query string if provided
        if query and query.strip():
            q_clean = query.strip().lower()
            raw_documents = [
                d for d in raw_documents 
                if q_clean in (d.document_number or "").lower() or q_clean in (d.customer_name or "").lower()
            ]
            
        # Format dates & build safe dictionary list
        months_th = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
        doc_list = []
        total_sum = 0.0

        for doc in raw_documents:
            amt = float(doc.total_amount_after_vat or 0.0)
            total_sum += amt
            
            formatted_date = "-"
            if doc.date:
                try:
                    parts = str(doc.date).split('T')[0].split('-')
                    if len(parts) == 3:
                        y = int(parts[0]) + 543
                        m = int(parts[1])
                        d = int(parts[2])
                        if 1 <= m <= 12:
                            formatted_date = f"{d} {months_th[m-1]} {y}"
                        else:
                            formatted_date = str(doc.date)
                    else:
                        formatted_date = str(doc.date)
                except Exception:
                    formatted_date = str(doc.date)

            doc_list.append({
                "document_number": doc.document_number or "-",
                "formatted_date": formatted_date,
                "customer_name": doc.customer_name or "-",
                "total_amount_after_vat": amt,
                "payment_method": doc.payment_method or "CASH"
            })

        # Thai Date Today
        today = datetime.date.today()
        print_date = f"{today.day} {months_th[today.month - 1]} {today.year + 543}"
        
        filter_parts = []
        if year and year.strip(): filter_parts.append(f"ปี {year.strip()}")
        if month and month.strip(): filter_parts.append(f"เดือน {month.strip()}")
        if payment_method and payment_method.strip(): filter_parts.append(f"วิธีชำระเงิน: {payment_method.strip()}")
        if query and query.strip(): filter_parts.append(f"คำค้นหา: '{query.strip()}'")
        filter_desc = " | ".join(filter_parts) if filter_parts else "ทั้งหมด"

        return templates.TemplateResponse(
            request=request,
            name="print_documents_list.html",
            context={
                "documents": doc_list,
                "total_amount_sum": total_sum,
                "print_date": print_date,
                "filter_desc": filter_desc
            }
        )
    except Exception as e:
        print(f"Error rendering print_documents_list: {e}")
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการโหลดรายงานเอกสาร")

@app.get("/print/expenses/summary/list", response_class=HTMLResponse)
def print_expenses_summary_list(
    request: Request,
    year: Optional[str] = None,
    month: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    try:
        from database import Expense
        stmt = db.query(Expense)
        
        if year and year.strip() and year != "ALL":
            if month and month.strip() and month != "ALL":
                try:
                    pattern = f"{year.strip()}-{int(month.strip()):02d}-%"
                except ValueError:
                    pattern = f"{year.strip()}-%"
            else:
                pattern = f"{year.strip()}-%"
            stmt = stmt.filter(Expense.date.like(pattern))
        elif month and month.strip() and month != "ALL":
            try:
                pattern = f"%-{int(month.strip()):02d}-%"
                stmt = stmt.filter(Expense.date.like(pattern))
            except ValueError:
                pass
                
        if category and category.strip() and category != "ALL":
            stmt = stmt.filter(Expense.category == category.strip())
            
        raw_expenses = stmt.order_by(Expense.date.desc(), Expense.id.desc()).all()
        
        months_th = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
        exp_list = []
        total_sum = 0.0

        for exp in raw_expenses:
            amt = float(exp.net_amount or exp.amount or 0.0)
            total_sum += amt
            
            formatted_date = "-"
            if exp.date:
                try:
                    parts = str(exp.date).split('T')[0].split('-')
                    if len(parts) == 3:
                        y = int(parts[0]) + 543
                        m = int(parts[1])
                        d = int(parts[2])
                        if 1 <= m <= 12:
                            formatted_date = f"{d} {months_th[m-1]} {y}"
                        else:
                            formatted_date = str(exp.date)
                    else:
                        formatted_date = str(exp.date)
                except Exception:
                    formatted_date = str(exp.date)

            exp_list.append({
                "voucher_number": exp.voucher_number or f"PV-{str(exp.id).zfill(4)}",
                "formatted_date": formatted_date,
                "category": exp.category or "ทั่วไป",
                "pay_to": exp.pay_to or "-",
                "description": exp.description or exp.pay_to or "-",
                "amount": amt
            })

        # Thai Date Today
        today = datetime.date.today()
        print_date = f"{today.day} {months_th[today.month - 1]} {today.year + 543}"
        
        filter_parts = []
        if year and year.strip() and year != "ALL":
            try:
                th_year = int(year.strip()) + 543
                filter_parts.append(f"ปี {th_year} ({year.strip()})")
            except ValueError:
                filter_parts.append(f"ปี {year.strip()}")
        if month and month.strip() and month != "ALL":
            try:
                m_int = int(month.strip())
                if 1 <= m_int <= 12:
                    months_full = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
                    filter_parts.append(f"เดือน {months_full[m_int-1]}")
                else:
                    filter_parts.append(f"เดือน {month.strip()}")
            except ValueError:
                filter_parts.append(f"เดือน {month.strip()}")
        if category and category.strip() and category != "ALL":
            filter_parts.append(f"หมวดหมู่: {category.strip()}")
            
        filter_desc = " | ".join(filter_parts) if filter_parts else "ทั้งหมด (ALL)"

        return templates.TemplateResponse(
            request=request,
            name="print_expenses_list.html",
            context={
                "expenses": exp_list,
                "total_amount_sum": total_sum,
                "print_date": print_date,
                "filter_desc": filter_desc
            }
        )
    except Exception as e:
        print(f"Error rendering print_expenses_list: {e}")
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการโหลดรายงานรายจ่าย")

@app.get("/print/monthly-account", response_class=HTMLResponse)
@app.get("/api/reports/print-summary", response_class=HTMLResponse)
def print_monthly_account_summary(
    request: Request,
    year: Optional[str] = None,
    month: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_from_cookie)
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    try:
        now = datetime.date.today()
        target_year = year.strip() if (year and year.strip()) else str(now.year)
        
        # Fast bulk aggregation for 12 months (Jan - Dec)
        year_pattern = f"{target_year}-%"
        year_docs = db.query(Document.date, Document.total_amount_after_vat, Document.vat_amount).filter(
            Document.date.like(year_pattern)
        ).all()
        
        months_th = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
        monthly_stats = {m: {"sales": 0.0, "vat": 0.0, "count": 0, "expense": 0.0} for m in range(1, 13)}
        
        total_docs_count = 0
        total_vat_sum = 0.0
        total_sales_sum = 0.0
        
        for doc_date, sales, vat in year_docs:
            if doc_date and len(doc_date) >= 7:
                try:
                    m = int(doc_date.split("-")[1])
                    if 1 <= m <= 12:
                        s_val = float(sales or 0.0)
                        v_val = float(vat or 0.0)
                        monthly_stats[m]["sales"] += s_val
                        monthly_stats[m]["vat"] += v_val
                        monthly_stats[m]["count"] += 1
                        
                        total_docs_count += 1
                        total_vat_sum += v_val
                        total_sales_sum += s_val
                except Exception:
                    pass

        # Query expenses per month
        year_expenses = db.query(Expense.date, Expense.amount).filter(Expense.date.like(year_pattern)).all()
        for exp_date, exp_amt in year_expenses:
            if exp_date and len(exp_date) >= 7:
                try:
                    m = int(exp_date.split("-")[1])
                    if 1 <= m <= 12:
                        monthly_stats[m]["expense"] += float(exp_amt or 0.0)
                except Exception:
                    pass

        months_list = []
        for m in range(1, 13):
            s_val = monthly_stats[m]["sales"]
            e_val = monthly_stats[m]["expense"]
            months_list.append({
                "month_num": m,
                "month_name": months_th[m-1],
                "count": monthly_stats[m]["count"],
                "vat": monthly_stats[m]["vat"],
                "sales": s_val,
                "expense": e_val,
                "net": s_val - e_val
            })
            
        # Total Expenses for target_year
        exp_sum = db.query(func.sum(Expense.amount)).filter(Expense.date.like(year_pattern)).scalar()
        total_expenses = float(exp_sum) if exp_sum else 0.0
        net_profit = total_sales_sum - total_expenses

        # Thai Date Today
        print_date = f"{now.day} {months_th[now.month - 1]} {now.year + 543}"
        target_year_th = int(target_year) + 543 if target_year.isdigit() else target_year

        return templates.TemplateResponse(
            request=request,
            name="print_summary.html",
            context={
                "target_year": target_year,
                "target_year_th": target_year_th,
                "months_data": months_list,
                "total_docs_count": total_docs_count,
                "total_vat_sum": total_vat_sum,
                "total_sales_sum": total_sales_sum,
                "total_expenses": total_expenses,
                "net_profit": net_profit,
                "print_date": print_date
            }
        )
    except Exception as e:
        print(f"Error rendering print_summary: {e}")
        raise HTTPException(status_code=500, detail="เกิดข้อผิดพลาดในการโหลดรายงานประจำปี")

@app.get("/print/{doc_id}", response_class=HTMLResponse)
def print_invoice(doc_id: int, request: Request, db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user_from_cookie)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสารที่ต้องการพิมพ์")
    
    # Sort items
    items = sorted(doc.items, key=lambda x: x.item_index)
    
    # Pad items to at least 8 rows for standard invoice look
    display_items = []
    for item in items:
        display_items.append(item)
        
    # Calculate padding rows
    padding_count = max(0, 8 - len(display_items))
    padding_rows = range(padding_count)
    
    return templates.TemplateResponse(
        request=request,
        name="print.html",
        context={
            "doc": doc,
            "items": display_items,
            "padding_rows": padding_rows
        }
    )

@app.get("/print/shipping/{doc_id}", response_class=HTMLResponse)
def print_shipping_label(doc_id: int, request: Request, db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user_from_cookie)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสาร")
    return templates.TemplateResponse(
        request=request,
        name="shipping_label.html",
        context={
            "doc": doc
        }
    )

@app.get("/print/expense/{exp_id}", response_class=HTMLResponse)
def print_expense_voucher(exp_id: int, request: Request, db: Session = Depends(get_db), current_user: Optional[User] = Depends(get_current_user_from_cookie)):
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    import json
    from database import Expense
    exp = db.query(Expense).filter(Expense.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="ไม่พบใบสำคัญจ่ายที่ระบุ")
        
    items = []
    if exp.items_json:
        try:
            items = json.loads(exp.items_json)
        except Exception:
            items = []
            
    months_th = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
    formatted_date = str(exp.date)
    if exp.date:
        try:
            parts = str(exp.date).split('T')[0].split('-')
            if len(parts) == 3:
                y = int(parts[0]) + 543
                m = int(parts[1])
                d = int(parts[2])
                if 1 <= m <= 12:
                    formatted_date = f"{d} {months_th[m-1]} {y}"
        except Exception:
            pass

    setattr(exp, "formatted_date", formatted_date)
    
    padding_count = max(0, 8 - (len(items) if items else 1))
    padding_rows = range(padding_count)

    return templates.TemplateResponse(
        request=request,
        name="print_voucher.html",
        context={
            "exp": exp,
            "items": items,
            "padding_rows": padding_rows
        }
    )

# ----------------- VIDEO COURSES API -----------------
class VideoCourseSchema(BaseModel):
    title: str
    category: str = "ทั่วไป"
    video_url: str
    description: Optional[str] = None
    instructor: Optional[str] = "กัวซา เฮ้าส์"
    duration: Optional[str] = None

def convert_to_embed_url(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if "youtube.com/watch?v=" in url:
        v_id = url.split("watch?v=")[1].split("&")[0]
        return f"https://www.youtube.com/embed/{v_id}"
    elif "youtu.be/" in url:
        v_id = url.split("youtu.be/")[1].split("?")[0]
        return f"https://www.youtube.com/embed/{v_id}"
    elif "drive.google.com/file/d/" in url:
        f_id = url.split("drive.google.com/file/d/")[1].split("/")[0]
        return f"https://drive.google.com/file/d/{f_id}/preview"
    return url

@app.get("/api/videos")
def get_videos(category: Optional[str] = None, query: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(VideoCourse)
    if category and category != "ALL" and category != "":
        q = q.filter(VideoCourse.category == category)
    if query:
        search_pattern = f"%{query.strip()}%"
        q = q.filter(
            or_(
                VideoCourse.title.ilike(search_pattern),
                VideoCourse.description.ilike(search_pattern),
                VideoCourse.instructor.ilike(search_pattern)
            )
        )
    return q.order_by(VideoCourse.id.desc()).all()

@app.post("/api/videos")
def create_video(payload: VideoCourseSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    embed = convert_to_embed_url(payload.video_url)
    v = VideoCourse(
        title=payload.title,
        category=payload.category or "ทั่วไป",
        video_url=payload.video_url,
        embed_url=embed,
        description=payload.description,
        instructor=payload.instructor or "กัวซา เฮ้าส์",
        duration=payload.duration,
        created_by_user_id=current_user.id
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return {"success": True, "message": "เพิ่มคลิปการสอนเรียบร้อยแล้ว", "video": v}

@app.put("/api/videos/{video_id}")
def update_video(video_id: int, payload: VideoCourseSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    v = db.query(VideoCourse).filter(VideoCourse.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="ไม่พบคลิปการสอนที่ต้องการแก้ไข")
    
    v.title = payload.title
    v.category = payload.category or "ทั่วไป"
    v.video_url = payload.video_url
    v.embed_url = convert_to_embed_url(payload.video_url)
    v.description = payload.description
    v.instructor = payload.instructor or "กัวซา เฮ้าส์"
    v.duration = payload.duration
    db.commit()
    db.refresh(v)
    return {"success": True, "message": "อัปเดตข้อมูลคลิปการสอนเรียบร้อยแล้ว", "video": v}

@app.delete("/api/videos/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    v = db.query(VideoCourse).filter(VideoCourse.id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="ไม่พบคลิปการสอนที่ต้องการลบ")
    
    db.delete(v)
    db.commit()
    return {"success": True, "message": "ลบคลิปการสอนเรียบร้อยแล้ว"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
