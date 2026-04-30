"""FlightAI — a multimodal airline customer-support assistant.

Combines:
  * GPT-4.1-mini chat with function/tool calling
  * SQLite-backed ticket-price lookup
  * DALL·E-3 destination image generation
  * gpt-4o-mini-tts spoken replies
  * Gradio Blocks UI tying chat, image, and audio together
"""

import base64
import json
import os
import sqlite3
from io import BytesIO

import gradio as gr
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

CHAT_MODEL = "gpt-4.1-mini"
IMAGE_MODEL = "dall-e-3"
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "onyx"
DB_PATH = "prices.db"

SYSTEM_MESSAGE = (
    "You are a helpful assistant for an Airline called FlightAI. "
    "Give short, courteous answers, no more than 1 sentence. "
    "Always be accurate. If you don't know the answer, say so. "
    "Whenever the user mentions a destination city — even casually, in a booking, "
    "or while asking a question — call the get_ticket_price tool with that city "
    "so we can quote a price and show a preview."
)

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def get_ticket_price(city: str) -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT price FROM prices WHERE city = ?", (city.lower(),)
        ).fetchone()
    if row:
        return f"Ticket price to {city} is ${row[0]}"
    return f"No fixed price on file for {city}; please contact the desk for a custom quote."


PRICE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_ticket_price",
        "description": "Get the price of a return ticket to the destination city.",
        "parameters": {
            "type": "object",
            "properties": {
                "destination_city": {
                    "type": "string",
                    "description": "The city that the customer wants to travel to",
                },
            },
            "required": ["destination_city"],
            "additionalProperties": False,
        },
    },
}
TOOLS = [PRICE_TOOL]


def handle_tool_calls(message):
    responses, cities = [], []
    for tool_call in message.tool_calls:
        if tool_call.function.name == "get_ticket_price":
            city = json.loads(tool_call.function.arguments).get("destination_city")
            cities.append(city)
            responses.append({
                "role": "tool",
                "content": get_ticket_price(city),
                "tool_call_id": tool_call.id,
            })
    return responses, cities


def artist(city: str) -> Image.Image:
    response = client().images.generate(
        model=IMAGE_MODEL,
        prompt=(
            f"An image representing a vacation in {city}, showing tourist spots "
            f"and everything unique about {city}, in a vibrant pop-art style"
        ),
        size="1024x1024",
        n=1,
        response_format="b64_json",
    )
    return Image.open(BytesIO(base64.b64decode(response.data[0].b64_json)))


def talker(message: str) -> bytes:
    response = client().audio.speech.create(model=TTS_MODEL, voice=TTS_VOICE, input=message)
    return response.content


def chat(history):
    history = [{"role": h["role"], "content": h["content"]} for h in history]
    messages = [{"role": "system", "content": SYSTEM_MESSAGE}] + history
    response = client().chat.completions.create(model=CHAT_MODEL, messages=messages, tools=TOOLS)

    cities = []
    while response.choices[0].finish_reason == "tool_calls":
        message = response.choices[0].message
        tool_responses, called_cities = handle_tool_calls(message)
        cities.extend(called_cities)
        messages.append(message)
        messages.extend(tool_responses)
        response = client().chat.completions.create(model=CHAT_MODEL, messages=messages, tools=TOOLS)

    reply = response.choices[0].message.content
    history.append({"role": "assistant", "content": reply})

    voice = talker(reply)
    image = artist(cities[0]) if cities else None
    return history, voice, image


def put_message_in_chatbot(message, history):
    return "", history + [{"role": "user", "content": message}]


def build_ui():
    with gr.Blocks(title="FlightAI") as ui:
        gr.Markdown("# ✈️ FlightAI — Multimodal Airline Assistant")
        with gr.Row():
            chatbot = gr.Chatbot(height=500)
            image_output = gr.Image(height=500, interactive=False, label="Destination preview")
        with gr.Row():
            audio_output = gr.Audio(autoplay=True, label="Spoken reply")
        with gr.Row():
            message = gr.Textbox(label="Chat with our AI Assistant:", placeholder="Ask about ticket prices to London, Paris, Tokyo...")

        message.submit(
            put_message_in_chatbot,
            inputs=[message, chatbot],
            outputs=[message, chatbot],
        ).then(
            chat,
            inputs=chatbot,
            outputs=[chatbot, audio_output, image_output],
        )
    return ui


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. Copy .env.example to .env and add your key.")
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"{DB_PATH} not found. Run `python init_db.py` first.")
    build_ui().launch(inbrowser=True)
