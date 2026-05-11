#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import imaplib
import email
import os
import re
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def decode_str(s):
    try:
        subject = email.header.decode_header(s)
    except:
        # print('Header decode error')
        return None 
    sub_bytes = subject[0][0] 
    sub_charset = subject[0][1]
    if None == sub_charset:
        subject = sub_bytes
    elif 'unknown-8bit' == sub_charset:
        subject = str(sub_bytes, 'utf8')
    else:
        subject = str(sub_bytes, sub_charset)
    return subject

def parse_nav_from_text(text):
    records = []
    # 尝试解析 HTML table 格式: <td>日期</td> ... <td>单位净值</td>
    rows = re.findall(r'<tr>(.*?)</tr>', text, re.DOTALL)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) >= 4:
            date_raw = re.sub(r'<.*?>', '', cells[0]).strip()
            nav_raw = re.sub(r'<.*?>', '', cells[3]).strip()
            m = re.match(r'(\d{4})(\d{2})(\d{2})', date_raw)
            if m and re.match(r'^\d+\.?\d*$', nav_raw):
                dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                records.append((dt, float(nav_raw)))
    if records:
        records.sort(key=lambda x: x[0])
        return records
    # fallback: 纯文本格式
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        m = re.search(r'(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}).*?(\d+\.\d+)', line)
        if not m:
            m = re.search(r'(\d{4}年\d{1,2}月\d{1,2}日).*?(\d+\.\d+)', line)
        if m:
            date_str, val_str = m.group(1), m.group(2)
            for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y年%m月%d日'):
                try:
                    dt = datetime.strptime(date_str, fmt)
                    records.append((dt, float(val_str)))
                    break
                except ValueError:
                    continue
    records.sort(key=lambda x: x[0])
    return records


def fetch_nav_and_plot():
    IMAP_SERVER = 'imap.163.com'
    EMAIL = os.environ.get('MAIL_USER', 'sungsun@163.com')
    PASSWORD = os.environ.get('MAIL_PASS', 'PMSpb3AXYAiN2ju') #omK
    imap_id = ("name", "sungang", "contact", "sungsun@163.com", "version", "1.0.0", "vendor", "imaplib")

    try:
        with imaplib.IMAP4_SSL(IMAP_SERVER) as mail:
            status, _ = mail.login(EMAIL, PASSWORD)
            if status != "OK":
                raise Exception("无法登录")
            mail.xatom('ID', '("' + '" "'.join(imap_id) + '")')
            mail.select(mailbox='INBOX', readonly=True)

            status, messages = mail.search('UTF-8', '(SUBJECT "幻方")'.encode('utf-8'))
            if status != 'OK' or not messages[0]:
                print("UTF-8 搜索无结果，尝试全量搜索后本地过滤...")
                status, messages = mail.search(None, 'ALL')

            email_ids = messages[0].split()
            print(f"待筛选邮件数: {len(email_ids)}")

            all_records = []
            for eid in email_ids:
                status, msg_data = mail.fetch(eid, '(RFC822)')
                if status != 'OK':
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                subject = decode_str(msg['Subject'])
                if '幻方' not in subject:
                    continue
                print(f"  解析: {subject}")
                for part in msg.walk():
                    if part.get_content_type() in ('text/plain', 'text/html'):
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode('utf-8', errors='ignore')
                            records = parse_nav_from_text(body)
                            all_records.extend(records)

            mail.close()
            mail.logout()

        if not all_records:
            print("未在邮件正文中找到净值数据")
            return

        print(f"\n共提取 {len(all_records)} 条净值记录")
        dates, values = zip(*all_records)

        # 输出表格
        print(f"\n{'日期':<16} {'净值':>8}")
        print('-' * 26)
        for d, v in all_records:
            print(f"{d.strftime('%Y-%m-%d'):<16} {v:>8.4f}")

        # 绘图
        plt.rcParams['font.family'] = "WenQuanYi Zen Hei"
        plt.figure(figsize=(12, 6))
        plt.plot(dates, values, marker='o', linestyle='-', color='#e74c3c', linewidth=2, markersize=5)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.gcf().autofmt_xdate(rotation=45)
        plt.xlabel('时间')
        plt.ylabel('净值')
        plt.title('幻方净值走势')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig('nav_trend.png')
        print(f"\n趋势图已保存: nav_trend.png")
        plt.show()

    except Exception as e:
        print(f"发生错误: {str(e)}")


if __name__ == '__main__':
    fetch_nav_and_plot()

