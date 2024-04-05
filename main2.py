import logging
import os
import time
import json
import re
import asyncio
from pymongo import MongoClient
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

API_ID = int(os.getenv("TG_API_ID", "13216322"))
API_HASH = os.getenv("TG_API_HASH", "15e5e632a8a0e52251ac8c3ccbe462c7")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7079929259:AAEC6jQzSzAPolYhL4nwExldNlIKf4sRcjU")
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb+srv://user654321:user123456@cluster0.c4f70nh.mongodb.net/")
BOT_USERNAME = None

bot = Client('bot', api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo_client = MongoClient(MONGODB_URL)
download_folder = 'files'
database = mongo_client.userdb.sessions

if not os.path.isdir(download_folder):
    os.makedirs(download_folder)

numpad = [
    [
        InlineKeyboardButton("1", callback_data='{"press":1}'),
        InlineKeyboardButton("2", callback_data='{"press":2}'),
        InlineKeyboardButton("3", callback_data='{"press":3}')
    ],
    [
        InlineKeyboardButton("4", callback_data='{"press":4}'),
        InlineKeyboardButton("5", callback_data='{"press":5}'),
        InlineKeyboardButton("6", callback_data='{"press":6}')
    ],
    [
        InlineKeyboardButton("7", callback_data='{"press":7}'),
        InlineKeyboardButton("8", callback_data='{"press":8}'),
        InlineKeyboardButton("9", callback_data='{"press":9}')
    ],
    [
        InlineKeyboardButton("Clear All", callback_data='{"press":"clear_all"}'),
        InlineKeyboardButton("0", callback_data='{"press":0}'),
        InlineKeyboardButton("⌫", callback_data='{"press":"clear"}')
    ]
]

settings_keyboard = [
    [
        InlineKeyboardButton("Download command", callback_data='{"page":"settings","press":"dlcmd"}')
    ],
    [
        InlineKeyboardButton("Download message", callback_data='{"page":"settings","press":"dlmsg"}')
    ],
    [
        InlineKeyboardButton("Info delete delay", callback_data='{"page":"settings","press":"dltime"}')
    ],
]

def select_not_none(l):
    for i in l:
        if i is not None:
            return i

def intify(s):
    try:
        return int(s)
    except:
        return s

def get(obj, key, default=None):
    try:
        return obj[key]
    except:
        return default

def yesno(x, page='def'):
    return [
        [InlineKeyboardButton("Yes", callback_data='{{"page":"{}","press":"yes{}"}}'.format(page, x))],
        [InlineKeyboardButton("No", callback_data='{{"page":"{}","press":"no{}"}}'.format(page, x))]
    ]

@bot.on_callback_query()
async def callback_handler(bot, update):
    query = update.data
    evnt_dta = json.loads(query)
    if get(evnt_dta, 'page', '') == 'settings':
        await handle_settings(update, evnt_dta)
        return
    press = evnt_dta['press']
    user_data = database.find_one({"chat_id": update.message.chat.id})
    login = json.loads(user_data['login'])
    login['code'] = get(login, 'code', '')
    if type(press)==int:
        login['code'] += str(press)
    elif press=="clear":
        login['code'] = login['code'][:-1]
    elif press=="clear_all" or press=="nocode":
        login['code'] = ''
        login['code_ok'] = False
    elif press=="yescode":
        login['code_ok'] = True
    elif press=="yespass":
        login['pass_ok'] = True
        login['need_pass'] = False
    elif press=="nopass":
        login['pass_ok'] = False
        login['need_pass'] = True
        await update.message.edit_text(strings['ask_pass'])
    elif press=="yeslogout":
        data = {
            'logged_in': False,
            'login': '{}',
        }
        database.update_one({'_id': user_data['_id']}, {'$set': data})
        await update.message.edit_text(strings['logged_out'])
        return
    elif press=="nologout":
        await update.message.edit_text(strings['not_logged_out'])
        return
    database.update_one({'_id': user_data['_id']}, {'$set': {'login': json.dumps(login)}})
    if len(login['code'])==login['code_len'] and not get(login, 'code_ok', False):
        await update.message.edit_text(strings['ask_ok']+login['code'], reply_markup=InlineKeyboardMarkup(yesno('code')))
    elif press=="nopass":
        return
    elif not await sign_in(update):
        await update.message.edit_text(strings['ask_code']+login['code'], reply_markup=InlineKeyboardMarkup(numpad))

@bot.on_message(filters.command("activate") & filters.private)
async def activate_handler(bot, update):
    user_data = database.find_one({"chat_id": update.message.chat.id})
    if not get(user_data, 'logged_in', False) or user_data['session'] is None:
        await update.message.reply_text(strings['need_login'])
        return
    if get(user_data, 'activated', False):
        await update.message.reply_text(strings['already_activated'])
        return
    database.update_one({'_id': user_data['_id']}, {'$set': {'activated': True}})
    settings = get(user_data, 'settings', {})
    log = await update.message.reply_text(strings['timeout_start'].format(get(settings, 'dl_command', '/dl')))
    await asyncio.sleep(60)
    database.update_one({'_id': user_data['_id']}, {'$set': {'activated': False}})
    await log.edit_text(strings['timed_out'])

@bot.on_message(filters.private)
async def private_message_handler(bot, update):
    user_data = database.find_one({"chat_id": update.message.chat.id})
    if user_data is None:
        database.insert_one({
            "chat_id": update.message.chat.id,
            "first_name": update.message.chat.first_name,
            "last_name": update.message.chat.last_name,
            "username": update.message.chat.username,
        })
    if update.message.text in direct_reply:
        await update.message.reply_text(direct_reply[update.message.text])
        return
    if update.message.contact:
        if update.message.contact.user_id==update.message.chat.id:
            await handle_usr(update.message.contact, update)
        else:
            await update.message.reply_text(strings['wrong_phone'])
        return
    if update.message.text == "/login":
        if get(user_data, 'logged_in', False):
            await update.message.reply_text(strings['already_logged_in'])
            return
        await update.message.reply_text(strings['ask_phone'], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("SHARE CONTACT", request_contact=True, resize=True, single_use=True)]]))
        return
    if update.message.text == "/settings":
        await update.message.reply_text(strings['settings_home'], reply_markup=InlineKeyboardMarkup(settings_keyboard))
        return
    if update.message.text == "/logout":
        if not get(user_data, 'logged_in', False):
            await update.message.reply_text(strings['need_login'])
            return
        await update.message.reply_text(strings['logout_sure'], reply_markup=InlineKeyboardMarkup(yesno('logout')))
        return
    if update.message.text.startswith("/add_session"):
        args = update.message.text.split(' ', 1)
        if len(args) == 1:
            return
        msg = await update.message.reply_text(strings['checking_str_session'])
        user_data = database.find_one({"chat_id": update.message.chat.id})
        data = {
            'session': args[1],
            'logged_in': True
        }
        uclient = Client(session_name=user_data['session'], api_id=API_ID, api_hash=API_HASH)
        await uclient.connect()
        if not await uclient.is_user_authorized():
            await msg.edit_text(strings['session_invalid'])
            await uclient.disconnect()
            return
        await msg.edit_text(strings['str_session_ok'])
        database.update_one({'_id': user_data['_id']}, {'$set': data})
        return

# Add the rest of the code here...
print("Botstarted")
bot.run()
