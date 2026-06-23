# Dairy Delivery Bot - AI Agent Documentation

A Telegram bot for a dairy delivery service built with **Aiogram 3.x**, **AsyncPG**, and **Python 3.8+**. Dual-service architecture: Telegram bot polling + aiohttp web server for admin dashboard API.

## Quick Reference

| Task | Command |
|------|---------|
| **Setup** | `pip install -r requirements.txt` |
| **Run** | `python bot.py` (requires `.env` + PostgreSQL) |
| **Config** | Copy `.env.example` to `.env`, fill in `BOT_TOKEN`, `DB_*`, `ADMIN_IDS`, `DASHBOARD_PASSWORD` |
| **Logs** | `bot.log` (rotating file: 5MB, 5 backups, UTF-8) |

## Architecture

### Core Layers

1. **Telegram Bot** (`bot.py`, `handlers/`, `states/`, `keyboards/`)
   - Aiogram 3.28.2 with FSM (Finite State Machine) for multi-step flows
   - Handlers organized by feature (registration, menu, order, admin)
   - Memory-based FSM storage (resets on restart; not persistent)

2. **Database** (`database/`)
   - AsyncPG pool (2-20 connections) to PostgreSQL 5+
   - 5 tables: users, products, orders, order_items, branches
   - Auto-creates schema + seeds 4 default products on first run

3. **Web API** (`bot.py` routes)
   - aiohttp server on port 8080 (configurable via `PORT` env var)
   - Bearer token auth (SHA256 hash of `DASHBOARD_PASSWORD`)
   - Endpoints: login, orders, products, broadcast, stats, customers

4. **Admin Dashboard** (`static/`)
   - Vanilla JS PWA with service workers
   - `/chorvador-panel` custom URL for secure entry
   - Real-time order management, product pricing, reports

### Data Flow

```
User
  ↓ (Telegram message)
→ Router (handlers/) → FSM State (states/) → DB (models.py)
  ↓ (API call)
→ Bearer Token Auth → API Route (bot.py) → Dashboard (static/)
```

## Key Patterns

### FSM Flows (Multi-Step Dialogs)

- **Registration**: Name → Phone Contact → Location (deduplicates phone numbers)
- **Ordering**: Product Selection → Quantity → Confirmation → Payment Confirmation
- **Admin Panel**: FSM for product editing, order updates

FSM data stored in memory—only persists during a single user session.

```python
# Example: Registration flow
class RegistrationStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_location = State()
```

### Admin Access Control

Two levels:
1. Hardcoded: `ADMIN_IDS` comma-separated in `.env` (checked at request time)
2. Database: `is_admin` boolean flag in users table

Every admin handler uses `is_admin_check()` filter—check both paths when restricting access.

```python
@router.message(IsAdmin(), Command("admin_menu"))
async def admin_menu(message: Message):
    ...
```

### Async Patterns

**All I/O is async**—no blocking operations:
- Database: `await pool.execute()`, `await pool.fetch()`
- Telegram: `await message.answer()`
- Web: `aiohttp` handlers are async functions
- Scheduler: `while True: await asyncio.sleep(delay)`

Never use `.result()`, `time.sleep()`, or blocking DB drivers.

### Transactional Orders

Order + items created in single DB transaction—either all succeed or all fail:

```python
async with pool.acquire() as conn:
    async with conn.transaction():
        order_id = await conn.fetchval("INSERT INTO orders ...")
        await conn.executemany("INSERT INTO order_items ...", items)
```

### Scheduler & Background Tasks

Simple time-based loop in `utils/scheduler.py`:
- **1:00 AM**: Daily production report to admins
- **5:30 AM**: Breakfast reminder to all customers

No external scheduler needed. Starts on bot startup, runs in background.

```python
while True:
    now = datetime.datetime.now()
    if now.hour == 1 and now.minute == 0:
        # Send report
    await asyncio.sleep(60)
```

## File Organization

```
dairy_delivery_bot/
├── bot.py                     # Main entry + API routes + startup/shutdown
├── requirements.txt           # Aiogram, asyncpg, python-dotenv
├── .env.example / .env        # Config (see Quick Reference)
├── database/
│   ├── connection.py          # AsyncPG pool init + SSL support
│   ├── models.py              # Schema + CRUD queries (users, products, orders)
│   └── __init__.py
├── handlers/
│   ├── registration.py        # New user onboarding (FSM)
│   ├── menu.py                # Main user menu + my profile/orders
│   ├── order.py               # Order flow (cart, quantity, confirmation)
│   ├── admin.py               # Admin-only operations (protected)
│   └── __init__.py
├── keyboards/
│   ├── keyboards.py           # Reply + inline keyboard builders
│   └── __init__.py
├── states/
│   ├── registration_states.py # Registration FSM states
│   ├── order_states.py        # Ordering FSM states
│   ├── admin_states.py        # Admin workflow FSM states
│   └── __init__.py
├── utils/
│   ├── logger.py              # Rotating file logging
│   ├── scheduler.py           # Background tasks (1 AM + 5:30 AM)
│   └── __init__.py
├── static/
│   ├── index.html / login.html  # Admin dashboard UI
│   ├── app.js / style.css       # Dashboard logic + styling
│   ├── sw.js / manifest.json    # Service worker + PWA manifest
│   └── icon.png
└── .gitignore
```

## Development Conventions

| Convention | Details |
|-----------|---------|
| **Language** | All UI strings hard-coded in Uzbek; no i18n framework |
| **Type Hints** | Use throughout (async functions, DB return types, handler params) |
| **Error Handling** | Try-catch + `logger.error()` in handlers; DB errors include exception details |
| **Logging** | Use `from utils.logger import logger`; auto-rotating, console + file |
| **Numbers** | Prices use `decimal.Decimal` (avoid float precision loss); convert to `float` for JSON |
| **Timestamps** | DB defaults use `NOW()`; format for display: `.strftime("%d.%m.%Y")` |
| **Concurrency** | Manual rate limiting: `await asyncio.sleep(0.05)` between broadcasts (~20 msgs/sec) |
| **Routers** | Each handler file registers its router in `bot.py`: `router.include_router(...)` |

## Common Tasks

### Add a New Handler (e.g., support tickets)

1. Create `handlers/support.py` with FSM states and message handlers
2. Import router and register in `bot.py`:
   ```python
   from handlers.support import router as support_router
   dp.include_router(support_router)
   ```
3. Define FSM states in `states/support_states.py`
4. Create inline/reply keyboards in `keyboards/keyboards.py`

### Query Orders with CRUD Pattern

See `database/models.py` for existing patterns:
```python
async def get_all_orders(pool):
    query = "SELECT * FROM orders WHERE status = $1"
    return await pool.fetch(query, "completed")
```

### Add an Admin API Endpoint

1. Add route in `bot.py` with Bearer token check:
   ```python
   @app.post("/api/my-endpoint")
   async def my_endpoint(request):
       token = request.headers.get("Authorization", "").replace("Bearer ", "")
       if not verify_token(token):
           return web.json_response({"error": "Unauthorized"}, status=401)
       # Your logic
   ```
2. Use `pool` from app context: `pool = app["db_pool"]`
3. Return JSON response

### Add Scheduled Task

Edit `utils/scheduler.py`:
```python
while True:
    now = datetime.datetime.now()
    if now.hour == YOUR_HOUR and now.minute == 0:
        await broadcast_to_admins("Your message")
    await asyncio.sleep(60)
```

## Testing & Debugging

- **Logs**: `tail -f bot.log` for real-time events
- **Database**: Connect with `psql` to inspect tables
- **FSM State**: Add `logger.debug()` in handlers to trace state transitions
- **API**: Use curl or Postman with Bearer token: `curl -H "Authorization: Bearer TOKEN" http://localhost:8080/api/...`

## Gotchas

1. **FSM doesn't persist**: Memory storage resets on bot restart. For critical data, use the database.
2. **Admin checks**: Don't forget to apply `IsAdmin()` filter to sensitive handlers.
3. **Async context**: Never use `pool.execute()` outside an async function—always `await`.
4. **Price precision**: Use `Decimal` for prices, not floats. Convert to `float` only for JSON.
5. **Broadcast rate**: Telegram has soft rate limits (~30 msgs/sec per bot). 50ms sleep between broadcasts helps.
6. **Timezone**: All timestamps use server timezone. Check `.env` or system settings if times are off.

## Database Schema (Auto-Created on Startup)

```sql
CREATE TABLE users (id SERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE, name TEXT, phone TEXT UNIQUE, location TEXT, is_admin BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW());

CREATE TABLE products (id SERIAL PRIMARY KEY, name TEXT, price DECIMAL(10,2), category TEXT, created_at TIMESTAMP DEFAULT NOW());

CREATE TABLE orders (id SERIAL PRIMARY KEY, user_id INT, status TEXT, total DECIMAL(10,2), created_at TIMESTAMP DEFAULT NOW(), FOREIGN KEY (user_id) REFERENCES users(id));

CREATE TABLE order_items (id SERIAL PRIMARY KEY, order_id INT, product_id INT, quantity INT, FOREIGN KEY (order_id) REFERENCES orders(id), FOREIGN KEY (product_id) REFERENCES products(id));

CREATE TABLE branches (id SERIAL PRIMARY KEY, name TEXT, address TEXT, phone TEXT, latitude NUMERIC, longitude NUMERIC);
```

## Useful Links

- **Aiogram Docs**: https://docs.aiogram.dev/en/latest/
- **AsyncPG**: https://magicstack.github.io/asyncpg/
- **Telegram Bot API**: https://core.telegram.org/bots/api
