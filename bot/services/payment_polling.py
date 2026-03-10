"""
Polling для проверки платежей YooKassa
"""
import asyncio
from datetime import datetime, timedelta
from bot.services.payment_service import PaymentService
from bot.services.database import Database
from bot.services.xray_manager import XRayManager
from bot.config import cfg


class PaymentPoller:
    """Проверка платежей через API YooKassa"""
    
    def __init__(self):
        self.payment_service = PaymentService(cfg.DB_PATH)
        self.db = Database(cfg.DB_PATH)
        self.xray = XRayManager(cfg.XRAY_CONFIG_PATH, cfg.KEYS_PATH)
    
    def get_pending_payments(self):
        """Получить ожидающие платежи из БД"""
        with self.db._get_conn() as conn:
            cursor = conn.cursor()
            # Берем платежи за последние 24 часа со статусом pending
            cursor.execute("""
                SELECT id, telegram_id, amount, period_months, status, created_at
                FROM payments 
                WHERE status = 'pending' 
                AND created_at > ?
                ORDER BY created_at DESC
            """, ((datetime.now() - timedelta(hours=24)).isoformat(),))
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    async def check_and_process_payments(self, bot=None):
        """Проверить все ожидающие платежи"""
        pending = self.get_pending_payments()
        processed = []
        
        for payment in pending:
            payment_id = payment.get('payment_id')
            if not payment_id:
                continue
            
            # Проверяем статус через API
            result = await self.payment_service.check_payment(payment_id)
            
            if result and result.get('paid') == True and result.get('status') == 'succeeded':
                # Платеж успешен - активируем подписку
                telegram_id = payment['telegram_id']
                period_months = payment['period_months']
                
                await self._activate_subscription(telegram_id, period_months, bot)
                
                # Обновляем статус платежа
                with self.db._get_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE payments SET status = 'completed' WHERE id = ?",
                        (payment['id'],)
                    )
                    conn.commit()
                
                processed.append(payment_id)
        
        return processed
    
    async def _activate_subscription(self, telegram_id: int, period_months: int, bot=None):
        """Активировать подписку после оплаты"""
        from datetime import timedelta
        
        # Создаем подписку
        config = self.xray.create_client(telegram_id, "mobile", "xtls-rprx-vision")
        
        # Вычисляем срок действия
        expires_at = datetime.now() + timedelta(days=30 * period_months)
        
        # Сохраняем в БД
        self.db.add_subscription(
            telegram_id=telegram_id,
            email=config.email,
            uuid=config.uuid,
            device_type="mobile",
            flow="xtls-rprx-vision",
            expires_at=expires_at
        )
        
        # Отправляем уведомление пользователю
        if bot:
            try:
                await bot.send_message(
                    telegram_id,
                    f"✅ <b>Оплата прошла!</b>\n\n"
                    f"Ваша подписка активирована на {period_months} мес.\n"
                    f"Конфиг: {config.link[:100]}..."
                )
            except Exception as e:
                print(f"Error sending notification: {e}")


async def payment_poller(bot, interval_minutes=5):
    """
    Фоновая задача проверки платежей
    Запускать: asyncio.create_task(payment_poller(bot))
    """
    poller = PaymentPoller()
    
    while True:
        try:
            processed = await poller.check_and_process_payments(bot)
            if processed:
                print(f"Processed {len(processed)} payments")
        except Exception as e:
            print(f"Error in payment poller: {e}")
        
        # Ждать interval_minutes минут
        await asyncio.sleep(interval_minutes * 60)
