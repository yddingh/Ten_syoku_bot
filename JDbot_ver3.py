import time
import csv
import os
import re
import random
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# 搜索结果页
TARGET_URL = "https://pdt.r-agent.com/pdt/app/pdt_joboffer_search_view?searchKeyword=%E3%83%87%E3%83%BC%E3%82%BF%E3%82%B5%E3%82%A4%E3%82%A8%E3%83%B3%E3%83%86%E3%82%A3%E3%82%B9%E3%83%88&searchJobtypes=1110000000,3305000000&searchPlaces=35,37,36&searchSalaryFrom=500&searchTypeOfEmployment=1&searchHoliday=1&sort=2&sn=e2005d526aa8027c084ac80c391860fe&PDT63B=undefined&PDT61C=undefined" 

# 只抓取该日期及之后的更新
START_DATE_LIMIT = "2026-01-01" 

#结果文件(跳过既存内容)
CSV_FILE = "jd_data_raw.csv"


def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # 启动时最大化窗口，防止遮挡
    chrome_options.add_argument("--start-maximized")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def get_existing_ids():
    ids = set()
    if not os.path.exists(CSV_FILE):
        return ids
    try:
        with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                jid = row.get('求人票No')
                if jid:
                    ids.add(jid.strip())
                else:
                    content = row.get('内容全文', '') or row.get('原始全文', '')
                    id_match = re.search(r'([a-z]\d{9})|K\d{8}-\d{3}-\d{2}-\d{3}', content)
                    if id_match: ids.add(id_match.group(0))
    except Exception as e:
        print(f"读取旧数据异常: {e}")
    return ids

def parse_date(date_str):
    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
    return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else None

def crawl_jd():
    limit_dt = datetime.strptime(START_DATE_LIMIT, "%Y-%m-%d")
    dealt_ids = get_existing_ids() 
    print(f"本地库已识别: {len(dealt_ids)} 条记录。")

    driver = init_driver()
    driver.get(TARGET_URL)
    input("【操作提示】请手动完成登录并进入列表页，确认看到JD卡片后在此按回车...")

    # 初始化CSV头
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["序号", "求人票No", "更新日期", "内容全文"])

    new_saved_count = 0
    
    try:
        while True:
            # 获取当前可见的所有按钮
            wait = WebDriverWait(driver, 10)
            buttons = driver.find_elements(By.CLASS_NAME, "mod-jobList-toDetailButton")
            
            found_new_to_click = False 

            for btn in buttons:
                # 获取ID进行初步查重
                href = btn.get_attribute("href")
                id_match = re.search(r'jobofferManagementNo=([^&]+)', href)
                jd_id = id_match.group(1) if id_match else None
                
                if not jd_id or jd_id in dealt_ids:
                    continue 

                # 发现新ID
                found_new_to_click = True
                main_window = driver.current_window_handle
                
                # 物理点击逻辑：先滚动，再点击
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(0.5) # 给滚动一点缓冲时间
                    btn.click() # 使用物理点击
                    
                    # 等待新窗口
                    wait.until(lambda d: len(d.window_handles) > 1)
                    driver.switch_to.window(driver.window_handles[-1])
                    
                    # 抓取全文
                    body_element = wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    full_text = body_element.text
                    
                    # 提取日期判定
                    date_match = re.search(r'最終更新日\s*(\d{4}年\d{1,2}月\d{1,2}日)', full_text)
                    update_date_str = date_match.group(1) if date_match else "未知日期"
                    update_dt = parse_date(update_date_str)

                    if update_dt and update_dt < limit_dt:
                        print(f"ID: {jd_id} 更新于 {update_date_str}，早于设定日期，跳过。")
                    else:
                        with open(CSV_FILE, 'a', newline='', encoding='utf-8-sig') as f:
                            writer = csv.writer(f)
                            writer.writerow([len(dealt_ids)+1, jd_id, update_date_str, full_text.replace('\n', ' ')])
                        new_saved_count += 1
                        print(f"新增保存: {jd_id} ({update_date_str})")

                    dealt_ids.add(jd_id)
                except Exception as e:
                    print(f"抓取 ID {jd_id} 时出错 (可能因遮挡或加载超时): {e}")
                finally:
                    if len(driver.window_handles) > 1:
                        driver.close()
                    driver.switch_to.window(main_window)
                    # 稍微休息，提速的关键：缩短不必要的 sleep
                    time.sleep(random.uniform(0.8, 1.5))

            # 翻页加载更多
            try:
                # 物理模拟点击“加载更多”
                load_more_btn = driver.find_element(By.CSS_SELECTOR, ".mod-loadMore-text")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_btn)
                time.sleep(1)
                
                # 先尝试常规点击，如果被挡住，报错会被捕获
                load_more_btn.click()
                print("--- 已点击加载更多，等待内容刷新 ---")
                time.sleep(4) 
            except Exception:
                # 如果物理点击失败（比如真的被挡住了），且当前屏没有新内容点，说明到头了
                if not found_new_to_click:
                    print("已到达列表底部或无法继续点击。")
                    break
                else:
                    # 如果是因为网络慢按钮没出来，再等一会
                    time.sleep(2)
                    continue

    finally:
        driver.quit()
        print(f"任务结束。目前库总计: {len(dealt_ids)} 条，本次新增: {new_saved_count} 条。")

if __name__ == "__main__":
    crawl_jd()