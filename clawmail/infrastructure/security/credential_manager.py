"""
CredentialManager — 双层加密凭据管理
设计规范：design/tech_spec.md 第 4 节安全设计

加密层次：
  明文密码
    └── Fernet.encrypt(master_key) → 密文 BLOB，存入 accounts.credentials_encrypted
  主密钥：
    - macOS  → macOS Keychain（via keyring）
    - Windows → Windows Credential Manager（via keyring）
    - Linux  → SecretService / keyrings.alt
"""

import keyring
from cryptography.fernet import Fernet

KEYRING_SERVICE = "clawmail"
KEYRING_KEY_ACCOUNT = "master_key"


class CredentialManager:

    def _get_or_create_master_key(self) -> bytes:
        """从 OS Keychain 读取主密钥，不存在则生成并保存。"""
        key = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_ACCOUNT)
        if key is None:
            key = Fernet.generate_key().decode()
            keyring.set_password(KEYRING_SERVICE, KEYRING_KEY_ACCOUNT, key)
        return key.encode()

    def encrypt_credentials(self, plaintext: str) -> bytes:
        """加密邮箱密码/授权码，返回密文 BLOB 存入数据库。"""
        f = Fernet(self._get_or_create_master_key())
        return f.encrypt(plaintext.encode())

    def decrypt_credentials(self, ciphertext: bytes) -> str:
        """解密从数据库读取的密文，返回明文密码。"""
        f = Fernet(self._get_or_create_master_key())
        return f.decrypt(ciphertext).decode()
