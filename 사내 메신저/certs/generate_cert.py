# -*- coding: utf-8 -*-
"""
SSL 인증서 생성 스크립트
자체 서명 인증서를 생성합니다.
"""

import os
import sys
import socket
import datetime

def generate_certificate(cert_path, key_path):
    """자체 서명 SSL 인증서 생성"""
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        print("cryptography 라이브러리가 필요합니다.")
        print("설치: pip install cryptography")
        return False
    
    # 키 생성
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # 호스트명 및 IP 수집
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except socket.error:
        local_ip = "127.0.0.1"
    
    # Subject Alternative Names
    san_list = [
        x509.DNSName("localhost"),
        x509.DNSName(hostname),
        x509.IPAddress(ipaddress_from_string("127.0.0.1")),
    ]
    
    if local_ip != "127.0.0.1":
        san_list.append(x509.IPAddress(ipaddress_from_string(local_ip)))
    
    # 인증서 생성
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "KR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Seoul"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Seoul"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Internal Messenger"),
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])
    
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )
    
    # 디렉토리 생성
    os.makedirs(os.path.dirname(cert_path), exist_ok=True)
    
    # 키 저장
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # 인증서 저장
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    print(f"인증서 생성 완료:")
    print(f"  - 인증서: {cert_path}")
    print(f"  - 개인키: {key_path}")
    print(f"  - 호스트: {hostname}")
    print(f"  - IP: {local_ip}")
    print(f"  - 유효기간: 365일")
    return True


def ipaddress_from_string(ip_string):
    """IP 주소 문자열을 ipaddress 객체로 변환"""
    import ipaddress
    return ipaddress.ip_address(ip_string)


if __name__ == "__main__":
    # 스크립트 위치 기준으로 경로 설정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cert_path = os.path.join(script_dir, "cert.pem")
    key_path = os.path.join(script_dir, "key.pem")
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        response = input("기존 인증서가 있습니다. 재생성하시겠습니까? (y/N): ")
        if response.lower() != 'y':
            print("취소되었습니다.")
            sys.exit(0)
    
    generate_certificate(cert_path, key_path)
