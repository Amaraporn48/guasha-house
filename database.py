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
    role = Column(String, default="staff") # admin / developer / staff
    token_version = Column(Integer, default=1, nullable=False)
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

class Region(Base):
    __tablename__ = "regions"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    display_order = Column(Integer, default=0)
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
    thumbnail_url = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    instructor = Column(String, default="กัวซา เฮ้าส์")
    duration = Column(String, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True, nullable=False)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String, nullable=True, index=True)
    role = Column(String, nullable=True) # admin / developer / staff / anonymous
    action = Column(String, nullable=False, index=True) # LOGIN, LOGOUT, LOGIN_FAILED, CHANGE_PASSWORD, etc.
    target_type = Column(String, nullable=True) # auth, user, document, expense, customer, product, system
    target_id = Column(String, nullable=True) # document_number, user_id, etc.
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    result = Column(String, default="success") # success / failed
    details = Column(Text, nullable=True) # Sanitized audit summary (STRICTLY NO PASSWORDS OR TOKENS)

class SlideBanner(Base):
    __tablename__ = "slide_banners"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=True)
    subtitle = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String, nullable=False)
    link_url = Column(String, nullable=True, default="")
    order_index = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class SiteSetting(Base):
    __tablename__ = "site_settings"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        
        # Safely migrate columns in isolated transactions
        is_pg = "postgresql" in str(engine.url).lower()
        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER DEFAULT 1;" if is_pg else "ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 1;",
            "ALTER TABLE video_courses ADD COLUMN IF NOT EXISTS thumbnail_url VARCHAR;" if is_pg else "ALTER TABLE video_courses ADD COLUMN thumbnail_url VARCHAR;"
        ]
        for cmd in migrations:
            try:
                with engine.connect() as conn:
                    conn.execute(text(cmd))
                    conn.commit()
            except Exception:
                pass
                
        # Seed default admin user only if users table is empty
        db = SessionLocal()
        try:
            if db.query(User).count() == 0:
                import bcrypt
                def hash_pw(pw_str: str) -> str:
                    return bcrypt.hashpw(pw_str.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                admin_user = User(
                    username="guasha",
                    fullname="Guasha Administrator",
                    role="admin",
                    token_version=1,
                    hashed_password=hash_pw("199/4")
                )
                db.add(admin_user)
                db.commit()
                print("✅ Initial admin user 'guasha' seeded successfully.")

            # Seed default slide banners if table is empty
            if db.query(SlideBanner).count() == 0:
                default_banners = [
                    SlideBanner(
                        image_url="/static/banner1.png",
                        subtitle="",
                        title="",
                        description="",
                        link_url="#branches",
                        order_index=1,
                        is_active=True
                    ),
                    SlideBanner(
                        image_url="https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=1200&q=80",
                        subtitle="Professional Training Course",
                        title="คอร์สเรียนสปานวดกัวซายกกระชับระดับมืออาชีพ",
                        description="หลักสูตรเรียนกัวซาอย่างละเอียดทุกขั้นตอน สอนเทคนิคการกวาดเปิดน้ำเหลืองและผ่อนคลายกล้ามเนื้อหน้าสำหรับทำธุรกิจหรือดูแลตัวเอง",
                        link_url="#lessons",
                        order_index=2,
                        is_active=True
                    ),
                    SlideBanner(
                        image_url="https://images.unsplash.com/photo-1608248597279-f99d160bfcbc?auto=format&fit=crop&w=1200&q=80",
                        subtitle="Guasha House Skincare",
                        title="ผลิตภัณฑ์ครีมบำรุงธรรมชาติสำหรับนวดกัวซา",
                        description="พัฒนาครีมและน้ำมันสูตรพิเศษสำหรับหล่อลื่นผิวขณะทำกัวซา อุดมด้วยสารสกัดธรรมชาติบริสุทธิ์เพื่อความกระจ่างใสเปล่งปลั่ง",
                        link_url="#products",
                        order_index=3,
                        is_active=True
                    )
                ]
                db.add_all(default_banners)
                db.commit()
                print("✅ Default slide banners seeded successfully.")

            # Seed default site settings if not present
            default_settings = {
                "contact_phone": "061-496-6361",
                "contact_address": "บริษัท กัวซา เฮ้าส์ จำกัด\n199/4 ถนนกรุงเทพกรีฑา แขวงหัวหมาก เขตบางกะปิ กรุงเทพฯ 10240",
                "contact_line_url": "https://line.me",
                "contact_line_id": "@guashahouse",
                "contact_facebook_url": "https://www.facebook.com/share/19USgHRf1X/?mibextid=wwXIfr",
                "contact_tiktok_url": "https://www.tiktok.com/@guashahouse_bykrunoon",
                "contact_email": "info@guashahouse.com"
            }
            for k, v in default_settings.items():
                existing = db.query(SiteSetting).filter(SiteSetting.key == k).first()
                if not existing:
                    db.add(SiteSetting(key=k, value=v))
            db.commit()
            print("✅ Default site settings seeded successfully.")

            # Seed default regions if not present
            from database import Region
            default_regions = [
                ("กรุงเทพฯ", 0),
                ("ภาคกลาง", 1),
                ("ภาคเหนือ", 2),
                ("ภาคใต้", 3),
                ("ภาคตะวันออกเฉียงเหนือ", 4),
            ]
            for region_name, order in default_regions:
                if not db.query(Region).filter(Region.name == region_name).first():
                    db.add(Region(name=region_name, display_order=order))
            db.commit()
            print("✅ Default regions seeded successfully.")
        finally:
            db.close()
    except Exception as e:
        print("init_db note:", e)
