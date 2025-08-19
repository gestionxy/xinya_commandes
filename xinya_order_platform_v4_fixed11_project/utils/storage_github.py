
from __future__ import annotations
import base64, requests
from typing import Optional
class GitHubStorage:
    def __init__(self, token: str, repo: str, branch: str = "main", base_path: str = ""):
        self.token = token.strip()
        self.repo = repo.strip()
        self.branch = (branch or "main").strip()
        self.base_path = base_path.strip().strip("/")
        self.api = f"https://api.github.com/repos/{self.repo}/contents"
    def _headers(self):
        return {"Authorization": f"token {self.token}", "Accept": "application/vnd.github+json"}
    def _fullpath(self, path: str) -> str:
        path = path.strip().lstrip("/")
        if self.base_path:
            return f"{self.base_path}/{path}"
        return path
    def _get_sha_if_exists(self, path: str) -> Optional[str]:
        import requests as _r
        url = f"{self.api}/{path}?ref={self.branch}"
        r = _r.get(url, headers=self._headers(), timeout=30)
        if r.status_code == 200:
            return r.json().get("sha")
        return None
    def upload_bytes(self, path: str, content: bytes, commit_message: str = "update via streamlit") -> dict:
        path = self._fullpath(path)
        url = f"{self.api}/{path}"
        sha = self._get_sha_if_exists(path)
        payload = {"message": commit_message, "branch": self.branch, "content": base64.b64encode(content).decode("utf-8")}
        if sha: payload["sha"] = sha
        r = requests.put(url, headers=self._headers(), json=payload, timeout=60)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"GitHub upload failed: {r.status_code} {r.text}")
        return r.json()
