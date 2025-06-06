# telebot/schedule.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from database_manager import set_config, get_all_configs_like, delete_config_key
from user_state import user_state, set_user_state

router = Router()
AVAILABLE_SCRIPTS = ["avito", "zzap", "trast", "froza"]

WEEKDAYS = {
    1: "Пн",
    2: "Вт",
    3: "Ср",
    4: "Чт",
    5: "Пт",
    6: "Сб",
    7: "Вс"
}

@router.message(F.text == "⏰ Расписание")
async def schedule_entry(msg: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Текущее расписание", callback_data="schedule_view"),
            InlineKeyboardButton(text="⚙️ Изменить расписание", callback_data="schedule_manage")
        ]
    ])
    await msg.answer("Выберите действие:", reply_markup=keyboard)

@router.callback_query(F.data == "schedule_view")
async def view_all_schedules(call: CallbackQuery):
    text = "<b>Текущее расписание скриптов:</b>"
    found = False
    for script in AVAILABLE_SCRIPTS:
        entries = get_all_configs_like(f"{script}.schedule.%")
        if not entries:
            continue
        found = True
        text += f"\n\n<b>{script}</b>:"
        for _, expr in entries:
            parts = expr.split()
            if len(parts) == 5:
                minute, hour, _, _, days = parts
                day_names = ", ".join(WEEKDAYS.get(int(d), f"{d}") for d in days.split(",") if d.isdigit())
                text += f"\n🕒 <b>{hour.zfill(2)}:{minute.zfill(2)}</b> — <i>{day_names}</i>"
    if not found:
        text += "\nНет активных расписаний."
    await call.message.edit_text(text, parse_mode="HTML")

@router.callback_query(F.data == "schedule_manage")
async def manage_schedule_menu(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="schedule_add")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="schedule_delete")]
    ])
    await call.message.edit_text("Выберите действие:", reply_markup=keyboard)

@router.callback_query(F.data == "schedule_add")
async def select_script_for_add(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=script, callback_data=f"schedule_add_{script}")]
        for script in AVAILABLE_SCRIPTS
    ])
    await call.message.edit_text("Выберите скрипт для добавления расписания:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("schedule_add_"))
async def select_script(call: CallbackQuery):
    script = call.data.replace("schedule_add_", "")
    set_user_state(call.from_user.id, {"step": "time", "script": script})
    await call.message.edit_text(f"Настройка расписания для <b>{script}</b>.\nВведите время запуска (например, 14.30):", parse_mode="HTML")

@router.message(F.text.func(lambda text, msg: user_state.get(msg.from_user.id, {}).get("step") == "time"))
async def handle_schedule_time_input(msg: Message):
    try:
        parts = msg.text.strip().replace(":", ".").split(".")
        hour, minute = map(int, parts)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError()
    except ValueError:
        await msg.answer("❌ Неверный формат. Введите время как HH.MM (например, 14.30).")
        return

    state = user_state[msg.from_user.id]
    state.update({"hour": hour, "minute": minute, "step": "weekday", "days": set()})
    set_user_state(msg.from_user.id, state)
    await update_days_markup(msg, state)

async def update_days_markup(target, state):
    selected_days = state.get("days", set())
    buttons = []
    for val in range(1, 8):
        label = WEEKDAYS[val]
        checked = "☑️" if val in selected_days else "▫️"
        buttons.append([InlineKeyboardButton(text=f"{checked} {label}", callback_data=f"day_{val}")])
    buttons.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data="save_schedule")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await target.answer("Выберите дни недели:", reply_markup=markup) if isinstance(target, Message) else await target.message.edit_reply_markup(reply_markup=markup)

@router.callback_query(F.data.func(lambda data: data.startswith("day_") or data == "save_schedule"))
async def process_days(call: CallbackQuery):
    user_id = call.from_user.id
    state = user_state.get(user_id, {})

    if call.data.startswith("day_"):
        day = int(call.data.replace("day_", ""))
        days = state.get("days", set())
        days ^= {day}
        state["days"] = days
        set_user_state(user_id, state)
        await update_days_markup(call, state)
        await call.answer("День обновлён")
        return

    if call.data == "save_schedule":
        script = state.get("script")
        hour = state.get("hour")
        minute = state.get("minute")
        days = sorted(state.get("days", []))

        if not days:
            await call.answer("❌ Нужно выбрать хотя бы один день.", show_alert=True)
            return

        cron_expr = f"{minute} {hour} * * {','.join(map(str, days))}"
        cron_key = f"{script}.schedule.{hour:02d}_{minute:02d}_{'_'.join(map(str, days))}"
        set_config(cron_key, cron_expr)

        time_str = f"{hour:02d}:{minute:02d}"
        day_names = ", ".join(WEEKDAYS.get(int(d), str(d)) for d in days)

        await call.message.edit_text(
            f"✅ Расписание сохранено для <b>{script}</b>\n🕒 <b>{time_str}</b> — <i>{day_names}</i>",
            parse_mode="HTML"
        )

        user_state.pop(user_id, None)

@router.callback_query(F.data == "schedule_delete")
async def select_script_to_delete(call: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=script, callback_data=f"delete_select_{script}")]
        for script in AVAILABLE_SCRIPTS
    ])
    await call.message.edit_text("Выберите скрипт для удаления расписания:", reply_markup=keyboard)

@router.callback_query(F.data.startswith("delete_select_"))
async def show_script_schedules(call: CallbackQuery):
    script = call.data.replace("delete_select_", "")
    entries = get_all_configs_like(f"{script}.schedule.%")
    if not entries:
        await call.message.edit_text("Нет расписаний для удаления.")
        return

    buttons = []
    for key, expr in entries:
        try:
            parts = expr.split()
            if len(parts) == 5:
                minute, hour, _, _, days = parts
                day_names = ", ".join(WEEKDAYS.get(int(d), f"{d}") for d in days.split(",") if d.isdigit())
                label = f"{hour.zfill(2)}:{minute.zfill(2)} — {day_names}"
            else:
                label = expr  # fallback
        except Exception:
            label = expr  # fallback
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"delkey_{key}")])

    await call.message.edit_text(
        f"Выберите расписание для удаления ({script}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@router.callback_query(F.data.startswith("delkey_"))
async def delete_schedule(call: CallbackQuery):
    key = call.data.replace("delkey_", "")
    # Извлекаем выражение перед удалением
    entries = get_all_configs_like(key)
    expr = entries[0][1] if entries else None
    delete_config_key(key)

    if expr:
        try:
            parts = expr.split()
            if len(parts) == 5:
                minute, hour, _, _, days = parts
                day_names = ", ".join(WEEKDAYS.get(int(d), f"{d}") for d in days.split(",") if d.isdigit())
                label = f"{hour.zfill(2)}:{minute.zfill(2)} — {day_names}"
            else:
                label = expr
        except Exception:
            label = expr
    else:
        label = key

    await call.message.edit_text(f"✅ Расписание <b>{label}</b> удалено.", parse_mode="HTML")

@router.message()
async def fallback_handler(msg: Message):
    state = user_state.get(msg.from_user.id, {})
    if state.get("step") == "time":
        await handle_schedule_time_input(msg)
