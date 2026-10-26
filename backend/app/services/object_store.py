from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Protocol

from app.config import settings
from app.core.errors import ApiError

_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _validate_key(key: str) -> None:
    if not _SAFE_KEY.match(key) or ".." in key.split("/") or key.startswith("/"):
        raise ValueError("invalid object key")


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def presigned_url(self, key: str, expires_seconds: int) -> str | None: ...


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        _validate_key(key)
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise ValueError("object key escapes storage root")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass

    def presigned_url(self, key: str, expires_seconds: int) -> str | None:
        return None


class S3ObjectStore:
    def __init__(self) -> None:
        import boto3
        from botocore.config import Config

        self.bucket = settings.S3_BUCKET
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            aws_access_key_id=settings.S3_ACCESS_KEY or None,
            aws_secret_access_key=settings.S3_SECRET_KEY or None,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        _validate_key(key)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    def get(self, key: str) -> bytes:
        _validate_key(key)
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def open(self, key: str) -> BinaryIO:
        _validate_key(key)
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"]

    def delete(self, key: str) -> None:
        _validate_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presigned_url(self, key: str, expires_seconds: int) -> str | None:
        _validate_key(key)
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )


_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    global _store
    if _store is None:
        if settings.STORAGE_BACKEND.lower() == "s3":
            _store = S3ObjectStore()
        elif settings.STORAGE_BACKEND.lower() == "local":
            _store = LocalObjectStore(settings.OBJECT_STORE_DIR)
        else:
            raise RuntimeError(f"Unsupported STORAGE_BACKEND: {settings.STORAGE_BACKEND}")
    return _store


def _signing_key() -> bytes:
    key = settings.download_signing_key
    if not key:
        raise RuntimeError("DOWNLOAD_SIGNING_KEY or JWT_SECRET is not configured")
    return key.encode("utf-8")


def sign_local_download(version_id: uuid.UUID, expires_at: int) -> str:
    message = f"{version_id}:{expires_at}".encode("utf-8")
    signature = hmac.new(_signing_key(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")


def verify_local_download(version_id: uuid.UUID, expires_at: int, signature: str) -> None:
    if expires_at < int(time.time()):
        raise ApiError(403, "FORBIDDEN", "Download link expired.")
    expected = sign_local_download(version_id, expires_at)
    if not hmac.compare_digest(expected, signature):
        raise ApiError(403, "FORBIDDEN", "Invalid download link.")


def build_download_url(version_id: uuid.UUID, expires_seconds: int = 300) -> tuple[str, datetime]:
    expires_at = int(time.time()) + expires_seconds
    signature = sign_local_download(version_id, expires_at)
    url = (
        f"{settings.API_V1_STR}/document-versions/{version_id}/content"
        f"?expires={expires_at}&signature={signature}"
    )
    return url, datetime.fromtimestamp(expires_at, tz=timezone.utc)
