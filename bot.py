# bot.py

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

# Import our settings and the API client instance
from app.core.setting import settings
from app.core.API_Client import APIClient,api_client

from aiogram.client.default import DefaultBotProperties #


# --- Placeholder Handlers (We will replace these later) ---
# We create dummy handlers for each role to test the routing logic.
# In the future, these will be imported from app/admin/handlers.py, etc.

async def handle_admin_message(message: Message, user_role: str):
    await message.answer(f"Hello admin! Your message was: '{message.text}'\nYour confirmed role is: {user_role}")


async def handle_casher_message(message: Message, user_role: str):
    await message.answer(f"Hello casher! Your message was: '{message.text}'\nYour confirmed role is: {user_role}")


async def handle_consultant_message(message: Message, user_role: str):
    await message.answer(f"Hello consultant! Your message was: '{message.text}'\nYour confirmed role is: {user_role}")


async def handle_patient_message(message: Message, user_role: str):
    await message.answer(f"Welcome, Patient! Your message was: '{message.text}'\nWe see you as a: {user_role}")


# A dictionary to map role names to their handler functions
ROLE_HANDLERS = {
    "admin": handle_admin_message,
    "casher": handle_casher_message,
    "consultant": handle_consultant_message,
    "Patient": handle_patient_message,
}


# --- The Main Dispatcher Logic ---
async def role_based_dispatcher(message: Message, bot: Bot):
    """
    This is the core logic of our bot.
    1. It gets the user's role from the API.
    2. It calls the appropriate handler based on the role.
    """
    telegram_id = message.from_user.id
    try:
        # Get user role from our API client
        user_role = await api_client.get_user_role(telegram_id)

        # If get_user_role returns None or an unrecognized role, default to "Patient"
        if not user_role or user_role not in ROLE_HANDLERS:
            logging.warning(f"User {telegram_id} has role '{user_role}', which has no handler. Defaulting to Patient.")
            user_role = "Patient"

        # Get the correct handler function from our mapping
        handler_function = ROLE_HANDLERS[user_role]

        # Call the handler and pass the message and role
        await handler_function(message=message, user_role=user_role)

    except Exception as e:
        logging.error(f"Failed to process message for user {telegram_id}: {e}")
        await message.answer("An error occurred while processing your request. Please try again later.")


# --- Bot Startup and Shutdown Logic ---
async def main() -> None:
    # Initialize Bot instance with a default parse mode which will be passed to all API calls
    default_properties = DefaultBotProperties(parse_mode=ParseMode.HTML)

    bot = Bot(settings.BOT_TOKEN.get_secret_value(), default=default_properties)

    # Create a Dispatcher instance
    dp = Dispatcher()

    # The most important part: Register our role dispatcher to handle ALL messages
    # This function will now act as a gatekeeper for every incoming message.
    dp.message.register(role_based_dispatcher)

    # A simple handler for the /start command to give a welcome message
    # This will be caught by role_based_dispatcher as well, which is fine.
    # @dp.message(CommandStart())
    # async def command_start_handler(message: Message) -> None:
    #     await message.answer(f"Hello, {message.from_user.full_name}! Welcome to Fazel Pharma.")

    # --- Initial API Login ---
    # Try to log in to the API when the bot starts.
    # If it fails, the bot will not start.
    try:
        # This will trigger the _login method in our APIClient
        await api_client._get_valid_token()
    except Exception as e:
        logging.critical(f"Could not connect to API on startup. Shutting down. Error: {e}")
        return  # Exit the main function if API login fails

    # Start polling
    try:
        await dp.start_polling(bot)
    finally:
        # Close the API client's session on shutdown
        await api_client.close()
        logging.info("Bot stopped and API client session closed.")


if __name__ == "__main__":
    if __name__ == "__main__":
        logging.basicConfig(level=logging.INFO)
        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            logging.warning("Bot stopped by user.")