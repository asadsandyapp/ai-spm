"""Real-time dashboard WebSocket feed."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from ai_spm.config import get_settings
from ai_spm.infrastructure.db.session import get_platform_session
from ai_spm.services.dashboard_service import DashboardService

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["websocket"])
dashboard_service = DashboardService()
settings = get_settings()

_connections: dict[str, list[WebSocket]] = {}


def _verify_ws_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        org_id = payload.get("org_id")
        if org_id and payload.get("type") == "admin":
            return str(org_id)
    except JWTError:
        return None
    return None


@router.websocket("/admin/v1/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return

    org_id = _verify_ws_token(token)
    if not org_id:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    _connections.setdefault(org_id, []).append(websocket)
    logger.info("dashboard_ws_connected", org_id=org_id)

    try:
        from uuid import UUID

        org_uuid = UUID(org_id)
        while True:
            # Platform session + explicit org_id filters (same as service queries).
            # Avoids tenant-role RLS races on pooled connections that briefly
            # returned empty metrics and made the UI flip 1 ↔ 0 agents.
            async with get_platform_session() as session:
                metrics = await dashboard_service.get_metrics(session, org_uuid)
                threats = await dashboard_service.get_threats(session, org_uuid, limit=10)

            await websocket.send_json({
                "type": "dashboard_update",
                "metrics": metrics,
                "threats": threats[:5],
            })
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    finally:
        conns = _connections.get(org_id, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.info("dashboard_ws_disconnected", org_id=org_id)


async def broadcast_event(org_id: str, event: dict[str, Any]) -> None:
    """Push real-time event to connected dashboard clients."""
    for ws in _connections.get(org_id, []):
        try:
            await ws.send_json({"type": "event", "payload": event})
        except Exception:
            pass
