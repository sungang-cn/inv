#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import imaplib 
import email 
import getpass 

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
    #EMAIL = input("请输入163邮箱地址: ") 
    #PASSWORD = getpass.getpass("请输入邮箱授权码: ") # 安全输入密码
    EMAIL = 'sungsun@163.com'
    PASSWORD = 'PMSpb3AXYAiN2ju'
    imap_id = ("name", "sungang", "contact", "sungsun@163.com", "version", "1.0.0", "vendor", "imaplib")
    try:
        # 连接IMAP服务器
        with imaplib.IMAP4_SSL(IMAP_SERVER) as mail: 
            status, data = mail.login(EMAIL, PASSWORD)
            if status != "OK":
                raise Exception("无法登录")
            status, data = mail.capability()
            if status != "OK":
                raise Exception("无法获取capability")
            else:
                print(data)
            mail.xatom('ID', '("' + '" "'.join(imap_id) + '")')
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
            # 搜索所有未读邮件（可根据需求修改搜索条件）
            status, messages = mail.search(None, 'ALL') 
            #status, messages = mail.search(None,'SUBJECT "2026"') 
            #status, messages = mail.search(None, 'SUBJECT "幻方量化"'.encode('utf-8'))
            if status != 'OK': 
                print("没有找到邮件") 
                return
            # 获取邮件列表
            email_ids = messages[0].split() 
            print(f"找到 {len(email_ids)} 封新邮件")
            for email_id in email_ids:
                # 获取邮件内容
                status, msg_data = mail.fetch(email_id, '(RFC822)') 
                if status != 'OK': 
                    continue
                # 解析邮件
                raw_email = msg_data[0][1] 
                msg = email.message_from_bytes(raw_email)
                # 解析邮件头
                subject = decode_str(msg['Subject']) 
                from_ = decode_str(msg['From']) 
                print(f"\n主题: {subject}") 
                print(f"发件人: {from_}")
                # 解析邮件正文
                for part in msg.walk(): 
                    content_type = part.get_content_type()
                    print(content_type)
                    '''
                    if content_type == 'text/plain': 
                        body = part.get_payload(decode=True).decode('utf-8', errors='ignore') 
                        print("\n正文内容:") 
                        print(body.strip())
                    '''
            mail.close()
            mail.logout()

    except Exception as e: 
        print(f"发生错误: {str(e)}") 

if __name__ == '__main__':
    get_email_content()

