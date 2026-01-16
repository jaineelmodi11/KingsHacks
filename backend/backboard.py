# backend/backboard.py
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
    ) -> Any:
        """
        Try multiple endpoint candidates until one succeeds.
        Returns the decoded JSON payload (dict OR list OR primitive).
        """
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
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Backboard auth failed: {detail}",
                )

            if response.status_code >= 500:
                errors.append(f"{url}: {response.status_code} {response.text}")
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
        assistant_id = None
        if isinstance(response, dict):
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
        thread_id = None
        if isinstance(response, dict):
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
    ) -> Any:
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

    # -----------------------------
    # Memory retrieval helpers
    # -----------------------------

    @staticmethod
    def extract_retrieved_memories(payload: Any) -> List[Dict[str, Any]]:
        """
        Extract retrieved memories from a Backboard response.
        Supports multiple possible response shapes/keys.
        Normalizes strings into {"memory": "..."} dicts.
        """
        def _normalize_list(lst: Any) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            if not isinstance(lst, list):
                return out
            for x in lst:
                if isinstance(x, dict):
                    out.append(x)
                elif isinstance(x, str) and x.strip():
                    out.append({"memory": x.strip()})
            return out

        if payload is None:
            return []

        if isinstance(payload, dict):
            for key in (
                "retrieved_memories",
                "retrievedMemories",
                "retrieval_memories",
                "memory_hits",
                "retrievals",
                "memories",
                "results",
            ):
                norm = _normalize_list(payload.get(key))
                if norm:
                    return norm

            for key in ("data", "message", "response", "raw_response", "run", "output"):
                nested = payload.get(key)
                out = BackboardClient.extract_retrieved_memories(nested)
                if out:
                    return out

        if isinstance(payload, list):
            for item in payload:
                out = BackboardClient.extract_retrieved_memories(item)
                if out:
                    return out

        return []

    @staticmethod
    def _normalize_memories_payload(payload: Any) -> List[Dict[str, Any]]:
        """
        Normalize Backboard 'list memories' responses into:
          [{"memory": "<string>"}, ...]
        Accepts shapes like:
          {"memories":[{"content":"..."}, ...]}
          {"data":{"memories":[...]}}
          [{"content":"..."}, ...]
        """
        def wrap_item(x: Any) -> Optional[Dict[str, Any]]:
            if isinstance(x, dict):
                content = x.get("content") or x.get("memory") or x.get("text")
                if isinstance(content, str) and content.strip():
                    # keep extra fields if present
                    extra = {k: v for k, v in x.items() if k not in ("content", "memory", "text")}
                    return {"memory": content.strip(), **extra}
                return None
            if isinstance(x, str) and x.strip():
                return {"memory": x.strip()}
            return None

        if payload is None:
            return []

        if isinstance(payload, list):
            out: List[Dict[str, Any]] = []
            for item in payload:
                w = wrap_item(item)
                if w:
                    out.append(w)
            return out

        if isinstance(payload, dict):
            if isinstance(payload.get("memories"), list):
                return [w for w in (wrap_item(i) for i in payload["memories"]) if w]
            data = payload.get("data")
            if isinstance(data, dict) and isinstance(data.get("memories"), list):
                return [w for w in (wrap_item(i) for i in data["memories"]) if w]
            if isinstance(payload.get("items"), list):
                return [w for w in (wrap_item(i) for i in payload["items"]) if w]
            if isinstance(payload.get("results"), list):
                return [w for w in (wrap_item(i) for i in payload["results"]) if w]

        return []

    async def add_memory(
        self,
        *,
        assistant_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        payload: Dict[str, Any] = {"content": content}
        if metadata:
            payload["metadata"] = metadata

        paths = [
            f"assistants/{assistant_id}/memories",
            f"v1/assistants/{assistant_id}/memories",
            f"api/v1/assistants/{assistant_id}/memories",
            f"api/assistants/{assistant_id}/memories",
        ]
        return await self._request_with_fallback("POST", paths, json_payload=payload)

    async def list_memories(self, *, assistant_id: str) -> List[Dict[str, Any]]:
        paths = [
            f"assistants/{assistant_id}/memories",
            f"v1/assistants/{assistant_id}/memories",
            f"api/v1/assistants/{assistant_id}/memories",
            f"api/assistants/{assistant_id}/memories",
        ]
        resp = await self._request_with_fallback("GET", paths)
        return self._normalize_memories_payload(resp)

    async def query_memories(
        self,
        *,
        thread_id: str,
        assistant_id: str,
        query: str,
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Try to trigger retrieval via a tiny LLM call and read retrieved memories.
        If Backboard doesn't include retrieved_memories in the response, fallback to listing memories.
        """
        prompt = (
            "Memory lookup. Reply only with 'OK'.\n"
            f"Query: {query}\n"
            "Do not store this message as a user memory."
        )

        payload = None
        try:
            payload = await self.send_message(
                thread_id=thread_id,
                message=prompt,
                send_to_llm=True,
                memory="off",  # common casing
                assistant_id=assistant_id,
            )
        except HTTPException as exc:
            # fallback if memory="off" isn't supported
            if exc.status_code in (400, 405, 422):
                payload = await self.send_message(
                    thread_id=thread_id,
                    message=prompt,
                    send_to_llm=True,
                    memory="Auto",
                    assistant_id=assistant_id,
                )
            else:
                raise

        mems = self.extract_retrieved_memories(payload)

        # Fallback: if Backboard didn't return retrieved_memories, list all memories explicitly
        if not mems:
            mems = await self.list_memories(assistant_id=assistant_id)

            # lightweight filtering: prioritize TP_* memories
            q = (query or "").lower()
            tp_only: List[Dict[str, Any]] = []
            for m in mems:
                s = (m.get("memory") or "").lower()
                if s.startswith("tp_profile") or s.startswith("tp_baseline") or s.startswith("tp_trusted_merchant"):
                    tp_only.append(m)
                elif q and q in s:
                    tp_only.append(m)

            mems = tp_only or mems

        return mems[:top_k]
