#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
龙旗X计划私募证券投资基金B净值邮件追踪工具
通过IMAP协议连接163网易邮箱，自动搜索并提取"龙旗基金净值"邮件，
解析基金净值数据，生成结构化表格和趋势曲线图。

使用方法:
    python fund_nav_tracker.py
    python fund_nav_tracker.py --days 30       # 搜索最近30天的邮件
    python fund_nav_tracker.py --output mydata  # 指定输出文件名前缀
"""

import email
import imaplib
import logging
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from dotenv import load_dotenv

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# 加载 .env 文件中的环境变量
load_dotenv()


# ============================================================================
# 0. 基金配置（可在此增删要追踪的基金）
# ============================================================================

FUND_CONFIGS: list[dict] = [
    {
        "key": "longqi",  # 命令行 --funds 选择时使用的标识
        "name": "龙旗X计划私募证券投资基金B",
        "subject_keyword": "AVG87B",  # 主题过滤（产品代码最稳定）
        "product_keyword": "龙旗X计划",  # 正文产品名细分标识
        "output_prefix": "longqi_nav",
    },
    {
        "key": "huanfang_13",
        "name": "幻方中证500量化多策略13号私募证券投资基金",
        "subject_keyword": "净值报告",  # 主题含「净值报告」(周报)
        "product_keyword": "13号",  # 正文产品名含「13号」，与20号区分
        "output_prefix": "huanfang_13_nav",
    },
    {
        "key": "huanfang_20",
        "name": "幻方500量化多策略20号私募证券投资基金",
        "subject_keyword": "净值报告",
        "product_keyword": "20号",
        "output_prefix": "huanfang_20_nav",
    },
]


# ============================================================================
# 1. 邮箱连接与认证
# ============================================================================

class MailClient:
    """163网易邮箱 IMAP 客户端"""

    IMAP_SERVER = "imap.163.com"
    IMAP_PORT = 993

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
    ):
        """
        初始化邮箱客户端。

        Args:
            username: 邮箱地址（若为 None 则从环境变量 MAIL_USERNAME 读取）
            password: 邮箱密码/授权码（若为 None 则从环境变量 MAIL_PASSWORD 读取）
        """
        self.username = username or os.getenv("MAIL_USERNAME", "")
        self.password = password or os.getenv("MAIL_PASSWORD", "")

        if not self.username or not self.password:
            raise ValueError(
                "邮箱账号或密码未提供。请设置环境变量 MAIL_USERNAME 和 "
                "MAIL_PASSWORD，或直接传入参数。\n"
                "注意：163邮箱需使用「授权码」而非登录密码，"
                "可在 设置 > POP3/SMTP/IMAP 中获取。"
            )

        self.connection: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        """连接并登录IMAP服务器"""
        logger.info("正在连接 %s:%d ...", self.IMAP_SERVER, self.IMAP_PORT)
        self.connection = imaplib.IMAP4_SSL(self.IMAP_SERVER, self.IMAP_PORT)
        # imaplib 默认用 ASCII 编码命令参数，搜索中文关键词会失败，改为 UTF-8
        self.connection._encoding = "utf-8"
        self.connection.login(self.username, self.password)
        logger.info("登录成功: %s", self.username)
        imap_id = ("name", "sungang", "contact", "sungsun@163.com", "version", "1.0.0", "vendor", "imaplib")
        self.connection.xatom('ID', '("' + '" "'.join(imap_id) + '")')
        logger.info("ID执行成功: %s", self.username)

    def disconnect(self) -> None:
        """断开连接"""
        if self.connection:
            try:
                self.connection.logout()
            except Exception:
                pass
            self.connection = None
            logger.info("已断开IMAP连接")

    def select_mailbox(self, mailbox: str = "INBOX") -> int:
        """选择邮箱文件夹，返回邮件总数"""
        status, data = self.connection.select(mailbox)
        if status != "OK":
            raise RuntimeError(f"无法打开邮箱文件夹: {mailbox}")
        count = int(data[0])
        logger.info("文件夹 [%s] 中共有 %d 封邮件", mailbox, count)
        return count


# ============================================================================
# 2. 邮件搜索与筛选
# ============================================================================

class MailSearcher:
    """邮件搜索与筛选器。

    注意：163 IMAP 的 SUBJECT/BODY 搜索对中文及特殊字符均不可靠（返回 0），
    因此只用 SINCE 拉取日期范围内候选，再批量拉取 SUBJECT 在客户端按关键词过滤。
    """

    def __init__(self, client: MailClient):
        self.client = client

    def build_search_criteria(self, days_back: int = 90) -> str:
        """构建 IMAP SINCE 搜索条件（仅按日期过滤）。"""
        since_date = (datetime.now() - timedelta(days=days_back)).strftime(
            "%d-%b-%Y"
        )
        criteria = f'(SINCE "{since_date}")'
        logger.info("搜索条件: %s", criteria)
        return criteria

    def fetch_candidates(self, days_back: int = 90) -> list[bytes]:
        """用 SINCE 拉取日期范围内的候选邮件 ID 列表。"""
        criteria = self.build_search_criteria(days_back)
        status, data = self.client.connection.search("UTF-8", criteria)
        if status != "OK":
            raise RuntimeError(f"邮件搜索失败, status={status}")
        ids = data[0].split()
        logger.info("SINCE 命中 %d 封候选邮件", len(ids))
        return ids

    def fetch_subjects(self, mail_ids: list[bytes]) -> dict[bytes, str]:
        """批量拉取多封邮件的 SUBJECT，返回 {mail_id: subject}。

        为避免逐封 RTT，分批批量 fetch 仅 SUBJECT 头。163 IMAP 的批量响应
        每封邮件形如三段:
            b'1 (BODY[HEADER.FIELDS (SUBJECT)] {71}'
            b'Subject: =?GBK?B?...?=\\r\\n\\r\\n'
            b')'
        逐段解析出邮件编号与主题。
        """
        subjects: dict[bytes, str] = {}
        step = 100
        for i in range(0, len(mail_ids), step):
            chunk = mail_ids[i : i + step]
            # 注意：IMAP message-set 必须是字符串，传 bytes 会导致命令畸形/返回空
            rng = f"{int(chunk[0])}:{int(chunk[-1])}"
            try:
                status, data = self.client.connection.fetch(
                    rng, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])"
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("批量拉取SUBJECT失败(%s)，回退逐封: %s", rng, e)
                status, data = "NO", []
            if status != "OK":
                # 回退：逐封拉取本批（message-set 同样用字符串）
                for mid in chunk:
                    try:
                        st, dd = self.client.connection.fetch(
                            str(int(mid)), "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])"
                        )
                        if st == "OK":
                            msg = email.message_from_bytes(dd[0][1])
                            subjects[mid] = MailParser.decode_str(msg.get("Subject"))
                    except Exception:  # noqa: BLE001
                        pass
                continue
            cur_mid: bytes | None = None
            for item in data:
                # 163 返回结构：每封邮件是 tuple(编号段, Subject段) 或单独 bytes
                parts = item if isinstance(item, tuple) else (item,)
                blob = b""
                for p in parts:
                    if isinstance(p, bytes):
                        blob += p
                if not blob:
                    continue
                # 本项可能同时含编号与 Subject（合并格式），也可能只有其一（拆分格式）
                m_id = re.match(rb"^(\d+)\s*\(", blob)
                if m_id:
                    cur_mid = m_id.group(1)
                if b"Subject:" in blob and cur_mid is not None:
                    sm = re.search(rb"Subject:\s*(.*)", blob, re.I | re.S)
                    if sm:
                        # 长主题会被折叠成多行 RFC2047 编码，先展开折叠续行再解码
                        unfolded = re.sub(rb"\r\n[ \t]+", b"", sm.group(1))
                        raw = unfolded.split(b"\r\n")[0]
                        raw_str = raw.decode("latin-1", "replace")
                        subjects[cur_mid] = MailParser.decode_str(raw_str).strip()
                    cur_mid = None
        return subjects

    def fetch_email(self, mail_id: bytes) -> email.message.Message | None:
        """根据邮件ID获取完整邮件内容"""
        status, data = self.client.connection.fetch(mail_id, "(RFC822)")
        if status != "OK":
            logger.warning("获取邮件 %s 失败", mail_id.decode())
            return None

        raw_email = data[0][1]
        return email.message_from_bytes(raw_email)


# ============================================================================
# 3. 邮件正文解析
# ============================================================================

class MailParser:
    """邮件解析器：解码邮件头、提取正文文本"""

    @staticmethod
    def decode_str(value: str | bytes | None) -> str:
        """解码邮件头中的编码字符串"""
        if value is None:
            return ""
        result_parts: list[str] = []
        for part, charset in decode_header(value):
            if isinstance(part, bytes):
                try:
                    result_parts.append(part.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result_parts.append(part.decode("utf-8", errors="replace"))
            else:
                result_parts.append(str(part))
        return "".join(result_parts)

    @staticmethod
    def get_mail_date(msg: email.message.Message) -> datetime | None:
        """提取邮件发送日期"""
        date_str = msg.get("Date")
        if date_str:
            try:
                return parsedate_to_datetime(date_str)
            except Exception:
                pass
        return None

    @classmethod
    def extract_text(cls, msg: email.message.Message) -> str:
        """递归提取邮件正文纯文本"""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                # 跳过附件
                if "attachment" in content_disposition:
                    continue

                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            return payload.decode(charset, errors="replace")
                        except (LookupError, UnicodeDecodeError):
                            return payload.decode("utf-8", errors="replace")

                if content_type == "text/html":
                    # 如果有text/plain优先用plain；否则提取html文本
                    continue

            # 如果没找到 text/plain，尝试 text/html
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                if "attachment" in content_disposition:
                    continue
                if content_type == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            html = payload.decode(charset, errors="replace")
                        except (LookupError, UnicodeDecodeError):
                            html = payload.decode("utf-8", errors="replace")
                        # 简单去除HTML标签
                        text = re.sub(r"<[^>]+>", "", html)
                        text = re.sub(r"&nbsp;", " ", text)
                        text = re.sub(r"\s+", " ", text).strip()
                        return text

        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset, errors="replace")
                except (LookupError, UnicodeDecodeError):
                    return payload.decode("utf-8", errors="replace")

        return ""

    @classmethod
    def extract_html(cls, msg: email.message.Message) -> str:
        """递归提取邮件正文中的 HTML 源码（用于表格结构化解析）"""
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in content_disposition:
                continue
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return payload.decode(charset, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        return payload.decode("utf-8", errors="replace")
        return ""

    @classmethod
    def parse_email(cls, msg: email.message.Message) -> dict:
        """解析单封邮件的关键信息"""
        subject = cls.decode_str(msg.get("Subject"))
        mail_date = cls.get_mail_date(msg)
        body_text = cls.extract_text(msg)
        html = cls.extract_html(msg)
        return {
            "subject": subject,
            "date": mail_date,
            "body": body_text,
            "html": html,
        }


# ============================================================================
# 4. 基金净值数据解析与清洗
# ============================================================================

class NAVDataParser:
    """
    基金净值数据解析器，从邮件正文中提取日期和净值。
    
    支持的常见格式：
        - 2024-01-15  净值: 1.2345
        - 2024/01/15  1.2345
        - 2024年1月15日  累计净值: 1.2345
        - 表格形式的净值数据
    """

    # 日期 + 净值 的正则模式（按优先级排列）
    PATTERNS = [
        # 模式0: YYYY-MM-DD 后面跟着净值数字（中文冒号/空格分隔）
        re.compile(
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})[^0-9]*?净值[^0-9]*?(\d+\.?\d*)",
            re.IGNORECASE,
        ),
        # 模式1: YYYY年MM月DD日 后面跟着净值
        re.compile(
            r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日[^0-9]*?"
            r"(?:单位\s*)?净值[^0-9]*?(\d+\.?\d*)",
            re.IGNORECASE,
        ),
        # 模式2: YYYY-MM-DD 后紧跟数字（制表符/空格分隔的表格行）
        re.compile(
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})\s+(\d+\.?\d+)",
        ),
        # 模式3: 日期在上，净值在紧邻的下一行
        re.compile(
            r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}).*?\n.*?(\d+\.?\d+)",
            re.DOTALL,
        ),
        # 模式4: YYYY年MM月DD日 后面跟数字
        re.compile(
            r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s+(\d+\.?\d+)",
        ),
    ]

    @classmethod
    def extract_nav_records(cls, text: str, html: str = "") -> list[dict]:
        """
        从邮件正文提取所有日期和净值记录。

        优先解析 HTML 表格结构（最可靠，单元格边界清晰）；
        若无 HTML 或解析失败，则回退到纯文本正则匹配。

        Args:
            text: 邮件纯文本正文（去标签后）
            html: 邮件原始 HTML 源码

        Returns:
            [{"date": datetime.date, "nav": float}, ...]
        """
        records: list[dict] = []
        seen_dates: set[str] = set()

        # 优先：从 HTML 表格解析
        if html:
            for rec in cls._extract_from_html(html):
                date_key = rec["date"].isoformat()
                if date_key not in seen_dates:
                    seen_dates.add(date_key)
                    records.append(rec)
            if records:
                logger.debug("HTML 表格解析命中 %d 条", len(records))

        # 回退：纯文本表格行匹配
        if not records:
            for rec in cls._extract_table_rows(text):
                date_key = rec["date"].isoformat()
                if date_key not in seen_dates:
                    seen_dates.add(date_key)
                    records.append(rec)

        # 最后兜底：正则匹配
        if not records:
            records = cls._extract_by_regex(text, seen_dates)

        # 按日期排序
        records.sort(key=lambda r: r["date"])
        return records

    @classmethod
    def _extract_from_html(cls, html: str) -> list[dict]:
        """
        通用 HTML 表格净值解析：依据表头「单位净值」列与日期列提取。
        兼容龙旗(净值日期|单位净值|累计单位净值)与幻方(日期|...|单位净值|复权净值)
        等不同表格结构；每封邮件通常只含一天一条净值记录。
        """
        tr_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
        cell_re = re.compile(
            r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL
        )

        rows: list[list[str]] = []
        for tr_match in tr_re.finditer(html):
            cells = [
                cls._clean_cell(m.group(1))
                for m in cell_re.finditer(tr_match.group(1))
            ]
            if cells:
                rows.append(cells)
        if not rows:
            return []

        # 定位表头中的「单位净值」列与日期列
        unit_idx: int | None = None
        date_idx: int | None = None
        header: list[str] | None = None
        for row in rows:
            for i, c in enumerate(row):
                cs = c.strip()
                if cs == "单位净值" and unit_idx is None:
                    unit_idx = i
                if cs in ("净值日期", "日期") and date_idx is None:
                    date_idx = i
            if unit_idx is not None:
                header = row
                break
        if unit_idx is None:
            return []

        records: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            if header is not None and row == header:
                continue
            # 日期：优先用表头日期列，否则在数据行内找日期格式单元格
            date_val = None
            if date_idx is not None and date_idx < len(row):
                date_val = row[date_idx]
            else:
                for c in row:
                    if re.match(r"^\d{4}[-/]?\d{1,2}[-/]?\d{1,2}$", c.strip()):
                        date_val = c.strip()
                        break
            # 净值：单位净值列
            nav_val = row[unit_idx] if unit_idx < len(row) else None
            if not date_val or not nav_val:
                continue
            parsed_date = cls._parse_date(date_val)
            nav = cls._parse_nav(nav_val)
            if parsed_date is None or nav is None:
                continue
            key = parsed_date.isoformat()
            if key not in seen:
                seen.add(key)
                records.append({"date": parsed_date, "nav": nav})
        return records

    @classmethod
    def _clean_cell(cls, raw: str) -> str:
        """清理单元格文本：去 HTML 标签、&nbsp;、首尾空白"""
        raw = re.sub(r"<[^>]+>", "", raw)
        raw = raw.replace("&nbsp;", " ")
        return raw.strip()

    @classmethod
    def _parse_date(cls, s: str) -> datetime.date | None:
        """解析多种日期格式: 2026-06-12 / 20200925 / 2026年06月12日"""
        s = s.strip()
        m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)  # 紧凑型 20200925
        if m:
            try:
                return datetime(
                    int(m.group(1)), int(m.group(2)), int(m.group(3))
                ).date()
            except ValueError:
                pass
        m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
        if m:
            try:
                return datetime(
                    int(m.group(1)), int(m.group(2)), int(m.group(3))
                ).date()
            except ValueError:
                pass
        m = re.match(r"^(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", s)
        if m:
            try:
                return datetime(
                    int(m.group(1)), int(m.group(2)), int(m.group(3))
                ).date()
            except ValueError:
                pass
        return None

    @classmethod
    def _parse_nav(cls, s: str) -> float | None:
        """从单元格文本中提取净值浮点数（去掉逗号/%/空白）"""
        s = s.strip().replace(",", "")
        m = re.search(r"\d+(?:\.\d+)?", s)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
        return None

    @classmethod
    def extract_product_name(cls, html: str) -> str:
        """从邮件 HTML 中提取产品名称，用于区分同一发送方下的不同基金。

        幻方：产品名在 <h3> 标签（如「幻方中证500量化多策略13号私募证券投资基金」），
             需排除「尊敬的 孙刚 先生...」之类的寒暄行。
        龙旗：产品名在表格的「产品名称」列。
        """
        if not html:
            return ""
        # 1) 幻方风格：<h3>产品名</h3>
        h3_re = re.compile(r"<h3[^>]*>(.*?)</h3>", re.IGNORECASE | re.DOTALL)
        for m in h3_re.finditer(html):
            name = cls._clean_cell(m.group(1))
            # 跳过寒暄/说明行
            if any(w in name for w in ("先生", "女士", "如下", "尊敬的", "您好")):
                continue
            if name:
                return name

        # 2) 龙旗风格：表格「产品名称」列
        tr_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
        cell_re = re.compile(
            r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL
        )
        rows: list[list[str]] = []
        for tr in tr_re.finditer(html):
            cells = [cls._clean_cell(c.group(1)) for c in cell_re.finditer(tr.group(1))]
            if cells:
                rows.append(cells)
        name_idx: int | None = None
        header: list[str] | None = None
        for row in rows:
            for i, c in enumerate(row):
                if c.strip() == "产品名称":
                    name_idx = i
                    header = row
                    break
            if name_idx is not None:
                break
        if name_idx is not None:
            for row in rows:
                if header is not None and row == header:
                    continue
                if name_idx < len(row) and row[name_idx]:
                    return row[name_idx]
        return ""

    @classmethod
    def _extract_table_rows(cls, text: str) -> list[dict]:
        """
        尝试识别文本中的表格行（一行包含日期和数字）。
        适用于类似以下格式：
            2024-01-15    1.2345
            2024-01-16    1.2350
        """
        records: list[dict] = []
        lines = text.strip().splitlines()

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 尝试匹配: 日期 ... 数字（行末）
            m = re.search(
                r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b.*?(\d+\.\d{2,})\s*$",
                line,
            )
            if m:
                date_str = m.group(1)
                nav_str = m.group(2)
                try:
                    parsed_date = datetime.strptime(
                        date_str.replace("/", "-"), "%Y-%m-%d"
                    ).date()
                    nav_value = float(nav_str)
                    records.append({"date": parsed_date, "nav": nav_value})
                except ValueError:
                    continue

        return records

    @classmethod
    def _extract_by_regex(cls, text: str, seen_dates: set[str]) -> list[dict]:
        """使用正则模式逐条匹配"""
        records: list[dict] = []

        for idx, pattern in enumerate(cls.PATTERNS):
            for m in pattern.finditer(text):
                try:
                    if idx in (1, 4):
                        # 中文日期：年 月 日 + 数字
                        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                        nav = float(m.group(4))
                        parsed_date = datetime(y, mo, d).date()
                    else:
                        date_str = m.group(1).replace("/", "-")
                        parsed_date = datetime.strptime(
                            date_str, "%Y-%m-%d"
                        ).date()
                        nav = float(m.group(2))

                    date_key = parsed_date.isoformat()
                    if date_key not in seen_dates:
                        seen_dates.add(date_key)
                        records.append({"date": parsed_date, "nav": nav})
                except (ValueError, IndexError):
                    continue

        return records


# ============================================================================
# 5. 表格生成
# ============================================================================

class TableGenerator:
    """将解析结果输出为结构化表格"""

    @staticmethod
    def to_dataframe(records: list[dict]) -> pd.DataFrame:
        """
        将净值记录列表转为 pandas DataFrame。

        Columns: 日期, 基金净值, 日涨跌幅(%)
        """
        if not records:
            logger.warning("没有数据可生成表格")
            return pd.DataFrame(columns=["日期", "基金净值", "日涨跌幅(%)"])

        df = pd.DataFrame(records)
        df["日期"] = pd.to_datetime(df["date"])
        df["基金净值"] = df["nav"].round(4)
        df = df.sort_values("日期").reset_index(drop=True)

        # 计算日涨跌幅
        df["日涨跌幅(%)"] = (
            df["基金净值"].pct_change() * 100
        ).round(4)

        # 选择并排序列
        result = df[["日期", "基金净值", "日涨跌幅(%)"]]
        return result

    @staticmethod
    def print_table(df: pd.DataFrame) -> None:
        """在控制台格式化打印表格"""
        if df.empty:
            print("没有数据。")
            return
        print("\n" + "=" * 65)
        print("  龙旗X计划私募证券投资基金B净值数据汇总")
        print("=" * 65)
        print(
            f"{'日期':<14} {'基金净值':>12} {'日涨跌幅(%)':>14}"
        )
        print("-" * 65)
        for _, row in df.iterrows():
            date_str = row["日期"].strftime("%Y-%m-%d")
            nav_str = f"{row['基金净值']:.4f}" if pd.notna(row["基金净值"]) else "N/A"
            chg_str = (
                f"{row['日涨跌幅(%)']:+.2f}%"
                if pd.notna(row["日涨跌幅(%)"])
                else "N/A"
            )
            print(f"{date_str:<14} {nav_str:>12} {chg_str:>14}")
        print("-" * 65)
        print(f"共 {len(df)} 条记录")
        if len(df) > 1:
            latest_nav = df.iloc[-1]["基金净值"]
            first_nav = df.iloc[0]["基金净值"]
            total_change = (latest_nav - first_nav) / first_nav * 100
            print(f"区间涨跌幅: {total_change:+.2f}%")
        print("=" * 65 + "\n")


# ============================================================================
# 6. 趋势曲线图绘制
# ============================================================================

class ChartDrawer:
    """使用 matplotlib 绘制基金净值趋势曲线"""

    @staticmethod
    def draw_line_chart(
        df: pd.DataFrame,
        save_path: str = "fund_nav_trend.png",
        title: str = "龙旗基金净值趋势图",
    ) -> None:
        """
        绘制基金净值折线图并保存。

        Args:
            df: 包含 日期/基金净值/日涨跌幅(%) 列的 DataFrame
            save_path: 图表保存路径
            title: 图表标题
        """
        if df.empty:
            logger.warning("没有数据，无法绘图")
            return

        # 配置中文字体（支持 Windows / macOS / Linux）
        plt.rcParams["font.sans-serif"] = [
            "Microsoft YaHei",
            "SimHei",
            "PingFang SC",
            "WenQuanYi Zen Hei",
            "WenQuanYi Micro Hei",
            "DejaVu Sans",
        ]
        plt.rcParams["axes.unicode_minus"] = False

        # 去除非数值行
        plot_df = df.dropna(subset=["基金净值"]).copy()
        dates = plot_df["日期"]
        navs = plot_df["基金净值"]

        if len(dates) < 2:
            logger.warning("数据量不足，无法绘制有意义的曲线（至少需要2个点）")
            return

        fig, ax1 = plt.subplots(figsize=(14, 7))

        # --- 主坐标轴：基金净值折线 ---
        color_nav = "#2C7FB8"
        ax1.set_xlabel("日期", fontsize=13)
        ax1.set_ylabel("基金净值", fontsize=13, color=color_nav)
        (line1,) = ax1.plot(
            dates,
            navs,
            marker="o",
            markersize=5,
            linewidth=2,
            color=color_nav,
            label="基金净值",
            zorder=5,
        )
        ax1.tick_params(axis="y", labelcolor=color_nav)
        ax1.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda y, _: f"{y:.4f}")
        )

        # 在每个数据点上标注净值
        for i, (d, n) in enumerate(zip(dates, navs)):
            offset = 8 if i % 2 == 0 else -16  # 交错标注避免重叠
            ax1.annotate(
                f"{n:.4f}",
                (d, n),
                textcoords="offset points",
                xytext=(0, offset),
                ha="center",
                fontsize=8,
                color=color_nav,
                alpha=0.85,
            )

        # --- 次坐标轴：涨跌幅柱状图 ---
        changes = plot_df["日涨跌幅(%)"]
        if changes.notna().any():
            ax2 = ax1.twinx()
            color_chg = "#E6550D"
            ax2.set_ylabel("日涨跌幅(%)", fontsize=13, color=color_chg)
            bars = ax2.bar(
                dates,
                changes.fillna(0),
                width=0.6,
                color=[
                    "#E6550D" if v >= 0 else "#2CA02C" if v < 0 else "#999"
                    for v in changes.fillna(0)
                ],
                alpha=0.35,
                label="日涨跌幅(%)",
                zorder=1,
            )
            ax2.tick_params(axis="y", labelcolor=color_chg)
            ax2.axhline(y=0, color="#999", linewidth=0.8, linestyle="--")

        # --- 标题与图例 ---
        start_str = dates.iloc[0].strftime("%Y-%m-%d")
        end_str = dates.iloc[-1].strftime("%Y-%m-%d")
        ax1.set_title(
            f"{title}\n({start_str} 至 {end_str}, 共{len(dates)}个交易日)",
            fontsize=16,
            fontweight="bold",
            pad=18,
        )

        # 合并图例
        lines = [line1]
        labels = ["基金净值"]
        if changes.notna().any():
            from matplotlib.patches import Patch
            lines.append(
                Patch(facecolor="#E6550D", alpha=0.35, label="日涨跌幅(%)")
            )
            labels.append("日涨跌幅(%)")
        ax1.legend(lines, labels, loc="upper left", fontsize=11)

        # --- 网格 ---
        ax1.grid(True, linestyle="--", alpha=0.35)
        ax1.set_axisbelow(True)

        # --- X轴日期格式 ---
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
        ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate(rotation=30, ha="right")

        # --- 调边距 ---
        y_min, y_max = navs.min(), navs.max()
        y_margin = (y_max - y_min) * 0.15 or 0.01
        ax1.set_ylim(y_min - y_margin, y_max + y_margin)

        fig.tight_layout()
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        logger.info("趋势图已保存至: %s", save_path)


# ============================================================================
# 7. 主控流程
# ============================================================================

def run(
    days_back: int = 3650,
    funds: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """
    执行完整流程：连接邮箱 -> 拉取候选 -> 客户端按主题粗筛 ->
    按邮件正文产品名细分到具体基金 -> 为每个基金生成 CSV 与趋势图。

    两只幻方基金的邮件主题完全相同（均为"幻方量化 YYYYMMDD 净值报告"），
    无法靠主题区分，必须依据邮件正文中的产品名（含"13号"/"20号"）细分。
    """
    logger.info("=" * 55)
    logger.info("  基金净值追踪工具")
    logger.info("=" * 55)

    client = MailClient()
    try:
        client.connect()
    except imaplib.IMAP4.error as e:
        logger.error(
            "IMAP登录失败: %s\n"
            "请确认:\n"
            "  1. 163邮箱已开启IMAP服务 (设置 > POP3/SMTP/IMAP)\n"
            "  2. 使用授权码而非登录密码\n"
            "  3. .env 文件中 MAIL_USERNAME / MAIL_PASSWORD 配置正确",
            e,
        )
        return {}

    try:
        client.select_mailbox("INBOX")

        # ---- Step 2: 拉取候选 + 批量获取主题 ----
        searcher = MailSearcher(client)
        candidate_ids = searcher.fetch_candidates(days_back=days_back)
        subjects = searcher.fetch_subjects(candidate_ids)
        logger.info("已获取 %d 封候选邮件的主题，开始按基金过滤", len(subjects))

        # ---- Step 3: 按主题粗筛候选，再按邮件正文产品名细分到具体基金 ----
        # 先构建每封邮件的候选基金列表（主题匹配），避免重复 fetch 同一封邮件
        mail_candidates: dict[bytes, list[dict]] = {}
        for mid, subj in subjects.items():
            cands = [cfg for cfg in FUND_CONFIGS if cfg["subject_keyword"] in subj]
            if cands:
                mail_candidates[mid] = cands

        records_by_fund: dict[str, list[dict]] = {
            cfg["key"]: [] for cfg in FUND_CONFIGS
        }
        for mid, cands in mail_candidates.items():
            msg = searcher.fetch_email(mid)
            if msg is None:
                continue
            info = MailParser.parse_email(msg)
            body = info["body"]
            html = info.get("html", "")
            if not body.strip() and not html.strip():
                continue

            product_name = NAVDataParser.extract_product_name(html)
            records = NAVDataParser.extract_nav_records(body, html=html)
            if not records:
                continue

            # 依据邮件正文中的产品名细分到具体基金
            target = None
            for cfg in cands:
                pk = cfg.get("product_keyword")
                if pk and pk in product_name:
                    target = cfg
                    break
            if target is None:
                if len(cands) == 1:
                    target = cands[0]
                else:
                    # 多候选但产品名无法细分，跳过以免错归
                    logger.debug(
                        "  [%s] 产品名「%s」无法匹配候选基金，跳过",
                        info["subject"],
                        product_name,
                    )
                    continue

            records_by_fund[target["key"]].extend(records)
            logger.info(
                "  [%s] %s -> 提取 %d 条", target["name"], info["subject"], len(records)
            )

        # ---- Step 4: 为每个基金生成表格与趋势图（受 --funds 过滤） ----
        results: dict[str, pd.DataFrame] = {}
        for cfg in FUND_CONFIGS:
            if funds and cfg["key"] not in funds:
                continue
            recs = records_by_fund.get(cfg["key"], [])
            if not recs:
                logger.warning("[%s] 未提取到净值数据", cfg["name"])
                continue

            df = TableGenerator.to_dataframe(recs)
            TableGenerator.print_table(df)

            csv_path = f"{cfg['output_prefix']}_data.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            logger.info("[%s] 数据表格已保存至: %s", cfg["name"], csv_path)

            png_path = f"{cfg['output_prefix']}_trend.png"
            ChartDrawer.draw_line_chart(
                df, save_path=png_path, title=f"{cfg['name']} 净值趋势图"
            )

            results[cfg["key"]] = df

        return results

    finally:
        client.disconnect()



if __name__ == "__main__":
    import argparse

    available = " ".join(c["key"] for c in FUND_CONFIGS)
    parser = argparse.ArgumentParser(
        description="基金净值邮件追踪工具（支持多基金）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
示例:
  python fund_nav_tracker.py                      # 处理全部基金，全量历史
  python fund_nav_tracker.py --days 90            # 仅最近90天
  python fund_nav_tracker.py --funds longqi       # 仅处理龙旗
  python fund_nav_tracker.py --funds {available}  # 指定基金

可用基金 key: {available}
        """,
    )
    parser.add_argument(
        "--days",
        type=int,
        default=3650,
        help="搜索最近多少天的邮件 (默认: 3650=全量历史)",
    )
    parser.add_argument(
        "--funds",
        nargs="*",
        default=None,
        help=f"仅处理指定基金 key (默认: 全部)，可选: {available}",
    )
    args = parser.parse_args()

    results = run(days_back=args.days, funds=args.funds)

    total = sum(len(df) for df in results.values())
    if not results:
        logger.warning("未获取到有效数据，程序退出。")
    else:
        logger.info(
            "程序运行完毕，共处理 %d 个基金、%d 条净值记录。",
            len(results),
            total,
        )
