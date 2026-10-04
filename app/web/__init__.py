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
from ..models import ChannelInstance
from ..scheduler import SchedulerService
from ..state import StateStore
from ..store import AppConfigStore

log = logging.getLogger("web")

PACKAGE_DIR = Path(__file__).resolve().parent


def create_app(store: AppConfigStore | None = None, scheduler: SchedulerService | None = None) -> FastAPI:
    app_store = store or AppConfigStore()
    state_store = StateStore(app_store.env.state_path)
    app_scheduler = scheduler or SchedulerService(app_store, state_store)

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
        return JSONResponse({"ok": True, "config": cfg.public_dict()})

    # ---- 操作 ----

    async def api_test_channel(request: Request, _=Depends(_api_guard)):
        payload = await request.json()
        if payload.get("id"):  # 已保存实例：服务端取完整配置（含密钥）
            cfg = app_store.load()
            inst = next((c for c in cfg.channels if c.id == str(payload["id"])), None)
            if inst is None:
                raise HTTPException(status_code=404, detail="渠道不存在")
        else:  # 未保存草稿：用前端提交的配置直接测
            try:
                inst = ChannelInstance.from_mapping(payload.get("instance") or {})
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        title = "洛克王国远行商人｜测试推送"
        md = f"**{inst.name}** 渠道配置正确。\n\n- 测试时间：{now_text}"
        ok, detail = send_instance(inst, title, md, f"{inst.name} 渠道测试推送（{now_text}）")
        return JSONResponse({"ok": ok, "message": detail}, status_code=200 if ok else 400)

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
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")
    return app
