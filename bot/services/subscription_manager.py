"""
Менеджер подписок - проверка истечения сроков
"""
import asyncio
from datetime import datetime
from bot.services.database import Database
from bot.services.xray_manager import XRayManager
from bot.config import cfg


class SubscriptionManager:
    def __init__(self):
        self.db = Database(cfg.DB_PATH)
        self.xray = XRayManager(cfg.XRAY_CONFIG_PATH, cfg.KEYS_PATH)
    
    def get_expired_subscriptions(self):
        """Получить просроченные подписки"""
        with Database(cfg.DB_PATH)._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, telegram_id, email, uuid, expires_at 
                FROM subscriptions 
                WHERE is_active = 1 
                AND expires_at IS NOT NULL 
                AND expires_at < ?
            """, (datetime.now().isoformat(),))
            return cursor.fetchall()
    
    def check_and_deactivate_expired(self, bot=None):
        """Проверить и деактивировать просроченные подписки"""
        expired = self.get_expired_subscriptions()
        deactivated = []
        
        for sub in expired:
            sub_id, telegram_id, email, uuid, expires_at = sub
            
            # Удаляем из XRay
            try:
                self.xray.remove_client(email)
            except Exception as e:
                print(f"Error removing client from XRay: {e}")
            
            # Деактивируем в БД
            with Database(cfg.DB_PATH)._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE subscriptions SET is_active = 0 WHERE id = ?",
                    (sub_id,)
                )
                conn.commit()
            
            deactivated.append({
                'telegram_id': telegram_id,
                'email': email,
                'expires_at': expires_at
            })
            
            # Отправляем уведомление пользователю
            if bot:
                try:
                    asyncio.create_task(bot.send_message(
                        telegram_id,
                        f"⏰ <b>Подписка истекла</b>\n\n"
                        f"Ваша подписка {email} истекла {expires_at}.\n"
                        f"Для продления нажмите /start"
                    ))
                except Exception as e:
                    print(f"Error sending notification: {e}")
        
        return deactivated
    
    def get_expiring_soon(self, days=3):
        """Получить подписки, которые истекают через N дней"""
        from datetime import timedelta
        with Database(cfg.DB_PATH)._get_conn() as conn:
            cursor = conn.cursor()
            future_date = (datetime.now() + timedelta(days=days)).isoformat()
            cursor.execute("""
                SELECT telegram_id, email, expires_at 
                FROM subscriptions 
                WHERE is_active = 1 
                AND expires_at IS NOT NULL 
                AND expires_at < ?
                AND expires_at > ?
            """, (future_date, datetime.now().isoformat()))
            return cursor.fetchall()
    
    def notify_expiring_soon(self, bot, days=3):
        """Отправить уведомления о скором истечении"""
        expiring = self.get_expiring_soon(days)
        
        for telegram_id, email, expires_at in expiring:
            try:
                asyncio.create_task(bot.send_message(
                    telegram_id,
                    f"⚠️ <b>Подписка скоро истекает</b>\n\n"
                    f"Ваша подписка {email} истекает {expires_at}.\n"
                    f"Для продления нажмите /start"
                ))
            except Exception as e:
                print(f"Error sending notification: {e}")
    
    def sync_with_xray(self):
        """Синхронизация XRay с БД - удалить из XRay неактивные подписки"""
        with Database(cfg.DB_PATH)._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT email FROM subscriptions WHERE is_active = 1
            """)
            active_emails = [row[0] for row in cursor.fetchall()]
        
        removed = self.xray.sync_with_db(active_emails)
        return removed


# Функция для запуска в background
async def subscription_checker(bot, interval_hours=1):
    """
    Фоновая задача проверки подписок
    Запускать через asyncio.create_task(subscription_checker(bot))
    """
    manager = SubscriptionManager()
    
    while True:
        try:
            # Проверить и деактивировать просроченные
            deactivated = manager.check_and_deactivate_expired(bot)
            if deactivated:
                print(f"Deactivated {len(deactivated)} expired subscriptions")
            
            # Отправить уведомления о скором истечении (за 3 дня)
            manager.notify_expiring_soon(bot, days=3)
            
        except Exception as e:
            print(f"Error in subscription checker: {e}")
        
        # Ждать interval_hours часов
        await asyncio.sleep(interval_hours * 3600)
