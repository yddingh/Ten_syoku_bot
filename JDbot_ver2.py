import time
import csv
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# --- 配置区 ---
TARGET_URL = "https://pdt.r-agent.com/pdt/app/pdt_joboffer_search_view?searchKeyword=%E3%83%87%E3%83%BC%E3%82%BF%E3%82%B5%E3%82%A4%E3%82%A8%E3%83%B3%E3%83%86%E3%82%A3%E3%82%B9%E3%83%88&searchJobtypes=1110000000,3305000000&searchPlaces=35,37,36&searchSalaryFrom=500&searchTypeOfEmployment=1&searchHoliday=1&sort=2&sn=e2005d526aa8027c084ac80c391860fe&PDT63B=undefined" # 直接访问搜索结果页
CSV_FILE = "jd_data_raw.csv"

def init_driver():
    chrome_options = Options()
    # 模拟真实浏览器，减少被识别为Bot的概率
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

def save_to_csv(data, index):
    with open(CSV_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([index, data.replace('\n', '  ')]) # 换行符转为空格，方便后续处理

def crawl_jd():
    driver = init_driver()
    driver.get(TARGET_URL)
    
    print("【操作提示】")
    print("1. 请在弹出的浏览器中完成登录。")
    print("2. 确保页面已加载出搜索结果列表。")
    print("3. 回到这里按回车键开始自动抓取...")
    input()
    
    # 初始化CSV标题
    with open(CSV_FILE, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(["序号", "内容全文"])

    jd_index = 1
    
    try:
        while True:
            # 获取当前页面所有的“詳細を見る”按钮
            # 使用 find_elements 实时获取，防止 DOM 刷新导致元素失效
            buttons = driver.find_elements(By.CLASS_NAME, "mod-jobList-toDetailButton")
            
            # 如果当前页面的按钮都已经点过了
            if jd_index > len(buttons):
                print(f"当前页面的 {len(buttons)} 条已处理完，尝试点击‘さらに読み込む’...")
                try:
                    # 查找“加载更多”按钮
                    load_more_xpath = "//p[contains(@class, 'mod-loadMore-text') and contains(text(), 'さらに読み込む')]"
                    load_more_btn = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, load_more_xpath))
                    )
                    
                    # 滚动到按钮位置并点击
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_btn)
                    time.sleep(1)
                    load_more_btn.click()
                    
                    print("已点击加载更多，等待新内容加载...")
                    time.sleep(3) # 给Ajax留出加载时间
                    continue # 重新进入循环获取更新后的 buttons 列表
                except Exception as e:
                    print("无法找到更多加载按钮，可能已到底，或者需要手动干预。")
                    break

            # 处理当前的按钮
            target_btn = buttons[jd_index-1]
            main_window = driver.current_window_handle
            
            try:
                # 滚动到该按钮，防止被遮挡
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_btn)
                time.sleep(0.5)
                
                # JS点击打开新窗口
                driver.execute_script("arguments[0].click();", target_btn)
                
                # 等待新窗口出现并切换
                WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) > 1)
                for handle in driver.window_handles:
                    if handle != main_window:
                        driver.switch_to.window(handle)
                        break
                
                # 等待Body加载后抓取全文内容
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                content = driver.find_element(By.TAG_NAME, "body").text
                
                save_to_csv(content, jd_index)
                print(f"成功抓取第 {jd_index} 条")
                
                # 关闭详情页，切回主列表
                driver.close()
                driver.switch_to.window(main_window)
                
                jd_index += 1
                # 随机增加一点延迟，模拟人类阅读速度，防止被封
                time.sleep(random.uniform(1.2, 2.5))
                
            except Exception as e:
                print(f"处理第 {jd_index} 条时发生错误: {e}")
                # 发生错误时尝试回到主窗口继续
                if len(driver.window_handles) > 1:
                    driver.close()
                driver.switch_to.window(main_window)
                jd_index += 1 # 跳过该条继续

    except KeyboardInterrupt:
        print("程序被手动停止")
    finally:
        driver.quit()
        print(f"任务结束，共抓取 {jd_index-1} 条数据。")

if __name__ == "__main__":
    crawl_jd()