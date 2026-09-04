import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from sqlalchemy.pool import NullPool

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./guasa_house.db")

# Convert postgres:// URI scheme to postgresql:// for SQLAlchemy compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

is_serverless = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME") or os.getenv("SERVERLESS"))

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
elif is_serverless:
    # Use NullPool on serverless to prevent connection exhaustion across ephemeral Lambdas
    engine = create_engine(DATABASE_URL, poolclass=NullPool, pool_pre_ping=True)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    fullname = Column(String, nullable=False)
    role = Column(String, default="staff") # admin / staff
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    address = Column(String, nullable=False)
    tax_id = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=True)
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    unit_price = Column(Float, default=0.0)
    stock_quantity = Column(Integer, default=0)
    is_service = Column(Boolean, default=False)
    image_url = Column(String, nullable=True) # Product Image URL
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    document_number = Column(String, unique=True, index=True, nullable=False) # e.g. INV-2026-0001
    date = Column(String, index=True, nullable=False) # YYYY-MM-DD
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    customer_name = Column(String, nullable=False)
    customer_address = Column(String, nullable=False)
    customer_tax_id = Column(String, nullable=False)
    customer_phone = Column(String, nullable=True)
    customer_email = Column(String, nullable=True)
    
    total_amount_before_vat = Column(Float, default=0.0)
    vat_amount = Column(Float, default=0.0)
    total_amount_after_vat = Column(Float, default=0.0)
    total_amount_text = Column(String, nullable=False) # e.g. หนึ่งหมื่นบาทถ้วน
    
    payment_method = Column(String, nullable=False) # CASH / CHEQUE
    cheque_bank = Column(String, nullable=True)
    cheque_number = Column(String, nullable=True)
    cheque_date = Column(String, nullable=True)
    cheque_branch = Column(String, nullable=True)
    
    received_by = Column(String, nullable=True)
    received_date = Column(String, nullable=True)
    
    shipping_name = Column(String, nullable=True)
    shipping_address = Column(String, nullable=True)
    payment_slip = Column(String, nullable=True)
    
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_by_username = Column(String, nullable=False)
    status = Column(String, default="issued") # issued / void
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    items = relationship("DocumentItem", back_populates="document", cascade="all, delete-orphan")

class DocumentItem(Base):
    __tablename__ = "document_items"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    item_index = Column(Integer, nullable=False)
    description = Column(String, nullable=False)
    quantity = Column(Float, default=0.0)
    unit_price = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    
    document = relationship("Document", back_populates="items")

class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    region = Column(String, nullable=False) # e.g. กรุงเทพฯ, ภาคเหนือ, ภาคใต้, ภาคกลาง
    address = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    map_pin = Column(String, nullable=True) # Google Maps URL
    image_url = Column(String, nullable=True) # Storefront Image URL
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    voucher_number = Column(String, nullable=True) # PV-2026-0001
    date = Column(String, index=True, nullable=False) # YYYY-MM-DD
    category = Column(String, nullable=False) # ค่าน้ำ-ค่าไฟ, ค่าเช่า, ค่าแรง, ซื้อสินค้าเข้าสต็อก, ฯลฯ
    pay_to = Column(String, nullable=True) # จ่ายให้แก่ใคร
    address = Column(String, nullable=True) # ที่อยู่ผู้รับเงิน
    tax_id = Column(String, nullable=True) # เลขประจำตัวผู้เสียภาษีผู้รับเงิน
    description = Column(String, nullable=True) # รายละเอียดสรุป
    items_json = Column(Text, nullable=True) # รายการสินค้า/บริการในตาราง (JSON)
    subtotal = Column(Float, default=0.0) # จำนวนเงินรวมก่อนหักภาษี
    withholding_tax_percent = Column(Float, default=0.0) # 3% หรือ 0%
    withholding_tax_amount = Column(Float, default=0.0) # ยอดเงินหัก ณ ที่จ่าย
    amount = Column(Float, default=0.0) # จำนวนเงินสุทธิ (net_amount)
    net_amount = Column(Float, default=0.0) # จำนวนเงินสุทธิ
    note = Column(String, nullable=True) # หมายเหตุ
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class VideoCourse(Base):
    __tablename__ = "video_courses"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    category = Column(String, default="ทั่วไป")
    video_url = Column(String, nullable=False)
    embed_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    instructor = Column(String, default="กัวซา เฮ้าส์")
    duration = Column(String, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            import bcrypt
            def hash_pw(pw_str: str) -> str:
                return bcrypt.hashpw(pw_str.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Ensure guasha user exists with requested credentials
            guasha_user = db.query(User).filter(User.username == "guasha").first()
            if not guasha_user:
                guasha_user = User(
                    username="guasha",
                    fullname="Guasha Administrator",
                    role="admin",
                    hashed_password=hash_pw("199/4")
                )
                db.add(guasha_user)
            else:
                guasha_user.hashed_password = hash_pw("199/4")
                guasha_user.role = "admin"
                
            # Seed user1 if not present
            user1 = db.query(User).filter(User.username == "user1").first()
            if not user1:
                user1 = User(
                    username="user1",
                    fullname="Account 1",
                    role="admin",
                    hashed_password=hash_pw("123456")
                )
                db.add(user1)
                
            db.commit()
            print("✅ User 'guasha' configured with admin access.")
        finally:
            db.close()
    except Exception as e:
        print("init_db note:", e)
