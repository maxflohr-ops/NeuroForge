#!/usr/bin/env python3
"""
Drive Agent
Owns the shared "Ridge Club YouTube" folder structure and handles resumable uploads.

    <root>/01 Full Videos/<file>.mp4
    <root>/02 Opus Clips/<video title> [id]/<clip>.mp4

Works on both My Drive and Shared Drives (supportsAllDrives everywhere).
"""

from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import Config

SCOPES = ["https://www.googleapis.com/auth/drive"]
CHUNK_SIZE = 32 * 1024 * 1024  # 32 MB resumable-upload chunks


class DriveAgent:
    def __init__(self, config: Config):
        self.config = config
        creds = service_account.Credentials.from_service_account_file(
            str(config.service_account_file), scopes=SCOPES)
        self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
        self._folder_cache = {}  # (parent_id, name) -> folder_id

    # ── folders ──────────────────────────────────────────────────
    def ensure_folder(self, name: str, parent_id: str) -> str:
        """Find or create a folder under parent_id, cached per run."""
        key = (parent_id, name)
        if key in self._folder_cache:
            return self._folder_cache[key]

        escaped = name.replace("'", "\\'")
        query = (f"name = '{escaped}' and '{parent_id}' in parents "
                 "and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
        result = self.service.files().list(
            q=query, fields="files(id)", pageSize=1,
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        files = result.get("files", [])
        if files:
            folder_id = files[0]["id"]
        else:
            meta = {"name": name, "mimeType": "application/vnd.google-apps.folder",
                    "parents": [parent_id]}
            folder_id = self.service.files().create(
                body=meta, fields="id", supportsAllDrives=True).execute()["id"]

        self._folder_cache[key] = folder_id
        return folder_id

    def full_videos_folder(self) -> str:
        return self.ensure_folder(self.config.full_videos_folder_name,
                                  self.config.drive_root_folder_id)

    def clips_folder_for(self, video_folder_name: str) -> str:
        clips_root = self.ensure_folder(self.config.opus_clips_folder_name,
                                        self.config.drive_root_folder_id)
        return self.ensure_folder(video_folder_name, clips_root)

    # ── uploads ──────────────────────────────────────────────────
    def find_file(self, name: str, parent_id: str):
        escaped = name.replace("'", "\\'")
        query = f"name = '{escaped}' and '{parent_id}' in parents and trashed = false"
        result = self.service.files().list(
            q=query, fields="files(id)", pageSize=1,
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        files = result.get("files", [])
        return files[0]["id"] if files else None

    def upload_file(self, local_path: Path, parent_id: str) -> str:
        """Resumable upload; skips if a file with the same name already exists."""
        existing = self.find_file(local_path.name, parent_id)
        if existing:
            return existing

        media = MediaFileUpload(str(local_path), chunksize=CHUNK_SIZE, resumable=True)
        request = self.service.files().create(
            body={"name": local_path.name, "parents": [parent_id]},
            media_body=media, fields="id", supportsAllDrives=True)

        response = None
        while response is None:
            _status, response = request.next_chunk(num_retries=5)
        return response["id"]
