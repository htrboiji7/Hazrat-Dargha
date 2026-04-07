#!/usr/bin/env python3
"""
EPIC DUAL BOMBER – Webhook Version (GOD LEVEL VIP UI)
----------------------------------------------------------------
- Full Uncut Version: Admin Panel, Background Webhook, Dummy APIs
- Blockquotes, Box Drawing (├, └, ━), Monospace styling
- Premium spacing and Cyber-Terminal Dashboard look
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
from flask import Flask, request, render_template_string, redirect, url_for
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
import requests
import qrcode
from pymongo import MongoClient
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

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
ADMIN_WEB_KEY = os.getenv("ADMIN_WEB_KEY", "admin123")
PORT = int(os.environ.get("PORT", 8000))

TIME_PLANS = [(5, 10), (10, 20), (15, 30), (20, 40), (25, 50)]
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

SMS_PAYLOAD = {"mobile": None, "otp": "123456", "action": "send_otp"}
CALL_PAYLOAD = {"phone": None, "action": "initiate_call"}
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
    if users.find_one({"user_id": user_id}): return
    users.insert_one({
        "user_id": user_id, 
        "credits": 20, 
        "lifetime": False, 
        "total_bombs": 0, 
        "total_requests": 0, 
        "banned": False, 
        "joined_at": datetime.now(), 
        "last_bonus": datetime.now() - timedelta(days=1),
        "referred_by": referrer_id,
        "referral_count": 0
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
    return float('inf') if user and user.get("lifetime") else (user.get("credits", 0) if user else 0)

def add_credits(user_id, amount): users.update_one({"user_id": user_id}, {"$inc": {"credits": amount}})
def deduct_credits(user_id, amount): users.update_one({"user_id": user_id}, {"$inc": {"credits": -amount}})
def set_lifetime(user_id): users.update_one({"user_id": user_id}, {"$set": {"lifetime": True}})
def is_banned(user_id): user = users.find_one({"user_id": user_id}); return user.get("banned", False) if user else False
def ban_user(user_id): users.update_one({"user_id": user_id}, {"$set": {"banned": True}})
def unban_user(user_id): users.update_one({"user_id": user_id}, {"$set": {"banned": False}})
def is_number_protected(number): return protected.find_one({"number": number, "paid_until": {"$gt": datetime.now()}}) is not None

def protect_number(number, user_id, duration_days): 
    protected.update_one(
        {"number": number}, 
        {"$set": {"owner_id": user_id, "paid_until": datetime.now() + timedelta(days=duration_days), "protected_at": datetime.now()}}, 
        upsert=True
    )

def add_pending_payment(user_id, tx_id, amount, credits): 
    payments.insert_one({"user_id": user_id, "transaction_id": tx_id, "amount": amount, "credits": credits, "status": "pending", "timestamp": datetime.now()})

def get_pending_payment(tx_id): return payments.find_one({"transaction_id": tx_id, "status": "pending"})
def verify_payment(tx_id): payments.update_one({"transaction_id": tx_id}, {"$set": {"status": "verified"}})

def apply_daily_bonus(user_id):
    user = users.find_one({"user_id": user_id})
    if not user: return 0
    last = user.get("last_bonus")
    if not last or last.date() < datetime.now().date():
        bonus = random.randint(1, 5)
        add_credits(user_id, bonus)
        users.update_one({"user_id": user_id}, {"$set": {"last_bonus": datetime.now()}})
        return bonus
    return 0

def generate_upi_qr(upi_id, payee_name, amount, note):
    upi_url = f"upi://pay?pa={upi_id}&pn={payee_name}&am={amount}&cu=INR&tn={note}"
    qr = qrcode.make(upi_url)
    bio = BytesIO()
    qr.save(bio, 'PNG')
    bio.seek(0)
    return bio, upi_url

def can_bomb(user_id, required_credits):
    user = users.find_one({"user_id": user_id})
    if not user or user.get("banned"): return False, "🚫 <b>ACCESS DENIED:</b> You are banned."
    credits = get_user_credits(user_id)
    if credits < required_credits and not user.get("lifetime"): return False, f"⚠️ <b>INSUFFICIENT CREDITS!</b>\n\n├ <b>Required:</b> <code>{required_credits}</code>\n└ <b>Available:</b> <code>{credits}</code>\n\n<i>Please use /buy to recharge.</i>"
    return True, "OK"

def can_use_extreme_speed(user_id):
    user = users.find_one({"user_id": user_id})
    return True if user and (user.get("lifetime") or user.get("credits", 0) >= EXTREME_MIN_CREDITS) else False

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
    bomb_logs.insert_one({"user_id": user_id, "target": target, "bomb_type": bomb_type, "success": success, "failed": failed, "duration_sec": duration_sec, "speed": speed_name, "stopped": stopped, "timestamp": datetime.now()})
    users.update_one({"user_id": user_id}, {"$inc": {"total_bombs": 1, "total_requests": success+failed}})

def set_stop_flag(user_id): active_bombs.update_one({"user_id": user_id}, {"$set": {"stop": True}}, upsert=True)
def clear_stop_flag(user_id): active_bombs.delete_one({"user_id": user_id})
def is_stopped(user_id): doc = active_bombs.find_one({"user_id": user_id}); return doc.get("stop", False) if doc else False

def get_inactive_users(days=7):
    threshold = datetime.now() - timedelta(days=days)
    all_users = list(users.find({}, {"user_id": 1}))
    inactive = []
    for u in all_users:
        last_bomb = bomb_logs.find_one({"user_id": u["user_id"]}, sort=[("timestamp", -1)])
        if not last_bomb or last_bomb["timestamp"] < threshold:
            inactive.append(u["user_id"])
    return inactive

# ================= TELEGRAM HANDLERS =================
async def get_missing_channels(update, context):
    missing = []
    for ch in FORCE_CHANNELS:
        cid = ch.split('|')[0] if '|' in ch else ch
        try:
            member = await context.bot.get_chat_member(chat_id=cid, user_id=update.effective_user.id)
            if member.status not in ["member", "administrator", "creator"]: missing.append(ch)
        except: missing.append(ch)
    return missing

async def force_join_wall(update, context, missing=None):
    if missing is None: missing = await get_missing_channels(update, context)
    if not missing: return False
    
    keyboard = []
    for ch in missing:
        parts = ch.split('|')
        url = parts[1] if len(parts) > 1 else (f"https://t.me/{ch[1:]}" if ch.startswith('@') else ch)
        keyboard.append([InlineKeyboardButton("💎 Join Premium Channel", url=url)])
    keyboard.append([InlineKeyboardButton("✅ VERIFY MY STATUS", callback_data='verify_force')])
    
    text = (
        "🚫 <b>ACCESS RESTRICTED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<blockquote>To unlock this bot and receive free daily credits, you must become a member of our network.</blockquote>\n\n"
        "👇 <b>Tap the buttons below to join, then click VERIFY.</b>"
    )
    
    if update.callback_query: await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else: await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    return True

async def start(update, context):
    user_id = update.effective_user.id
    args = context.args
    ref = None
    if args and args[0].startswith("ref_"):
        try: ref = int(args[0].split("_")[1])
        except: pass

    init_user(user_id, ref)
    if is_banned(user_id): return await update.message.reply_text("🚫 <b>You are banned from using this bot.</b>", parse_mode='HTML')
    if await force_join_wall(update, context): return
    
    bonus = apply_daily_bonus(user_id)
    if bonus: await update.message.reply_text(f"🎁 <b>DAILY BONUS:</b> You received <b>+{bonus} Credits!</b>", parse_mode='HTML')
    await show_main_menu(update, context)

async def show_main_menu(update, context):
    user_id = update.effective_user.id
    credits = get_user_credits(user_id)
    
    keyboard = [
        [InlineKeyboardButton("💣 SMS BOMB", callback_data='sms_bomb'), InlineKeyboardButton("📞 CALL BOMB", callback_data='call_bomb')],
        [InlineKeyboardButton("🛡️ VIP SHIELD", callback_data='protect'), InlineKeyboardButton("📊 MY STATS", callback_data='stats')],
        [InlineKeyboardButton("💰 ADD CREDITS", callback_data='buy'), InlineKeyboardButton("🔗 REFER & EARN", callback_data='referral')],
        [InlineKeyboardButton("🛑 STOP ATTACK", callback_data='stop_self'), InlineKeyboardButton("ℹ️ HELP / INFO", callback_data='help')]
    ]
    if user_id in ADMIN_IDS: keyboard.append([InlineKeyboardButton("⚙️ ROOT ADMIN PANEL", callback_data='admin')])
    
    text = (
        "🌟 <b>E L I T E   B O M B E R   V I P</b> 🌟\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👤 <b>PROFILE INFO:</b>\n"
        f"├ <b>User ID:</b> <code>{user_id}</code>\n"
        f"└ <b>Balance:</b> 💎 <code>{credits}</code> Credits\n\n"
        "⚡ <b>RATES & PLANS:</b>\n"
        "<blockquote>"
        "• 05 Min : 10 Credits\n"
        "• 10 Min : 20 Credits\n"
        "• 15 Min : 30 Credits\n"
        "• 20 Min : 40 Credits\n"
        "• 25 Min : 50 Credits"
        "</blockquote>\n"
        "👇 <b>SELECT A MODULE:</b>"
    )
    if update.callback_query: await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
    else: await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def bomb_start(update, context, bomb_type):
    query = update.callback_query
    user_id = update.effective_user.id
    if is_banned(user_id): return await query.edit_message_text("🚫 <b>You are banned.</b>", parse_mode='HTML')
    if await force_join_wall(update, context): return
    
    context.user_data['bomb_type'] = bomb_type
    context.user_data['bomb_step'] = 'phone' 
    
    keyboard = [[InlineKeyboardButton("🔙 Cancel & Go Back", callback_data='start')]]
    text = (
        f"🎯 <b>{bomb_type.upper()} ATTACK INITIATED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<blockquote>Send the 10-digit target mobile number below without any country code.</blockquote>\n\n"
        "📱 <b>Waiting for Target Number...</b>"
    )
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update, context):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if is_banned(user_id): return
    if await force_join_wall(update, context): return

    step = context.user_data.get('bomb_step')
    
    # 1. BOMB FLOW
    if step == 'phone':
        if not re.match(r'^\d{10}$', text):
            return await update.message.reply_text("❌ <b>INVALID FORMAT:</b> Please send exactly 10 digits.", parse_mode='HTML')
        if is_number_protected(text):
            return await update.message.reply_text("🛡️ <b>SECURE SERVER:</b> This number is protected by our VIP Shield and cannot be targeted.", parse_mode='HTML')
        
        context.user_data['target'] = text
        context.user_data['bomb_step'] = 'duration'
        
        keyboard = [
            [InlineKeyboardButton("⏱️ 05 Min [10cr]", callback_data='dur_5'), InlineKeyboardButton("⏱️ 10 Min [20cr]", callback_data='dur_10')],
            [InlineKeyboardButton("⏱️ 15 Min [30cr]", callback_data='dur_15'), InlineKeyboardButton("⏱️ 20 Min [40cr]", callback_data='dur_20')],
            [InlineKeyboardButton("🔥 25 Min [50cr]", callback_data='dur_25')],
            [InlineKeyboardButton("🔙 Cancel Action", callback_data='start')]
        ]
        msg = (
            "🎯 <b>TARGET ACQUIRED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"├ <b>Target:</b> <code>+91-{text}</code>\n"
            f"└ <b>Status:</b> 🟢 <i>Vulnerable</i>\n\n"
            "⏳ <b>Select Bombing Duration:</b>"
        )
        await update.message.reply_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # 2. PAYMENT & PROTECT
    if context.user_data.get('pending_payment'):
        pending = context.user_data['pending_payment']
        add_pending_payment(user_id, text, pending['amount'], pending['credits'])
        for admin in ADMIN_IDS:
            try: await context.bot.send_message(admin, f"💸 <b>PAYMENT PENDING</b>\nUser: <code>{user_id}</code>\nTXID: <code>{text}</code>\nAmount: ₹{pending['amount']}", parse_mode='HTML')
            except: pass
        await update.message.reply_text("✅ <b>PAYMENT RECORDED!</b>\n<blockquote>Admin will verify your UTR/Txn ID shortly.</blockquote>", parse_mode='HTML')
        context.user_data.pop('pending_payment')
        return

    if context.user_data.get('action') == 'protect':
        if not re.match(r'^\d{10}$', text): return await update.message.reply_text("❌ <b>10 digits only.</b>", parse_mode='HTML')
        plan = context.user_data['protect_plan']
        if get_user_credits(user_id) < plan['cost']: return await update.message.reply_text("❌ <b>Insufficient Credits.</b>", parse_mode='HTML')
        
        deduct_credits(user_id, plan['cost'])
        protect_number(text, user_id, plan['days'] if plan['days'] else 3650)
        await update.message.reply_text(f"🛡️ <b>SHIELD ACTIVATED!</b>\nNumber <code>{text}</code> is now 100% protected.", parse_mode='HTML')
        context.user_data.clear()
        return

async def duration_callback(update, context):
    query = update.callback_query
    durations = {'dur_5': (300, 10), 'dur_10': (600, 20), 'dur_15': (900, 30), 'dur_20': (1200, 40), 'dur_25': (1500, 50)}
    if query.data not in durations: return
    
    context.user_data['duration'] = durations[query.data][0]
    context.user_data['cost'] = durations[query.data][1]
    context.user_data['bomb_step'] = 'speed'
    
    keyboard = [
        [InlineKeyboardButton("🐢 SLOW [1/s]", callback_data='speed_slow'), InlineKeyboardButton("⚡ MEDIUM [5/s]", callback_data='speed_medium')],
        [InlineKeyboardButton("🔥 FAST [20/s]", callback_data='speed_fast')],
        [InlineKeyboardButton("💀 EXTREME [100/s] (VIP)", callback_data='speed_extreme')],
        [InlineKeyboardButton("🔙 Cancel", callback_data='start')]
    ]
    msg = (
        "⚙️ <b>CONFIGURING ENGINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"├ <b>Target:</b> <code>+91-{context.user_data.get('target')}</code>\n"
        f"└ <b>Duration:</b> <code>{context.user_data['duration']//60} Mins</code>\n\n"
        "🚀 <b>Select Attack Speed:</b>\n"
        "<blockquote>Extreme mode requires 100+ Credits or Lifetime Plan to avoid server crash.</blockquote>"
    )
    await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def speed_callback(update, context):
    query = update.callback_query
    speed_map = {'speed_slow':'slow', 'speed_medium':'medium', 'speed_fast':'fast', 'speed_extreme':'extreme'}
    speed = speed_map.get(query.data)
    
    user_id = update.effective_user.id
    if speed == 'extreme' and not can_use_extreme_speed(user_id):
        return await query.answer("⚠️ Extreme speed requires 100+ credits. Choose another.", show_alert=True)
    
    phone = context.user_data.get('target')
    duration = context.user_data.get('duration')
    cost = context.user_data.get('cost')
    bomb_type = context.user_data.get('bomb_type')
    
    if not phone or not duration: return await query.edit_message_text("❌ <b>Session expired. Please use /start again.</b>", parse_mode='HTML')
    context.user_data.clear() 
    
    allowed, msg = can_bomb(user_id, cost)
    if not allowed: return await query.edit_message_text(msg, parse_mode='HTML')
    
    deduct_credits(user_id, cost)
    clear_stop_flag(user_id)
    
    msg = (
        f"☢️ <b>{bomb_type.upper()} ATTACK LAUNCHED</b> ☢️\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Target:</b> <code>{phone}</code>\n"
        f"⚙️ <b>Mode:</b> <code>{bomb_type.upper()} [{speed.upper()}]</code>\n"
        f"⏱️ <b>Time Limit:</b> <code>{duration//60} Mins</code>\n\n"
        "🟡 <i>Establishing connection to botnet servers...</i>"
    )
    status_msg = await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORT OPERATION", callback_data=f"stop_{user_id}")]]))
    asyncio.create_task(bomb_engine(user_id, phone, duration, speed, bomb_type, status_msg))

async def bomb_engine(user_id, phone, duration_sec, speed_name, bomb_type, status_msg):
    delay = SPEEDS[speed_name]
    api_list = SMS_APIS if bomb_type == "sms" else CALL_APIS
    payload_tmpl = SMS_PAYLOAD if bomb_type == "sms" else CALL_PAYLOAD
    
    success = failed = 0
    lock = threading.Lock()
    stop_req = False
    start_time = time.time()
    end_time = start_time + duration_sec

    def worker():
        nonlocal success, failed, stop_req
        while not stop_req and time.time() < end_time and not is_stopped(user_id):
            url = random.choice(api_list)
            try:
                requests.post(url, json=payload_tmpl, timeout=3)
                with lock: success += 1
            except:
                with lock: failed += 1
            time.sleep(delay)

    threads = [threading.Thread(target=worker) for _ in range(MAX_THREADS)]
    for t in threads: t.start()

    while any(t.is_alive() for t in threads):
        if is_stopped(user_id):
            stop_req = True
            break
        await asyncio.sleep(2.5)
        
        try:
            msg = (
                f"🔴 <b>{bomb_type.upper()} SERVER ACTIVE</b> 🔴\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>Target:</b> <code>+91-{phone}</code>\n"
                f"⏱️ <b>Time Left:</b> <code>{int(end_time - time.time())} sec</code>\n\n"
                "📈 <b>LIVE TERMINAL LOG:</b>\n"
                f"├ ✅ <b>Success:</b> <code>{success} Pkts</code>\n"
                f"└ ❌ <b>Failed:</b>  <code>{failed} Pkts</code>\n"
            )
            await status_msg.edit_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛑 ABORT OPERATION", callback_data=f"stop_{user_id}")]]))
        except: pass

    stop_req = True
    log_bomb(user_id, phone, bomb_type, success, failed, duration_sec, speed_name, stop_req)
    clear_stop_flag(user_id)
    
    # Auto Protect Suggestion
    count = increment_bomb_counter(user_id, phone)
    if count >= 3:
        try:
            await status_msg.reply_text(
                f"🔒 <b>SECURITY ALERT:</b> You've attacked <code>{phone}</code> {count} times.\n"
                f"<blockquote>Protect this number for 30 days using 50 credits?</blockquote>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛡️ Enable Auto-Protect", callback_data=f"auto_protect_{phone}")]])
            )
        except: pass

    msg = (
        "🏁 <b>ATTACK TERMINATED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Target:</b> <code>{phone}</code>\n"
        f"✅ <b>Total Payload Sent:</b> <code>{success}</code>\n"
        f"💎 <b>Remaining Credits:</b> <code>{get_user_credits(user_id)}</code>"
    )
    await status_msg.edit_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Return to Base", callback_data='start')]]))

# --- OTHER COMMANDS UI UPGRADES ---
async def my_stats(update, context):
    user_id = update.effective_user.id
    user = users.find_one({"user_id": user_id})
    text = (
        "📊 <b>YOUR VIP TERMINAL STATS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Account ID:</b> <code>{user_id}</code>\n"
        f"💎 <b>Current Balance:</b> <code>{get_user_credits(user_id)}</code> Cr\n\n"
        "📈 <b>LIFETIME ACTIVITY:</b>\n"
        f"├ 💣 <b>Attacks Launched:</b> <code>{user.get('total_bombs', 0)}</code>\n"
        f"└ 📨 <b>Total Packets:</b> <code>{user.get('total_requests', 0)}</code>\n"
    )
    await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='start')]]))

async def buy_command(update, context):
    keyboard = [
        [InlineKeyboardButton("💎 100 Credits [₹50]", callback_data='buy_100')],
        [InlineKeyboardButton("💎 1000 Credits [₹250]", callback_data='buy_1000')],
        [InlineKeyboardButton("🌟 LIFETIME VIP [₹899]", callback_data='buy_lifetime')],
        [InlineKeyboardButton("🔙 Main Menu", callback_data='start')]
    ]
    text = (
        "💰 <b>TOP-UP TERMINAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<blockquote>Supercharge your bot with premium credits. Select a package below:</blockquote>"
    )
    await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def process_buy_plan(query, user_id, plan_key, context):
    plans = {'100': (50,100), '1000': (250,1000), 'lifetime': (899,0)}
    amount, credits = plans[plan_key]
    qr_img, upi_url = generate_upi_qr(UPI_ID, "EpicBomber", amount, f"Credits:{credits}")
    context.user_data['pending_payment'] = {'amount': amount, 'credits': credits}
    text = (
        "💳 <b>PAYMENT GATEWAY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"├ <b>Amount:</b> <code>₹{amount}</code>\n"
        f"└ <b>Credits:</b> <code>{credits if credits else 'Lifetime'}</code>\n\n"
        "<blockquote>1. Scan the QR code below.\n2. Pay via GPay/PhonePe/Paytm.\n3. Send your 12-digit UTR/Transaction ID in this chat to verify.</blockquote>"
    )
    await query.edit_message_text(text, parse_mode='HTML')
    await query.message.reply_photo(qr_img)

async def protect_command(update, context):
    keyboard = [
        [InlineKeyboardButton("🛡️ 30 Days [50 Cr]", callback_data='protect_30'), InlineKeyboardButton("🛡️ 180 Days [250 Cr)", callback_data='protect_180')],
        [InlineKeyboardButton("🌟 LIFETIME SHIELD [1000 Cr]", callback_data='protect_lifetime')],
        [InlineKeyboardButton("🔙 Cancel", callback_data='start')]
    ]
    text = (
        "🛡️ <b>VIP NUMBER SHIELD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "<blockquote>Protect your personal number from being attacked by our botnet. Once shielded, no one can bomb you.</blockquote>"
    )
    await update.callback_query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def process_protect_plan(query, user_id, plan, context):
    plans = {'30': (50,30), '180': (250,180), 'lifetime': (1000,None)}
    cost, days = plans[plan]
    if get_user_credits(user_id) < cost: return await query.edit_message_text("❌ <b>Insufficient Credits.</b>", parse_mode='HTML')
    context.user_data['protect_plan'] = {'cost': cost, 'days': days}
    context.user_data['action'] = 'protect'
    await query.edit_message_text("📱 <b>Send the 10-digit number you want to shield:</b>", parse_mode='HTML')

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
            return await query.edit_message_text("❌ <b>Need 50 credits to protect. Use /buy</b>", parse_mode='HTML')
        
        user = users.find_one({"user_id": user_id})
        if not user.get("lifetime"): deduct_credits(user_id, cost)
        protect_number(phone, user_id, 30)
        await query.edit_message_text(f"✅ <b>SUCCESS:</b> <code>{phone}</code> is protected for 30 days!", parse_mode='HTML')

# ================= ADMIN LOGIC (FULL & UNCUT) =================
async def admin_panel(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data='admin_stats'), InlineKeyboardButton("➕ Add Credits", callback_data='admin_add')],
        [InlineKeyboardButton("🚫 Ban User", callback_data='admin_ban'), InlineKeyboardButton("✅ Unban", callback_data='admin_unban')],
        [InlineKeyboardButton("📢 Broadcast", callback_data='admin_broadcast'), InlineKeyboardButton("🔘 Verify Txn", callback_data='admin_verify')],
        [InlineKeyboardButton("📄 Export Logs", callback_data='admin_export')],
        [InlineKeyboardButton("🔙 Exit Panel", callback_data='start')]
    ]
    await query.edit_message_text("⚙️ <b>ROOT ACCESS TERMINAL</b>\n━━━━━━━━━━━━━━━━━━━━", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_stats_cmd(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    query = update.callback_query
    total_users = users.count_documents({})
    total_bombs = bomb_logs.count_documents({})
    total_req = bomb_logs.aggregate([{"$group": {"_id": None, "sum": {"$sum": "$success"}}}])
    total_req = list(total_req)[0]['sum'] if total_req else 0
    await query.edit_message_text(f"📊 <b>SYSTEM STATS</b>\n├ Users: <code>{total_users}</code>\n├ Bombs: <code>{total_bombs}</code>\n└ OTPs: <code>{total_req}</code>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin", callback_data='admin')]]))

async def admin_add_credits(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    context.user_data['admin_action'] = 'add'
    await update.callback_query.edit_message_text("Send: <code>user_id amount</code>", parse_mode='HTML')

async def admin_ban(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    context.user_data['admin_action'] = 'ban'
    await update.callback_query.edit_message_text("Send user_id to ban")

async def admin_unban(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    context.user_data['admin_action'] = 'unban'
    await update.callback_query.edit_message_text("Send user_id to unban")

async def admin_broadcast(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    context.user_data['admin_action'] = 'broadcast'
    await update.callback_query.edit_message_text("Send broadcast message")

async def admin_verify(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
    context.user_data['admin_action'] = 'verify'
    await update.callback_query.edit_message_text("Send: <code>user_id transaction_id</code>", parse_mode='HTML')

async def admin_export_logs(update, context):
    if update.effective_user.id not in ADMIN_IDS: return
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
    if user_id not in ADMIN_IDS: return
    text = update.message.text.strip()
    action = context.user_data.get('admin_action')
    
    if action == 'add':
        parts = text.split()
        if len(parts) == 2:
            uid, amt = int(parts[0]), int(parts[1])
            add_credits(uid, amt)
            await update.message.reply_text(f"✅ Added {amt} to {uid}")
            try: await context.bot.send_message(uid, f"🎉 <b>{amt} credits added by admin!</b>", parse_mode='HTML')
            except: pass
        else: await update.message.reply_text("Invalid format")
        context.user_data.pop('admin_action')
        
    elif action == 'ban':
        try:
            uid = int(text)
            ban_user(uid)
            await update.message.reply_text(f"Banned {uid}")
        except: await update.message.reply_text("Invalid ID")
        context.user_data.pop('admin_action')
        
    elif action == 'unban':
        try:
            uid = int(text)
            unban_user(uid)
            await update.message.reply_text(f"Unbanned {uid}")
        except: await update.message.reply_text("Invalid ID")
        context.user_data.pop('admin_action')
        
    elif action == 'broadcast':
        msg = text
        all_users = [u['user_id'] for u in users.find({}, {'user_id': 1})]
        sent = 0
        for uid in all_users:
            try:
                await context.bot.send_message(uid, f"📢 <b>BROADCAST</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{msg}", parse_mode='HTML')
                sent += 1
                await asyncio.sleep(0.05)
            except: pass
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
                    try: await context.bot.send_message(uid, "🌟 <b>Lifetime access granted!</b>", parse_mode='HTML')
                    except: pass
                else:
                    add_credits(uid, payment['credits'])
                    await update.message.reply_text(f"Added {payment['credits']} credits to {uid}")
                    try: await context.bot.send_message(uid, f"✅ <b>Payment verified! +{payment['credits']} credits</b>", parse_mode='HTML')
                    except: pass
            else: await update.message.reply_text("Payment not found or mismatch")
        else: await update.message.reply_text("Invalid format")
        context.user_data.pop('admin_action')

# ================= BUTTON CALLBACK HUB =================
async def button_callback(update, context):
    query = update.callback_query
    data = query.data

    if data == 'verify_force':
        missing = await get_missing_channels(update, context)
        if missing: await query.answer("🚫 You must join all channels first!", show_alert=True)
        else:
            await query.answer("✅ Verification Successful! Access Granted.", show_alert=True)
            await show_main_menu(update, context)
        return

    await query.answer() 
    
    if data == 'start': await show_main_menu(update, context)
    elif data == 'sms_bomb': await bomb_start(update, context, 'sms')
    elif data == 'call_bomb': await bomb_start(update, context, 'call')
    elif data == 'stats': await my_stats(update, context)
    elif data == 'buy': await buy_command(update, context)
    elif data == 'protect': await protect_command(update, context)
    elif data.startswith('dur_'): await duration_callback(update, context)
    elif data.startswith('speed_'): await speed_callback(update, context)
    elif data.startswith('buy_'): await process_buy_plan(query, update.effective_user.id, data.split('_')[1], context)
    elif data.startswith('protect_'): await process_protect_plan(query, update.effective_user.id, data.split('_')[1], context)
    elif data.startswith('auto_protect_'): await auto_protect_callback(update, context)
    elif data == 'stop_self':
        set_stop_flag(update.effective_user.id)
        await query.edit_message_text("🛑 <b>ABORT SIGNAL SENT</b>\n<blockquote>Terminating all active processes...</blockquote>", parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data='start')]]))
    elif data.startswith('stop_'):
        uid = int(data.split('_')[1])
        if uid == update.effective_user.id:
            set_stop_flag(uid)
            await query.answer("Stopping Attack... Please wait a few seconds.", show_alert=True)
    elif data == 'help':
        msg = (
            "ℹ️ <b>SUPPORT TERMINAL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<blockquote>If you face any issues with payments, bombing stuck, or need custom scripts, contact the Administrator.</blockquote>"
        )
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='start')]]))
    elif data == 'referral':
        msg = (
            "🔗 <b>REFER & EARN SYSTEM</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "<blockquote>Share your unique link below. You and your friend both will receive <b>free credits</b> when they join!</blockquote>\n\n"
            f"👉 <b>Your Link:</b>\n<code>https://t.me/{BOT_USERNAME}?start=ref_{update.effective_user.id}</code>"
        )
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='start')]]))
    
    # Admin Callbacks
    elif data == 'admin' and update.effective_user.id in ADMIN_IDS: await admin_panel(update, context)
    elif data == 'admin_stats' and update.effective_user.id in ADMIN_IDS: await admin_stats_cmd(update, context)
    elif data == 'admin_add' and update.effective_user.id in ADMIN_IDS: await admin_add_credits(update, context)
    elif data == 'admin_ban' and update.effective_user.id in ADMIN_IDS: await admin_ban(update, context)
    elif data == 'admin_unban' and update.effective_user.id in ADMIN_IDS: await admin_unban(update, context)
    elif data == 'admin_broadcast' and update.effective_user.id in ADMIN_IDS: await admin_broadcast(update, context)
    elif data == 'admin_verify' and update.effective_user.id in ADMIN_IDS: await admin_verify(update, context)
    elif data == 'admin_export' and update.effective_user.id in ADMIN_IDS: await admin_export_logs(update, context)

# ================= BACKGROUND SCHEDULER =================
async def auto_broadcast_inactive(app: Application):
    inactive_users = get_inactive_users(days=7)
    for uid in inactive_users:
        try:
            await app.bot.send_message(uid, "📢 <b>SYSTEM NOTICE</b>\n━━━━━━━━━━━━━━━━━━━━\n\nYou haven't used the bomber in 7 days!\nCome back and claim your free daily login bonus.", parse_mode='HTML')
            await asyncio.sleep(0.5)
        except: pass
    logging.info(f"Auto-broadcast sent to {len(inactive_users)} inactive users.")

# ================= SERVER ARCHITECTURE =================
app_flask = Flask(__name__)
telegram_app = None
loop = None

@app_flask.route('/webhook', methods=['POST'])
def webhook():
    if telegram_app is None: return "Application not ready", 500
    try:
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        asyncio.run_coroutine_threadsafe(telegram_app.process_update(update), loop)
        return "OK", 200
    except: return "Error", 500

@app_flask.route('/')
def dashboard():
    if request.args.get('admin_key') != ADMIN_WEB_KEY: return "Unauthorized", 401
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
    ''', total_users=total_users, total_bombs=total_bombs, total_requests=total_requests, active_bombs=active_bombs_count, logs=recent_logs)

@app_flask.route('/add_credits', methods=['POST'])
def add_credits_web():
    if request.args.get('admin_key') != ADMIN_WEB_KEY: return "Unauthorized", 401
    add_credits(int(request.form['user_id']), int(request.form['amount']))
    return redirect(url_for('dashboard', admin_key=ADMIN_WEB_KEY))

@app_flask.route('/ban', methods=['POST'])
def ban_web():
    if request.args.get('admin_key') != ADMIN_WEB_KEY: return "Unauthorized", 401
    ban_user(int(request.form['user_id']))
    return redirect(url_for('dashboard', admin_key=ADMIN_WEB_KEY))

@app_flask.route('/unban', methods=['POST'])
def unban_web():
    if request.args.get('admin_key') != ADMIN_WEB_KEY: return "Unauthorized", 401
    unban_user(int(request.form['user_id']))
    return redirect(url_for('dashboard', admin_key=ADMIN_WEB_KEY))

def set_webhook():
    host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    if host:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": f"https://{host}/webhook", "drop_pending_updates": True})

def start_asyncio_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.new_event_loop()
    
    telegram_app = Application.builder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("stop", stop_command))
    telegram_app.add_handler(CommandHandler("stats", my_stats))
    telegram_app.add_handler(CommandHandler("buy", buy_command))
    telegram_app.add_handler(CommandHandler("protect", protect_command))
    telegram_app.add_handler(CommandHandler("referral", referral_command))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input), group=1)
    
    loop.run_until_complete(telegram_app.initialize())
    loop.run_until_complete(telegram_app.start())
    set_webhook()
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(auto_broadcast_inactive(telegram_app), loop), 'cron', hour=10, minute=0)
    scheduler.start()
    
    threading.Thread(target=start_asyncio_loop, args=(loop,), daemon=True).start()
    app_flask.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
