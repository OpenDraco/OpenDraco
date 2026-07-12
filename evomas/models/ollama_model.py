
import json
from pydantic import BaseModel
import sys
from typing import Optional, List, Any, Dict, Literal
import ollama
from ollama import ChatResponse, Message
from enum import Enum
import traceback


class OllamaModelEnum(str, Enum):
    QWEN_35_9B = "qwen3.5:9b"


class MessageRoleEnum(str, Enum):
    user = "user"
    system = "system"
    assistant = "assistant"
    tool = "tool"


class OllamaWrapper:
    def __init__(self) -> None:
        self.chat_history: List[Dict[str, Any]] = []

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: OllamaModelEnum = OllamaModelEnum.QWEN_35_9B,
        think: bool | Literal["low", "medium", "high"] = True,
        num_ctx: int = 2048,
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Any] = None,
        timeout_seconds: Optional[int] = None,
        stream: bool = True,
        temperature: float = 0.8,
        top_k: int = 40,
        top_p: float = 0.9,
        min_p: float = 0.0,
        repeat_penalty: float = 1.1,
        repeat_last_n: int = 64,
        seed: int = 0,
        stop: Optional[List[str]] = None,
        num_predict: int = -1,
    ) -> ChatResponse:

        self.chat_history.extend(messages)

        options = {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "top_k": top_k,
            "top_p": top_p,
            "min_p": min_p,
            "repeat_penalty": repeat_penalty,
            "repeat_last_n": repeat_last_n,
            "seed": seed,
            "num_predict": num_predict,
        }

        if stop is not None:
            options["stop"] = stop

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": self.chat_history,
            "options": options,
            "stream": stream,
            "think": think,
            "keep_alive": "5m",
            "tools": tools,
        }

        if response_format and issubclass(response_format, BaseModel):
            kwargs["format"] = response_format.model_json_schema()

        try:
            if stream:
                response_iterator = ollama.chat(**kwargs)
                print("\033[92m--- Streaming Output ---\033[0m")

                full_content = ""
                thinking = ""
                final_chunk = None
                tool_calls = []

                in_thinking_mode = False
                has_started_content = False

                for chunk in response_iterator:
                    final_chunk = chunk

                    if getattr(chunk.message, "thinking", None):
                        if not in_thinking_mode:
                            in_thinking_mode = True
                            print("\033[90m--- Streaming Thinking Process ---\033[0m")

                        thought_chunk = chunk.message.thinking
                        print(f"\033[90m{thought_chunk}\033[0m", end="", flush=True)
                        thinking += thought_chunk

                    elif getattr(chunk.message, "content", None):
                        if in_thinking_mode or not has_started_content:
                            in_thinking_mode = False
                            has_started_content = True
                            print("\n\033[92m--- Streaming Final Output ---\033[0m")

                        content_chunk = chunk.message.content
                        print(content_chunk, end="", flush=True)
                        full_content += content_chunk

                    if getattr(chunk.message, "tool_calls", None):
                        tool_calls = chunk.message.tool_calls

                if full_content or thinking:
                    print()

                msg = Message(
                    role=MessageRoleEnum.assistant.value,
                    content=full_content,
                    tool_calls=tool_calls if tool_calls else None,
                    thinking=thinking if thinking else None,
                )

                response = ChatResponse(
                    model=getattr(final_chunk, "model", model),
                    created_at=getattr(final_chunk, "created_at", ""),
                    message=msg,
                    done=True,
                    total_duration=getattr(final_chunk, "total_duration", 0),
                    load_duration=getattr(final_chunk, "load_duration", 0),
                    prompt_eval_count=getattr(final_chunk, "prompt_eval_count", 0),
                    prompt_eval_duration=getattr(
                        final_chunk, "prompt_eval_duration", 0
                    ),
                    eval_count=getattr(final_chunk, "eval_count", 0),
                    eval_duration=getattr(final_chunk, "eval_duration", 0),
                )

            else:
                response: ChatResponse = ollama.chat(**kwargs)

            msg = response.message
            if msg:
                history_msg = {"role": msg.role, "content": msg.content or ""}
                if msg.tool_calls:
                    history_msg["tool_calls"] = [
                        {
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ]
                self.chat_history.append(history_msg)
            return response

        except ollama.ResponseError as oe:
            error_message = f"Ollama API ResponseError ({oe.status_code}): {str(oe)}"
            print(f"\n\033[91m[!] {error_message}\033[0m")
            print("\033[91m[!] Full Traceback:\033[0m")
            traceback.print_exc()

            return ChatResponse(
                message=Message(role="assistant", content=error_message),
                done=True,
            )

        except Exception as e:
            error_message = f"Ollama API General Error: {str(e)}"
            print(f"\n\033[91m[!] {error_message}\033[0m")
            print("\033[91m[!] Full Traceback:\033[0m")
            traceback.print_exc()

            return ChatResponse(
                message=Message(role="assistant", content=error_message),
                done=True,
            )

    @staticmethod
    def print_response(response: ChatResponse) -> None:
        OllamaWrapper.print_message(response.message)
        OllamaWrapper.print_metrics(response)

    @staticmethod
    def print_message(message: Message) -> None:
        if not message:
            return

        thinking = message.thinking
        if thinking:
            print("\033[90m--- Thinking Process ---\033[0m")
            print(f"\033[90m{thinking.strip()}\033[0m")

        if message.tool_calls:
            print("\033[94m--- Tool Calls Requested ---\033[0m")
            for tc in message.tool_calls:
                print(f"Tool Name: {tc.function.name}")
                print(f"Arguments: {json.dumps(tc.function.arguments, indent=2)}")

        if message.content:
            print("\033[92m--- Final Output ---\033[0m")
            raw_content = message.content.strip()
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            safe_content = raw_content.encode(encoding, errors="replace").decode(
                encoding, errors="replace"
            )
            print(safe_content)

    @staticmethod
    def print_metrics(response: ChatResponse) -> None:
        if not response:
            return

        print("\033[93m--- Execution Metrics ---\033[0m")
        ns_to_s = lambda ns: round(ns / 1e9, 2) if ns else 0.0

        print(f"Total Duration:        {ns_to_s(response.total_duration)} s")
        print(f"Load Duration:         {ns_to_s(response.load_duration)} s")
        print(f"Prompt Eval Count:     {response.prompt_eval_count} tokens")
        print(f"Prompt Eval Duration:  {ns_to_s(response.prompt_eval_duration)} s")
        print(f"Eval Count:            {response.eval_count} tokens")
        print(f"Eval Duration:         {ns_to_s(response.eval_duration)} s")

        tokens_used = (response.prompt_eval_count or 0) + (response.eval_count or 0)

        print(f"Total Tokens Used:     {tokens_used} tokens")
