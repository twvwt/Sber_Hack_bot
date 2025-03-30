import re
import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pyrogram import Client
from pyrogram.types import ChatPrivileges

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import or_f, Command, CommandStart, StateFilter
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, FSInputFile, Message, PollAnswer
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler


# Модифицируем класс TaskStorage для хранения информации о мероприятиях
# class TaskStorage:
#     def __init__(self):
#         self.tasks: Dict[int, List[Dict]] = defaultdict(list)
#         self.events: Dict[int, Dict] = {}  # {chat_id: event_data}

# task_storage = TaskStorage()


# Инициализация FastAPI
app = FastAPI()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = Router()

# Глобальные переменные
user_data: Dict[int, Dict] = {}
vote_results: Dict[int, Dict[str, Dict[str, List[str]]]] = defaultdict(
    lambda: {'location': defaultdict(list), 'products': defaultdict(list)}
)
discussion_data: Dict[int, Dict] = {}
organizers: Dict[int, int] = {}
proposal_messages: Dict[int, Dict[int, Tuple[int, str]]] = {}
saved_proposals: Dict[int, List[str]] = defaultdict(list)
original_messages: Dict[int, Dict[int, types.Message]] = {}

class TaskStorage:
    def __init__(self):
        self.tasks: Dict[int, List[Dict]] = defaultdict(list)

task_storage = TaskStorage()

class EventStates(StatesGroup):
    location = State()
    format = State()
    date = State()
    budget = State()
    guests = State()

# FastAPI endpoints
@app.get("/tasks/{chat_id}", response_class=HTMLResponse)
async def show_tasks(request: Request, chat_id: int):
    chat_id = int(chat_id)
    
    # Получаем данные из task_storage
    products_votes = vote_results.get(chat_id, {}).get('products', {})
    
    tasks = []
    participants = set()
    
    for option, voters in products_votes.items():
        tasks.append({
            'name': option,
            'voters': voters
        })
        participants.update(voters)
    
    current_assignments = task_storage.tasks.get(chat_id, [])
    
    return templates.TemplateResponse("tasks.html", {
        "request": request,
        "chat_id": chat_id,
        "tasks": tasks,
        "participants": list(participants),
        "assignments": current_assignments
    })

@app.post("/assign_task/{chat_id}")
async def assign_task(chat_id: int, request: Request):
    try:
        data = await request.json()
        task = data.get("task")
        user_id = data.get("user_id")
        deadline = data.get("deadline")
        
        if not all([task, user_id, deadline]):
            return JSONResponse({"status": "error", "message": "Missing required fields"}, status_code=400)
        
        chat_id = int(chat_id)
        user_id = int(user_id)
        
        task_storage.tasks[chat_id].append({
            "task": task,
            "assigned_to": user_id,
            "deadline": deadline,
            "status": "pending"
        })
        return {"status": "success"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/complete_task/{chat_id}")
async def complete_task(chat_id: int, request: Request):
    try:
        data = await request.json()
        task = data.get("task")
        
        if not task:
            return JSONResponse({"status": "error", "message": "Task is required"}, status_code=400)
        
        chat_id = int(chat_id)
        
        for assignment in task_storage.tasks.get(chat_id, []):
            if assignment["task"] == task:
                assignment["status"] = "completed"
                break
        return {"status": "success"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.post("/delete_task/{chat_id}")
async def delete_task(chat_id: int, request: Request):
    try:
        data = await request.json()
        task = data.get("task")
        
        if not task:
            return JSONResponse({"status": "error", "message": "Task is required"}, status_code=400)
        
        chat_id = int(chat_id)
        task_storage.tasks[chat_id] = [
            a for a in task_storage.tasks.get(chat_id, []) 
            if a["task"] != task
        ]
        return {"status": "success"}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
# Telegram Bot Handlers
@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer_photo(
        photo=FSInputFile('static/img/sber_logo.jpg'),
        caption="Добро пожаловать в бота для организации мероприятий!",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Создать мероприятие", callback_data="create_mp"),
                    InlineKeyboardButton(text="Мои мероприятия", callback_data="my_mp")
                ]
            ]
        ))

@router.callback_query(F.data == 'create_mp')
async def process_create_mp(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_data[user_id] = {}
    
    buttons = {
        'location': "📍 Место",
        'format': "🎭 Формат", 
        'date': "📅 Дата",
        'budget': "💰 Бюджет",
        'guests': "👥 Гости",
        'finish': "✅ Завершить"
    }
    
    await callback.message.edit_media(
        media=InputMediaPhoto(
            media=FSInputFile('static/img/sber_logo.jpg'),
            caption="Для организации мероприятия необходимо заполнить следующие данные:"
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=buttons['location'], callback_data="location"),
                    InlineKeyboardButton(text=buttons['format'], callback_data="format")
                ],
                [
                    InlineKeyboardButton(text=buttons['date'], callback_data="date"),
                    InlineKeyboardButton(text=buttons['budget'], callback_data="budget")
                ],
                [
                    InlineKeyboardButton(text=buttons['guests'], callback_data="guests")
                ],
                [
                    InlineKeyboardButton(text=buttons['finish'], callback_data="finish")
                ]
            ]
        )
    )
    await callback.answer()

@router.callback_query(F.data.in_(['location', 'format', 'date', 'budget', 'guests']))
async def process_event_data(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data_type = callback.data
    
    state_mapping = {
        'location': EventStates.location,
        'format': EventStates.format,
        'date': EventStates.date,
        'budget': EventStates.budget,
        'guests': EventStates.guests
    }
    await state.set_state(state_mapping[data_type])
    
    questions = {
        'location': 'Введите город(область), где бы вы хотели провести мероприятие:',
        'format': "Введите формат мероприятия (Например: свадьба, корпоратив, день рождения):",
        'date': 'Введите дату и время для мероприятия (Формат: ДД.ММ.ГГГГ):',
        'budget': "Какой бюджет на мероприятие? (Только цифры, мин. 10000)",
        'guests': "Сколько гостей планируется?"
    }
    
    await callback.message.answer(questions[data_type])
    await callback.answer()

@router.message(StateFilter(EventStates.location))
async def process_location(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data.setdefault(user_id, {})['location'] = message.text
    await send_updated_buttons(message, user_id)
    await state.clear()

@router.message(StateFilter(EventStates.format))
async def process_format(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data.setdefault(user_id, {})['format'] = message.text
    await send_updated_buttons(message, user_id)
    await state.clear()

@router.message(StateFilter(EventStates.date))
async def process_date(message: Message, state: FSMContext):
    user_id = message.from_user.id
    date_str = message.text.strip()
    
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_str):
        await message.answer("❌ Неверный формат даты. Введите дату в формате ДД.ММ.ГГГГ")
        return
    
    try:
        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
        if date_obj < datetime.now():
            await message.answer("❌ Дата не может быть в прошлом. Введите будущую дату")
            return
        
        user_data.setdefault(user_id, {})['date'] = date_str
        await send_updated_buttons(message, user_id)
        await state.clear()
    except ValueError:
        await message.answer("❌ Некорректная дата. Проверьте правильность дня и месяца")

@router.message(StateFilter(EventStates.budget))
async def process_budget(message: Message, state: FSMContext):
    user_id = message.from_user.id
    budget_str = message.text.strip()
    
    if not re.match(r'^\d+$', budget_str):
        await message.answer("❌ Бюджет должен быть целым числом. Введите сумму без пробелов и символов")
        return
    
    budget = int(budget_str)
    if budget < 10000:
        await message.answer("❌ Минимальный бюджет - 10000 рублей. Введите большую сумму")
        return
    
    user_data.setdefault(user_id, {})['budget'] = f"{budget} ₽"
    await send_updated_buttons(message, user_id)
    await state.clear()

@router.message(StateFilter(EventStates.guests))
async def process_guests(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_data.setdefault(user_id, {})['guests'] = message.text
    await send_updated_buttons(message, user_id)
    await state.clear()

async def send_updated_buttons(message: Message, user_id: int):
    event_data = user_data.get(user_id, {})
    buttons = {
        'location': f"📍 Место {'✅' if event_data.get('location') else ''}",
        'format': f"🎭 Формат {'✅' if event_data.get('format') else ''}",
        'date': f"📅 Дата {'✅' if event_data.get('date') else ''}",
        'budget': f"💰 Бюджет {'✅' if event_data.get('budget') else ''}",
        'guests': f"👥 Гости {'✅' if event_data.get('guests') else ''}",
        'finish': "✅ Завершить"
    }
    
    await message.answer_photo(
        photo=FSInputFile('static/img/sber_logo.jpg'),
        caption="Для организации мероприятия необходимо заполнить следующие данные:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=buttons['location'], callback_data="location"),
                    InlineKeyboardButton(text=buttons['format'], callback_data="format")
                ],
                [
                    InlineKeyboardButton(text=buttons['date'], callback_data="date"),
                    InlineKeyboardButton(text=buttons['budget'], callback_data="budget")
                ],
                [
                    InlineKeyboardButton(text=buttons['guests'], callback_data="guests")
                ],
                [
                    InlineKeyboardButton(text=buttons['finish'], callback_data="finish")
                ]
            ]
        )
    )




@router.callback_query(F.data == 'finish')
async def process_finish(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    event_data = user_data.get(user_id, {})
    if all(key in event_data for key in ['location', 'format', 'date', 'budget', 'guests']):
        summary = (
            "✅ Данные мероприятия сохранены:\n\n"
            f"📍 Город: {event_data['location']}\n"
            f"🎭 Формат: {event_data['format']}\n"
            f"📅 Дата: {event_data['date']}\n"
            f"💰 Бюджет: {event_data['budget']}\n"
            f"👥 Гости: {event_data['guests']}"
        )
        
        # Отправляем подтверждение пользователю
        await callback.message.answer(summary)
        await callback.answer("Мероприятие создано!")
        
        # Создаем группу и добавляем участников
        try:
            # Инициализируем Pyrogram клиент (укажите свои api_id и api_hash)
            pyro_app = Client(
                "my_session",
                api_id = 24373411,
                api_hash = '195b8f73d79491b07e658b1ca6dae0c9'
            )
            
            async with pyro_app:
                # Получаем информацию об организаторе
                organizer = await pyro_app.get_users(user_id)
                organizer_id = callback.from_user.id
                # Создаем группу с названием на основе формата мероприятия
                group_title = f"Мероприятие: {event_data['format']}"
                group_description = f"Организатор: {organizer.first_name}\nДата: {event_data['date']}"
                
                group = await pyro_app.create_supergroup(
                    title=group_title,
                    description=group_description
                )
                # Планируем напоминание
            # schedule_reminder(event_data, group.id, callback.bot)
                # Добавляем бота и организатора в группу
                await pyro_app.add_chat_members(
                    group.id,
                    ["win_hackaton_bot", organizer_id]  # Укажите username вашего бота
                )
                print(user_id)
                # Даем права администратора боту
                await pyro_app.promote_chat_member(
                    chat_id=group.id,
                    user_id="win_hackaton_bot",  # Укажите username вашего бота
                    privileges=ChatPrivileges(
                        can_manage_chat=True,
                        can_promote_members=True,
                        can_delete_messages=True,
                        can_invite_users=True,
                        can_restrict_members=True,
                        can_pin_messages=True,
                        can_change_info=True
                    )
                )
                
                # Даем права администратора организатору
                await pyro_app.promote_chat_member(
                    chat_id=group.id,
                    user_id=user_id,
                    privileges=ChatPrivileges(
                        can_manage_chat=True,
                        can_promote_members=True,
                        can_delete_messages=True,
                        can_invite_users=True,
                        can_restrict_members=True,
                        can_pin_messages=True,
                        can_change_info=True
                    )
                )
                
                # Отправляем данные о мероприятии в группу
                group_message = (
                    "🎉 Группа для мероприятия создана!\n\n"
                    f"📌 Организатор: {organizer.first_name} (@{organizer.username})\n"
                    f"📍 Место: {event_data['location']}\n"
                    f"🎭 Формат: {event_data['format']}\n"
                    f"📅 Дата: {event_data['date']}\n"
                    f"💰 Бюджет: {event_data['budget']}\n"
                    f"👥 Гостей: {event_data['guests']}\n\n"
                    "Для управления мероприятием используйте команды бота.\nДля того, чтобы начать обусуждение мероприятия введите команду /mp_start"
                )
                
                await pyro_app.send_message(
                    chat_id=group.id,
                    text=group_message
                )
                # await pyro_app.send_message(
                #     chat_id=7218590203,
                #     text= f'"Место:{event_data['location']}\nФормат:{event_data['format']}\nДата:{event_data['date']}Бюджет:{event_data['budget']}\nКоличество гостей:{event_data['guests']}Это данные, которые мне предоставили родственники, сформируй топ-5 мест, чтобы уложиться в бюджет.Сформируй JSON файлом в формате: ["место": [{"список вещей и продуктов:их стоимость(Количество:10)"},адрес, описание, погода].На русском в формате JSON без лишнего текста"'
                # )
                # Отправляем ссылку на группу организатору
                group_link = f"t.me/c/{group.id}/1"
                await callback.message.answer(
                    f"🎉 Группа для вашего мероприятия создана: {group_link}"
                )
                
        except Exception as e:
            print(f"Ошибка при создании группы: {e}")
# # Функция для планирования напоминания
# def schedule_reminder(event_date: datetime, chat_id: int, bot: Bot):
#     reminder_time = event_date - timedelta(days=1)
#     if reminder_time < datetime.now():
#         return  # Не планируем, если мероприятие уже скоро
        
#     scheduler.add_job(
#         send_reminder,
#         'date',
#         run_date=reminder_time,
#         args=[chat_id, bot],
#         id=f"reminder_{chat_id}"
#     )

# Функция отправки напоминания
async def send_reminder(chat_id: int, bot: Bot):
        event = task_storage.events.get(chat_id)
        if not event:
            return
            
        event_date = event['date']
        days_left = (event_date - datetime.now()).days
        
        await bot.send_message(
            chat_id=chat_id,
            text=f"⏰ Напоминание: до мероприятия '{event['title']}' остался 1 день!\n"
                 f"📅 Дата: {event_date.strftime('%d.%m.%Y')}\n\n"
                 "Проверьте готовность всех задач!"
        )
@router.message(Command('mp_start'))
async def start_discussion(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if chat_id in organizers and organizers[chat_id] != user_id:
        await message.answer("❌ Только организатор может запустить обсуждение!")
        return
    
    if chat_id not in organizers:
        organizers[chat_id] = user_id
    
    await message.answer(
        "⏱ Укажите время обсуждения и время опроса в формате:\n"
        "<code>/time минуты_обсуждения минуты_опроса</code>\n\n"
        "Пример: <code>/time 15 5</code>",
        parse_mode="HTML"
    )

@router.message(Command('time'))
async def set_discussion_times(message: Message, state: FSMContext):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if chat_id not in organizers or organizers[chat_id] != user_id:
        await message.answer("❌ Только организатор может устанавливать время!")
        return
    
    try:
        args = message.text.split()
        discussion_time = int(args[1])
        voting_time = int(args[2])
        
        # Сохраняем время в FSM
        await state.update_data(
            discussion_time=discussion_time,
            voting_time=voting_time
        )
        
        # Показываем подтверждение с возможностью изменить
        await message.answer(
            f"⏱ Установлено время:\n"
            f"Обсуждение: {discussion_time} мин\n"
            f"Голосование: {voting_time} мин\n\n"
            "Все верно?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Да, начать", callback_data="confirm_time"),
                        InlineKeyboardButton(text="🔄 Изменить", callback_data="change_time")
                    ]
                ]
            )
        )
        
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат времени. Используйте:\n"
            "<code>/time минуты_обсуждения минуты_опроса</code>\n\n"
            "Пример: <code>/time 15 5</code>",
            parse_mode="HTML"
        )

@router.callback_query(F.data == "confirm_time")
async def confirm_time_handler(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    chat_id = callback.message.chat.id
    
    discussion_data[chat_id] = {
        'current_stage': None,
        'discussion_time': data['discussion_time'],
        'voting_time': data['voting_time'],
        'end_time': None,
        'stage': 1
    }
    
    await callback.message.edit_text("⏱ Время установлено! Начинаем обсуждение...")
    await start_stage(chat_id, 1, callback.bot)
    await state.clear()

@router.callback_query(F.data == "change_time")
async def change_time_handler(callback: CallbackQuery):
    await callback.message.edit_text(
        "⏱ Укажите время обсуждения и время опроса в формате:\n"
        "<code>/time минуты_обсуждения минуты_опроса</code>\n\n"
        "Пример: <code>/time 15 5</code>",
        parse_mode="HTML"
    )
    await callback.answer()

async def start_stage(chat_id: int, stage_number: int, bot: Bot):
    if stage_number == 1:
        stage_name = "Выбор места мероприятия"
        stage_instructions = "Предлагайте варианты в формате:\n!ПРЕДЛОЖЕНИЕ Ваш вариант места"
        discussion_data[chat_id]['current_stage'] = 'location'
    else:
        stage_name = "Выбор продуктов и услуг"
        stage_instructions = "Предлагайте варианты в формате:\n!ПРЕДЛОЖЕНИЕ Ваш вариант продукта/услуги"
        discussion_data[chat_id]['current_stage'] = 'products'
    
    discussion_data[chat_id]['stage'] = stage_number
    saved_proposals[chat_id] = []
    
    await bot.send_message(
        chat_id=chat_id,
        text=f"🎉 Этап {stage_number}: {stage_name}\n\n{stage_instructions}"
    )
    
    discussion_time = discussion_data[chat_id]['discussion_time']
    end_time = datetime.now() + timedelta(minutes=discussion_time)
    discussion_data[chat_id]['end_time'] = end_time
    
    asyncio.create_task(discussion_timer(chat_id, stage_number, bot))

async def discussion_timer(chat_id: int, stage_number: int, bot: Bot):
    try:
        await asyncio.sleep(discussion_data[chat_id]['discussion_time'] * 60)
        await bot.send_message(chat_id, "⏰ Время обсуждения закончилось! Создаю опрос...")
        await create_polls(chat_id, stage_number, bot)
    except Exception as e:
        print(f"Ошибка в discussion_timer: {e}")
        await bot.send_message(chat_id, f"❌ Ошибка при создании опроса: {e}")

@router.message(F.text.startswith('!ПРЕДЛОЖЕНИЕ'))
async def handle_proposal(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in discussion_data or not discussion_data[chat_id]['current_stage']:
        return
    
    proposal_text = message.text.replace('!ПРЕДЛОЖЕНИЕ', '').strip()
    if not proposal_text:
        await message.reply("Пожалуйста, укажите предложение после !ПРЕДЛОЖЕНИЕ")
        return
    
    if proposal_text not in saved_proposals[chat_id]:
        saved_proposals[chat_id].append(proposal_text)
        await message.reply(f"✅ Предложение сохранено! Всего вариантов: {len(saved_proposals[chat_id])}")
    else:
        await message.reply("❌ Это предложение уже было добавлено ранее")

def create_voting_keyboard(stage_number: int, current_poll: int, total_polls: int):
    builder = InlineKeyboardBuilder()
    if current_poll == total_polls:
        builder.button(
            text="✅ Завершить голосование", 
            callback_data=f"finish_voting_{stage_number}"
        )
    return builder.as_markup()

async def create_polls(chat_id: int, stage_number: int, bot: Bot):
    try:
        proposals = saved_proposals.get(chat_id, [])
        if not proposals:
            await bot.send_message(chat_id, "❌ Ни одного предложения не поступило. Пропускаем этот этап.")
            return

        chunks = [proposals[i:i + 10] for i in range(0, len(proposals), 10)]
        
        for i, chunk in enumerate(chunks, 1):
            question = f"🏆 Голосование {i}/{len(chunks)} за {'место' if stage_number == 1 else 'продукты'}:"
            
            poll = await bot.send_poll(
                chat_id=chat_id,
                question=question,
                options=chunk,
                is_anonymous=False,
                allows_multiple_answers=(stage_number != 1),
                reply_markup=create_voting_keyboard(stage_number, i, len(chunks))
            )
            vote_results[chat_id][str(poll.poll.id)] = {
                'options': chunk,
                'question': question
            }
            
            await asyncio.sleep(1)

        saved_proposals.pop(chat_id, None)
        
    except Exception as e:
        print(f"Ошибка при создании опросов: {e}")
        await bot.send_message(chat_id, f"❌ Не удалось создать опросы: {e}")

@router.poll_answer()
async def handle_poll_answer(poll_answer: PollAnswer, bot: Bot):
    try:
        user_id = poll_answer.user.id
        for chat_id, polls in vote_results.items():
            if poll_answer.poll_id in polls:
                poll_info = polls[poll_answer.poll_id]
                selected_options = [poll_info['options'][i] for i in poll_answer.option_ids]
                
                # Сохраняем голоса в соответствующей категории
                stage = discussion_data.get(chat_id, {}).get('current_stage')
                if stage in ['location', 'products']:
                    for option in selected_options:
                        vote_results[chat_id][stage][option].append(user_id)
                
                break
    except Exception as e:
        print(f"Ошибка при обработке голоса: {e}")

@router.callback_query(F.data.startswith("finish_voting_"))
async def finish_voting(callback: types.CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    stage_number = int(callback.data.split("_")[-1])
    
    if chat_id not in organizers or organizers[chat_id] != callback.from_user.id:
        await callback.answer("❌ Только организатор может завершить голосование!", show_alert=True)
        return
    
    try:
        if stage_number == 1:
            await callback.message.answer("✅ Голосование за место завершено! Переходим к следующему этапу...")
            await asyncio.sleep(5)
            await start_stage(chat_id, 2, bot)
        else:
            # Сохраняем результаты голосования перед очисткой
            voting_results = vote_results.get(chat_id, {}).get('products', {})
            
            # Формируем задачи из результатов голосования
            tasks = []
            participants = set()
            
            for option, voters in voting_results.items():
                tasks.append(option)
                participants.update(voters)
            
            # Сохраняем в task_storage
            task_storage.tasks[chat_id] = []
            
            # Формируем URL
            web_url = f"http://127.0.0.1:8000/tasks/{chat_id}"
            
            await callback.message.answer(
                "🎉 Все этапы голосования завершены!",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="📋 Распределить задачи",
                                url=web_url
                            )
                        ]
                    ]
                )
            )
            
            # Очищаем данные только после сохранения
            discussion_data.pop(chat_id, None)
            saved_proposals.pop(chat_id, None)
        
        await callback.answer()
    except Exception as e:
        print(f"Ошибка при завершении голосования: {e}")
        await callback.answer("❌ Ошибка при завершении голосования", show_alert=True)

async def run_bot():
    bot = Bot(token="7610916683:AAFFyrf6TAH7qL0kPvjUhmXlv4Zl6YdakcU")
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import uvicorn
    from threading import Thread
    
    # Запуск FastAPI в отдельном потоке
    Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=8000)).start()
    
    # Запуск бота
    asyncio.run(run_bot())