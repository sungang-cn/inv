#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import imaplib
import email
import os

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

def get_email_content():
    # 邮箱配置（替换为你的信息）
    IMAP_SERVER = 'imap.163.com'
    EMAIL = os.environ.get('MAIL_USER', 'sungsun@163.com')
    PASSWORD = os.environ.get('MAIL_PASS', 'PMSpb3AXYAiN2ju') #omK
    imap_id = ("name", "sungang", "contact", "sungsun@163.com", "version", "1.0.0", "vendor", "imaplib")
    try:
        # 连接IMAP服务器
        with imaplib.IMAP4_SSL(IMAP_SERVER) as mail:
            status, data = mail.login(EMAIL, PASSWORD)
            if status != "OK":
                raise Exception("无法登录")
            status, cap = mail.capability()
            if status != "OK":
                raise Exception("无法获取capability")
            status, _ = mail.xatom('ID', '("' + '" "'.join(imap_id) + '")')
            if status != "OK":
                raise Exception("无法执行xatom ID")
            status, maillist = mail.list()
            if status != "OK":
                raise Exception("无法获取邮箱目录列表")
            #print(maillist)
            status, message = mail.select(mailbox='INBOX', readonly=True) # 选择收件箱
            #status, message = mail.select(b'() "/" "INBOX"') # 选择收件箱
            if status != "OK":
                raise Exception("无法选择邮箱")
            status, messages = mail.search(None, 'ALL')
            if status != 'OK': 
                print("没有找到邮件") 
                return
            # 获取邮件列表
            email_ids = messages[0].split() 
            print(f"找到 {len(email_ids)} 封新邮件")
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                if status != 'OK':
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                subject = decode_str(msg['Subject'])
                from_ = decode_str(msg['From'])
                print(f"\n主题: {subject}")
                print(f"发件人: {from_}")
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        print(f"正文:\n{body.strip()}")
            mail.close()
            mail.logout()

    except Exception as e: 
        print(f"发生错误: {str(e)}") 

if __name__ == '__main__':
    get_email_content()

