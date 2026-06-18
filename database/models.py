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
    await execute_query("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name VARCHAR(150) NOT NULL UNIQUE,
            price NUMERIC(12, 2) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    # 4. orders table
    # status values: 'pending', 'confirmed', 'completed', 'cancelled'
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
            ("Qatiq", Decimal("7000.00")),
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
    # Standardize phone number search by stripping extra chars if needed, 
    # but exact match is safe since bot provides contact
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

async def add_product(name: str, price: Decimal) -> Dict[str, Any]:
    row = await fetch_row(
        "INSERT INTO products (name, price) VALUES ($1, $2) RETURNING *;",
        name, price
    )
    return dict(row)

async def set_product_active_status(product_id: int, is_active: bool):
    await execute_query("UPDATE products SET is_active = $1 WHERE id = $2;", is_active, product_id)

# --- ORDER METHODS ---

async def create_order(telegram_id: int, cart_items: List[Dict[str, Any]], total_price: Decimal,
                       delivery_date: datetime.date = None, delivery_time_start: str = '06:30', 
                       delivery_time_end: str = '07:30') -> int:
    """
    Creates an order with its items in a transaction.
    cart_items should be a list of dicts: [{'product_id': int, 'quantity': float, 'price': Decimal}]
    """
    if delivery_date is None:
        # Deliver tomorrow morning
        delivery_date = datetime.date.today() + datetime.timedelta(days=1)
        
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Get user local ID
            user_id = await conn.fetchval("SELECT id FROM users WHERE telegram_id = $1;", telegram_id)
            if not user_id:
                raise ValueError(f"User with telegram ID {telegram_id} not found in database.")
                
            # Create Order
            order_id = await conn.fetchval(
                """
                INSERT INTO orders (user_id, status, total_price, delivery_date, delivery_time_start, delivery_time_end)
                VALUES ($1, 'confirmed', $2, $3, $4, $5)
                RETURNING id;
                """,
                user_id, total_price, delivery_date, delivery_time_start, delivery_time_end
            )
            
            # Create Order Items
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
    """Retrieves user's orders and their items."""
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
        # Parse JSON array if needed (asyncpg automatically parses json / jsonb arrays as python lists)
        import json
        if isinstance(order_dict['items'], str):
            order_dict['items'] = json.loads(order_dict['items'])
        result.append(order_dict)
    return result

async def get_all_orders(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves all orders with user info."""
    query = """
        SELECT o.id as order_id, o.status, o.total_price, o.delivery_date, o.delivery_time_start, 
               o.delivery_time_end, o.created_at, u.full_name, u.phone_number, u.telegram_id,
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
    """
    Computes total quantity of each product needed for production on a specific date.
    Only includes orders with status 'confirmed' (or 'pending').
    """
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
    """Computes daily sales report: total revenue, order count, etc."""
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
