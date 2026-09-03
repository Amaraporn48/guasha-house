import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./guasa_house.db")

# Convert postgres:// URI scheme to postgresql:// for SQLAlchemy compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if "sqlite" in DATABASE_URL:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
    date = Column(String, nullable=False) # YYYY-MM-DD
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
    date = Column(String, nullable=False) # YYYY-MM-DD
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

def init_db():
    Base.metadata.create_all(bind=engine)
    # Auto-add missing columns for SQLite/PostgreSQL fallback
    for col_name, col_type in [
        ("voucher_number", "VARCHAR"),
        ("pay_to", "VARCHAR"),
        ("address", "VARCHAR"),
        ("tax_id", "VARCHAR"),
        ("items_json", "TEXT"),
        ("subtotal", "FLOAT"),
        ("withholding_tax_percent", "FLOAT"),
        ("withholding_tax_amount", "FLOAT"),
        ("net_amount", "FLOAT"),
        ("note", "VARCHAR")
    ]:
        try:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE expenses ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
        except Exception:
            pass
