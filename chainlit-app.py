import chainlit as cl
import requests
import json
from sseclient import SSEClient

RAG_URL = "http://rag-query:3000/v1/chat/completions"
MODEL = "tag-service"

MAX_HISTORY = 10  # keep last N messages only


def build_messages(history):
    """
    Convert stored history into OpenAI-style messages
    """
    messages = []
    for h in history:
        messages.append({
            "role": h["role"],
            "content": h["content"]
        })
    return messages


@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("history", [])
    await cl.Message(
        content="🧠 RAG assistant ready. Ask anything."
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    history = cl.user_session.get("history", [])

    # Add user message to memory
    history.append({"role": "user", "content": message.content})
    history = history[-MAX_HISTORY:]

    payload = {
        "model": MODEL,
        "messages": build_messages(history),
        "stream": True
    }

    msg = cl.Message(content="")
    await msg.send()

    assistant_reply = ""

    try:
        with requests.post(
            RAG_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            stream=True,
            timeout=120,
        ) as response:
            response.raise_for_status()

            client = SSEClient(response)

            for event in client.events():
                if event.data == "[DONE]":
                    break

                data = json.loads(event.data)

                delta = (
                    data.get("choices", [{}])[0]
                    .get("delta", {})
                    .get("content")
                )

                if delta:
                    assistant_reply += delta
                    await msg.stream_token(delta)

    except Exception as e:
        error_msg = f"\n❌ Streaming error: {e}"
        assistant_reply += error_msg
        await msg.stream_token(error_msg)

    # Save assistant reply to memory
    history.append({"role": "assistant", "content": assistant_reply})
    history = history[-MAX_HISTORY:]
    cl.user_session.set("history", history)

    await msg.update()