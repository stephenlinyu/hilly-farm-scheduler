import os
import sys

from werkzeug.security import check_password_hash

from app import app, default_worker_password, ensure_auth_schema, get_db_connection


DEFAULT_ADMIN_PASSWORD = "Admin@123456"
FALLBACK_SECRET_KEY = "farm-system-dev-secret-change-me"


def main():
    public_scope = os.environ.get("FARM_PUBLIC_SCOPE", "all").strip().lower()
    if public_scope not in {"admin", "all"}:
        print("[错误] FARM_PUBLIC_SCOPE 只能是 admin 或 all。")
        return 2

    ensure_auth_schema()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, password_hash, role, machine_id, is_active FROM users ORDER BY id"
        )
        users = cursor.fetchall()
    finally:
        conn.close()

    admin = next((user for user in users if user.get("username") == "admin"), None)
    if not admin or not admin.get("is_active"):
        print("[错误] 未找到可用的 admin 管理员账号。")
        return 2

    if check_password_hash(admin["password_hash"], DEFAULT_ADMIN_PASSWORD):
        print("[安全拦截] 管理员仍在使用默认密码，禁止开放公网。")
        print("请先通过本机管理端登录，在右上角修改密码后再运行公网启动脚本。")
        return 3

    if not app.secret_key or app.secret_key == FALLBACK_SECRET_KEY or len(str(app.secret_key)) < 32:
        print("[安全拦截] Flask 会话密钥无效或正在使用开发回退值，禁止开放公网。")
        return 4

    default_workers = []
    if public_scope == "all":
        for user in users:
            if not user.get("is_active") or user.get("role") != "worker" or not user.get("machine_id"):
                continue
            if check_password_hash(
                user["password_hash"], default_worker_password(user["machine_id"])
            ):
                default_workers.append(user["username"])

        if default_workers:
            preview = ", ".join(default_workers[:8])
            remainder = len(default_workers) - min(len(default_workers), 8)
            print(
                f"[安全拦截] 有 {len(default_workers)} 个启用的工作人员账号仍在使用可预测默认密码，禁止开放工作人员公网入口。"
            )
            print(f"账号示例：{preview}" + (f"，另有 {remainder} 个" if remainder else ""))
            print("请让需要使用的工作人员先修改密码，并停用不需要公开的账号。")
            return 5

    if public_scope == "admin":
        print("公网开放前安全检查通过：仅开放管理端，工作人员入口保持关闭。")
    else:
        print("公网开放前安全检查通过：管理端和工作人员端均允许开放。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
