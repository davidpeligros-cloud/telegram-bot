"""
Database layer mejorado
SQLite con thread-safety, indexing y métodos avanzados
"""

import logging
import os
import sqlite3
from contextlib import contextmanager
from threading import Lock
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

os.makedirs("data", exist_ok=True)


class DealDatabase:
    """
    Gestor de base de datos con:
    - Thread-safety completo
    - Connection management
    - Índices optimizados
    - Métodos avanzados
    """

    def __init__(self, db_path: str = "data/deals.db"):
        self.db_path = db_path
        self.lock = Lock()
        self._init_db()
        logger.info(f"Database inicializada: {db_path}")

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS deals (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            product TEXT NOT NULL,
                            link TEXT UNIQUE NOT NULL,
                            price TEXT,
                            score INTEGER NOT NULL,
                            group_name TEXT NOT NULL,
                            date TEXT NOT NULL,
                            message_id INTEGER,
                            user_id INTEGER,
                            image_path TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )

                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS shipments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            product_name TEXT NOT NULL,
                            carrier TEXT NOT NULL,
                            tracking_number TEXT NOT NULL,
                            status TEXT NOT NULL,
                            notes TEXT,
                            purchase_price REAL DEFAULT 0.0,
                            resell_price REAL DEFAULT 0.0,
                            fees REAL DEFAULT 0.0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )

                    # Migración de esquema: añadir columnas si no existen.
                    cursor.execute("PRAGMA table_info(deals)")
                    columns = [row[1] for row in cursor.fetchall()]
                    if "created_at" not in columns:
                        logger.info("Migrando esquema: agregando columna created_at")
                        cursor.execute("ALTER TABLE deals ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                    if "message_id" not in columns:
                        logger.info("Migrando esquema: agregando columna message_id")
                        cursor.execute("ALTER TABLE deals ADD COLUMN message_id INTEGER")
                    if "user_id" not in columns:
                        logger.info("Migrando esquema: agregando columna user_id")
                        cursor.execute("ALTER TABLE deals ADD COLUMN user_id INTEGER")
                    if "image_path" not in columns:
                        logger.info("Migrando esquema: agregando columna image_path")
                        cursor.execute("ALTER TABLE deals ADD COLUMN image_path TEXT")

                    # Migración de esquema de shipments: añadir columnas si no existen.
                    cursor.execute("PRAGMA table_info(shipments)")
                    ship_columns = [row[1] for row in cursor.fetchall()]
                    if "purchase_price" not in ship_columns:
                        logger.info("Migrando esquema: agregando columna purchase_price a shipments")
                        cursor.execute("ALTER TABLE shipments ADD COLUMN purchase_price REAL DEFAULT 0.0")
                    if "resell_price" not in ship_columns:
                        logger.info("Migrando esquema: agregando columna resell_price a shipments")
                        cursor.execute("ALTER TABLE shipments ADD COLUMN resell_price REAL DEFAULT 0.0")
                    if "fees" not in ship_columns:
                        logger.info("Migrando esquema: agregando columna fees a shipments")
                        cursor.execute("ALTER TABLE shipments ADD COLUMN fees REAL DEFAULT 0.0")

                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_score ON deals(score DESC)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON deals(date DESC)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_group ON deals(group_name)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_link ON deals(link)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_created ON deals(created_at DESC)")
                    conn.commit()
                    logger.info("Tablas e índices creados correctamente")
            except Exception as e:
                logger.error(f"Error inicializando BD: {e}")
                raise

    def save_deal(
        self,
        product: str,
        link: str,
        price: str,
        score: int,
        group_name: str,
        date: str,
        message_id: Optional[int] = None,
        user_id: Optional[int] = None,
        image_path: Optional[str] = None,
    ) -> bool:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO deals (
                            product, link, price, score,
                            group_name, date, message_id, user_id, image_path
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (product, link, price, score, group_name, date, message_id, user_id, image_path),
                    )
                    conn.commit()
                    logger.info(f"Deal guardado: {link}")
                    return True
            except sqlite3.IntegrityError:
                logger.warning(f"Link duplicado: {link}")
                return False
            except Exception as e:
                logger.error(f"Error guardando deal: {e}")
                return False

    def has_link(self, link: str) -> bool:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1 FROM deals WHERE link = ? LIMIT 1", (link,))
                    return cursor.fetchone() is not None
            except Exception as e:
                logger.error(f"Error verificando link: {e}")
                return False

    def get_existing_links(self) -> List[str]:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT link FROM deals")
                    return [row[0] for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"Error cargando links existentes: {e}")
                return []

    def get_top_deals(self, limit: int = 10) -> List[Tuple]:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT id, product, link, price, score, group_name, date
                        FROM deals
                        ORDER BY score DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error en get_top_deals: {e}")
                return []

    def get_top_groups(self, limit: int = 10) -> List[Tuple]:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT group_name, COUNT(*) as count, AVG(score) as avg_score
                        FROM deals
                        GROUP BY group_name
                        ORDER BY count DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error en get_top_groups: {e}")
                return []

    def get_deals_by_date_range(self, start_date: str, end_date: str, min_score: int = 0) -> List[Tuple]:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT *
                        FROM deals
                        WHERE date BETWEEN ? AND ? AND score >= ?
                        ORDER BY date DESC
                        """,
                        (start_date, end_date, min_score),
                    )
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error en get_deals_by_date_range: {e}")
                return []

    def get_deals_by_group(self, group_name: str, limit: int = 50) -> List[Tuple]:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT *
                        FROM deals
                        WHERE group_name = ?
                        ORDER BY date DESC
                        LIMIT ?
                        """,
                        (group_name, limit),
                    )
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error en get_deals_by_group: {e}")
                return []

    def search_deals(self, query: str) -> List[Tuple]:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT *
                        FROM deals
                        WHERE product LIKE ? OR link LIKE ?
                        ORDER BY date DESC
                        LIMIT 50
                        """,
                        (f"%{query}%", f"%{query}%"),
                    )
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error en search_deals: {e}")
                return []

    def get_statistics(self) -> dict:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM deals")
                    total = cursor.fetchone()[0]
                    cursor.execute("SELECT AVG(score) FROM deals")
                    avg_score = cursor.fetchone()[0] or 0
                    cursor.execute("SELECT COUNT(DISTINCT group_name) FROM deals")
                    groups = cursor.fetchone()[0]
                    cursor.execute("SELECT MAX(score) FROM deals")
                    best_score = cursor.fetchone()[0] or 0
                    return {
                        "total_deals": total,
                        "avg_score": round(avg_score, 1),
                        "unique_groups": groups,
                        "best_score": best_score,
                    }
            except Exception as e:
                logger.error(f"Error en get_statistics: {e}")
                return {}

    def get_all_deals(self, limit: int = 500) -> List[Tuple]:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT *
                        FROM deals
                        ORDER BY date DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error en get_all_deals: {e}")
                return []

    def delete_old_deals(self, days: int = 30) -> int:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        DELETE FROM deals
                        WHERE date < datetime('now', '-' || ? || ' days')
                        """,
                        (days,),
                    )
                    conn.commit()
                    deleted = cursor.rowcount
                    logger.info(f"Eliminados {deleted} deals antiguos")
                    return deleted
            except Exception as e:
                logger.error(f"Error eliminando deals: {e}")
                return 0

    def vacuum(self) -> None:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    conn.execute("VACUUM")
                    logger.info("Base de datos optimizada")
            except Exception as e:
                logger.error(f"Error en VACUUM: {e}")

    def top_deals(self) -> List[Tuple]:
        return self.get_top_deals(10)

    def top_groups(self) -> List[Tuple]:
        return self.get_top_groups(10)

    # =========================
    # SÉCCIÓN DE ENVÍOS (SHIPMENTS)
    # =========================

    def save_shipment(
        self,
        product_name: str,
        carrier: str,
        tracking_number: str,
        status: str = "Pedido",
        notes: Optional[str] = None,
        purchase_price: float = 0.0,
        resell_price: float = 0.0,
        fees: float = 0.0,
    ) -> bool:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO shipments (
                            product_name, carrier, tracking_number, status, notes, purchase_price, resell_price, fees
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (product_name, carrier, tracking_number, status, notes, purchase_price, resell_price, fees),
                    )
                    conn.commit()
                    logger.info(f"Envío guardado: {product_name} - {tracking_number}")
                    return True
            except Exception as e:
                logger.error(f"Error guardando envío: {e}")
                return False

    def get_all_shipments(self) -> List[sqlite3.Row]:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM shipments ORDER BY created_at DESC")
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error obteniendo todos los envíos: {e}")
                return []

    def get_active_shipments(self) -> List[sqlite3.Row]:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM shipments WHERE status != 'Recibido' ORDER BY created_at DESC")
                    return cursor.fetchall()
            except Exception as e:
                logger.error(f"Error obteniendo envíos activos: {e}")
                return []

    def update_shipment_status(self, shipment_id: int, new_status: str, notes: Optional[str] = None) -> bool:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    if notes is not None:
                        cursor.execute(
                            "UPDATE shipments SET status = ?, notes = ? WHERE id = ?",
                            (new_status, notes, shipment_id),
                        )
                    else:
                        cursor.execute(
                            "UPDATE shipments SET status = ? WHERE id = ?",
                            (new_status, shipment_id),
                        )
                    conn.commit()
                    logger.info(f"Estado de envío {shipment_id} actualizado a {new_status}")
                    return True
            except Exception as e:
                logger.error(f"Error actualizando envío {shipment_id}: {e}")
                return False

    def delete_shipment(self, shipment_id: int) -> bool:
        with self.lock:
            try:
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM shipments WHERE id = ?", (shipment_id,))
                    conn.commit()
                    logger.info(f"Envío {shipment_id} eliminado")
                    return True
            except Exception as e:
                logger.error(f"Error eliminando envío {shipment_id}: {e}")
                return False

