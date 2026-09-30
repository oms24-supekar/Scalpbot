import os
import threading
import time
import uuid

import requests
from dotenv import load_dotenv


load_dotenv("/opt/scalpbot/.env")


class TelegramControl:
    def __init__(
        self,
        status_provider=None,
        kill_callback=None,
        resume_callback=None,
    ):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = str(
            os.getenv("TELEGRAM_CHAT_ID", "")
        ).strip()

        if not self.token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN missing.")

        if not self.chat_id:
            raise RuntimeError("TELEGRAM_CHAT_ID missing.")

        self.base_url = (
            f"https://api.telegram.org/bot{self.token}"
        )

        self.status_provider = status_provider
        self.kill_callback = kill_callback
        self.resume_callback = resume_callback

        self._offset = None
        self._running = False
        self._thread = None
        self._pending = {}
        self._pending_lock = threading.Lock()

    def _request(self, method, endpoint, **kwargs):
        response = requests.request(
            method=method,
            url=f"{self.base_url}/{endpoint}",
            timeout=30,
            **kwargs,
        )

        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(
                f"Telegram API error: {data}"
            )

        return data

    def send(self, text, reply_markup=None):
        payload = {
            "chat_id": self.chat_id,
            "text": str(text),
        }

        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            return self._request(
                "POST",
                "sendMessage",
                json=payload,
            )
        except Exception as error:
            print(
                f"⚠️ Telegram send failed: {error}"
            )
            return None

    def notify(self, text):
        self.send(text)

    def set_handlers(
        self,
        status_provider=None,
        kill_callback=None,
        resume_callback=None,
    ):
        if status_provider is not None:
            self.status_provider = status_provider

        if kill_callback is not None:
            self.kill_callback = kill_callback

        if resume_callback is not None:
            self.resume_callback = resume_callback

    def _authorized_chat(self, chat_id):
        return str(chat_id) == self.chat_id

    def _handle_message(self, message):
        incoming_chat_id = (
            message.get("chat", {}).get("id")
        )

        if not self._authorized_chat(incoming_chat_id):
            return

        text = (message.get("text") or "").strip()
        command = (
            text.split()[0].lower()
            if text
            else ""
        )

        if command in ("/start", "/help"):
            self.send(
                "🤖 ScalpBot Control\n\n"
                "/status - bot/exchange status\n"
                "/kill - block NEW entries\n"
                "/resume - allow entries again\n\n"
                "/kill does not close an existing trade."
            )
            return

        if command == "/status":
            if self.status_provider is None:
                self.send("⚠️ Status provider not ready.")
                return

            try:
                self.send(self.status_provider())
            except Exception as error:
                self.send(
                    f"🚨 Status check failed:\n{error}"
                )
            return

        if command == "/kill":
            if self.kill_callback is None:
                self.send("⚠️ Kill handler not ready.")
                return

            try:
                self.kill_callback()
                self.send(
                    "🛑 KILL SWITCH ON\n"
                    "New entries are blocked.\n"
                    "Existing position management continues."
                )
            except Exception as error:
                self.send(
                    f"🚨 Kill switch failed:\n{error}"
                )
            return

        if command == "/resume":
            if self.resume_callback is None:
                self.send("⚠️ Resume handler not ready.")
                return

            try:
                self.resume_callback()
                self.send(
                    "✅ KILL SWITCH OFF\n"
                    "New entries may resume if all other "
                    "safety checks pass."
                )
            except Exception as error:
                self.send(
                    f"🚨 Resume failed:\n{error}"
                )

    def request_trade_confirmation(
        self,
        summary,
        timeout_seconds=120,
    ):
        token = uuid.uuid4().hex[:10]
        event = threading.Event()

        with self._pending_lock:
            self._pending[token] = {
                "event": event,
                "decision": None,
            }

        keyboard = {
            "inline_keyboard": [[
                {
                    "text": "✅ CONFIRM",
                    "callback_data": (
                        f"trade_confirm:{token}"
                    ),
                },
                {
                    "text": "❌ REJECT",
                    "callback_data": (
                        f"trade_reject:{token}"
                    ),
                },
            ]]
        }

        sent = self.send(
            "⚡ LIVE TRADE CONFIRMATION\n\n"
            f"{summary}\n\n"
            "Tap a button below — no typing needed.\n"
            f"Expires in {timeout_seconds}s.",
            reply_markup=keyboard,
        )

        if sent is None:
            with self._pending_lock:
                self._pending.pop(token, None)
            return False

        event.wait(timeout_seconds)

        with self._pending_lock:
            result = self._pending.pop(
                token,
                None,
            )

        if not result:
            return False

        decision = result.get("decision")

        if decision is True:
            self.send("✅ Trade confirmed.")
            return True

        if decision is False:
            self.send("❌ Trade rejected.")
            return False

        self.send(
            "⌛ Trade confirmation timed out. "
            "Signal skipped."
        )
        return False

    def _remove_inline_keyboard(
        self,
        callback,
    ):
        message = callback.get(
            "message",
            {},
        )

        chat_id = (
            message.get("chat", {})
            .get("id")
        )

        message_id = message.get(
            "message_id"
        )

        if (
            chat_id is None
            or message_id is None
        ):
            return

        try:
            self._request(
                "POST",
                "editMessageReplyMarkup",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reply_markup": {
                        "inline_keyboard": []
                    },
                },
            )
        except Exception:
            pass

    def _answer_callback(
        self,
        callback_query_id,
        text,
    ):
        try:
            self._request(
                "POST",
                "answerCallbackQuery",
                json={
                    "callback_query_id": callback_query_id,
                    "text": text,
                },
            )
        except Exception:
            pass

    def _handle_callback(self, callback):
        chat_id = (
            callback.get("message", {})
            .get("chat", {})
            .get("id")
        )

        callback_id = callback.get("id")

        if not self._authorized_chat(chat_id):
            self._answer_callback(
                callback_id,
                "Unauthorized",
            )
            return

        data = callback.get("data") or ""

        if ":" not in data:
            return

        action, token = data.split(":", 1)

        with self._pending_lock:
            pending = self._pending.get(token)

            if pending is None:
                self._answer_callback(
                    callback_id,
                    "Expired",
                )
                return

            if action == "trade_confirm":
                pending["decision"] = True
                pending["event"].set()
                self._answer_callback(
                    callback_id,
                    "Confirmed",
                )
                self._remove_inline_keyboard(
                    callback
                )

            elif action == "trade_reject":
                pending["decision"] = False
                pending["event"].set()
                self._answer_callback(
                    callback_id,
                    "Rejected",
                )
                self._remove_inline_keyboard(
                    callback
                )

    def _poll_once(self):
        params = {"timeout": 25}

        if self._offset is not None:
            params["offset"] = self._offset

        data = self._request(
            "GET",
            "getUpdates",
            params=params,
        )

        for update in data.get("result", []):
            update_id = update.get("update_id")

            if update_id is not None:
                self._offset = int(update_id) + 1

            if "message" in update:
                self._handle_message(
                    update["message"]
                )

            if "callback_query" in update:
                self._handle_callback(
                    update["callback_query"]
                )

    def _poll_loop(self):
        while self._running:
            try:
                self._poll_once()
            except Exception as error:
                print(
                    f"⚠️ Telegram polling error: {error}"
                )
                time.sleep(3)

    def start(self):
        if self._running:
            return

        try:
            self._request(
                "POST",
                "deleteWebhook",
                json={"drop_pending_updates": False},
            )
        except Exception:
            pass

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="telegram-control",
            daemon=True,
        )
        self._thread.start()

        print("✅ Telegram control started")

    def stop(self):
        self._running = False
