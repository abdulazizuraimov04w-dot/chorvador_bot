import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
from database.connection import execute_query, fetch_row, fetch_rows, fetch_val, get_pool
from utils.logger import logger

async def create_tables():
    """Creates database tables if they do not exist and populates initial data."""
    logger.info("Creating database tables if not exist...")
    
    # 1. branches table
    await execute_query("""
        CREATE TABLE IF NOT EXISTS branches (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # 2. users table
    await execute_query("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            phone_number VARCHAR(20) UNIQUE NOT NULL,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # 3. products table
    # ✅ YaNGI: image_url maydoni qo'shildi
    await execute_query("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL UNIQUE,
            price NUMERIC(12, 2) NOT NULL,
            image_url TEXT DEFAULT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # ✅ Agar jadval avval yaratilgan bo'lsa, image_url ustunini qo'shish (migration)
    await execute_query("""
        ALTER TABLE products ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT NULL;
    """)
    
    # 4. orders table
    await execute_query("""
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES users(id) ON DELETE CASCADE,
            status VARCHAR(50) DEFAULT 'pending',
            total_price NUMERIC(12, 2) DEFAULT 0,
            delivery_date DATE DEFAULT CURRENT_DATE,
            delivery_time_start VARCHAR(10) DEFAULT '06:30',
            delivery_time_end VARCHAR(10) DEFAULT '07:30',
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # 5. order_items table
    await execute_query("""
        CREATE TABLE IF NOT EXISTS order_items (
            id SERIAL PRIMARY KEY,
            order_id INT REFERENCES orders(id) ON DELETE CASCADE,
            product_id INT REFERENCES products(id) ON DELETE RESTRICT,
            quantity DOUBLE PRECISION NOT NULL,
            price_at_purchase NUMERIC(12, 2) NOT NULL
        );
    """)

    # 6. settings table
    await execute_query("""
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(100) PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # Default sozlamalar
    default_settings = {
        'reminder_hour':   '6',
        'reminder_minute': '0',
        'reminder_text':   "☀️ Xayrli tong!\n\nBugun nonushtaga nima buyurtma qilasiz? 🥛🧀🍞\nQuyidagi mahsulotlardan birini tanlab buyurtma berishingiz mumkin:",
        'reminder_photo':  '',
        'report_hour':     '6',
        'report_minute':   '0',
    }
    for k, v in default_settings.items():
        await execute_query(
            "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING;",
            k, v
        )

    logger.info("Tables checked/created successfully.")
    
    # Insert default branch if empty
    branches_count = await fetch_val("SELECT COUNT(*) FROM branches;")
    if branches_count == 0:
        await execute_query("INSERT INTO branches (name) VALUES ('Asosiy filial');")
        logger.info("Default branch 'Asosiy filial' inserted.")
        
    # Insert default products if empty
    products_count = await fetch_val("SELECT COUNT(*) FROM products;")
    if products_count == 0:
        default_products = [
            ("Qatiq",  Decimal("7000.00")),
            ("Qaymoq", Decimal("20000.00")),
            ("Tvorog", Decimal("8500.00")),
            ("Malako", Decimal("12000.00"))
        ]
        for name, price in default_products:
            await execute_query(
                "INSERT INTO products (name, price) VALUES ($1, $2) ON CONFLICT (name) DO NOTHING;",
                name, price
            )
        logger.info("Default products inserted.")

# --- USER METHODS ---

async def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    row = await fetch_row("SELECT * FROM users WHERE telegram_id = $1;", telegram_id)
    return dict(row) if row else None

async def get_user_by_phone_number(phone_number: str) -> Optional[Dict[str, Any]]:
    row = await fetch_row("SELECT * FROM users WHERE phone_number = $1;", phone_number)
    return dict(row) if row else None

async def create_user(telegram_id: int, full_name: str, phone_number: str,
                      latitude: float, longitude: float, branch_id: int = 1,
                      is_admin: bool = False) -> Dict[str, Any]:
    row = await fetch_row(
        """
        INSERT INTO users (telegram_id, full_name, phone_number, latitude, longitude, branch_id, is_admin)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *;
        """,
        telegram_id, full_name, phone_number, latitude, longitude, branch_id, is_admin
    )
    return dict(row)

async def get_all_users() -> List[Dict[str, Any]]:
    rows = await fetch_rows("SELECT u.*, b.name as branch_name FROM users u LEFT JOIN branches b ON u.branch_id = b.id ORDER BY u.created_at DESC;")
    return [dict(r) for r in rows]

async def update_user_admin_status(telegram_id: int, is_admin: bool):
    await execute_query("UPDATE users SET is_admin = $1 WHERE telegram_id = $2;", is_admin, telegram_id)

# --- PRODUCT METHODS ---

async def get_active_products() -> List[Dict[str, Any]]:
    rows = await fetch_rows("SELECT * FROM products WHERE is_active = TRUE ORDER BY name ASC;")
    return [dict(r) for r in rows]

async def get_all_products() -> List[Dict[str, Any]]:
    rows = await fetch_rows("SELECT * FROM products ORDER BY name ASC;")
    return [dict(r) for r in rows]

async def get_product_by_id(product_id: int) -> Optional[Dict[str, Any]]:
    row = await fetch_row("SELECT * FROM products WHERE id = $1;", product_id)
    return dict(row) if row else None

async def update_product_price(product_id: int, new_price: Decimal):
    await execute_query("UPDATE products SET price = $1 WHERE id = $2;", new_price, product_id)

async def add_product(name: str, price: Decimal, image_url: str = None) -> Dict[str, Any]:
    """✅ YaNGI: image_url parametri qo'shildi"""
    row = await fetch_row(
        "INSERT INTO products (name, price, image_url) VALUES ($1, $2, $3) RETURNING *;",
        name, price, image_url
    )
    return dict(row)

async def set_product_active_status(product_id: int, is_active: bool):
    await execute_query("UPDATE products SET is_active = $1 WHERE id = $2;", is_active, product_id)

# ✅ YaNGI: Mahsulot rasmini yangilash
async def update_product_image(product_id: int, image_url: str) -> Optional[Dict[str, Any]]:
    """Admin tomonidan mahsulot rasmini yangilash."""
    row = await fetch_row(
        "UPDATE products SET image_url = $1 WHERE id = $2 RETURNING *;",
        image_url, product_id
    )
    return dict(row) if row else None

# ✅ YaNGI: Mahsulotni to'liq yangilash (nom, narx, rasm)
async def update_product(product_id: int, name: str = None, price: Decimal = None,
                         image_url: str = None) -> Optional[Dict[str, Any]]:
    """Admin tomonidan mahsulot ma'lumotlarini yangilash."""
    fields = []
    values = []
    idx = 1
    if name is not None:
        fields.append(f"name = ${idx}"); values.append(name); idx += 1
    if price is not None:
        fields.append(f"price = ${idx}"); values.append(price); idx += 1
    if image_url is not None:
        fields.append(f"image_url = ${idx}"); values.append(image_url); idx += 1
    if not fields:
        return await get_product_by_id(product_id)
    values.append(product_id)
    row = await fetch_row(
        f"UPDATE products SET {', '.join(fields)} WHERE id = ${idx} RETURNING *;",
        *values
    )
    return dict(row) if row else None

# --- ORDER METHODS ---

async def create_order(telegram_id: int, cart_items: List[Dict[str, Any]], total_price: Decimal,
                       delivery_date: datetime.date = None, delivery_time_start: str = '06:30',
                       delivery_time_end: str = '07:30') -> int:
    if delivery_date is None:
        delivery_date = datetime.date.today() + datetime.timedelta(days=1)
        
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            user_id = await conn.fetchval("SELECT id FROM users WHERE telegram_id = $1;", telegram_id)
            if not user_id:
                raise ValueError(f"User with telegram ID {telegram_id} not found in database.")
                
            order_id = await conn.fetchval(
                """
                INSERT INTO orders (user_id, status, total_price, delivery_date, delivery_time_start, delivery_time_end)
                VALUES ($1, 'confirmed', $2, $3, $4, $5)
                RETURNING id;
                """,
                user_id, total_price, delivery_date, delivery_time_start, delivery_time_end
            )
            
            for item in cart_items:
                await conn.execute(
                    """
                    INSERT INTO order_items (order_id, product_id, quantity, price_at_purchase)
                    VALUES ($1, $2, $3, $4);
                    """,
                    order_id, item['product_id'], item['quantity'], item['price']
                )
            
            return order_id

async def get_user_orders(telegram_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    query = """
        SELECT o.id as order_id, o.status, o.total_price, o.delivery_date, o.delivery_time_start, 
               o.delivery_time_end, o.created_at,
               array_to_json(array_agg(json_build_object(
                   'product_name', p.name,
                   'quantity', oi.quantity,
                   'price', oi.price_at_purchase
               ))) as items
        FROM orders o
        JOIN users u ON o.user_id = u.id
        LEFT JOIN order_items oi ON o.id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE u.telegram_id = $1
        GROUP BY o.id
        ORDER BY o.created_at DESC
        LIMIT $2;
    """
    rows = await fetch_rows(query, telegram_id, limit)
    result = []
    for r in rows:
        order_dict = dict(r)
        import json
        if isinstance(order_dict['items'], str):
            order_dict['items'] = json.loads(order_dict['items'])
        result.append(order_dict)
    return result

async def get_all_orders(limit: int = 50) -> List[Dict[str, Any]]:
    query = """
        SELECT o.id as order_id, o.status, o.total_price, o.delivery_date, o.delivery_time_start, 
               o.delivery_time_end, o.created_at, u.full_name, u.phone_number, u.telegram_id,
               u.latitude, u.longitude,
               array_to_json(array_agg(json_build_object(
                   'product_name', p.name,
                   'quantity', oi.quantity,
                   'price', oi.price_at_purchase
               ))) as items
        FROM orders o
        JOIN users u ON o.user_id = u.id
        LEFT JOIN order_items oi ON o.id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.id
        GROUP BY o.id, u.id
        ORDER BY o.created_at DESC
        LIMIT $1;
    """
    rows = await fetch_rows(query, limit)
    result = []
    for r in rows:
        order_dict = dict(r)
        import json
        if isinstance(order_dict['items'], str):
            order_dict['items'] = json.loads(order_dict['items'])
        result.append(order_dict)
    return result

async def update_order_status(order_id: int, status: str):
    await execute_query("UPDATE orders SET status = $1 WHERE id = $2;", status, order_id)

# --- REPORT METHODS ---

async def get_production_report(date: datetime.date) -> List[Dict[str, Any]]:
    query = """
        SELECT p.name as product_name, SUM(oi.quantity) as total_quantity
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.delivery_date = $1 AND o.status IN ('confirmed', 'completed')
        GROUP BY p.name
        ORDER BY p.name ASC;
    """
    rows = await fetch_rows(query, date)
    return [dict(r) for r in rows]

async def get_daily_sales_report(date: datetime.date) -> Dict[str, Any]:
    query_sales = """
        SELECT COALESCE(SUM(total_price), 0) as revenue, COUNT(*) as order_count
        FROM orders
        WHERE delivery_date = $1 AND status IN ('confirmed', 'completed');
    """
    row = await fetch_row(query_sales, date)
    
    query_items = """
        SELECT p.name as product_name, SUM(oi.quantity) as total_quantity, SUM(oi.quantity * oi.price_at_purchase) as total_revenue
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.delivery_date = $1 AND o.status IN ('confirmed', 'completed')
        GROUP BY p.name
        ORDER BY total_revenue DESC;
    """
    rows_items = await fetch_rows(query_items, date)
    
    return {
        "date": date,
        "revenue": row["revenue"] if row else Decimal(0),
        "order_count": row["order_count"] if row else 0,
        "items": [dict(r) for r in rows_items]
    }

async def get_undelivered_orders() -> List[Dict[str, Any]]:
    query = """
        SELECT o.id as order_id, o.status, o.total_price, o.delivery_date, o.delivery_time_start, 
               o.delivery_time_end, o.created_at, u.full_name, u.phone_number, u.telegram_id,
               u.latitude, u.longitude,
               array_to_json(array_agg(json_build_object(
                   'product_name', p.name,
                   'quantity', oi.quantity,
                   'price', oi.price_at_purchase
               ))) as items
        FROM orders o
        JOIN users u ON o.user_id = u.id
        LEFT JOIN order_items oi ON o.id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE o.status IN ('pending', 'confirmed')
        GROUP BY o.id, u.id
        ORDER BY o.delivery_date ASC, o.created_at ASC;
    """
    rows = await fetch_rows(query)
    result = []
    for r in rows:
        row_dict = dict(r)
        if row_dict.get('delivery_date'):
            row_dict['delivery_date'] = row_dict['delivery_date'].strftime("%Y-%m-%d")
        if row_dict.get('created_at'):
            row_dict['created_at'] = row_dict['created_at'].strftime("%Y-%m-%d %H:%M")
        if row_dict.get('total_price'):
            row_dict['total_price'] = float(row_dict['total_price'])
        result.append(row_dict)
    return result

async def get_setting(key: str, default: str = None) -> Optional[str]:
    row = await fetch_row("SELECT value FROM settings WHERE key = $1;", key)
    return row['value'] if row else default

async def get_all_settings() -> Dict[str, str]:
    rows = await fetch_rows("SELECT key, value FROM settings;")
    return {r['key']: r['value'] for r in rows}

async def set_setting(key: str, value: str):
    await execute_query(
        """INSERT INTO settings (key, value, updated_at) VALUES ($1, $2, NOW())
           ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = NOW();""",
        key, value
    )

async def get_dashboard_stats() -> Dict[str, Any]:
    total_customers = await fetch_val("SELECT COUNT(*) FROM users;")
    total_orders    = await fetch_val("SELECT COUNT(*) FROM orders;")
    total_revenue   = await fetch_val("SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status IN ('confirmed', 'completed');")
    
    chart_query = """
        SELECT 
            d.date::date as sale_date,
            COALESCE(SUM(o.total_price), 0) as daily_revenue,
            COUNT(o.id) as daily_orders
        FROM generate_series(CURRENT_DATE - INTERVAL '6 days', CURRENT_DATE, '1 day'::interval) d(date)
        LEFT JOIN orders o ON o.delivery_date = d.date::date AND o.status IN ('confirmed', 'completed')
        GROUP BY d.date
        ORDER BY d.date ASC;
    """
    chart_rows = await fetch_rows(chart_query)
    chart_data = []
    for r in chart_rows:
        chart_data.append({
            "date": r["sale_date"].strftime("%d.%m"),
            "revenue": float(r["daily_revenue"]),
            "orders": r["daily_orders"]
        })
        
    monthly_query = """
        SELECT 
            TO_CHAR(d.month, 'YYYY-MM') as month_label,
            COALESCE(SUM(o.total_price), 0) as revenue,
            COUNT(o.id) as order_count,
            COALESCE(SUM(oi_agg.total_qty), 0) as total_qty
        FROM generate_series(
            DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '5 months',
            DATE_TRUNC('month', CURRENT_DATE),
            '1 month'::interval
        ) d(month)
        LEFT JOIN orders o ON DATE_TRUNC('month', o.delivery_date) = d.month
            AND o.status IN ('confirmed', 'completed')
        LEFT JOIN (
            SELECT order_id, SUM(quantity) as total_qty FROM order_items GROUP BY order_id
        ) oi_agg ON oi_agg.order_id = o.id
        GROUP BY d.month
        ORDER BY d.month ASC;
    """
    monthly_rows = await fetch_rows(monthly_query)
    monthly_data = []
    for r in monthly_rows:
        monthly_data.append({
            "month": r["month_label"],
            "revenue": float(r["revenue"]),
            "orders": r["order_count"],
            "qty": float(r["total_qty"])
        })

    today = datetime.date.today()
    today_row = await fetch_row(
        "SELECT COALESCE(SUM(total_price),0) as rev, COUNT(*) as cnt FROM orders WHERE delivery_date=$1 AND status IN ('confirmed','completed');",
        today
    )
    
    top_products_query = """
        SELECT p.name, SUM(oi.quantity) as total_qty, SUM(oi.quantity * oi.price_at_purchase) as total_rev
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.delivery_date >= CURRENT_DATE - INTERVAL '30 days'
          AND o.status IN ('confirmed', 'completed')
        GROUP BY p.name ORDER BY total_qty DESC;
    """
    top_rows = await fetch_rows(top_products_query)
    top_products = [{"name": r["name"], "qty": float(r["total_qty"]), "rev": float(r["total_rev"])} for r in top_rows]

    forecast_query = """
        SELECT p.name,
            ROUND(SUM(oi.quantity)::numeric / GREATEST(COUNT(DISTINCT o.delivery_date), 1), 1) as avg_daily
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        JOIN orders o ON oi.order_id = o.id
        WHERE o.delivery_date >= CURRENT_DATE - INTERVAL '30 days'
          AND o.status IN ('confirmed', 'completed')
        GROUP BY p.name ORDER BY avg_daily DESC;
    """
    forecast_rows = await fetch_rows(forecast_query)
    forecast = [{"name": r["name"], "avg_daily": float(r["avg_daily"]), "monthly": float(r["avg_daily"]) * 30} for r in forecast_rows]

    return {
        "total_customers": total_customers,
        "total_orders":    total_orders,
        "total_revenue":   float(total_revenue),
        "today_revenue":   float(today_row["rev"]) if today_row else 0,
        "today_orders":    today_row["cnt"] if today_row else 0,
        "chart_data":      chart_data,
        "monthly_data":    monthly_data,
        "top_products":    top_products,
        "forecast":        forecast
    }

async def get_dashboard_orders(date_filter: str = None) -> List[Dict[str, Any]]:
    if date_filter is None:
        date_filter = datetime.date.today().isoformat()
    query = """
        SELECT o.id as order_id, o.status, o.total_price, o.delivery_date, o.delivery_time_start, 
               o.delivery_time_end, o.created_at, u.full_name, u.phone_number, u.telegram_id,
               u.latitude, u.longitude,
               array_to_json(array_agg(json_build_object(
                   'product_name', p.name,
                   'quantity', oi.quantity,
                   'price', oi.price_at_purchase
               ))) as items
        FROM orders o
        JOIN users u ON o.user_id = u.id
        LEFT JOIN order_items oi ON o.id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE o.delivery_date = $1
        GROUP BY o.id, u.id
        ORDER BY 
            CASE 
                WHEN o.status = 'pending'   THEN 1
                WHEN o.status = 'confirmed' THEN 2
                WHEN o.status = 'completed' THEN 3
                ELSE 4
            END ASC,
            o.created_at DESC;
    """
    rows = await fetch_rows(query, date_filter)
    result = []
    for r in rows:
        order_dict = dict(r)
        import json
        if isinstance(order_dict['items'], str):
            order_dict['items'] = json.loads(order_dict['items'])
        order_dict['delivery_date'] = order_dict['delivery_date'].strftime("%Y-%m-%d")
        order_dict['created_at']    = order_dict['created_at'].strftime("%H:%M | %d.%m.%Y")
        order_dict['total_price']   = float(order_dict['total_price'])
        result.append(order_dict)
    return result
