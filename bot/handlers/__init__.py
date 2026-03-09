from aiogram import Router


def get_routers() -> list[Router]:
    from . import admin, payment, user

    return [
        user.router,
        admin.router,
        payment.router,
    ]
