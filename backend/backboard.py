# backend/backboard.py
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
        errors: List[str] = []
        if json_payload is not None and data_payload is not None:
            raise ValueError("Provide only one of json_payload or data_payload")

        for path in path_candidates:
            url = f"{self.api_base_url}/{path.lstrip('/')}"
            try:
                resp = await self._client.request(
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

            if resp.status_code in (401, 403):
                raise HTTPException(status_code=resp.status_code, detail="Backboard auth failed")

            if resp.status_code >= 500:
                errors.append(f"{url}: {resp.status_code} {resp.text}")
                continue

            if resp.status_code in (404, 405):
                errors.append(f"{url}: {resp.status_code}")
                continue

            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail=f"Backboard error: {resp.text}")

            try:
                return resp.json()
            except ValueError:
                raise HTTPException(status_code=502, detail="Backboard returned non-JSON response")

        raise HTTPException(status_code=502, detail=f"Unable to reach Backboard endpoints. Tried: {'; '.join(errors)}")

    @staticmethod
    def _extract_assistant_text(payload: Any) -> Optional[str]:
        if payload is None:
            return None
        if isinstance(payload, str) and payload.strip():
            return payload.strip()

        if isinstance(payload, dict):
            for key in ("assistant_text", "assistant_response", "response", "text", "content", "message"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
                if isinstance(val, dict):
                    nested = val.get("content") or val.get("text")
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()

            msgs = payload.get("messages")
            if isinstance(msgs, list):
                for m in msgs:
                    if isinstance(m, dict) and m.get("role") == "assistant":
                        c = m.get("content") or m.get("text")
                        if isinstance(c, str) and c.strip():
                            return c.strip()

            data = payload.get("data")
            if isinstance(data, dict):
                return BackboardClient._extract_assistant_text(data)

        if isinstance(payload, list):
            for item in payload:
                t = BackboardClient._extract_assistant_text(item)
                if t:
                    return t
        return None

    async def extract_assistant_text(self, payload: Any) -> Optional[str]:
        return self._extract_assistant_text(payload)

    async def create_assistant(self, name: str) -> str:
        payload = {"name": name, "display_name": name}
        paths = ["assistants", "v1/assistants", "api/v1/assistants", "api/assistants"]
        resp = await self._request_with_fallback("POST", paths, json_payload=payload)

        if isinstance(resp, dict):
            assistant_id = resp.get("id") or resp.get("assistant_id") or resp.get("assistantId") or resp.get("data", {}).get("id")
            if assistant_id:
                return str(assistant_id)

        raise HTTPException(status_code=502, detail="Backboard did not return an assistant_id")

    async def create_thread(self, assistant_id: str) -> str:
        payload = {"assistant_id": assistant_id, "assistantId": assistant_id}
        paths = [
            f"assistants/{assistant_id}/threads",
            f"v1/assistants/{assistant_id}/threads",
            f"api/v1/assistants/{assistant_id}/threads",
            "threads",
            "v1/threads",
        ]
        resp = await self._request_with_fallback("POST", paths, json_payload=payload)

        if isinstance(resp, dict):
            thread_id = resp.get("id") or resp.get("thread_id") or resp.get("threadId") or resp.get("data", {}).get("id")
            if thread_id:
                return str(thread_id)

        raise HTTPException(status_code=502, detail="Backboard did not return a thread_id")

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
            f"v1/threads/{thread_id}/messages",
            f"api/v1/threads/{thread_id}/messages",
            f"assistants/{assistant_id}/threads/{thread_id}/messages" if assistant_id else None,
            f"api/assistants/{assistant_id}/threads/{thread_id}/messages" if assistant_id else None,
            f"v1/assistants/{assistant_id}/threads/{thread_id}/messages" if assistant_id else None,
            f"api/v1/assistants/{assistant_id}/threads/{thread_id}/messages" if assistant_id else None,
            "messages",
            "v1/messages",
            "api/v1/messages",
        ]
        return await self._request_with_fallback("POST", [p for p in paths if p], data_payload=payload)

    # ---- Memories API ----

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

    @staticmethod
    def _normalize_memories_payload(payload: Any) -> List[Dict[str, Any]]:
        def wrap_item(x: Any) -> Optional[Dict[str, Any]]:
            if isinstance(x, dict):
                content = x.get("content") or x.get("memory") or x.get("text")
                if isinstance(content, str) and content.strip():
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

    async def list_memories(self, *, assistant_id: str) -> List[Dict[str, Any]]:
        paths = [
            f"assistants/{assistant_id}/memories",
            f"v1/assistants/{assistant_id}/memories",
            f"api/v1/assistants/{assistant_id}/memories",
            f"api/assistants/{assistant_id}/memories",
        ]
        resp = await self._request_with_fallback("GET", paths)
        return self._normalize_memories_payload(resp)

    @staticmethod
    def extract_retrieved_memories(payload: Any) -> List[Dict[str, Any]]:
        def norm_list(lst: Any) -> List[Dict[str, Any]]:
            if not isinstance(lst, list):
                return []
            out = []
            for x in lst:
                if isinstance(x, dict):
                    out.append(x)
                elif isinstance(x, str) and x.strip():
                    out.append({"memory": x.strip()})
            return out

        if payload is None:
            return []

        if isinstance(payload, dict):
            for key in ("retrieved_memories", "retrievedMemories", "memory_hits", "retrievals", "results"):
                n = norm_list(payload.get(key))
                if n:
                    return n
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

    async def query_memories(
        self,
        *,
        thread_id: str,
        assistant_id: str,
        query: str,
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        # Try retrieval via tiny LLM call
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
                memory="off",
                assistant_id=assistant_id,
            )
        except HTTPException as exc:
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

        # Fallback: list memories explicitly
        if not mems:
            mems = await self.list_memories(assistant_id=assistant_id)

        # Prefer TP_* memories
        tp = []
        for m in mems:
            s = (m.get("memory") or "").strip().lower()
            if s.startswith("tp_"):
                tp.append(m)
        mems = tp or mems

        return mems[:top_k]
