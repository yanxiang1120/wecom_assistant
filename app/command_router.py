import asyncio
import datetime as dt
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeAlias


@dataclass(frozen=True)
class OutboundMessage:
    msg_type: str
    payload: dict[str, Any]


SendMessage: TypeAlias = Callable[[str, OutboundMessage], Awaitable[None]]


@dataclass
class CommandContext:
    user_id: str
    content: str
    send_message: SendMessage | None = None

    async def notify(self, msg_type: str, payload: dict[str, Any]) -> None:
        if self.send_message:
            await self.send_message(self.user_id, OutboundMessage(msg_type=msg_type, payload=payload))

    async def notify_text(self, content: str) -> None:
        await self.notify("text", {"content": content})

    async def notify_markdown(self, content: str) -> None:
        await self.notify("markdown", {"content": content})

    async def notify_textcard(self, title: str, description: str, url: str, btn: str = "详情") -> None:
        await self.notify(
            "textcard",
            {
                "title": title,
                "description": description,
                "url": url,
                "btn": btn,
            },
        )

    async def notify_image(self, media_path: str) -> None:
        await self.notify("image", {"media_path": media_path})

    async def notify_file(self, file_path: str) -> None:
        await self.notify("file", {"file_path": file_path})

    async def notify_news(self, articles: list) -> None:
        await self.notify("news", {"articles": articles})


Handler: TypeAlias = Callable[[str, CommandContext], Awaitable[None]]


class CommandRouter:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {
            "help": self._handle_help,
            "ping": self._handle_ping,
            "time": self._handle_time,
            "echo": self._handle_echo,
            "msgtest": self._handle_msg_test,
            "longtask": self._handle_longtask,
        }

    async def dispatch(self, ctx: CommandContext) -> None:
        text = (ctx.content or "").strip()
        if not text:
            await ctx.notify_text(self._help_text())
            return

        parts = text.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        handler = self._handlers.get(command)
        if not handler:
            await ctx.notify_text(f"未知指令: {command}\n\n" + self._help_text())
            return
        await handler(arg, ctx)

    async def _handle_help(self, arg: str, ctx: CommandContext) -> None:
        await ctx.notify_text(self._help_text())

    async def _handle_ping(self, arg: str, ctx: CommandContext) -> None:
        await ctx.notify_text("pong")

    async def _handle_time(self, arg: str, ctx: CommandContext) -> None:
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await ctx.notify_text(f"当前服务时间: {now}")

    async def _handle_echo(self, arg: str, ctx: CommandContext) -> None:
        if not arg:
            await ctx.notify_text("用法: echo 你的内容")
            return
        await ctx.notify_text(arg)

    async def _handle_msg_test(self, arg: str, ctx: CommandContext) -> None:
        # 任务卡片
        title = "任务卡片通知"
        description = "这是一个 textcard 示例消息。"
        await ctx.notify_textcard(
            title=title,
            description=description,
            url="https://github.com/yanxiang1120/wecom_assistant",
            btn="查看",
        )
        # markdown
        content = "`markdown` 通知" \
                  "\n您的会议室已经预定，稍后会同步到`邮箱`" \
                  "\n>**事项详情**" \
                  "\n>事　项：<font color=\"info\">开会</font>" \
                  "\n>组织者：@miglioguan" \
                  "\n>参与者：@miglioguan、@kunliu、@jamdeezhou、@kanexiong、@kisonwang" \
                  "\n>" \
                  "\n>会议室：<font color=\"info\">广州TIT 1楼 301</font>" \
                  "\n>日　期：<font color=\"warning\">2026年2月10日</font>" \
                  "\n>时　间：<font color=\"comment\">上午9:00-11:00</font>" \
                  "\n>" \
                  "\n>请准时参加会议。" \
                  "\n>" \
                  "\n>如需修改会议信息，请点击：[修改会议信息](https://github.com/yanxiang1120/wecom_assistant)"
        await ctx.notify_markdown(content)
        # Image
        script_path = os.path.dirname(__file__)
        project_path = os.path.abspath(os.path.dirname(script_path))
        await ctx.notify_image(f"{project_path}/tmp/goodluck.png")
        # File
        await ctx.notify_file(f"{project_path}/tmp/record.csv")
        # 图文卡片
        articles = [
            {
                "title": "标题1",
                "description": "简介1",
                "url": "https://github.com/yanxiang1120/wecom_assistant",
                "picurl": "https://avatars.githubusercontent.com/u/4798762?v=4"
            },
            {
                "title": "标题2",
                "description": "简介2",
                "url": "https://github.com/yanxiang1120/wecom_assistant",
                "picurl": "https://avatars.githubusercontent.com/u/4798762?v=4"
            },
            {
                "title": "标题3",
                "description": "简介3",
                "url": "https://github.com/yanxiang1120/wecom_assistant",
                "picurl": "https://avatars.githubusercontent.com/u/4798762?v=4"
            },
            {
                "title": "标题4",
                "description": "简介4",
                "url": "https://github.com/yanxiang1120/wecom_assistant",
                "picurl": "https://avatars.githubusercontent.com/u/4798762?v=4"
            }
        ]
        await ctx.notify_news(articles)

    async def _handle_longtask(self, arg: str, ctx: CommandContext) -> None:
        # task start
        await ctx.notify_text(f"任务开始执行。。。")
        # exec task
        seconds = 5
        await asyncio.sleep(seconds)
        # task finish
        await ctx.notify_markdown(f"**任务执行完成**\n耗时：`{seconds}` 秒")

    @staticmethod
    def _help_text() -> str:
        return (
            "可用指令:\n"
            "1) help - 查看帮助\n"
            "2) ping - 你还活着吗\n"
            "3) time - 返回服务当前时间\n"
            "4) echo <文本> - 回显文本\n"
            "5) msgtest - 消息模板测试\n"
            "6) longtask - 耗时任务模板\n"
        )
