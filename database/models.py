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
    
    # 2.5 categories table (Supermarket Categories)
    await execute_query("""
        CREATE TABLE IF NOT EXISTS categories (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL UNIQUE,
            icon VARCHAR(50) DEFAULT '🛍️',
            sort_order INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # 3. products table
    await execute_query("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL UNIQUE,
            price NUMERIC(12, 2) NOT NULL,
            image_url TEXT DEFAULT NULL,
            category_id INT REFERENCES categories(id) ON DELETE SET NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # Migration for existing tables
    await execute_query("""
        ALTER TABLE products ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT NULL;
        ALTER TABLE products ADD COLUMN IF NOT EXISTS category_id INT REFERENCES categories(id) ON DELETE SET NULL;
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
        'reminder_hour':        '6',
        'reminder_minute':      '0',
        'reminder_text':        "🍽️ Assalomu alaykum!\n\nBugun nima yemoqchi bo'lasiz?\nTaomim orqali qulay va tez buyurtma bering!",
        'reminder_photo':       '',
        'report_hour':          '6',
        'report_minute':        '0',
        'min_order_amount':     '0',
        'loyalty_target':       '10',
        'delivery_fee_per_km':  '2000',
        'delivery_min_fee':     '3000',
    }
    for k, v in default_settings.items():
        await execute_query(
            "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING;",
            k, v
        )
    # 7. couriers table
    await execute_query("""
        CREATE TABLE IF NOT EXISTS couriers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone_number VARCHAR(20) NOT NULL,
            telegram_id BIGINT UNIQUE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # 8. mfy table
    await execute_query("""
        CREATE TABLE IF NOT EXISTS mfy (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL UNIQUE,
            courier_id INT REFERENCES couriers(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # 9. scheduled_notifications table
    await execute_query("""
        CREATE TABLE IF NOT EXISTS scheduled_notifications (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            text TEXT NOT NULL,
            media_url TEXT,
            media_type VARCHAR(50),
            send_hour INT NOT NULL,
            send_minute INT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            last_sent_date DATE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # 10. restaurants table (Taomim hamkor oshxonalar)
    await execute_query("""
        CREATE TABLE IF NOT EXISTS restaurants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(20),
            address TEXT,
            latitude DOUBLE PRECISION NOT NULL DEFAULT 41.2995,
            longitude DOUBLE PRECISION NOT NULL DEFAULT 69.2401,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    # Migrations
    await execute_query("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS mfy_id INT REFERENCES mfy(id) ON DELETE SET NULL;
    """)
    await execute_query("""
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS courier_id INT REFERENCES couriers(id) ON DELETE SET NULL;
    """)
    await execute_query("""
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS address_text TEXT;
    """)
    await execute_query("""
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_fee NUMERIC(10,2) DEFAULT 0;
    """)
    await execute_query("""
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS distance_km NUMERIC(6,2) DEFAULT 0;
    """)
    await execute_query("""
        ALTER TABLE orders ADD COLUMN IF NOT EXISTS restaurant_id INT REFERENCES restaurants(id) ON DELETE SET NULL;
    """)
    await execute_query("""
        ALTER TABLE products ADD COLUMN IF NOT EXISTS restaurant_id INT REFERENCES restaurants(id) ON DELETE SET NULL;
    """)

    logger.info("Tables checked/created successfully.")

    # Insert default categories if empty
    categories_count = await fetch_val("SELECT COUNT(*) FROM categories;")
    if categories_count == 0:
        default_cats = [
            ("Sho'rvalar",                   "🍲", 1),
            ("Guruch taomlari",               "🍚", 2),
            ("Xamirli taomlar",               "🥟", 3),
            ("Quyma taomlar",                 "🍜", 4),
            ("Go'shtli taomlar",              "🥩", 5),
            ("Salatlar",                      "🥗", 6),
            ("Desertlar",                     "🍰", 7),
            ("Ichimliklar",                   "🥤", 8),
            ("Tushlik seti",                  "🍱", 9),
        ]
        for c_name, c_icon, c_order in default_cats:
            await execute_query(
                "INSERT INTO categories (name, icon, sort_order) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING;",
                c_name, c_icon, c_order
            )
        logger.info("Default Taomim food categories inserted.")

    # Insert default branch if empty
    branches_count = await fetch_val("SELECT COUNT(*) FROM branches;")
    if branches_count == 0:
        await execute_query("INSERT INTO branches (name) VALUES ('Asosiy filial');")
        logger.info("Default branch inserted.")

# --- USER METHODS ---

async def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    row = await fetch_row("""
        SELECT u.*, m.name as mfy_name 
        FROM users u 
        LEFT JOIN mfy m ON u.mfy_id = m.id 
        WHERE u.telegram_id = $1;
    """, telegram_id)
    return dict(row) if row else None

async def get_user_by_phone_number(phone_number: str) -> Optional[Dict[str, Any]]:
    row = await fetch_row("SELECT * FROM users WHERE phone_number = $1;", phone_number)
    return dict(row) if row else None

async def create_user(telegram_id: int, full_name: str, phone_number: str,
                      latitude: float, longitude: float, branch_id: int = 1,
                      is_admin: bool = False, mfy_id: int = None) -> Dict[str, Any]:
    row = await fetch_row(
        """
        INSERT INTO users (telegram_id, full_name, phone_number, latitude, longitude, branch_id, is_admin, mfy_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *;
        """,
        telegram_id, full_name, phone_number, latitude, longitude, branch_id, is_admin, mfy_id
    )
    return dict(row)

async def get_all_users() -> List[Dict[str, Any]]:
    rows = await fetch_rows("""
        SELECT u.*, b.name as branch_name, m.name as mfy_name 
        FROM users u 
        LEFT JOIN branches b ON u.branch_id = b.id 
        LEFT JOIN mfy m ON u.mfy_id = m.id
        ORDER BY u.created_at DESC;
    """)
    return [dict(r) for r in rows]

async def update_user_admin_status(telegram_id: int, is_admin: bool):
    await execute_query("UPDATE users SET is_admin = $1 WHERE telegram_id = $2;", is_admin, telegram_id)

async def get_customers_analytics() -> List[Dict[str, Any]]:
    """Barcha mijozlar haqida to'liq analitik ma'lumotlar (buyurtmalar, summa, segment va boshqalar)."""
    rows = await fetch_rows("""
        SELECT
            u.id,
            u.telegram_id,
            u.full_name,
            u.phone_number,
            u.latitude,
            u.longitude,
            u.is_admin,
            u.created_at,

            -- Buyurtmalar statistikasi
            COUNT(o.id)                                         AS total_orders,
            COALESCE(SUM(o.total_price), 0)                    AS total_spent,
            COALESCE(AVG(o.total_price), 0)                    AS avg_order_value,
            MAX(o.created_at)                                  AS last_order_date,
            MIN(o.created_at)                                  AS first_order_date,

            -- Oxirgi buyurtmadan necha kun o'tdi
            COALESCE(
                EXTRACT(DAY FROM NOW() - MAX(o.created_at))::int,
                9999
            )                                                  AS days_since_last_order,

            -- Eng sevimli mahsulot (eng ko'p buyurtma qilingan)
            (
                SELECT p2.name
                FROM order_items oi2
                JOIN products p2 ON oi2.product_id = p2.id
                JOIN orders o2 ON oi2.order_id = o2.id
                WHERE o2.user_id = u.id
                  AND o2.status IN ('confirmed','completed')
                GROUP BY p2.name
                ORDER BY SUM(oi2.quantity) DESC
                LIMIT 1
            )                                                  AS favorite_product,

            -- 70k+ so'mlik mos buyurtmalar soni (loyalty)
            COUNT(o.id) FILTER (WHERE o.total_price >= 70000)   AS qualifying_orders,

            -- Mijoz segmenti
            CASE
                WHEN COUNT(o.id) = 0 THEN 'new'
                WHEN COALESCE(SUM(o.total_price), 0) >= 500000 THEN 'vip'
                WHEN COALESCE(EXTRACT(DAY FROM NOW() - MAX(o.created_at))::int, 9999) <= 30 THEN 'active'
                ELSE 'sleeping'
            END                                                AS segment

        FROM users u
        LEFT JOIN orders o
            ON o.user_id = u.id
            AND o.status IN ('confirmed','completed','pending')
        GROUP BY u.id
        ORDER BY total_spent DESC, u.created_at DESC;
    """)
    result = []
    for r in rows:
        d = dict(r)
        if d.get('created_at'):
            d['created_at'] = d['created_at'].strftime("%Y-%m-%d %H:%M")
        if d.get('last_order_date'):
            d['last_order_date'] = d['last_order_date'].strftime("%Y-%m-%d %H:%M")
        if d.get('first_order_date'):
            d['first_order_date'] = d['first_order_date'].strftime("%Y-%m-%d %H:%M")
        d['total_spent']     = float(d['total_spent'])
        d['avg_order_value'] = float(d['avg_order_value'])
        d['total_orders']    = int(d['total_orders'])
        d['days_since_last_order'] = int(d['days_since_last_order'])
        q_orders = int(d.get('qualifying_orders') or 0)
        d['qualifying_orders'] = q_orders
        d['loyalty_step']      = q_orders % 10 if q_orders % 10 != 0 else (10 if q_orders > 0 else 0)
        d['gifts_earned']      = q_orders // 10
        result.append(d)
    return result

async def get_customer_detail(user_id: int) -> Optional[Dict[str, Any]]:
    """Alohida mijoz profili + barcha buyurtmalar tarixi."""
    user_row = await fetch_row("""
        SELECT
            u.id, u.telegram_id, u.full_name, u.phone_number,
            u.latitude, u.longitude, u.is_admin, u.created_at,
            COUNT(o.id)                         AS total_orders,
            COALESCE(SUM(o.total_price), 0)    AS total_spent,
            COALESCE(AVG(o.total_price), 0)    AS avg_order_value,
            MAX(o.created_at)                   AS last_order_date,
            COALESCE(EXTRACT(DAY FROM NOW() - MAX(o.created_at))::int, 9999) AS days_since_last_order,
            (
                SELECT p2.name
                FROM order_items oi2
                JOIN products p2 ON oi2.product_id = p2.id
                JOIN orders o2 ON oi2.order_id = o2.id
                WHERE o2.user_id = u.id AND o2.status IN ('confirmed','completed')
                GROUP BY p2.name ORDER BY SUM(oi2.quantity) DESC LIMIT 1
            ) AS favorite_product,
            CASE
                WHEN COUNT(o.id) = 0 THEN 'new'
                WHEN COALESCE(SUM(o.total_price), 0) >= 500000 THEN 'vip'
                WHEN COALESCE(EXTRACT(DAY FROM NOW() - MAX(o.created_at))::int, 9999) <= 30 THEN 'active'
                ELSE 'sleeping'
            END AS segment
        FROM users u
        LEFT JOIN orders o ON o.user_id = u.id AND o.status IN ('confirmed','completed')
        WHERE u.id = $1
        GROUP BY u.id;
    """, user_id)

    if not user_row:
        return None

    user = dict(user_row)
    if user.get('created_at'):
        user['created_at'] = user['created_at'].strftime("%Y-%m-%d %H:%M")
    if user.get('last_order_date'):
        user['last_order_date'] = user['last_order_date'].strftime("%Y-%m-%d %H:%M")
    user['total_spent']     = float(user['total_spent'])
    user['avg_order_value'] = float(user['avg_order_value'])
    user['total_orders']    = int(user['total_orders'])
    user['days_since_last_order'] = int(user['days_since_last_order'])

    # Buyurtmalar tarixi
    orders_rows = await fetch_rows("""
        SELECT
            o.id AS order_id,
            o.status,
            o.total_price,
            o.delivery_date,
            o.created_at,
            o.delivery_time_start,
            o.delivery_time_end,
            array_to_json(array_agg(json_build_object(
                'product_name', p.name,
                'quantity',     oi.quantity,
                'price',        oi.price_at_purchase
            ))) AS items
        FROM orders o
        LEFT JOIN order_items oi ON oi.order_id = o.id
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE o.user_id = $1
        GROUP BY o.id
        ORDER BY o.created_at DESC
        LIMIT 50;
    """, user_id)

    import json
    orders = []
    for r in orders_rows:
        od = dict(r)
        od['total_price']   = float(od['total_price'])
        od['delivery_date'] = od['delivery_date'].strftime("%d.%m.%Y") if od.get('delivery_date') else ''
        od['created_at']    = od['created_at'].strftime("%d.%m.%Y %H:%M") if od.get('created_at') else ''
        if isinstance(od.get('items'), str):
            od['items'] = json.loads(od['items'])
        orders.append(od)

    user['orders'] = orders
    return user

async def get_min_order_amount() -> float:
    """Minimal buyurtma summasi (0 = chek yo'q)."""
    val = await fetch_val("SELECT value FROM settings WHERE key = 'min_order_amount';")
    try:
        return float(val) if val else 0.0
    except (ValueError, TypeError):
        return 0.0

async def get_loyalty_target() -> int:
    """Sovg'a marrasi (default 10 buyurtma)."""
    val = await fetch_val("SELECT value FROM settings WHERE key = 'loyalty_target';")
    try:
        return int(val) if val else 10
    except (ValueError, TypeError):
        return 10

# --- RESTAURANT METHODS ---
import math

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Ikki koordinata orasidagi masofani km da hisoblaydi (Haversine formulasi)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))

async def get_delivery_fee_settings() -> Dict[str, float]:
    """Yetkazib berish tariflari sozlamalarini olish."""
    rows = await fetch_rows("SELECT key, value FROM settings WHERE key IN ('delivery_fee_per_km', 'delivery_min_fee');")
    result = {'delivery_fee_per_km': 2000.0, 'delivery_min_fee': 3000.0}
    for r in rows:
        try:
            result[r['key']] = float(r['value'])
        except (ValueError, TypeError):
            pass
    return result

async def calculate_delivery_fee(user_lat: float, user_lon: float, restaurant_ids: List[int]) -> Dict[str, Any]:
    """Eng uzoq oshxonaga qarab yetkazib berish narxini hisoblaydi."""
    if not restaurant_ids:
        return {'fee': 0, 'distance_km': 0, 'restaurant_id': None}

    settings = await get_delivery_fee_settings()
    fee_per_km = settings['delivery_fee_per_km']
    min_fee    = settings['delivery_min_fee']

    max_distance = 0.0
    farthest_id  = restaurant_ids[0]

    for r_id in restaurant_ids:
        restaurant = await get_restaurant_by_id(r_id)
        if not restaurant:
            continue
        dist = haversine_km(user_lat, user_lon, restaurant['latitude'], restaurant['longitude'])
        if dist > max_distance:
            max_distance = dist
            farthest_id  = r_id

    raw_fee = max(min_fee, max_distance * fee_per_km)
    rounded_fee = round(raw_fee / 500) * 500  # 500 so'mga yaxlitlash

    return {
        'fee':           rounded_fee,
        'distance_km':   round(max_distance, 2),
        'restaurant_id': farthest_id
    }

async def get_all_restaurants() -> List[Dict[str, Any]]:
    rows = await fetch_rows("""
        SELECT r.*, 
               COUNT(p.id) FILTER (WHERE p.is_active) AS active_products_count
        FROM restaurants r
        LEFT JOIN products p ON p.restaurant_id = r.id
        GROUP BY r.id
        ORDER BY r.name;
    """)
    return [dict(r) for r in rows]

async def get_active_restaurants() -> List[Dict[str, Any]]:
    rows = await fetch_rows("SELECT * FROM restaurants WHERE is_active = TRUE ORDER BY name;")
    return [dict(r) for r in rows]

async def get_restaurant_by_id(restaurant_id: int) -> Optional[Dict[str, Any]]:
    row = await fetch_row("SELECT * FROM restaurants WHERE id = $1;", restaurant_id)
    return dict(row) if row else None

async def create_restaurant(name: str, phone: str, address: str,
                            latitude: float, longitude: float) -> Dict[str, Any]:
    row = await fetch_row("""
        INSERT INTO restaurants (name, phone, address, latitude, longitude)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *;
    """, name, phone, address, latitude, longitude)
    return dict(row)

async def update_restaurant(restaurant_id: int, name: str, phone: str, address: str,
                            latitude: float, longitude: float, is_active: bool) -> Optional[Dict[str, Any]]:
    row = await fetch_row("""
        UPDATE restaurants
        SET name=$1, phone=$2, address=$3, latitude=$4, longitude=$5, is_active=$6
        WHERE id=$7
        RETURNING *;
    """, name, phone, address, latitude, longitude, is_active, restaurant_id)
    return dict(row) if row else None

async def delete_restaurant(restaurant_id: int) -> bool:
    await execute_query("DELETE FROM restaurants WHERE id = $1;", restaurant_id)
    return True

async def get_user_loyalty_info(telegram_id_or_user_id: int) -> Dict[str, Any]:
    """Mijozning 70k+ so'mlik buyurtmalari bo'yicha loyalty progress va visual bar matnini hisoblash."""
    min_amount = await get_min_order_amount()
    target     = await get_loyalty_target()

    # User_id yoki telegram_id orqali user topamiz
    user = await fetch_row("""
        SELECT id, telegram_id, full_name FROM users 
        WHERE id = $1 OR telegram_id = $1 LIMIT 1;
    """, telegram_id_or_user_id)

    if not user:
        return {
            "qualifying_orders": 0,
            "target": target,
            "current_step": 0,
            "remaining": target,
            "gifts_earned": 0,
            "is_gift_order": False,
            "min_amount": min_amount,
            "progress_bar": "⬜" * target,
            "text": f"🎁 Sovg'aga {target} ta buyurtma qoldi!\n[ {'⬜'*target} ] 0/{target}"
        }

    u_id = user['id']
    # Minimal summa va bajarilgan statusga ega buyurtmalar soni
    q_count = await fetch_val("""
        SELECT COUNT(id) FROM orders 
        WHERE user_id = $1 
          AND status IN ('confirmed', 'completed', 'pending')
          AND total_price >= $2;
    """, u_id, min_amount) or 0

    current_step = q_count % target
    remaining    = target - current_step if current_step != 0 else target
    gifts_earned = q_count // target

    # Agar q_count > 0 va q_count % target == 0 bo'lsa, demak oxirgi buyurtma yubiley sovg'ali bo'lgan
    is_gift_order = (q_count > 0 and current_step == 0)

    # Visual Emoji Progress Bar generator (masalan: 🟩🟩🟩🟩🟩🟩🟩⬜⬜⬜)
    filled_blocks = current_step if current_step > 0 else (target if is_gift_order else 0)
    empty_blocks  = target - filled_blocks

    # Progress bar belgilari: to'lgani 🟩, to'lmagani ⬜
    bar_str = "🟩" * filled_blocks + "⬜" * empty_blocks

    if is_gift_order:
        text = f"🎉 **TABRIKLAYMIZ!** Siz {target}-yubiley buyurtmangizdasiz!\n[ {bar_str} ] {target}/{target}\n🎁 **Sizga MAXSUS SOVG'A biriktirildi!**"
    elif remaining == 1:
        text = f"🔥 **JUDA YA QINS IZ!** Yana 1 ta buyurtma bersangiz SOVG'A olasiz!\n[ {bar_str} ] {current_step}/{target}"
    else:
        text = f"🎁 **Sovg'angizga {remaining} ta buyurtma qoldi!**\n[ {bar_str} ] {current_step}/{target}"

    return {
        "user_id": u_id,
        "qualifying_orders": q_count,
        "target": target,
        "current_step": current_step if not is_gift_order else target,
        "remaining": 0 if is_gift_order else remaining,
        "gifts_earned": gifts_earned,
        "is_gift_order": is_gift_order,
        "min_amount": min_amount,
        "progress_bar": bar_str,
        "text": text
    }

# --- CATEGORY METHODS ---

async def get_all_categories() -> List[Dict[str, Any]]:
    rows = await fetch_rows("SELECT * FROM categories ORDER BY sort_order ASC, name ASC;")
    return [dict(r) for r in rows]

async def create_category(name: str, icon: str = '🛍️', sort_order: int = 0) -> int:
    row = await fetch_row(
        "INSERT INTO categories (name, icon, sort_order) VALUES ($1, $2, $3) RETURNING id;",
        name, icon or '🛍️', sort_order
    )
    return row['id']

async def update_category(category_id: int, name: str, icon: str = '🛍️', sort_order: int = 0):
    await execute_query(
        "UPDATE categories SET name = $1, icon = $2, sort_order = $3 WHERE id = $4;",
        name, icon or '🛍️', sort_order, category_id
    )

async def delete_category(category_id: int):
    await execute_query("DELETE FROM categories WHERE id = $1;", category_id)

# --- PRODUCT METHODS ---

async def get_active_products() -> List[Dict[str, Any]]:
    rows = await fetch_rows("""
        SELECT p.*, c.name as category_name, c.icon as category_icon,
               r.name as restaurant_name
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN restaurants r ON p.restaurant_id = r.id
        WHERE p.is_active = TRUE 
        ORDER BY c.sort_order ASC, p.name ASC;
    """)
    return [dict(r) for r in rows]

async def get_all_products() -> List[Dict[str, Any]]:
    rows = await fetch_rows("""
        SELECT p.*, c.name as category_name, c.icon as category_icon,
               r.name as restaurant_name
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN restaurants r ON p.restaurant_id = r.id
        ORDER BY p.name ASC;
    """)
    return [dict(r) for r in rows]

async def get_product_by_id(product_id: int) -> Optional[Dict[str, Any]]:
    row = await fetch_row("SELECT * FROM products WHERE id = $1;", product_id)
    return dict(row) if row else None

async def update_product_price(product_id: int, new_price: Decimal):
    await execute_query("UPDATE products SET price = $1 WHERE id = $2;", new_price, product_id)

async def add_product(name: str, price: Decimal, image_url: str = None,
                      category_id: int = None, restaurant_id: int = None) -> Dict[str, Any]:
    row = await fetch_row(
        "INSERT INTO products (name, price, image_url, category_id, restaurant_id) VALUES ($1, $2, $3, $4, $5) RETURNING *;",
        name, price, image_url, category_id, restaurant_id
    )
    return dict(row)

async def set_product_active_status(product_id: int, is_active: bool):
    await execute_query("UPDATE products SET is_active = $1 WHERE id = $2;", is_active, product_id)

async def update_product_image(product_id: int, image_url: str) -> Optional[Dict[str, Any]]:
    row = await fetch_row(
        "UPDATE products SET image_url = $1 WHERE id = $2 RETURNING *;",
        image_url, product_id
    )
    return dict(row) if row else None

async def update_product(product_id: int, name: str = None, price: Decimal = None,
                         image_url: str = None, category_id: int = None,
                         restaurant_id: int = None) -> Optional[Dict[str, Any]]:
    fields = []
    values = []
    idx = 1
    if name is not None:
        fields.append(f"name = ${idx}"); values.append(name); idx += 1
    if price is not None:
        fields.append(f"price = ${idx}"); values.append(price); idx += 1
    if image_url is not None:
        fields.append(f"image_url = ${idx}"); values.append(image_url); idx += 1
    if category_id is not None:
        fields.append(f"category_id = ${idx}"); values.append(category_id); idx += 1
    if restaurant_id is not None:
        fields.append(f"restaurant_id = ${idx}"); values.append(restaurant_id); idx += 1

    if not fields:
        return await get_product_by_id(product_id)

    values.append(product_id)
    query = f"UPDATE products SET {', '.join(fields)} WHERE id = ${idx} RETURNING *;"
    row = await fetch_row(query, *values)
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
                
            # Get user's mfy_id to auto-assign courier
            mfy_id = await conn.fetchval("SELECT mfy_id FROM users WHERE id = $1;", user_id)
            courier_id = None
            if mfy_id:
                courier_id = await conn.fetchval("SELECT courier_id FROM mfy WHERE id = $1;", mfy_id)

            order_id = await conn.fetchval(
                """
                INSERT INTO orders (user_id, status, total_price, delivery_date, delivery_time_start, delivery_time_end, courier_id)
                VALUES ($1, 'confirmed', $2, $3, $4, $5, $6)
                RETURNING id;
                """,
                user_id, total_price, delivery_date, delivery_time_start, delivery_time_end, courier_id
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
               u.latitude, u.longitude, m.name as mfy_name, c.name as courier_name, c.phone_number as courier_phone,
               o.courier_id,
               array_to_json(array_agg(json_build_object(
                   'product_name', p.name,
                   'quantity', oi.quantity,
                   'price', oi.price_at_purchase
               ))) as items
        FROM orders o
        JOIN users u ON o.user_id = u.id
        LEFT JOIN mfy m ON u.mfy_id = m.id
        LEFT JOIN couriers c ON o.courier_id = c.id
        LEFT JOIN order_items oi ON o.id = oi.order_id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE o.delivery_date = $1
        GROUP BY o.id, u.id, m.name, c.name, c.phone_number
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

# ============================================================
# LOGISTICS (COURIERS & MFY) & SCHEDULED NOTIFICATIONS
# ============================================================

async def get_all_couriers() -> List[Dict[str, Any]]:
    rows = await fetch_rows("SELECT * FROM couriers ORDER BY name ASC;")
    return [dict(r) for r in rows]

async def get_courier_by_id(courier_id: int) -> Optional[Dict[str, Any]]:
    row = await fetch_row("SELECT * FROM couriers WHERE id = $1;", courier_id)
    return dict(row) if row else None

async def create_courier(name: str, phone_number: str, telegram_id: int = None) -> int:
    return await fetch_val(
        "INSERT INTO couriers (name, phone_number, telegram_id) VALUES ($1, $2, $3) RETURNING id;",
        name, phone_number, telegram_id
    )

async def update_courier(courier_id: int, name: str, phone_number: str, telegram_id: int = None, is_active: bool = True):
    await execute_query(
        "UPDATE couriers SET name = $1, phone_number = $2, telegram_id = $3, is_active = $4 WHERE id = $5;",
        name, phone_number, telegram_id, is_active, courier_id
    )

async def delete_courier(courier_id: int):
    await execute_query("DELETE FROM couriers WHERE id = $1;", courier_id)


async def get_all_mfy() -> List[Dict[str, Any]]:
    rows = await fetch_rows("""
        SELECT m.id, m.name, m.courier_id, c.name as courier_name 
        FROM mfy m 
        LEFT JOIN couriers c ON m.courier_id = c.id 
        ORDER BY m.name ASC;
    """)
    return [dict(r) for r in rows]

async def get_mfy_by_id(mfy_id: int) -> Optional[Dict[str, Any]]:
    row = await fetch_row("SELECT * FROM mfy WHERE id = $1;", mfy_id)
    return dict(row) if row else None

async def create_mfy(name: str, courier_id: int = None) -> int:
    return await fetch_val(
        "INSERT INTO mfy (name, courier_id) VALUES ($1, $2) RETURNING id;",
        name, courier_id
    )

async def update_mfy(mfy_id: int, name: str, courier_id: int = None):
    await execute_query(
        "UPDATE mfy SET name = $1, courier_id = $2 WHERE id = $3;",
        name, courier_id, mfy_id
    )

async def delete_mfy(mfy_id: int):
    await execute_query("DELETE FROM mfy WHERE id = $1;", mfy_id)


async def get_all_scheduled_notifications() -> List[Dict[str, Any]]:
    rows = await fetch_rows("SELECT * FROM scheduled_notifications ORDER BY send_hour ASC, send_minute ASC;")
    return [dict(r) for r in rows]

async def create_scheduled_notification(title: str, text: str, media_url: str = None, media_type: str = None, send_hour: int = 6, send_minute: int = 0) -> int:
    return await fetch_val(
        "INSERT INTO scheduled_notifications (title, text, media_url, media_type, send_hour, send_minute) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id;",
        title, text, media_url, media_type, send_hour, send_minute
    )

async def update_scheduled_notification(notif_id: int, title: str, text: str, media_url: str = None, media_type: str = None, send_hour: int = 6, send_minute: int = 0, is_active: bool = True):
    await execute_query(
        "UPDATE scheduled_notifications SET title = $1, text = $2, media_url = $3, media_type = $4, send_hour = $5, send_minute = $6, is_active = $7 WHERE id = $8;",
        title, text, media_url, media_type, send_hour, send_minute, is_active, notif_id
    )

async def delete_scheduled_notification(notif_id: int):
    await execute_query("DELETE FROM scheduled_notifications WHERE id = $1;", notif_id)

async def update_notification_last_sent(notif_id: int, last_sent_date: datetime.date):
    await execute_query(
        "UPDATE scheduled_notifications SET last_sent_date = $1 WHERE id = $2;",
        last_sent_date, notif_id
    )

async def update_order_courier(order_id: int, courier_id: int = None):
    await execute_query(
        "UPDATE orders SET courier_id = $1 WHERE id = $2;",
        courier_id, order_id
    )
