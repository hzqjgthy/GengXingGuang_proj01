import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

try:
    import pymysql
except ImportError:  # pragma: no cover - exercised only before dependency install
    pymysql = None


class DatabaseError(RuntimeError):
    pass


class Database:
    """Small repository supporting MySQL in runtime and SQLite in tests."""

    def __init__(self, base_dir: Path, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.engine = str(config.get("DB_ENGINE", os.getenv("DB_ENGINE", "mysql"))).strip().lower()
        self.sqlite_path = Path(config.get("SQLITE_PATH", os.getenv("SQLITE_PATH", str(base_dir / "data" / "tcm_demo.test.db"))))
        self.mysql_config = {
            "host": config.get("MYSQL_HOST", os.getenv("MYSQL_HOST", "127.0.0.1")),
            "port": int(config.get("MYSQL_PORT", os.getenv("MYSQL_PORT", "3306"))),
            "user": config.get("MYSQL_USER", os.getenv("MYSQL_USER", "root")),
            "password": config.get("MYSQL_PASSWORD", os.getenv("MYSQL_PASSWORD", "")),
            "database": config.get("MYSQL_DATABASE", os.getenv("MYSQL_DATABASE", "tcm_demo")),
            "charset": "utf8mb4",
            "autocommit": True,
        }
        self._sqlite_ready = False
        if self.engine == "sqlite":
            self._ensure_sqlite_schema()

    @property
    def configured(self) -> bool:
        if self.engine == "sqlite":
            return True
        return pymysql is not None

    def health(self) -> Dict[str, Any]:
        try:
            with self.connection() as conn:
                if self.engine == "sqlite":
                    conn.execute("SELECT 1")
                else:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1")
            return {"engine": self.engine, "status": "ok"}
        except Exception as exc:
            return {"engine": self.engine, "status": "error", "message": str(exc)}

    @contextmanager
    def connection(self):
        if self.engine == "sqlite":
            self._ensure_sqlite_schema()
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return

        if pymysql is None:
            raise DatabaseError("未安装PyMySQL，请先安装项目依赖")
        try:
            conn = pymysql.connect(**self.mysql_config, cursorclass=pymysql.cursors.DictCursor)
        except Exception as exc:
            raise DatabaseError("无法连接MySQL：%s" % exc) from exc
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_sqlite_schema(self):
        if self._sqlite_ready:
            return
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active');
                CREATE TABLE IF NOT EXISTS patient_cases (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, case_key TEXT, display_name TEXT NOT NULL, case_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS health_records (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, case_id INTEGER, record_json TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS analysis_results (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, record_id INTEGER, provider TEXT NOT NULL, model_name TEXT NOT NULL, analysis_json TEXT NOT NULL, review_json TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS constitution_results (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, answers_json TEXT NOT NULL, score_json TEXT NOT NULL, explanation_json TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS knowledge_graphs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title TEXT NOT NULL, input_text TEXT NOT NULL, graph_json TEXT NOT NULL, created_at TEXT NOT NULL);
                """
            )
        self._sqlite_ready = True

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def create_user(self, username: str, password: str) -> Dict[str, Any]:
        username = username.strip()
        if len(username) < 3 or len(username) > 64:
            raise ValueError("用户名长度应为3到64个字符")
        if len(password) < 6:
            raise ValueError("密码至少需要6个字符")
        password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")
        now = self._now()
        try:
            with self.connection() as conn:
                if self.engine == "sqlite":
                    cursor = conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)", (username, password_hash, now))
                    user_id = cursor.lastrowid
                else:
                    with conn.cursor() as cursor:
                        cursor.execute("INSERT INTO users(username,password_hash,created_at) VALUES(%s,%s,%s)", (username, password_hash, now))
                        user_id = cursor.lastrowid
        except Exception as exc:
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                raise ValueError("用户名已存在") from exc
            raise DatabaseError("创建用户失败：%s" % exc) from exc
        return {"id": user_id, "username": username}

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            if self.engine == "sqlite":
                row = conn.execute("SELECT id,username,password_hash,status FROM users WHERE username=?", (username.strip(),)).fetchone()
                data = dict(row) if row else None
            else:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT id,username,password_hash,status FROM users WHERE username=%s", (username.strip(),))
                    data = cursor.fetchone()
        if not data or data["status"] != "active" or not check_password_hash(data["password_hash"], password):
            return None
        return {"id": int(data["id"]), "username": data["username"]}

    def upsert_case(self, user_id: int, case: Dict[str, Any]) -> int:
        now = self._now()
        persisted_case = self._persisted_case(case)
        case_json = json.dumps(persisted_case, ensure_ascii=False)
        case_key = case.get("id")
        with self.connection() as conn:
            if self.engine == "sqlite":
                row = conn.execute("SELECT id FROM patient_cases WHERE user_id=? AND case_key=?", (user_id, case_key)).fetchone()
                if row:
                    conn.execute("UPDATE patient_cases SET case_json=?,display_name=?,updated_at=? WHERE id=?", (case_json, case.get("display_name", "病例"), now, row["id"]))
                    return int(row["id"])
                cur = conn.execute("INSERT INTO patient_cases(user_id,case_key,display_name,case_json,created_at,updated_at) VALUES(?,?,?,?,?,?)", (user_id, case_key, case.get("display_name", "病例"), case_json, now, now))
                return int(cur.lastrowid)
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM patient_cases WHERE user_id=%s AND case_key=%s", (user_id, case_key))
                row = cursor.fetchone()
                if row:
                    cursor.execute("UPDATE patient_cases SET case_json=%s,display_name=%s,updated_at=%s WHERE id=%s", (case_json, case.get("display_name", "病例"), now, row["id"]))
                    return int(row["id"])
                cursor.execute("INSERT INTO patient_cases(user_id,case_key,display_name,case_json,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s)", (user_id, case_key, case.get("display_name", "病例"), case_json, now, now))
                return int(cursor.lastrowid)

    def save_analysis(self, user_id: int, case: Dict[str, Any], analysis: Dict[str, Any], meta: Dict[str, Any], review: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
        case_id = self.upsert_case(user_id, case)
        now = self._now()
        record_json = json.dumps(self._persisted_case(case), ensure_ascii=False)
        analysis_json = json.dumps(analysis, ensure_ascii=False)
        review_json = json.dumps(review or {}, ensure_ascii=False)
        with self.connection() as conn:
            if self.engine == "sqlite":
                record = conn.execute("INSERT INTO health_records(user_id,case_id,record_json,created_at) VALUES(?,?,?,?)", (user_id, case_id, record_json, now))
                record_id = int(record.lastrowid)
                result = conn.execute("INSERT INTO analysis_results(user_id,record_id,provider,model_name,analysis_json,review_json,created_at) VALUES(?,?,?,?,?,?,?)", (user_id, record_id, meta.get("provider", ""), meta.get("model", ""), analysis_json, review_json, now))
                return {"case_id": case_id, "record_id": record_id, "analysis_id": int(result.lastrowid)}
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO health_records(user_id,case_id,record_json,created_at) VALUES(%s,%s,%s,%s)", (user_id, case_id, record_json, now))
                record_id = int(cursor.lastrowid)
                cursor.execute("INSERT INTO analysis_results(user_id,record_id,provider,model_name,analysis_json,review_json,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)", (user_id, record_id, meta.get("provider", ""), meta.get("model", ""), analysis_json, review_json, now))
                return {"case_id": case_id, "record_id": record_id, "analysis_id": int(cursor.lastrowid)}

    @staticmethod
    def _persisted_case(case: Dict[str, Any]) -> Dict[str, Any]:
        persisted = dict(case)
        # The image is sent to the model transiently; storing the Base64 payload in JSON would bloat history.
        persisted.pop("tongue_image_data", None)
        return persisted

    def update_analysis_review(self, user_id: int, analysis_id: int, review: Dict[str, Any]) -> bool:
        review_json = json.dumps(review, ensure_ascii=False)
        with self.connection() as conn:
            if self.engine == "sqlite":
                cur = conn.execute("UPDATE analysis_results SET review_json=? WHERE id=? AND user_id=?", (review_json, analysis_id, user_id))
                return cur.rowcount == 1
            with conn.cursor() as cursor:
                cursor.execute("UPDATE analysis_results SET review_json=%s WHERE id=%s AND user_id=%s", (review_json, analysis_id, user_id))
                return cursor.rowcount == 1

    def list_history(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self.connection() as conn:
            if self.engine == "sqlite":
                rows = conn.execute("SELECT a.id,a.provider,a.model_name,a.analysis_json,a.created_at,r.record_json FROM analysis_results a LEFT JOIN health_records r ON r.id=a.record_id WHERE a.user_id=? ORDER BY a.created_at DESC LIMIT ?", (user_id, limit)).fetchall()
                rows = [dict(row) for row in rows]
            else:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT a.id,a.provider,a.model_name,a.analysis_json,a.created_at,r.record_json FROM analysis_results a LEFT JOIN health_records r ON r.id=a.record_id WHERE a.user_id=%s ORDER BY a.created_at DESC LIMIT %s", (user_id, limit))
                    rows = cursor.fetchall()
        result = []
        for row in rows:
            analysis = json.loads(row["analysis_json"])
            record = json.loads(row["record_json"]) if row.get("record_json") else {}
            result.append({"id": int(row["id"]), "provider": row["provider"], "model": row["model_name"], "created_at": str(row["created_at"]), "display_name": record.get("display_name", "病例"), "primary_syndrome": analysis.get("primary_syndrome", "未生成"), "confidence": analysis.get("confidence"), "fasting_glucose": (record.get("labs") or {}).get("fasting_glucose"), "tongue_analysis": analysis.get("tongue_analysis", {})})
        return result

    def save_constitution(self, user_id: int, answers: Dict[str, Any], scores: Dict[str, Any], explanation: Dict[str, Any]) -> int:
        now = self._now()
        values = (user_id, json.dumps(answers, ensure_ascii=False), json.dumps(scores, ensure_ascii=False), json.dumps(explanation, ensure_ascii=False), now)
        with self.connection() as conn:
            if self.engine == "sqlite":
                cur = conn.execute("INSERT INTO constitution_results(user_id,answers_json,score_json,explanation_json,created_at) VALUES(?,?,?,?,?)", values)
                return int(cur.lastrowid)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO constitution_results(user_id,answers_json,score_json,explanation_json,created_at) VALUES(%s,%s,%s,%s,%s)", values)
                return int(cursor.lastrowid)

    def save_knowledge_graph(self, user_id: int, title: str, input_text: str, graph: Dict[str, Any]) -> int:
        now = self._now()
        values = (user_id, title, input_text, json.dumps(graph, ensure_ascii=False), now)
        with self.connection() as conn:
            if self.engine == "sqlite":
                cur = conn.execute("INSERT INTO knowledge_graphs(user_id,title,input_text,graph_json,created_at) VALUES(?,?,?,?,?)", values)
                return int(cur.lastrowid)
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO knowledge_graphs(user_id,title,input_text,graph_json,created_at) VALUES(%s,%s,%s,%s,%s)", values)
                return int(cursor.lastrowid)
