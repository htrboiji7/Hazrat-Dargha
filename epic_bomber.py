#!/usr/bin/env python3
"""
EPIC DUAL BOMBER – Time‑based, Speed control, Flask Dashboard, Auto‑broadcast
-----------------------------------------------------------------------------
- Time plans: 5/10/15/20/25 min (5min=10cr, 10min=20cr, 15min=30cr, 20min=40cr, 25min=50cr)
- Speeds: Slow(1/s), Medium(5/s), Fast(20/s), Extreme(100/s) – Extreme requires ≥100cr or Lifetime
- SMS + Call dummy APIs (50 SMS, 20 Call) – no real messages
- Credits system, referrals, random daily bonus (1-5), number protection, auto-protect suggestion
- Flask admin dashboard (live stats, add credits, ban/unban, view logs)
- Auto‑broadcast to users inactive for 7 days
- Stop button, live timer, force‑join, UPI payment QR
"""

import os
import re
import asyncio
import threading
import logging
import time
import random
import csv
from io import StringIO, BytesIO
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from flask import Flask, render_template_string, request, redirect, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
import requests
import qrcode
from pymongo import MongoClient
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(','))) if os.getenv("ADMIN_IDS") else []
FORCE_CHANNELS = [c.strip() for c in os.getenv("FORCE_CHANNELS", "").split(',') if c.strip()]
UPI_ID = os.getenv("UPI_ID", "your_upi@fampay")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBot")
REFERRAL_CREDITS = int(os.getenv("REFERRAL_CREDITS", 2))
EXTREME_MIN_CREDITS = int(os.getenv("EXTREME_MIN_CREDITS", 100))
PORT = int(os.environ.get("PORT", 8000))
FLASK_PORT = int(os.environ.get("FLASK_PORT", 5000))
ADMIN_WEB_KEY = os.getenv("ADMIN_WEB_KEY", "admin123")

# Time plans: (minutes, credits)
TIME_PLANS = [(5, 10), (10, 20), (15, 30), (20, 40), (25, 50)]

# Speed settings (delay in seconds)
SPEEDS = {"slow": 1.0, "medium": 0.2, "fast": 0.05, "extreme": 0.01}
MAX_THREADS = 15

# ================= DUMMY APIS =================
SMS_APIS = [
    "https://httpbin.org/post", "https://httpbin.org/status/200",
    "https://reqres.in/api/users", "https://jsonplaceholder.typicode.com/posts",
    "https://postman-echo.com/post", "https://webhook.site/#!/dummy-echo",
    "https://dummyapi.io/data/v1/post", "https://api.mockable.io/api/demo",
    "https://run.mocky.io/v3/1d0c5f4a-3b2e-4a1c-8f9d-0e1a2b3c4d5e",
    "https://httpbin.org/delay/0", "https://httpbin.org/anything",
    "https://httpbin.org/response-headers?free=edu", "https://httpbin.org/cookies/set?dummy=sms",
    "https://httpbin.org/xml", "https://httpbin.org/json", "https://httpbin.org/bytes/100",
    "https://httpbin.org/stream/1", "https://httpbin.org/redirect/1", "https://httpbin.org/status/201",
    "https://httpbin.org/status/202", "https://httpbin.org/status/204", "https://httpbin.org/status/301",
    "https://httpbin.org/status/302", "https://httpbin.org/status/400", "https://httpbin.org/status/401",
    "https://httpbin.org/status/403", "https://httpbin.org/status/404", "https://httpbin.org/status/500",
    "https://httpbin.org/status/502", "https://httpbin.org/status/503", "https://httpbin.org/get?dummy=sms",
    "https://httpbin.org/delete", "https://httpbin.org/patch", "https://httpbin.org/put",
    "https://reqres.in/api/register", "https://reqres.in/api/login",
    "https://jsonplaceholder.typicode.com/albums", "https://jsonplaceholder.typicode.com/photos",
    "https://jsonplaceholder.typicode.com/todos", "https://jsonplaceholder.typicode.com/comments",
    "https://dummy.restapiexample.com/api/v1/create", "https://api.instantwebtools.com/v1/airlines",
    "https://fakestoreapi.com/products", "https://dummyjson.com/products/add",
    "https://httpbin.org/headers", "https://httpbin.org/ip", "https://httpbin.org/user-agent",
    "https://httpbin.org/cache", "https://httpbin.org/etag/test"
]

CALL_APIS = [
    "https://httpbin.org/post", "https://reqres.in/api/users",
    "https://postman-echo.com/post", "https://jsonplaceholder.typicode.com/posts",
    "https://httpbin.org/status/200", "https://httpbin.org/anything",
    "https://dummyapi.io/data/v1/post", "https://api.mockable.io/api/demo",
    "https://run.mocky.io/v3/1d0c5f4a-3b2e-4a1c-8f9d-0e1a2b3c4d5e",
    "https://httpbin.org/delay/0", "https://httpbin.org/response-headers?free=call",
    "https://httpbin.org/status/201", "https://httpbin.org/status/202",
    "https://httpbin.org/status/204", "https://httpbin.org/get?dummy=call",
    "https://reqres.in/api/register", "https://fakestoreapi.com/products",
    "https://dummyjson.com/products/add", "https://httpbin.org/headers",
    "https://httpbin.org/ip"
]

SMS_PAYLOAD = {"mobile": None, "otp": "123456", "action": "send_otp", "source": "telegram"}
CALL_PAYLOAD = {"phone": None, "action": "initiate_call", "type": "voice", "source": "telegram"}
HEADERS = {"Content-Type": "application/json"}

# ================= DATABASE =================
client = MongoClient(MONGO_URI)
db = client['epic_bomber']
users = db['users']
protected = db['protected_numbers']
payments = db['pending_payments']
bomb_logs = db['bomb_logs']
active_bombs = db['active_bombs']
referrals = db['referrals']
bomb_counter = db['bomb_counter']

# ================= HELPER FUNCTIONS =================
def init_user(user_id, referrer_id=None):
    if users.find_one({"user_id": user_id}):
        return
    users.insert_one({
        "user_id": user_id,
        "credits": 20,
        "lifetime": False,
        "total_bombs": 0,
        "total_requests": 0,
        "banned": False,
        "joined_at": datetime.now(),
        "referred_by": None,
        "referral_count": 0,
        "last_bonus": datetime.now() - timedelta(days=1)
    })
    if referrer_id and referrer_id != user_id:
        referrer = users.find_one({"user_id": referrer_id, "banned": False})
        if referrer:
            add_credits(referrer_id, REFERRAL_CREDITS)
            add_credits(user_id, REFERRAL_CREDITS)
            users.update_one({"user_id": referrer_id}, {"$inc": {"referral_count": 1}})
            referrals.insert_one({"referrer": referrer_id, "referee": user_id, "timestamp": datetime.now()})

def get_user_credits(user_id):
    user = users.find_one({"user_id": user_id})
    if not user:
        return 0
    if user.get("lifetime"):
        return float('inf')
    return user.get("credits", 0)

def add_credits(user_id, amount):
    users.update_one({"user_id": user_id}, {"$inc": {"credits": amount}})

def deduct_credits(user_id, amount):
    users.update_one({"user_id": user_id}, {"$inc": {"credits": -amount}})

def set_lifetime(user_id):
    users.update_one({"user_id": user_id}, {"$set": {"lifetime": True}})

def is_banned(user_id):
    user = users.find_one({"user_id": user_id})
    return user.get("banned", False) if user else False

def ban_user(user_id):
    users.update_one({"user_id": user_id}, {"$set": {"banned": True}})

def unban_user(user_id):
    users.update_one({"user_id": user_id}, {"$set": {"banned": False}})

def is_number_protected(number):
    return protected.find_one({"number": number, "paid_until": {"$gt": datetime.now()}}) is not None

def protect_number(number, user_id, duration_days):
    protected.update_one(
        {"number": number},
        {"$set": {"owner_id": user_id, "paid_until": datetime.now() + timedelta(days=duration_days), "protected_at": datetime.now()}},
        upsert=True
    )

def add_pending_payment(user_id, tx_id, amount, credits):
    payments.insert_one({"user_id": user_id, "transaction_id": tx_id, "amount": amount, "credits": credits, "status": "pending", "timestamp": datetime.now()})

def get_pending_payment(tx_id):
    return payments.find_one({"transaction_id": tx_id, "status": "pending"})

def verify_payment(tx_id):
    payments.update_one({"transaction_id": tx_id}, {"$set": {"status": "verified"}})

def apply_daily_bonus(user_id):
    user = users.find_one({"user_id": user_id})
    if not user:
        return 0
    last = user.get("last_bonus")
    if not last or last.date() < datetime.now().date():
        bonus = random.randint(1, 5)
        add_credits(user_id, bonus)
        users.update_one({"user_id": user_id}, {"$set": {"last_bonus": datetime.now()}})
        return bonus
    return 0

def generate_referral_link(user_id):
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def generate_upi_qr(upi_id, payee_name, amount, note):
    upi_url = f"upi://pay?pa={upi_id}&pn={payee_name}&am={amount}&cu=INR&tn={note}"
    qr = qrcode.make(upi_url)
    bio = BytesIO()
    qr.save(bio, 'PNG')
    bio.seek(0)
    return bio, upi_url

def can_bomb(user_id, required_credits):
    user = users.find_one({"user_id": user_id})
    if not user or user.get("banned"):
        return False, "Banned or not found."
    credits = get_user_credits(user_id)
    if credits < required_credits and not user.get("lifetime"):
        return False, f"Insufficient credits. Need {required_credits}. Use /buy"
    return True, "OK"

def can_use_extreme_speed(user_id):
    user = users.find_one({"user_id": user_id})
    if not user:
        return False
    if user.get("lifetime"):
        return True
    return user.get("credits", 0) >= EXTREME_MIN_CREDITS

def increment_bomb_counter(user_id, number):
    counter = bomb_counter.find_one({"user_id": user_id, "number": number})
    if counter:
        new_count = counter.get("count", 0) + 1
        bomb_counter.update_one({"_id": counter["_id"]}, {"$set": {"count": new_count, "last_bomb": datetime.now()}})
        return new_count
    else:
        bomb_counter.insert_one({"user_id": user_id, "number": number, "count": 1, "last_bomb": datetime.now()})
        return 1

def log_bomb(user_id, target, bomb_type, success, failed, duration_sec, speed_name, stopped=False):
    bomb_logs.insert_one({
        "user_id": user_id, "target": target, "bomb_type": bomb_type,
        "success": success, "failed": failed,
        "duration_sec": duration_sec, "speed": speed_name, "stopped": stopped,
        "timestamp": datetime.now()
    })
    users.update_one({"user_id": user_id}, {"$inc": {"total_bombs": 1, "total_requests": success+failed}})

def set_stop_flag(user_id):
    active_bombs.update_one({"user_id": user_id}, {"$set": {"stop": True}}, upsert=True)

def clear_stop_flag(user_id):
    active_bombs.delete_one({"user_id": user_id})

def is_stopped(user_id):
    doc = active_bombs.find_one({"user_id": user_id})
    return doc.get("stop", False) if doc else False

def get_inactive_users(days=7):
    threshold = datetime.now() - timedelta(days=days)
    all_users = list(users.find({}, {"user_id": 1}))
    inactive = []
    for u in all_users:
        last_bomb = bomb_logs.find_one({"user_id": u["user_id"]}, sort=[("timestamp", -1)])
        if not last_bomb or last_bomb["timestamp"] < threshold:
            inactive.append(u["user_id"])
    return inactive

# ================= BOMB ENGINE =================
def send_one_request(url, payload_template, phone, req_id):
    payload = {}
    for k, v in payload_template.items():
        payload[k] = phone if v is None else v
    payload["req_id"] = req_id
    try:
        resp = requests.post(url, json=payload, headers=HEADERS, timeout=3)
        return resp.status_code < 500
    except:
        return False

async def run_time_bomb(update, context, phone, duration_sec, speed_name, bomb_type):
    user_id = update.effective_user.id
    # find cost
    cost = None
    for minutes, cred in TIME_PLANS:
        if minutes*60 == duration_sec:
            cost = cred
            break
    if cost is None:
        await update.message.reply_text("Invalid duration.")
        return

    if speed_name == "extreme" and not can_use_extreme_speed(user_id):
        await update.message.reply_text(f"⚠️ Extreme speed requires at least {EXTREME_MIN_CREDITS} credits or Lifetime. Use another speed.")
        return

    allowed, msg = can_bomb(user_id, cost)
    if not allowed:
        await update.message.reply_text(f"❌ {msg}")
        return
    if is_number_protected(phone):
        await update.message.reply_text("🔒 This number is protected and cannot be bombed.")
        return

    user = users.find_one({"user_id": user_id})
    if not user.get("lifetime"):
        deduct_credits(user_id, cost)

    delay = SPEEDS[speed_name]
    api_list = SMS_APIS if bomb_type == "sms" else CALL_APIS
    payload_template = SMS_PAYLOAD if bomb_type == "sms" else CALL_PAYLOAD

    status_msg = await update.message.reply_text(
        f"🔥 {bomb_type.upper()} Time Bomb\n"
        f"📱 {phone}\n⏱️ Duration: {duration_sec//60} min\n⚡ Speed: {speed_name.upper()} (~{1/delay:.0f} req/sec)\n"
        f"💎 Credits: {cost}\n🟡 Starting...",
        parse_mode='HTML'
    )
    keyboard = [[InlineKeyboardButton("🛑 STOP", callback_data=f"stop_{user_id}")]]
    await status_msg.edit_text(status_msg.text_html, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    clear_stop_flag(user_id)
    success = failed = 0
    lock = threading.Lock()
    stop_req = False
    start_time = time.time()
    end_time = start_time + duration_sec

    def worker():
        nonlocal success, failed, stop_req
        while not stop_req and time.time() < end_time and not is_stopped(user_id):
            url = random.choice(api_list)
            ok = send_one_request(url, payload_template, phone, int(time.time()*1000))
            with lock:
                if ok:
                    success += 1
                else:
                    failed += 1
            time.sleep(delay)

    threads = []
    for _ in range(MAX_THREADS):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)

    last_update = time.time()
    while any(t.is_alive() for t in threads) and not stop_req:
        if is_stopped(user_id):
            stop_req = True
            break
        if time.time() - last_update > 2:
            remaining = max(0, end_time - time.time())
            elapsed = time.time() - start_time
            rate = success / elapsed if elapsed > 0 else 0
            await status_msg.edit_text(
                f"🔥 {bomb_type.upper()} in Progress\n📱 {phone}\n"
                f"⏱️ Remaining: {int(remaining)} sec\n"
                f"✅ {success} | ❌ {failed} | ⚡ {rate:.1f}/sec",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            last_update = time.time()
        await asyncio.sleep(1)

    stop_req = True
    for t in threads:
        t.join()
    stopped = is_stopped(user_id) or stop_req
    log_bomb(user_id, phone, bomb_type, success, failed, duration_sec, speed_name, stopped)
    clear_stop_flag(user_id)

    # Auto-protect suggestion
    count = increment_bomb_counter(user_id, phone)
    if count >= 3:
        await status_msg.reply_text(
            f"🔒 You've bombed {phone} {count} times. Protect it for 30 days with 50 credits?\n"
            f"Use /protect or click below.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ Protect Now", callback_data=f"auto_protect_{phone}")]])
        )

    result = f"{'🛑 Stopped' if stopped else '✅ Completed'}\n📱 {phone}\n📨 {success} requests sent\n❌ {failed} failed\n💎 Remaining: {get_user_credits(user_id)}"
    await status_msg.edit_text(result, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data='start')]]))

# ================= FLASK DASHBOARD =================
app_flask = Flask(__name__)

def is_admin_auth():
    key = request.args.get('admin_key') or request.form.get('admin_key')
    return key == ADMIN_WEB_KEY

@app_flask.route('/')
def dashboard():
    if not is_admin_auth():
        return "Unauthorized", 401
    total_users = users.count_documents({})
    total_bombs = bomb_logs.count_documents({})
    total_requests = bomb_logs.aggregate([{"$group": {"_id": None, "sum": {"$sum": "$success"}}}])
    total_requests = list(total_requests)[0]['sum'] if total_requests else 0
    active_bombs_count = active_bombs.count_documents({})
    recent_logs = list(bomb_logs.find().sort("timestamp", -1).limit(20))
    return render_template_string('''
        <html><head><title>Admin Dashboard</title><style>table,th,td{border:1px solid black;border-collapse:collapse;padding:5px;}</style></head>
        <body><h1>Epic Bomber Admin</h1>
        <p>Total Users: {{ total_users }}</p><p>Total Bombs: {{ total_bombs }}</p><p>Total OTPs Sent: {{ total_requests }}</p><p>Active Bombs: {{ active_bombs }}</p>
        <hr><h2>Manage User</h2>
        <form action="/add_credits" method="post">User ID: <input name="user_id"> Credits: <input name="amount"> <input type="submit" value="Add Credits"></form>
        <form action="/ban" method="post">User ID: <input name="user_id"> <input type="submit" value="Ban"></form>
        <form action="/unban" method="post">User ID: <input name="user_id"> <input type="submit" value="Unban"></form>
        <hr><h2>Recent Bomb Logs</h2>
        <table><tr><th>User</th><th>Target</th><th>Type</th><th>Success</th><th>Failed</th><th>Time</th></tr>
        {% for log in logs %}<tr><td>{{ log.user_id }}</td><td>{{ log.target }}</td><td>{{ log.bomb_type }}</td><td>{{ log.success }}</td><td>{{ log.failed }}</td><td>{{ log.timestamp }}</td></tr>{% endfor %}
        </table></body></html>
    ''', total_users=total_users, total_bombs=total_bombs, total_requests=total_requests,
       active_bombs=active_bombs_count, logs=recent_logs)

@app_flask.route('/add_credits', methods=['POST'])
def add_credits_web():
    if not is_admin_auth():
        return "Unauthorized", 401
    user_id = int(request.form['user_id'])
    amount = int(request.form['amount'])
    add_credits(user_id, amount)
    return redirect(url_for('dashboard', admin_key=ADMIN_WEB_KEY))

@app_flask.route('/ban', methods=['POST'])
def ban_web():
    if not is_admin_auth():
        return "Unauthorized", 401
    user_id = int(request.form['user_id'])
    ban_user(user_id)
    return redirect(url_for('dashboard', admin_key=ADMIN_WEB_KEY))

@app_flask.route('/unban', methods=['POST'])
def unban_web():
    if not is_admin_auth():
        return "Unauthorized", 401
    user_id = int(request.form['user_id'])
    unban_user(user_id)
    return redirect(url_for('dashboard', admin_key=ADMIN_WEB_KEY))

def run_flask():
    app_flask.run(host='0.0.0.0', port=FLASK_PORT, debug=False)

# ================= TELEGRAM HANDLERS =================
async def get_missing_channels(update, context):
    missing = []
    for ch in FORCE_CHANNELS:
        cid = ch.split('|')[0] if '|' in ch else ch
        try:
            member = await context.bot.get_chat_member(chat_id=cid, user_id=update.effective_user.id)
            if member.status not in ["member", "administrator", "creator"]:
                missing.append(ch)
        except:
            missing.append(ch)
    return missing

async def force_join_wall(update, context, missing=None):
    if missing is None:
        missing = await get_missing_channels(update, context)
    if not missing:
        return False
    keyboard = []
    for ch in missing:
        parts = ch.split('|')
        url = parts[1] if len(parts) > 1 else (f"https://t.me/{ch[1:]}" if ch.startswith('@') else ch)
        keyboard.append([InlineKeyboardButton("📢 Join", url=url)])
    keyboard.append([InlineKeyboardButton("✅ Verify", callback_data='verify_force')])
    text = "🚫 Join channels first."
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    return True

async def start(update, context):
    user_id = update.effective_user.id
    args = context.args
    ref = None
    if args and args[0].startswith("ref_"):
        try:
            ref = int(args[0].split("_")[1])
        except:
            pass
    init_user(user_id, ref)
    if is_banned(user_id):
        await update.message.reply_text("Banned.")
        return
    if await force_join_wall(update, context):
        return
    bonus = apply_daily_bonus(user_id)
    if bonus:
        await update.message.reply_text(f"🎁 Random daily bonus: +{bonus} credits!")
    await show_main_menu(update, context)

async def show_main_menu(update, context):
    user_id = update.effective_user.id
    credits = get_user_credits(user_id)
    is_admin = user_id in ADMIN_IDS
    keyboard = [
        [InlineKeyboardButton("💣 SMS Bomb", callback_data='sms_bomb'), InlineKeyboardButton("📞 Call Bomb", callback_data='call_bomb')],
        [InlineKeyboardButton("🛡️ Protect", callback_data='protect'), InlineKeyboardButton("📊 Stats", callback_data='stats')],
        [InlineKeyboardButton("💰 Buy", callback_data='buy'), InlineKeyboardButton("🔗 Refer", callback_data='referral')],
        [InlineKeyboardButton("🛑 Stop", callback_data='stop_self'), InlineKeyboardButton("ℹ️ Help", callback_data='help')],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("⚙️ Admin", callback_data='admin')])
    text = f"🌟 Welcome!\n💎 Credits: {credits}\n⚡ Time-based: 5min=10cr, 10min=20cr, 15min=30cr, 20min=40cr, 25min=50cr"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def bomb_start(update, context, bomb_type):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if is_banned(user_id):
        await query.edit_message_text("Banned.")
        return
    if await force_join_wall(update, context):
        return
    context.user_data['bomb_type'] = bomb_type
    context.user_data['bomb_step'] = 'duration'
    keyboard = [
        [InlineKeyboardButton("5 min - 10 cr", callback_data='dur_5'), InlineKeyboardButton("10 min - 20 cr", callback_data='dur_10')],
        [InlineKeyboardButton("15 min - 30 cr", callback_data='dur_15'), InlineKeyboardButton("20 min - 40 cr", callback_data='dur_20')],
        [InlineKeyboardButton("25 min - 50 cr", callback_data='dur_25')]
    ]
    await query.edit_message_text("Select duration:", reply_markup=InlineKeyboardMarkup(keyboard))

async def duration_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    duration_map = {'dur_5':300, 'dur_10':600, 'dur_15':900, 'dur_20':1200, 'dur_25':1500}
    cost_map = {'dur_5':10, 'dur_10':20, 'dur_15':30, 'dur_20':40, 'dur_25':50}
    if data not in duration_map:
        return
    context.user_data['duration'] = duration_map[data]
    context.user_data['cost'] = cost_map[data]
    context.user_data['bomb_step'] = 'speed'
    keyboard = [
        [InlineKeyboardButton("🐢 Slow (1/sec)", callback_data='speed_slow')],
        [InlineKeyboardButton("⚡ Medium (5/sec)", callback_data='speed_medium')],
        [InlineKeyboardButton("🔥 Fast (20/sec)", callback_data='speed_fast')],
        [InlineKeyboardButton("💀 Extreme (100/sec)", callback_data='speed_extreme')]
    ]
    await query.edit_message_text("Select speed:", reply_markup=InlineKeyboardMarkup(keyboard))

async def speed_callback(update, context):
    query = update.callback_query
    await query.answer()
    speed_map = {'speed_slow':'slow', 'speed_medium':'medium', 'speed_fast':'fast', 'speed_extreme':'extreme'}
    speed = speed_map.get(query.data)
    if not speed:
        return
    user_id = update.effective_user.id
    if speed == 'extreme' and not can_use_extreme_speed(user_id):
        await query.edit_message_text(f"⚠️ Extreme speed requires at least {EXTREME_MIN_CREDITS} credits or Lifetime. Please select another speed.")
        return
    phone = context.user_data.get('target')
    duration = context.user_data.get('duration')
    bomb_type = context.user_data.get('bomb_type')
    if not phone or not duration:
        await query.edit_message_text("Session expired. Use /start again.")
        return
    context.user_data.pop('bomb_step', None)
    context.user_data.pop('target', None)
    context.user_data.pop('duration', None)
    await run_time_bomb(update, context, phone, duration, speed, bomb_type)

async def handle_message(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if is_banned(user_id):
        await update.message.reply_text("Banned.")
        return
    if await force_join_wall(update, context):
        return
    # Payment TX ID
    if context.user_data.get('pending_payment'):
        pending = context.user_data['pending_payment']
        add_pending_payment(user_id, text, pending['amount'], pending['credits'])
        for admin in ADMIN_IDS:
            await context.bot.send_message(admin, f"💸 Payment pending\nUser: {user_id}\nTXID: {text}\n₹{pending['amount']}")
        await update.message.reply_text("✅ Payment recorded. Admin will verify.")
        context.user_data.pop('pending_payment')
        return
    # Protect flow
    if context.user_data.get('action') == 'protect':
        if not re.match(r'^\d{10}$', text):
            await update.message.reply_text("10 digits only.")
            return
        plan = context.user_data.get('protect_plan')
        if not plan:
            await update.message.reply_text("Select plan first.")
            return
        cost, days = plan['cost'], plan['days']
        credits = get_user_credits(user_id)
        if credits < cost and not users.find_one({"user_id": user_id}).get("lifetime"):
            await update.message.reply_text(f"Need {cost} credits.")
            return
        if not users.find_one({"user_id": user_id}).get("lifetime"):
            deduct_credits(user_id, cost)
        if days is None:
            protect_number(text, user_id, 365*100)
            await update.message.reply_text(f"✅ {text} protected forever!")
        else:
            protect_number(text, user_id, days)
            await update.message.reply_text(f"✅ {text} protected for {days} days.")
        context.user_data.pop('action')
        context.user_data.pop('protect_plan')
        return
    # Bombing flow
    step = context.user_data.get('bomb_step')
    if step == 'duration':
        # already handled by callback
        return
    elif step == 'speed':
        # handled by callback
        return
    elif step == 'phone':
        if not re.match(r'^\d{10}$', text):
            await update.message.reply_text("Invalid number.")
            return
        if is_number_protected(text):
            await update.message.reply_text("🔒 Number is protected.")
            return
        context.user_data['target'] = text
        context.user_data['bomb_step'] = 'duration'
        # show duration menu
        keyboard = [
            [InlineKeyboardButton("5 min - 10 cr", callback_data='dur_5'), InlineKeyboardButton("10 min - 20 cr", callback_data='dur_10')],
            [InlineKeyboardButton("15 min - 30 cr", callback_data='dur_15'), InlineKeyboardButton("20 min - 40 cr", callback_data='dur_20')],
            [InlineKeyboardButton("25 min - 50 cr", callback_data='dur_25')]
        ]
        await update.message.reply_text("Select duration:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text("Use /start")

async def protect_command(update, context):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("Banned.")
        return
    if await force_join_wall(update, context):
        return
    keyboard = [
        [InlineKeyboardButton("30 Days - 50 Credits", callback_data='protect_30')],
        [InlineKeyboardButton("6 Months - 250 Credits", callback_data='protect_180')],
        [InlineKeyboardButton("Lifetime - 1000 Credits", callback_data='protect_lifetime')],
        [InlineKeyboardButton("🔙 Back", callback_data='start')]
    ]
    await update.message.reply_text("🛡️ Protection Plans", reply_markup=InlineKeyboardMarkup(keyboard))

async def process_protect_plan(query, user_id, plan, context):
    plans = {'30': (50,30), '180': (250,180), 'lifetime': (1000,None)}
    cost, days = plans[plan]
    credits = get_user_credits(user_id)
    if credits < cost and not users.find_one({"user_id": user_id}).get("lifetime"):
        await query.edit_message_text(f"Need {cost} credits")
        return
    context.user_data['protect_plan'] = {'cost': cost, 'days': days}
    context.user_data['action'] = 'protect'
    await query.edit_message_text("Send 10-digit number to protect:")

async def auto_protect_callback(update, context):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("auto_protect_"):
        phone = data.split("_")[2]
        user_id = update.effective_user.id
        cost = 50
        credits = get_user_credits(user_id)
        if credits < cost and not users.find_one({"user_id": user_id}).get("lifetime"):
            await query.edit_message_text(f"Need {cost} credits to protect. Use /buy")
            return
        if not users.find_one({"user_id": user_id}).get("lifetime"):
            deduct_credits(user_id, cost)
        protect_number(phone, user_id, 30)
        await query.edit_message_text(f"✅ {phone} protected for 30 days!")
    else:
        await query.edit_message_text("Unknown")

async def buy_command(update, context):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await update.message.reply_text("Banned.")
        return
    if await force_join_wall(update, context):
        return
    keyboard = [
        [InlineKeyboardButton("100 Credits - ₹50", callback_data='buy_100')],
        [InlineKeyboardButton("1000 Credits - ₹250", callback_data='buy_1000')],
        [InlineKeyboardButton("2000 Credits - ₹599", callback_data='buy_2000')],
        [InlineKeyboardButton("Lifetime - ₹899", callback_data='buy_lifetime')],
        [InlineKeyboardButton("🔙 Back", callback_data='start')]
    ]
    await update.message.reply_text("💰 Buy Credits", reply_markup=InlineKeyboardMarkup(keyboard))

async def process_buy_plan(query, user_id, plan_key, context):
    plans = {'100': (50,100), '1000': (250,1000), '2000': (599,2000), 'lifetime': (899,0)}
    amount, credits = plans[plan_key]
    qr_img, upi_url = generate_upi_qr(UPI_ID, "EpicBomber", amount, f"Credits:{credits}")
    context.user_data['pending_payment'] = {'amount': amount, 'credits': credits}
    await query.edit_message_text(f"Pay ₹{amount}\nSend TX ID after payment.")
    await query.message.reply_photo(qr_img, caption="Scan to pay")
    await query.message.reply_text(f"UPI: {upi_url}")

async def my_stats(update, context):
    user_id = update.effective_user.id
    user = users.find_one({"user_id": user_id})
    if not user:
        await update.message.reply_text("Use /start first")
        return
    credits = get_user_credits(user_id)
    total_bombs = user.get("total_bombs", 0)
    total_req = user.get("total_requests", 0)
    text = f"💎 Credits: {credits}\n💣 Bombs: {total_bombs}\n📨 Total OTPs: {total_req}"
    await update.message.reply_text(text, parse_mode='HTML')

async def referral_command(update, context):
    user_id = update.effective_user.id
    link = generate_referral_link(user_id)
    await update.message.reply_text(f"🔗 Referral link:\n{link}\n+{REFERRAL_CREDITS} each")

async def help_command(update, context):
    text = "🔥 Epic Time Bomber\n- Time plans: 5/10/15/20/25 min (credits: 10/20/30/40/50)\n- Speeds: Slow(1/s), Medium(5/s), Fast(20/s), Extreme(100/s – needs ≥100 credits or lifetime)\n- Daily random bonus (1-5)\n- Auto-protect after 3 bombs on same number\n- Commands: /start, /stop, /stats, /buy, /protect, /referral"
    await update.message.reply_text(text)

async def stop_command(update, context):
    set_stop_flag(update.effective_user.id)
    await update.message.reply_text("🛑 Stop signal sent.")

async def status_command(update, context):
    user_id = update.effective_user.id
    if is_stopped(user_id):
        await update.message.reply_text("Bombing active, stop requested.")
    else:
        await update.message.reply_text("No active bombing.")

# ================= ADMIN PANEL (Inline) =================
async def admin_panel(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data='admin_stats')],
        [InlineKeyboardButton("➕ Add Credits", callback_data='admin_add')],
        [InlineKeyboardButton("🚫 Ban", callback_data='admin_ban'), InlineKeyboardButton("✅ Unban", callback_data='admin_unban')],
        [InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast')],
        [InlineKeyboardButton("🔘 Verify Payment", callback_data='admin_verify')],
        [InlineKeyboardButton("📄 Export Logs", callback_data='admin_export')],
        [InlineKeyboardButton("🔙 Back", callback_data='start')]
    ]
    await query.edit_message_text("⚙️ Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_stats_cmd(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    query = update.callback_query
    total_users = users.count_documents({})
    total_bombs = bomb_logs.count_documents({})
    total_req = bomb_logs.aggregate([{"$group": {"_id": None, "sum": {"$sum": "$success"}}}])
    total_req = list(total_req)[0]['sum'] if total_req else 0
    text = f"👥 Users: {total_users}\n💣 Bombs: {total_bombs}\n📨 OTPs: {total_req}"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data='admin')]]))

async def admin_add_credits(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    context.user_data['admin_action'] = 'add'
    await update.callback_query.edit_message_text("Send: `user_id amount`")

async def admin_ban(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    context.user_data['admin_action'] = 'ban'
    await update.callback_query.edit_message_text("Send user_id to ban")

async def admin_unban(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    context.user_data['admin_action'] = 'unban'
    await update.callback_query.edit_message_text("Send user_id to unban")

async def admin_broadcast(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    context.user_data['admin_action'] = 'broadcast'
    await update.callback_query.edit_message_text("Send broadcast message")

async def admin_verify(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    context.user_data['admin_action'] = 'verify'
    await update.callback_query.edit_message_text("Send: `user_id transaction_id`")

async def admin_export_logs(update, context):
    if update.effective_user.id not in ADMIN_IDS:
        return
    query = update.callback_query
    await query.answer()
    logs = list(bomb_logs.find())
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["user_id", "target", "type", "success", "failed", "duration_sec", "speed", "stopped", "timestamp"])
    for log in logs:
        writer.writerow([log.get("user_id"), log.get("target"), log.get("bomb_type"), log.get("success"), log.get("failed"), log.get("duration_sec"), log.get("speed"), log.get("stopped"), log.get("timestamp")])
    output.seek(0)
    await query.message.reply_document(document=output, filename="bomb_logs.csv")
    await query.edit_message_text("Logs exported.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data='admin')]]))

async def handle_admin_input(update, context):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    text = update.message.text.strip()
    action = context.user_data.get('admin_action')
    if action == 'add':
        parts = text.split()
        if len(parts) == 2:
            uid, amt = int(parts[0]), int(parts[1])
            add_credits(uid, amt)
            await update.message.reply_text(f"Added {amt} to {uid}")
            await context.bot.send_message(uid, f"🎉 {amt} credits added by admin!")
        else:
            await update.message.reply_text("Invalid format")
        context.user_data.pop('admin_action')
    elif action == 'ban':
        try:
            uid = int(text)
            ban_user(uid)
            await update.message.reply_text(f"Banned {uid}")
        except:
            await update.message.reply_text("Invalid ID")
        context.user_data.pop('admin_action')
    elif action == 'unban':
        try:
            uid = int(text)
            unban_user(uid)
            await update.message.reply_text(f"Unbanned {uid}")
        except:
            await update.message.reply_text("Invalid ID")
        context.user_data.pop('admin_action')
    elif action == 'broadcast':
        msg = text
        all_users = [u['user_id'] for u in users.find({}, {'user_id': 1})]
        sent = 0
        for uid in all_users:
            try:
                await context.bot.send_message(uid, f"📢 Broadcast\n\n{msg}")
                sent += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await update.message.reply_text(f"Sent to {sent} users")
        context.user_data.pop('admin_action')
    elif action == 'verify':
        parts = text.split()
        if len(parts) == 2:
            uid, tx = int(parts[0]), parts[1]
            payment = get_pending_payment(tx)
            if payment and payment['user_id'] == uid:
                verify_payment(tx)
                if payment['credits'] == 0:
                    set_lifetime(uid)
                    await update.message.reply_text(f"Lifetime granted to {uid}")
                    await context.bot.send_message(uid, "🌟 Lifetime access granted!")
                else:
                    add_credits(uid, payment['credits'])
                    await update.message.reply_text(f"Added {payment['credits']} credits to {uid}")
                    await context.bot.send_message(uid, f"✅ Payment verified! +{payment['credits']} credits")
            else:
                await update.message.reply_text("Payment not found or mismatch")
        else:
            await update.message.reply_text("Invalid format")
        context.user_data.pop('admin_action')
    else:
        await update.message.reply_text("No pending action")

# ================= BUTTON CALLBACK =================
async def button_callback(update, context):
    query = update.callback_query
    data = query.data
    await query.answer()
    if data == 'verify_force':
        missing = await get_missing_channels(update, context)
        if missing:
            await query.answer("Join all channels first!", show_alert=True)
        else:
            await query.answer("Verified!")
            await show_main_menu(update, context)
    elif data == 'start':
        await show_main_menu(update, context)
    elif data == 'sms_bomb':
        await bomb_start(update, context, 'sms')
    elif data == 'call_bomb':
        await bomb_start(update, context, 'call')
    elif data == 'protect':
        await protect_command(update, context)
    elif data == 'stats':
        await my_stats(update, context)
    elif data == 'buy':
        await buy_command(update, context)
    elif data == 'referral':
        await referral_command(update, context)
    elif data == 'help':
        await help_command(update, context)
    elif data == 'stop_self':
        set_stop_flag(update.effective_user.id)
        await query.edit_message_text("🛑 Stop signal sent.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data='start')]]))
    elif data.startswith('stop_'):
        uid = int(data.split('_')[1])
        if uid == update.effective_user.id:
            set_stop_flag(uid)
            await query.answer("Stop sent!", show_alert=True)
    elif data.startswith('dur_'):
        await duration_callback(update, context)
    elif data.startswith('speed_'):
        await speed_callback(update, context)
    elif data.startswith('protect_'):
        await process_protect_plan(query, update.effective_user.id, data.split('_')[1], context)
    elif data.startswith('buy_'):
        await process_buy_plan(query, update.effective_user.id, data.split('_')[1], context)
    elif data.startswith('auto_protect_'):
        await auto_protect_callback(update, context)
    elif data == 'admin' and update.effective_user.id in ADMIN_IDS:
        await admin_panel(update, context)
    elif data == 'admin_stats' and update.effective_user.id in ADMIN_IDS:
        await admin_stats_cmd(update, context)
    elif data == 'admin_add' and update.effective_user.id in ADMIN_IDS:
        await admin_add_credits(update, context)
    elif data == 'admin_ban' and update.effective_user.id in ADMIN_IDS:
        await admin_ban(update, context)
    elif data == 'admin_unban' and update.effective_user.id in ADMIN_IDS:
        await admin_unban(update, context)
    elif data == 'admin_broadcast' and update.effective_user.id in ADMIN_IDS:
        await admin_broadcast(update, context)
    elif data == 'admin_verify' and update.effective_user.id in ADMIN_IDS:
        await admin_verify(update, context)
    elif data == 'admin_export' and update.effective_user.id in ADMIN_IDS:
        await admin_export_logs(update, context)
    else:
        await query.edit_message_text("Unknown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data='start')]]))

# ================= AUTO-BROADCAST SCHEDULER =================
async def auto_broadcast_inactive(app: Application):
    inactive_users = get_inactive_users(days=7)
    for uid in inactive_users:
        try:
            await app.bot.send_message(uid, "📢 *You haven't used the bomber in 7 days!*\nCome back and enjoy free bombing. Use /start to get daily bonus.", parse_mode='Markdown')
            await asyncio.sleep(0.5)
        except:
            pass
    logging.info(f"Auto-broadcast sent to {len(inactive_users)} inactive users.")

# ================= HEALTH CHECK SERVER =================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    server = HTTPServer(('0.0.0.0', PORT), HealthHandler)
    server.serve_forever()

# ================= MAIN =================
async def main():
    # Start health server for Render
    threading.Thread(target=run_health_server, daemon=True).start()
    # Start Flask dashboard in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()
    # Setup Telegram application
    application = Application.builder().token(BOT_TOKEN).build()
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stats", my_stats))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("protect", protect_command))
    application.add_handler(CommandHandler("referral", referral_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input), group=1)
    # Scheduler for auto-broadcast (every day at 10:00 AM)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(auto_broadcast_inactive, 'cron', hour=10, minute=0, args=[application])
    scheduler.start()
    # Start polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logging.info("Epic Bomber Bot started!")
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
