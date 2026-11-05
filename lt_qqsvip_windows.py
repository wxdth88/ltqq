#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
联通十周年「充值享会员」抢 QQ超级会员 —— Windows 桌面版（含内置登录）
=====================================================================
功能：
  1. 内置浏览器登录：手机号 + 短信验证码 + 滑块，登录后【自动获取 Cookie】
     —— 无需再手动抓包复制 Cookie
  2. 每天到点(默认 10:00:00)自动「锁单」，秒级抢 QQ超级会员名额
  3. 锁单成功后弹窗 + 响铃提醒 → 你自己在手机上完成充值

目标档位：QQ超级会员 · 充300送一年 (giftCode 26101311)

依赖：  pip install requests pywebview
打包：  pyinstaller -F -w --name 联通抢会员 lt_qqsvip_windows.py
说明：  登录那一下需要你手动拖滑块 + 输短信验证码（联通强制人机验证，无法自动化）
"""

import json
import os
import sys
import time
import threading
import datetime
import webbrowser
import subprocess
import requests
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

API_BASE = "https://kapi.10010.com/app-charge353-activity/kcard-10th-anniversary"
PAGE = "https://txwk.10010.com/kcard-h5/thay/tenth-anniversary/tenth-anniversary-recharge.html#/"
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "config.json")

STATUS = {1: "未开始", 2: "已结束", 3: "未登录", 4: "无资格",
          5: "未充值", 6: "充值中", 7: "已成功", 8: "已锁定"}

# 登录态需要的 cookie（会全部保留，这里只是打日志用）
NEED_COOKIES = ["KSESSIONID", "TDC_itoken", "acw_tc", "sensorsdata2015jssdkcross"]


# ---------------- 可选依赖 ----------------
try:
    import webview
    HAS_WEBVIEW = True
except Exception:
    HAS_WEBVIEW = False


# ---------------- 接口 ----------------
def _headers(cookie):
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://txwk.10010.com",
        "Referer": "https://txwk.10010.com/",
        "User-Agent": UA,
        "Cookie": cookie.strip(),
    }


def api_query(cookie):
    r = requests.post(f"{API_BASE}/query", data="{}",
                      headers=_headers(cookie), timeout=10)
    return r.json()


def api_charge_pre(cookie, gift_code):
    r = requests.post(f"{API_BASE}/chargePre", data=f"giftCode={gift_code}",
                      headers=_headers(cookie), timeout=10)
    return r.json()


def pick_qq_gift(data):
    gifts = data.get("giftInfos") or []
    qq = [g for g in gifts if "QQ超级会员" in (g.get("giftName") or "")]
    if not qq:
        qq = [g for g in gifts if (g.get("giftCode") or "") == "26101311"]
    if not qq:
        return None
    qq.sort(key=lambda g: (int(g.get("month") or 0), int(g.get("payamount") or 0)),
            reverse=True)
    return qq[0]


def build_cookie(cookies):
    """把 pywebview 返回的 cookie 列表拼成 Cookie 头"""
    parts = []
    for c in cookies:
        name = value = None
        if isinstance(c, dict):
            name = c.get("name") or c.get("Name")
            value = c.get("value") or c.get("Value")
        else:
            name = getattr(c, "name", None)
            value = getattr(c, "value", None)
        if name and value is not None:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


# ---------------- 主程序 ----------------
class App:
    def __init__(self, root):
        self.root = root
        root.title("联通十周年 - 抢QQ超级会员")
        root.geometry("640x700")
        self.running = False
        self._build_ui()
        self._load_config()
        self.log("提示：首次使用请点「登录」获取 Cookie，之后每天到点自动抢")

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}
        frm = ttk.Frame(self.root); frm.pack(fill="both", expand=True, **pad)

        ttk.Label(frm, text="Cookie（点击「登录」自动获取，一般无需手动粘贴）").pack(anchor="w")
        self.cookie_text = tk.Text(frm, height=3, wrap="char")
        self.cookie_text.pack(fill="x")

        cfg = ttk.Frame(frm); cfg.pack(fill="x", pady=6)
        ttk.Label(cfg, text="giftCode:").grid(row=0, column=0, sticky="e")
        self.gift_var = tk.StringVar(value="26101311")
        ttk.Entry(cfg, textvariable=self.gift_var, width=16).grid(row=0, column=1, padx=4)
        ttk.Label(cfg, text="抢购时间:").grid(row=0, column=2, sticky="e", padx=(14, 0))
        self.time_var = tk.StringVar(value="10:00:00")
        ttk.Entry(cfg, textvariable=self.time_var, width=10).grid(row=0, column=3, padx=4)
        ttk.Label(cfg, text="提前量ms:").grid(row=0, column=4, sticky="e", padx=(14, 0))
        self.offset_var = tk.StringVar(value="0")
        ttk.Entry(cfg, textvariable=self.offset_var, width=6).grid(row=0, column=5, padx=4)

        btns = ttk.Frame(frm); btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="📱 登录", command=self.login).pack(side="left", padx=3)
        ttk.Button(btns, text="① 测试登录", command=self.test_login).pack(side="left", padx=3)
        ttk.Button(btns, text="② 立即抢", command=self.grab_now).pack(side="left", padx=3)
        ttk.Button(btns, text="③ 开始每日自动抢", command=self.start_schedule).pack(side="left", padx=3)
        ttk.Button(btns, text="停止", command=self.stop_schedule).pack(side="left", padx=3)
        ttk.Button(btns, text="保存", command=self._save_config).pack(side="left", padx=3)
        ttk.Button(btns, text="打开活动页", command=lambda: webbrowser.open(PAGE)).pack(side="left", padx=3)

        ttk.Label(frm, text="运行日志").pack(anchor="w")
        self.log_text = scrolledtext.ScrolledText(frm, height=20, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="未启动定时任务")
        ttk.Label(frm, textvariable=self.status_var, foreground="#333").pack(anchor="w", pady=3)

    def log(self, msg):
        def _w():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _w)

    def _set_status(self, msg):
        self.root.after(0, lambda: self.status_var.set(msg))

    # ---------- 配置 ----------
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                c = json.load(open(CONFIG_FILE, encoding="utf-8"))
                self.cookie_text.delete("1.0", "end")
                self.cookie_text.insert("1.0", c.get("cookie", ""))
                self.gift_var.set(c.get("gift_code", "26101311"))
                self.time_var.set(c.get("time", "10:00:00"))
                self.offset_var.set(str(c.get("offset_ms", 0)))
                self.log("已加载上次保存的配置")
            except Exception:
                pass

    def _save_config(self):
        try:
            c = {
                "cookie": self.cookie_text.get("1.0", "end").strip(),
                "gift_code": self.gift_var.get().strip(),
                "time": self.time_var.get().strip(),
                "offset_ms": int(self.offset_var.get().strip() or 0),
            }
            json.dump(c, open(CONFIG_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            self.log("配置已保存到 config.json")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")

    def _get_cookie(self):
        return self.cookie_text.get("1.0", "end").strip()

    # ---------- 登录（内置浏览器）----------
    def login(self):
        if not HAS_WEBVIEW:
            messagebox.showwarning(
                "缺少组件",
                "未安装 pywebview。请在命令行执行：\n\n    pip install pywebview\n\n"
                "或手动粘贴 Cookie 到上方输入框（可从手机上抓包获取）。")
            return
        threading.Thread(target=self._do_login, daemon=True).start()

    def _do_login(self):
        self.log("📱 已打开内置浏览器登录窗口…")
        self.log("请在窗口里：点「请登录」→ 拖滑块 → 输手机号+短信验证码 → 登录")
        result = {"cookie": None, "err": None}

        def complete_login_js():
            """用户在登录窗口点「✅ 完成登录」后调用：读 cookie 并关窗"""
            try:
                wins = webview.windows
                if not wins:
                    result["err"] = "无窗口"
                    return
                cookies = wins[0].get_cookies()
                cookie = build_cookie(cookies)
                if not cookie or "KSESSIONID" not in cookie:
                    result["err"] = "未读到登录 Cookie，请确认已登录成功"
                else:
                    result["cookie"] = cookie
                wins[0].destroy()
            except Exception as e:
                result["err"] = f"读取 Cookie 失败：{e}"

        # 暴露给 JS
        class Api:
            def complete_login(self):
                complete_login_js()

        window = webview.create_window(
            "联通登录（登录后点右下角「✅ 完成登录」）",
            PAGE,
            width=420, height=800,
            on_top=True,
            js_api=Api(),
        )

        def inject_btn():
            js = """
            (function(){
              if(document.getElementById('minis_done'))return;
              var b=document.createElement('button');
              b.id='minis_done';
              b.innerText='✅ 完成登录';
              b.style.cssText='position:fixed;right:12px;bottom:24px;z-index:999999;'
                +'padding:12px 18px;background:#e60012;color:#fff;border:none;'
                +'border-radius:24px;font-size:15px;font-weight:bold;'
                +'box-shadow:0 2px 10px rgba(0,0,0,.35)';
              b.onclick=function(){
                if(window.pywebview && window.pywebview.api){
                  window.pywebview.api.complete_login();
                }else{
                  alert('接口未就绪，请稍后再点');
                }
              };
              document.body.appendChild(b);
            })();
            """
            try:
                window.evaluate_js(js)
            except Exception:
                pass

        def loaded():
            inject_btn()

        window.events.loaded += loaded
        webview.start()

        # 窗口关闭后，把结果同步到主线程
        def apply():
            if result.get("err"):
                self.log(f"❌ {result['err']}")
            elif result.get("cookie"):
                self.cookie_text.delete("1.0", "end")
                self.cookie_text.insert("1.0", result["cookie"])
                self._save_config()
                self.log("✅ 登录成功，已自动获取并保存 Cookie")
                self.test_login()
            else:
                self.log("⚠️ 登录窗口已关闭（未获取到 Cookie）")
        self.root.after(0, apply)

    # ---------- 动作 ----------
    def test_login(self):
        threading.Thread(target=self._do_test_login, daemon=True).start()

    def _do_test_login(self):
        cookie = self._get_cookie()
        if not cookie:
            self.log("❌ Cookie 为空，请先点「登录」")
            return
        try:
            j = api_query(cookie)
            d = j.get("data") or {}
            if j.get("code") != "00000":
                self.log(f"❌ 查询失败：code={j.get('code')} msg={j.get('msg')}")
                if j.get("code") == "3":
                    self.log("   → Cookie 已失效，请重新点「登录」")
                return
            gift = pick_qq_gift(d)
            self.log(f"✅ 登录成功 手机号={d.get('phone')} 状态={STATUS.get(d.get('status'), d.get('status'))}")
            self.log(f"🎁 资格：{d.get('prizeName') or '未获取到'}")
            if gift:
                flag = "🔴 已售罄" if str(gift.get("stockStatus")) == "2" else "🟢 有货"
                self.log(f"🎯 目标：{gift.get('giftName')} {gift.get('giftCode')} "
                         f"{gift.get('month')}个月 充值¥{int(gift.get('payamount') or 0)//100} 库存:{flag}")
            else:
                self.log("⚠️ 未找到 QQ超级会员档位")
        except Exception as e:
            self.log(f"❌ 测试异常：{e}")

    def grab_now(self):
        if not messagebox.askokcancel("确认", "立即抢会真实锁单(占用今天的名额)，确定吗？"):
            return
        threading.Thread(target=self._grab_once, daemon=True).start()

    def _grab_once(self):
        cookie = self._get_cookie()
        gift_code = self.gift_var.get().strip()
        if not cookie:
            self.log("❌ Cookie 为空，请先点「登录」")
            return
        try:
            r = api_charge_pre(cookie, gift_code)
            code = (r or {}).get("code")
            msg = (r or {}).get("msg") or ""
            if code == "00000":
                self.log("🎉 锁单成功！已抢到 QQ超级会员名额，请尽快在手机上完成充值！")
                self._alert("抢到啦！", "已锁单成功，快去手机活动页完成充值(收短信验证码)。")
                return
            tip = {"3": "Cookie 已失效，请重新登录", "B0102": "库存已售罄",
                   "B0103": "已充值过", "B0104": "已锁定其他会员", "B0105": "充值中",
                   "501": "活动太火爆/繁忙"}.get(code, "")
            self.log(f"⚠️ 锁单返回：code={code} msg={msg}{('（' + tip + '）') if tip else ''}")
        except Exception as e:
            self.log(f"❌ 锁单异常：{e}")

    # ---------- 定时抢购 ----------
    def start_schedule(self):
        if self.running:
            self.log("定时任务已运行")
            return
        try:
            h, m, s = self.time_var.get().strip().split(":")
            datetime.time(int(h), int(m), int(s))
        except Exception:
            messagebox.showerror("错误", "抢购时间格式应为 HH:MM:SS")
            return
        if not self._get_cookie():
            messagebox.showerror("错误", "请先点「登录」获取 Cookie")
            return
        self.running = True
        self.log("▶️ 已启动每日自动抢")
        threading.Thread(target=self._schedule_loop, daemon=True).start()

    def stop_schedule(self):
        self.running = False
        self._set_status("已停止定时任务")
        self.log("⏹️ 已停止定时任务")

    def _schedule_loop(self):
        while self.running:
            h, m, s = (int(x) for x in self.time_var.get().strip().split(":"))
            now = datetime.datetime.now()
            target = now.replace(hour=h, minute=m, second=s, microsecond=0)
            if target <= now:
                target += datetime.timedelta(days=1)
            offset_ms = int(self.offset_var.get().strip() or 0)
            self._set_status(f"下次抢购：{target.strftime('%m-%d %H:%M:%S')}")
            self.log(f"⏰ 下次抢购 {target.strftime('%m-%d %H:%M:%S')}，提前30秒进入倒计时")
            pre = target - datetime.timedelta(seconds=30)
            while self.running and datetime.datetime.now() < pre:
                time.sleep(1)
            if not self.running:
                break
            self.log("🔥 已进入抢购倒计时，等待到点...")
            fire_at = target + datetime.timedelta(milliseconds=offset_ms)
            # ① 粗睡到 fire_at - 50ms，避开 Windows timer resolution(~15.6ms) 误差
            coarse = (fire_at - datetime.datetime.now()).total_seconds() - 0.05
            if coarse > 0:
                time.sleep(coarse)
            # ② 高精度忙等到 fire_at：perf_counter 亚毫秒，卡 ±1~2ms
            fire_ts = fire_at.timestamp()
            t0_wall = time.time()
            t0_perf = time.perf_counter()
            fire_perf = t0_perf + (fire_ts - t0_wall)
            while self.running and time.perf_counter() < fire_perf:
                pass
            if not self.running:
                break
            self.log("🚀 到点！发起锁单...")
            for i in range(20):
                if not self.running:
                    break
                if i > 0:
                    time.sleep(0.15)
                r = self._try_grab()
                if r is True:
                    break
                if r == "FATAL":
                    break
            # 本轮结束，等 60 秒进入下一轮
            for _ in range(60):
                if not self.running:
                    break
                time.sleep(1)

    def _try_grab(self):
        """返回 True=成功, False=可重试, 'FATAL'=停止(售罄/失效)"""
        cookie = self._get_cookie()
        gift_code = self.gift_var.get().strip()
        try:
            r = api_charge_pre(cookie, gift_code)
            code = (r or {}).get("code")
            msg = (r or {}).get("msg") or ""
            if code == "00000":
                self.log("🎉 锁单成功！请尽快在手机上完成充值！")
                self._alert("抢到啦！", "已锁单成功，快去手机活动页完成充值。")
                return True
            tip = {"3": "Cookie 失效", "B0102": "已售罄", "B0103": "已充值过",
                   "B0104": "已锁其他", "B0105": "充值中", "501": "繁忙"}.get(code, "")
            self.log(f"⚠️ 锁单返回 code={code}{(' ' + tip) if tip else ''}")
            # 售罄 / cookie 失效等不再重试
            if code in ("3", "B0102", "B0103", "B0104", "B0105"):
                return "FATAL"
            return False
        except Exception as e:
            self.log(f"❌ 锁单异常：{e}")
            return False

    # ---------- 提醒 ----------
    def _alert(self, title, msg):
        def _w():
            try:
                import winsound
                for _ in range(3):
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
            messagebox.showinfo(title, msg)
        self.root.after(0, _w)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()