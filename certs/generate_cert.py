# -*- coding: utf-8 -*-
"""
자가 서명 SSL 인증서 생성 스크립트.
"""

from __future__ import annotations

import datetime
import importlib
import ipaddress
import os
import socket
import sys
from typing import Any


def _load_cryptography() -> tuple[Any, Any, Any, Any, Any, Any] | None:
    try:
        x509 = importlib.import_module("cryptography.x509")
        oid_module = importlib.import_module("cryptography.x509.oid")
        primitives_module = importlib.import_module("cryptography.hazmat.primitives")
        backends_module = importlib.import_module("cryptography.hazmat.backends")
        asymmetric_module = importlib.import_module("cryptography.hazmat.primitives.asymmetric")
    except Exception:
        return None

    return (
        x509,
        oid_module.NameOID,
        primitives_module.hashes,
        backends_module.default_backend,
        asymmetric_module.rsa,
        primitives_module.serialization,
    )


def ipaddress_from_string(ip_string: str):
    """문자열 IP 주소를 ipaddress 객체로 변환한다."""
    return ipaddress.ip_address(ip_string)


def generate_certificate(cert_path: str, key_path: str) -> bool:
    """자가 서명 SSL 인증서를 생성한다."""
    cryptography_modules = _load_cryptography()
    if cryptography_modules is None:
        print("cryptography 라이브러리가 필요합니다.")
        print("설치: pip install cryptography")
        return False

    x509, NameOID, hashes, default_backend, rsa, serialization = cryptography_modules

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except socket.error:
        local_ip = "127.0.0.1"

    san_list = [
        x509.DNSName("localhost"),
        x509.DNSName(hostname),
        x509.IPAddress(ipaddress_from_string("127.0.0.1")),
    ]
    if local_ip != "127.0.0.1":
        san_list.append(x509.IPAddress(ipaddress_from_string(local_ip)))

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "KR"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Seoul"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Seoul"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Internal Messenger"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .sign(key, hashes.SHA256(), default_backend())
    )

    os.makedirs(os.path.dirname(cert_path), exist_ok=True)

    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print("인증서 생성 완료:")
    print(f"  - 인증서: {cert_path}")
    print(f"  - 개인키: {key_path}")
    print(f"  - 호스트: {hostname}")
    print(f"  - IP: {local_ip}")
    print("  - 유효기간: 365일")
    return True


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cert_path = os.path.join(script_dir, "cert.pem")
    key_path = os.path.join(script_dir, "key.pem")

    if os.path.exists(cert_path) and os.path.exists(key_path):
        response = input("기존 인증서가 있습니다. 다시 생성하시겠습니까? (y/N): ")
        if response.lower() != "y":
            print("취소했습니다.")
            sys.exit(0)

    generate_certificate(cert_path, key_path)
