from imapclient import IMAPClient
import imapclient
from email import message_from_bytes
from email.header import decode_header
from datetime import datetime


'''
通过imapclient实现本地邮箱与网上邮箱连接管理，实现包括新邮件下载（收件箱和垃圾邮件），邮件移动，邮件删除等
基础邮箱功能。每隔2分钟（用户可调节）更新网上邮箱的列表下载相关新邮件。用户在本地对邮件的操作，除了彻底删除
邮件以外，不会对云端邮件进行影响（例如，从收件下载下来的邮件1，在本地删除放入回收站时，不需要在网上邮箱进行
相应地把邮件放入网上邮箱的回收站，但当用户把本地回收站的邮件1彻底删除时候，才在网上邮箱彻底删除该邮件）。

更新邮件方式：上次更新后保存了最后一封邮件的uid（lastUid），通过搜索识别lastUid的邮件为新邮件，下载到本地进行操作。
收件箱邮件接收后经过AI处理，经过垃圾邮件再过滤，生成摘要，提取分类，识别任务等步骤，合并统一json文件后本地
保存，保存后被UI读取显示到本地智能邮箱程序中。垃圾邮件接收后经AI再次检测是否为真垃圾邮件，如果为否，移动到
收件箱再进行邮箱处理。
'''

class mailIMAP:
    def __init__(self, EMAIL, AUTHOR_CODE):

        self.EMAIL = EMAIL
        self.AUTHOR_CODE = AUTHOR_CODE
        self.login()

    
    def downloadMails(self, lastUid):

        
        # 打开收件箱
        self.server.select_folder('INBOX')

        # 在收件箱中搜索lastUid以后的邮件并下载
        newMessages_INBOX = self.server.search(['UID', f'{lastUid+1}:*'])
        if newMessages_INBOX:

            newLastUid_INBOX = newMessages_INBOX[-1]

            for uid, data in self.server.fetch(newMessages_INBOX, ['ENVELOPE', 'RFC822']).items():
                envelope = data[b'ENVELOPE']
                ...
                # 每逢邮件下载后经过AI处理
                # self.newMailPreprocess(message, ai_provider)
                ...

        else:
            newLastUid_INBOX = lastUid

        # 搜索垃圾邮件箱
        self.server.select_folder('垃圾邮件')

        # 在垃圾邮件箱中搜索lastUid以后的邮件并下载
        newMessages_JUNK = self.server.search(['UID', f'{lastUid+1}:*'])
        if newMessages_JUNK:

            newLastUid_JUNK = newMessages_JUNK[-1]

            for uid, data in self.server.fetch(newMessages_JUNK, ['ENVELOPE', 'RFC822']).items():
                envelope = data[b'ENVELOPE']
                ...
                # 每逢邮件下载后经过AI处理
                # self.junkMailsVerify(message, ai_provider)
                ...

        else:
            newLastUid_JUNK = lastUid

        
        
        # 更新lastUid
        newLastUid = max(newLastUid_INBOX, newLastUid_JUNK)

        return newLastUid
    
    
    def newMailPreprocess(self, message, ai_provider):
        # 将邮件原文
        ...

    
    def junkMailsVerify(self, message, ai_provider):
        # 通过OpenClaw再次检测message是否为垃圾邮件：
        # 如果是，放入垃圾邮件文件夹。
        # 如果不是，该邮箱当作新邮件转入收件箱，然后进行AI处理。
        ...
    
    def mailDeletion(self, uid):

        # 彻底删除回收站中的标记为uid的邮件
        self.server.add_flags(uid, '\\Deleted')
        self.server.expunge() 
        ...

    def login(self):
        # 登录到邮件
        self.server = IMAPClient("imap.163.com", ssl=True, port=993)
        self.server.login(self.EMAIL, self.AUTHOR_CODE)
        self.server.id_({"name": "IMAPClient", "version": str(imapclient.__version__)})

    def logout(self):
        # 退出登录
        self.server.logout()




if __name__ == "main":

    RECEIVER_EMAIL = "ClawMail001@163.com"
    AUTHORIZATION_CODE = "NPY2kzXDN3GCkc5i"