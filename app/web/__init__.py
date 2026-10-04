"""FastAPI Web 控制台：配置渠道实例 / 任务 / 全局设置，手动执行与测试推送。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth as web_auth
from ..channels import send_instance
from ..channels.manifest import CHANNEL_TYPES
from ..history import HistoryStore
from ..models import ChannelInstance
from ..scheduler import SchedulerService
from ..state import StateStore
from ..store import AppConfigStore

log = logging.getLogger("web")

PACKAGE_DIR = Path(__file__).resolve().parent


def create_app(store: AppConfigStore | None = None, scheduler: SchedulerService | None = None) -> FastAPI:
    app_store = store or AppConfigStore()
    app_cfg = app_store.load()
    state_store = StateStore(app_store.env.state_path)
    history_store = HistoryStore(app_store.env.history_path, app_cfg.history_days)
    app_scheduler = scheduler or SchedulerService(app_store, state_store, history_store)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        app_scheduler.start()
        try:
            yield
        finally:
            app_scheduler.stop()

    app = FastAPI(title="洛克王国远行商人推送控制台", lifespan=lifespan)

    def _page_guard(request: Request) -> object:
        """页面守卫：未登录跳登录页；未启用认证直接放行。"""
        if web_auth.auth_enabled(app_store.load()) and not web_auth.session_valid(
            request.cookies.get(web_auth.SESSION_COOKIE)
        ):
            raise HTTPException(status_code=303, detail="/login", headers={"Location": "/login"})
        return True

    def _api_guard(request: Request) -> object:
        """API 守卫：未登录返回 401。"""
        if web_auth.auth_enabled(app_store.load()) and not web_auth.session_valid(
            request.cookies.get(web_auth.SESSION_COOKIE)
        ):
            raise HTTPException(status_code=401, detail="请先登录")
        return True

    def _read_page(name: str) -> str:
        return (PACKAGE_DIR / "static" / name).read_text(encoding="utf-8")

    # ---- 页面 ----

    async def login_page():
        cfg = app_store.load()
        if not web_auth.auth_enabled(cfg):
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(_read_page("login.html"))

    async def index(request: Request):
        if web_auth.auth_enabled(app_store.load()) and not web_auth.session_valid(
            request.cookies.get(web_auth.SESSION_COOKIE)
        ):
            return RedirectResponse("/login", status_code=303)
        return HTMLResponse(_read_page("index.html"))

    # ---- 认证 ----

    async def api_login(request: Request):
        payload = await request.json()
        cfg = app_store.load()
        if not web_auth.auth_enabled(cfg):
            return JSONResponse({"ok": True, "message": "未启用登录认证"})
        if not web_auth.credentials_valid(
            cfg, str(payload.get("username", "")), str(payload.get("password", ""))
        ):
            raise HTTPException(status_code=401, detail="用户名或密码不正确")
        resp = JSONResponse({"ok": True, "message": "登录成功"})
        resp.set_cookie(
            web_auth.SESSION_COOKIE, web_auth.create_session(),
            max_age=web_auth.SESSION_TTL, httponly=True, samesite="lax",
        )
        return resp

    async def api_logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(web_auth.SESSION_COOKIE)
        return resp

    # ---- 数据 ----

    async def api_state(request: Request, _=Depends(_api_guard)):
        cfg = app_store.load()
        return {
            "config": cfg.public_dict(),
            "channel_types": CHANNEL_TYPES,
            "scheduler": dict(app_scheduler.state),
            "config_issue": app_store.last_issue,
            "auth_username": str(cfg.console_auth.get("username") or "admin"),
            "now": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }

    async def api_change_account(request: Request, _=Depends(_api_guard)):
        payload = await request.json()
        cfg = app_store.load()
        current_user = str(cfg.console_auth.get("username") or "admin")
        if not web_auth.credentials_valid(cfg, current_user, str(payload.get("old_password", ""))):
            raise HTTPException(status_code=400, detail="当前密码不正确")
        new_username = str(payload.get("username", "")).strip()
        new_password = str(payload.get("new_password", ""))
        if not new_username:
            raise HTTPException(status_code=400, detail="用户名不能为空")
        if len(new_password) < 4:
            raise HTTPException(status_code=400, detail="新密码至少 4 位")
        app_store.save_console_password(new_username, new_password)
        web_auth.destroy_others(request.cookies.get(web_auth.SESSION_COOKIE))
        return JSONResponse({"ok": True, "message": "账号密码已更新，其他已登录会话已失效"})

    async def api_save_config(request: Request, _=Depends(_api_guard)):
        payload = await request.json()
        try:
            cfg = app_store.save_public(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"保存失败：{exc}") from exc
        app_scheduler.wake()
        # 保留天数即时生效：文件日志 handler 与历史存储原地更新
        from .. import logs as app_logs

        app_logs.set_file_retention(cfg.log_retention_days)
        if app_scheduler.history is not None:
            app_scheduler.history.set_days(cfg.history_days)
        return JSONResponse({"ok": True, "config": cfg.public_dict()})

    # ---- 操作 ----

    async def api_test_channel(request: Request, _=Depends(_api_guard)):
        payload = await request.json()
        draft = payload.get("instance") if isinstance(payload.get("instance"), dict) else {}
        if payload.get("id"):  # 已保存实例：以服务端配置为基础（密钥打码回显为空）
            cfg = app_store.load()
            saved = next((c for c in cfg.channels if c.id == str(payload["id"])), None)
            if saved is None:
                raise HTTPException(status_code=404, detail="渠道不存在")
            inst = saved
            if draft.get("type") == saved.type:
                # 表单里新填的字段生效；留空（=保持不变）的字段沿用已保存密钥
                merged_config = dict(saved.config)
                for key, value in (draft.get("config") or {}).items():
                    if str(value).strip():
                        merged_config[str(key)] = str(value).strip()
                inst = ChannelInstance(
                    id=saved.id, type=saved.type,
                    name=str(draft.get("name") or "").strip() or saved.name,
                    enabled=True, config=merged_config,
                )
        else:  # 未保存草稿：用前端提交的配置直接测
            try:
                inst = ChannelInstance.from_mapping(draft)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        title = "洛克王国远行商人｜测试推送"
        md = f"**{inst.name}** 渠道配置正确。\n\n- 测试时间：{now_text}"
        ok, detail = send_instance(inst, title, md, f"{inst.name} 渠道测试推送（{now_text}）")
        return JSONResponse({"ok": ok, "message": detail}, status_code=200 if ok else 400)

    async def api_history(request: Request, _=Depends(_api_guard)):
        try:
            days = min(int(request.query_params.get("days", "14")), 90)
        except ValueError:
            days = 14
        history = getattr(app_scheduler, "history", None)
        return {
            "slots": ["08:00", "12:00", "16:00", "20:00"],
            "days": days,
            "history": history.query(days) if history else {},
        }

    async def api_logs(request: Request, _=Depends(_api_guard)):
        from ..logs import ring

        level = request.query_params.get("level", "DEBUG").upper()
        try:
            limit = min(int(request.query_params.get("limit", "500")), 2000)
        except ValueError:
            limit = 500
        return {"logs": ring.query(min_level=level, limit=limit)}

    async def api_run_task(request: Request, _=Depends(_api_guard)):
        payload = await request.json()
        message = app_scheduler.run_task_now(str(payload.get("id", "")).strip())
        return JSONResponse({"ok": True, "message": message})

    async def api_run_all(_=Depends(_api_guard)):
        message = app_scheduler.run_all_now()
        return JSONResponse({"ok": True, "message": message})

    # ---- 路由注册 ----

    app.add_api_route("/login", login_page, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/", index, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/api/login", api_login, methods=["POST"])
    app.add_api_route("/api/logout", api_logout, methods=["POST"])
    app.add_api_route("/api/state", api_state, methods=["GET"])
    app.add_api_route("/api/account", api_change_account, methods=["POST"])
    app.add_api_route("/api/config", api_save_config, methods=["POST"])
    app.add_api_route("/api/test-channel", api_test_channel, methods=["POST"])
    app.add_api_route("/api/run-task", api_run_task, methods=["POST"])
    app.add_api_route("/api/run-all", api_run_all, methods=["POST"])
    app.add_api_route("/api/logs", api_logs, methods=["GET"])
    app.add_api_route("/api/history", api_history, methods=["GET"])
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    return app
