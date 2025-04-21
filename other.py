from pprint import pprint
from DrissionPage import Chromium, ChromiumOptions
from DrissionPage.items import ChromiumTab, MixTab
import time
import json
import re
import threading
import os  # 新增

PAYMENT_INFO = {
    "guid": None,
    "muid": None,
    "sid": None,
    "hcaptcha_response": None,
    "portal_session_id": None,
    "session_api_key": None,
    "payment_user_agent": None,
    "stripeJsId": None,
    "api_key": None,
    "setup_intent_id": None,
    "setup_intent_client_secret": None,
    "acct_id": None,
    "hcaptcha_duration": None,
    "payment_method_id": None,
    "setup_intent_status": None,
    "page_load_time": 0,
}

HCAPTCHA_INFO = {"response": None, "duration": None, "updated_at": 0}

CAPTURED_MESSAGES = []
CAPTURED_MESSAGE_LOCK = threading.Lock()

DATA_EVENTS = {
    "hcaptcha_updated": threading.Event(),
    "guid_updated": threading.Event(),
    "muid_updated": threading.Event(),
    "sid_updated": threading.Event(),
    "portal_session_updated": threading.Event(),
    "session_api_key_updated": threading.Event(),
    "acct_id_updated": threading.Event(),
    "api_key_updated": threading.Event(),
    "stripe_js_id_updated": threading.Event(),
    "payment_user_agent_updated": threading.Event(),
    "setup_intent_updated": threading.Event(),
    "payment_method_updated": threading.Event(),
}


BACKGROUND_THREAD_RUNNING = True


def init_browser():
    co = ChromiumOptions()
    co.incognito()
    c = Chromium(co)
    c.set.timeouts(9000)
    return c, c.latest_tab


def background_data_collector(tab):
    global PAYMENT_INFO, HCAPTCHA_INFO, CAPTURED_MESSAGES, DATA_EVENTS, BACKGROUND_THREAD_RUNNING

    while BACKGROUND_THREAD_RUNNING:
        try:

            for log in tab.console.steps(timeout=1):
                if log.text.startswith("捕获postMessage:"):
                    message_content = log.text.replace(
                        "捕获postMessage:", "", 1
                    ).strip()
                    try:
                        message_data = json.loads(message_content)

                        with CAPTURED_MESSAGE_LOCK:
                            CAPTURED_MESSAGES.append(message_data)

                        if (
                            isinstance(message_data, dict)
                            and message_data.get("type") == "execute"
                            and message_data.get("channel") == "hcaptcha-invisible"
                        ):
                            body = message_data.get("body", {})
                            if isinstance(body, dict) and "response" in body:
                                HCAPTCHA_INFO["response"] = body["response"]
                                if "duration" in body:
                                    HCAPTCHA_INFO["duration"] = body["duration"]
                                HCAPTCHA_INFO["updated_at"] = time.time()
                                print(
                                    f"[后台线程] 获取到新的hCaptcha响应: {HCAPTCHA_INFO['response'][:30]}... 持续时间: {HCAPTCHA_INFO['duration']}"
                                )

                                PAYMENT_INFO["hcaptcha_response"] = HCAPTCHA_INFO[
                                    "response"
                                ]
                                PAYMENT_INFO["hcaptcha_duration"] = HCAPTCHA_INFO[
                                    "duration"
                                ]

                                DATA_EVENTS["hcaptcha_updated"].set()

                        if (
                            isinstance(message_data, dict)
                            and "originatingScript" in message_data
                            and "payload" in message_data
                        ):
                            payload = message_data.get("payload", {})
                            if isinstance(payload, dict):
                                if "guid" in payload and not PAYMENT_INFO["guid"]:
                                    PAYMENT_INFO["guid"] = payload["guid"]
                                    print(f"[后台线程] 提取到GUID: {payload['guid']}")
                                    DATA_EVENTS["guid_updated"].set()

                                if "muid" in payload and not PAYMENT_INFO["muid"]:
                                    PAYMENT_INFO["muid"] = payload["muid"]
                                    print(f"[后台线程] 提取到MUID: {payload['muid']}")
                                    DATA_EVENTS["muid_updated"].set()

                                if "sid" in payload and not PAYMENT_INFO["sid"]:
                                    PAYMENT_INFO["sid"] = payload["sid"]
                                    print(f"[后台线程] 提取到SID: {payload['sid']}")
                                    DATA_EVENTS["sid_updated"].set()
                    except Exception as e:
                        pass

            time.sleep(0.1)
        except Exception as e:
            print(f"[后台线程] 数据收集出错: {e}")
            time.sleep(1)


def wait_for_hcaptcha(timeout=60):
    print(f"等待hCaptcha响应，最多等待{timeout}秒...")
    return DATA_EVENTS["hcaptcha_updated"].wait(timeout)


def wait_for_payment_info(fields, timeout=60):
    if isinstance(fields, str):
        fields = [fields]

    print(f"等待支付信息字段: {', '.join(fields)}，最多等待{timeout}秒...")

    events_to_wait = []
    for field in fields:
        event_name = f"{field}_updated"
        if event_name in DATA_EVENTS:
            events_to_wait.append(DATA_EVENTS[event_name])

    if not events_to_wait:
        print(f"警告: 没有找到与字段 {', '.join(fields)} 对应的事件")
        return False

    start_time = time.time()
    all_set = True
    for event in events_to_wait:
        remaining_time = timeout - (time.time() - start_time)
        if remaining_time <= 0:
            all_set = False
            break
        if not event.wait(remaining_time):
            all_set = False
            break

    return all_set


def wait_for_specific_data(check_func, timeout=60, check_interval=0.5):
    print(f"等待特定条件满足，最多等待{timeout}秒...")

    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_func():
            return True
        time.sleep(check_interval)

    return False


def login_cerebrium(tab, email, password):
    tab.get("https://dashboard.cerebrium.ai/login")
    print(f"登录页面加载完成，准备使用账号 {email} 登录")

    # 通过Google登录
    tab.ele("tag:button@@text():Google").click()
    tab.wait.load_start()
    print("Google登录页面加载完成")

    # 输入邮箱
    tab.ele("#identifierId").input(email)
    tab.ele("tag:button@@text():下一步").click()
    print("邮箱账号输入完成")

    # 输入密码
    password_input = tab.ele("#password")
    password_input.wait.clickable()
    password_input.input(password)
    tab.ele("tag:button@@text():下一步").click()
    tab.wait.load_start()
    print("密码输入完成")

    # 点击继续按钮（如果存在）
    try:
        tab.ele("tag:button@@text():Continue").click()
        tab.wait.load_start()
        print("继续按钮点击完成")
    except:
        print("继续按钮不存在")

    tab.wait.load_start()
    print("跳转完成")


def handle_billing_page(tab: ChromiumTab, c: Chromium):
    global PAYMENT_INFO, HCAPTCHA_INFO, CAPTURED_MESSAGES, DATA_EVENTS, BACKGROUND_THREAD_RUNNING

    try:
        for key in PAYMENT_INFO:
            PAYMENT_INFO[key] = None
        PAYMENT_INFO["page_load_time"] = int(time.time())

        HCAPTCHA_INFO["response"] = None
        HCAPTCHA_INFO["duration"] = None
        HCAPTCHA_INFO["updated_at"] = 0

        with CAPTURED_MESSAGE_LOCK:
            CAPTURED_MESSAGES.clear()

        for event in DATA_EVENTS.values():
            event.clear()

        BACKGROUND_THREAD_RUNNING = True

        tab.listen.start(["p/session/live_"])

        manage_button = tab.ele("tag:button@@text():Manage")
        manage_button.wait.clickable()
        manage_button.click()
        tab.wait.load_start()

        tab.wait(10)

        tab.console.start()

        res = tab.listen.wait(1)
        redirect_url = res.url  # type: ignore
        response = res.response  # type: ignore
        data = response.raw_body

        bps_match = re.search(r"portal_session_id&quot;:&quot;(bps_[^&]+)&quot;", data)
        if bps_match:
            portal_session_id = bps_match.group(1)
            PAYMENT_INFO["portal_session_id"] = portal_session_id
            print(f"通过正则提取到的Portal Session ID: {portal_session_id}")
            DATA_EVENTS["portal_session_updated"].set()

        ek_match = re.search(r"session_api_key&quot;:&quot;(ek_live_[^&]+)&quot;", data)
        if ek_match:
            session_api_key = ek_match.group(1)
            PAYMENT_INFO["session_api_key"] = session_api_key
            print(f"通过正则提取到的Session API Key: {session_api_key}")
            DATA_EVENTS["session_api_key_updated"].set()

        acct_match = re.search(r"id&quot;:&quot;(acct_[^&]+)&quot;", data)
        if acct_match:
            acct_id = acct_match.group(1)
            PAYMENT_INFO["acct_id"] = acct_id
            DATA_EVENTS["acct_id_updated"].set()

        js_script = """
        (function() {
            let messages = [];
            
            function captureMessage(event) {
                console.log('捕获postMessage:', event.data);
                messages.push({
                    source: event.source ? 'iframe' : 'window',
                    origin: event.origin,
                    data: event.data
                });
            }
            
            window.addEventListener('message', captureMessage, false);
        })();
        """

        tab.run_js(js_script, as_expr=True)

        js_script = """
        (function() {
            let messages = [];
            
            function captureMessage(event) {
                console.log('捕获postMessage:', event.data);
                messages.push({
                    source: event.source ? 'iframe' : 'window',
                    origin: event.origin,
                    data: event.data
                });
            }
            
            window.addEventListener('message', captureMessage, false);
        })();
        """

        tab.run_js(js_script, as_expr=True)

        data_thread = threading.Thread(
            target=background_data_collector, args=(tab,), daemon=True
        )
        data_thread.start()

        add_payment_button = tab.ele("tag:a@@text():添加支付方式")
        add_payment_button.wait.clickable()
        add_payment_button.click()
        tab.wait.load_start()

        print("等待收集消息...")
        time.sleep(5)

        def get_hcaptcha_info():
            return HCAPTCHA_INFO

        try:
            if CAPTURED_MESSAGE_LOCK.acquire(timeout=2):  # 最多等待2秒
                try:
                    collected_messages = list(CAPTURED_MESSAGES)
                    print(f"已收集到 {len(collected_messages)} 条消息")
                finally:
                    CAPTURED_MESSAGE_LOCK.release()
            else:
                print("警告：获取消息超时，继续执行")
                collected_messages = []
        except Exception as e:
            print(f"获取消息时出错: {e}")
            collected_messages = []

        if not all([PAYMENT_INFO["guid"], PAYMENT_INFO["muid"], PAYMENT_INFO["sid"]]):
            for message_data in collected_messages:
                if (
                    isinstance(message_data, dict)
                    and "originatingScript" in message_data
                    and "payload" in message_data
                ):
                    payload = message_data.get("payload", {})
                    if isinstance(payload, dict):
                        if "guid" in payload and not PAYMENT_INFO["guid"]:
                            PAYMENT_INFO["guid"] = payload["guid"]
                            print(f"提取到GUID: {payload['guid']}")
                            DATA_EVENTS["guid_updated"].set()
                        if "muid" in payload and not PAYMENT_INFO["muid"]:
                            PAYMENT_INFO["muid"] = payload["muid"]
                            print(f"提取到MUID: {payload['muid']}")
                            DATA_EVENTS["muid_updated"].set()
                        if "sid" in payload and not PAYMENT_INFO["sid"]:
                            PAYMENT_INFO["sid"] = payload["sid"]
                            print(f"提取到SID: {payload['sid']}")
                            DATA_EVENTS["sid_updated"].set()

        frames = tab.get_frames()
        for frame in frames:  # type: ignore
            frame_url = frame.url
            print(f"Frame URL: {frame_url}")

            if "apiKey" in frame_url:
                api_key_match = re.search(r"apiKey]=([^&]+)", frame_url)
                if api_key_match:
                    api_key = api_key_match.group(1)
                    PAYMENT_INFO["api_key"] = api_key
                    DATA_EVENTS["api_key_updated"].set()

            if "link-auth-modal-inner" in frame_url:
                stripe_js_id_match = re.search(r"stripeJsId=([^&]+)", frame_url)
                if stripe_js_id_match:
                    stripe_js_id = stripe_js_id_match.group(1)
                    print(f"提取到的Stripe JS ID: {stripe_js_id}")
                    PAYMENT_INFO["stripeJsId"] = stripe_js_id
                    DATA_EVENTS["stripe_js_id_updated"].set()

        if PAYMENT_INFO["api_key"] is None:
            print("无法从URL中提取apiKey")

        if "stripeJsId" not in PAYMENT_INFO or PAYMENT_INFO["stripeJsId"] is None:
            print("无法从URL中提取stripeJsId")

        tmp_tab: MixTab = c.new_tab()
        res = tmp_tab.get("https://js.stripe.com/v3/.deploy_status_henson.json")
        print(res, tmp_tab.json, tmp_tab.url)

        try:
            deploy_status = tab.json
            if (
                deploy_status
                and "deployedRevisions" in deploy_status
                and len(deploy_status["deployedRevisions"]) > 0
            ):
                first_revision = deploy_status["deployedRevisions"][0]
                revision_prefix = first_revision[:10]
                payment_user_agent = f"stripe.js/{revision_prefix}; stripe-js-v3/{revision_prefix}; payment-element"
                PAYMENT_INFO["payment_user_agent"] = payment_user_agent
                print(f"Payment User Agent: {payment_user_agent}")
                DATA_EVENTS["payment_user_agent_updated"].set()
            else:
                print("无法获取deployedRevisions信息")
        except Exception as e:
            print(f"提取deployedRevisions信息时出错: {e}")

        print("\n提取的支付信息:")
        print(f"GUID: {PAYMENT_INFO['guid']}")
        print(f"MUID: {PAYMENT_INFO['muid']}")
        print(f"SID: {PAYMENT_INFO['sid']}")
        print(f"hCaptcha响应: {PAYMENT_INFO['hcaptcha_response']}")
        print(f"API Key: {PAYMENT_INFO['api_key']}")
        print(f"Payment User Agent: {PAYMENT_INFO['payment_user_agent']}")
        print(f"Stripe JS ID: {PAYMENT_INFO['stripeJsId']}")
        print(f"Portal Session ID: {PAYMENT_INFO['portal_session_id']}")
        print(f"Session API Key: {PAYMENT_INFO['session_api_key']}")
        print(f"Account ID: {PAYMENT_INFO['acct_id']}")

        try:
            portal_session_id = PAYMENT_INFO["portal_session_id"]
            session_api_key = PAYMENT_INFO["session_api_key"]

            setup_intent_url = f"https://billing.stripe.com/v1/billing_portal/sessions/{portal_session_id}/setup_intents/"
            query_params = {
                "include_only[]": [
                    "id",
                    "object",
                    "client_secret",
                    "payment_method_types",
                ]
            }
            headers = {
                "Authorization": f"Bearer {session_api_key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "stripe-account": PAYMENT_INFO["acct_id"],
                "stripe-livemode": "true",
                "stripe-version": "2025-03-01.dashboard",
            }

            latest_info = get_hcaptcha_info()
            if latest_info["response"]:
                PAYMENT_INFO["hcaptcha_response"] = latest_info["response"]
                PAYMENT_INFO["hcaptcha_duration"] = latest_info["duration"]
                print(
                    f"使用最新的hCaptcha响应，更新于 {int(time.time() - latest_info['updated_at'])} 秒前"
                )

            response = tab.post(  # type: ignore
                url=setup_intent_url, params=query_params, headers=headers
            )

            if response.status_code == 200:
                setup_intent = response.json()
                if setup_intent and "id" in setup_intent:
                    setup_intent_id = setup_intent["id"]
                    setup_intent_client_secret = setup_intent.get("client_secret")
                    PAYMENT_INFO["setup_intent_id"] = setup_intent_id
                    PAYMENT_INFO["setup_intent_client_secret"] = (
                        setup_intent_client_secret
                    )
                    DATA_EVENTS["setup_intent_updated"].set()

                    print(f"\n成功获取Setup Intent:")
                    print(f"Setup Intent ID: {setup_intent_id}")
                    print(f"Setup Intent Client Secret: {setup_intent_client_secret}")
                else:
                    print(f"\n无法从响应中获取setup_intent信息")
                    print(f"响应内容: {tab.json}")
            else:
                print(f"\n获取setup_intent失败，状态码: {response.status_code}")
                print(f"响应内容: {response.text}")
        except Exception as e:
            print(f"\n获取setup_intent时出错: {e}")

        try:
            latest_info = get_hcaptcha_info()
            if latest_info["response"]:
                PAYMENT_INFO["hcaptcha_response"] = latest_info["response"]
                PAYMENT_INFO["hcaptcha_duration"] = latest_info["duration"]
                print(
                    f"使用最新的hCaptcha响应，更新于 {int(time.time() - latest_info['updated_at'])} 秒前"
                )

            time_on_page = int(time.time()) - PAYMENT_INFO["page_load_time"]

            card_data = {
                "type": "card",
                "card[number]": "5154 cccccccccccccc",
                "card[cvc]": "ccc",
                "card[exp_year]": "cc",
                "card[exp_month]": "cc",
                "allow_redisplay": "unspecified",
                "billing_details[address][country]": "cc",
                "pasted_fields": "number",
                "payment_user_agent": PAYMENT_INFO.get("payment_user_agent"),
                "referrer": "https://billing.stripe.com",
                "time_on_page": str(time_on_page),
                "client_attribution_metadata[client_session_id]": PAYMENT_INFO.get(
                    "stripeJsId"
                ),
                "client_attribution_metadata[merchant_integration_source]": "elements",
                "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
                "client_attribution_metadata[merchant_integration_version]": "2021",
                "client_attribution_metadata[payment_intent_creation_flow]": "standard",
                "client_attribution_metadata[payment_method_selection_flow]": "merchant_specified",
                "guid": PAYMENT_INFO.get("guid"),
                "muid": PAYMENT_INFO.get("muid"),
                "sid": PAYMENT_INFO.get("sid"),
                "key": PAYMENT_INFO.get("api_key"),
            }

            if PAYMENT_INFO.get("hcaptcha_response"):
                card_data["radar_options[hcaptcha_token]"] = PAYMENT_INFO.get(
                    "hcaptcha_response"
                )

            payment_methods_url = "https://api.stripe.com/v1/payment_methods"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            print("\n正在提交卡片信息...")
            card_response = tab.post(  # type: ignore
                url=payment_methods_url, data=card_data, headers=headers
            )

            if card_response.status_code == 200:
                payment_method = card_response.json()
                if payment_method and "id" in payment_method:
                    payment_method_id = payment_method["id"]
                    PAYMENT_INFO["payment_method_id"] = payment_method_id
                    DATA_EVENTS["payment_method_updated"].set()

                    print(f"\n成功创建支付方式:")
                    print(f"Payment Method ID: {payment_method_id}")
                    print(f"Card Brand: {payment_method.get('card', {}).get('brand')}")
                    print(f"Last4: {payment_method.get('card', {}).get('last4')}")
                else:
                    print(f"\n无法从响应中获取payment_method信息")
                    print(f"响应内容: {tab.json}")
            else:
                print(f"\n提交卡片信息失败，状态码: {card_response.status_code}")
                print(f"响应内容: {card_response.text}")

            if (
                "payment_method_id" in PAYMENT_INFO
                and "setup_intent_id" in PAYMENT_INFO
            ):
                latest_info = get_hcaptcha_info()
                if latest_info["response"]:
                    PAYMENT_INFO["hcaptcha_response"] = latest_info["response"]
                    PAYMENT_INFO["hcaptcha_duration"] = latest_info["duration"]
                    print(
                        f"使用最新的hCaptcha响应，更新于 {int(time.time() - latest_info['updated_at'])} 秒前"
                    )

                confirm_url = f"https://billing.stripe.com/v1/billing_portal/sessions/{PAYMENT_INFO['portal_session_id']}/setup_intents/{PAYMENT_INFO['setup_intent_id']}/confirm"
                confirm_params = {
                    "include_only[]": [
                        "id",
                        "status",
                        "client_secret",
                        "payment_method",
                    ]
                }
                confirm_data = {
                    "payment_method": PAYMENT_INFO["payment_method_id"],
                    "return_url": f"{redirect_url}/payment-methods/return?in_flow=false&make_customer_default=true",
                }

                if PAYMENT_INFO.get("hcaptcha_response"):
                    confirm_data["passive_captcha_token"] = PAYMENT_INFO.get(
                        "hcaptcha_response"
                    )

                confirm_headers = {
                    "Authorization": f"Bearer {PAYMENT_INFO['session_api_key']}",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "stripe-account": PAYMENT_INFO["acct_id"],
                    "stripe-livemode": "true",
                    "stripe-version": "2025-03-01.dashboard",
                }

                print("\n正在确认setup_intent...")
                confirm_response = tab.post(  # type: ignore
                    url=confirm_url,
                    params=confirm_params,
                    data=confirm_data,
                    headers=confirm_headers,
                )

                if confirm_response.status_code == 200:
                    confirm_result = confirm_response.json()
                    print(f"\n确认结果: {confirm_result.get('status')}")
                    PAYMENT_INFO["setup_intent_status"] = confirm_result.get("status")
                    DATA_EVENTS["setup_intent_updated"].set()
                else:
                    print(
                        f"\n确认setup_intent失败，状态码: {confirm_response.status_code}"
                    )
                    print(f"响应内容: {confirm_response.text}")

        except Exception as e:
            print(f"\n提交卡片信息或确认setup_intent时出错: {e}")

        return PAYMENT_INFO

    except Exception as e:
        print(f"添加支付方式按钮不存在: {e}")
        return None


# 辅助函数，用于等待特定数据
def wait_for_data(data_type, timeout=60):
    if data_type in DATA_EVENTS:
        print(f"等待{data_type}数据，最多等待{timeout}秒...")
        return DATA_EVENTS[data_type].wait(timeout)
    else:
        print(f"警告: 未知的数据类型 {data_type}")
        return False

if __name__ == "__main__":
    c, tab = init_browser()
    # 从环境变量读取邮箱和密码
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    login_cerebrium(tab, email, password)
    handle_billing_page(tab, c)
