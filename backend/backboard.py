import json
from typing import Any, Dict, Iterable, List, Optional

import httpx
from fastapi import HTTPException


DEFAULT_API_BASE_URL = "https://app.backboard.io/api"


class BackboardClient:
    def __init__(self, api_key: Optional[str], api_base_url: Optional[str] = None):
        self.api_key = api_key
        self.api_base_url = (api_base_url or DEFAULT_API_BASE_URL).rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            # Backboard expects X-API-Key, so send both common casings for safety
            headers["X-API-Key"] = self.api_key
            headers["x-api-key"] = self.api_key
        return headers

    async def _request_with_fallback(
        self,
        method: str,
        path_candidates: Iterable[str],
        *,
        json_payload: Optional[Dict[str, Any]] = None,
        data_payload: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        errors: List[str] = []
        if json_payload is not None and data_payload is not None:
            raise ValueError("Provide only one of json_payload or data_payload")

        for path in path_candidates:
            url = f"{self.api_base_url}/{path.lstrip('/')}"
            try:
                response = await self._client.request(
                    method,
                    url,
                    json=json_payload,
                    data=data_payload,
                    files=files,
                    headers=self._headers(),
                )
            except httpx.HTTPError as exc:
                errors.append(f"{url}: {exc}")
                continue

            if response.status_code in (401, 403):
                detail = self._extract_error_message(response)
                raise HTTPException(status_code=response.status_code, detail=f"Backboard auth failed: {detail}")

            if response.status_code >= 500:
                errors.append(f"{url}: {response.status_code} {response.text}")
                # try the next candidate in case this path is wrong
                continue

            if response.status_code in (404, 405):
                errors.append(f"{url}: {response.status_code}")
                continue

            if response.status_code >= 400:
                detail = self._extract_error_message(response)
                raise HTTPException(status_code=response.status_code, detail=f"Backboard error: {detail}")

            try:
                return response.json()
            except ValueError:
                raise HTTPException(status_code=502, detail="Backboard returned non-JSON response")

        if errors:
            raise HTTPException(
                status_code=502,
                detail=f"Unable to reach Backboard endpoints. Tried: {'; '.join(errors)}",
            )
        raise HTTPException(status_code=502, detail="Backboard request failed without a response.")

    @staticmethod
    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                for key in ("message", "error", "detail"):
                    if key in payload and isinstance(payload[key], str):
                        return payload[key]
            return response.text
        except ValueError:
            return response.text

    @staticmethod
    def _extract_assistant_text(payload: Any) -> Optional[str]:
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            for key in (
                "assistant_text",
                "assistant_response",
                "response",
                "text",
                "content",
                "message",
            ):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value
                if isinstance(value, dict):
                    nested = value.get("content") or value.get("text")
                    if isinstance(nested, str) and nested.strip():
                        return nested
            message = payload.get("message")
            if isinstance(message, dict):
                nested = message.get("text") or message.get("content")
                if isinstance(nested, str) and nested.strip():
                    return nested
            messages = payload.get("messages")
            if isinstance(messages, list):
                for item in messages:
                    if not isinstance(item, dict):
                        continue
                    if item.get("role") == "assistant":
                        maybe = item.get("content") or item.get("text")
                        if isinstance(maybe, str) and maybe.strip():
                            return maybe
            data = payload.get("data")
            if isinstance(data, dict):
                return BackboardClient._extract_assistant_text(data)
        if isinstance(payload, list):
            for item in payload:
                extracted = BackboardClient._extract_assistant_text(item)
                if extracted:
                    return extracted
        return None

    async def create_assistant(self, name: str) -> str:
        payload = {"name": name, "display_name": name}
        paths = [
            "assistants",
            "assistant",
            "v1/assistants",
            "api/v1/assistants",
            "api/assistants",
        ]
        response = await self._request_with_fallback("POST", paths, json_payload=payload)
        assistant_id = (
            response.get("id")
            or response.get("assistant_id")
            or response.get("assistantId")
            or response.get("data", {}).get("id")
        )
        if not assistant_id:
            raise HTTPException(status_code=502, detail="Backboard did not return an assistant_id")
        return str(assistant_id)

    async def create_thread(self, assistant_id: str) -> str:
        payload = {
            "assistant_id": assistant_id,
            "assistantId": assistant_id,
        }
        paths = [
            f"assistants/{assistant_id}/threads",
            f"api/assistants/{assistant_id}/threads",
            f"v1/assistants/{assistant_id}/threads",
            f"api/v1/assistants/{assistant_id}/threads",
            "v1/threads",
            "threads",
            "thread",
            "v1/threads/create",
            "threads/create",
            "api/v1/threads",
            "api/threads",
            "api/threads/create",
        ]
        response = await self._request_with_fallback("POST", paths, json_payload=payload)
        thread_id = (
            response.get("id")
            or response.get("thread_id")
            or response.get("threadId")
            or response.get("data", {}).get("id")
        )
        if not thread_id:
            raise HTTPException(status_code=502, detail="Backboard did not return a thread_id")
        return str(thread_id)

    async def send_message(
        self,
        *,
        thread_id: str,
        message: str,
        send_to_llm: bool,
        memory: str = "Auto",
        assistant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload = {
            "thread_id": thread_id,
            "threadId": thread_id,
            "content": message,
            "stream": "false",
            "send_to_llm": send_to_llm,
            "memory": memory,
        }
        paths = [
            f"threads/{thread_id}/messages",
            f"assistants/{assistant_id}/threads/{thread_id}/messages" if assistant_id else None,
            f"api/assistants/{assistant_id}/threads/{thread_id}/messages" if assistant_id else None,
            f"v1/assistants/{assistant_id}/threads/{thread_id}/messages" if assistant_id else None,
            f"api/v1/assistants/{assistant_id}/threads/{thread_id}/messages" if assistant_id else None,
            f"v1/threads/{thread_id}/messages",
            "v1/messages",
            "messages",
            f"api/v1/threads/{thread_id}/messages",
            f"api/threads/{thread_id}/messages",
            "api/v1/messages",
            "api/messages",
        ]
        return await self._request_with_fallback("POST", [p for p in paths if p], data_payload=payload)

    async def extract_assistant_text(self, payload: Dict[str, Any]) -> Optional[str]:
        return self._extract_assistant_text(payload)
