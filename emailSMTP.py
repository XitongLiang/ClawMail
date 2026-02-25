import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

# 163 邮箱配置
SMTP_SERVER = 'smtp.163.com'
SMTP_PORT = 465  # SSL 端口
SENDER_EMAIL = 'ClawMail001@163.com'  # 你的 163 邮箱地址
AUTHORIZATION_CODE = 'NPY2kzXDN3GCkc5i'  # 163 邮箱授权码（不是登录密码！）


def send_email(receiver, subject, body, is_html=False):
    """
    发送邮件
    :param receiver: 收件人邮箱
    :param subject: 邮件主题
    :param body: 邮件正文
    :param is_html: 是否为 HTML 格式
    """
    # 创建邮件对象
    msg = MIMEMultipart()
    msg['From'] = Header(f'发件人昵称 <{SENDER_EMAIL}>', 'utf-8')
    msg['To'] = Header(receiver, 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    
    # 添加邮件正文
    content_type = 'html' if is_html else 'plain'
    msg.attach(MIMEText(body, content_type, 'utf-8'))
    
    try:
        # 连接 SMTP 服务器（使用 SSL）
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.set_debuglevel(1)  # 开启调试模式，查看详细日志（可选）
            
            # 登录（使用授权码，不是邮箱密码）
            server.login(SENDER_EMAIL, AUTHORIZATION_CODE)
            
            # 发送邮件
            server.sendmail(SENDER_EMAIL, receiver, msg.as_string())
            print(f"✅ 邮件发送成功！收件人: {receiver}")
            
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ 认证失败: {e}")
        print("提示：请检查是否使用了正确的授权码（不是登录密码）")
    except Exception as e:
        print(f"❌ 发送失败: {e}")


if __name__ == "__main__":
    # ============ 使用示例 ============

# 示例 1：发送纯文本邮件
    send_email(
        receiver='xitong.liang@outlook.com',
        subject='测试邮件 - 纯文本',
        body='你好，这是一封来自 Python 的测试邮件！\n\n这是第二行内容。'
    )
