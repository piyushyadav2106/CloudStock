import os
from datetime import datetime
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-before-deployment")
uri = os.getenv("DATABASE_URL", "sqlite:///inventory.db")
if uri.startswith("mysql://"):
    uri = uri.replace("mysql://", "mysql+pymysql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    sku = db.Column(db.String(40), unique=True, nullable=False)
    category = db.Column(db.String(80), default="General")
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    threshold = db.Column(db.Integer, nullable=False, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice = db.Column(db.String(40), unique=True, nullable=False)
    customer = db.Column(db.String(120), nullable=False, default="Walk-in Customer")
    phone = db.Column(db.String(30), default="")
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    tax = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship("SaleItem", backref="sale", cascade="all, delete-orphan")

class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sale.id"), nullable=False)
    product_id = db.Column(db.Integer, nullable=True)
    name = db.Column(db.String(120), nullable=False)
    sku = db.Column(db.String(40), nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)

@app.template_filter("money")
def money(value):
    try: return "₹{:,.2f}".format(Decimal(value or 0))
    except Exception: return "₹0.00"

@app.context_processor
def globals_for_templates():
    return {"year": datetime.now().year}

@app.route("/")
def dashboard():
    count = Product.query.count()
    value = db.session.query(func.sum(Product.cost * Product.stock)).scalar() or 0
    today = datetime.now().date()
    revenue = db.session.query(func.sum(Sale.total)).filter(func.date(Sale.created_at) == today).scalar() or 0
    low = Product.query.filter(Product.stock <= Product.threshold).order_by(Product.stock).limit(6).all()
    recent = Sale.query.order_by(Sale.created_at.desc()).limit(6).all()
    days = []
    for n in range(6, -1, -1):
        day = today.fromordinal(today.toordinal()-n)
        total = db.session.query(func.sum(Sale.total)).filter(func.date(Sale.created_at) == day).scalar() or 0
        days.append({"label": day.strftime("%a"), "total": float(total)})
    return render_template("dashboard.html", active="dashboard", count=count, value=value, revenue=revenue,
                           sale_count=Sale.query.count(), low=low, recent=recent, days=days)

@app.route("/products")
def products():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    query = Product.query
    if q: query = query.filter(db.or_(Product.name.ilike(f"%{q}%"), Product.sku.ilike(f"%{q}%")))
    if category: query = query.filter_by(category=category)
    categories = [x[0] for x in db.session.query(Product.category).distinct().order_by(Product.category).all()]
    return render_template("products.html", active="products", products=query.order_by(Product.created_at.desc()).all(),
                           q=q, category=category, categories=categories)

@app.route("/products/new", methods=["GET", "POST"])
@app.route("/products/<int:pid>/edit", methods=["GET", "POST"])
def product_form(pid=None):
    p = Product.query.get_or_404(pid) if pid else None
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            sku = request.form["sku"].strip().upper()
            price, cost = Decimal(request.form["price"]), Decimal(request.form["cost"])
            stock, threshold = int(request.form["stock"]), int(request.form["threshold"])
            duplicate = Product.query.filter(Product.sku == sku, Product.id != (p.id if p else -1)).first()
            if not name or not sku or duplicate or min(price, cost, stock, threshold) < 0: raise ValueError()
            if p is None: p = Product(name=name, sku=sku)
            p.name, p.sku = name, sku
            p.category = request.form.get("category", "General").strip() or "General"
            p.price, p.cost, p.stock, p.threshold = price, cost, stock, threshold
            db.session.add(p); db.session.commit()
            flash("Product saved successfully.", "success")
            return redirect(url_for("products"))
        except (ValueError, ArithmeticError, KeyError):
            flash("Check all fields. SKU must be unique and values cannot be negative.", "error")
    return render_template("product_form.html", active="products", p=p)

@app.route("/products/<int:pid>/delete", methods=["POST"])
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    if SaleItem.query.filter_by(product_id=p.id).first():
        flash("This product appears in sales history. Set stock to zero instead.", "error")
    else:
        db.session.delete(p); db.session.commit(); flash("Product deleted.", "success")
    return redirect(url_for("products"))

@app.route("/billing")
def billing():
    return render_template("billing.html", active="billing", products=Product.query.filter(Product.stock > 0).order_by(Product.name).all())

@app.route("/billing/checkout", methods=["POST"])
def checkout():
    data = request.get_json(silent=True) or {}
    if not data.get("items"): return jsonify(ok=False, error="Add at least one product first."), 400
    try:
        rate = Decimal(str(data.get("tax_rate", 0)))
        if rate < 0 or rate > 100: raise ValueError("Tax must be between 0 and 100.")
        prepared, subtotal = [], Decimal("0.00")
        for line in data["items"]:
            p = Product.query.get(int(line["id"]))
            qty = int(line["quantity"])
            if not p or qty < 1 or p.stock < qty: raise ValueError("Not enough stock for a selected product.")
            amount = (Decimal(p.price) * qty).quantize(Decimal("0.01"))
            prepared.append((p, qty, Decimal(p.price), amount)); subtotal += amount
        tax = (subtotal * rate / 100).quantize(Decimal("0.01"))
        sale = Sale(invoice="CS-" + datetime.now().strftime("%y%m%d%H%M%S") + f"-{Sale.query.count()+1:03}",
                    customer=(data.get("customer") or "Walk-in Customer").strip()[:120],
                    phone=(data.get("phone") or "").strip()[:30], subtotal=subtotal, tax_rate=rate, tax=tax, total=subtotal+tax)
        db.session.add(sale); db.session.flush()
        for p, qty, price, amount in prepared:
            p.stock -= qty
            db.session.add(SaleItem(sale_id=sale.id, product_id=p.id, name=p.name, sku=p.sku, qty=qty, price=price, amount=amount))
        db.session.commit()
        return jsonify(ok=True, redirect=url_for("invoice", sid=sale.id))
    except (ValueError, KeyError, TypeError, ArithmeticError) as e:
        db.session.rollback()
        return jsonify(ok=False, error=str(e) or "Please check the bill."), 400

@app.route("/sales")
def sales():
    return render_template("sales.html", active="sales", sales=Sale.query.order_by(Sale.created_at.desc()).all())

@app.route("/invoice/<int:sid>")
def invoice(sid):
    return render_template("invoice.html", active="sales", sale=Sale.query.get_or_404(sid))

@app.route("/health")
def health(): return {"status": "ok"}

def seed():
    if Product.query.count() == 0 and os.getenv("SEED_DEMO_DATA", "true").lower() == "true":
        db.session.add_all([
            Product(name="Wireless Mouse",sku="ACC-001",category="Accessories",price=599,cost=350,stock=42,threshold=8),
            Product(name="Mechanical Keyboard",sku="ACC-002",category="Accessories",price=2499,cost=1700,stock=18,threshold=5),
            Product(name="USB-C Hub",sku="ELE-001",category="Electronics",price=1899,cost=1200,stock=4,threshold=6),
            Product(name="Laptop Stand",sku="OFF-001",category="Office",price=999,cost=600,stock=23,threshold=5),
            Product(name="HDMI Cable",sku="CAB-001",category="Cables",price=399,cost=180,stock=3,threshold=10),
            Product(name="HD Webcam",sku="ELE-002",category="Electronics",price=1799,cost=1150,stock=12,threshold=4)])
        db.session.commit()
with app.app_context():
    db.create_all(); seed()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "true").lower() == "true")
