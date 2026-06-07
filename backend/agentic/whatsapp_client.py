import os
import json
import requests


_whatsapp_api_url = os.environ.get("WHATSAPP_API_URL", "http://localhost:9110")
_whatsapp_api_token = os.environ.get("WHATSAPP_API_TOKEN", "")
_admin_phone = os.environ.get("WHATSAPP_ADMIN_PHONE", "")
_webhook_base = os.environ.get("MARIA_WEBHOOK_BASE_URL", "http://localhost:10001")
_call_timeout = int(os.environ.get("WHATSAPP_TIMEOUT", "15"))


def _auth_headers():
    return {
        "Authorization": f"Bearer {_whatsapp_api_token}",
        "Content-Type": "application/json",
    }


def is_configured() -> bool:
    return bool(_whatsapp_api_token and _admin_phone)


def send_text(to: str, message: str) -> dict:
    if not is_configured():
        return {"success": False, "error": "WhatsApp not configured"}
    try:
        r = requests.post(
            f"{_whatsapp_api_url}/whatsapp_api/send-text",
            json={"to": to, "message": message},
            headers=_auth_headers(),
            timeout=_call_timeout,
        )
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_media(to: str, message: str, media_url: str) -> dict:
    if not is_configured():
        return {"success": False, "error": "WhatsApp not configured"}
    try:
        r = requests.post(
            f"{_whatsapp_api_url}/whatsapp_api/send-media",
            json={"to": to, "message": message, "mediaUrl": media_url},
            headers=_auth_headers(),
            timeout=_call_timeout,
        )
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_ask(to: str, question: str, options: list, task_id: str = None) -> dict:
    if not is_configured():
        return {"success": False, "error": "WhatsApp not configured"}
    callback_url = f"{_webhook_base}/api/webhooks/whatsapp"
    if task_id:
        callback_url += f"?task_id={task_id}"
    try:
        r = requests.post(
            f"{_whatsapp_api_url}/whatsapp_api/send-ask",
            json={
                "to": to,
                "question": question,
                "options": options,
                "callbackUrl": callback_url,
            },
            headers=_auth_headers(),
            timeout=_call_timeout,
        )
        return r.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_admin_text(message: str) -> dict:
    return send_text(_admin_phone, message)


def send_admin_ask(question: str, options: list, task_id: str = None) -> dict:
    return send_ask(_admin_phone, question, options, task_id=task_id)


def send_admin_alert(subject: str, body: str, task_id: str = None) -> dict:
    message = f"*{subject}*\n\n{body}"
    if task_id:
        message += f"\n\nTask: `{task_id}`"
    return send_admin_text(message)


def health_check() -> dict:
    if not _whatsapp_api_token:
        return {"status": "not_configured"}
    try:
        r = requests.get(
            f"{_whatsapp_api_url}/health",
            headers=_auth_headers(),
            timeout=_call_timeout,
        )
        return r.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}
