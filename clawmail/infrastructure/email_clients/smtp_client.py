"""
ClawSMTPClient — 异步 SMTP 发件客户端
使用 aiosmtplib 3.0.1，支持 SSL（port 465）。
"""

import mimetypes
import os
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from clawmail.domain.models.account import Account


class SMTPSendError(Exception):
    pass


class ClawSMTPClient:
    """无状态 SMTP 发件封装，每次调用独立建立连接。"""

    async def send_email(
        self,
        account: Account,
        password: str,
        to_addresses: list,
        subject: str,
        body: str,
        cc_addresses: list = None,
        html_body: str = None,
        attachments: list = None,   # 文件路径列表
    ) -> None:
        """
        发送邮件。
        - 提供 html_body 时发送 multipart/alternative（HTML + 纯文本降级）。
        - 提供 attachments 时外层升级为 multipart/mixed，内层保留 alternative。
        to_addresses / cc_addresses：邮箱地址字符串列表。
        出错时抛出 SMTPSendError。
        """
        # 构建文本/HTML 内容部分
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body, "plain", "utf-8"))
        if html_body:
            alt.attach(MIMEText(html_body, "html", "utf-8"))

        if attachments:
            # 有附件：外层用 mixed，内层嵌 alternative
            msg = MIMEMultipart("mixed")
            msg.attach(alt)
            for path in attachments:
                try:
                    ctype, encoding = mimetypes.guess_type(path)
                    if ctype is None or encoding is not None:
                        ctype = "application/octet-stream"
                    maintype, subtype = ctype.split("/", 1)
                    with open(path, "rb") as f:
                        data = f.read()
                    part = MIMEBase(maintype, subtype)
                    part.set_payload(data)
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition", "attachment",
                        filename=os.path.basename(path),
                    )
                    msg.attach(part)
                except OSError:
                    pass   # 文件读取失败时跳过，不中断发送
        else:
            # 无附件：直接用 alternative（保持原结构）
            msg = alt

        from_name = account.display_name or account.email_address
        msg["From"] = f"{from_name} <{account.email_address}>"
        msg["To"] = ", ".join(to_addresses)
        msg["Subject"] = subject
        if cc_addresses:
            msg["Cc"] = ", ".join(cc_addresses)

        try:
            await aiosmtplib.send(
                msg,
                hostname=account.smtp_server or "smtp.163.com",
                port=account.smtp_port or 465,
                use_tls=True,
                username=account.email_address,
                password=password,
            )
        except Exception as e:
            raise SMTPSendError(str(e)) from e
