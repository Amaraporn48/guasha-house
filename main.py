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

from database import engine, SessionLocal, init_db, User, Customer, Product, Document, DocumentItem

# Initialize database
init_db()

# Secret configurations for JWT
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "guasa_house_secret_key_2026_luxury_corp")
ALGORITHM = "HS256"

app = FastAPI(title="Guasha House Billing System")

# Base directory for reliable relative path resolution in Vercel/serverless environments
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Ensure upload directories exist safely
try:
    os.makedirs(os.path.join(STATIC_DIR, "uploads", "slips"), exist_ok=True)
    os.makedirs(os.path.join(STATIC_DIR, "uploads", "branches"), exist_ok=True)
    os.makedirs(os.path.join(STATIC_DIR, "uploads", "products"), exist_ok=True)
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
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

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
            
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
    finally:
        db.close()


def migrate_database():
    db = SessionLocal()
    try:
        db.execute(text("UPDATE products SET name = REPLACE(name, 'Guasa', 'Guasha')"))
        db.execute(text("UPDATE products SET description = REPLACE(description, 'Guasa', 'Guasha')"))
        
        # New Document columns
        for col in ["received_by", "received_date", "shipping_name", "shipping_address", "payment_slip"]:
            try:
                db.execute(text(f"ALTER TABLE documents ADD COLUMN {col} VARCHAR"))
            except Exception:
                pass
                
        # New Product columns
        try:
            db.execute(text("ALTER TABLE products ADD COLUMN stock_quantity INTEGER DEFAULT 0"))
        except Exception:
            pass
        try:
            db.execute(text("ALTER TABLE products ADD COLUMN is_service BOOLEAN DEFAULT 0"))
        except Exception:
            pass
        try:
            db.execute(text("ALTER TABLE products ADD COLUMN image_url VARCHAR"))
        except Exception:
            pass
            
        # New Branch columns
        try:
            db.execute(text("ALTER TABLE branches ADD COLUMN image_url VARCHAR"))
        except Exception:
            pass
            
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error migrating database: {e}")
    finally:
        db.close()

migrate_database()
seed_database()

# Authentication Helpers
def get_current_user(access_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

# UI Routing endpoints
@app.get("/", response_class=HTMLResponse)
def get_home_page(request: Request):
    return templates.TemplateResponse(request=request, name="home.html")

@app.get("/admin", response_class=HTMLResponse)
def get_admin_page(request: Request, access_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if not access_token:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(request=request, name="index.html", context={"user": user})
    except jwt.PyJWTError:
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(key="access_token")
        return response

@app.get("/login", response_class=HTMLResponse)
def get_login_page(request: Request, access_token: Optional[str] = Cookie(None), db: Session = Depends(get_db)):
    if access_token:
        try:
            payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            user = db.query(User).filter(User.username == username).first()
            if user:
                return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        except jwt.PyJWTError:
            pass
    return templates.TemplateResponse(request=request, name="login.html")

@app.post("/api/auth/login")
def login_api(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"}
        )
    
    # Generate JWT
    token_data = {
        "sub": user.username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    response = JSONResponse(content={"success": True, "message": "เข้าสู่ระบบสำเร็จ"})
    # Secure HTTPOnly Cookie valid for 7 days
    response.set_cookie(
        key="access_token", 
        value=token, 
        httponly=True, 
        max_age=7 * 24 * 3600, 
        samesite="lax",
        secure=False # Set to True in production with HTTPS
    )
    return response

@app.get("/api/auth/logout")
def logout_api():
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

# ----------------- USER MANAGEMENT API -----------------
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
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
def create_user(user: UserCreateSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not user.username or not user.password or not user.fullname:
        raise HTTPException(status_code=400, detail="กรุณากรอกข้อมูลให้ครบถ้วน")
        
    existing = db.query(User).filter(User.username == user.username.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="ชื่อผู้ใช้งาน (Username) นี้ถูกใช้งานแล้ว")
        
    new_user = User(
        username=user.username.strip(),
        fullname=user.fullname.strip(),
        hashed_password=hash_password(user.password),
        role=user.role or "staff"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"success": True, "message": "เพิ่มผู้ใช้งานสำเร็จ", "id": new_user.id}

@app.put("/api/users/{user_id}")
def update_user(user_id: int, user: UserUpdateSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลผู้ใช้งาน")
        
    if user.username.strip() != u.username:
        existing = db.query(User).filter(User.username == user.username.strip()).first()
        if existing:
            raise HTTPException(status_code=400, detail="ชื่อผู้ใช้งาน (Username) นี้ถูกใช้งานแล้ว")
            
    u.username = user.username.strip()
    u.fullname = user.fullname.strip()
    u.role = user.role or "staff"
    
    if user.password and user.password.strip():
        u.hashed_password = hash_password(user.password.strip())
        
    db.commit()
    return {"success": True, "message": "แก้ไขข้อมูลผู้ใช้งานสำเร็จ"}

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="ไม่สามารถลบบัญชีผู้ใช้ที่กำลังเข้าสู่ระบบอยู่ได้")
        
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลผู้ใช้งาน")
        
    db.delete(u)
    db.commit()
    return {"success": True, "message": "ลบผู้ใช้งานสำเร็จ"}

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
def create_customer(customer: CustomerSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Check if duplicate name
    existing = db.query(Customer).filter(Customer.name == customer.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="มีลูกค้าชื่อนี้อยู่ในระบบแล้ว")
    
    new_cust = Customer(
        name=customer.name,
        address=customer.address,
        tax_id=customer.tax_id,
        phone=customer.phone,
        email=customer.email,
        notes=customer.notes
    )
    db.add(new_cust)
    db.commit()
    db.refresh(new_cust)
    return new_cust

@app.put("/api/customers/{customer_id}")
def update_customer(customer_id: int, customer: CustomerSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลลูกค้า")
        
    cust.name = customer.name
    cust.address = customer.address
    cust.tax_id = customer.tax_id
    cust.phone = customer.phone
    cust.email = customer.email
    cust.notes = customer.notes
    db.commit()
    db.refresh(cust)
    return cust

@app.delete("/api/customers/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cust = db.query(Customer).filter(Customer.id == customer_id).first()
    if not cust:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลลูกค้า")
    db.delete(cust)
    db.commit()
    return {"success": True, "message": "ลบข้อมูลลูกค้าสำเร็จ"}

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
def create_product(product: ProductSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
    return new_prod

@app.put("/api/products/{product_id}")
def update_product(product_id: int, product: ProductSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
    return prod

@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    prod = db.query(Product).filter(Product.id == product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="ไม่พบข้อมูลสินค้า")
    db.delete(prod)
    db.commit()
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
def create_document(doc_data: DocumentCreateSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    max_attempts = 10
    # Extract year from document date
    doc_year = "2026"
    if doc_data.date and len(doc_data.date) >= 4:
        doc_year = doc_data.date[:4]
        
    for attempt in range(max_attempts):
        try:
            # We use an immediate/nested transaction to ensure safety
            with db.begin_nested():
                doc_num = generate_invoice_number(db, doc_year)
                
                # Check for absolute safety in DB state (prevents duplicate number generation in memory)
                existing = db.query(Document).filter(Document.document_number == doc_num).first()
                if existing:
                    # Let loop retry and fetch new incremented serial
                    raise IntegrityError("Collision detected", params=None, orig=None)
                
                new_doc = Document(
                    document_number=doc_num,
                    date=doc_data.date,
                    customer_id=doc_data.customer_id,
                    customer_name=doc_data.customer_name,
                    customer_address=doc_data.customer_address,
                    customer_tax_id=doc_data.customer_tax_id,
                    customer_phone=doc_data.customer_phone,
                    customer_email=doc_data.customer_email,
                    total_amount_before_vat=doc_data.total_amount_before_vat,
                    vat_amount=doc_data.vat_amount,
                    total_amount_after_vat=doc_data.total_amount_after_vat,
                    total_amount_text=bahttext(doc_data.total_amount_after_vat),
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
                db.flush() # Forces SQL execution within nesting to trigger unique constraint errors
                
                for idx, item in enumerate(doc_data.items, 1):
                    new_item = DocumentItem(
                         document_id=new_doc.id,
                         item_index=idx,
                         description=item.description,
                         quantity=item.quantity,
                         unit_price=item.unit_price,
                         amount=item.quantity * item.unit_price
                    )
                    db.add(new_item)
                    
                    # Stock deduction logic
                    prod = db.query(Product).filter(Product.name == item.description).first()
                    if prod and not prod.is_service:
                        prod.stock_quantity = max(0, prod.stock_quantity - int(item.quantity))
                
            db.commit()
            return {"success": True, "document_id": new_doc.id, "document_number": doc_num}
        except IntegrityError:
            db.rollback()
            if attempt == max_attempts - 1:
                raise HTTPException(status_code=500, detail="ไม่สามารถสร้างเลขที่เอกสารแบบไม่ซ้ำกันได้เนื่องจากการใช้งานที่หนาแน่น กรุณาลองใหม่อีกครั้ง")
            # Otherwise, loop will rerun transaction block
            continue

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
        # Search document number or customer name
        search_filter = or_(
            Document.document_number.like(f"%{query}%"),
            Document.customer_name.like(f"%{query}%")
        )
        q = q.filter(search_filter)
        
    if date:
        q = q.filter(Document.date == date)
        
    if month:
        # Match YYYY-MM
        q = q.filter(Document.date.like(f"%-{month}-%"))
        
    if year:
        # Match YYYY-...
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
    
    # Convert relational list to dict output
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
def update_document(doc_id: int, doc_data: DocumentCreateSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสาร")
        
    try:
        with db.begin_nested():
            # Update main record fields (keep document number same)
            doc.date = doc_data.date
            doc.customer_id = doc_data.customer_id
            doc.customer_name = doc_data.customer_name
            doc.customer_address = doc_data.customer_address
            doc.customer_tax_id = doc_data.customer_tax_id
            doc.customer_phone = doc_data.customer_phone
            doc.customer_email = doc_data.customer_email
            
            doc.total_amount_before_vat = doc_data.total_amount_before_vat
            doc.vat_amount = doc_data.vat_amount
            doc.total_amount_after_vat = doc_data.total_amount_after_vat
            doc.total_amount_text = bahttext(doc_data.total_amount_after_vat)
            
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
                prod = db.query(Product).filter(Product.name == old_item.description).first()
                if prod and not prod.is_service:
                    prod.stock_quantity = prod.stock_quantity + int(old_item.quantity)
            
            # Clear old items
            db.query(DocumentItem).filter(DocumentItem.document_id == doc.id).delete()
            
            # Add updated items
            for idx, item in enumerate(doc_data.items, 1):
                new_item = DocumentItem(
                    document_id=doc.id,
                    item_index=idx,
                    description=item.description,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    amount=item.quantity * item.unit_price
                )
                db.add(new_item)
                
                # Deduct stock for new items
                prod = db.query(Product).filter(Product.name == item.description).first()
                if prod and not prod.is_service:
                    prod.stock_quantity = max(0, prod.stock_quantity - int(item.quantity))
                
        db.commit()
        return {"success": True, "document_id": doc.id, "document_number": doc.document_number}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการแก้ไขเอกสาร: {str(e)}")

@app.post("/api/documents/{doc_id}/duplicate")
def duplicate_document(doc_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    old_doc = db.query(Document).filter(Document.id == doc_id).first()
    if not old_doc:
        raise HTTPException(status_code=404, detail="ไม่พบต้นฉบับเอกสาร")
        
    # Prepare duplicate schema data
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
    
    return create_document(doc_create_data, db, current_user)

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสาร")
    db.delete(doc)
    db.commit()
    return {"success": True, "message": "ลบเอกสารสำเร็จ"}

# ----------------- DASHBOARD API -----------------
@app.get("/api/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    
    # Total documents
    total_docs = db.query(Document).count()
    
    # Get current month pattern YYYY-MM
    now = datetime.date.today()
    current_month_str = f"{now.year}-{now.month:02d}"
    
    # Current month documents count
    month_docs = db.query(Document).filter(Document.date.like(f"{current_month_str}-%")).count()
    
    # Current month sales (sum of total_amount_after_vat)
    month_sales_query = db.query(func.sum(Document.total_amount_after_vat)).filter(
        Document.date.like(f"{current_month_str}-%")
    ).scalar()
    month_sales = float(month_sales_query) if month_sales_query else 0.0
    
    # Current month expenses
    month_exp_query = db.query(func.sum(Expense.amount)).filter(
        Expense.date.like(f"{current_month_str}-%")
    ).scalar()
    month_expenses = float(month_exp_query) if month_exp_query else 0.0
    
    # Net profit current month
    net_profit_month = month_sales - month_expenses
    
    # Total sales all time
    total_sales_query = db.query(func.sum(Document.total_amount_after_vat)).scalar()
    total_sales = float(total_sales_query) if total_sales_query else 0.0
    
    # Total expenses all time
    total_exp_query = db.query(func.sum(Expense.amount)).scalar()
    total_expenses = float(total_exp_query) if total_exp_query else 0.0
    
    # Total customers
    total_cust = db.query(Customer).count()
    
    # 12 Months breakdown for Dashboard Chart
    months_chart_data = []
    months_th = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    for m in range(1, 13):
        m_str = f"{now.year}-{m:02d}"
        
        s_sum = db.query(func.sum(Document.total_amount_after_vat)).filter(
            Document.date.like(f"{m_str}-%")
        ).scalar()
        s_val = float(s_sum) if s_sum else 0.0
        
        e_sum = db.query(func.sum(Expense.amount)).filter(
            Expense.date.like(f"{m_str}-%")
        ).scalar()
        e_val = float(e_sum) if e_sum else 0.0
        
        months_chart_data.append({
            "month_num": m,
            "month_name": months_th[m-1],
            "sales": s_val,
            "expenses": e_val,
            "profit": s_val - e_val
        })

    # Recent documents (5)
    recent_docs = db.query(Document).order_by(Document.document_number.desc()).limit(5).all()
    
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
        "monthly_documents": month_docs,
        "monthly_sales": month_sales,
        "monthly_expenses": month_expenses,
        "net_profit_month": net_profit_month,
        "total_sales": total_sales,
        "total_expenses": total_expenses,
        "total_customers": total_cust,
        "months_chart_data": months_chart_data,
        "recent_documents": recent_list
    }

# ----------------- REPORTS API -----------------
@app.get("/api/reports/summary")
def get_reports_summary(year: Optional[str] = None, month: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not year:
        year = str(datetime.date.today().year)
        
    # Generate data for months Jan-Dec
    months_data = []
    for m in range(1, 13):
        m_str = f"{year}-{m:02d}"
        
        sales_sum = db.query(func.sum(Document.total_amount_after_vat)).filter(
            Document.date.like(f"{m_str}-%")
        ).scalar()
        sales_sum = float(sales_sum) if sales_sum else 0.0
        
        vat_sum = db.query(func.sum(Document.vat_amount)).filter(
            Document.date.like(f"{m_str}-%")
        ).scalar()
        vat_sum = float(vat_sum) if vat_sum else 0.0
        
        count = db.query(Document).filter(
            Document.date.like(f"{m_str}-%")
        ).count()
        
        months_data.append({
            "month_num": m,
            "month_name": ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."][m-1],
            "sales": sales_sum,
            "vat": vat_sum,
            "count": count
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
    defaults = ["ค่าน้ำ-ค่าไฟ", "ค่าเช่าสถานที่", "ค่าแรง/จ้างงาน", "ซื้อสินค้าเข้าสต็อก", "อื่นๆ"]
    for d in defaults:
        if d not in cats:
            cats.append(d)
    return cats

@app.get("/api/expenses")
def get_expenses(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    return db.query(Expense).order_by(Expense.date.desc()).all()

@app.post("/api/expenses")
def create_expense(exp_data: ExpenseCreateSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    new_exp = Expense(
        amount=exp_data.amount,
        category=exp_data.category,
        description=exp_data.description,
        date=exp_data.date
    )
    db.add(new_exp)
    db.commit()
    return {"success": True, "message": "บันทึกรายจ่ายสำเร็จ", "expense_id": new_exp.id}

@app.delete("/api/expenses/{exp_id}")
def delete_expense(exp_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    exp = db.query(Expense).filter(Expense.id == exp_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="ไม่พบรายการรายจ่าย")
    db.delete(exp)
    db.commit()
    return {"success": True, "message": "ลบรายการรายจ่ายสำเร็จ"}

# ----------------- INVENTORY UPGRADE & RESTOCK -----------------
class RestockSchema(BaseModel):
    product_id: int
    quantity: int
    cost_amount: float
    date: str

@app.post("/api/products/restock")
def restock_product(restock_data: RestockSchema, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from database import Expense
    prod = db.query(Product).filter(Product.id == restock_data.product_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้า")
    
    # Update stock quantity
    prod.stock_quantity = (prod.stock_quantity or 0) + restock_data.quantity
    
    # Register as expense
    new_exp = Expense(
        amount=restock_data.cost_amount,
        category="ซื้อสินค้าเข้าสต็อก",
        description=f"ซื้อสินค้าเติมสต็อก: {prod.name} จำนวน {restock_data.quantity} ชิ้น",
        date=restock_data.date
    )
    db.add(new_exp)
    db.commit()
    return {"success": True, "message": "เพิ่มสินค้าเข้าสต็อกและบันทึกรายจ่ายสำเร็จ", "new_stock": prod.stock_quantity}

# ----------------- PAYMENT SLIP UPLOAD -----------------
from fastapi import File, UploadFile
import shutil
import uuid
import os

@app.post("/api/documents/upload-slip")
def upload_payment_slip(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    UPLOAD_DIR = "static/uploads/slips"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".pdf"]:
        raise HTTPException(status_code=400, detail="รูปแบบไฟล์ไม่รองรับ (รองรับเฉพาะ JPG, PNG, WEBP, PDF)")
        
    filename = f"slip_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการบันทึกไฟล์: {e}")
        
    return {"success": True, "filename": filename, "url": f"/static/uploads/slips/{filename}"}

@app.post("/api/branches/upload-image")
def upload_branch_image(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    UPLOAD_DIR = "static/uploads/branches"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="รูปแบบไฟล์ไม่รองรับ (รองรับเฉพาะ JPG, PNG, WEBP)")
        
    filename = f"branch_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการบันทึกไฟล์: {e}")
        
    return {"success": True, "filename": filename, "url": f"/static/uploads/branches/{filename}"}

@app.post("/api/products/upload-image")
def upload_product_image(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    UPLOAD_DIR = "static/uploads/products"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="รูปแบบไฟล์ไม่รองรับ (รองรับเฉพาะ JPG, PNG, WEBP)")
        
    filename = f"product_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    
    try:
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"เกิดข้อผิดพลาดในการบันทึกไฟล์: {e}")
        
    return {"success": True, "filename": filename, "url": f"/static/uploads/products/{filename}"}

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
@app.get("/print/{doc_id}", response_class=HTMLResponse)
def print_invoice(doc_id: int, request: Request, db: Session = Depends(get_db)):
    # Load document without strict user context for easy print popup
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสารที่ต้องการพิมพ์")
    
    # Sort items
    items = sorted(doc.items, key=lambda x: x.item_index)
    
    # Pad items to at least 5 rows for standard invoice look
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
def print_shipping_label(doc_id: int, request: Request, db: Session = Depends(get_db)):
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
def print_expense_voucher(exp_id: int, request: Request, db: Session = Depends(get_db)):
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

    return templates.TemplateResponse(
        request=request,
        name="print_voucher.html",
        context={
            "exp": exp,
            "items": items
        }
    )

@app.get("/print/summary/list", response_class=HTMLResponse)
def print_documents_summary(
    request: Request,
    query: Optional[str] = None,
    year: Optional[str] = None,
    month: Optional[str] = None,
    payment_method: Optional[str] = None,
    db: Session = Depends(get_db)
):
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
            name="print_summary.html",
            context={
                "documents": doc_list,
                "total_amount_sum": total_sum,
                "print_date": print_date,
                "filter_desc": filter_desc
            }
        )
    except Exception as e:
        print(f"Error rendering print_summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
